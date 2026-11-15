"""Temporary diagnostic: which copper group causes the 'Unused primitive' warnings."""
import dataclasses
from pathlib import Path
from signal_integrity import analysis, fdtd
from signal_integrity.kicad_pcb import parse_board

BOARD = Path(__file__).resolve().parents[2] / "hardware" / "desk-node.kicad_pcb"
board = parse_board(BOARD)
stackup = analysis.default_stackup(board)
width = analysis.model_width(stackup)
model = dataclasses.replace(analysis.model_for(board, stackup, width), time_steps=300)
out = Path("signal_integrity/build/unused")
out.mkdir(parents=True, exist_ok=True)
for omit in [(), ("vias",), ("bottom",), ("top",), ("ground",), ("vias", "bottom")]:
    name = "+".join(omit) or "none"
    fdtd.run_isolated(model, omit=omit, log_path=out / f"{name}.log")
    text = (out / f"{name}.log").read_text(encoding="utf-8", errors="replace")
    print(f"UNUSED omit={name}: {text.count('Unused primitive')} warnings", flush=True)
