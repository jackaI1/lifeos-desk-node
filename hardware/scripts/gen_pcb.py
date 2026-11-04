#!/usr/bin/env python3
"""Build hardware/desk-node.kicad_pcb from design.py with KiCad 8's pcbnew API.

Run with KiCad's bundled Python (see hardware/scripts/build.sh):

  gen_pcb.py place   -> board outline, footprints, nets, keep-outs (unrouted)
  gen_pcb.py dsn     -> export Specctra DSN for Freerouting
  gen_pcb.py ses     -> import Freerouting session, add GND pours + stitching

Board coordinates below are in mm relative to the board's top-left corner.
"""
import os
import sys
import subprocess
import xml.etree.ElementTree as ET

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design  # noqa: E402
from gen_schematic import uid  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(HW, f"{design.PROJECT}.kicad_pcb")
FP_DIRS = [os.environ.get("KICAD8_FOOTPRINT_DIR", ""),
           "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints",
           "/usr/share/kicad/footprints"]

OX, OY = 100.0, 100.0          # board origin on the KiCad canvas
W, H = 50.0, 55.0              # board size
CORNER = 2.0                   # outline corner radius
ANTENNA_KEEPOUT = 0.0          # module antenna region (6.19 mm) + margin, full width

# ref -> (x, y, rotation_deg, side)
PLACEMENT = {
    # ESP32 module, antenna flush with the top edge
    "U1": (25.0, 6.56, 0, "F"),
    "C4": (13.4, 2.8, 0, "F"),
    "C3": (13.4, 5.4, 0, "F"),
    "R3": (12.6, 15.8, 0, "F"),
    "C5": (12.6, 18.2, 0, "F"),
    "SW1": (6.0, 19.5, 90, "F"),
    "R6": (38.2, 16.0, 90, "F"),
    "R7": (40.2, 16.0, 90, "F"),
    "J3": (46.6, 12.6, 0, "F"),
    "R4": (37.0, 25.5, 0, "F"),
    "SW2": (38.0, 30.5, 0, "F"),
    # power entry, bottom-left: USB-C -> polyfuse -> TVS -> LDO
    "J1": (14.0, 50.4, 0, "F"),
    "R1": (10.0, 43.0, 90, "F"),
    "R2": (18.5, 43.0, 90, "F"),
    "F1": (14.0, 41.0, 0, "F"),
    "D1": (7.5, 39.0, 90, "F"),
    "C1": (14.0, 36.5, 90, "F"),
    "U2": (22.0, 34.0, 0, "F"),
    "C2": (28.5, 34.0, 90, "F"),
    "C8": (30.5, 34.0, 90, "F"),
    "R8": (4.5, 30.0, 0, "F"),
    "D2": (4.5, 27.5, 180, "F"),
    # display header + bulk cap, bottom-middle
    "J2": (21.5, 51.0, 180, "F"),
    "C7": (14.5, 28.0, 90, "F"),
    "J4": (15.0, 23.8, 90, "F"),
    "R9": (23.8, 27.0, 0, "F"),
    "R10": (28.0, 27.0, 0, "F"),
    "R11": (32.0, 27.0, 0, "F"),
    # SHT31 on a slotted peninsula, bottom-right, far from LDO and ESP32
    "U3": (44.5, 49.5, 0, "F"),
    "C6": (44.5, 46.2, 0, "F"),
    "R5": (40.5, 50.0, 90, "F"),
    # mounting holes (M3, no copper)
    "H1": (4.0, 11.0, 0, "F"),
    "H2": (46.5, 31.0, 0, "F"),
    "H3": (4.0, 51.0, 0, "F"),
    "H4": (34.3, 51.0, 0, "F"),
}

# Thermal-isolation slots around the sensor peninsula (x1, y1, x2, y2), 1 mm wide
SLOTS = [(37.0, 42.0, 38.0, 51.5), (37.0, 42.0, 48.5, 43.0)]
PENINSULA = (38.0, 43.0, W, H)  # no copper pour here (sensor sees air, not ground plane heat)


def mm(x, y):
    return pcbnew.VECTOR2I_MM(OX + x, OY + y)


def fp_dir():
    for d in FP_DIRS:
        if d and os.path.isdir(d):
            return d
    sys.exit("KiCad 8 footprint library not found; set KICAD8_FOOTPRINT_DIR")


