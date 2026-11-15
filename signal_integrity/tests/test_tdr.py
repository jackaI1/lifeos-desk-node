"""TDR inversion checked against a reflection with a known impedance."""

import numpy as np
import pytest

from signal_integrity.tdr import tdr_impedance, uniform_grid

STEP = 50e6
FREQ = np.arange(1, 121) * STEP          # 50 MHz to 6 GHz, as the openEMS model uses


def _single_reflection(z_ohm: float, delay_s: float, z0: float = 50.0) -> np.ndarray:
    rho = (z_ohm - z0) / (z_ohm + z0)
    return rho * np.exp(-2j * np.pi * FREQ * 2 * delay_s)


@pytest.mark.parametrize("z_ohm", [40.0, 50.0, 75.0])
def test_step_recovers_the_impedance_after_the_reflection(z_ohm):
    delay = 1e-9
    t, z = tdr_impedance(FREQ, _single_reflection(z_ohm, delay))
    after = (t > 2 * delay + 0.3e-9) & (t < 2 * delay + 0.9e-9)
    before = t < delay
    assert float(np.mean(z[after])) == pytest.approx(z_ohm, rel=0.02)
    assert float(np.mean(z[before])) == pytest.approx(50.0, rel=0.02)


def test_time_axis_starts_at_zero_with_the_expected_step():
    t, _ = tdr_impedance(FREQ, np.zeros(len(FREQ), dtype=complex))
    assert t[0] == 0.0
    assert t[1] - t[0] == pytest.approx(1.0 / (4096 * STEP))


def test_matched_line_gives_50_ohm_everywhere():
    t, z = tdr_impedance(FREQ, np.zeros(len(FREQ), dtype=complex))
    assert np.allclose(z, 50.0)


def test_uneven_frequencies_are_refused():
    with pytest.raises(ValueError):
        uniform_grid(np.array([1.0, 2.0, 4.0, 5.0]))


def test_grid_that_does_not_start_at_one_step_is_refused():
    with pytest.raises(ValueError):
        uniform_grid(np.array([2.0, 3.0, 4.0]))


def test_length_mismatch_is_refused():
    with pytest.raises(ValueError):
        tdr_impedance(FREQ, np.zeros(10, dtype=complex))
