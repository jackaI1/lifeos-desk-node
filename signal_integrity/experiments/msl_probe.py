"""Temporary probe: one 50 ohm microstrip line in two boundary setups. Not part of the model."""
import sys
import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS

H, ER, W = 1.6, 4.5, 3.0
L = 16.0
F0 = 3e9


def run(variant: str, res: float = 0.5, n_ts: int = 12000):
    fdtd = openEMS(NrTS=n_ts, EndCriteria=1e-3)
    fdtd.SetGaussExcite(F0, F0)
    if variant == "pec_bottom":
        fdtd.SetBoundaryCond(["PML_8", "PML_8", "PML_8", "PML_8", "PEC", "PML_8"])
        zmin = 0.0
    else:
        fdtd.SetBoundaryCond(["PML_8"] * 6)
        zmin = -6.0
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)
    x_lo, x_hi = -10.0, L + 10.0
    mesh.AddLine("x", [-10.0, 0.0, L, L + 10.0, -10.0 - 0.0])
    mesh.AddLine("y", [-W / 2, 0.0, W / 2, -15.0, 15.0])
    mesh.AddLine("z", [zmin, 0.0, H, H + 8.0])
    mesh.SmoothMeshLines("all", res, ratio=1.4)
    sub = csx.AddMaterial("FR4")
    sub.SetMaterialProperty(epsilon=ER)
    sub.AddBox([x_lo, -15.0, 0.0], [x_hi, 15.0, H], priority=0)
    pec = csx.AddMetal("pec")
    if variant != "pec_bottom":
        pec.AddBox([x_lo, -15.0, 0.0], [x_hi, 15.0, 0.0], priority=10)
    port = [None, None]
    port[0] = fdtd.AddMSLPort(1, pec, [-10.0, -W / 2, H], [0.0, W / 2, 0.0], "x", "z",
                              excite=-1, FeedShift=0.5, priority=10)
    port[1] = fdtd.AddMSLPort(2, pec, [L + 10.0, -W / 2, H], [L, W / 2, 0.0], "x", "z",
                              excite=0, priority=10)
    fdtd.Run("/tmp/msl-probe-" + variant, cleanup=True, verbose=1)
    f = np.arange(1, 13) * 0.5e9
    ref = np.full(len(f), 50.0)
    for p in port:
        p.CalcPort("/tmp/msl-probe-" + variant, f, ref_impedance=ref)
    s11 = port[0].uf_ref / port[0].uf_inc
    s21 = port[1].uf_ref / port[0].uf_inc
    for i in range(0, len(f), 2):
        print(f"PROBE {variant} {f[i]/1e9:4.1f} GHz  S11 {20*np.log10(abs(s11[i])+1e-30):8.2f} dB"
              f"  S21 {20*np.log10(abs(s21[i])+1e-30):8.2f} dB", flush=True)


if __name__ == "__main__":
    for variant in sys.argv[1:]:
        run(variant)
