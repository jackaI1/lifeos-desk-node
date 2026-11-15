"""3D FDTD model of a desk-node trace with a via transition, solved with openEMS.

FDTD (finite-difference time-domain) steps Maxwell's equations on a 3D grid.
openEMS is the open-source solver; CSXCAD builds the geometry. Both are Python
packages that come with the openEMS install (Debian/Ubuntu: openems and
python3-openems). This module imports them only when a simulation is requested,
so the rest of the package runs without them.

Geometry (all lengths in millimetres, looking down the board from the top):

    port 1                 via 1                 via 2                 port 2
    |  top trace (layer 1, z = h) ---- |                    | ---- top trace  |
                                       |  bottom trace (z = 0)  |

- The 1.6 mm FR-4 board is one dielectric slab. Its bottom copper is ground
  (the board's GND pour, with a 0.3 mm clearance around the vias).
- The signal leaves the top trace, drops through via 1 to the bottom layer, runs
  across the board inside a slot in the ground, and climbs back through via 2.
- Each via pad sits in a clearance hole (antipad) in the ground plane. The
  antipad size is the pad plus two clearances, as the board's GND pour sets it.

The structure is symmetric about its centre, so S22 equals S11 and S12 equals
S21 for this reciprocal device. The model therefore runs one simulation with
port 1 excited.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

C0 = 299792458.0
Z_REF = 50.0   # S-parameters are referred to this impedance


class OpenEMSUnavailable(RuntimeError):
    """openEMS or CSXCAD cannot be imported on this machine."""


@dataclass(frozen=True)
class ViaModel:
    x_mm: Tuple[float, float]   # positions of via 1 and via 2 along the trace
    drill_mm: float
    pad_mm: float
    antipad_mm: float


@dataclass(frozen=True)
class TraceModel:
    width_mm: float
    h_mm: float                 # dielectric height
    er: float
    tand: float
    length_mm: float            # total port-to-port span (both ports in the same frame)
    ground_width_mm: float
    ground_clearance_mm: float  # gap between the bottom trace and the ground pour
    via: ViaModel
    mesh_mm: float = 0.5
    fine_mesh: bool = False     # extra 0.3-0.6 mm lines beside the vias (off: the via lines suffice)
    gauss_fc_hz: float = 3.0e9  # width of the excitation pulse (centre is 3 GHz)
    f_stop_hz: float = 6e9
    n_freq: int = 120           # frequency points, evenly spaced from one step to f_stop
    air_mm: float = 8.0
    end_criteria: float = 1e-3
    time_steps: int = 25000

    @property
    def freq_hz(self) -> np.ndarray:
        """Evenly spaced grid starting at one step (50 MHz for the defaults), as the TDR needs."""
        return np.arange(1, self.n_freq + 1) * (self.f_stop_hz / self.n_freq)


def default_model(width_mm: float, h_mm: float, er: float, tand: float,
                  drill_mm: float, pad_mm: float, clearance_mm: float) -> TraceModel:
    """Build the model from the board's stackup and via values."""
    spacing = 8.0
    via_x = (8.0, 8.0 + spacing)
    antipad = pad_mm + 2.0 * clearance_mm
    return TraceModel(
        width_mm=width_mm, h_mm=h_mm, er=er, tand=tand,
        length_mm=via_x[1] + 8.0,
        ground_width_mm=30.0,   # the absorbing faces sit 15 mm from the trace, as in the probe
        ground_clearance_mm=clearance_mm,
        via=ViaModel(via_x, drill_mm, pad_mm, antipad),
    )


ROOT = Path(__file__).resolve().parents[1]


def model_from_dict(data: dict) -> "TraceModel":
    """Rebuild a TraceModel from its JSON form (tuples come back as lists)."""
    via = dict(data["via"])
    via["x_mm"] = tuple(via["x_mm"])
    fields = dict(data)
    fields["via"] = ViaModel(**via)
    return TraceModel(**fields)


