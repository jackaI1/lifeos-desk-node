"""Time-domain reflectometry (TDR) from a one-port S11 measured in frequency.

A TDR instrument sends a fast step and watches the reflection. The same result
comes from S11 by an inverse FFT: the impulse response of the reflection is
the inverse transform of S11, and its running sum is the step response. The
step response gives the impedance seen at each moment in time:

    rho(t)  = running sum of the impulse response (the reflection coefficient)
    Z(t)    = Z0 (1 + rho) / (1 - rho)

A discontinuity appears as a step in Z(t) at the round-trip time to it. A
Hann window in frequency trims ringing, at the cost of a slower edge.
"""

from typing import Tuple

import numpy as np


def uniform_grid(freq_hz) -> Tuple[float, int]:
    """Return (step, count) for a frequency list that starts at one step and is evenly spaced."""
    f = np.asarray(freq_hz, dtype=float)
    if len(f) < 3:
        raise ValueError("need at least three frequency points")
    step = f[1] - f[0]
    if not np.allclose(np.diff(f), step, rtol=1e-6, atol=0.0):
        raise ValueError("frequencies must be evenly spaced for the inverse FFT")
    if not np.isclose(f[0], step, rtol=1e-6):
        raise ValueError("the first frequency must equal the step (no gaps from DC)")
    return float(step), len(f)


def tdr_impedance(freq_hz, s11, z0: float = 50.0, n_fft: int = 4096) -> Tuple[np.ndarray, np.ndarray]:
    """Return (time_s, Z_ohm) for a one-port S11 on an evenly spaced grid starting at one step.

    The response is extended to DC by holding the lowest-frequency value, which is the
    usual choice when the measurement does not reach DC. n_fft zero-pads the spectrum,
    which sets the time resolution: dt = 1 / (n_fft * step).
    """
    step, count = uniform_grid(freq_hz)
    s = np.asarray(s11, dtype=complex)
    if len(s) != count:
        raise ValueError("s11 and frequencies must have the same length")
    if n_fft < 2 * count:
        raise ValueError("n_fft must be at least twice the number of frequency points")
    # One-sided spectrum from DC to the top frequency, with DC held at the first value.
    spectrum = np.concatenate([[s[0]], s])
    window = np.hanning(2 * count + 1)[count:]   # 1 at DC, falling to 0 at the top frequency
    windowed = spectrum * window
    impulse = np.fft.irfft(windowed, n=n_fft)
    rho = np.cumsum(impulse)
    # Keep the first part of the record: the reflection from the discontinuity arrives early.
    span = n_fft // 2
    time = np.arange(span) / (n_fft * step)
    rho = rho[:span]
    z = z0 * (1.0 + rho) / (1.0 - rho)
    return time, z
