import json
import os
import subprocess
import sys
from pathlib import Path

import can
import cantools
import pytest

from can_monitor import analyze as analyzer
from can_monitor.analyze import analyze, analyze_file, main
from can_monitor.candump import read_candump
from can_monitor.examples.build_faults_log import build as build_faults
from can_monitor.virtual_node import run as simulate

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(HERE, "..", "examples", "candump")
CLEAN = os.path.join(EXAMPLES, "desk_node_clean.log")
FAULTS = os.path.join(EXAMPLES, "desk_node_faults.log")
DB = cantools.database.load_file(analyzer.DEFAULT_DBC)


def check(lines, timeout=10.0):
    return analyze(iter(lines), DB, heartbeat_timeout=timeout)


def heartbeat_line(ts, counter=0, temperature=21.0, humidity=45.0, **flags):
    # strict=False lets the out-of-range cases be encoded; bit widths are still enforced.
    payload = DB.encode_message("DeskNode", dict(Temperature=temperature, Humidity=humidity,
                                                  Heartbeat=counter, SensorFault=0,
                                                  QueueLoss=0, **flags), strict=False)
    return can.Message(timestamp=ts, arbitration_id=0x120, data=payload, is_extended_id=False)


def kinds(report):
    return [f.kind for f in report.findings]


def test_clean_recorded_log_has_no_findings():
    report = analyze_file(CLEAN)
    assert report.ok, report.findings
    assert report.frames == 120 and report.heartbeats == 120 and report.bus_off_events == 0


def test_corrupted_log_reports_each_injected_fault_once():
    report = analyze_file(FAULTS)
    assert kinds(report) == [
        "missing_heartbeat", "heartbeat_skip", "out_of_range", "out_of_range",
        "sensor_fault", "bus_off", "queue_loss", "malformed_line", "timestamp_reversed",
    ]
    by_kind = {f.kind: f for f in report.findings}
    assert by_kind["bus_off"].time == pytest.approx(1700000070.5)
    assert by_kind["malformed_line"].line is not None
    assert report.bus_off_events == 1
    assert report.heartbeats == 110  # 120 clean frames, 10 removed, one out of order ignored


def test_build_script_reproduces_committed_fault_log(tmp_path):
    out = tmp_path / "faults.log"
    build_faults(CLEAN, str(out))
    assert out.read_text(encoding="utf-8") == Path(FAULTS).read_text(encoding="utf-8")


def test_simulator_reproduces_committed_clean_log(tmp_path):
    out = tmp_path / "clean.log"
    assert simulate(str(out), 120) == 120
    assert out.read_text(encoding="utf-8") == Path(CLEAN).read_text(encoding="utf-8")


def test_simulated_gap_is_flagged_only_past_the_timeout(tmp_path):
    log = tmp_path / "gap.log"
    simulate(str(log), 60, silent=["10:20"])  # 10 frames missing -> 11 s silence
    assert kinds(analyze_file(str(log), heartbeat_timeout=10)) == ["missing_heartbeat", "heartbeat_skip"]
    # A 12 s timeout accepts the 11 s silence, but the counter still shows the lost frames.
    assert kinds(analyze_file(str(log), heartbeat_timeout=12)) == ["heartbeat_skip"]


def test_silence_before_the_last_record_is_flagged():
    # The log ends at 59 s (an unknown frame), so the heartbeat at 49 s is 10 s old.
    records = [heartbeat_line(float(t), counter=t) for t in range(50)]
    records.append(can.Message(timestamp=59.0, arbitration_id=0x2AA, data=b"\x00", is_extended_id=False))
    report = check(records, timeout=5)
    assert report.findings[-1].kind == "missing_heartbeat"
    assert "last 10.00 s" in report.findings[-1].detail


def test_log_with_no_heartbeat_is_flagged():
    records = [can.Message(timestamp=t, arbitration_id=0x2AA, data=b"\x00", is_extended_id=False)
               for t in (0.0, 5.0, 30.0)]
    report = analyze(records, DB, heartbeat_timeout=10)
    assert kinds(report) == ["unknown_id"] * 3 + ["missing_heartbeat"]


@pytest.mark.parametrize("temperature, humidity, expect_out_of_range", [
    (-40.0, 0.0, False),   # the DBC lower bound is inclusive
    (125.0, 100.0, False),
    (125.01, 50.0, True),
    (25.0, 100.01, True),
])
def test_out_of_range_uses_the_dbc_limits(temperature, humidity, expect_out_of_range):
    msg = heartbeat_line(1.0, temperature=temperature, humidity=humidity)
    report = check([msg])
    assert ("out_of_range" in kinds(report)) is expect_out_of_range


def test_heartbeat_counter_wraps_without_a_finding():
    records = [heartbeat_line(float(i), counter=i % 256) for i in range(260)]
    assert check(records).ok


def test_counter_skip_is_reported_with_the_expected_value():
    report = check([heartbeat_line(0.0, counter=5), heartbeat_line(1.0, counter=9)])
    assert report.findings[0].kind == "heartbeat_skip"
    assert "expected 6" in report.findings[0].detail


def test_frames_with_the_wrong_length_are_decode_errors():
    msg = can.Message(timestamp=0.0, arbitration_id=0x120, data=b"\x00" * 7, is_extended_id=False)
    assert kinds(check([msg])) == ["decode_error"]


def test_error_frames_other_than_bus_off_are_flagged_separately():
    msg = can.Message(timestamp=0.0, arbitration_id=0x04, data=b"\x00" * 8, is_error_frame=True)
    report = check([msg])
    assert kinds(report) == ["error_frame"]
    assert report.bus_off_events == 0


def test_sensor_fault_marker_is_out_of_range_too():
    raw = {"Temperature": 0xFFFF, "Humidity": 4500, "Heartbeat": 0, "SensorFault": 1, "QueueLoss": 0}
    payload = DB.encode_message("DeskNode", raw, scaling=False, strict=False)
    msg = can.Message(timestamp=0.0, arbitration_id=0x120, data=payload, is_extended_id=False)
    assert set(kinds(check([msg]))) == {"out_of_range", "sensor_fault"}


def test_timeout_must_be_positive():
    with pytest.raises(ValueError):
        check([], timeout=0)


def test_cli_exit_codes_and_json_report(tmp_path, capsys):
    out_json = tmp_path / "report.json"
    assert main([CLEAN, "--json", str(out_json)]) == 0
    assert json.loads(out_json.read_text())["ok"] is True
    assert main([FAULTS, "--json", str(out_json)]) == 1
    data = json.loads(out_json.read_text())
    assert data["ok"] is False and data["bus_off_events"] == 1
    assert "bus_off" in capsys.readouterr().out
    assert main([str(tmp_path / "missing.log")]) == 2


def test_cli_runs_as_a_module():
    proc = subprocess.run([sys.executable, "-m", "can_monitor.analyze", CLEAN],
                          capture_output=True, text=True, cwd=os.path.join(HERE, "..", ".."))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("frames=120 heartbeats=120")


def test_fault_log_contains_a_real_bus_off_error_frame():
    errors = [r for r in read_candump(FAULTS) if isinstance(r, can.Message) and r.is_error_frame]
    assert len(errors) == 1 and errors[0].arbitration_id & 0x40
