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
    # A passive, reciprocal two-port: loss is non-negative and the trace is short.
    assert all(il > -0.01 for il in result["il_db"])
    assert result["at_ghz"][1.0]["il_db"] < 1.0
    assert result["at_ghz"][3.0]["il_db"] < 3.0
    # The two vias are a low-impedance step. The TDR must show a dip below the trace impedance.
    trace_z = analysis.impedance.microstrip_z0(width, stackup.h_mm, stackup.er, stackup.t_mm)
    assert result["tdr_min_ohm"] < 0.8 * trace_z
    assert result["tdr_min_ohm"] > 10.0
    assert Path(result["touchstone"]).exists()
    assert np.isfinite(result["tdr_max_ohm"])
