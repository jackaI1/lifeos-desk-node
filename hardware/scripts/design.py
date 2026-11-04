"""Single source of truth for the LifeOS desk node circuit.

Both the schematic generator (gen_schematic.py) and the board generator
(gen_pcb.py) read this file, and `kicad-cli pcb drc --schematic-parity`
checks the two KiCad outputs against each other in CI.

Electrical contract: docs/pinout.md (owned by the firmware branch).
  * ESP32-WROOM-32E-N4, I2C0 on GPIO21 (SDA) / GPIO22 (SCL), 100 kHz
  * SHT31-DIS at 0x44 (ADDR low, ALERT unused, nRESET pulled high)
  * SSD1306 128x64 7-pin SPI module; legacy 4-pin I2C expansion retained
  * UART0 programming header GND, 3V3, U0TXD/GPIO1, U0RXD/GPIO3, EN, GPIO0
  * USB 5 V in, 3.3 V regulator rated >= 600 mA
"""

PROJECT = "desk-node"
TITLE = "LifeOS desk node"
REVISION = "A"
DATE = "2026-11-03"

# Footprint shorthands (KiCad 8 standard library)
R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
SW_TS1187 = "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A"

# Net names
GND, VBUS, V5, V3 = "GND", "VBUS", "+5V", "+3V3"

