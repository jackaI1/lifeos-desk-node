"""PRBS7 OOK link: complex-field dispersion, square-law detection and receiver noise."""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LinkConfig:
    n_bits: int = 32768
    samples_per_bit: int = 32
    bit_rate_gbps: float = 10.0
    extinction_ratio_db: float = 10.0
    fiber_km: float = 20.0
    beta2_ps2_per_km: float = -21.7
    receiver_bandwidth_ghz: float = 7.0
    noise_std_mw: float = 0.0015
    seed: int = 2026

    def __post_init__(self):
        for name in ('n_bits', 'samples_per_bit', 'seed'):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f'{name} must be an integer')
        if not 127 <= self.n_bits <= 1_000_000:
            raise ValueError('n_bits must be 127..1000000')
        if not 8 <= self.samples_per_bit <= 128 or self.samples_per_bit % 2:
            raise ValueError('samples_per_bit must be even and 8..128')
        if self.n_bits * self.samples_per_bit > 16_000_000:
            raise ValueError('capture exceeds 16 million samples')
        if self.seed < 0:
            raise ValueError('seed must be nonnegative')
        # Deliberately broad supported ranges keep derived FFT arithmetic finite.
        ranges = dict(bit_rate_gbps=(.001, 1000), extinction_ratio_db=(.001, 100),
                      receiver_bandwidth_ghz=(.001, 1e6), fiber_km=(0, 10000),
                      noise_std_mw=(0, 100), beta2_ps2_per_km=(-10000, 10000))
        for name, (minimum, maximum) in ranges.items():
            value = getattr(self, name)
            if not np.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError(f'{name} must be finite and {minimum}..{maximum}')



@dataclass
class Capture:
    bits: np.ndarray
    samples_mw: np.ndarray
    decisions: np.ndarray
    threshold_mw: float


def prbs7(n_bits: int) -> np.ndarray:
    """Fibonacci LFSR x^7 + x^6 + 1, all-ones initial state, period 127."""
    if not isinstance(n_bits, int) or n_bits <= 0:
        raise ValueError('n_bits must be a positive integer')
    state = [1] * 7
    period = []
    for _ in range(127):
        period.append(state[-1])
        state = [state[-1] ^ state[-2]] + state[:-1]
    return np.resize(np.array(period, dtype=np.uint8), n_bits)


def acquire(config: LinkConfig, power_dbm: float) -> Capture:
    if not np.isfinite(power_dbm) or not -80 <= power_dbm <= 20:
        raise ValueError('received power must be finite and -80..20 dBm')
    bits = prbs7(config.n_bits)
    power_mw = 10 ** (power_dbm / 10)
    ratio = 10 ** (config.extinction_ratio_db / 10)
    low = 2 * power_mw / (1 + ratio)
    high = ratio * low
    field = np.sqrt(np.repeat(np.where(bits, high, low), config.samples_per_bit))
    # ps is used throughout the dispersion transfer function, avoiding mixed SI units.
    dt_ps = 1000 / (config.bit_rate_gbps * config.samples_per_bit)
    frequency_per_ps = np.fft.fftfreq(field.size, dt_ps)
    omega = 2 * np.pi * frequency_per_ps
    transfer = np.exp(-0.5j * config.beta2_ps2_per_km * config.fiber_km * omega**2)
    detected = np.abs(np.fft.ifft(np.fft.fft(field) * transfer))**2
    # Gaussian electrical response, -3 dB amplitude at configured bandwidth.
    bandwidth_per_ps = config.receiver_bandwidth_ghz / 1000
    response = np.exp(-np.log(2) / 2 * (frequency_per_ps / bandwidth_per_ps)**2)
    samples = np.fft.ifft(np.fft.fft(detected) * response).real
    # Common random numbers across power points reduce sweep variance; no clipping
    # after detection because electrical receiver noise can yield negative readings.
    samples += np.random.default_rng(config.seed).normal(0, config.noise_std_mw, samples.size)
    threshold = (high + low) / 2
    decisions = (samples[config.samples_per_bit // 2::config.samples_per_bit] > threshold)
    return Capture(bits, samples, decisions.astype(np.uint8), threshold)


def simulate_spectrum() -> tuple[np.ndarray, np.ndarray]:
    """Separate phenomenological laser spectrum, not the Fourier transform of PRBS data."""
    wavelength = np.linspace(1548.5, 1551.5, 3001)
    def gaussian(center, width):
        return np.exp(-4 * np.log(2) * ((wavelength - center) / width)**2)
    linear_mw = (gaussian(1550.0, 0.08) + 1e-3 * gaussian(1550.8, 0.06)
                 + 1e-4 * gaussian(1549.2, 0.06) + 1e-8)
    return wavelength, 10 * np.log10(linear_mw)
