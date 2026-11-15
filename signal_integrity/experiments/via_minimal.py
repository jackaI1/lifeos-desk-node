"""Temporary diagnostic: one-factor changes from the probe that worked."""
import subprocess
import sys

VARIANTS = ["probe_w297", "probe_L24_w297"]


def build(variant: str) -> None:
    import tempfile
    import numpy as np
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS
    h, er, w = 1.6, 4.5, (2.97 if "w297" in variant else 3.0)
    L = 24.0 if "L24" in variant else 16.0
    xl, xh = -10.0, L + 10.0
    fdtd = openEMS(NrTS=12000, EndCriteria=1e-3)
    fdtd.SetGaussExcite(3e9, 3e9)
    fdtd.SetBoundaryCond(["PML_8", "PML_8", "PML_8", "PML_8", "PML_8", "PML_8"])
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)
    wg = 15.0
    xs = [xl, 0.0, L, xh]
    ys = [-w / 2, 0.0, w / 2, -wg, wg]
    zs = [-6.0, 0.0, h, h + 8.0]
    if variant == "probe_zfine":
        zs = [-6.0, 0.0, 0.25 * h, 0.5 * h, 0.75 * h, h, h + 8.0]
    if variant == "probe_xylines":
        xs = xs + [7.85, 8.15, 15.85, 16.15, 7.4, 8.6, 15.4, 16.6]
        ys = ys + [-1.785, 1.785, -0.15, 0.15, -0.6, 0.6]
    mesh.AddLine("x", xs)
    mesh.AddLine("y", ys)
    mesh.AddLine("z", zs)
    mesh.SmoothMeshLines("all", 0.5, ratio=1.4)
    sub = csx.AddMaterial("FR4")
    sub.SetMaterialProperty(epsilon=er)
    sub.AddBox([xl, -wg, 0.0], [xh, wg, h], priority=0)
    pec = csx.AddMetal("pec")
    pec.AddBox([xl, -wg, 0.0], [xh, wg, 0.0], priority=10)
    pec.AddBox([0.0, -w / 2, h], [L, w / 2, h], priority=10)
    port = [None, None]
    port[0] = fdtd.AddMSLPort(1, pec, [xl, -w / 2, h], [0.0, w / 2, 0.0], "x", "z", excite=-1, FeedShift=0.5, priority=10)
    port[1] = fdtd.AddMSLPort(2, pec, [xh, -w / 2, h], [L, w / 2, 0.0], "x", "z", excite=0, priority=10)
    folder = tempfile.mkdtemp(prefix="probe-")
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
            for line in (proc.stdout + proc.stderr).splitlines():
                if line.startswith("VIAMIN"):
                    print(line, flush=True)
            if proc.returncode:
                print(f"VIAMIN {v} exit={proc.returncode}", proc.stderr[-300:], flush=True)
