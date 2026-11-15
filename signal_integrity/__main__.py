"""Command-line entry point: python -m signal_integrity [--simulate] [--out DIR]

Without --simulate, the run reads the board and writes the closed-form impedance
table (no openEMS needed). With --simulate it also runs the 3D FDTD model, reads
the result with scikit-rf, and adds the S-parameters, TDR and plots to the report.

Exit status: 0 the run finished and every physics check passed, 1 a physics check
failed, 2 the run could not finish (bad board file, openEMS missing when --simulate
is set, or an impedance that cannot be met).
"""

import argparse
import sys
from pathlib import Path

from signal_integrity import analysis, impedance
from signal_integrity.fdtd import OpenEMSUnavailable
from signal_integrity.kicad_pcb import parse_board
from signal_integrity.report import write_report

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PCB = ROOT / "hardware" / "desk-node.kicad_pcb"
DEFAULT_OUT = HERE / "build"


def _nearest(simulated, ghz):
    """(S21 dB, S11 dB) at the grid point nearest ghz."""
    import numpy as np

    f = np.asarray(simulated["freq_ghz"])
    i = int(np.argmin(np.abs(f - ghz)))
    return (-simulated["il_db"][i], -simulated["rl_db"][i])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Signal-integrity check of the desk-node board.")
    parser.add_argument("--pcb", default=str(DEFAULT_PCB), help="KiCad board file")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output folder")
    parser.add_argument("--net", help="signal net to model (default: longest signal net)")
    parser.add_argument("--width", type=float, help="trace width in mm (default: most used on the net)")
    parser.add_argument("--simulate", action="store_true", help="run the openEMS 3D model")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        board = parse_board(args.pcb)
        stackup = analysis.default_stackup(board)
        rep_net, _ = analysis.pick_representative(board)
        net = args.net or rep_net
        widths = board.track_widths(net)
        if not widths:
            raise ValueError(f"net {net!r} has no tracks on the board")
        if args.width:
            width = args.width
        elif args.simulate:
            # The 3D model uses a 50 ohm trace: the board's 0.25 mm traces are about 128 ohm, and
            # a strip that narrow cannot be resolved on a practical mesh (see the report).
            width = analysis.model_width(stackup)
        else:
            width = max(sorted(widths), key=lambda w: widths[w])
        closed = analysis.closed_form(board, stackup)
        simulated = analysis.simulate(board, stackup, width, out) if args.simulate else None
    except OpenEMSUnavailable as exc:
        print(f"signal-integrity error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        print(f"signal-integrity error: {exc}", file=sys.stderr)
        return 2
    report = write_report(out, board=board, stackup=stackup, net=net, width_mm=width,
                          closed=closed, simulated=simulated, pcb=args.pcb)
    z_trace = impedance.microstrip_z0(width, stackup.h_mm, stackup.er, stackup.t_mm)
    print(f"trace: {net} at {width:g} mm -> {z_trace:.1f} ohm (closed form)")
    print(f"via: {closed['via']['z0_ohm']:.1f} ohm; 50 ohm needs {closed['width_for_50_mm']:.2f} mm of trace")
    if simulated:
        print("   GHz   S21 dB   S11 dB")
        for ghz in (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0):
            s21_db, s11_db = _nearest(simulated, ghz)
            print(f"  {ghz:5.1f}  {s21_db:7.2f}  {s11_db:7.2f}")
        print(f"TDR: {simulated['tdr_min_ohm']:.1f} to {simulated['tdr_max_ohm']:.1f} ohm "
              f"(0.2 to 2 ns); insertion loss at 3 GHz "
              f"{simulated['at_ghz'][3.0]['il_db']:.2f} dB")
        checks = analysis.physics_checks(simulated, stackup, width)
        for name, ok, detail in checks:
            print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")
    print(f"report: {report}")
    if simulated and not all(ok for _, ok, _ in checks):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
