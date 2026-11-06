import csv
import json
import subprocess
import sys

import numpy as np
import pytest

from submeter_bench.batch import BatchConfig, run_batch, within_limit
from submeter_bench.control import ControlLimits
from submeter_bench.report import write_report


def test_control_limits_match_hand_calculated_moving_range():
    # Alternating 0 and 2: center = 1, every moving range = 2.
    limits = ControlLimits.fit([0.0, 2.0] * 10)
    assert limits.center == 1
    assert limits.sigma == pytest.approx(2 / 1.128)
    assert limits.lower == pytest.approx(1 - 6 / 1.128)
    assert limits.upper == pytest.approx(1 + 6 / 1.128)
    assert not limits.alarm(1)
    assert limits.alarm(8)
    assert limits.alarm(-8)


@pytest.mark.parametrize("values", [[0] * 20, [1, 2], [float("nan")] * 20])
def test_unusable_control_baseline_is_rejected(values):
    with pytest.raises(ValueError):
        ControlLimits.fit(values)


def test_specification_decision_is_inclusive_and_does_not_round():
    assert within_limit(1, 1)
    assert within_limit(-1, 1)
    assert not within_limit(1.0000001, 1)
    assert not within_limit(-1.0000001, 1)


@pytest.fixture(scope="module")
def batch():
    return run_batch(BatchConfig())


def test_batch_is_repeatable_and_preserves_prefixes(batch):
    assert batch == run_batch(BatchConfig())
    short = run_batch(BatchConfig(units=2))
    assert short.units == batch.units[:2]
    assert short.measurements == [m for m in batch.measurements if m.unit_index <= 2]
    assert short.control_limits == batch.control_limits


def test_every_unit_gets_all_load_points_and_correct_aggregation(batch):
    assert len(batch.units) == 40
    assert len(batch.measurements) == 960
    assert len(batch.baseline_measurements) == 480
    for unit in batch.units:
        rows = [m for m in batch.measurements if m.unit_id == unit.id]
        assert len(rows) == 24
        assert unit.passed == all(m.passed for m in rows)
        assert unit.failed_points == sum(not m.passed for m in rows)
        assert unit.control_alarms == sum(m.control_alarm for m in rows)
        assert all(m.reference_wh > 0 and np.isfinite(m.meter_wh) for m in rows)


def test_frozen_baseline_detects_drift_before_first_failed_unit(batch):
    first_alarm = next(u.index for u in batch.units if u.control_alarms)
    first_failure = next(u.index for u in batch.units if not u.passed)
    assert first_alarm < first_failure
    no_drift = run_batch(BatchConfig(gain_drift_pct=0))
    assert all(u.passed for u in no_drift.units)
    assert batch.control_limits == no_drift.control_limits


def test_phase_drift_is_more_visible_at_low_power_factor():
    result = run_batch(BatchConfig(units=2, gain_drift_pct=0, phase_drift_deg=1))
    rows = {m.point_id: m for m in result.measurements if m.unit_index == 2}
    assert abs(rows["1ph-10A-lag"].error_pct) > 2
    assert abs(rows["1ph-10A-unity"].error_pct) < 0.2
    assert rows["1ph-10A-lag"].error_pct < 0 < rows["1ph-10A-lead"].error_pct


def test_power_offset_drift_is_more_visible_at_light_load():
    result = run_batch(BatchConfig(units=2, gain_drift_pct=0, offset_drift_w=1))
    rows = {m.point_id: m for m in result.measurements if m.unit_index == 2}
    assert rows["1ph-0.4A-unity"].error_pct > 1.5
    assert abs(rows["1ph-50A-unity"].error_pct) < 0.1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"units": 0},
        {"units": 2.5},
        {"baseline_units": 9},
        {"seed": -1},
        {"gain_drift_pct": float("nan")},
        {"phase_drift_deg": float("inf")},
        {"offset_drift_w": float("nan")},
    ],
)
def test_invalid_batch_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        BatchConfig(**kwargs)


def test_report_contains_auditable_results_and_decodable_charts(tmp_path, batch):
    from PIL import Image

    write_report(batch, tmp_path)
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["simulated"] is True
    assert report["config"]["seed"] == 42
    assert len(report["meters"]) == 40
    assert len(report["baseline_meters"]) == 20
    assert len(report["points"]) == 24
    assert len(report["control_limits"]) == 24
    assert report["summary"]["first_control_alarm"] < report["summary"]["first_failed_unit"]
    with (tmp_path / "measurements.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1440
    assert {r["role"] for r in rows} == {"baseline", "production"}
    assert b"\r" not in (tmp_path / "measurements.csv").read_bytes()
    assert all(r["source_url"].startswith("https://www.oiml.org/") for r in rows)
    with (tmp_path / "units.csv").open() as f:
        assert len(list(csv.DictReader(f))) == 40
    for phases in (1, 3):
        with Image.open(tmp_path / f"control-{phases}ph.png") as chart:
            assert chart.width >= 1500
            chart.verify()
    assert "SIMULATED" in (tmp_path / "report.md").read_text()
    import matplotlib.pyplot as plt

    assert plt.get_fignums() == []


def test_cli_reports_failures_and_enforces_opt_in_exit_policy(tmp_path):
    command = [
        sys.executable,
        "-m",
        "submeter_bench",
        "--units",
        "2",
        "--gain-drift-pct",
        "3",
        "--output",
        str(tmp_path),
    ]
    normal = subprocess.run(command, capture_output=True, text=True)
    assert normal.returncode == 0, normal.stderr
    assert "1/2 units passed" in normal.stdout
    strict = subprocess.run(command + ["--fail-on-unit-failure"], capture_output=True, text=True)
    assert strict.returncode == 1
    summary = json.loads((tmp_path / "report.json").read_text())["summary"]
    assert summary["passed_units"] == 1


def test_cli_rejects_invalid_inputs_without_traceback(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "submeter_bench", "--seed", "-1", "--output", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert not list(tmp_path.iterdir())
