"""Measurements from simulated samples, with explicit reference voltages."""

import numpy as np

from pdn.model import Study


def ac_metrics(frequency, z, target):
    f, magnitude = np.asarray(frequency), np.abs(z)
    peaks = (
        np.flatnonzero((magnitude[1:-1] > magnitude[:-2]) & (magnitude[1:-1] > magnitude[2:])) + 1
    )
    above = magnitude > target
    crossings = np.flatnonzero(above[:-1] != above[1:])
    boundaries = []
    if above[0]:
        boundaries.append(float(f[0]))
    for i in crossings:
        fraction = (target - magnitude[i]) / (magnitude[i + 1] - magnitude[i])
        boundaries.append(
            float(10 ** (np.log10(f[i]) + fraction * (np.log10(f[i + 1]) - np.log10(f[i]))))
        )
    if above[-1]:
        boundaries.append(float(f[-1]))
    worst = int(np.argmax(magnitude))
    return {
        "sampled_range_hz": [float(f[0]), float(f[-1])],
        "target_ohm": float(target),
        "max_ohm": float(magnitude[worst]),
        "max_frequency_hz": float(f[worst]),
        "meets_target": bool(np.all(~above)),
        "above_target_bands_hz": [boundaries[i : i + 2] for i in range(0, len(boundaries), 2)],
        "peaks": [
            {"frequency_hz": float(f[i]), "impedance_ohm": float(magnitude[i])} for i in peaks
        ],
    }


def transient_metrics(model: Study, time, voltage):
    # Reference the simulated operating point before the step, not the unloaded 0.9 V source.
    baseline = float(np.mean(voltage[time < model.delay_s * 0.9]))
    after = np.flatnonzero(time >= model.delay_s)
    low = int(after[np.argmin(voltage[after])])
    minimum = float(voltage[low])
    droop = baseline - minimum
    return {
        "baseline_v": baseline,
        "minimum_v": minimum,
        "minimum_time_s": float(time[low]),
        "droop_v": droop,
        "nominal_drop_v": model.nominal_v - minimum,
        "overshoot_v": float(np.max(voltage[after])) - baseline,
        "droop_budget_v": model.droop_budget_v,
        "meets_droop_budget": bool(droop <= model.droop_budget_v),
    }
