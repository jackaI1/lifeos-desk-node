"""Reference numbers come from NBS Circular 74; see docs/references.md.

These tests catch unit, end-effect, pair-counting and self-term errors.
"""

import math

import numpy as np
import pytest
from scipy.integrate import quad

from reactor.coils import (
    MU0,
    Coil,
    filament_inductance,
    mutual_inductance,
    nagaoka_coefficient,
    nagaoka_inductance,
    self_inductance,
    wheeler_inductance,
)


def test_nbs_400_turn_textbook_example():
    coil = Coil(0.1, 0.4, 400, wire_diameter_m=0.0005)
    assert nagaoka_inductance(coil) == pytest.approx(0.012919, rel=1e-4, abs=0)
    assert filament_inductance(coil) == pytest.approx(0.012909, rel=2e-4, abs=0)


def test_nbs_1000_turn_multilayer_textbook_example():
    # Book specifies pitch but not bare diameter: assume 0.9 mm in a 1 mm cell.
    coil = Coil(0.1, 0.1, 100, layers=10, wire_diameter_m=0.0009, radial_pitch_m=0.001)
    assert nagaoka_inductance(coil) == pytest.approx(0.1952, rel=0.005, abs=0)
    assert filament_inductance(coil) == pytest.approx(0.1952, rel=0.005, abs=0)


@pytest.mark.parametrize(
    "diameter_length, coefficient",
    [
        (0.05, 0.9791),
        (0.1, 0.9588),
        (0.5, 0.8181),
        (1.0, 0.6884),
        (2.0, 0.5255),
        (4.0, 0.3654),
        (10.0, 0.2033),
        (50.0, 0.0611),
    ],
)
def test_nbs_nagaoka_table(diameter_length, coefficient):
    assert nagaoka_coefficient(1.0, 2.0 / diameter_length) == pytest.approx(coefficient, abs=5.1e-5)


@pytest.mark.parametrize("radius,length", [(1e-6, 1e3), (1e3, 1e-6), (0.1, 0.2)])
def test_nagaoka_extreme_aspect_ratios_stay_finite(radius, length):
    assert 0 < nagaoka_coefficient(radius, length) <= 1


@pytest.mark.parametrize("layers, expected", [(1, 0.0003448275862), (4, 0.004740740741)])
def test_wheeler_inches_to_henries(layers, expected):
    # r=1 inch, length=2 inches, 100 turns/layer; 4-layer depth=0.3 inch.
    coil = Coil(
        0.0254,
        0.0508,
        100,
        layers=layers,
        wire_diameter_m=0.0003,
        radial_pitch_m=(0.00762 - 0.0003) / 3,
    )
    assert wheeler_inductance(coil) == pytest.approx(expected, rel=1e-8, abs=0)


def test_maxwell_mutual_against_independent_neumann_quadrature():
    # Direct angular integral of dl1 dot dl2 / separation, not elliptic integrals.
    a, b, z = 0.13, 0.09, 0.07
    integral = quad(
        lambda angle: (
            math.cos(angle) / math.sqrt(a * a + b * b + z * z - 2 * a * b * math.cos(angle))
        ),
        0,
        2 * math.pi,
        epsabs=1e-11,
    )[0]
    assert mutual_inductance(a, b, z) == pytest.approx(MU0 * a * b / 2 * integral, rel=1e-11, abs=0)
    assert mutual_inductance(b, a, -z) == pytest.approx(mutual_inductance(a, b, z))


def test_far_field_mutual_avoids_cancellation():
    # Dipole limit mu0*pi*a²*b²/(2*z³); cancellation in K/E otherwise returns zero.
    assert mutual_inductance(0.1, 0.1, 1000.0) == pytest.approx(1.9739208802e-19, rel=1e-7, abs=0)


def test_two_turn_sum_includes_self_and_both_mutual_terms():
    coil = Coil(0.1, 0.02, 2, wire_diameter_m=0.001)
    expected = 2 * MU0 * 0.1 * (math.log(1600) - 1.75) + 2 * mutual_inductance(0.1, 0.1, 0.01)
    assert filament_inductance(coil) == pytest.approx(expected, rel=1e-13, abs=0)


def test_one_turn_retains_finite_wire_self_inductance():
    coil = Coil(0.1, 0.02, 1, wire_diameter_m=0.001)
    assert filament_inductance(coil) == pytest.approx(7.0720504169e-7, rel=1e-7, abs=0)
    assert self_inductance(0.1, 0.001) == pytest.approx(7.0720504169e-7, rel=1e-7, abs=0)


