"""Independent expectations: P = sum(Vrms * Irms * cos(phi)), Wh = P * t / 3600."""

import math

import numpy as np
import pytest

from submeter_bench.meter import ChannelError, Meter, make_meter
from submeter_bench.profile import TestPoint, class_b_limit, default_points
from submeter_bench.waveforms import energy_wh, synthesize


def point(phases=1, current=10, pf=1, leading=False):
    return TestPoint("test", phases, current, pf, leading)


def test_rectangular_samples_have_hand_calculated_energy():
    # Four one-second samples: (10*2 + 10*4 + 10*6 + 10*8) / 3600.
    assert energy_wh(
        np.array([[10.0, 10.0, 10.0, 10.0]]), np.array([[2.0, 4.0, 6.0, 8.0]]), 1
    ) == pytest.approx(200 / 3600)


@pytest.mark.parametrize(
    "phases,pf,leading,expected",
    [
        (1, 1, False, 1 / 15),
        (3, 1, False, 0.2),
        (1, 0.5, False, 1 / 30),
        (3, 0.5, False, 0.1),
        (1, 0.8, True, 4 / 75),
        (3, 0.8, True, 0.16),
    ],
)
def test_sinusoidal_energy_matches_hand_values(phases, pf, leading, expected):
    # 120 V, 10 A, 12 cycles at 60 Hz = 0.2 s.
    samples = synthesize(point(phases, pf=pf, leading=leading))
    assert energy_wh(samples.voltage, samples.current, samples.sample_rate) == pytest.approx(
        expected, abs=1e-12
    )


def test_three_phase_waveforms_are_120_degrees_apart():
    samples = synthesize(point(3))
    assert samples.voltage.shape == (3, 1440)
    assert np.sum(samples.voltage, axis=0) == pytest.approx(np.zeros(1440), abs=1e-10)
    assert np.sqrt(np.mean(samples.voltage**2, axis=1)) == pytest.approx([120] * 3)


def test_integrator_keeps_reverse_energy_and_handles_unbalanced_phases():
    v = np.ones((3, 3600)) * 120
    i = np.array([np.ones(3600), np.ones(3600) * 2, np.zeros(3600)])
    assert energy_wh(v, i, 1) == pytest.approx(360)
    assert energy_wh(v, -i, 1) == pytest.approx(-360)


def test_unity_meter_matches_reference_and_gain_errors_multiply():
    samples = synthesize(point(3))
    reference = energy_wh(samples.voltage, samples.current, samples.sample_rate)
    assert Meter("ideal", (ChannelError(),) * 3).read_wh(samples) == pytest.approx(reference)
    meter = Meter("gain", (ChannelError(voltage_gain_pct=1, current_gain_pct=2),) * 3)
    assert meter.read_wh(samples) / reference == pytest.approx(1.0302)


@pytest.mark.parametrize("leading,angle", [(False, 60), (True, -60)])
def test_phase_error_has_correct_lagging_and_leading_sign(leading, angle):
    samples = synthesize(point(pf=0.5, leading=leading))
    meter = Meter("phase", (ChannelError(phase_error_deg=1),))
    expected = 1200 * math.cos(math.radians(angle + 1)) * 0.2 / 3600
    assert meter.read_wh(samples) == pytest.approx(expected, abs=1e-12)


def test_dc_offsets_and_residual_watts_are_integrated():
    samples = synthesize(point())
    meter = Meter(
        "offset", (ChannelError(voltage_offset_v=2, current_offset_a=3, power_offset_w=4),)
    )
    # AC cross terms average to zero; DC product adds 6 W, residual adds 4 W.
    assert meter.read_wh(samples) == pytest.approx(1210 * 0.2 / 3600)


def test_seeded_channels_repeat_and_differ_between_units():
    assert make_meter(42, 0) == make_meter(42, 0)
    assert make_meter(42, 0).channels != make_meter(42, 1).channels
    assert len(set(make_meter(42, 0).channels)) == 3


@pytest.mark.parametrize(
    "current,pf,leading,expected",
    [
        (0.4, 1, False, 1.5),
        (0.999, 1, False, 1.5),
        (1, 1, False, 1),
        (50, 1, False, 1),
        (0.4, 0.5, False, 1.8),
        (0.4, 0.8, True, 1.8),
        (1, 0.5, False, 1.5),
        (50, 0.8, True, 1.5),
    ],
)
def test_class_b_limits_at_band_boundaries(current, pf, leading, expected):
    assert class_b_limit(current, pf, leading) == expected


def test_profile_covers_two_wirings_and_every_point_is_traceable():
    points = default_points()
    assert len(points) == 24
    assert len({p.id for p in points}) == 24
    assert {p.phases for p in points} == {1, 3}
    for p in points:
        assert p.limit_pct == class_b_limit(p.current_a, p.power_factor, p.leading)
        assert "Table 2" in p.limit_source
        assert "Table 10" in p.point_source or "additional" in p.point_source
        assert p.source_url.startswith("https://www.oiml.org/")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"phases": 2},
        {"current": -1},
        {"pf": 0},
        {"pf": 1.1},
        {"pf": float("nan")},
    ],
)
def test_invalid_points_are_rejected(kwargs):
    with pytest.raises(ValueError):
        synthesize(point(**kwargs))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sample_rate": 100},
        {"cycles": 0},
        {"cycles": 1.5},
        {"frequency": 0},
        {"voltage_rms": float("nan")},
        {"sample_rate": 7201},
    ],
)
def test_invalid_sampling_is_rejected(kwargs):
    with pytest.raises(ValueError):
        synthesize(point(), **kwargs)


@pytest.mark.parametrize(
    "v,i,rate",
    [
        (np.ones((1, 2)), np.ones((1, 3)), 1),
        (np.ones((1, 0)), np.ones((1, 0)), 1),
        (np.array([[float("nan")]]), np.ones((1, 1)), 1),
        (np.ones((1, 1)), np.ones((1, 1)), 0),
    ],
)
def test_integrator_rejects_invalid_data(v, i, rate):
    with pytest.raises(ValueError):
        energy_wh(v, i, rate)


@pytest.mark.parametrize(
    "current,pf,leading",
    [
        (0.399, 1, False),
        (50.001, 1, False),
        (1, 0.49, False),
        (1, 0.79, True),
    ],
)
def test_no_standard_limit_is_invented_outside_profile(current, pf, leading):
    with pytest.raises(ValueError):
        class_b_limit(current, pf, leading)
