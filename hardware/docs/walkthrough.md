# How the desk board fits together

I built a circuit-board design because I wanted the desk display's controller,
room sensor and screen connections together before ordering a board. The gadget
is meant to show my next LifeOS class or deadline and send room temperature and
humidity readings back to LifeOS. This is a design for an unbuilt prototype.

## Following power and data

1. A USB-C wall supply brings in 5 V. A resettable fuse limits sustained fault
   current, and a protection diode absorbs short voltage spikes. These parts
   do not make the board safe for arbitrary power supplies.
2. A voltage regulator lowers that supply to the 3.3 V used by the electronics.
   The chosen regulator is an LDO, a linear regulator that needs some voltage
   difference between its input and output. That difference becomes heat.
3. The ESP32 controller reads the SHT31 room sensor over I²C, a two-wire data
   connection shared with the optional expansion socket. The firmware uses
   Wi-Fi to fetch the next event and upload readings through the LifeOS adapter.
4. The controller sends the event and reading to the screen over SPI, a clocked
   data connection with separate control signals. The seven-pin screen socket
   carries power, ground, clock, data, reset, command/data selection and selection
   of the screen. The screen stays powered between updates.
5. An external USB-to-UART adapter connects the computer to the programming
   socket. UART is the serial connection used to load firmware and read text
   logs. USB-C on this board supplies power only.

The PCB, or printed circuit board, replaces loose connections with patterned
copper paths. I kept copper away from the controller's antenna and put the room
sensor beside slots to reduce heat reaching it from the controller and regulator.
Those choices still need checking on a real assembled board.

## Finding the right file

| File | What I use it for |
| --- | --- |
| [desk-node.kicad_pro](../desk-node.kicad_pro) | Open the project and its settings in KiCad 8. |
| [desk-node.kicad_sch](../desk-node.kicad_sch) | Read the schematic, the drawing of parts and electrical connections. |
| [desk-node.kicad_pcb](../desk-node.kicad_pcb) | Inspect the physical board, component positions, holes and copper paths. |
| [bom.csv](../bom.csv) | Review the bill of materials, the shopping list with supplier part numbers. |
| [export_fab.sh](../scripts/export_fab.sh) | Check the design and generate manufacturing and assembly files. |
| [Board guide](../README.md) | Follow the connections, ordering and first-board steps. |

## Trying it without ordering anything

Install KiCad 8 with its standard symbol and footprint libraries. From a checkout
of this repository, open `hardware/desk-node.kicad_pro` in KiCad. The schematic
and board editors let me inspect the electrical drawing and physical layout.
From a terminal at the repository root, run:

```sh
kicad-cli version
hardware/scripts/export_fab.sh
```

If KiCad is installed as a macOS app and its command is not on PATH, run:

```sh
KICAD_CLI=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli hardware/scripts/export_fab.sh
```

The script runs ERC, electrical rule checking of the schematic, and DRC, design
rule checking of physical spacing and connections. It also checks that the board
matches the schematic and the agreed firmware pins. Passing these checks cannot
prove that parts fit, radio reception is good or a real board works.

The outputs appear in `hardware/fab/`. Gerbers describe the board layers, drill
files locate holes, the BOM lists parts and the placement file gives assembly
positions. Before paying for a board, I need to inspect antenna clearance,
connector orientation, footprints, part polarity, slots and placement rotations
in the manufacturer's preview. The [ordering checklist](design.md#review-by-eye-before-ordering)
covers those checks and first power-up.
