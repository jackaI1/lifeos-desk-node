import pytest

from three_phase_fault.industrial import build_network, run_study


def test_study_has_load_flow_and_faults_at_all_buses():
    result = run_study(build_network())
    assert len(result["buses"]) == 4
    assert all(bus["voltage_pu"] > 0 for bus in result["buses"])
    assert all(bus["fault_ka"] > 0 for bus in result["buses"])
    assert result["buses"][0]["fault_ka"] > result["buses"][-1]["fault_ka"]


def test_overloaded_cable_is_reported():
    net = build_network()
    net.line.loc[:, "max_i_ka"] = 0.01
    result = run_study(net)
    assert any("cable" in warning.lower() for warning in result["violations"])


def test_generator_is_standby():
    net = build_network()
    assert not net.sgen.iloc[0].in_service


@pytest.mark.parametrize(
    ("bus_name", "cable_ohm"),
    [
        pytest.param("Main switchboard", 0j, id="main-switchboard"),
        pytest.param(
            "Motor control centre", complex(0.124, 0.08) * 0.12, id="motor-control-centre"
        ),
    ],
)
def test_fault_currents_match_independent_impedance_calculations(bus_name, cable_ohm):
    import math

    result = run_study(build_network())
    # IEC source equivalent, referred to 400 V; transformer correction factor.
    source_z = 1.1 * 0.4**2 / 250
    source_x = source_z / math.sqrt(1 + 0.1**2)
    source = complex(0.1 * source_x, source_x)
    xt = math.sqrt(0.06**2 - 0.01**2)
    kt = 0.95 * 1.1 / (1 + 0.6 * xt)
    transformer = complex(0.01, xt) * 0.4**2 * kt
    expected_ka = 1.1 * 0.4 / (math.sqrt(3) * abs(source + transformer + cable_ohm))
    bus = next(bus for bus in result["buses"] if bus["name"] == bus_name)
    assert bus["fault_ka"] == pytest.approx(expected_ka, rel=0.002), (
        f"{bus_name}: pandapower {bus['fault_ka']:.6f} kA, independent {expected_ka:.6f} kA"
    )
    assert any("Breaker" in warning for warning in result["violations"])


def test_outputs(tmp_path, monkeypatch):
    import json
    import sys

    from three_phase_fault.industrial import main

    monkeypatch.setattr(sys, "argv", ["industrial", "--output", str(tmp_path)])
    main()
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["buses"][1]["fault_ka"] == pytest.approx(24.45, rel=0.002)
    assert report["buses"][2]["fault_ka"] == pytest.approx(9.82, rel=0.002)
    assert any("Breaker" in warning for warning in report["violations"])
    assert (tmp_path / "one-line.png").stat().st_size > 1000
