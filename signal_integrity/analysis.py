"""Stackup, closed-form impedance table, and scikit-rf metrics for the desk-node board.

Everything here runs without openEMS except `simulate`, which imports fdtd only
when called. Results go into a plain dictionary so the report and the tests read
the same numbers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from signal_integrity import fdtd, impedance, tdr
from signal_integrity.kicad_pcb import Board

POWER_AND_GROUND = {"GND", "+3V3", "+5V", "VBUS"}
Z_REF = 50.0


@dataclass(frozen=True)
class Stackup:
    """The board's two-layer stack. Thickness and copper come from the board file and its notes."""
    h_mm: float            # dielectric height between the layers (board thickness)
    copper_um: float       # 1 oz copper, as stated in hardware/docs/design.md
    er: float              # ASSUMED: FR-4 relative permittivity near 1 GHz
    tand: float            # ASSUMED: FR-4 loss tangent

    @property
    def t_mm(self) -> float:
        return self.copper_um / 1000.0

    def describe(self) -> List[str]:
        return [
            f"Dielectric: FR-4, {self.h_mm:g} mm thick between the two copper layers "
            f"(from the board file).",
            f"Copper: {self.copper_um:g} um (1 oz), from hardware/docs/design.md.",
            f"Permittivity er = {self.er:g} and loss tangent {self.tand:g}: ASSUMED typical "
            f"FR-4 values. The fabricator's stackup sheet should replace them.",
            "Solder mask and the copper plating are left out of both models.",
        ]


def default_stackup(board: Board) -> Stackup:
    return Stackup(h_mm=board.thickness_mm, copper_um=35.0, er=4.5, tand=0.02)


def pick_representative(board: Board) -> Tuple[str, float]:
    """The longest signal net, and the track width used for most of its length.

    Power and ground nets are skipped: their widths are set by current, not by impedance.
    """
    lengths: Dict[str, float] = Counter()
    for track in board.tracks:
        if track.net and track.net not in POWER_AND_GROUND:
            lengths[track.net] += track.length_mm
    if not lengths:
        raise ValueError("the board has no signal nets")
    net = max(sorted(lengths), key=lambda n: lengths[n])
    widths = board.track_widths(net)
    width = max(sorted(widths), key=lambda w: widths[w])
    return net, width


def closed_form(board: Board, stackup: Stackup) -> Dict[str, object]:
    """Microstrip impedance for every track width on the board, the via, and the 50 ohm width."""
    lengths = board.track_widths()
    rows = [{"width_mm": w,
             "z0_ohm": impedance.microstrip_z0(w, stackup.h_mm, stackup.er, stackup.t_mm),
             "length_mm": lengths[w]}
            for w in sorted(lengths)]
    via = board.vias[0]
    antipad = via.pad_mm + 2.0 * board.ground_clearance_mm
    return {
        "tracks": rows,
        "width_for_50_mm": impedance.width_for_z0(Z_REF, stackup.h_mm, stackup.er, stackup.t_mm),
        "via": {
            "pad_mm": via.pad_mm,
            "drill_mm": via.drill_mm,
            "antipad_mm": antipad,
            "z0_ohm": impedance.via_z0(via.drill_mm, antipad, stackup.er),
        },
    }


def model_width(stackup: Stackup) -> float:
    """Width of the 50 ohm trace on this stackup, used for the 3D via model."""
    return impedance.width_for_z0(Z_REF, stackup.h_mm, stackup.er, stackup.t_mm)


def model_for(board: Board, stackup: Stackup, width_mm: float) -> fdtd.TraceModel:
    via = board.vias[0]
    return fdtd.default_model(width_mm, stackup.h_mm, stackup.er, stackup.tand,
                              via.drill_mm, via.pad_mm, board.ground_clearance_mm)


def network_from_s(freq_hz: np.ndarray, s11: np.ndarray, s21: np.ndarray,
                   path: Optional[Path] = None):
    """Build a scikit-rf two-port from the simulated S11 and S21 (symmetric device)."""
    import skrf

    freq = skrf.Frequency.from_f(freq_hz, unit="Hz")
    s = np.zeros((len(freq_hz), 2, 2), dtype=complex)
    s[:, 0, 0] = s11
    s[:, 1, 1] = s11      # symmetric device: port 2 matches port 1
    s[:, 0, 1] = s21
    s[:, 1, 0] = s21      # reciprocal device
    net = skrf.Network(frequency=freq, s=s, z0=Z_REF, name="desk-node-via-transition")
    if path is not None:
        net.write_touchstone(filename=str(path), write_z0=False)
    return net


