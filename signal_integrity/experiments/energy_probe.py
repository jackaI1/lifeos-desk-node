"""Temporary diagnostic: final solver energy for a through trace on the model's mesh."""
import subprocess
import sys


def through(folder: str) -> None:
    import numpy as np
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS
    h, er, w, L = 1.6, 4.5, 2.97, 24.0
    xl, xh, wg = -10.0, L + 10.0, 15.0
    fdtd = openEMS(NrTS=25000, EndCriteria=1e-3)
    fdtd.SetGaussExcite(3e9, 3e9)
    fdtd.SetBoundaryCond(["PML_8"] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)
    mesh.AddLine("x", [xl, 0.0, L, xh, 7.4, 7.7, 8.0, 8.3, 8.6, 16.0])
    mesh.AddLine("y", [-wg, wg, -w / 2, w / 2, -1.785, 1.785, -0.3, 0.3, -0.6, 0.6])
    mesh.AddLine("z", [-8.0, 0.0, 0.25 * h, 0.5 * h, 0.75 * h, h, h + 8.0])
    mesh.SmoothMeshLines("all", 0.5, ratio=1.4)
    sub = csx.AddMaterial("FR4")
    sub.SetMaterialProperty(epsilon=er)
    sub.AddBox([xl, -wg, 0.0], [xh, wg, h], priority=0)
    cu = csx.AddMetal("copper")
    cu.AddBox([xl, -wg, 0.0], [xh, wg, 0.0], priority=10)
    cu.AddBox([0.0, -w / 2, h], [L, w / 2, h], priority=10)
    p1 = fdtd.AddMSLPort(1, cu, [xl, -w / 2, h], [0.0, w / 2, 0.0], "x", "z", excite=-1, FeedShift=0.5, Feed_R=50, priority=10)
    p2 = fdtd.AddMSLPort(2, cu, [xh, -w / 2, h], [L, w / 2, 0.0], "x", "z", excite=0, Feed_R=50, priority=10)
    fdtd.Run(folder, cleanup=False, verbose=2)
    f = np.arange(1, 13) * 0.5e9
    for p in (p1, p2):
        p.CalcPort(folder, f, ref_impedance=np.full(len(f), 50.0))
    print(f"THROUGH S21 at 2 GHz {20*np.log10(abs((p2.uf_ref/p1.uf_inc)[3])+1e-30):.2f} dB", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "through":
        through("/tmp/energy-through")
    else:
        proc = subprocess.run([sys.executable, "-c", "import sys; sys.argv=['x','through']; from signal_integrity.experiments.energy_probe import through; through('/tmp/energy-through')"],
                              capture_output=True, text=True)
        lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if "Energy:" in ln or "THROUGH" in ln or "Warning" in ln]
        for ln in lines[-4:]:
            print("ENERGY", ln[:170], flush=True)
        print("ENERGY exit", proc.returncode, flush=True)
