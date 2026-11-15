"""Temporary diagnostic: S21 of a plain through trace against a trace with a via pair."""
import subprocess
import sys

VARIANTS = ["through", "via_pair"]


def build(variant: str) -> None:
    import tempfile
    import numpy as np
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS
    h, er, w, L = 1.6, 4.5, 2.97, 24.0
    fdtd = openEMS(NrTS=12000, EndCriteria=1e-3)
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
    if variant == "through":
        cu.AddBox([x_lo, -wg, 0.0], [x_hi, wg, 0.0], priority=10)
        cu.AddBox([0.0, -w / 2, h], [L, w / 2, h], priority=10)
    else:
        cu.AddBox([x_lo, -wg, 0.0], [8 - 0.6, wg, 0.0], priority=10)
        cu.AddBox([16 + 0.6, -wg, 0.0], [x_hi, wg, 0.0], priority=10)
        cu.AddBox([8 - 0.6, 1.785, 0.0], [8 + 0.6, wg, 0.0], priority=10)
        cu.AddBox([8 - 0.6, -wg, 0.0], [8 + 0.6, -1.785, 0.0], priority=10)
        cu.AddBox([16 - 0.6, 1.785, 0.0], [16 + 0.6, wg, 0.0], priority=10)
        cu.AddBox([16 - 0.6, -wg, 0.0], [16 + 0.6, -1.785, 0.0], priority=10)
        cu.AddBox([8 + 0.6, 1.785, 0.0], [16 - 0.6, wg, 0.0], priority=10)
        cu.AddBox([8 + 0.6, -wg, 0.0], [16 - 0.6, -1.785, 0.0], priority=10)
        cu.AddBox([0.0, -w / 2, h], [8.0, w / 2, h], priority=10)
        cu.AddBox([16.0, -w / 2, h], [L, w / 2, h], priority=10)
        cu.AddBox([8.0, -w / 2, 0.0], [16.0, w / 2, 0.0], priority=10)
        cu.AddBox([8 - 0.15, -0.15, 0.0], [8 + 0.15, 0.15, h], priority=20)
        cu.AddBox([16 - 0.15, -0.15, 0.0], [16 + 0.15, 0.15, h], priority=20)
    port = [None, None]
    port[0] = fdtd.AddMSLPort(1, cu, [x_lo, -w / 2, h], [0.0, w / 2, 0.0], "x", "z", excite=-1, FeedShift=0.5, priority=10)
    port[1] = fdtd.AddMSLPort(2, cu, [x_hi, -w / 2, h], [L, w / 2, 0.0], "x", "z", excite=0, priority=10)
    folder = tempfile.mkdtemp(prefix="via-min-")
    fdtd.Run(folder, cleanup=False, verbose=1)
    f = np.arange(1, 13) * 0.5e9
    for p in port:
        p.CalcPort(folder, f, ref_impedance=np.full(len(f), 50.0))
    s11 = port[0].uf_ref / port[0].uf_inc
    s21 = port[1].uf_ref / port[0].uf_inc
    for i in (1, 3, 5, 7, 9, 11):
        print(f"VIAMIN {variant} {f[i]/1e9:4.1f} GHz S21 {20*np.log10(abs(s21[i])+1e-30):8.2f} dB "
              f"S11 {20*np.log10(abs(s11[i])+1e-30):8.2f} dB", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        build(sys.argv[1])
    else:
        for v in VARIANTS:
            proc = subprocess.run([sys.executable, __file__, v], capture_output=True, text=True)
            print((proc.stdout + proc.stderr).count("VIAMIN") and "", end="")
            for line in (proc.stdout + proc.stderr).splitlines():
                if line.startswith("VIAMIN"):
                    print(line, flush=True)
            if proc.returncode:
                print(f"VIAMIN {v} exit={proc.returncode}", proc.stderr[-400:], flush=True)