def add_line(board, a, b, layer, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(mm(*a))
    s.SetEnd(mm(*b))
    s.SetLayer(layer)
    s.SetWidth(pcbnew.FromMM(width))
    board.Add(s)


def add_arc(board, center, start, angle_deg, layer, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetCenter(mm(*center))
    s.SetStart(mm(*start))
    s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(angle_deg, pcbnew.DEGREES_T), True)
    s.SetLayer(layer)
    s.SetWidth(pcbnew.FromMM(width))
    board.Add(s)


def outline(board):
    e, r = pcbnew.Edge_Cuts, CORNER
    add_line(board, (r, 0), (W - r, 0), e)
    add_line(board, (W, r), (W, H - r), e)
    add_line(board, (W - r, H), (r, H), e)
    add_line(board, (0, H - r), (0, r), e)
    add_arc(board, (W - r, r), (W - r, 0), 90, e)
    add_arc(board, (W - r, H - r), (W, H - r), 90, e)
    add_arc(board, (r, H - r), (r, H), 90, e)
    add_arc(board, (r, r), (0, r), 90, e)
    # One closed L-shaped cutout: overlapping rectangles form an invalid outline.
    points = [(37, 42), (48.5, 42), (48.5, 43), (38, 43), (38, 51.5), (37, 51.5)]
    for a, b in zip(points, points[1:] + points[:1]):
        add_line(board, a, b, e)


def rect_zone(board, x1, y1, x2, y2, layers, net=None, rule=None, name="", priority=0):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    for layer in layers:
        ls.AddLayer(layer)
    z.SetLayerSet(ls)
    o = z.Outline()
    o.NewOutline()
    for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        p = mm(x, y)
        o.Append(p.x, p.y)
    if name:
        z.SetZoneName(name)
    if rule:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowCopperPour("pour" in rule)
        z.SetDoNotAllowTracks("tracks" in rule)
        z.SetDoNotAllowVias("vias" in rule)
        z.SetDoNotAllowPads("pads" in rule)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetNet(net)
        z.SetAssignedPriority(priority)
        z.SetLocalClearance(pcbnew.FromMM(0.3))
        z.SetMinThickness(pcbnew.FromMM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(pcbnew.FromMM(0.3))
        z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.4))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


def keepouts(board):
    both = (pcbnew.F_Cu, pcbnew.B_Cu)
    # Espressif: no copper, traces, vias or components under/near the PCB antenna.
    rect_zone(board, 0, -22, W, ANTENNA_KEEPOUT, both, rule="pour tracks vias pads",
              name="ANTENNA_KEEPOUT")
    # Sensor peninsula: signal traces allowed, but no ground pour (thermal isolation)
    rect_zone(board, *PENINSULA, both, rule="pour", name="SENSOR_NO_POUR")
    for x1, y1, x2, y2 in SLOTS:
        rect_zone(board, x1 - 0.3, y1 - 0.3, x2 + 0.3, y2 + 0.3, both,
                  rule="pour tracks vias pads", name="SLOT")


def silk_text(board, text, x, y, size=1.0, layer=None, angle=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(mm(x, y))
    t.SetLayer(layer if layer is not None else pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I_MM(size, size))
    t.SetTextThickness(pcbnew.FromMM(size * 0.15))
    t.SetTextAngleDegrees(angle)
    if t.GetLayer() == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


def place():
    board = pcbnew.NewBoard(PCB)
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    board.SetFileName(PCB)

    # Use KiCad's actual netlist, including hierarchical signal names and each
    # no-connect net, so PCB/schematic parity checks every pad without exceptions.
    os.makedirs(os.path.join(HW, "build"), exist_ok=True)
    xml = os.path.join(HW, "build", "netlist.xml")
    cli = os.environ.get("KICAD_CLI", "kicad-cli")
    subprocess.run([cli, "sch", "export", "netlist", "--format", "kicadxml",
                    "--output", xml, os.path.join(HW, design.PROJECT + ".kicad_sch")], check=True)
    nets, pin_nets = {}, {}
    for net in ET.parse(xml).findall("./nets/net"):
        name = net.attrib["name"]
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni
        for node in net.findall("node"):
            pin_nets[(node.attrib["ref"], node.attrib["pin"])] = ni

    lib = fp_dir()
    for c in design.COMPONENTS:
        libname, fpname = c["fp"].split(":")
        directory = os.path.join(HW, "DeskNode.pretty") if libname == "DeskNode" else os.path.join(lib, libname + ".pretty")
        fp = pcbnew.FootprintLoad(directory, fpname)
        if fp is None:
            sys.exit(f"footprint {c['fp']} not found")
        fp.SetFPID(pcbnew.LIB_ID(libname, fpname))
        fp.SetReference(c["ref"])
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + uid("sym", c["ref"])))
        fp.SetSheetname("Root")
        fp.SetSheetfile(f"{design.PROJECT}.kicad_sch")
        for key in ("LCSC", "MPN"):
            if c.get(key.lower()):
                f = pcbnew.PCB_FIELD(fp, fp.GetFieldCount(), key)
                f.SetText(c[key.lower()])
                f.SetVisible(False)
                f.SetLayer(pcbnew.F_Fab)
                fp.AddField(f)
        if not c.get("bom", True):
            fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        x, y, rot, side = PLACEMENT[c["ref"]]
        board.Add(fp)
        fp.SetPosition(mm(x, y))
        fp.SetOrientationDegrees(rot)
        if side == "B":
            fp.Flip(fp.GetPosition(), False)
        for pad in fp.Pads():
            net = pin_nets.get((c["ref"], pad.GetNumber()))
            if net:
                pad.SetNet(net)
        # keep reference designators small and on silk
        ref = fp.Reference()
        ref.SetTextSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
        ref.SetTextThickness(pcbnew.FromMM(0.12))
        ref.SetVisible(False)

    outline(board)
    keepouts(board)
    silk_text(board, "ANTENNA OUTSIDE PCB", 25, -10, 1.0, layer=pcbnew.Dwgs_User)
    silk_text(board, "USB 5V", 14, 43.5, 0.8)
    silk_text(board, "RESET", 6, 24.2, 0.8)
    silk_text(board, "BOOT", 38, 35, 0.8)
    silk_text(board, "I2C", 25, 42, 0.8)
    silk_text(board, "SPI OLED", 23, 21.4, 0.8)
    silk_text(board, "UART 3V3", 43, 10, 0.7)
    silk_text(board, f"LifeOS desk node rev {design.REVISION}", 25, 30.0, 1.0, layer=pcbnew.B_SilkS)
    silk_text(board, "github.com/jackaI1/lifeos-desk-node", 25, 32.0, 0.8, layer=pcbnew.B_SilkS)
    pcbnew.SaveBoard(PCB, board)
    print(f"placed {len(design.COMPONENTS)} footprints -> {PCB}")


