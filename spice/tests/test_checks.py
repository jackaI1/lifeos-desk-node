"""Checks that the ngspice netlists still agree with the hand calculations.

The tests that need ngspice are skipped when it is not installed. CI installs it,
so a drift in a netlist or in the schematic fails there.
"""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from spice import checks

FIXTURE = Path(__file__).parent / "fixtures" / "desk-node-netlist.xml"
needs_ngspice = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice not installed")


def _root(text: str = None) -> ET.Element:
    if text is None:
        return ET.parse(FIXTURE).getroot()
    return ET.fromstring(text)


def test_parse_value_handles_schematic_strings():
    assert checks.parse_value("10uF 25V", "F") == pytest.approx(10e-6)
    assert checks.parse_value("100nF", "F") == pytest.approx(100e-9)
    assert checks.parse_value("22uF 16V", "F") == pytest.approx(22e-6)
    assert checks.parse_value("4.7k", "ohm") == pytest.approx(4700.0)
    assert checks.parse_value("5.1k", "ohm") == pytest.approx(5100.0)
    with pytest.raises(checks.SpiceError):
        checks.parse_value("USB-C power", "ohm")


def test_schematic_values_come_from_the_fixture_netlist():
    values = checks.read_schematic(_root())
    assert values.c_in == pytest.approx(10e-6)
    # C2, C3 (22 uF each), C7 (10 uF), C4, C6, C8 (100 nF each) sit on +3V3.
    assert values.c_out == pytest.approx(2 * 22e-6 + 10e-6 + 3 * 100e-9)
    assert values.r_pullup_sda == pytest.approx(4700.0)
    assert values.r_pullup_scl == pytest.approx(4700.0)


def test_wiring_change_is_refused():
    # Move R6's pin 1 from +3V3 to GND: the checker must stop rather than simulate it.
    root = _root()
    nets = {n.attrib["name"]: n for n in root.findall("./nets/net")}
    moved = next(node for node in nets["+3V3"].findall("node") if node.attrib["ref"] == "R6")
    nets["+3V3"].remove(moved)
    nets["GND"].append(moved)
    with pytest.raises(checks.SpiceError, match="R6"):
        checks.read_schematic(root)


def test_pullup_change_in_the_schematic_is_visible():
    # A 10 kohm SDA pull-up is outside the 967 to 7081 ohm window at 400 kHz.
    text = FIXTURE.read_text(encoding="utf-8")
    values = checks.read_schematic(_root(text))
    assert values.r_pullup_sda < checks.hand.max_pullup_for_rise(300e-9, 50e-12)


def test_i2c_template_fills_every_token():
    deck = checks.fill_i2c_netlist(4700.0, 50e-12, 2.5e-6)
    assert "@" not in deck
    assert "meas tran t_rise" in deck
    assert "Rpu vdd sda 4700" in deck


def test_power_template_needs_each_param_line_once():
    with pytest.raises(checks.SpiceError):
        checks.fill_power_netlist(checks.SchematicValues(10e-6, 54.3e-6, 4700, 4700),
                                  template="* no parameters here\n")


def test_sensitivity_flags_a_bigger_bus_load():
    values = checks.read_schematic(_root())
    rows = dict((round(pf), margin) for pf, _, margin in checks.pullup_sensitivity(values))
    assert rows[50] > 1.0       # 4.7 kohm meets 300 ns on a 50 pF bus
    assert rows[100] < 1.0      # and does not on a 100 pF bus


@needs_ngspice
def test_simulated_results_match_the_hand_calculations(tmp_path):
    values = checks.read_schematic(_root())
    results, _ = checks.power_checks(values, tmp_path)
    i2c, _ = checks.i2c_checks(values, tmp_path)
    failed = [c for c in results + i2c if not c.passed]
    assert not failed, [(c.name, c.measured, c.expected, c.agreement) for c in failed]


@needs_ngspice
def test_load_step_drift_is_caught(tmp_path):
    # Halve the load step in the deck but keep the hand value at 600 mA: the droop must fail.
    template = checks.POWER_NETLIST.read_text(encoding="utf-8")
    drifted = template.replace("Istep vout 0 PWL(0 0 10m 0 10.001m 0.6 15m 0.6 15.001m 0)",
                               "Istep vout 0 PWL(0 0 10m 0 10.001m 0.3 15m 0.3 15.001m 0)")
    assert drifted != template
    values = checks.read_schematic(_root())
    deck = tmp_path / "drifted.cir"
    deck.write_text(checks.fill_power_netlist(values, template=drifted), encoding="utf-8")
    measured = checks.run_ngspice(deck)
    droop = measured["v_before_step"] - measured["v_after_step"]
    assert droop == pytest.approx(0.03, rel=0.02)   # the drifted deck really does draw 300 mA
    expected = checks.hand.load_step_droop(checks.ASSUMED["I_STEP"], checks.ASSUMED["R_OUT"])
    assert abs(droop - expected) / expected > checks.AGREE_TOLERANCE["droop"]


@needs_ngspice
def test_pullup_drift_is_caught(tmp_path):
    # A 10 kohm pull-up on the I2C template is slower than the 300 ns limit at 400 kHz.
    deck = tmp_path / "slow.cir"
    deck.write_text(checks.fill_i2c_netlist(10000.0, 50e-12, 2.5e-6), encoding="utf-8")
    measured = checks.run_ngspice(deck)["t_rise"]
    assert measured > checks.LIMITS["rise_fm_max_s"]
