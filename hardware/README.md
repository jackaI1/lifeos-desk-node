# LifeOS desk node PCB — revision A

KiCad **8.0.9**, two copper layers, **50 × 55 mm**, 1.6 mm FR-4, 1 oz copper.
Open `desk-node.kicad_pro` to inspect the schematic and routed PCB together.
This is an unbuilt prototype design; ERC/DRC success is not bench validation.

![Top assembly, rendered from the KiCad PCB](images/desk-node-top.png)
![Bottom assembly, rendered from the KiCad PCB](images/desk-node-bottom.png)

The KiCad 8 model library lacks the exact USB-C, SHT31 and two pushbutton models;
these locations show their board pads only. These renders do not validate those
parts' body height, plug fit or sensor opening. Check the manufacturer drawings.

## Circuit and firmware contract

The board implements [pinout revision 2](../docs/pinout.md):

| Interface | Connector / pins | Behavior |
| --- | --- | --- |
| Sensor | SHT31-DIS, SDA GPIO21 / SCL GPIO22 | I²C at 100 kHz, address 0x44 |
| Default display | J4: GND, 3V3, SCLK18, MOSI23, RESET25, DC26, CS27 | Seven-pin SSD1306 module, 4-wire SPI, mode 0, 4 MHz |
| Expansion / legacy display | J2: GND, 3V3, SCL22, SDA21 | Optional legacy SSD1306 I²C at 0x3C |
| Programming / logs | J3: GND, 3V3 reference, TX GPIO1, RX GPIO3, EN, GPIO0 | UART0 115200 8N1; RESET + BOOT buttons |
| Power | J1 USB-C | **5 V power only**, no USB data or USB–UART bridge |

Use an external **3.3 V logic** UART adapter, TX crossed to RX. With USB power
connected, leave the adapter's supply lead disconnected; J3 pin 2 is a reference,
not a second power input. Hold BOOT, tap RESET, release BOOT to enter the ROM
loader. UART0 exposes both bootloader programming and firmware cycle logs.

J1 has separate 5.1 kΩ CC pull-downs, a 750 mA resettable fuse, and a unidirectional
5 V TVS after the fuse. The AZ1117CH-3.3TRG1 is an **800 mA** ceramic-compatible
LDO. C1 is 10 µF input; C2 is 22 µF output with 100 nF in parallel; the ESP32 and
display have local bulk and ceramic capacitors. Use a regulated USB wall supply
with sufficient current for Wi-Fi peaks (5 V, 1 A or more). This board does not
enumerate on USB or negotiate PD/current capability; do not assume a computer's
unconfigured USB port permits its peak load. The fuse is fault protection, not
a precise current limiter or overvoltage disconnect.

At 250 mA, estimated LDO dissipation is `(5 − 3.3) × 0.25 = 0.425 W`; a 600 mA
burst gives 1.02 W before quiescent losses. The output tab has a dedicated +3V3
copper area. The 800 mA device rating is **not** a claim of continuous board
thermal capability. Measure rail droop and temperature during Wi-Fi operation.
LED and LDO quiescent current also prevent microamp whole-board sleep claims.
Battery charging is omitted because the firmware contract targets USB power;
there is no battery connector or safe Li-ion power path in this revision.

The WROOM-32E follows the existing firmware contract instead of changing to C3/S3.
Its PCB antenna extends **6.19 mm beyond the top board edge**. The footprint and
board keep-outs prohibit copper/tracks/vias/pads around the antenna. The SHT31
sits on an L-slotted peninsula away from the LDO/ESP32, with no copper pour on
that peninsula. Routed power, ground and I²C traces cross its remaining neck.
Allow airflow and compare readings against ambient after warm-up.

R6/R7 provide the I²C pull-ups. Account for any pull-ups on a J2 module. R9/R10
pull OLED RESET/CS high and R11 pulls D/C low so the powered SPI display retains
its frame when the ESP32 releases its GPIOs in deep sleep. Connect only the
display variant selected in firmware.

## Validation and fabrication

```sh
# KiCad 8 must be installed, with its standard symbols and footprints.
KICAD_CLI=kicad-cli hardware/scripts/export_fab.sh
```

The script fails on **any** ERC/DRC severity, checks schematic parity and an
independent physical pin contract, then writes `hardware/fab/`:

