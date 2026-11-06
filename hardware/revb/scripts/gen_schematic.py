#!/usr/bin/env python3
"""Generate hardware/revb/desk-node-b.kicad_sch (KiCad 8 format) from design.py.

Every connected pin gets a short wire stub ending in a net label or power
symbol; unused pins get a no-connect flag. Library symbols are copied from the
installed KiCad 8 symbol libraries and embedded in the schematic, so the file
opens without any project-specific library tables.

Usage: gen_schematic.py [--symbols DIR] [--out FILE]
"""
import argparse
import copy
import math
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design  # noqa: E402
from sexpr import Sym, dump, find, find1, parse  # noqa: E402

DEFAULT_SYMBOLS = [
    os.environ.get("KICAD8_SYMBOL_DIR", ""),
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols",
    "/usr/share/kicad/symbols",
]
NS = uuid.UUID("6f1b8f6e-2c55-4a59-9a43-6b1d6a0d5e11")
STUB = 2.54
FONT = [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]]]
FONT_HIDDEN = [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], [Sym("hide"), Sym("yes")]]


def uid(*key):
    return str(uuid.uuid5(NS, "/".join(map(str, key))))


def snap(at):
    """Snap a symbol origin to KiCad's 50 mil (1.27 mm) connection grid."""
    return (r(round(at[0] / 2.54) * 2.54), r(round(at[1] / 2.54) * 2.54))


def r(v):
    """Round to the 0.01 mm grid KiCad expects and avoid float noise."""
    return round(v * 100) / 100


class Libs:
    def __init__(self, path):
        self.path = path
        self.cache = {}

    def lib(self, name):
        if name not in self.cache:
            with open(os.path.join(self.path, name + ".kicad_sym"), encoding="utf-8") as f:
                tree = parse(f.read())
            self.cache[name] = {x[1]: x for x in find(tree, "symbol")}
        return self.cache[name]

    def symbol(self, lib_id):
        """Return a flattened copy of a library symbol named 'Lib:Name'."""
        lib, name = lib_id.split(":")
        syms = self.lib(lib)
        node = copy.deepcopy(syms[name])
        ext = find1(node, "extends")
        if ext:
            parent = copy.deepcopy(syms[ext[1]])
            child_props = {p[1]: p for p in find(node, "property")}
            out = [Sym("symbol"), name]
            for item in parent[2:]:
                if isinstance(item, list) and item[0] == "property":
                    out.append(child_props.pop(item[1], item))
                elif isinstance(item, list) and item[0] == "symbol":
                    item[1] = name + item[1][len(ext[1]):]
                    out.append(item)
                else:
                    out.append(item)
            # child-only properties go before the first unit sub-symbol
            first_unit = next(i for i, x in enumerate(out) if isinstance(x, list) and x[0] == "symbol")
            for p in child_props.values():
                out.insert(first_unit, p)
                first_unit += 1
            node = out
        node[1] = lib_id
        return node


def pins_of(sym):
    """Yield (number, name, type, x, y, angle, hidden) for unit 1 / common pins."""
    for unit in find(sym, "symbol"):
        for p in find(unit, "pin"):
            at = find1(p, "at")
            hidden = Sym("hide") in p or any(
                isinstance(x, list) and x[:2] == [Sym("hide"), Sym("yes")] for x in p)
            yield (find1(p, "number")[1], find1(p, "name")[1], str(p[1]),
                   float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0, hidden)


def pin_point(origin, px, py, angle):
    """Schematic position of a pin end and its outward unit vector (rotation 0)."""
    x, y = origin[0] + px, origin[1] - py
    a = math.radians(angle)
    dx, dy = -math.cos(a), math.sin(a)  # outward = away from the symbol body
    return (r(x), r(y)), (round(dx), round(dy))


