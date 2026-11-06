import json
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pytest

from three_phase_fault.cli import main
from three_phase_fault.plots import waveforms


def test_cli_all_faults_relay_and_plots(tmp_path):
    output = tmp_path / "study.json"
    assert (
        main(
            [
                "examples/feeder.json",
                "--bus",
                "workshop",
                "--pickup-a",
                "500",
                "--plots",
                str(tmp_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    data = json.loads(output.read_text())
    assert len(data["studies"]) == 4
    assert data["studies"][0]["relay"]["phases"]["a"]["picked_up"]
    for study in data["studies"]:
        for file in study["plots"]:
            from pathlib import Path

            assert Path(file).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(list(tmp_path.glob("*.png"))) == 8
    assert plt.get_fignums() == []


def test_cli_source_relay_and_stdout(capsys):
    assert (
        main(
            [
                "examples/kirtley.json",
                "--bus",
                "fault",
                "--fault",
                "lg",
                "--pickup-a",
                "1000",
                "--relay-source",
                "breaker_B",
                "--zf",
                "0.01",
                "0",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert len(data["studies"]) == 1
    assert data["studies"][0]["relay"]["location"] == "breaker_B"


@pytest.mark.parametrize(
    "args",
    [
        ["missing.json", "--bus", "fault"],
        ["examples/feeder.json", "--bus", "typo"],
        ["examples/feeder.json", "--bus", "plant", "--relay-source", "grid"],
        ["examples/feeder.json", "--bus", "plant", "--pickup-a", "500", "--relay-source", "bad"],
        ["examples/feeder.json", "--bus", "plant", "--pickup-a", "500", "--max-time-s", "-1"],
    ],
)
def test_cli_errors(args, capsys):
    assert main(args) == 2
    assert "three-phase-fault:" in capsys.readouterr().err


def test_module_entrypoint():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "three_phase_fault",
            "examples/kirtley.json",
            "--bus",
            "fault",
            "--fault",
            "3ph",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["studies"][0]["fault"] == "3ph"


def test_waveform_rms_scaling_and_frequency():
    time, values = waveforms([10, 0, 10j], 50, cycles=1, samples=1001)
    assert time[-1] == pytest.approx(0.02)
    assert values[0, 0] == pytest.approx(10 * np.sqrt(2))
    assert values[0, 500] == pytest.approx(-10 * np.sqrt(2))
    assert values[2, 250] == pytest.approx(-10 * np.sqrt(2))
    assert np.sqrt(np.mean(values[0, :-1] ** 2)) == pytest.approx(10)


@pytest.mark.parametrize(
    "phasors,hz,cycles,samples",
    [([1, 2], 60, 3, 100), ([1, 2, 3], 0, 3, 100), ([1, 2, 3], 60, 0, 100), ([1, 2, 3], 60, 3, 1)],
)
def test_invalid_waveform(phasors, hz, cycles, samples):
    with pytest.raises(ValueError):
        waveforms(phasors, hz, cycles, samples)
