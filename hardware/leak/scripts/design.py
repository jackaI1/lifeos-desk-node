PROJECT,TITLE,REVISION,DATE='leak-node','Desk water probe interface','A','2026-11-06'
GND,V3,V5,VBUS='GND','+3V3','+5V','VBUS'
R='Resistor_SMD:R_0603_1608Metric';C='Capacitor_SMD:C_0603_1608Metric'
COMPONENTS=[
 dict(ref='J1',lib='Connector_Generic:Conn_01x04',value='MCU 3V3 GND ALERT SENSE',fp='Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical',mpn='Samtec TSW-104-07-G-S',at=(50,70),nets={'1':V3,'2':GND,'3':'ALERT_N','4':'SENSE'}),
 dict(ref='J2',lib='Connector_Generic:Conn_01x02',value='External conductive probe',fp='Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',mpn='Samtec TSW-102-07-G-S',at=(50,130),nets={'1':'SENSE','2':GND}),
 dict(ref='U1',lib='Comparator:LMV331',value='LMV331IDBVR',fp='Package_TO_SOT_SMD:SOT-23-5',mpn='LMV331IDBVR',at=(140,100),nets={'1':'SENSE','2':GND,'3':'REF','4':'ALERT_N','5':V3}),
 dict(ref='R1',lib='Device:R',value='1M',fp=R,mpn='RC0603FR-071ML',at=(90,70),nets={'1':V3,'2':'SENSE'}),
 dict(ref='R2',lib='Device:R',value='100k',fp=R,mpn='RC0603FR-07100KL',at=(90,120),nets={'1':V3,'2':'REF'}),
 dict(ref='R3',lib='Device:R',value='100k',fp=R,mpn='RC0603FR-07100KL',at=(90,165),nets={'1':'REF','2':GND}),
 dict(ref='R4',lib='Device:R',value='10M',fp=R,mpn='RC0603FR-0710ML',at=(140,160),nets={'1':'ALERT_N','2':'SENSE'}),
 dict(ref='R5',lib='Device:R',value='10k',fp=R,mpn='RC0603FR-0710KL',at=(190,70),nets={'1':V3,'2':'ALERT_N'}),
 dict(ref='R6',lib='Device:R',value='1k',fp=R,mpn='RC0603FR-071KL',at=(240,70),nets={'1':V3,'2':'LED_A'}),
 dict(ref='D1',lib='Device:LED',value='Red wet indicator',fp='LED_SMD:LED_0603_1608Metric',mpn='LTST-C190KRKT',at=(240,120),nets={'1':'ALERT_N','2':'LED_A'}),
 dict(ref='C1',lib='Device:C',value='100nF',fp=C,mpn='GRM188R71C104KA01D',at=(190,165),nets={'1':V3,'2':GND}),
]
PWR_FLAGS=[(V3,(270,70)),(GND,(290,70))]
NOTES=[((30,30),'3.3V conductive probe front end; active-low wet output; external probe; not a safety alarm'),((30,220),'1M pull-up and 10M feedback give hysteresis. Keep the probe traces clean and short. Prototype, not manufactured.')]

# Keep the exact footprint geometry local and portable with this board.
for component in COMPONENTS:
 component["fp"]="Leak:"+component["fp"].split(":")[1]
