"""Ensure the battery contract detects unsafe edits, using a real KiCad netlist."""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest

ROOT=Path(__file__).resolve().parents[3]
SPEC=importlib.util.spec_from_file_location('battery_contract',ROOT/'hardware/revb/scripts/check_contract.py')
contract=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(contract)
NETLIST=Path(__file__).with_name('expected-netlist.xml')
BOARD=ROOT/'hardware/revb/desk-node-b.kicad_pcb'


def test_real_netlist_and_actual_outline():
    contract.check(NETLIST,BOARD)


def test_bad_charge_jumper_is_rejected(tmp_path):
    tree=ET.parse(NETLIST)
    for node in tree.findall('./nets/net/node'):
        if node.attrib=={'ref':'JP1','pin':'1','pinfunction':'Pin_1','pintype':'passive'}:
            node.set('pin','3')
    file=tmp_path/'shorted.xml';tree.write(file)
    with pytest.raises(ValueError,match='JP1'):
        contract.check(file,BOARD)


def test_grown_board_is_rejected(tmp_path):
    file=tmp_path/'too-large.kicad_pcb'
    # Change one actual edge endpoint; component and trace coordinates stay intact.
    text=BOARD.read_text()
    start=text.index('(gr_line')
    end=text.index('(segment',start)
    region=text[start:end].replace('148 ', '150 ')
    file.write_text(text[:start]+region+text[end:])
    with pytest.raises(ValueError,match='48x54'):
        contract.check(NETLIST,file)
