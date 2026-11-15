"""Temporary diagnostic: minimal copper configurations and the solver's unused-primitive count."""
import subprocess
import sys

VARIANTS = ["ground_top", "ground_top_port", "ground_ports", "ground_bottom", "ground_top_lowered", "ground_top_thick"]


def build_and_count(variant: str) -> None:
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS
    import tempfile, os
    h, er, w, L = 1.6, 4.5, 2.97, 24.0
    fdtd = openEMS(NrTS=100, EndCriteria=1e-3)
    fdtd.SetGaussExcite(3e9, 1.5e9)
    fdtd.SetBoundaryCond(["PML_8"] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)
    x_lo, x_hi = -4.0, L + 4.0
    wg = 15.0
    mesh.AddLine("x", [x_lo, 0.0, 8.0, 16.0, L, x_hi, 8 - 0.3, 8 + 0.3, 16 - 0.3, 16 + 0.3])
    mesh.AddLine("y", [-wg, wg, -w / 2, w / 2, -w / 2 - 0.3, w / 2 + 0.3, 0.0])
    mesh.AddLine("z", [-6.0, 0.0, 0.25 * h, 0.5 * h, 0.75 * h, h, h + 6.0])
    mesh.SmoothMeshLines("all", 0.5, ratio=1.4)
    sub = csx.AddMaterial("FR4")
    sub.SetMaterialProperty(epsilon=er)
    sub.AddBox([x_lo, -wg, 0.0], [x_hi, wg, h], priority=0)
    cu = csx.AddMetal("copper")
    if variant.startswith("ground"):
        cu.AddBox([x_lo, -wg, 0.0], [x_hi, wg, 0.0], priority=10)
    if "top" in variant:
        ztop = h - 0.001 if variant.endswith("lowered") else h
        if variant.endswith("thick"):
            cu.AddBox([0.0, -w / 2, h], [L, w / 2, h + 0.035], priority=10)
        else:
            cu.AddBox([0.0, -w / 2, ztop], [L, w / 2, ztop], priority=10)
    if "bottom" in variant:
        cu.AddBox([8.0, -w / 2, 0.0], [16.0, w / 2, 0.0], priority=10)
    if "port" in variant or "ports" in variant:
        fdtd.AddMSLPort(1, cu, [x_lo, -w / 2, h], [0.0, w / 2, 0.0], "x", "z", excite=-1, FeedShift=0.5, priority=10)
        fdtd.AddMSLPort(2, cu, [x_hi, -w / 2, h], [L, w / 2, 0.0], "x", "z", excite=0, priority=10)
    folder = tempfile.mkdtemp(prefix="unused-min-")
    fdtd.Run(folder, cleanup=False, verbose=2)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        build_and_count(sys.argv[1])
    else:
        for v in VARIANTS:
            proc = subprocess.run([sys.executable, __file__, v], capture_output=True, text=True)
            text = proc.stdout + proc.stderr
            print(f"MINIMAL {v}: exit={proc.returncode} unused={text.count('Unused primitive')}", flush=True)
