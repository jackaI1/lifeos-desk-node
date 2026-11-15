"""Closed-form microstrip and via checks against the published formulas."""

import math

import pytest

from signal_integrity import impedance as z


def test_narrow_strip_formula_in_air():
    # er = 1 gives eps_eff = 1. For u = w/h = 0.5: Z = 60 ln(8/u + u/4) = 166.8 ohm.
    assert z.microstrip_z0(0.5, 1.0, 1.0) == pytest.approx(60.0 * math.log(16.125), rel=1e-9)


def test_wide_strip_formula_in_air():
    # For u = 2 (w = 2h) in air: Z = 120 pi / (u + 1.393 + 0.667 ln(u + 1.444)) = 89.38 ohm.
    expected = 120 * math.pi / (2 + 1.393 + 0.667 * math.log(3.444))
    assert z.microstrip_z0(2.0, 1.0, 1.0) == pytest.approx(expected, rel=1e-9)
    assert z.microstrip_z0(2.0, 1.0, 1.0) == pytest.approx(89.38, abs=0.01)


def test_both_branches_meet_at_u_equals_one():
    below = z.microstrip_z0(0.999999, 1.0, 4.5)
    above = z.microstrip_z0(1.000001, 1.0, 4.5)
    assert below == pytest.approx(above, rel=0.02)


def test_impedance_falls_as_the_trace_widens():
    widths = [0.15, 0.25, 0.5, 1.0, 2.0, 3.0, 4.0]
    values = [z.microstrip_z0(w, 1.6, 4.5, 0.035) for w in widths]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_fifty_ohm_width_on_the_board_stackup():
    # 1.6 mm FR-4 with er 4.5: about 3 mm of trace gives 50 ohm, and the copper thickness narrows it.
    w = z.width_for_z0(50.0, 1.6, 4.5, 0.035)
    assert 2.9 < w < 3.05
    assert z.microstrip_z0(w, 1.6, 4.5, 0.035) == pytest.approx(50.0, abs=1e-6)


def test_copper_thickness_lowers_impedance():
    # Thicker copper widens the effective strip, so the impedance is lower.
    assert z.microstrip_z0(0.25, 1.6, 4.5, 0.035) < z.microstrip_z0(0.25, 1.6, 4.5, 0.0)


def test_thickness_correction_is_zero_without_copper():
    assert z.thickness_corrected_width(0.25, 1.6, 0.0) == 0.25


def test_board_trace_impedances_are_in_the_expected_band():
    # The board's 0.25 mm trace is well above 50 ohm, so it is high impedance on this stackup.
    value = z.microstrip_z0(0.25, 1.6, 4.5, 0.035)
    assert 120 < value < 135


def test_via_formula_coaxial():
    # 60 / sqrt(er) ln(D / d): D/d = 4 in er 4.5 gives 39.2 ohm.
    assert z.via_z0(0.3, 1.2, 4.5) == pytest.approx(60 / math.sqrt(4.5) * math.log(4.0), rel=1e-12)
    assert z.via_z0(0.3, 1.2, 4.5) == pytest.approx(39.21, abs=0.01)


def test_via_antipad_must_be_larger_than_drill():
    with pytest.raises(ValueError):
        z.via_z0(0.3, 0.3, 4.5)


def test_bad_inputs_are_refused():
    with pytest.raises(ValueError):
        z.microstrip_z0(0.0, 1.6, 4.5)
    with pytest.raises(ValueError):
        z.width_for_z0(1000.0, 1.6, 4.5)
