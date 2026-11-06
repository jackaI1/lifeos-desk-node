import json
import subprocess
import sys
from dataclasses import asdict, replace

import numpy as np
import pytest

from pdn.model import Study
from pdn.study import run_study


def test_real_cli_writes_reproducible_study_and_editable_input(tmp_path):
    config = tmp_path / "input.json"
    config.write_text(json.dumps(asdict(replace(Study(), step_a=20))))
    out = tmp_path / "results"
    proc = subprocess.run(
        [sys.executable, "-m", "pdn", "--config", str(config), "--output", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads((out / "summary.json").read_text())
    assert result["target_ohm"] == 0.00225
    assert set(result["variants"]) == {"full", "no_package", "damped_package"}
    for name, variant in result["variants"].items():
        assert variant["max_ac_relative_error"] < 1e-6
        assert variant["transient"]["droop_v"] > 0
        assert variant["transient"]["baseline_v"] > 0.89
        assert variant["ac"]["peaks"]
        tran = np.loadtxt(out / f"{name}-transient.csv", delimiter=",", skiprows=1)
        assert tran[-1, 0] == 0.0001
        assert (out / f"{name}-ac.cir").exists()
        assert (out / f"{name}-tran.cir").exists()
    for name in ("impedance.png", "load-step.png"):
        assert (out / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (out / "report.md").stat().st_size > 1000
    assert json.loads((out / "input.json").read_text())["step_a"] == 20
    full = result["variants"]["full"]
    damped = result["variants"]["damped_package"]
    assert full["ac"]["max_ohm"] > 0.02
    assert damped["ac"]["max_ohm"] < 0.008
    assert damped["transient"]["droop_v"] < full["transient"]["droop_v"]


def test_bad_cli_input_explains_error_without_traceback(tmp_path):
    config = tmp_path / "bad.json"
    config.write_text('{"rise_s": -1}')
    proc = subprocess.run(
        [sys.executable, "-m", "pdn", "--config", str(config), "--output", str(tmp_path / "out")],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode != 0
    assert "rise_s" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_accepts_sub_decade_sweep_and_reports_actual_coverage(tmp_path):
    config = tmp_path / "narrow.json"
    config.write_text(json.dumps(asdict(replace(Study(), f_start_hz=1e6, f_stop_hz=2e6))))
    out = tmp_path / "narrow"
    proc = subprocess.run(
        [sys.executable, "-m", "pdn", "--config", str(config), "--output", str(out)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads((out / "summary.json").read_text())
    for variant in result["variants"].values():
        low, high = variant["ac"]["sampled_range_hz"]
        assert low == pytest.approx(1e6)
        assert 2e6 / 10 ** (1 / 200) < high <= 2e6 * (1 + 1e-10)


def test_failed_rerun_preserves_all_previous_results(tmp_path, monkeypatch):
    out = tmp_path / "study"
    run_study(Study(), out)
    original = {p.name: p.read_bytes() for p in out.iterdir()}
    # Missing external tool is a real failure at the simulator boundary, after input staging.
    monkeypatch.setenv("PATH", "")
    with pytest.raises(RuntimeError, match="install ngspice"):
        run_study(replace(Study(), step_a=25), out)
    assert {p.name: p.read_bytes() for p in out.iterdir()} == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["study"]