def metrics(net, z_points_ns: Tuple[float, ...] = (0.5, 1.0, 2.0)) -> Dict[str, object]:
    """Insertion loss, return loss and the TDR impedance from a scikit-rf two-port."""
    f = net.f
    s21_db = 20 * np.log10(np.maximum(np.abs(net.s[:, 1, 0]), 1e-12))
    s11_db = 20 * np.log10(np.maximum(np.abs(net.s[:, 0, 0]), 1e-12))
    time_s, z_t = tdr.tdr_impedance(f, net.s[:, 0, 0], z0=Z_REF)
    tdr_ns = time_s * 1e9
    at = {}
    for target in (1.0, 2.4, 3.0, 5.0):
        i = int(np.argmin(np.abs(f - target * 1e9)))
        at[target] = {"il_db": float(-s21_db[i]), "rl_db": float(-s11_db[i])}
    window = (tdr_ns > 0.2) & (tdr_ns < 2.0)
    return {
        "freq_ghz": (f / 1e9).tolist(),
        "il_db": (-s21_db).tolist(),
        "rl_db": (-s11_db).tolist(),
        "at_ghz": at,
        "tdr_ns": tdr_ns.tolist(),
        "tdr_z_ohm": z_t.tolist(),
        "tdr_min_ohm": float(np.min(z_t[window])),
        "tdr_max_ohm": float(np.max(z_t[window])),
        "tdr_min_at_ns": float(tdr_ns[window][int(np.argmin(z_t[window]))]),
        "z_at_ns": {t: float(np.interp(t, tdr_ns, z_t)) for t in z_points_ns},
    }


def simulate(board: Board, stackup: Stackup, width_mm: float, out: Path) -> Dict[str, object]:
    """Run the via-transition model with openEMS, read it with scikit-rf, and return the metrics."""
    model = model_for(board, stackup, width_mm)
    freq, s11, s21 = fdtd.run_isolated(model, log_path=out / "openems-via.log")
    net = network_from_s(freq, s11, s21, path=out / "desk_node_via.s2p")
    result = metrics(net)
    result["touchstone"] = str(out / "desk_node_via.s2p")
    result["width_mm"] = width_mm
    return result


def physics_checks(result: Dict[str, object], stackup: Stackup, width_mm: float) -> List[Tuple[str, bool, str]]:
    """Checks on the simulated via transition. Each is (name, passed, what was measured).

    Only the outputs this model has been shown to reproduce are pass/fail:
    - the 50 ohm trace is matched at 1 GHz (return loss), as the closed form predicts;
    - the via lowers the TDR impedance below the 50 ohm reference, by more than 5 %, and
      not below 80 % of the via's own closed-form impedance.
    Insertion loss is reported separately by `unverified_notes`, because this run does not
    yet end with the energy gone, and a passive via cannot give |S21| above 1.
    """
    trace_z = impedance.microstrip_z0(width_mm, stackup.h_mm, stackup.er, stackup.t_mm)
    via_z = impedance.via_z0(0.3, 0.6 + 2.0 * 0.3, stackup.er)
    rl_1 = result["at_ghz"][1.0]["rl_db"]
    tdr_min = result["tdr_min_ohm"]
    return [
        ("trace matched near 50 ohm at 1 GHz", rl_1 > 10.0,
         f"return loss {rl_1:.1f} dB (limit 10 dB; trace {trace_z:.1f} ohm)"),
        ("TDR dip from the via below 50 ohm", tdr_min < 0.95 * Z_REF,
         f"lowest {tdr_min:.1f} ohm (limit below {0.95 * Z_REF:.1f} ohm; via {via_z:.1f} ohm closed form)"),
        ("TDR dip not below 80 % of the via impedance", tdr_min > 0.8 * via_z,
         f"lowest {tdr_min:.1f} ohm (limit above {0.8 * via_z:.1f} ohm)"),
    ]


def unverified_notes(result: Dict[str, object]) -> List[str]:
    """What this run cannot yet be trusted for, with the measured reason."""
    peak_gain = max(-v for v in result["il_db"])
    return [
        f"Insertion loss is not verified: |S21| reaches {peak_gain:.1f} dB above 1 at some "
        "frequencies, which a passive via cannot do. The solver ends before the energy leaves, "
        "so the transmitted wave is incomplete.",
    ]
