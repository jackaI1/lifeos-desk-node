"""Battery revision; reuse Rev A signal contract, replace its supply."""
import copy
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location("rev_a", Path(__file__).resolve().parents[2] / "scripts/design.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
PROJECT, TITLE, REVISION, DATE = "desk-node-b", "LifeOS battery desk node", "B", "2026-11-06"
GND, VBUS, V5, V3 = a.GND, a.VBUS, a.V5, a.V3
COMPONENTS = [copy.deepcopy(c) for c in a.COMPONENTS if c["ref"] not in ("R8", "D2")]
for c in COMPONENTS:
    if c["ref"] == "U2":
        c.update(lib="Regulator_Linear:AP2112K-3.3", value="AP2112K-3.3TRG1", fp="Package_TO_SOT_SMD:SOT-23-5", lcsc="C51118", mpn="AP2112K-3.3TRG1", nets={"1":"SYS", "2":GND,"3":"SYS","5":V3})
    if c["ref"] == "C2":
        c.update(value="22uF 16V")
COMPONENTS += [
 dict(ref="U4",lib="Battery_Management:MCP73831-2-OT",value="MCP73831T-2ACI/OT",fp="Package_TO_SOT_SMD:SOT-23-5",mpn="MCP73831T-2ACI/OT",at=(110,290),nets={"2":GND,"3":"CHARGE_BAT","4":V5,"5":"PROG"}),
 dict(ref="R12",lib="Device:R",value="10k 100mA charge",fp=a.R0603,mpn="0603WAF1002T5E",at=(80,300),nets={"1":"PROG","2":GND}),
 dict(ref="C9",lib="Device:C",value="4.7uF 10V",fp=a.C0805,mpn="GRM21BR71A475KA73L",at=(145,280),nets={"1":"CHARGE_BAT","2":GND}),
 dict(ref="C10",lib="Device:C",value="10uF 10V",fp=a.C0805,mpn="GRM21BR61A106KE19L",at=(175,280),nets={"1":"SYS","2":GND}),
 dict(ref="J5",lib="Connector_Generic:Conn_01x02",value="Protected 1S LiPo",fp="Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal",mpn="JST S2B-PH-SM4-TB",at=(210,280),nets={"1":"BAT_PLUS","2":GND}),
 dict(ref="JP1",lib="Connector_Generic:Conn_01x03",value="1-2 RUN / 2-3 CHARGE",fp="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",mpn="Samtec TSW-103-07-G-S + one shunt",at=(260,280),nets={"1":"SYS","2":"BAT_PLUS","3":"CHARGE_BAT"}),
]
PWR_FLAGS = [(GND,(275,90)),(V5,(295,90)),(VBUS,(315,90)),("SYS",(300,305))]
NOTES = [(p,s) for p,s in a.NOTES if p != (30,30)] + [
 ((30,30),"USB-C charges only; AP2112K 600mA 55uA IQ; no always-on power LED"),
 ((30,325),"JP1: ONE shunt only, 1-2 RUN or 2-3 CHARGE. Remove USB before moving shunt. Charge disconnects all node loads."),
 ((30,340),"Protected 1S 4.2V LiPo >=500mAh, >=1A pulse. 100mA charge; no cell temperature supervision. Supervised room-temperature charging only."),
]
