#!/usr/bin/env python3
"""Check the exported schematic against the firmware's physical pin contract.

This deliberately uses fixed expected pins, independent of design.py, to catch
an internally consistent but incorrectly wired schematic/PCB pair.
"""
import sys
import xml.etree.ElementTree as ET


def check(path, overrides=None):
    pins = {}
    for net in ET.parse(path).findall("./nets/net"):
        for node in net.findall("node"):
            pins[(node.attrib["ref"], node.attrib["pin"])] = net.attrib["name"]
    expected = {
        "U1": {"1": "GND", "2": "+3V3", "3": "/EN", "15": "GND",
               "25": "/IO0", "30": "/SPI_SCLK", "37": "/SPI_MOSI",
               "10": "/OLED_RST", "11": "/OLED_DC", "12": "/OLED_CS", "33": "/I2C_SDA", "34": "/U0RXD",
               "35": "/U0TXD", "36": "/I2C_SCL", "38": "GND", "39": "GND"},
        "U2": {"1": "GND", "2": "+3V3", "3": "+5V"},
        "U3": {"1": "/I2C_SDA", "2": "GND", "4": "/I2C_SCL", "5": "+3V3",
               "6": "/SHT_NRST", "7": "GND", "8": "GND", "9": "GND"},
        "J2": {"1": "GND", "2": "+3V3", "3": "/I2C_SCL", "4": "/I2C_SDA"},
        "J4": {"1": "GND", "2": "+3V3", "3": "/SPI_SCLK", "4": "/SPI_MOSI",
               "5": "/OLED_RST", "6": "/OLED_DC", "7": "/OLED_CS"},
        "J3": {"1": "GND", "2": "+3V3", "3": "/U0TXD", "4": "/U0RXD",
               "5": "/EN", "6": "/IO0"},
        "J1": {"A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
               "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND",
               "A5": "/CC1", "B5": "/CC2", "S1": "GND"},
        "R1": {"1": "/CC1", "2": "GND"},
        "R2": {"1": "/CC2", "2": "GND"},
        "R3": {"1": "+3V3", "2": "/EN"},
        "R4": {"1": "+3V3", "2": "/IO0"},
        "R5": {"1": "+3V3", "2": "/SHT_NRST"},
        "R6": {"1": "+3V3", "2": "/I2C_SDA"},
        "R7": {"1": "+3V3", "2": "/I2C_SCL"},
        "R9": {"1": "+3V3", "2": "/OLED_RST"},
        "R10": {"1": "+3V3", "2": "/OLED_CS"},
        "R11": {"1": "/OLED_DC", "2": "GND"},
        "F1": {"1": "VBUS", "2": "+5V"},
        "D1": {"1": "+5V", "2": "GND"},
    }
    expected.update(overrides or {})
    for ref, mapping in expected.items():
        for pin, name in mapping.items():
            actual = pins.get((ref, pin))
            if actual != name:
                raise ValueError(f"{ref}.{pin}: expected {name}, got {actual}")
    # FLASH/NC pins, unused boot straps and ALERT must stay free of external nets.
    for ref, numbers in {"U1": ["14", "17", "18", "19", "20", "21", "22", "23", "24", "29", "32"],
                         "U3": ["3"]}.items():
        for pin in numbers:
            if not pins.get((ref, pin), "").startswith("unconnected-"):
                raise ValueError(f"{ref}.{pin} must be unconnected")
    count = sum(map(len, expected.values()))
    print(f"PASS: {count} contract pin-net checks + 12 unused-pin checks")


if __name__ == "__main__":
    check(sys.argv[1])
