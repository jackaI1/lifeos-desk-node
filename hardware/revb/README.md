# Battery desk node, Rev B

I built a smaller battery board because the USB version's regulator and power
light keep drawing current between updates. This version keeps the working
firmware pin assignments and the screen's last image, adds a LiPo charger, and
uses a regulator with a much smaller standing current. It is a routed prototype
design, not an assembled or measured board.

Open [desk-node-b.kicad_pro](desk-node-b.kicad_pro) in KiCad 8 to inspect the
circuit drawing and physical board. With KiCad 8 and Python 3.11 or newer on PATH:

```sh
hardware/revb/check.sh
python3 -m power_budget.compare
```

The first command checks the circuit and copper, checks the firmware pins and
battery connections independently, then exports files into `hardware/revb/fab/`.
The second prints calculated current and runtime. The
[power guide](../../docs/power-and-battery.md) explains every input and has an
empty table for real microamp-meter measurements.

## What changed

| Design choice | Rev A | Rev B |
| --- | --- | --- |
| Board bounding size | 50 × 55 mm | 48 × 54 mm, 5.75% less area |
| Supply | 5 V USB | Protected 1S LiPo, 4.2 V full; USB charges only |
| Regulator | AZ1117C-3.3, 4 mA typical own current | AP2112K-3.3, 55 µA typical own current, 600 mA output rating |
| Always-on light | Red LED through 1 kΩ | Removed |
| Charger | None | MCP73831T-2ACI/OT, 4.2 V, 100 mA set by 10 kΩ |
| Display | Powered throughout sleep | Same, no firmware changes |
| Signal connectors | J2 I²C, J3 UART, J4 SPI | Same pin assignments |

Dimensions describe the **carrier PCB**, not the complete assembled envelope:
the module antenna overhangs the top edge by 6.19 mm and connectors extend beyond
the board. The battery and display are external. The top slot ends at x = 46.5 mm;
the SHT31 sensor remains on the slotted peninsula. Antenna copper exclusions,
0.3 mm minimum drill, two copper layers and 0.15 mm minimum track/space are kept.
The module uses its factory antenna and match; the
[RF calculator](../../docs/antenna-matching.md) is for a future external feed,
not for attaching parts to the carrier's digital pins.

## Battery and charging connections

Use one protected 1S 4.2 V LiPo, nominally 500 mAh or more, with at least a 1 A
pulse rating and a manufacturer-approved charge current of at least 100 mA.
**J5 pin 1 is positive, pin 2 is ground.** Check polarity at the actual plug;
similar JST leads can be wired in opposite directions.

**JP1 must have exactly one two-pin shunt**, rated at least 1 A:

- **Pins 1–2 RUN:** battery feeds SYS and the 3.3 V regulator. The charger's
  battery output is disconnected from the cell.
- **Pins 2–3 CHARGE:** battery feeds the charger. SYS and the entire node load
  are disconnected. The screen goes off and pending readings are lost.

Unplug USB before moving the shunt. Never bridge all three pins. There is no
run-while-charging mode. J1 USB-C retains CC pull-downs, fuse and TVS; it feeds
only the charger. The programming adapter must use 3.3 V logic and leave its
power lead disconnected. J3 pin 2 is a voltage reference, not a power input.

The charger uses 10 µF at USB input and 4.7 µF at BAT. SYS has 10 µF, and the
regulator has 22 µF output plus local ceramic/bulk capacitors. Check ceramic
capacitance after voltage bias. At 100 mA and a 3.0 V cell, charger dissipation
is calculated as `(5 - 3) × 0.1 = 0.2 W`; thermal regulation can reduce current.
STAT is unused, so there is no charge-status light. Charge termination is about
7.5 mA for this exact charger suffix and cannot be confirmed by a light here.

This charger has no cell-temperature input, and this board has no independent
undervoltage cutoff. Use only a protected pack and supervised, room-temperature
charging allowed by its manufacturer. Stop normal operation at **3.7 V loaded**
for the runtime assumption; this is not an automatic cutoff or a guarantee of
regulation. The AP2112's maximum listed dropout at 600 mA is 400 mV, before output
tolerance, cell sag and trace loss. A protected pack's deep-discharge trip is far
below this usable operating point. The regulator may lose 3.3 V regulation first;
measure rail droop under Wi-Fi bursts before relying on stored readings.

## Checks and ordering

`check.sh` fails on every ERC or DRC severity, missing connection or schematic
parity difference, with no ignored violations. ERC checks electrical connections;
DRC checks copper spacing, outlines and connections. It also reproduces the
schematic from `scripts/design.py`, runs the independent fixed pin contract,
and checks the actual PCB outline dimensions. GitHub runs these checks alongside
Rev A's existing fabrication checks and uploads both sets of outputs.

The **committed routed PCB is the layout source**. `scripts/design.py` reuses
Rev A's signal circuit and replaces its supply; the schematic generator embeds
standard KiCad 8 symbols. The layout began with generated placement and
Freerouting 2.1, then received sensor connections and local power/ground repairs.
Regenerate only the schematic with `python3 hardware/revb/scripts/gen_schematic.py`;
edit the PCB in KiCad and rerun checks after layout changes. Do not use Rev A's
board generator on this layout. Library attribution is in
[the hardware library notes](../LIBRARIES.md); the copied WROOM footprint uses
the same 0.3 mm thermal drills and two-layer antenna exclusion.

Before ordering, compare exact manufacturer drawings for the SOT-23-5 regulator
and charger, battery connector polarity and shunt pitch. Review board-edge plug
access, the antenna/enclosure clearance, slots, footprints, paste, thermal vias,
and the fabrication and assembly previews. Supplier identifiers from Rev A's
component database apply to Rev A only; Rev B's exported BOM lists exact new
part numbers but does not claim purchasing approval or complete supplier records.
Neither ERC nor DRC establishes charge safety, heat, battery runtime, RF range,
sensor temperature bias or physical assembly fit.
