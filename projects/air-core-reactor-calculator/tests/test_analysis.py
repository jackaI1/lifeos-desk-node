import math

import pytest

from reactor.analysis import analyze, check_plausibility
from reactor.circuit import fault_current
from reactor.coils import Coil


@pytest.fixture
def coil():
    return Coil(0.1, 0.4, 400, wire_diameter_m=0.0005)


def test_analysis_reports_all_methods_and_real_disagreement(coil):
    result = analyze(coil)
    assert result["inductance_h"]["filament"] == pytest.approx(0.012909, rel=0.0002)
    assert set(result["inductance_h"]) == {"wheeler", "nagaoka", "filament"}
    assert result["max_disagreement_percent"] < 2
    assert not any(flag["severity"] == "error" for flag in result["flags"])


@pytest.mark.parametrize("bad_value", [0.0, -1.0, math.nan, math.inf, 1e6, 1e-12])
def test_physical_checker_flags_impossible_filament_results(coil, bad_value):
    flags = check_plausibility(coil, {"filament": bad_value})
    assert any(flag["severity"] == "error" for flag in flags)


def test_sheet_long_solenoid_bound_catches_unit_mistake(coil):
    flags = check_plausibility(coil, {"nagaoka": 12.919})
    assert "sheet_bound" in {flag["code"] for flag in flags}


def test_valid_sparse_coil_gets_model_warning():
    sparse = Coil(0.1, 0.5, 2, wire_diameter_m=0.001)
    flags = analyze(sparse)["flags"]
    assert "sparse_winding" in {flag["code"] for flag in flags}
    assert "model_disagreement" in {flag["code"] for flag in flags}


def test_checker_distinguishes_disagreement_from_impossibility(coil):
    flags = check_plausibility(coil, {"wheeler": 0.008, "nagaoka": 0.012919, "filament": 0.012909})
    assert any(
        flag["code"] == "model_disagreement" and flag["severity"] == "warning" for flag in flags
    )
    assert not any(flag["severity"] == "error" for flag in flags)


def test_per_unit_reactor_adds_reactance_on_correct_three_phase_base():
    # 10 kV/100 MVA -> 1 ohm, Ibase=5773.502692 A.
    # Source j0.1, reactor j0.1 -> 10 pu becomes 5 pu.
    result = fault_current(
        0.1 / (2 * math.pi * 50),
        voltage_kv=10,
        base_mva=100,
        frequency_hz=50,
        source_r_pu=0,
        source_x_pu=0.1,
    )
    assert result["base_impedance_ohm"] == pytest.approx(1.0)
    assert result["reactor_x_pu"] == pytest.approx(0.1)
    assert result["before_a"] == pytest.approx(57735.02692)
    assert result["after_a"] == pytest.approx(28867.51346)
    assert result["reduction_percent"] == pytest.approx(50.0)


def test_resistive_source_uses_complex_impedance_magnitude():
    result = fault_current(
        0.1 / (2 * math.pi * 60),
        voltage_kv=10,
        base_mva=100,
        frequency_hz=60,
        source_r_pu=0.03,
        source_x_pu=0.04,
    )
    assert result["before_pu"] == pytest.approx(20.0)
    assert result["after_pu"] == pytest.approx(1 / math.hypot(0.03, 0.14))


def test_zero_reactor_is_no_change():
    result = fault_current(0.0)
    assert result["reduction_percent"] == 0
    assert result["before_a"] == result["after_a"]


@pytest.mark.parametrize(
    "changes",
    [
        {"inductance_h": -1},
        {"inductance_h": math.nan},
        {"inductance_h": math.inf},
        {"voltage_kv": 0},
        {"base_mva": -1},
        {"frequency_hz": 0},
        {"source_r_pu": -1},
        {"source_x_pu": -0.1},
        {"source_r_pu": 0, "source_x_pu": 0},
        {"base_mva": math.nan},
        {"inductance_h": True},
    ],
)
def test_invalid_circuit_inputs_rejected(changes):
    fields = dict(inductance_h=0.001)
    fields.update(changes)
    with pytest.raises(ValueError):
        fault_current(**fields)


def test_tiny_source_impedance_is_rejected_before_current_overflows():
    with pytest.raises(ValueError, match="Source impedance"):
        fault_current(0.001, source_r_pu=1e-320, source_x_pu=0)
