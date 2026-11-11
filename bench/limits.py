"""Pass/fail limits and the measurement math behind them.

Nothing here touches an instrument, so the logic can be tested directly:
ripple (peak-to-peak in a steady window), a rail's 90 % ready time, and
range checks against limits from limits.toml.
"""

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

REQUIRED_KEYS = {
    "supply": ("vbus_setpoint_v", "setpoint_tolerance_v", "max_input_current_ma"),
    "rail_vbus": ("tolerance_fraction",),
    "rail_3v3": ("nominal_v", "tolerance_fraction", "max_ripple_mvpp"),
    "sequence": ("ready_fraction", "min_delay_ms", "max_delay_ms"),
    "capture": ("window_ms", "points", "steady_window_ms"),
}


class ConfigError(ValueError):
    """The limits file is missing a section or a value."""


@dataclass(frozen=True)
class Limits:
    vbus_setpoint_v: float
    setpoint_tolerance_v: float
    max_input_current_ma: float
    vbus_tolerance_fraction: float
    v3v3_nominal_v: float
    v3v3_tolerance_fraction: float
    max_ripple_mvpp: float
    ready_fraction: float
    min_delay_ms: float
    max_delay_ms: float
    window_ms: float
    points: int
    steady_window_ms: float

    def __post_init__(self):
        if self.points < 16 or self.window_ms <= 0 or self.steady_window_ms <= 0:
            raise ConfigError("capture needs points >= 16 and positive windows")
        if self.steady_window_ms >= self.window_ms:
            raise ConfigError("steady_window_ms must be shorter than window_ms")
        if not 0 < self.ready_fraction < 1:
            raise ConfigError("ready_fraction must be between 0 and 1")
        if self.min_delay_ms > self.max_delay_ms:
            raise ConfigError("min_delay_ms is larger than max_delay_ms")


def load_limits(path) -> Limits:
    """Read limits.toml and fail loudly if a section or key is missing."""
    with Path(path).open("rb") as handle:
        data = tomllib.load(handle)
    for section, keys in REQUIRED_KEYS.items():
        if section not in data:
            raise ConfigError(f"missing [{section}] section")
        for key in keys:
            if key not in data[section]:
                raise ConfigError(f"missing {section}.{key}")
    supply, vbus, v3, seq, cap = (data[s] for s in ("supply", "rail_vbus", "rail_3v3", "sequence", "capture"))
    return Limits(
        vbus_setpoint_v=float(supply["vbus_setpoint_v"]),
        setpoint_tolerance_v=float(supply["setpoint_tolerance_v"]),
        max_input_current_ma=float(supply["max_input_current_ma"]),
        vbus_tolerance_fraction=float(vbus["tolerance_fraction"]),
        v3v3_nominal_v=float(v3["nominal_v"]),
        v3v3_tolerance_fraction=float(v3["tolerance_fraction"]),
        max_ripple_mvpp=float(v3["max_ripple_mvpp"]),
        ready_fraction=float(seq["ready_fraction"]),
        min_delay_ms=float(seq["min_delay_ms"]),
        max_delay_ms=float(seq["max_delay_ms"]),
        window_ms=float(cap["window_ms"]),
        points=int(cap["points"]),
        steady_window_ms=float(cap["steady_window_ms"]),
    )


def steady_slice(times_s: Sequence[float], window_ms: float) -> slice:
    """Index range covering the last `window_ms` of a record."""
    end = times_s[-1]
    start_time = end - window_ms / 1000.0
    start = next(i for i, t in enumerate(times_s) if t >= start_time)
    return slice(start, len(times_s))


def mean_and_ripple_pp(volts: Sequence[float]) -> tuple:
    """Mean voltage and peak-to-peak ripple (max - min) over a steady window."""
    if not volts:
        raise ValueError("empty steady window")
    return sum(volts) / len(volts), max(volts) - min(volts)


def crossing_time(times_s: Sequence[float], volts: Sequence[float], level: float) -> Optional[float]:
    """First time the waveform reaches `level`, interpolated between samples; None if never."""
    for i in range(1, len(volts)):
        if volts[i] >= level > volts[i - 1]:
            frac = (level - volts[i - 1]) / (volts[i] - volts[i - 1])
            return times_s[i - 1] + frac * (times_s[i] - times_s[i - 1])
    if volts and volts[0] >= level:
        return times_s[0]
    return None


@dataclass(frozen=True)
class Check:
    name: str
    measured: Optional[float]
    low: float
    high: float
    unit: str
    description: str

    @property
    def passed(self) -> bool:
        return self.measured is not None and not math.isnan(self.measured) and self.low <= self.measured <= self.high


def evaluate(limits: Limits, *, vbus_times, vbus_volts, v3_times, v3_volts, input_current_a: float) -> list:
    """Compute every check from captured waveforms and the measured input current."""
    steady = steady_slice(vbus_times, limits.steady_window_ms)
    v3_steady = steady_slice(v3_times, limits.steady_window_ms)
    vbus_mean, _ = mean_and_ripple_pp(vbus_volts[steady])
    v3_mean, v3_pp = mean_and_ripple_pp(v3_volts[v3_steady])

    vbus_ready = crossing_time(vbus_times, vbus_volts, limits.ready_fraction * limits.vbus_setpoint_v)
    v3_ready = crossing_time(v3_times, v3_volts, limits.ready_fraction * limits.v3v3_nominal_v)
    delay_ms = None if vbus_ready is None or v3_ready is None else (v3_ready - vbus_ready) * 1000.0

    v3_band = limits.v3v3_nominal_v * limits.v3v3_tolerance_fraction
    vbus_band = limits.vbus_setpoint_v * limits.vbus_tolerance_fraction
    return [
        Check("rail_vbus_mean_v", vbus_mean, limits.vbus_setpoint_v - vbus_band,
              limits.vbus_setpoint_v + vbus_band, "V", "steady VBUS within tolerance"),
        Check("rail_3v3_mean_v", v3_mean, limits.v3v3_nominal_v - v3_band,
              limits.v3v3_nominal_v + v3_band, "V", "steady 3V3 within tolerance"),
        Check("rail_3v3_ripple_mvpp", v3_pp * 1000.0, 0.0, limits.max_ripple_mvpp, "mVpp",
              "peak-to-peak ripple in the steady window"),
        Check("sequence_3v3_after_vbus_ms", delay_ms, limits.min_delay_ms, limits.max_delay_ms, "ms",
              "3V3 reaches 90 % after VBUS reaches 90 %"),
        Check("input_current_ma", input_current_a * 1000.0, 0.0, limits.max_input_current_ma, "mA",
              "steady current drawn from the 5 V supply"),
    ]
