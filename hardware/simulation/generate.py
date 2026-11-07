"""Native KiCad supply and photodiode amplifier, sharing the desk sheet writer."""
import json
import importlib.util
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'scripts'))
import gen_schematic as sch
import gen_project as project
import types
R='Resistor_SMD:R_0603_1608Metric';C='Capacitor_SMD:C_0603_1608Metric'
d=types.SimpleNamespace(PROJECT='light-front-end',TITLE='Desk light input and 3.3V supply',DATE='2026-11-06',REVISION='A',GND='GND',V3='+3V3',V5='+5V',VBUS='VBUS')
d.COMPONENTS=[
 dict(ref='J1',lib='Connector_Generic:Conn_01x02',value='5V input',fp='Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',at=(40,70),nets={'1':d.V5,'2':d.GND}),
 dict(ref='U1',lib='Regulator_Linear:AP2112K-3.3',value='AP2112K-3.3TRG1',fp='Package_TO_SOT_SMD:SOT-23-5',at=(90,70),nets={'1':d.V5,'2':d.GND,'3':d.V5,'5':d.V3}),
 dict(ref='C1',lib='Device:C',value='1uF',fp=C,at=(40,120),nets={'1':d.V5,'2':d.GND}),
 dict(ref='C2',lib='Device:C',value='1uF',fp=C,at=(90,120),nets={'1':d.V3,'2':d.GND}),
 dict(ref='R1',lib='Device:R',value='100k',fp=R,at=(140,70),nets={'1':d.V3,'2':'REF'}),
 dict(ref='R2',lib='Device:R',value='100k',fp=R,at=(140,120),nets={'1':'REF','2':d.GND}),
 dict(ref='C3',lib='Device:C',value='100pF',fp=C,at=(200,165),nets={'1':'OUT','2':'SUM'}),
 dict(ref='R3',lib='Device:R',value='100k',fp=R,at=(200,210),nets={'1':'OUT','2':'SUM'}),
 dict(ref='U2',lib='Amplifier_Operational:MCP6001R',value='MCP6001RT-I/OT',fp='Package_TO_SOT_SMD:SOT-23-5',at=(250,100),nets={'1':'OUT','2':d.V3,'3':'REF','4':'SUM','5':d.GND}),
 dict(ref='D1',lib='Device:D_Photo',value='BPW34 photodiode',fp='OptoDevice:Photodiode_Vishay_BPW34',at=(200,70),nets={'1':'SUM','2':d.GND}),
 dict(ref='C5',lib='Device:C',value='1nF',fp=C,at=(140,165),nets={'1':'REF','2':d.GND}),
 dict(ref='C4',lib='Device:C',value='100nF',fp=C,at=(300,70),nets={'1':d.V3,'2':d.GND}),
 dict(ref='J2',lib='Connector_Generic:Conn_01x02',value='ADC output',fp='Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',at=(320,130),nets={'1':'OUT','2':d.GND}),
]
sch.design=project.design=d
sheet=sch.Sheet(sch.Libs(next(p for p in sch.DEFAULT_SYMBOLS if p and Path(p).is_dir())))
for c in d.COMPONENTS:sheet.component(c)
sheet.pwr_flag(d.V5,(340,70));sheet.pwr_flag(d.GND,(360,70))
sheet.text((30,30),'Light input prototype: photodiode current becomes an ADC voltage; model assumptions in report.md')
(HERE/'light-front-end.kicad_sch').write_text(sheet.render().replace('Pinout contract: docs/pinout.md','Circuit model: hardware/simulation/report.md'))
project.lib_tables(str(HERE))

project.PROJECT["meta"]["filename"]=d.PROJECT+".kicad_pro"
project.PROJECT["net_settings"]["netclass_patterns"]=[]
(HERE/(d.PROJECT+".kicad_pro")).write_text(json.dumps(project.PROJECT,indent=2)+"\n")