def export_dsn(dsn):
    board = pcbnew.LoadBoard(PCB)
    # KiCad 8 DSN export treats pour-only rule areas as routing keep-outs.
    # Remove only these from the in-memory export; retain them in the saved PCB.
    for z in list(board.Zones()):
        if z.GetIsRuleArea() and not z.GetDoNotAllowTracks() and not z.GetDoNotAllowVias():
            board.Remove(z)
    ok = pcbnew.ExportSpecctraDSN(board, dsn)
    if not ok:
        sys.exit("DSN export failed")
    print(f"exported {dsn}")


def import_ses(ses):
    board = pcbnew.LoadBoard(PCB)
    if not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit("SES import failed")
    from finish_routes import finish
    finish(board)
    gnd = board.FindNet(design.GND)
    both = (pcbnew.F_Cu, pcbnew.B_Cu)
    # Inset the pour from the board edge; the antenna rule area clips the top.
    for layer in both:
        rect_zone(board, 0.0, 0.0, W, H, (layer,), net=gnd, name=f"GND_{layer}")
    # SOT-223 tab is +3V3, so a dedicated output copper area spreads LDO heat.
    sink = rect_zone(board, 17, 28.5, 33.5, 39.5, (pcbnew.F_Cu,),
                     net=board.FindNet(design.V3), name="LDO_HEATSINK", priority=1)
    sink.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    stitch(board, gnd)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)
    print("imported routes, poured GND")


def stitch(board, gnd):
    """Drop GND stitching vias on a grid wherever they keep clear of everything."""
    ds = board.GetDesignSettings()
    drill, dia = pcbnew.FromMM(0.3), pcbnew.FromMM(0.6)
    clearance = pcbnew.FromMM(0.5)
    blocked = []
    for fp in board.GetFootprints():
        bb = fp.GetBoundingBox(False, False)
        blocked.append(bb)
    for t in board.GetTracks():
        bb = t.GetBoundingBox()
        blocked.append(bb)
    excl = [(0, 0, W, ANTENNA_KEEPOUT + 1.0), PENINSULA,
            (SLOTS[0][0] - 1, SLOTS[0][1] - 1, SLOTS[0][2] + 1, SLOTS[0][3] + 1),
            (SLOTS[1][0] - 1, SLOTS[1][1] - 1, SLOTS[1][2] + 1, SLOTS[1][3] + 1)]
    n = 0
    y = ANTENNA_KEEPOUT + 2.0
    while y < H - 1.5:
        x = 1.5
        while x < W - 1.5:
            if not any(a <= x <= c and b <= y <= d for a, b, c, d in excl):
                p = mm(x, y)
                box = pcbnew.BOX2I(pcbnew.VECTOR2I(p.x - dia // 2 - clearance, p.y - dia // 2 - clearance),
                                   pcbnew.VECTOR2I(dia + 2 * clearance, dia + 2 * clearance))
                if not any(b.Intersects(box) for b in blocked):
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(p)
                    v.SetDrill(drill)
                    v.SetWidth(dia)
                    v.SetNet(gnd)
                    board.Add(v)
                    blocked.append(box)
                    n += 1
            x += 4.0
        y += 4.0
    print(f"added {n} stitching vias")
    del ds


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "place"
    if cmd == "place":
        place()
    elif cmd == "dsn":
        export_dsn(sys.argv[2])
    elif cmd == "ses":
        import_ses(sys.argv[2])
    else:
        sys.exit(__doc__)
