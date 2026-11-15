"""Temperature sweep tests on simulated instruments: limits, settling, timeouts, judging."""

import csv
import dataclasses
import math
from pathlib import Path

import pyvisa
import pytest
import yaml

from bench import sweep
from bench.instruments import InstrumentError
from bench.sweep import (Chamber, SettleTimeout, SetpointError, SimClock, SweepError,
                         load_sweep_limits, main, rise_time_s, run_sweep, wait_for_settle)
from bench.sweep_sim import CHAMBER_RESOURCE, StepModel, device_definition, write_device_file

LIMITS = load_sweep_limits()


def _rm_for(step: StepModel, tmp_path: Path, mutate=None) -> pyvisa.ResourceManager:
    definition = device_definition(step)
    if mutate:
        mutate(definition)
    path = tmp_path / "device.yaml"
    path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")
    return pyvisa.ResourceManager(f"{path}@sim")


def test_limits_file_loads_with_the_expected_values():
    assert LIMITS.setpoints_c == (10.0, 25.0, 40.0, 55.0)
    assert LIMITS.bus_hz == 400_000.0
    assert LIMITS.rise_max_s == pytest.approx(300e-9)
    assert LIMITS.rail_low_v == pytest.approx(3.3 * 0.95)


def test_bad_bus_speed_is_refused(tmp_path):
    path = tmp_path / "limits.toml"
    text = Path(sweep.DEFAULT_LIMITS).read_text(encoding="utf-8").replace("400000.0", "250000.0")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SweepError, match="bus_hz"):
        load_sweep_limits(path)


def test_missing_limits_file_is_a_sweep_error(tmp_path):
    with pytest.raises(SweepError):
        load_sweep_limits(tmp_path / "absent.toml")


def test_settle_returns_once_probe_is_in_band_and_settled(tmp_path):
    step = StepModel(setpoint_c=25.0, bus_hz=400e3)
    rm = _rm_for(step, tmp_path)
    chamber = Chamber(rm, CHAMBER_RESOURCE)
    clock = SimClock()
    elapsed = wait_for_settle(chamber, 25.0, band_c=0.3, timeout_s=60, poll_s=5,
                              clock=clock, sleep=clock.advance)
    assert elapsed == 0.0
    chamber.close()
    rm.close()


def test_stuck_chamber_times_out_on_simulated_time(tmp_path):
    step = StepModel(setpoint_c=40.0, bus_hz=400e3, faults=("stuck-chamber",))
    rm = _rm_for(step, tmp_path)
    chamber = Chamber(rm, CHAMBER_RESOURCE)
    clock = SimClock()
    with pytest.raises(SettleTimeout, match="SETTLING"):
        wait_for_settle(chamber, 40.0, band_c=0.3, timeout_s=120, poll_s=10,
                        clock=clock, sleep=clock.advance)
    assert clock.now >= 120          # the timeout was honoured in simulated time
    chamber.close()
    rm.close()


def test_refused_setpoint_is_a_setpoint_error(tmp_path):
    step = StepModel(setpoint_c=40.0, bus_hz=400e3)

    def freeze_readback(definition):
        props = definition["devices"]["bench-chamber"]["properties"]["setpoint"]
        props["getter"] = {"q": ":TEMP:SET?", "r": "25.0"}   # reads 25 C whatever was set

    rm = _rm_for(step, tmp_path, mutate=freeze_readback)
    chamber = Chamber(rm, CHAMBER_RESOURCE)
    with pytest.raises(SetpointError, match="reads back"):
        chamber.set_setpoint(40.0)
    chamber.close()
    rm.close()


def test_unanswered_query_is_an_instrument_error(tmp_path):
    step = StepModel(setpoint_c=25.0, bus_hz=400e3)

    def drop_probe(definition):
        definition["devices"]["bench-chamber"]["dialogues"] = [
            d for d in definition["devices"]["bench-chamber"]["dialogues"] if d.get("q") != ":TEMP:PROBE?"]

    rm = _rm_for(step, tmp_path, mutate=drop_probe)
    chamber = Chamber(rm, CHAMBER_RESOURCE, timeout_ms=200)
    with pytest.raises(InstrumentError):
        chamber.probe()
    chamber.close()
    rm.close()


