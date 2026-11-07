# A water-probe board for my desk node

I built a small water-probe interface because I wanted to learn how to add a
simple leak indication beside the desk node's room readings. Two external probe
contacts act like a resistance: water lowers it, the board turns on a red light
and its output changes for a microcontroller to read. This is an unmanufactured
prototype, not a dependable flood alarm.

`leak-node.kicad_sch` is the circuit drawing and `leak-node.kicad_pcb` is its
45 by 35 mm, two-copper-layer layout. Footprints are embedded in the board and
the library tables name the stock KiCad 8 libraries. The MCU header is J1:
1=3.3 V, 2=ground, 3=active-low alert, 4=probe voltage for an ADC. J2 connects
the two external conductive probe contacts. The board does not include an MCU.

With KiCad 8 command-line tools installed, from the repository root:

```sh
hardware/leak/check.sh
```

I get electrical-rule and layout-rule reports, a PDF circuit drawing, a bill of
materials with manufacturer part numbers, and Gerber/drill files for fabrication
in `hardware/leak/build`. CI fails for any reported rule violation, including
schematic/layout disagreement, and saves those files as downloadable artifacts.
The check does not open a desktop application. Source changes can be regenerated
with `scripts/generate.py`; `scripts/board.py` does headless placement and imports
batch routes. The committed board is already routed and needs no router to check.

## Why these parts and dimensions

A 1 megohm pull-up keeps dry-probe current low. An LMV331 comparator compares the
probe voltage with half the supply from two 100 kilohm resistors. Its output
sinks current for the LED and has a separate 10 kilohm pull-up for the MCU. A
10 megohm feedback resistor gives hysteresis, so the output does not keep
switching at exactly one resistance. The ideal wet threshold is about 909
kilohms and release threshold about 1.11 megohms; real leakage, comparator offset,
probe contamination and water composition can move them. I must measure this
before choosing a useful physical threshold.

The 100 nF capacitor is beside the comparator supply. I use 0.25 mm signal
tracks, 0.20 mm net clearance, 0.6 mm vias with 0.3 mm drills and at least
0.3 mm copper-to-edge clearance. The current is low, so these widths are chosen
for routing and fabrication margin, not a high-current power path. The high
resistance input makes clean PCB surfaces, short probe leads and protection
against electrostatic discharge important. Continuous DC can corrode a wet
probe; intermittent power and a corrosion study are future hardware work.
The [simulation report](../simulation/report.md) shows the ideal threshold sweep
and the separate light-sensor amplifier calculation. No actual leakage, battery
draw or water response has been measured.
