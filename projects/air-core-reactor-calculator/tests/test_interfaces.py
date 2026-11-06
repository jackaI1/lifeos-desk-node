import json
import subprocess
import sys

import pytest

from reactor.web import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def geometry(**changes):
    fields = dict(
        mean_radius_mm="100",
        length_mm="400",
        turns_per_layer="400",
        layers="1",
        wire_diameter_mm="0.5",
        radial_pitch_mm="1",
        voltage_kv="11",
        base_mva="10",
        frequency_hz="60",
        source_r_pu="0.01",
        source_x_pu="0.1",
    )
    fields.update(changes)
    return fields


def test_default_page_has_working_example_and_units(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"12.91" in response.data
    assert b"Wheeler" in response.data and b"Nagaoka" in response.data
    assert b"Fault current" in response.data
    assert b"mm" in response.data and b"mH" in response.data
    with client.get("/static/style.css") as stylesheet:
        assert stylesheet.status_code == 200


def test_multilayer_submission_uses_all_inputs(client):
    response = client.post(
        "/",
        data=geometry(length_mm="100", turns_per_layer="100", layers="10", wire_diameter_mm="0.9"),
    )
    assert response.status_code == 200
    assert b"195." in response.data
    assert b"1000 turns" in response.data
    assert b"Wheeler accuracy" in response.data


@pytest.mark.parametrize(
    "changes",
    [
        {"mean_radius_mm": ""},
        {"layers": "1.5"},
        {"length_mm": "nan"},
        {"turns_per_layer": "5000"},
        {"wire_diameter_mm": "200"},
        {"source_x_pu": "-.1"},
        {"base_mva": "0"},
        {"radial_pitch_mm": "inf"},
        {"voltage_kv": "1e308"},
    ],
)
def test_invalid_form_is_readable_and_retains_input(client, changes):
    response = client.post("/", data=geometry(**changes))
    assert response.status_code == 400
    assert b"Check your inputs" in response.data
    assert b'value="400"' in response.data  # User does not lose the other dimensions.
    assert b"Traceback" not in response.data


def test_html_input_is_escaped(client):
    response = client.post("/", data=geometry(length_mm="<script>alert(1)</script>"))
    assert response.status_code == 400
    assert b"<script>alert(1)</script>" not in response.data


def test_missing_submission_fields_do_not_silently_use_default(client):
    response = client.post("/", data={"mean_radius_mm": "100"})
    assert response.status_code == 400


def test_cli_example_is_real_json_and_uses_filament_for_reactor():
    result = subprocess.run(
        [sys.executable, "-m", "reactor", "examples/series-reactor.json"],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["total_turns"] == 100
    assert 0.001 < report["inductance_h"]["filament"] < 0.003
    assert 0 < report["fault_current"]["after_a"] < report["fault_current"]["before_a"]
    # At 60 Hz, 11 kV, 10 MVA, Zbase=12.1 ohms.
    assert report["fault_current"]["reactor_x_pu"] == pytest.approx(
        31.1562907794 * report["inductance_h"]["filament"]
    )


@pytest.mark.parametrize(
    "contents", ["not json", '{"coil":{}}', '{"coil":null}', "[]", '{"coil":{},"unknown":1}']
)
def test_cli_invalid_input_has_no_traceback(tmp_path, contents):
    path = tmp_path / "invalid.json"
    path.write_text(contents)
    result = subprocess.run(
        [sys.executable, "-m", "reactor", str(path)], capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_extreme_supported_geometry_does_not_crash_results_template(client):
    response = client.post(
        "/",
        data=geometry(
            mean_radius_mm="999000",
            length_mm=".001",
            turns_per_layer="1",
            layers="20",
            wire_diameter_mm=".001",
            radial_pitch_mm=".001",
        ),
    )
    assert response.status_code == 200
    assert b"nan" not in response.data.lower()
    assert b"Fault current" in response.data


def test_underflow_scale_source_impedance_has_readable_error(client):
    response = client.post("/", data=geometry(source_r_pu="1e-320", source_x_pu="0"))
    assert response.status_code == 400
    assert b"Check your inputs" in response.data
