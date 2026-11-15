"""Closed-form checks of the hand-calculation formulas in spice/hand.py."""

import math

import pytest

from spice import hand


def test_rise_factor_is_ln_7_over_3():
    # 30 %-70 % of a first-order step: t = RC ln(7/3) = 0.8473 RC.
    assert hand.RISE_30_70_FACTOR == pytest.approx(0.847298, rel=1e-6)


def test_i2c_rise_matches_the_exact_rc_crossing_times():
    r, c = 4700.0, 50e-12
    tau = r * c
    t30 = -tau * math.log(1 - 0.3)
    t70 = -tau * math.log(1 - 0.7)
    assert hand.rise_time_30_70(r, c) == pytest.approx(t70 - t30, rel=1e-12)


def test_rise_time_for_the_board_pullup_is_199_ns():
    # 4.7 kohm and 50 pF: RC = 235 ns, so the 30 %-70 % rise is 199.1 ns.
    assert hand.rise_time_30_70(4700, 50e-12) == pytest.approx(199.1e-9, rel=1e-3)


def test_max_pullup_meets_the_limit_exactly():
    r = hand.max_pullup_for_rise(300e-9, 50e-12)
    assert hand.rise_time_30_70(r, 50e-12) == pytest.approx(300e-9, rel=1e-12)
    assert r == pytest.approx(7081.0, rel=1e-3)


def test_min_pullup_from_sink_current():
    # (3.3 - 0.4) V / 3 mA = 967 ohm.
    assert hand.min_pullup_for_sink(3.3, 0.4, 0.003) == pytest.approx(966.67, rel=1e-3)


def test_inrush_ramp_reduces_to_c_dvdt_when_rc_is_short():
    # With RC (10 ns) much shorter than a 1 ms ramp, the current is C dV/dt = 0.05 A.
    peak = hand.inrush_peak_ramp(5.0, 0.001, 10e-6, 1e-3)
    assert peak == pytest.approx(5.0 * 10e-6 / 1e-3, rel=1e-2)


def test_inrush_ramp_peak_for_the_board_values():
    # Hand value for 0.3 ohm, 10 uF and a 1 us ramp: (5 * 10e-6 / 1e-6) (1 - e^(-1/3)).
    expected = 50.0 * (1 - math.exp(-1.0 / 3.0))
    assert hand.inrush_peak_ramp(5.0, 0.3, 10e-6, 1e-6) == pytest.approx(expected, rel=1e-12)
    assert hand.inrush_peak_ramp(5.0, 0.3, 10e-6, 1e-6) == pytest.approx(14.17, abs=0.01)


def test_input_drop_is_ohms_law_on_the_series_path():
    assert hand.input_voltage_under_load(5.0, 0.615, 0.3) == pytest.approx(4.8155)


def test_load_step_droop_is_i_times_r():
    assert hand.load_step_droop(0.6, 0.1) == pytest.approx(0.06)


def test_burst_ripple_goes_to_i_r_for_long_bursts():
    # A 0.2 ms burst is much longer than RC = 5.4 us, so the ripple is I R.
    ripple = hand.burst_ripple_pp(0.25, 0.1, 54.3e-6, 0.2e-3)
    assert ripple == pytest.approx(0.025, rel=1e-3)


def test_burst_ripple_is_small_for_short_bursts():
    # A burst of one time constant reaches only 63 % of I R.
    tau = 0.1 * 54.3e-6
    ripple = hand.burst_ripple_pp(0.25, 0.1, 54.3e-6, tau)
    assert ripple == pytest.approx(0.025 * (1 - math.exp(-1)), rel=1e-9)
