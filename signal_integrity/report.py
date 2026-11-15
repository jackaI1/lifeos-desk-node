"""Markdown report and plots for the signal-integrity run."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from signal_integrity.analysis import Stackup  # noqa: E402
from signal_integrity.impedance import microstrip_z0  # noqa: E402
from signal_integrity.kicad_pcb import Board  # noqa: E402


def _plot_losses(simulated: Dict[str, object], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    f = simulated["freq_ghz"]
    ax.plot(f, simulated["il_db"], label="insertion loss |S21| (dB)", color="#1f77b4")
    ax.plot(f, simulated["rl_db"], label="return loss |S11| (dB)", color="#d62728")
    ax.set_xlabel("frequency (GHz)")
    ax.set_ylabel("loss (dB)")
    ax.set_title("Simulated via transition, 50 ohm reference")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _plot_tdr(simulated: Dict[str, object], z_trace: float, z_via: float, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    t = simulated["tdr_ns"]
    ax.plot(t, simulated["tdr_z_ohm"], color="#2ca02c", label="TDR impedance from S11")
    ax.axhline(z_trace, color="#555555", linestyle="--", label=f"trace, closed form {z_trace:.0f} ohm")
    ax.axhline(z_via, color="#9467bd", linestyle=":", label=f"via, closed form {z_via:.0f} ohm")
    ax.axhline(50.0, color="#999999", linestyle="-.", linewidth=0.8, label="50 ohm reference")
    ax.set_xlim(0, 3)
    ax.set_ylim(0, max(200.0, z_trace * 1.2))
    ax.set_xlabel("time (ns)")
    ax.set_ylabel("impedance (ohm)")
    ax.set_title("TDR-style response (inverse FFT of S11)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def write_report(out: Path, *, board: Board, stackup: Stackup, net: str, width_mm: float,
                 closed: dict, simulated: Optional[dict], pcb: str) -> Path:
    z_trace = microstrip_z0(width_mm, stackup.h_mm, stackup.er, stackup.t_mm)
    z_via = closed["via"]["z0_ohm"]
    lines = [
        "# Desk node signal-integrity check",
        "",
        f"Board: `{Path(pcb).name}` ({len(board.tracks)} tracks, {len(board.vias)} vias, "
        f"{board.thickness_mm:g} mm, 2 copper layers).",
        "",
        "## Stackup and assumptions",
        "",
        *[f"- {line}" for line in stackup.describe()],
        f"- GND pour clearance {board.ground_clearance_mm:g} mm (board file); "
        f"via antipad = pad + 2 x clearance.",
        "",
        "## Closed-form impedance (Hammerstad-Jensen microstrip, coaxial via)",
        "",
        "| track width | microstrip Z0 | total length on the board |",
        "| --- | --- | --- |",
    ]
    for row in closed["tracks"]:
        lines.append(f"| {row['width_mm']:g} mm | {row['z0_ohm']:.1f} ohm | {row['length_mm']:.1f} mm |")
    via = closed["via"]
    lines += [
        "",
        f"- 50 ohm needs a {closed['width_for_50_mm']:.2f} mm trace on this stackup.",
        f"- Via: pad {via['pad_mm']:g} mm, drill {via['drill_mm']:g} mm, antipad {via['antipad_mm']:g} mm, "
        f"Z = {via['z0_ohm']:.1f} ohm. A via this low sits between the trace and the rest of the path.",
        "",
        f"Representative trace for the 3D model: `{net}` at {width_mm:g} mm, "
        f"{z_trace:.1f} ohm closed form.",
        "",
    ]
    if simulated is None:
        lines += [
            "## 3D FDTD model (openEMS)",
            "",
            "Not run. Re-run with `python3 -m signal_integrity --simulate` once openEMS is installed.",
            "",
        ]
    else:
        at = simulated["at_ghz"]
        lines += [
            "## 3D FDTD model (openEMS) and scikit-rf",
            "",
            "A top-layer trace drops through one via into a bottom-layer trace that crosses a slot in the "
            "ground pour, then climbs back through a second via. Ports are at both ends of the top trace.",
            "",
            "| frequency | insertion loss (S21) | return loss (S11) |",
            "| --- | --- | --- |",
        ]
        for ghz in sorted(at):
            lines.append(f"| {ghz:g} GHz | {at[ghz]['il_db']:.2f} dB | {at[ghz]['rl_db']:.2f} dB |")
        z_at = simulated["z_at_ns"]
        lines += [
            "",
            f"TDR impedance (0.2 to 2 ns window): {simulated['tdr_min_ohm']:.1f} to "
            f"{simulated['tdr_max_ohm']:.1f} ohm, lowest at {simulated['tdr_min_at_ns']:.2f} ns. "
            f"At 0.5 / 1 / 2 ns: {z_at[0.5]:.1f} / {z_at[1.0]:.1f} / {z_at[2.0]:.1f} ohm.",
            "",
            "Touchstone file: `desk_node_via.s2p`. Plots: `losses.png`, `tdr.png`.",
            "",
            "![Insertion and return loss](losses.png)",
            "![TDR impedance](tdr.png)",
            "",
        ]
        _plot_losses(simulated, out / "losses.png")
        _plot_tdr(simulated, z_trace, z_via, out / "tdr.png")
    lines += [
        "## Limits of this check",
        "",
        "- The stackup values er and tanδ are typical FR-4 values, not the fabricator's.",
        "- The model has no solder mask, plating or pads on the vias, and zero-thickness copper.",
        "- It is one representative trace, not every net. Power nets carry current, not impedance.",
        "- A simulation or a closed form is not a measurement. A time-domain reflectometer on the "
        "assembled board is the test that settles it.",
        "",
    ]
    path = out / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
