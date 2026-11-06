"""Seeded channel errors perturb the measured signals, not the final error percentage."""

import math
from dataclasses import dataclass, fields

import numpy as np

from .waveforms import Samples, energy_wh


@dataclass(frozen=True)
class ChannelError:
    voltage_gain_pct: float = 0
    current_gain_pct: float = 0
    phase_error_deg: float = 0  # Positive means an additional current lag.
    voltage_offset_v: float = 0
    current_offset_a: float = 0
    power_offset_w: float = 0  # Residual active-power bias per element.

    def __post_init__(self):
        if not all(math.isfinite(getattr(self, f.name)) for f in fields(self)):
            raise ValueError("all channel errors must be finite")


@dataclass(frozen=True)
class Meter:
    id: str
    channels: tuple[ChannelError, ...]

    def read_wh(self, samples: Samples) -> float:
        phases = samples.voltage.shape[0]
        if len(self.channels) < phases:
            raise ValueError("meter has fewer measurement channels than the waveform")
        channels = self.channels[:phases]

        def column(name):
            return np.array([getattr(c, name) for c in channels])[:, None]

        delta = np.deg2rad(column("phase_error_deg"))
        shifted_i = samples.current * np.cos(delta) - samples.current_quadrature * np.sin(delta)
        measured_v = samples.voltage * (1 + column("voltage_gain_pct") / 100)
        measured_v = measured_v + column("voltage_offset_v")
        measured_i = shifted_i * (1 + column("current_gain_pct") / 100)
        measured_i = measured_i + column("current_offset_a")
        residual = sum(c.power_offset_w for c in channels) * samples.duration_s / 3600
        return float(energy_wh(measured_v, measured_i, samples.sample_rate) + residual)


def make_meter(
    seed: int,
    index: int,
    *,
    gain_shift_pct: float = 0,
    phase_shift_deg: float = 0,
    offset_shift_w: float = 0,
    prefix: str = "UUT",
) -> Meter:
    """Independent seed per unit makes prefixes reproducible when batch length changes."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, index]))
    errors = rng.normal(size=(3, 6)) * [0.012, 0.025, 0.015, 0.002, 0.00002, 0.003]
    errors[:, 1] += gain_shift_pct
    errors[:, 2] += phase_shift_deg
    errors[:, 5] += offset_shift_w
    return Meter(
        f"{prefix}-{index + 1:03d}",
        tuple(ChannelError(*(float(value) for value in row)) for row in errors),
    )
