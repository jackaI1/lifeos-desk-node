"""Run the desk node's ngspice netlists and compare them with hand calculations.

Steps:

1. Read the part values and nets from the Rev A schematic. The KiCad CLI writes
   a netlist, and this script reads the capacitors on +5V and +3V3, the SDA and
   SCL pull-ups, and checks which nets each part is on.
2. Fill the ASSUMED constants and the schematic values into the two netlists in
   this folder. Each run writes a copy of the filled netlist to spice/build/decks/.
3. Run ngspice headless (ngspice -b) and read the .meas and print results.
4. Compare each result with its hand calculation (spice/hand.py) within a stated
   tolerance, and with the design limit where one exists.

Exit status: 0 when every check passes, 1 when a check fails, 2 when the
checks cannot run (no ngspice, no KiCad CLI, or a netlist error).

    python3 -m spice.checks                      # write spice/build/
    python3 -m spice.checks --out /tmp/spice     # other output folder
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from spice import hand

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SCHEMATIC = ROOT / "hardware" / "desk-node.kicad_sch"
DEFAULT_OUT = HERE / "build"
POWER_NETLIST = HERE / "usb_5v_regulator.cir"
I2C_TEMPLATE = HERE / "i2c_pullup.cir"

# Tolerance between simulation and hand calculation, as a fraction of the hand value.
AGREE_TOLERANCE = {
    "inrush": 0.05,
    "input_drop": 0.01,
    "v_before": 0.002,
    "droop": 0.05,
    "ripple": 0.10,
    "rise": 0.05,
}

# Assumed values that are not on the schematic (see the netlist comments).
ASSUMED = {
    "R_CABLE": 0.1,      # ohm, USB cable and host path
    "R_FUSE": 0.2,       # ohm, resettable fuse on-resistance
    "R_OUT": 0.1,        # ohm, LDO output resistance
    "I_Q": 0.005,        # A, LDO quiescent current
    "I_IDLE": 0.010,     # A, idle load
    "I_BURST": 0.250,    # A, Wi-Fi burst load (250 mA is the design's running current)
    "I_STEP": 0.600,     # A, load step in the netlist's PWL source (fixed in the file)
    "C_BUS": 50e-12,     # F, I2C bus capacitance (pin, traces, J2 header)
    "R_DRIVE": 20.0,     # ohm, ESP32 open-drain on-resistance (fixed in the file)
}

# Design limits. Each one cites the rule it comes from.
LIMITS = {
    "vbus_min_v": 4.75,              # USB 2.0 minimum VBUS at the device
    "ldo_out_min_fraction": 0.95,    # 3V3 rail within -5 % while loaded
    "ripple_max_v": 0.030,           # bench limit for 3V3 ripple (bench/limits.toml)
    "rise_sm_max_s": 1.0e-6,         # I2C standard mode, 30 %-70 %
    "rise_fm_max_s": 300e-9,         # I2C fast mode, 30 %-70 %
    "sink_vol_v": 0.4,               # I2C fast mode VOL at the sink current
    "sink_current_a": 0.003,         # I2C fast mode minimum sink current
}

I2C_VDD = 3.3
I2C_LEVEL_LO = 0.3 * I2C_VDD
I2C_LEVEL_HI = 0.7 * I2C_VDD
USB_SOURCE_V = 5.0
USB_RISE_S = 1e-6                   # the netlist's 1 us VBUS ramp
LDO_NOMINAL_V = 3.3
PULLUP_CHECK_CAP = (50e-12, 100e-12)  # bus capacitances for the pull-up sensitivity


class SpiceError(RuntimeError):
    """ngspice or the KiCad CLI could not produce results."""


@dataclass
class Check:
    name: str
    measured: float
    expected: float
    unit: str
    agreement: float          # fraction of the hand value (sim - hand) / hand
    tolerance: float          # allowed |agreement|; 0 means no hand-value check
    limit_low: Optional[float]
    limit_high: Optional[float]
    passed: bool
    meaning: str


# ---------------------------------------------------------------- schematic values

_UNITS = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "M": 1e6}


def parse_value(text: str, unit: str) -> float:
    """Parse '10uF 25V', '100nF', '4.7k' or '5.1k' into SI units."""
    match = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([pnumkM]?)(?:" + unit + r")?(?=\s|$)", text)
    if not match:
        raise SpiceError(f"unsupported {unit} value {text!r}")
    return float(match.group(1)) * _UNITS[match.group(2)]


def export_netlist(schematic: Path = SCHEMATIC, out: Optional[Path] = None) -> ET.Element:
    """Export the schematic's KiCad XML netlist with kicad-cli and return its root."""
    cli = os.environ.get("KICAD_CLI", "kicad-cli")
    if shutil.which(cli) is None:
        raise SpiceError(f"{cli} not found; install KiCad 8 or set KICAD_CLI")
    with tempfile.TemporaryDirectory(prefix="desk-spice-") as folder:
        path = Path(folder) / "netlist.xml"
        proc = subprocess.run([cli, "sch", "export", "netlist", "--format", "kicadxml",
                               "-o", str(path), str(schematic)],
                              capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise SpiceError(f"kicad-cli failed: {proc.stderr.strip()[-300:]}")
        tree = ET.parse(path)
        if out is not None:
            shutil.copyfile(path, out)
    return tree.getroot()


@dataclass(frozen=True)
class SchematicValues:
    c_in: float          # C1 on +5V, farad
    c_out: float         # all capacitors on +3V3 to GND, farad
    r_pullup_sda: float  # R6, ohm
    r_pullup_scl: float  # R7, ohm


def read_schematic(root: ET.Element) -> SchematicValues:
    """Read the values and check the nets the simulations assume."""
    parts = {c.attrib["ref"]: c.findtext("value") or "" for c in root.findall("./components/comp")}
    nets: Dict[Tuple[str, str], str] = {}
    for net in root.findall("./nets/net"):
        for node in net.findall("node"):
            nets[(node.attrib["ref"], node.attrib["pin"])] = net.attrib["name"]

    def on_net(ref: str, pin: str) -> str:
        return nets.get((ref, pin), "")

    # Assumptions that depend on the wiring: C1 must sit on +5V, the output
    # caps on +3V3, and the pull-ups between +3V3 and the I2C lines.
    if on_net("C1", "1") != "+5V" or on_net("C1", "2") != "GND":
        raise SpiceError("C1 is no longer across +5V and GND; update spice/usb_5v_regulator.cir")
    if on_net("U2", "3") != "+5V" or on_net("U2", "2") != "+3V3":
        raise SpiceError("U2 is no longer +5V in and +3V3 out; update the regulator netlist")
    if (on_net("R6", "1"), on_net("R6", "2")) not in {("+3V3", "/I2C_SDA"), ("/I2C_SDA", "+3V3")}:
        raise SpiceError("R6 is no longer the SDA pull-up")
    if (on_net("R7", "1"), on_net("R7", "2")) not in {("+3V3", "/I2C_SCL"), ("/I2C_SCL", "+3V3")}:
        raise SpiceError("R7 is no longer the SCL pull-up")

    c_out = 0.0
    for ref, value in parts.items():
        if not ref.startswith("C"):
            continue
        pins = {on_net(ref, "1"), on_net(ref, "2")}
        if pins == {"+3V3", "GND"}:
            c_out += parse_value(value, "F")
    c_in = parse_value(parts["C1"], "F")
    return SchematicValues(
        c_in=c_in,
        c_out=c_out,
        r_pullup_sda=parse_value(parts["R6"], "ohm"),
        r_pullup_scl=parse_value(parts["R7"], "ohm"),
    )


# ---------------------------------------------------------------- netlists

def fill_power_netlist(values: SchematicValues, template: str = None) -> str:
    text = (template if template is not None else POWER_NETLIST.read_text(encoding="utf-8"))
    replacements = {
        "R_CABLE": ASSUMED["R_CABLE"],
        "R_FUSE": ASSUMED["R_FUSE"],
        "C_IN": values.c_in,
        "C_OUT": values.c_out,
        "R_OUT": ASSUMED["R_OUT"],
        "I_Q": ASSUMED["I_Q"],
        "I_IDLE": ASSUMED["I_IDLE"],
        "I_BURST": ASSUMED["I_BURST"],
    }
    for name, value in replacements.items():
        text, count = re.subn(rf"^\.param {name}=\S+", f".param {name}={value:.6g}", text,
                              flags=re.MULTILINE)
        if count != 1:
            raise SpiceError(f"expected one .param {name} line in the regulator netlist")
    return text


def fill_i2c_netlist(r_pullup: float, c_bus: float, bit_period_s: float, template: str = None) -> str:
    """Fill the I2C template for one pull-up and bus capacitance at one bus speed."""
    text = template if template is not None else I2C_TEMPLATE.read_text(encoding="utf-8")
    t_low = bit_period_s / 2.0
    tokens = {
        "R_PULLUP": f"{r_pullup:.6g}",
        "C_BUS": f"{c_bus:.6g}",
        "T_LOW": f"{t_low:.6g}",
        "T_PERIOD": f"{bit_period_s:.6g}",
        "T_LOW_MINUS_1U": f"{t_low - 1e-6:.6g}",
        "T_TWO_PERIODS": f"{2 * bit_period_s:.6g}",
        "LEVEL_LO": f"{I2C_LEVEL_LO:.6g}",
        "LEVEL_HI": f"{I2C_LEVEL_HI:.6g}",
    }
    for name, value in tokens.items():
        text = text.replace(f"@{name}@", value)
    if re.search(r"@[A-Z][A-Z_0-9]*@", text):
        raise SpiceError("unfilled token in the I2C netlist")
    return text


# ---------------------------------------------------------------- ngspice

_RESULT = re.compile(r"^([A-Za-z_][\w]*)\s*=\s*([-+]?[0-9.]+(?:[eE][-+]?\d+)?)\s*$", re.MULTILINE)


def run_ngspice(deck: Path, timeout_s: int = 120) -> Dict[str, float]:
    """Run one netlist headless and return its printed results by name."""
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        raise SpiceError("ngspice not found; install it (brew install ngspice, apt-get install ngspice)")
    try:
        proc = subprocess.run([ngspice, "-b", str(deck)], capture_output=True, text=True,
                              timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired as exc:
        raise SpiceError(f"ngspice timed out on {deck.name} after {timeout_s} s") from exc
    output = proc.stdout + proc.stderr
    if proc.returncode != 0 or re.search(r"^(Error|fatal)", output, re.MULTILINE | re.IGNORECASE):
        problems = [line for line in output.splitlines() if re.search(r"error|fatal", line, re.I)]
        raise SpiceError(f"ngspice failed on {deck.name}: {' | '.join(problems[:3])}")
    results = {name: float(value) for name, value in _RESULT.findall(output)}
    # Each meas line also prints the result, so the numbers are read from the print lines.
    return results


# ---------------------------------------------------------------- the checks

def _check(name, measured, expected, unit, tolerance, low, high, meaning) -> Check:
    """tolerance 0 means no hand value to compare; only the limits apply."""
    agreement = 0.0
    if tolerance:
        agreement = (measured - expected) / expected
    agrees = tolerance == 0 or abs(agreement) <= tolerance
    within = (low is None or measured >= low) and (high is None or measured <= high)
    return Check(name, measured, expected if tolerance else float('nan'), unit, agreement,
                 tolerance, low, high, agrees and within, meaning)


def power_checks(values: SchematicValues, deck_dir: Path) -> Tuple[List[Check], Path]:
    deck = deck_dir / "usb_5v_regulator.cir"
    deck.write_text(fill_power_netlist(values), encoding="utf-8")
    r = run_ngspice(deck)
    series_r = ASSUMED["R_CABLE"] + ASSUMED["R_FUSE"]
    i_out = ASSUMED["I_IDLE"] + ASSUMED["I_STEP"]
    checks = [
        _check("inrush_peak_a", r["i_inrush_peak"],
               hand.inrush_peak_ramp(USB_SOURCE_V, series_r, values.c_in, USB_RISE_S),
               "A", AGREE_TOLERANCE["inrush"], None, None,
               "Peak charging current of C1 at plug-in. Set by the assumed 0.3 ohm path; "
               "informational, not a pass/fail limit."),
        _check("input_drop_under_load_v", r["vin_under_step"],
               hand.input_voltage_under_load(USB_SOURCE_V, i_out + ASSUMED["I_Q"], series_r),
               "V", AGREE_TOLERANCE["input_drop"], LIMITS["vbus_min_v"], None,
               "+5V at the regulator with 615 mA drawn: the cable and fuse drop it."),
        _check("v3v3_before_step_v", r["v_before_step"],
               LDO_NOMINAL_V - ASSUMED["I_IDLE"] * ASSUMED["R_OUT"],
               "V", AGREE_TOLERANCE["v_before"], None, None,
               "3V3 rail at idle current."),
        _check("v3v3_droop_v", r["v_before_step"] - r["v_after_step"],
               hand.load_step_droop(ASSUMED["I_STEP"], ASSUMED["R_OUT"]),
               "V", AGREE_TOLERANCE["droop"],
               None, None,
               "3V3 droop for the 600 mA step (I R, held after the RC settles)."),
        _check("v3v3_loaded_min_v", r["v_after_step"], None,
               "V", 0.0, LIMITS["ldo_out_min_fraction"] * LDO_NOMINAL_V, None,
               "3V3 rail while loaded must stay within -5 % of nominal."),
        _check("v3v3_ripple_pp_v", r["v_ripple_max"] - r["v_ripple_min"],
               hand.burst_ripple_pp(ASSUMED["I_BURST"], ASSUMED["R_OUT"], values.c_out, 0.2e-3),
               "V", AGREE_TOLERANCE["ripple"], None, LIMITS["ripple_max_v"],
               "Peak-to-peak 3V3 ripple from a 250 mA, 0.2 ms burst each millisecond."),
    ]
    return checks, deck


def i2c_checks(values: SchematicValues, deck_dir: Path) -> Tuple[List[Check], List[Path]]:
    checks: List[Check] = []
    decks: List[Path] = []
    r_pu = values.r_pullup_sda
    sda_limits = {"100 kHz": (10e-6, "rise_sm_max_s"), "400 kHz": (2.5e-6, "rise_fm_max_s")}
    for label, (period, limit_key) in sda_limits.items():
        tag = label.replace(" ", "").replace("kHz", "k")
        deck = deck_dir / f"i2c_pullup_{tag}.cir"
        deck.write_text(fill_i2c_netlist(r_pu, ASSUMED["C_BUS"], period), encoding="utf-8")
        decks.append(deck)
        measured = run_ngspice(deck)["t_rise"]
        checks.append(_check(
            f"sda_rise_{tag}_s", measured,
            hand.rise_time_30_70(r_pu, ASSUMED["C_BUS"]), "s", AGREE_TOLERANCE["rise"],
            None, LIMITS[limit_key],
            f"SDA 30 %-70 % rise at {label} with {r_pu / 1000:g} kohm and "
            f"{ASSUMED['C_BUS'] * 1e12:g} pF bus capacitance."))

    # Pull-up window: the driver must hold VOL, and the 400 kHz rise must meet its limit.
    r_min = hand.min_pullup_for_sink(I2C_VDD, LIMITS["sink_vol_v"], LIMITS["sink_current_a"])
    r_max = hand.max_pullup_for_rise(LIMITS["rise_fm_max_s"], ASSUMED["C_BUS"])
    checks.append(_check(
        "pullup_sda_ohm", r_pu, (r_min + r_max) / 2.0, "ohm", 0.0, r_min, r_max,
        f"Pull-up must lie between {r_min:.0f} ohm (sink limit) and {r_max:.0f} ohm "
        f"(400 kHz rise limit at {ASSUMED['C_BUS'] * 1e12:g} pF)."))
    checks.append(_check(
        "pullup_scl_ohm", values.r_pullup_scl, (r_min + r_max) / 2.0, "ohm", 0.0, r_min, r_max,
        "SCL pull-up window, same rules as SDA."))
    return checks, decks


def pullup_sensitivity(values: SchematicValues) -> List[Tuple[float, float, float]]:
    """Largest 400 kHz pull-up for each bus capacitance. Rows: (pF, R_max ohm, margin)."""
    rows = []
    for c in PULLUP_CHECK_CAP:
        r_max = hand.max_pullup_for_rise(LIMITS["rise_fm_max_s"], c)
        rows.append((c * 1e12, r_max, r_max / values.r_pullup_sda))
    return rows


def run_all(out: Path) -> Tuple[List[Check], Dict[str, object]]:
    out.mkdir(parents=True, exist_ok=True)
    decks_dir = out / "decks"
    decks_dir.mkdir(exist_ok=True)
    root = export_netlist(SCHEMATIC, out / "netlist.xml")
    values = read_schematic(root)
    p_checks, _ = power_checks(values, decks_dir)
    i_checks, _ = i2c_checks(values, decks_dir)
    checks = p_checks + i_checks
    info = {
        "schematic": str(SCHEMATIC.relative_to(ROOT)),
        "c_in_f": values.c_in,
        "c_out_f": values.c_out,
        "r_pullup_sda_ohm": values.r_pullup_sda,
        "r_pullup_scl_ohm": values.r_pullup_scl,
        "assumed": ASSUMED,
        "sensitivity": pullup_sensitivity(values),
    }
    return checks, info


def write_report(out: Path, checks: List[Check], info: Dict[str, object]) -> Path:
    verdict = "PASS" if all(c.passed for c in checks) else "FAIL"
    lines = [
        f"# SPICE checks: {verdict}",
        "",
        "Simulated with ngspice in batch mode. Each result is compared with a hand calculation",
        "(`spice/hand.py`) within a stated tolerance, and with a design limit where one exists.",
        "",
        f"- Schematic: `{info['schematic']}` (KiCad netlist export)",
        f"- C1 (+5V): {info['c_in_f'] * 1e6:.1f} uF; output capacitance on +3V3: "
        f"{info['c_out_f'] * 1e6:.1f} uF",
        f"- SDA pull-up R6: {info['r_pullup_sda_ohm'] / 1000:g} kohm; SCL pull-up R7: "
        f"{info['r_pullup_scl_ohm'] / 1000:g} kohm",
        "- Assumed values (not on the schematic): " + ", ".join(
            f"{k} = {v:g}" for k, v in info["assumed"].items()),
        "",
        "| check | simulated | hand | diff | tolerance | limit | result | meaning |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in checks:
        limit = []
        if c.limit_low is not None:
            limit.append(f">= {c.limit_low:.4g}")
        if c.limit_high is not None:
            limit.append(f"<= {c.limit_high:.4g}")
        tol = f"{c.tolerance * 100:.1f} %" if c.tolerance else "-"
        hand_text = f"{c.expected:.4g} {c.unit}" if c.tolerance else "-"
        diff = f"{c.agreement * 100:+.2f} %" if c.tolerance else "-"
        lines.append(f"| {c.name} | {c.measured:.4g} {c.unit} | {hand_text} | {diff} | {tol} | "
                     f"{' and '.join(limit) or 'none'} | {'PASS' if c.passed else 'FAIL'} | "
                     f"{c.meaning} |")
    lines += ["", "## Pull-up sensitivity (400 kHz)", "",
              "| bus capacitance | largest pull-up for 300 ns | margin for R6 |",
              "| --- | --- | --- |"]
    for pf, r_max, margin in info["sensitivity"]:
        lines.append(f"| {pf:g} pF | {r_max / 1000:.2f} kohm | {margin:.2f} x |")
    lines += ["", "The decks that ran are in `decks/`, and the KiCad netlist used is `netlist.xml`.", ""]
    path = out / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the desk node SPICE checks.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output folder (default spice/build)")
    args = parser.parse_args(argv)
    out = Path(args.out)
    try:
        checks, info = run_all(out)
    except (SpiceError, ET.ParseError, KeyError) as exc:
        print(f"spice error: {exc}", file=sys.stderr)
        return 2
    report = write_report(out, checks, info)
    (out / "results.json").write_text(json.dumps([asdict(c) for c in checks], indent=2), encoding="utf-8")
    for c in checks:
        print(f"  {c.name:<28} {c.measured:>12.5g} {c.unit:<4} {'PASS' if c.passed else 'FAIL'}")
    passed = all(c.passed for c in checks)
    print(f"result: {'PASS' if passed else 'FAIL'}; report: {report}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
