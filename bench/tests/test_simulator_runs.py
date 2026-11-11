import csv
import glob
import subprocess
import sys
import tempfile
from pathlib import Path

import pyvisa
import pytest

from bench.__main__ import main as cli_main
from bench.harness import run_bench
from bench.instruments import SetpointError
from bench.limits import load_limits
from bench.simulator import Scenario, apply_faults, device_definition, rail_waveforms, write_device_file

ROOT = Path(__file__).resolve().parents[2]
LIMITS = ROOT / "bench" / "limits.toml"
CHECKS = ["rail_vbus_mean_v", "rail_3v3_mean_v", "rail_3v3_ripple_mvpp",
          "sequence_3v3_after_vbus_ms", "input_current_ma"]


def sim_temp_dirs():
    return set(glob.glob(str(Path(tempfile.gettempdir()) / "bench-sim-*")))


@pytest.fixture(scope="module")
def nominal(tmp_path_factory):
    out = tmp_path_factory.mktemp("nominal")
    return run_bench(LIMITS, out_root=out, stamp="20260101T000000Z")


def test_nominal_run_passes_all_checks(nominal):
    assert nominal.passed
    assert [c.name for c in nominal.checks] == CHECKS
    by_name = {c.name: c for c in nominal.checks}
    assert by_name["rail_3v3_ripple_mvpp"].measured == pytest.approx(8.0, abs=1.0)
    assert by_name["sequence_3v3_after_vbus_ms"].measured == pytest.approx(1.5, abs=0.1)
    assert by_name["input_current_ma"].measured == pytest.approx(60.0, abs=0.5)


def test_nominal_run_writes_timestamped_csv_capture_and_report(nominal):
    csv_path = nominal.measurements_csv
    assert csv_path.name == "20260101T000000Z_measurements.csv"
    assert nominal.run_dir.name == "20260101T000000Z-nominal"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert [r["check"] for r in rows] == CHECKS and {r["result"] for r in rows} == {"PASS"}
    capture = (nominal.run_dir / "20260101T000000Z_capture.csv").read_text(encoding="utf-8").splitlines()
    assert capture[0] == "time_ms,vbus_v,v3v3_v" and len(capture) == 6001
    report = (nominal.run_dir / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# Power-up bench check: PASS")
    assert "simulated SCPI supply and scope" in report
    assert "Steps" in report and "read back 5.000 V" in report


def test_ripple_injection_is_flagged_and_nothing_else_is(tmp_path):
    result = run_bench(LIMITS, faults=["ripple"], out_root=tmp_path, stamp="20260101T000001Z")
    failing = [c.name for c in result.checks if not c.passed]
    assert failing == ["rail_3v3_ripple_mvpp"]
    assert result.run_dir.name == "20260101T000001Z-ripple"
    assert "FAIL" in (result.run_dir / "report.md").read_text(encoding="utf-8")


def test_late_rail_injection_is_flagged_and_nothing_else_is(tmp_path):
    result = run_bench(LIMITS, faults=["late-rail"], out_root=tmp_path, stamp="20260101T000002Z")
    failing = [c.name for c in result.checks if not c.passed]
    assert failing == ["sequence_3v3_after_vbus_ms"]
    delay = next(c for c in result.checks if c.name == "sequence_3v3_after_vbus_ms")
    assert delay.measured == pytest.approx(14.0, abs=0.1)


def test_both_faults_together_fail_both_checks(tmp_path):
    result = run_bench(LIMITS, faults=["ripple", "late-rail"], out_root=tmp_path,
                       stamp="20260101T000003Z")
    assert {c.name for c in result.checks if not c.passed} == {"rail_3v3_ripple_mvpp",
                                                               "sequence_3v3_after_vbus_ms"}
    assert result.run_dir.name == "20260101T000003Z-late-rail+ripple"


def test_unknown_fault_name_is_rejected():
    with pytest.raises(ValueError, match="unknown fault"):
        apply_faults(Scenario(), ["brownout"])


def test_none_is_not_a_fault():
    assert apply_faults(Scenario(), ["none"]).faults == ()


def test_refused_setpoint_stops_the_run(tmp_path):
    limits = load_limits(LIMITS)
    too_high = type(limits)(**{**limits.__dict__, "vbus_setpoint_v": 7.0})
    with pytest.raises(SetpointError, match="reads back"):
        run_bench(limits=too_high, out_root=tmp_path, stamp="20260101T000004Z")
    assert not list(tmp_path.glob("*")), "no result folder should be written for a refused setpoint"


def test_device_file_is_valid_pyvisa_sim_and_serves_the_model(tmp_path):
    scenario = Scenario()
    path = write_device_file(scenario, tmp_path / "bench.yaml")
    rm = pyvisa.ResourceManager(f"{path}@sim")
    try:
        psu = rm.open_resource("TCPIP0::192.0.2.10::inst0::INSTR")
        psu.read_termination = psu.write_termination = "\n"
        assert psu.query("*IDN?").startswith("SIM,DESK-BENCH-PSU")
        psu.write("SOUR:VOLT 4.5")
        assert float(psu.query("SOUR:VOLT?")) == pytest.approx(4.5)
        psu.write("SOUR:VOLT 9.0")  # refused by the simulated supply, so the readback is unchanged
        assert float(psu.query("SOUR:VOLT?")) == pytest.approx(4.5)
        psu.close()
    finally:
        rm.close()


def test_device_definition_has_one_sample_per_point():
    definition = device_definition(Scenario(points=100))
    scope = definition["devices"]["bench-scope"]
    data = {d["q"]: d["r"] for d in scope["dialogues"] if d["q"].startswith(":WAV:DATA")}
    assert all(len(r.split(",")) == 100 for r in data.values())


def test_rail_model_matches_the_documented_timing():
    times, vbus, v3 = rail_waveforms(Scenario(points=3000, window_ms=30.0))
    assert vbus[-1] == pytest.approx(5.0)
    assert v3[-1] == pytest.approx(3.3, abs=0.02)
    assert v3[0] == pytest.approx(0.0) and times[1] - times[0] == pytest.approx(10e-6)


def test_no_simulator_files_are_left_behind(tmp_path):
    before = sim_temp_dirs()
    run_bench(LIMITS, out_root=tmp_path, stamp="20260101T000005Z")
    assert sim_temp_dirs() == before


def test_cli_exit_codes(tmp_path, capsys):
    assert cli_main(["--out", str(tmp_path / "a")]) == 0
    assert cli_main(["--out", str(tmp_path / "b"), "--inject", "ripple"]) == 1
    assert cli_main(["--config", str(tmp_path / "missing.toml")]) == 2
    assert cli_main(["--out", str(tmp_path / "c"), "--inject", "brownout"]) == 2
    err = capsys.readouterr().err
    assert "bench error" in err


def test_module_entry_point_runs(tmp_path):
    proc = subprocess.run([sys.executable, "-m", "bench", "--out", str(tmp_path)],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    assert "result: PASS" in proc.stdout
