import subprocess
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "freecad_tools", *map(str, args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )


def test_cli_demo_bom_reuse_and_revision_roundtrip(tmp_path):
    output = tmp_path / "demo"
    result = run_cli("generate", ROOT / "examples/dimensions.csv", output)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(list((output / "library").glob("*.FCStd"))) == 6
    workbook = load_workbook(output / "bom.xlsx")
    assert sum(workbook.active.cell(row, 4).value for row in range(2, 5)) == 8
    workbook.close()
    assert run_cli("bom", output / "assembly.FCStd", output / "second").returncode == 0
    assert run_cli("reuse", output / "library", output / "second-reuse.csv").returncode == 0
    vault = tmp_path / "vault"
    assert (
        run_cli(
            "check-in", vault, "PL-80", output / "library/PL-80.FCStd", "--expected", 0
        ).returncode
        == 0
    )
    for version, state in enumerate(("review", "released"), 1):
        assert run_cli("transition", vault, "PL-80", state, "--expected", version).returncode == 0
    assert run_cli("transition", vault, "PL-80", "draft", "--expected", 3).returncode == 2
    history = run_cli("history", vault, "PL-80")
    assert history.returncode == 0 and "released" in history.stdout
    assert run_cli("generate", ROOT / "examples/dimensions.csv", output).returncode == 2
    assert (output / "assembly.FCStd").exists()
