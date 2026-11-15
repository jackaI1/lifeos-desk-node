"""The 3D run itself. Skipped unless openEMS and CSXCAD import (CI installs them)."""

from pathlib import Path

import numpy as np
import pytest

from signal_integrity import analysis, fdtd
from signal_integrity.kicad_pcb import parse_board

BOARD = Path(__file__).resolve().parents[2] / "hardware" / "desk-node.kicad_pcb"

try:
    import CSXCAD  # noqa: F401
    import openEMS  # noqa: F401
    HAVE_OPENEMS = True
except ImportError:
    HAVE_OPENEMS = False

needs_openems = pytest.mark.skipif(not HAVE_OPENEMS, reason="openEMS/CSXCAD not installed")


@needs_openems
def test_via_transition_simulation_is_physical(tmp_path):
    board = parse_board(BOARD)
    stackup = analysis.default_stackup(board)
    net, width = analysis.pick_representative(board)
    result = analysis.simulate(board, stackup, width, tmp_path)
    # A passive, reciprocal two-port: loss is non-negative (small numerical slack allowed).
    assert all(il > -0.1 for il in result["il_db"])
    # The 16 mm reference line is low loss at 1 GHz on this stackup.
    assert result["through"]["at_ghz"][1.0]["il_db"] < 1.0
    # The two vias add loss above the reference line, and not much of it at 3 GHz.
    assert -0.2 < result["excess_db_at_ghz"][3.0] < 3.0
    # The vias are a low-impedance step, so the TDR must show a dip below the trace impedance.
    trace_z = analysis.impedance.microstrip_z0(width, stackup.h_mm, stackup.er, stackup.t_mm)
    assert result["tdr_min_ohm"] < trace_z
    assert result["tdr_min_ohm"] > 10.0
    assert Path(result["touchstone"]).exists()
    assert Path(result["through_touchstone"]).exists()
    assert np.isfinite(result["tdr_max_ohm"])
