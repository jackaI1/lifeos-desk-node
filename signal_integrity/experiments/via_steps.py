"""Temporary diagnostic: add one via feature at a time to the working probe."""
import subprocess
import sys

VARIANTS = ["probe", "probe_via", "probe_antipad"]


def build(variant: str) -> None:
    import tempfile
    import numpy as np
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS
    h, er, w, L = 1.6, 4.5, 2.97, 24.0
    xl, xh, wg = -10.0, L + 10.0, 15.0
    xv, rv, ra = L / 2.0, 0.3, 0.6
    fdtd = openEMS(NrTS=12000, EndCriteria=1e-3)
    fdtd.SetGaussExcite(3e9, 3e9)
    fdtd.SetBoundaryCond(["PML_8"] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)
    xs = [xl, 0.0, L, xh, xv - rv, xv + rv, xv - ra, xv + ra]
    ys = [-w / 2, 0.0, w / 2, -wg, wg, -rv, rv, -ra, ra]
    zs = [-8.0, 0.0, 0.25 * h, 0.5 * h, 0.75 * h, h, h + 8.0]
    mesh.AddLine("x", xs)
    mesh.AddLine("y", ys)
    mesh.AddLine("z", zs)
    mesh.SmoothMeshLines("all", 0.5, ratio=1.4)
    sub = csx.AddMaterial("FR4")
    sub.SetMaterialProperty(epsilon=er)
    sub.AddBox([xl, -wg, 0.0], [xh, wg, h], priority=0)
    pec = csx.AddMetal("pec")
    if variant == "probe_antipad":
        pec.AddBox([xl, -wg, 0.0], [xv - ra, wg, 0.0], priority=10)
        pec.AddBox([xv + ra, -wg, 0.0], [xh, wg, 0.0], priority=10)
        pec.AddBox([xv - ra, ra, 0.0], [xv + ra, wg, 0.0], priority=10)
        pec.AddBox([xv - ra, -wg, 0.0], [xv + ra, -ra, 0.0], priority=10)
    else:
        pec.AddBox([xl, -wg, 0.0], [xh, wg, 0.0], priority=10)
    pec.AddBox([0.0, -w / 2, h], [L, w / 2, h], priority=10)
    if variant == "probe_via":
        pec.AddBox([xv - rv, -rv, 0.0], [xv + rv, rv, h], priority=20)
    port = [None, None]
    port[0] = fdtd.AddMSLPort(1, pec, [xl, -w / 2, h], [0.0, w / 2, 0.0], "x", "z", excite=-1, FeedShift=0.5,
                              Feed_R=50, priority=10)
    port[1] = fdtd.AddMSLPort(2, pec, [xh, -w / 2, h], [L, w / 2, 0.0], "x", "z", excite=0, Feed_R=50,
                              priority=10)
    folder = tempfile.mkdtemp(prefix="steps-")
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
