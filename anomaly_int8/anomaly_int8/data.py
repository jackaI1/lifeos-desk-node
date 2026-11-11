"""Room-log windows for the desk node's anomaly detector.

The log format matches the one the room analysis tool reads: timestamp,
temperature_mc, humidity_mpermil (integer milli-degrees and thousandths of a
percent, exactly as the device sends them), plus an `anomaly` column (0 or 1)
that marks the readings I injected faults into. A real export from the adapter
database has no `anomaly` column and can be used for training as it is.
"""
import csv
from pathlib import Path

import numpy as np

WINDOW = 4                       # readings per model input
FEATURES = 2 * WINDOW            # four temperatures, then four humidities
CENTRE_MC = 22000                # 22 C: the room's typical temperature
CENTRE_MPERMIL = 45000           # 45 %RH: the room's typical humidity
TEMP_STEP_MC = 100               # the int8 input unit for temperature: 0.1 C
HUMIDITY_STEP_MPERMIL = 500      # the int8 input unit for humidity: 0.5 %RH
STEPS = np.array([TEMP_STEP_MC] * WINDOW + [HUMIDITY_STEP_MPERMIL] * WINDOW, dtype=np.int64)
PERIOD_SECONDS = 300             # the device wakes about every five minutes
# The anomaly column stores 0 for a normal reading or the code of the injected fault.
ANOMALY_NAMES = {1: 'spike', 2: 'stuck', 3: 'humidity_jump', 4: 'dropout'}
ANOMALY_KINDS = tuple(ANOMALY_NAMES.values())


def make_log(days=21, seed=11):
    """Return (timestamps, temperature_mc, humidity_mpermil, anomaly) for a synthetic room."""
    rng = np.random.default_rng(seed)
    count = days * 86400 // PERIOD_SECONDS
    seconds = np.arange(count) * PERIOD_SECONDS
    temperature = (22.0 + 0.9 * np.sin(2 * np.pi * seconds / 86400)
                   + 0.5 * np.sin(2 * np.pi * seconds / 5400)
                   + rng.normal(0, 0.12, count))
    humidity = 45.0 - 1.2 * (temperature - 22.0) + rng.normal(0, 0.8, count)
    temperature_mc = np.round(temperature * 1000).astype(np.int64)
    humidity_mpermil = np.round(np.clip(humidity, 20.0, 80.0) * 1000).astype(np.int64)
    anomaly = np.zeros(count, dtype=np.int64)
    position = WINDOW + int(rng.integers(0, 40))
    kind_index = 0
    while position < count - 4:
        code = 1 + kind_index % len(ANOMALY_NAMES)
        kind_index += 1
        if code == 1:          # spike: one temperature reading 6 C too high
            temperature_mc[position] += 6000
            anomaly[position] = code
        elif code == 2:        # stuck: the sensor repeats its last reading for four samples
            span = slice(position, position + 4)
            temperature_mc[span] = temperature_mc[position - 1]
            humidity_mpermil[span] = humidity_mpermil[position - 1]
            anomaly[span] = code
        elif code == 3:        # humidity jump: 25 %RH too high for two samples
            humidity_mpermil[position:position + 2] += 25000
            anomaly[position:position + 2] = code
        else:                  # dropout: the sensor reports values far outside the room
            temperature_mc[position] = -40000
            humidity_mpermil[position] = 0
            anomaly[position] = code
        position += int(rng.integers(40, 110))
    return seconds + 1700000000, temperature_mc, np.clip(humidity_mpermil, 0, 100000), anomaly


def write_log(path, timestamps, temperature_mc, humidity_mpermil, anomaly):
    with Path(path).open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['timestamp', 'temperature_mc', 'humidity_mpermil', 'anomaly'])
        for row in zip(timestamps, temperature_mc, humidity_mpermil, anomaly):
            writer.writerow([int(value) for value in row])


def read_log(path):
    """Read a log CSV. The anomaly column is optional; a real log has none."""
    with Path(path).open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError('log has no readings')
    try:
        timestamps = np.array([int(r['timestamp']) for r in rows], dtype=np.int64)
        temperature = np.array([int(r['temperature_mc']) for r in rows], dtype=np.int64)
        humidity = np.array([int(r['humidity_mpermil']) for r in rows], dtype=np.int64)
    except (KeyError, ValueError) as exc:
        raise ValueError('expected integer timestamp, temperature_mc and humidity_mpermil columns') from exc
    if np.any(np.diff(timestamps) <= 0):
        raise ValueError('timestamps must increase')
    if np.any(temperature < -45000) or np.any(temperature > 130000):
        raise ValueError('temperature_mc outside the sensor range')
    if np.any(humidity < 0) or np.any(humidity > 100000):
        raise ValueError('humidity_mpermil outside 0 to 100 %RH')
    anomaly = (np.array([int(r.get('anomaly') or 0) for r in rows], dtype=np.int64)
               if 'anomaly' in rows[0] else np.zeros(len(rows), dtype=np.int64))
    if np.any(anomaly < 0) or np.any(anomaly > len(ANOMALY_NAMES)):
        raise ValueError('anomaly must be 0 for normal or a code from 1 to 4')
    return timestamps, temperature, humidity, anomaly


def deviations(temperature_mc, humidity_mpermil):
    """Integer deviations of each window from the room centre, in the device's milli-units."""
    return np.concatenate([temperature_mc - CENTRE_MC, humidity_mpermil - CENTRE_MPERMIL], axis=1)


def windows(temperature_mc, humidity_mpermil, anomaly):
    """Return (deviation_mc[N,8], kind[N], contaminated[N]).

    `kind` is the largest anomaly code among the window's readings (0 if none).
    A window is contaminated when any of its readings is injected, because a
    spike anywhere in the window changes what the model sees.
    """
    count = len(temperature_mc)
    if count < WINDOW:
        raise ValueError('need at least four readings')
    ends = np.arange(WINDOW - 1, count)
    index = ends[:, None] - np.arange(WINDOW - 1, -1, -1)[None, :]
    temp_windows = temperature_mc[index]
    hum_windows = humidity_mpermil[index]
    rows = np.concatenate([temp_windows - CENTRE_MC, hum_windows - CENTRE_MPERMIL], axis=1)
    kind = np.max(anomaly[index], axis=1)
    contaminated = kind > 0
    return rows.astype(np.int64), kind, contaminated


def unit_features(deviation_mc):
    """Float features in device units (0.1 C and 0.5 %RH steps), used for training."""
    return deviation_mc.astype(np.float32) / STEPS.astype(np.float32)


def split_indices(count):
    """Chronological split: 70 % training, 15 % threshold, 15 % held-out test."""
    train_end = int(count * 0.70)
    validation_end = int(count * 0.85)
    return slice(0, train_end), slice(train_end, validation_end), slice(validation_end, count)