def test_absent_instrument_is_an_instrument_error(tmp_path):
    # pyvisa-sim opens any name and only fails on the first query, as a missing
    # instrument on the bus would.
    step = StepModel(setpoint_c=25.0, bus_hz=400e3)
    rm = _rm_for(step, tmp_path)
    chamber = Chamber(rm, "TCPIP0::192.0.2.99::inst0::INSTR", timeout_ms=200)
    with pytest.raises(InstrumentError):
        chamber.identify()
    chamber.close()
    rm.close()


def test_rise_time_matches_the_rc_closed_form():
    # 4.7 kohm and 50 pF at 25 C: the simulated SDA edge must match 0.8473 RC = 199.1 ns.
    step = StepModel(setpoint_c=25.0, bus_hz=400e3)
    dt, _, sda = step.waveforms()
    times = [i * dt for i in range(len(sda))]
    expected = math.log(7 / 3) * 4700 * 50e-12
    assert rise_time_s(times, sda) == pytest.approx(expected, rel=0.01)


def test_rise_time_refuses_a_capture_without_an_edge():
    times = [i * 1e-9 for i in range(50)]
    with pytest.raises(SweepError, match="rising edge"):
        rise_time_s(times, [3.3] * 50)


def test_nominal_sweep_passes_and_writes_outputs(tmp_path):
    result = run_sweep(limits=LIMITS, out_root=tmp_path, stamp="20260101T000000Z")
    assert result.passed
    assert [s.setpoint_c for s in result.steps] == [10.0, 25.0, 40.0, 55.0]
    rows = list(csv.DictReader((result.run_dir / "measurements.csv").open(encoding="utf-8")))
    assert len(rows) == 4 and all(r["result"] == "PASS" for r in rows)
    assert (result.run_dir / "sweep_plots.png").stat().st_size > 1000
    report = (result.run_dir / "report.md").read_text(encoding="utf-8")
    assert "Temperature sweep: PASS" in report and "simulated" in report.lower()


def test_sensor_drift_fails_only_the_sht31_check(tmp_path):
    result = run_sweep(limits=LIMITS, faults=["sensor-drift"], out_root=tmp_path,
                       stamp="20260101T000001Z")
    assert not result.passed
    failing = {s.setpoint_c: s.failing for s in result.steps}
    assert failing[10.0] == [] and failing[25.0] == []
    assert failing[40.0] == ["sht31_error"] and failing[55.0] == ["sht31_error"]


def test_ripple_fault_fails_only_the_ripple_check(tmp_path):
    result = run_sweep(limits=LIMITS, faults=["ripple"], out_root=tmp_path, stamp="20260101T000002Z")
    assert all(s.failing == ["ripple_3v3"] for s in result.steps)


def test_stuck_chamber_is_an_error_not_a_fail(tmp_path):
    with pytest.raises(SettleTimeout):
        run_sweep(limits=LIMITS, faults=["stuck-chamber"], out_root=tmp_path, stamp="20260101T000003Z")


def test_100_khz_sweep_uses_the_standard_mode_limit(tmp_path):
    limits = dataclasses.replace(LIMITS, bus_hz=100_000.0, rise_max_s=1.0e-6)
    result = run_sweep(limits=limits, out_root=tmp_path, stamp="20260101T000004Z")
    assert result.passed
    assert all(s.rise_s < 1.0e-6 for s in result.steps)


def test_cli_exit_codes(tmp_path, capsys):
    assert main(["--out", str(tmp_path), "--inject", "ripple"]) == 1
    assert main(["--out", str(tmp_path), "--inject", "stuck-chamber"]) == 2
    assert main(["--out", str(tmp_path), "--inject", "not-a-fault"]) == 2
    with pytest.raises(SystemExit):                                  # argparse: real hardware needs all four
        main(["--chamber", "X", "--out", str(tmp_path)])


def test_zero_settle_timeout_is_refused(tmp_path):
    path = tmp_path / "limits.toml"
    text = Path(sweep.DEFAULT_LIMITS).read_text(encoding="utf-8").replace(
        "settle_timeout_s = 600.0", "settle_timeout_s = 0.0")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SweepError, match="settling"):
        load_sweep_limits(path)
