"""Write the light-input amplifier as an OrCAD PSpice netlist, then check that file in ngspice.

OrCAD PSpice reads a SPICE-style netlist: a title line, circuit cards, analysis
cards and .END. This module takes the same circuit that spice.py simulates,
writes it in that form for OrCAD, and runs the written file itself. Each
analysis is run as its own deck, because ngspice does not run several analyses
in one batch file reliably. The circuit text is the same in every deck.

Run from the repository root:

    python3 -m hardware.simulation.orcad --out hardware/simulation/build/orcad
"""
import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMATIC = HERE / "light-front-end.kicad_sch"
TITLE = "Desk photodiode current amplifier, OrCAD PSpice netlist"
NETLIST_NAME = "light-front-end.cir"

SCALE = {"": 1.0, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "G": 1e9}

# Analysis cards and the print card that follows each one. Each analysis is
# checked alone, so each card group is a separate deck.
ANALYSES = {
    "dc": (".DC Iphoto 0 10u 0.1u", ".PRINT DC V(out)"),
    "ac": (".AC DEC 40 10 1MEG", ".PRINT AC VM(out)"),
    "tran": (".TRAN 1u 5m", ".PRINT TRAN V(out)"),
}

ROW = re.compile(r"^\s*(\d+)\s+(\S+)\s+(\S+)\s*$")


def _physical(value, unit):
    match = re.fullmatch(r"([0-9.]+)([pnumkMG]?)(?:" + re.escape(unit) + r")?", value)
    if not match:
        raise ValueError("unsupported component value " + repr(value))
    return float(match[1]) * SCALE[match[2]]


def kicad_values(netlist_xml):
    """Return (feedback resistor in ohms, feedback capacitor in farads) from a KiCad netlist.

    The check fails if R3 and C3 are not wired across the amplifier output, its
    inverting input and the photodiode node. A wrong drawing would otherwise give
    a netlist that simulates a different circuit.
    """
    tree = ET.parse(netlist_xml)
    values = {c.attrib["ref"]: c.findtext("value") for c in tree.findall("./components/comp")}
    nets = {}
    for net in tree.findall("./nets/net"):
        for node in net.findall("node"):
            nets[(node.attrib["ref"], node.attrib["pin"])] = net.attrib["name"]
    out_side = [nets.get(k) for k in (("R3", "1"), ("U2", "1"), ("C3", "1"))]
    sum_side = [nets.get(k) for k in (("R3", "2"), ("U2", "4"), ("D1", "1"))]
    wired = (
        None not in out_side + sum_side
        and len(set(out_side)) == 1
        and len(set(sum_side)) == 1
    )
    if not wired:
        raise ValueError("R3 and C3 are not wired across U2 pins 1 and 4 and D1")
    return _physical(values["R3"], "ohm"), _physical(values["C3"], "F")


def export_kicad_netlist(out_xml):
    """Ask KiCad's command-line tool for the drawing's netlist, as spice.py does."""
    subprocess.run(
        ["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml", "-o", str(out_xml), str(SCHEMATIC)],
        check=True,
        capture_output=True,
    )


def circuit(rf, cf):
    """The circuit cards, with the feedback values written as plain numbers."""
    return f"""{TITLE}
Vinput vin 0 SIN(5 .05 1000)
Ereg vcc 0 VALUE {{3.3+(V(vin)-5)*.001}}
Rtop vcc ref 100k
Rbottom ref 0 100k
Cref ref 0 1n
Iphoto sum 0 DC 1u AC 1 PULSE(0 1u 100u 1n 1n 1m 2m)
Rfeedback out sum {rf:.6e}
Cfeedback out sum {cf:.6e}
Cdiode sum 0 70p
Eerror drive 0 ref sum 100000
Rdominant drive pole 1k
Cdominant pole 0 15.915494u
Eoutput out 0 VALUE {{min(max(V(ref)+V(pole),.05),V(vcc)-.05)}}
"""


def netlist(rf, cf):
    """The full OrCAD netlist: circuit, then all three analyses, then .END."""
    cards = [card for pair in ANALYSES.values() for card in pair]
    return circuit(rf, cf) + "\n".join(cards) + "\n.END\n"


def deck_for(text, kind):
    """The same netlist with only one analysis and its print card left in."""
    keep = {card for card in ANALYSES[kind]}
    other = {card for name, pair in ANALYSES.items() if name != kind for card in pair}
    lines = [line for line in text.splitlines() if line not in other]
    assert all(card in lines for card in keep), "analysis card missing from netlist"
    return "\n".join(lines) + "\n"


def parse_rows(stdout):
    """Numeric rows from one ngspice .PRINT table as (index, x, value) tuples."""
    rows = []
    for line in stdout.splitlines():
        match = ROW.match(line)
        if match:
            rows.append((int(match[1]), float(match[2]), float(match[3])))
    return rows


def run_deck(path):
    result = subprocess.run(["ngspice", "-b", str(path)], capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    if result.returncode or "Error:" in output:
        raise RuntimeError(output[-1500:])
    return output


def measure(rf, cf, decks):
    """Run each analysis in ngspice and return the quantities the tests compare."""
    dc = parse_rows(run_deck(decks["dc"]))
    ac = parse_rows(run_deck(decks["ac"]))
    tr = parse_rows(run_deck(decks["tran"]))
    if not (dc and ac and tr):
        raise RuntimeError("ngspice printed no rows for an analysis")
    gain = (dc[-1][2] - dc[0][2]) / (dc[-1][1] - dc[0][1])
    low = ac[0][2]
    crossing = next((f for _, f, mag in ac if mag <= low / math.sqrt(2)), None)
    settled = min(tr, key=lambda row: abs(row[1] - 0.0009))
    return {
        "feedback_ohm": rf,
        "feedback_farad": cf,
        "gain_ohm": gain,
        "bandwidth_hz": crossing,
        "hand_bandwidth_hz": 1 / (2 * math.pi * rf * cf),
        "step_final_v": settled[2],
        "dc_points": len(dc),
        "ac_points": len(ac),
        "tran_points": len(tr),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="hardware/simulation/build/orcad")
    p.add_argument("--kicad-netlist", help="use an existing KiCad XML netlist instead of exporting one")
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if not shutil.which("ngspice"):
        raise SystemExit("ngspice is needed for the check")
    with tempfile.TemporaryDirectory(prefix="orcad-") as folder:
        xml = Path(a.kicad_netlist) if a.kicad_netlist else Path(folder) / "netlist.xml"
        if not a.kicad_netlist:
            export_kicad_netlist(xml)
        rf, cf = kicad_values(xml)
        text = netlist(rf, cf)
        (out / NETLIST_NAME).write_text(text)
        decks = {}
        for kind in ANALYSES:
            decks[kind] = Path(folder) / f"{kind}.cir"
            decks[kind].write_text(deck_for(text, kind))
        result = measure(rf, cf, decks)
    (out / "check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