- `desk-node-gerbers.zip`: copper, mask, silk, paste, outline and Excellon drills.
- `desk-node-bom-jlcpcb.csv`: grouped BOM with LCSC/JLCPCB part numbers.
- `desk-node-cpl-jlcpcb.csv`: assembly positions in mm and rotations.
- Native KiCad BOM/positions, schematic PDF and ERC/DRC reports.

[Hardware CI](../.github/workflows/hardware.yml) runs the same checks and uploads
the `desk-node-fab` artifact. Download the artifact for the exact commit you intend
to order. The checked-in [BOM](bom.csv) is also convenient for reviewing parts.
LCSC identities are specified, but stock, assembly eligibility, rotation offsets
and order pricing must be checked in the manufacturer's order preview. Headers
may need hand assembly. The external OLED, UART adapter and mounting hardware
are not included in the board BOM.

Design constraints: 0.15 mm minimum track/space, 0.3 mm copper-to-edge, 0.6/0.3 mm
via pad/drill. The local WROOM footprint changes the stock KiCad 0.2 mm thermal
drills to 0.3 mm and restricts its keep-out layer set to the two copper layers;
see [library attribution](LIBRARIES.md). Copper pours are filled and saved in the
PCB. Routing uses 0.5 mm USB/5 V, 0.3 mm 3V3 and 0.25 mm default tracks, with
local neck-downs as required by small pads. Both layers have GND pours/stitching.

## Regeneration

`scripts/design.py` defines parts, symbols, values and pin connections;
`scripts/gen_pcb.py` defines placement, outline and thermal/RF exclusions.
The committed routed PCB is the fabrication source. `finish_routes.py` completes
the two sensor-area paths left by Freerouting 2.1, using a conservative B.Cu
clearance grid; final KiCad DRC is authoritative. Freerouting 2.1 may run its
999-pass fallback despite `-mp`, so this regeneration can take several minutes. Rebuilding routes may produce
a different layout and **must** be followed by ERC/DRC and visual review.

```sh
# KiCad Python must be the interpreter containing pcbnew (bundled on macOS).
FREEROUTING_JAR=/path/to/freerouting.jar \
KICAD_CLI=kicad-cli JAVA=/path/to/java hardware/scripts/build.sh

# Render actual KiCad 3D geometry, using installed stock model libraries.
kicad-cli pcb export glb --subst-models --include-tracks --include-zones \
  --user-origin 100x100mm --force -o hardware/build/desk-node.glb hardware/desk-node.kicad_pcb
blender --background --factory-startup --python hardware/scripts/render_3d.py \
  -- hardware/build/desk-node.glb hardware/images
```

## Review by eye before ordering

- **Antenna:** module overhang and enclosure/metal/cable clearances. Espressif
  recommends at least 15 mm clearance inside the housing; keep screws and the
  display away from the antenna. Confirm RF performance on the assembled unit.
- **Connectors:** match J4's exact seven-pin order and 4-wire SPI straps to the
  purchased SSD1306 module. Check J2/J3 pin 1, crossed UART TX/RX, USB connector
  insertion direction, enclosure opening and plug access. Use short SPI leads.
- **Footprints/polarity:** compare USB-C shell holes, SHT31 pin 1/exposed pad,
  WROOM pads and thermal drills, LDO pinout, TVS cathode and LED cathode against
  the exact manufacturer drawings. Inspect paste coverage and thermal-via
  wicking risk with the assembler.
- **Manufacturing preview:** inspect both Gerber layers, connected ground fill,
  the 1 mm L-shaped routed slot and its inside corner radii, drill registration,
  silkscreen, mounting holes, CPL centroids and every polarized-part rotation.
  Confirm the fab supports the slot and the sensor neck survives handling.
- **First-board bring-up:** continuity check before power, current-limited 5 V,
  confirm 3.3 V and EN, flash over UART, scan for SHT31 at 0x44, verify SPI pixels
  and UART logs, then measure Wi-Fi rail droop, LDO temperature and sensor bias.

## Sources

- [Espressif module datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf)
  and [module placement guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html).
- [Sensirion SHT3x-DIS datasheet](https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf).
- [Diodes AZ1117C datasheet](https://www.diodes.com/datasheet/download/AZ1117C.pdf),
  including ceramic capacitor stability and thermal limits.
- [SHT31 assembly part C80862](https://jlcpcb.com/partdetail/Sensirion-SHT31_DIS_B25kS/C80862),
  [AZ1117C C92102](https://www.lcsc.com/product-detail/C92102.html),
  [seven-pin header C492406](https://www.lcsc.com/product-detail/C492406.html).