# Each component: ref, lib symbol, value, footprint, LCSC part, MPN, schematic
# position (mm, symbol origin on an A3 sheet), and pin -> net map. Pins not in
# the map get a no-connect flag in the schematic.
COMPONENTS = [
    # ---------------------------------------------------------- power input
    dict(ref="J1", lib="Connector:USB_C_Receptacle_USB2.0_16P", value="USB-C power",
         fp="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         lcsc="C165948", mpn="HRO TYPE-C-31-M-12", at=(45, 75),
         nets={"A4": VBUS, "A9": VBUS, "B4": VBUS, "B9": VBUS,
               "A1": GND, "A12": GND, "B1": GND, "B12": GND, "S1": GND,
               "A5": "CC1", "B5": "CC2"}),
    dict(ref="R1", lib="Device:R", value="5.1k", fp=R0603, lcsc="C23186",
         mpn="0603WAF5101T5E", at=(75, 105), nets={"1": "CC1", "2": GND}),
    dict(ref="R2", lib="Device:R", value="5.1k", fp=R0603, lcsc="C23186",
         mpn="0603WAF5101T5E", at=(85, 105), nets={"1": "CC2", "2": GND}),
    dict(ref="F1", lib="Device:Polyfuse", value="750mA", fp="Fuse:Fuse_1206_3216Metric",
         lcsc="C99563", mpn="Littelfuse 1206L075THYR", at=(100, 55),
         nets={"1": VBUS, "2": V5}),
    dict(ref="D1", lib="Device:D_Zener", value="SMF5.0A", fp="Diode_SMD:D_SOD-123F",
         lcsc="C193402", mpn="MDD SMF5.0A (5 V TVS)", at=(115, 80),
         nets={"1": V5, "2": GND}),
    dict(ref="C1", lib="Device:C", value="10uF 25V", fp=C0805, lcsc="C15850",
         mpn="CL21A106KAYNNNE", at=(130, 80), nets={"1": V5, "2": GND}),
    dict(ref="U2", lib="Regulator_Linear:AZ1117-3.3", value="AZ1117CH-3.3TRG1",
         fp="Package_TO_SOT_SMD:SOT-223-3_TabPin2", lcsc="C92102",
         mpn="AZ1117CH-3.3TRG1", at=(155, 60),
         nets={"1": GND, "2": V3, "3": V5}),
    dict(ref="C2", lib="Device:C", value="22uF 16V", fp=C0805, lcsc="C98190",
         mpn="CL21A226MOQNNNE", at=(175, 80), nets={"1": V3, "2": GND}),
    dict(ref="C8", lib="Device:C", value="100nF", fp=C0603, lcsc="C1591",
         mpn="CL10B104KB8NNNC", at=(185, 80), nets={"1": V3, "2": GND}),
    dict(ref="R8", lib="Device:R", value="1k", fp=R0603, lcsc="C21190",
         mpn="0603WAF1001T5E", at=(200, 70), nets={"1": V3, "2": "LED_PWR"}),
    dict(ref="D2", lib="Device:LED", value="Red", fp=LED0603, lcsc="C2286",
         mpn="KT-0603R", at=(205, 90), nets={"2": "LED_PWR", "1": GND}),

    # ---------------------------------------------------------- ESP32
    dict(ref="U1", lib="RF_Module:ESP32-WROOM-32E", value="ESP32-WROOM-32E-N4",
         fp="DeskNode:ESP32-WROOM-32E", lcsc="C701341",
         mpn="Espressif ESP32-WROOM-32E-N4", at=(110, 185),
         nets={"1": GND, "15": GND, "38": GND, "39": GND, "2": V3,
               "3": "EN", "25": "IO0", "35": "U0TXD", "34": "U0RXD",
               "33": "I2C_SDA", "36": "I2C_SCL", "30": "SPI_SCLK", "37": "SPI_MOSI",
               "12": "OLED_CS", "11": "OLED_DC", "10": "OLED_RST"}),
    dict(ref="C3", lib="Device:C", value="22uF 16V", fp=C0805, lcsc="C98190",
         mpn="CL21A226MOQNNNE", at=(140, 140), nets={"1": V3, "2": GND}),
    dict(ref="C4", lib="Device:C", value="100nF", fp=C0603, lcsc="C1591",
         mpn="CL10B104KB8NNNC", at=(150, 140), nets={"1": V3, "2": GND}),
    dict(ref="R3", lib="Device:R", value="10k", fp=R0603, lcsc="C25804",
         mpn="0603WAF1002T5E", at=(55, 140), nets={"1": V3, "2": "EN"}),
    dict(ref="C5", lib="Device:C", value="1uF", fp=C0603, lcsc="C15849",
         mpn="CL10A105KB8NNNC", at=(55, 170), nets={"1": "EN", "2": GND}),
    dict(ref="SW1", lib="Switch:SW_Push", value="RESET", fp=SW_TS1187, lcsc="C318884",
         mpn="XKB TS-1187A-B-A-B", at=(40, 160), nets={"1": "EN", "2": GND}),
    dict(ref="R4", lib="Device:R", value="10k", fp=R0603, lcsc="C25804",
         mpn="0603WAF1002T5E", at=(165, 175), nets={"1": V3, "2": "IO0"}),
    dict(ref="SW2", lib="Switch:SW_Push", value="BOOT", fp=SW_TS1187, lcsc="C318884",
         mpn="XKB TS-1187A-B-A-B", at=(175, 200), nets={"1": "IO0", "2": GND}),

    # ---------------------------------------------------------- programming
    dict(ref="J3", lib="Connector_Generic:Conn_01x06", value="UART0 prog",
         fp="Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
         lcsc="C492405", mpn="XFCN PZ254V-11-06P", at=(250, 70),
         nets={"1": GND, "2": V3, "3": "U0TXD", "4": "U0RXD", "5": "EN", "6": "IO0"}),

    # ---------------------------------------------------------- I2C sensor + display
    dict(ref="U3", lib="Sensor_Humidity:SHT31-DIS", value="SHT31-DIS-B",
         fp="Sensor_Humidity:Sensirion_DFN-8-1EP_2.5x2.5mm_P0.5mm_EP1.1x1.7mm",
         lcsc="C80862", mpn="Sensirion SHT31-DIS-B2.5KS", at=(260, 175),
         nets={"1": "I2C_SDA", "2": GND, "4": "I2C_SCL", "5": V3, "6": "SHT_NRST",
               "7": GND, "8": GND, "9": GND}),
    dict(ref="C6", lib="Device:C", value="100nF", fp=C0603, lcsc="C1591",
         mpn="CL10B104KB8NNNC", at=(285, 170), nets={"1": V3, "2": GND}),
    dict(ref="R5", lib="Device:R", value="10k", fp=R0603, lcsc="C25804",
         mpn="0603WAF1002T5E", at=(235, 160), nets={"1": V3, "2": "SHT_NRST"}),
    dict(ref="R6", lib="Device:R", value="4.7k", fp=R0603, lcsc="C23162",
         mpn="0603WAF4701T5E", at=(215, 140), nets={"1": V3, "2": "I2C_SDA"}),
    dict(ref="R7", lib="Device:R", value="4.7k", fp=R0603, lcsc="C23162",
         mpn="0603WAF4701T5E", at=(225, 140), nets={"1": V3, "2": "I2C_SCL"}),
    dict(ref="J2", lib="Connector_Generic:Conn_01x04", value="I2C expansion",
         fp="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
         lcsc="C492403", mpn="XFCN PZ254V-11-04P", at=(365, 230),
         nets={"1": GND, "2": V3, "3": "I2C_SCL", "4": "I2C_SDA"}),
    dict(ref="C7", lib="Device:C", value="10uF 25V", fp=C0805, lcsc="C15850",
         mpn="CL21A106KAYNNNE", at=(290, 230), nets={"1": V3, "2": GND}),

    dict(ref="J4", lib="Connector_Generic:Conn_01x07", value="SSD1306 SPI OLED",
         fp="Connector_PinHeader_2.54mm:PinHeader_1x07_P2.54mm_Vertical",
         lcsc="C492406", mpn="XFCN PZ254V-11-07P", at=(325, 230),
         nets={"1": GND, "2": V3, "3": "SPI_SCLK", "4": "SPI_MOSI",
               "5": "OLED_RST", "6": "OLED_DC", "7": "OLED_CS"}),

    dict(ref="R9", lib="Device:R", value="10k", fp=R0603, lcsc="C25804",
         mpn="0603WAF1002T5E", at=(305, 195), nets={"1": V3, "2": "OLED_RST"}),
    dict(ref="R10", lib="Device:R", value="10k", fp=R0603, lcsc="C25804",
         mpn="0603WAF1002T5E", at=(330, 195), nets={"1": V3, "2": "OLED_CS"}),
    dict(ref="R11", lib="Device:R", value="10k", fp=R0603, lcsc="C25804",
         mpn="0603WAF1002T5E", at=(355, 195), nets={"1": "OLED_DC", "2": GND}),

    # ---------------------------------------------------------- mechanical
    *[dict(ref=f"H{i}", lib="Mechanical:MountingHole", value="M3",
           fp="MountingHole:MountingHole_3.2mm_M3", lcsc="", mpn="", at=(330 + 12 * i, 120),
           nets={}, bom=False) for i in range(1, 5)],
]

# Power symbols that get a PWR_FLAG (nets with power-input pins but no
# power-output driver).
PWR_FLAGS = [(GND, (275, 90)), (V5, (295, 90)), (VBUS, (315, 90))]

NOTES = [
    ((30, 30), "USB-C 5 V input: CC pull-downs request default USB power, 750 mA polyfuse, 5 V TVS, AZ1117C-3.3 LDO (800 mA)"),
    ((30, 125), "ESP32-WROOM-32E: EN RC reset (10k/1uF), GPIO0 BOOT strap; antenna overhang"),
    ((220, 45), "UART0 programming header (3.3 V adapter only; do not back-feed 3V3 while USB is plugged in)"),
    ((205, 115), "I2C @100 kHz: SHT31 0x44 on GPIO21/22; J2 expansion has 4.7k pull-ups"),
    ((30, 260), "J4 SPI OLED: GND, 3V3, SCLK18, MOSI23, RESET25, DC26, CS27"),
    ((330, 105), "Mounting holes (M3)"),
]
