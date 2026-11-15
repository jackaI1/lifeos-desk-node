"""Temporary diagnostic: the via model on the coarse probe-like mesh, with metrics printed."""
import dataclasses
import sys
from pathlib import Path

import numpy as np

from signal_integrity import analysis, fdtd
from signal_integrity.kicad_pcb import parse_board

BOARD = Path(__file__).resolve().parents[2] / "hardware" / "desk-node.kicad_pcb"


def main(variant: str) -> None:
    board = parse_board(BOARD)
    stackup = analysis.default_stackup(board)
    width = analysis.model_width(stackup)
    base = analysis.model_for(board, stackup, width)
    steps = 12000 if variant == "coarse" else 40000
    model = dataclasses.replace(base, fine_mesh=False, air_mm=8.0, gauss_fc_hz=3.0e9,
                                time_steps=steps)
    out = Path("signal_integrity/build/coarse") / variant
    out.mkdir(parents=True, exist_ok=True)
    freq, s11, s21 = fdtd.run_isolated(model, log_path=out / "openems.log")
    net = analysis.network_from_s(freq, s11, s21, path=out / "via.s2p")
    res = analysis.metrics(net)
    f = np.asarray(res["freq_ghz"])
    for ghz in (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0):
        k = int(np.argmin(np.abs(f - ghz)))
        print(f"COARSE {variant} {ghz:4.1f} GHz  S21 {-res['il_db'][k]:7.2f} dB  "
              f"S11 {-res['rl_db'][k]:7.2f} dB", flush=True)
    print(f"COARSE {variant} TDR {res['tdr_min_ohm']:.1f} .. {res['tdr_max_ohm']:.1f} ohm", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