def run_isolated(model: TraceModel, *, log_path: Optional[Path] = None,
                 timeout_s: Optional[float] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run build_and_run in a fresh Python process and return (freq, S11, S21).

    The solver's console output goes to log_path when given, so a failed or slow run can be
    read afterwards.
    """
    if importlib.util.find_spec("CSXCAD") is None or importlib.util.find_spec("openEMS") is None:
        raise OpenEMSUnavailable(
            "openEMS and CSXCAD are needed for the 3D run. On Ubuntu 22.04: "
            "sudo apt-get install openems python3-openems")
    workdir = Path(tempfile.mkdtemp(prefix="desk-openems-run-"))
    try:
        spec = workdir / "spec.json"
        result = workdir / "result.npz"
        spec.write_text(json.dumps({"model": dataclasses.asdict(model)}), encoding="utf-8")
        log = workdir / "openems.log"
        with log.open("w", encoding="utf-8") as handle:
            proc = subprocess.run(
                [sys.executable, "-m", "signal_integrity.fdtd_worker", str(spec), str(result)],
                cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT, timeout=timeout_s,
                check=False)
        text = log.read_text(encoding="utf-8", errors="replace")
        if log_path is not None:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            Path(log_path).write_text(text, encoding="utf-8")
        if proc.returncode != 0 or not result.exists():
            raise RuntimeError(f"openEMS run failed (exit {proc.returncode}); last output:\n{text[-1500:]}")
        data = np.load(result)
        return data["freq"], data["s11"], data["s21"]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _require_openems():
    try:
        from CSXCAD import ContinuousStructure  # noqa: F401
        from openEMS import openEMS  # noqa: F401
    except ImportError as exc:
        raise OpenEMSUnavailable(
            "openEMS and CSXCAD are needed for the 3D run. On Ubuntu 22.04: "
            "sudo apt-get install openems python3-openems") from exc


def build_and_run(model: TraceModel, sim_dir: Optional[Path] = None,
                  keep: bool = False) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run the FDTD simulation. Returns (freq_hz, S11, S21) as complex arrays."""
    _require_openems()
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS

    unit = 1e-3
    freq = model.freq_hz
    w = model.width_mm
    h = model.h_mm
    via1, via2 = model.via.x_mm
    ra = model.via.antipad_mm / 2.0
    rv = 0.3   # half-width of the modelled via conductor (0.6 mm, the pad size)
    # Each port's outer section is 10 mm, so its measurement plane (the middle of the port box)
    # sits 5 mm from the absorbing boundary. At 2 mm the near field corrupted the port modes.
    x_lo = -10.0
    x_hi = model.length_mm + 10.0
    wg = model.ground_width_mm / 2.0
    ws = (w + 2.0 * model.ground_clearance_mm) / 2.0
    # Each port box runs from the outer edge of the mesh (inside the absorbing boundary) to its
    # device plane, as the openEMS MSL tutorial does. The strip between the ports is drawn
    # separately, without overlapping the port boxes: overlapping copper was flagged as unused.
    x_port1 = (x_lo, 0.0)
    x_port2 = (x_hi, model.length_mm)

    fdtd = openEMS(NrTS=model.time_steps, EndCriteria=model.end_criteria)
    f_center = 0.5 * model.f_stop_hz
    # A Gaussian pulse centred at 3 GHz, as in the openEMS microstrip tutorial.
    fdtd.SetGaussExcite(3.0e9, model.gauss_fc_hz)
    # Absorbing boundaries on all six faces. The ground is drawn explicitly below, so the
    # bottom face must not be a PEC wall: that would short the bottom trace and the antipads.
    fdtd.SetBoundaryCond(["PML_8"] * 6)

    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(unit)

    # Dielectric: 1.6 mm FR-4 with a loss tangent at the centre frequency.
    kappa = 2 * math.pi * f_center * 8.8541878128e-12 * model.er * model.tand
    substrate = csx.AddMaterial("FR4")
    substrate.SetMaterialProperty(epsilon=model.er, kappa=kappa)
    substrate.AddBox(priority=0, start=[x_lo, -wg, 0], stop=[x_hi, wg, h])

    copper = csx.AddMetal("copper")
    # Ground pour on the bottom layer, with antipads around both vias and a slot
    # for the bottom trace. Built from rectangles, since CSXCAD has no subtraction.
    # The bottom trace is wider than the antipad, so the pour is cut to the slot width (ws) at
    # each via: between the slot edges there is no copper, and the trace does not touch the pour.
    ground_slices = [
        ([x_lo, -wg, 0], [via1 - ra, wg, 0]),
        ([via2 + ra, -wg, 0], [x_hi, wg, 0]),
        ([via1 - ra, ws, 0], [via1 + ra, wg, 0]),
        ([via1 - ra, -wg, 0], [via1 + ra, -ws, 0]),
        ([via2 - ra, ws, 0], [via2 + ra, wg, 0]),
        ([via2 - ra, -wg, 0], [via2 + ra, -ws, 0]),
        ([via1 + ra, ws, 0], [via2 - ra, wg, 0]),
        ([via1 + ra, -wg, 0], [via2 - ra, -ws, 0]),
    ]
    for start, stop in ground_slices:
        copper.AddBox(start=start, stop=stop, priority=10)
    # Top trace: device plane 1 to via 1, and via 2 to device plane 2.
    copper.AddBox(start=[0.0, -w / 2, h], stop=[via1, w / 2, h], priority=10)
    copper.AddBox(start=[via2, -w / 2, h], stop=[model.length_mm, w / 2, h], priority=10)
    # Bottom trace inside the slot, joining the two via barrels.
    copper.AddBox(start=[via1, -w / 2, 0], stop=[via2, w / 2, 0], priority=10)
    # Vias: a square conductor through the substrate, 0.6 mm wide (the pad diameter). A round
    # barrel of drill size is below the mesh, and a 0.3 mm square puts lines 0.15 mm apart, which
    # forces a tiny time step and a run that ends before the energy has left. The drill and
    # antipad still set the via impedance in the closed-form check.
    for x in (via1, via2):
        copper.AddBox(start=[x - rv, -rv, 0], stop=[x + rv, rv, h], priority=20)


    # Mesh: lines at every feature edge, smoothed to the target resolution.
    # Fine lines where the fields change fastest: the 0.25 mm strip, the via barrels and the
    # antipads, and four layers of substrate. The smoothing grows the cells away from them.
    x_via = [via + sign * d for via in (via1, via2) for sign in (-1.0, 1.0)
             for d in (rv, ra)]
    y_via = [-rv, rv, -ra, ra]
    x_fine, y_fine = [], []
    if model.fine_mesh:
        x_fine = [via + sign * d for via in (via1, via2) for sign in (-1.0, 1.0)
                  for d in (0.3, 0.6)]
        y_fine = [sign * (w / 2 + d) for sign in (-1.0, 1.0) for d in (0.0, 0.15, 0.3)]
    x_lines = [x_lo, x_hi, x_port1[0], x_port1[1], x_port2[0], x_port2[1], via1, via2] + x_via + x_fine
    y_lines = [-wg, wg, -w / 2, w / 2, -ws, ws] + y_via + y_fine
    z_lines = [-model.air_mm, 0.0, 0.25 * h, 0.5 * h, 0.75 * h, h, h + model.air_mm]
    mesh.AddLine("x", x_lines)
    mesh.AddLine("y", y_lines)
    mesh.AddLine("z", z_lines)
    mesh.SmoothMeshLines("all", model.mesh_mm, ratio=1.4)
    # Ports are created after the mesh: openEMS checks the mesh lines inside each port box.
    # Microstrip port boxes follow openEMS's convention: start is the outer end of the line at
    # strip height, stop points towards the device at the ground plane.
    port_start1 = [x_port1[0], -w / 2, h]
    port_stop1 = [x_port1[1], w / 2, 0]
    port_start2 = [x_port2[0], -w / 2, h]
    port_stop2 = [x_port2[1], w / 2, 0]
    port = [None, None]
    port[0] = fdtd.AddMSLPort(1, copper, port_start1, port_stop1, "x", "z", excite=-1,
                              FeedShift=0.5, priority=10)
    port[1] = fdtd.AddMSLPort(2, copper, port_start2, port_stop2, "x", "z", excite=0, priority=10)

    owned = sim_dir is None
    folder = Path(tempfile.mkdtemp(prefix="desk-openems-")) if owned else Path(sim_dir)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        # Write the geometry explicitly, then solve. The solver's log goes to the console.
        csx.Write2XML(str(folder / "csx.xml"))
        fdtd.Run(str(folder), cleanup=False, verbose=2)
        # The reference is passed as an array, one value per frequency. A plain float makes the
        # Debian bindings read a field that only the other port types set (ut_tot).
        z_ref = np.full(len(freq), Z_REF)
        for p in port:
            # Refer S-parameters to 50 ohm, not to the line's own impedance.
            p.CalcPort(str(folder), freq, ref_impedance=z_ref)
        s11 = port[0].uf_ref / port[0].uf_inc
        s21 = port[1].uf_ref / port[0].uf_inc
    finally:
        if owned and not keep and sys.exc_info()[0] is None:
            shutil.rmtree(folder, ignore_errors=True)
    return freq, np.asarray(s11, dtype=complex), np.asarray(s21, dtype=complex)