def test_multilayer_sum_matches_explicit_pairs():
    coil = Coil(0.1, 0.05, 3, layers=3, wire_diameter_m=0.001, radial_pitch_m=0.002)
    turns = [(r, (j + 0.5) * coil.length_m / 3) for r in coil.layer_radii for j in range(3)]
    expected = sum(self_inductance(r, 0.001) for r, z in turns)
    for i, (r, z) in enumerate(turns):
        expected += 2 * sum(mutual_inductance(r, s, z - w) for s, w in turns[i + 1 :])
    assert filament_inductance(coil) == pytest.approx(expected, rel=1e-12, abs=0)


def test_scaling_all_dimensions_scales_inductance_linearly():
    first = Coil(0.1, 0.1, 50, layers=2, wire_diameter_m=0.001, radial_pitch_m=0.002)
    second = Coil(0.2, 0.2, 50, layers=2, wire_diameter_m=0.002, radial_pitch_m=0.004)
    for method in (wheeler_inductance, nagaoka_inductance, filament_inductance):
        assert method(second) == pytest.approx(2 * method(first), rel=1e-10, abs=0)


def test_dense_turns_approach_current_sheet():
    coil = Coil(0.1, 0.2, 500, wire_diameter_m=0.0003)
    assert filament_inductance(coil) == pytest.approx(nagaoka_inductance(coil), rel=0.002, abs=0)


def test_radial_separation_changes_multilayer_nagaoka():
    thin = Coil(0.1, 0.2, 50, layers=4, wire_diameter_m=0.001, radial_pitch_m=0.001)
    thick = Coil(0.1, 0.2, 50, layers=4, wire_diameter_m=0.001, radial_pitch_m=0.02)
    assert nagaoka_inductance(thick) < nagaoka_inductance(thin)


@pytest.mark.parametrize(
    "changes",
    [
        {"mean_radius_m": 0},
        {"length_m": -1},
        {"wire_diameter_m": 0},
        {"mean_radius_m": float("nan")},
        {"length_m": float("inf")},
        {"turns_per_layer": 2.5},
        {"turns_per_layer": True},
        {"layers": 0},
        {"layers": 21},
        {"turns_per_layer": 2001},
        {"wire_diameter_m": 0.01},  # Does not fit within axial turn pitch.
        {"layers": 3, "radial_pitch_m": 0.2},  # Crosses central axis.
        {"layers": 2, "radial_pitch_m": 0.0001},  # Overlapping layers.
        {"mean_radius_m": 1e-8},
        {"length_m": 1e4},
    ],
)
def test_invalid_geometry_rejected_before_calculation(changes):
    fields = dict(mean_radius_m=0.1, length_m=0.1, turns_per_layer=100, wire_diameter_m=0.001)
    fields.update(changes)
    with pytest.raises(ValueError):
        Coil(**fields)


@pytest.mark.parametrize("args", [(0, 0.1), (0.1, float("nan"))])
def test_invalid_coefficient_inputs(args):
    with pytest.raises(ValueError):
        nagaoka_coefficient(*args)


def test_mutual_vector_output_is_finite_and_decays():
    values = mutual_inductance(0.1, 0.1, np.array([0.001, 0.01, 1.0, 1000.0]))
    assert np.all(np.isfinite(values))
    assert np.all(np.diff(values) < 0)


def test_coincident_filaments_require_finite_self_model():
    with pytest.raises(ValueError, match="coincident"):
        mutual_inductance(0.1, 0.1, 0.0)


def test_nearly_equal_large_filaments_do_not_round_parameter_above_one():
    # This pair used to evaluate E(1.0000000000000002) -> NaN.
    result = mutual_inductance(999.0, 999.000001, 0.0)
    assert math.isfinite(result) and result > 0.02
    # Near-circular-loop limit M ≈ mu0*r*(ln(8r/separation)-2).
    expected = MU0 * 999.0 * (math.log(8 * 999.0 / (999.000001 - 999.0)) - 2)
    assert result == pytest.approx(expected, rel=1e-8, abs=0)


def test_very_long_multilayer_sheet_retains_interlayer_coupling():
    coil = Coil(1e-5, 1000.0, 10, layers=2, wire_diameter_m=1e-6)
    # Long coaxial sheets share the smaller sheet's cross-sectional flux.
    a, b = coil.layer_radii
    limit = MU0 * math.pi * 100 / 1000.0 * (a * a + b * b + 2 * a * a)
    assert nagaoka_inductance(coil) == pytest.approx(limit, rel=1e-7, abs=0)


def test_derived_layer_radii_are_validated_with_geometry():
    with pytest.raises(ValueError, match="layer radius"):
        Coil(1000.0, 1.0, 10, layers=2, wire_diameter_m=0.001)