def label_angle(d):
    return {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[d]


def power_rotation(net, d):
    if net == design.GND:  # GND symbol naturally points down
        return {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[d]
    return {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}[d]


POWER_LIB = {design.GND: "power:GND", design.V3: "power:+3V3",
             design.V5: "power:+5V", design.VBUS: "power:VBUS"}


class Sheet:
    def __init__(self, libs):
        self.libs = libs
        self.root = uid("root")
        self.items = []
        self.lib_symbols = {}
        self.pwr_n = 0

    def use(self, lib_id):
        if lib_id not in self.lib_symbols:
            self.lib_symbols[lib_id] = self.libs.symbol(lib_id)
        return self.lib_symbols[lib_id]

    def prop(self, name, value, at, hidden=False, angle=0, key=""):
        return [Sym("property"), name, value, [Sym("at"), r(at[0]), r(at[1]), angle],
                FONT_HIDDEN if hidden else FONT]

    def instance(self, ref, lib_id, value, at, rot=0, fp="", props=(), in_bom=True,
                 on_board=True, ref_at=None, val_at=None, hide_ref=False):
        sym = self.use(lib_id)
        lib_props = {p[1]: p for p in find(sym, "property")}

        def lib_pos(name, default):
            p = lib_props.get(name)
            if not p:
                return default
            a = find1(p, "at")
            return (at[0] + float(a[1]), at[1] - float(a[2]))

        node = [Sym("symbol"), [Sym("lib_id"), lib_id], [Sym("at"), r(at[0]), r(at[1]), rot],
                [Sym("unit"), 1], [Sym("exclude_from_sim"), Sym("no")],
                [Sym("in_bom"), Sym("yes" if in_bom else "no")],
                [Sym("on_board"), Sym("yes" if on_board else "no")],
                [Sym("dnp"), Sym("no")], [Sym("uuid"), uid("sym", ref)]]
        node.append(self.prop("Reference", ref, ref_at or lib_pos("Reference", (at[0] + 3, at[1] - 3)),
                              hidden=hide_ref))
        node.append(self.prop("Value", value, val_at or lib_pos("Value", (at[0] + 3, at[1] + 3)),
                              hidden=hide_ref and ref.startswith("#FLG")))
        node.append(self.prop("Footprint", fp, at, hidden=True))
        node.append(self.prop("Datasheet", lib_props.get("Datasheet", [0, 0, ""])[2], at, hidden=True))
        node.append(self.prop("Description", lib_props.get("Description", [0, 0, ""])[2], at, hidden=True))
        for k, v in props:
            node.append(self.prop(k, v, at, hidden=True))
        for num in sorted({p[0] for p in pins_of(sym)}):
            node.append([Sym("pin"), num, [Sym("uuid"), uid("pin", ref, num)]])
        node.append([Sym("instances"), [Sym("project"), design.PROJECT,
                     [Sym("path"), "/" + self.root, [Sym("reference"), ref], [Sym("unit"), 1]]]])
        self.items.append(node)
        return sym

    def wire(self, a, b):
        self.items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), a[0], a[1]], [Sym("xy"), b[0], b[1]]],
                           [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                           [Sym("uuid"), uid("wire", a, b)]])

    def label(self, net, at, d):
        ang = label_angle(d)
        just = [Sym("justify"), Sym("left" if ang in (0, 90) else "right"), Sym("bottom")]
        self.items.append([Sym("label"), net, [Sym("at"), at[0], at[1], ang],
                           [Sym("fields_autoplaced"), Sym("yes")],
                           [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], just],
                           [Sym("uuid"), uid("label", net, at)]])

    def power(self, net, at, d):
        self.pwr_n += 1
        ref = f"#PWR{self.pwr_n:02d}"
        rot = power_rotation(net, d)
        off = 5.0 if net == design.GND else 4.0
        val_at = (at[0] + d[0] * off, at[1] + d[1] * off)
        self.instance(ref, POWER_LIB[net], net, at, rot=rot, val_at=val_at, hide_ref=True)

    def pwr_flag(self, net, at):
        at = snap(at)
        self.pwr_n += 1
        flag_ref = f"#FLG{self.pwr_n:02d}"
        self.instance(flag_ref, "power:PWR_FLAG", "PWR_FLAG", at, hide_ref=True,
                      val_at=(at[0], at[1] - 4))
        # PWR_FLAG pin is at its origin; join it to a power symbol below it
        below = (at[0], r(at[1] + STUB))
        self.wire(at, below)
        self.power(net, below, (0, 1)) if net in POWER_LIB else self.label(net, below, (1, 0))

    def no_connect(self, at):
        self.items.append([Sym("no_connect"), [Sym("at"), at[0], at[1]], [Sym("uuid"), uid("nc", at)]])

    def text(self, at, s):
        self.items.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")],
                           [Sym("at"), at[0], at[1], 0],
                           [Sym("effects"), [Sym("font"), [Sym("size"), 2, 2]],
                            [Sym("justify"), Sym("left"), Sym("bottom")]],
                           [Sym("uuid"), uid("text", s)]])

    def component(self, c):
        c = dict(c, at=snap(c["at"]))
        props = []
        if c.get("lcsc"):
            props.append(("LCSC", c["lcsc"]))
        if c.get("mpn"):
            props.append(("MPN", c["mpn"]))
        sym = self.instance(c["ref"], c["lib"], c["value"], c["at"], fp=c["fp"], props=props,
                            in_bom=c.get("bom", True))
        done = set()
        for num, name, ptype, px, py, ang, hidden in pins_of(sym):
            end, d = pin_point(c["at"], px, py, ang)
            net = c["nets"].get(num)
            if end in done:
                continue  # stacked pins share one connection point
            if net is None:
                if hidden or ptype == "no_connect":
                    continue
                # a visible stacked partner may carry the net
                partners = [n for n, *_ in pins_of(sym)
                            if pin_point(c["at"], *_[2:5])[0] == end and n in c["nets"]]
                if partners:
                    continue
                self.no_connect(end)
                done.add(end)
                continue
            done.add(end)
            tip = (r(end[0] + d[0] * STUB), r(end[1] + d[1] * STUB))
            self.wire(end, tip)
            if net in POWER_LIB:
                self.power(net, tip, d)
            else:
                self.label(net, tip, d)

    def render(self):
        tb = [Sym("title_block"), [Sym("title"), design.TITLE], [Sym("date"), design.DATE],
              [Sym("rev"), design.REVISION],
              [Sym("comment"), 1, "Generated by hardware/scripts/gen_schematic.py from design.py"],
              [Sym("comment"), 2, "Pinout contract: docs/pinout.md"]]
        root = [Sym("kicad_sch"), [Sym("version"), 20231120], [Sym("generator"), "eeschema"],
                [Sym("generator_version"), "8.0"], [Sym("uuid"), self.root],
                [Sym("paper"), "A3"], tb,
                [Sym("lib_symbols"), *[self.lib_symbols[k] for k in sorted(self.lib_symbols)]],
                *self.items,
                [Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]]]
        return dump(root) + "\n"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=next((p for p in DEFAULT_SYMBOLS if p and os.path.isdir(p)), None))
    ap.add_argument("--out", default=os.path.join(here, "..", f"{design.PROJECT}.kicad_sch"))
    args = ap.parse_args()
    if not args.symbols:
        sys.exit("KiCad 8 symbol library not found; pass --symbols or set KICAD8_SYMBOL_DIR")
    sheet = Sheet(Libs(args.symbols))
    for c in design.COMPONENTS:
        sheet.component(c)
    for net, at in design.PWR_FLAGS:
        sheet.pwr_flag(net, at)
    for at, s in design.NOTES:
        sheet.text(at, s)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(sheet.render())
    print(f"wrote {os.path.normpath(args.out)}")


if __name__ == "__main__":
    main()
