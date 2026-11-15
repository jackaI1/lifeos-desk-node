"""Temporary diagnostic: does a square via box conduct, and is it reported unused?"""
import subprocess
import sys

VARIANTS = ["top_bottom_via", "top_bottom_novia", "top_bottom_viacyl"]


def build(variant: str) -> None:
    import tempfile
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS
    h, er, w, L = 1.6, 4.5, 2.97, 24.0
    fdtd = openEMS(NrTS=100, EndCriteria=1e-3)
    fdtd.SetGaussExcite(3e9, 3e9)
    fdtd.SetBoundaryCond(["PML_8"] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)
    x_lo, x_hi, wg = -4.0, L + 4.0, 15.0
    mesh.AddLine("x", [x_lo, 0.0, 8.0, 16.0, L, x_hi, 7.85, 8.15, 15.85, 16.15, 7.4, 8.6, 15.4, 16.6])
    mesh.AddLine("y", [-wg, wg, -w / 2, w / 2, -1.785, 1.785, -0.15, 0.15, -0.6, 0.6, 0.0])
    mesh.AddLine("z", [-8.0, 0.0, 0.25 * h, 0.5 * h, 0.75 * h, h, h + 8.0])
    mesh.SmoothMeshLines("all", 0.5, ratio=1.4)
    sub = csx.AddMaterial("FR4")
    sub.SetMaterialProperty(epsilon=er)
    sub.AddBox([x_lo, -wg, 0.0], [x_hi, wg, h], priority=0)
    cu = csx.AddMetal("copper")
    cu.AddBox([x_lo, -wg, 0.0], [x_hi, wg, 0.0], priority=10)
    cu.AddBox([0.0, -w / 2, h], [8.0, w / 2, h], priority=10)
    cu.AddBox([16.0, -w / 2, h], [L, w / 2, h], priority=10)
    cu.AddBox([8.0, -w / 2, 0.0], [16.0, w / 2, 0.0], priority=10)
    if variant == "top_bottom_via":
        cu.AddBox([8 - 0.15, -0.15, 0.0], [8 + 0.15, 0.15, h], priority=20)
        cu.AddBox([16 - 0.15, -0.15, 0.0], [16 + 0.15, 0.15, h], priority=20)
    elif variant == "top_bottom_viacyl":
        for x in (8.0, 16.0):
            cu.AddCylinder([x, 0, 0], [x, 0, h], 0.15, priority=20)
    fdtd.AddMSLPort(1, cu, [x_lo, -w / 2, h], [0.0, w / 2, 0.0], "x", "z", excite=-1, FeedShift=0.5, priority=10)
    fdtd.AddMSLPort(2, cu, [x_hi, -w / 2, h], [L, w / 2, 0.0], "x", "z", excite=0, priority=10)
    fdtd.Run(tempfile.mkdtemp(prefix="via-min-"), cleanup=False, verbose=2)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        build(sys.argv[1])
    else:
        for v in VARIANTS:
            proc = subprocess.run([sys.executable, __file__, v], capture_output=True, text=True)
            text = proc.stdout + proc.stderr
            print(f"VIAMIN {v}: exit={proc.returncode} unused={text.count('Unused primitive')}", flush=True)
