import math
import shutil
import subprocess
import pytest
from hardware.simulation import orcad

FEEDBACK_NETS = {
    "OUT": [("R3", "1"), ("U2", "1"), ("C3", "1")],
    "SUM": [("R3", "2"), ("U2", "4"), ("D1", "1")],
}


def write_netlist_xml(path, r3="100k", c3="100pF", wiring=FEEDBACK_NETS):
    nets = "".join(
        f'<net code="{i + 1}" name="{name}">'
        + "".join(f'<node ref="{ref}" pin="{pin}"/>' for ref, pin in nodes)
        + "</net>"
        for i, (name, nodes) in enumerate(wiring.items())
    )
    path.write_text(
        '<?xml version="1.0"?><export version="E"><components>'
        f'<comp ref="R3"><value>{r3}</value></comp>'
        f'<comp ref="C3"><value>{c3}</value></comp>'
        f"</components><nets>{nets}</nets></export>"
    )
    return path


def test_values_come_from_the_drawing(tmp_path):
    rf, cf = orcad.kicad_values(write_netlist_xml(tmp_path / "netlist.xml"))
    assert rf == pytest.approx(100000)
    assert cf == pytest.approx(100e-12)


def test_units_are_scaled(tmp_path):
    rf, cf = orcad.kicad_values(write_netlist_xml(tmp_path / "netlist.xml", r3="4.7M", c3="2.2nF"))
    assert rf == pytest.approx(4.7e6)
    assert cf == pytest.approx(2.2e-9)


def test_miswired_feedback_is_rejected(tmp_path):
    wiring = dict(FEEDBACK_NETS, SUM=[("R3", "2"), ("U2", "4")])  # D1 left off the summing node
    with pytest.raises(ValueError, match="not wired"):
        orcad.kicad_values(write_netlist_xml(tmp_path / "netlist.xml", wiring=wiring))


def test_netlist_is_pspice_shaped():
    text = orcad.netlist(100000, 100e-12)
    lines = text.splitlines()
    assert lines[0] == orcad.TITLE
    assert lines[-1] == ".END"
    assert "Rfeedback out sum 1.000000e+05" in text
    assert "Cfeedback out sum 1.000000e-10" in text
    for kind, (analysis, printed) in orcad.ANALYSES.items():
        assert analysis in lines and printed in lines, kind
    # ngspice-only control blocks and raw-data writers must not appear in an OrCAD file.
    assert ".control" not in text and "wrdata" not in text


def test_behavioral_sources_use_pspice_value_syntax():
    # PSpice does not accept ngspice's B-source form (B name n+ n- V=expr). Behavioral
    # sources must be E cards with VALUE {expr}, which both PSpice and ngspice read.
    cards = [line for line in orcad.netlist(100000, 100e-12).splitlines() if line and not line.startswith(".")]
    assert not [c for c in cards if c.startswith("B") or " V=" in c or " I=" in c]
    behavioral = [c for c in cards if c.startswith("E") and "VALUE" in c]
    assert {c.split()[0] for c in behavioral} == {"Ereg", "Eoutput"}
    for card in behavioral:
        parts = card.split(None, 3)
        assert len(parts) == 4 and parts[3].startswith("VALUE {") and parts[3].endswith("}"), card
        assert parts[3].count("(") == parts[3].count(")"), card


def test_element_cards_are_pspice_types():
    # Element cards allowed in the file: R, C, V, I and E (voltage-controlled sources).
    for line in orcad.netlist(100000, 100e-12).splitlines():
        if line and not line.startswith("."):
            if line == orcad.TITLE:
                continue
            assert line[0] in "RCVIE", line


def test_each_deck_keeps_one_analysis():
    text = orcad.netlist(100000, 100e-12)
    for kind, (analysis, printed) in orcad.ANALYSES.items():
        deck = orcad.deck_for(text, kind)
        assert analysis in deck and printed in deck
        for other, (other_analysis, other_printed) in orcad.ANALYSES.items():
            if other != kind:
                assert other_analysis not in deck and other_printed not in deck
        assert deck.splitlines()[-1] == ".END"


def test_parse_rows_reads_ngspice_table():
    stdout = "Index\ttime\tv(out)\n--------\n0\t0.000000e+00\t1.650000e+00\t\n1\t1.000000e-08\t1.650000e+00\n"
    assert orcad.parse_rows(stdout) == [(0, 0.0, 1.65), (1, 1e-8, 1.65)]


@pytest.mark.skipif(not shutil.which("ngspice"), reason="requires ngspice")
def test_written_netlist_reproduces_the_hand_numbers(tmp_path):
    xml = write_netlist_xml(tmp_path / "netlist.xml")
    out = tmp_path / "out"
    orcad.main(["--out", str(out), "--kicad-netlist", str(xml)])
    assert (out / orcad.NETLIST_NAME).read_text() == orcad.netlist(100000, 100e-12)
    rf, cf = 100000.0, 100e-12
    import json

    result = json.loads((out / "check.json").read_text())
    assert result["gain_ohm"] == pytest.approx(rf, rel=0.001)
    assert result["bandwidth_hz"] == pytest.approx(1 / (2 * math.pi * rf * cf), rel=0.12)
    assert result["step_final_v"] == pytest.approx(1.65 + 1e-6 * rf, abs=0.001)
    assert result["dc_points"] == 101


@pytest.mark.skipif(not shutil.which("kicad-cli"), reason="requires kicad-cli")
def test_drawing_export_matches_spice_inputs(tmp_path):
    xml = tmp_path / "netlist.xml"
    orcad.export_kicad_netlist(xml)
    rf, cf = orcad.kicad_values(xml)
    assert rf == pytest.approx(100000)
    assert cf == pytest.approx(100e-12)
