"""Independent fixed signal/power contract and actual board-size checks."""
from pathlib import Path
import importlib.util
import sys
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0,str(BASE))
from sexpr import parse, find, find1
spec = importlib.util.spec_from_file_location('rev_a_contract',BASE/'check_contract.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)


def check(netlist, pcb):
    a.check(netlist, {
        'U2': {'1':'/SYS','2':'GND','3':'/SYS','5':'+3V3'},
        'U4': {'2':'GND','3':'/CHARGE_BAT','4':'+5V','5':'/PROG'},
        'JP1': {'1':'/SYS','2':'/BAT_PLUS','3':'/CHARGE_BAT'},
        'J5': {'1':'/BAT_PLUS','2':'GND'},
        'R12': {'1':'/PROG','2':'GND'},
        'C9': {'1':'/CHARGE_BAT','2':'GND'},
        'C10': {'1':'/SYS','2':'GND'},
    })
    tree=ET.parse(netlist)
    refs={c.attrib['ref'] for c in tree.findall('./components/comp')}
    if refs & {'R8','D2'}:
        raise ValueError('always-on LED must be absent in Rev B')
    pins={(node.attrib['ref'],node.attrib['pin']):net.attrib['name'] for net in tree.findall('./nets/net') for node in net.findall('node')}
    for pin in [('U2','4'),('U4','1')]:
        if not pins.get(pin,'').startswith('unconnected-'):
            raise ValueError(f'{pin} must be unconnected')
    components={c.attrib['ref']:c.findtext('value') for c in tree.findall('./components/comp')}
    if components['U2']!='AP2112K-3.3TRG1' or components['U4']!='MCP73831T-2ACI/OT':
        raise ValueError('unexpected regulator/charger')
    board=parse(Path(pcb).read_text())
    points=[]
    for shape in find(board,'gr_line')+find(board,'gr_arc'):
        if find1(shape,'layer')[1]=='Edge.Cuts':
            points.extend(tuple(float(x) for x in find1(shape,key)[1:3]) for key in ('start','end'))
    width=max(x for x,y in points)-min(x for x,y in points)
    height=max(y for x,y in points)-min(y for x,y in points)
    if abs(width-48)>1e-5 or abs(height-54)>1e-5:
        raise ValueError(f'expected 48x54 mm, got {width}x{height}')
    print('PASS: Rev B power isolation, removed LED and 48x54 mm outline (5.75% less bounding area)')


if __name__=='__main__':
    check(sys.argv[1],sys.argv[2])
