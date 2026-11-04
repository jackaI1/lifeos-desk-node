#!/usr/bin/env python3
"""Write hardware/desk-node.kicad_pro: JLCPCB 2-layer design rules + net classes.

KiCad fills any keys not given here with its defaults when the project opens.
Rules follow JLCPCB's standard 2-layer capabilities with margin:
0.15 mm min track/space, 0.3 mm via drill / 0.6 mm via pad, 0.3 mm copper-to-edge.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design  # noqa: E402


def netclass(name, track, clearance=0.2, via=0.6, drill=0.3, priority=2147483647):
    return {
        "name": name, "clearance": clearance, "track_width": track,
        "via_diameter": via, "via_drill": drill,
        "microvia_diameter": 0.3, "microvia_drill": 0.1,
        "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
        "wire_width": 6, "bus_width": 12, "line_style": 0,
        "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
        "priority": priority,
    }


PROJECT = {
    "board": {
        "design_settings": {
            "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2,
                         "silk_line_width": 0.12, "silk_text_size_h": 0.8,
                         "silk_text_size_v": 0.8, "silk_text_thickness": 0.12},
            "rules": {
                "min_clearance": 0.15, "min_track_width": 0.15,
                "min_via_diameter": 0.5, "min_via_annular_width": 0.13,
                "min_through_hole_diameter": 0.3, "min_hole_to_hole": 0.25,
                "min_hole_clearance": 0.25, "min_copper_edge_clearance": 0.3,
                "min_connection": 0.0, "min_silk_clearance": 0.0,
                "min_text_height": 0.6, "min_text_thickness": 0.08,
                "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1,
                "solder_mask_to_copper_clearance": 0.0,
                "use_height_for_length_calcs": True,
            },
            "track_widths": [0.0, 0.25, 0.4, 0.6, 0.8],
            "via_dimensions": [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.6, "drill": 0.3}],
        },
    },
    "meta": {"filename": f"{design.PROJECT}.kicad_pro", "version": 1},
    "net_settings": {
        "classes": [
            netclass("Default", 0.25),
            netclass("Power", 0.5, priority=0),    # USB VBUS / +5V into the LDO
            netclass("Supply", 0.3, priority=1),   # +3V3: fits the SHT31's 0.5 mm pitch
        ],
        "meta": {"version": 3},
        "netclass_patterns": [{"netclass": "Power", "pattern": design.VBUS},
                              {"netclass": "Power", "pattern": design.V5},
                              {"netclass": "Supply", "pattern": design.V3}],
    },
    "schematic": {"meta": {"version": 1}},
    "text_variables": {},
}


def lib_tables(hw):
    """Project library tables naming only the stock KiCad 8 libraries the design uses,
    so ERC/DRC library checks work on a fresh install or in CI."""
    syms = sorted({c["lib"].split(":")[0] for c in design.COMPONENTS} | {"power"})
    fps = sorted({c["fp"].split(":")[0] for c in design.COMPONENTS})
    with open(os.path.join(hw, "sym-lib-table"), "w", encoding="utf-8") as f:
        f.write("(sym_lib_table\n  (version 7)\n")
        for n in syms:
            f.write(f'  (lib (name "{n}")(type "KiCad")(uri "${{KICAD8_SYMBOL_DIR}}/{n}.kicad_sym")'
                    '(options "")(descr ""))\n')
        f.write(")\n")
    with open(os.path.join(hw, "fp-lib-table"), "w", encoding="utf-8") as f:
        f.write("(fp_lib_table\n  (version 7)\n")
        for n in fps:
            if n == "DeskNode":
                f.write('  (lib (name "DeskNode")(type "KiCad")(uri "${KIPRJMOD}/DeskNode.pretty")(options "")(descr "KiCad 8 module with 0.3 mm thermal drills"))\n')
                continue
            f.write(f'  (lib (name "{n}")(type "KiCad")(uri "${{KICAD8_FOOTPRINT_DIR}}/{n}.pretty")'
                    '(options "")(descr ""))\n')
        f.write(")\n")


def main():
    hw = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    out = os.path.join(hw, f"{design.PROJECT}.kicad_pro")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(PROJECT, f, indent=2)
        f.write("\n")
    lib_tables(hw)
    print(f"wrote {out} + project library tables")


if __name__ == "__main__":
    main()
