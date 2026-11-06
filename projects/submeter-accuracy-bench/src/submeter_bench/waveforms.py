"""Uniform sample-cell integration and coherent single/three-phase sinusoidal signals."""

import math
from dataclasses import dataclass

import numpy as np

from .profile import TestPoint


def energy_wh(voltage: np.ndarray, current: np.ndarray, sample_rate: float) -> float:
    """Each simultaneous sample represents one full 1/sample_rate time cell."""
    v, i = np.asarray(voltage, dtype=float), np.asarray(current, dtype=float)
    if (
        v.ndim != 2
        or v.shape != i.shape
        or v.size == 0
        or not math.isfinite(sample_rate)
        or sample_rate <= 0
        or not np.isfinite(v).all()
        or not np.isfinite(i).all()
    ):
        raise ValueError("expected matching, nonempty finite (phase, sample) arrays and rate > 0")
    result = float(np.sum(v * i, dtype=np.float64) / sample_rate / 3600)
    if not math.isfinite(result):
        raise ValueError("energy overflow")
    return result


@dataclass(frozen=True)
class Samples:
    voltage: np.ndarray
    current: np.ndarray
    current_quadrature: np.ndarray
    sample_rate: float

    @property
    def duration_s(self) -> float:
        return self.voltage.shape[1] / self.sample_rate


def synthesize(
    point: TestPoint,
    *,
    sample_rate: float = 7200,
    cycles: int = 12,
    frequency: float = 60,
    voltage_rms: float = 120,
) -> Samples:
    """120 V is phase-to-neutral RMS; three-phase mode is four-wire, three-element."""
    if (
        not all(math.isfinite(x) and x > 0 for x in (sample_rate, cycles, frequency, voltage_rms))
        or int(cycles) != cycles
        or sample_rate <= 2 * frequency
    ):
        raise ValueError("positive finite settings, whole cycles and rate above Nyquist required")
    samples_per_cycle = sample_rate / frequency
    if not math.isclose(samples_per_cycle, round(samples_per_cycle), abs_tol=1e-10, rel_tol=0):
        raise ValueError("sample rate must give an integer number of samples per cycle")
    count = int(round(samples_per_cycle)) * int(cycles)
    angle = (2 * np.pi * frequency * np.arange(count) / sample_rate)[None, :]
    angle = angle - (np.arange(point.phases) * 2 * np.pi / 3)[:, None]
    phi = math.acos(point.power_factor) * (-1 if point.leading else 1)
    v = math.sqrt(2) * voltage_rms * np.sin(angle)
    i = math.sqrt(2) * point.current_a * np.sin(angle - phi)
    q = math.sqrt(2) * point.current_a * np.cos(angle - phi)
    for array in (v, i, q):
        array.setflags(write=False)
    return Samples(v, i, q, sample_rate)
