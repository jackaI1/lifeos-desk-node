"""The 3D run itself. Skipped unless openEMS and CSXCAD import (CI installs them)."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from signal_integrity import analysis, fdtd
from signal_integrity.kicad_pcb import parse_board

BOARD = Path(__file__).resolve().parents[2] / "hardware" / "desk-node.kicad_pcb"

# Look for the modules without importing them, so this process never loads the solver.
HAVE_OPENEMS = (importlib.util.find_spec("CSXCAD") is not None
                and importlib.util.find_spec("openEMS") is not None)

needs_openems = pytest.mark.skipif(not HAVE_OPENEMS, reason="openEMS/CSXCAD not installed")


@needs_openems
def test_via_transition_simulation_is_physical(tmp_path):
    board = parse_board(BOARD)
    stackup = analysis.default_stackup(board)
    net, width = analysis.pick_representative(board)
    result = analysis.simulate(board, stackup, width, tmp_path)
    failed = [(name, detail) for name, ok, detail in analysis.physics_checks(result, stackup, width) if not ok]
    assert not failed, failed
    assert Path(result["touchstone"]).exists()
    assert Path(result["through_touchstone"]).exists()
