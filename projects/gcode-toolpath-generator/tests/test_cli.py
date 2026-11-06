import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parents[1]
SAMPLE = ROOT / "examples/bracket.json"


def run(*args):
    return subprocess.run([sys.executable, "-m", "gcode_toolpath.cli", *map(str, args)],
                          capture_output=True, text=True, timeout=60,
                          env={**os.environ, "MPLBACKEND": "Agg"})


def test_bundle_and_edited_file_failure(tmp_path):
    generated = run("generate", SAMPLE, "--out", tmp_path)
    assert generated.returncode == 0, generated.stderr
    report = json.loads(generated.stdout)
    assert report["ok"] and report["moves"] > 400
    assert len(json.loads((tmp_path / "moves.json").read_text())) == report["moves"]
    for name in ("toolpath-top.png", "toolpath-3d.png"):
        with Image.open(tmp_path / name) as im:
            assert im.size == (1500, 1050)
            assert im.getextrema()[0][0] != im.getextrema()[0][1]
    checked = run("check", SAMPLE, tmp_path / "bracket.nc")
    assert checked.returncode == 0, checked.stderr
    path = tmp_path / "bracket.nc"
    path.write_text(path.read_text().replace("G1 Z-0.500", "G0 Z-0.500", 1))
    bad = run("check", SAMPLE, path)
    assert bad.returncode == 1
    assert not json.loads(bad.stdout)["ok"]


def test_bad_input_no_partial_bundle(tmp_path):
    path = tmp_path / "invalid.json"
    data = json.loads(SAMPLE.read_text())
    data["stepover"] = 10
    path.write_text(json.dumps(data))
    out = tmp_path / "output"
    result = run("generate", path, "--out", out)
    assert result.returncode == 2
    assert "Stepover" in result.stderr
    assert not out.exists()
