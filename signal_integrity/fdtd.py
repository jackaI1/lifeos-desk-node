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

import math
import shutil
import sys
import tempfile
from dataclasses import dataclass
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
    mesh_mm: float = 0.25
    f_stop_hz: float = 6e9
    n_freq: int = 120           # frequency points, evenly spaced from one step to f_stop
    air_mm: float = 6.0
    end_criteria: float = 1e-4
    time_steps: int = 40000

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
        ground_width_mm=12.0,
        ground_clearance_mm=clearance_mm,
        via=ViaModel(via_x, drill_mm, pad_mm, antipad),
    )


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
    rd = model.via.drill_mm / 2.0
    x_lo = -4.0
    x_hi = model.length_mm + 4.0
    wg = model.ground_width_mm / 2.0
    ws = (w + 2.0 * model.ground_clearance_mm) / 2.0
    # Each port box spans 1.5 mm: openEMS needs at least five mesh lines along it.
    # The boxes mirror each other about the board centre, so the model stays symmetric.
    port_len = 1.5
    x_port1 = (-port_len, 0.0)
    x_port2 = (model.length_mm, model.length_mm + port_len)

    fdtd = openEMS(NrTS=model.time_steps, EndCriteria=model.end_criteria)
    f_center = 0.5 * model.f_stop_hz
    fdtd.SetGaussExcite(f_center, f_center)
    fdtd.SetBoundaryCond(["PML_8", "PML_8", "PML_8", "PML_8", "PEC", "PML_8"])

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
    ground_slices = [
        ([x_lo, -wg, 0], [via1 - ra, wg, 0]),
        ([via2 + ra, -wg, 0], [x_hi, wg, 0]),
        ([via1 - ra, ra, 0], [via1 + ra, wg, 0]),
        ([via1 - ra, -wg, 0], [via1 + ra, -ra, 0]),
        ([via2 - ra, ra, 0], [via2 + ra, wg, 0]),
        ([via2 - ra, -wg, 0], [via2 + ra, -ra, 0]),
        ([via1 + ra, ws, 0], [via2 - ra, wg, 0]),
        ([via1 + ra, -wg, 0], [via2 - ra, -ws, 0]),
    ]
    for start, stop in ground_slices:
        copper.AddBox(start=start, stop=stop, priority=10)

    # Top trace: port 1 to via 1, and via 2 to port 2.
    copper.AddBox(start=[x_lo, -w / 2, h], stop=[via1, w / 2, h], priority=10)
    copper.AddBox(start=[via2, -w / 2, h], stop=[x_hi, w / 2, h], priority=10)
    # Bottom trace inside the slot, joining the two via barrels.
    copper.AddBox(start=[via1, -w / 2, 0], stop=[via2, w / 2, 0], priority=10)
    # Vias: a barrel through the substrate. Pads are left out; the antipad sets the
    # clearance that the impedance depends on.
    for x in (via1, via2):
        copper.AddCylinder(start=[x, 0, 0], stop=[x, 0, h], radius=rd, priority=20)


    # Mesh: lines at every feature edge, smoothed to the target resolution.
    x_lines = [x_lo, x_hi, x_port1[0], x_port1[1], x_port2[0], x_port2[1], via1, via2,
               via1 - ra, via1 + ra, via2 - ra, via2 + ra]
    y_lines = [-wg, wg, -w / 2, w / 2, -ws, ws, -ra, ra, 0.0]
    z_lines = [0.0, h, h + model.air_mm]
    mesh.AddLine("x", x_lines)
    mesh.AddLine("y", y_lines)
    mesh.AddLine("z", z_lines)
    mesh.SmoothMeshLines("all", model.mesh_mm, ratio=1.4)
    # Ports are created after the mesh: openEMS checks the mesh lines inside each port box.
    port_start1 = [x_port1[0], -w / 2, 0]
    port_stop1 = [x_port1[1], w / 2, h]
    port_start2 = [x_port2[0], -w / 2, 0]
    port_stop2 = [x_port2[1], w / 2, h]
    port = [None, None]
    port[0] = fdtd.AddMSLPort(1, copper, port_start1, port_stop1, "x", "z", excite=1, Feed_R=50)
    port[1] = fdtd.AddMSLPort(2, copper, port_start2, port_stop2, "x", "z", excite=0, Feed_R=50)

    owned = sim_dir is None
    folder = Path(tempfile.mkdtemp(prefix="desk-openems-")) if owned else Path(sim_dir)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        # Write the geometry explicitly, then solve. The solver's log goes to the console.
        csx.Write2XML(str(folder / "csx.xml"))
        fdtd.Run(str(folder), cleanup=False, verbose=2)
        try:
            for p in port:
                # Refer S-parameters to 50 ohm. Without this, openEMS uses the line's own impedance.
                p.CalcPort(str(folder), freq, ref_impedance=Z_REF)
        except AttributeError as exc:
            listing = sorted(item.name for item in folder.iterdir())
            raise RuntimeError(
                f"openEMS wrote no port data in {folder}; files there: {listing[:40]}") from exc
        s11 = port[0].uf_ref / port[0].uf_inc
        s21 = port[1].uf_ref / port[0].uf_inc
    finally:
        if owned and not keep and sys.exc_info()[0] is None:
            shutil.rmtree(folder, ignore_errors=True)
    return freq, np.asarray(s11, dtype=complex), np.asarray(s21, dtype=complex)
