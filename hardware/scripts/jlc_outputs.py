#!/usr/bin/env python3
"""Turn kicad-cli BOM/position CSVs into JLCPCB assembly files and zip the Gerbers.

  fab/desk-node-bom-jlcpcb.csv  Comment, Designator, Footprint, LCSC Part #
  fab/desk-node-cpl-jlcpcb.csv  Designator, Mid X, Mid Y, Layer, Rotation
  fab/desk-node-gerbers.zip     Gerbers + Excellon drill files for upload

Parts without an LCSC number (mounting holes) are left out. Through-hole
headers are kept in the BOM so they can be ordered, but may be hand-soldered.
"""
import csv
import os
import sys
import zipfile

NAME = "desk-node"

# JLCPCB's pick-and-place rotation reference differs from KiCad's for some
# packages. Corrections stay empty until checked in JLCPCB's CPL preview;
# add entries here as {"footprint name prefix": degrees}.
ROTATION_FIX = {}


def bom(out):
    src = os.path.join(out, f"{NAME}-bom-kicad.csv")
    rows = list(csv.DictReader(open(src, newline="", encoding="utf-8")))
    dst = os.path.join(out, f"{NAME}-bom-jlcpcb.csv")
    n = 0
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for r in rows:
            if not r.get("LCSC"):
                continue
            fp = r["Footprint"].split(":")[-1]
            w.writerow([r["Value"], r["Designator"].replace(" ", ""), fp, r["LCSC"]])
            n += 1
    print(f"JLCPCB BOM: {n} lines -> {dst}")


def cpl(out):
    src = os.path.join(out, f"{NAME}-pos.csv")
    rows = list(csv.DictReader(open(src, newline="", encoding="utf-8")))
    dst = os.path.join(out, f"{NAME}-cpl-jlcpcb.csv")
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in rows:
            rot = float(r["Rot"])
            for prefix, fix in ROTATION_FIX.items():
                if r["Package"].startswith(prefix):
                    rot = (rot + fix) % 360
            layer = "Top" if r["Side"].lower().startswith("top") else "Bottom"
            w.writerow([r["Ref"], f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm",
                        layer, f"{rot:.0f}"])
    print(f"JLCPCB CPL: {len(rows)} parts -> {dst}")


def zip_gerbers(out):
    gdir = os.path.join(out, "gerbers")
    dst = os.path.join(out, f"{NAME}-gerbers.zip")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(gdir)):
            z.write(os.path.join(gdir, fn), fn)
    print(f"Gerber zip: {dst}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "fab"
    bom(out)
    cpl(out)
    zip_gerbers(out)
