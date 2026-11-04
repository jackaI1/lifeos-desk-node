# Desk node enclosure: design spec

I'm designing a printed case and lid for my ESP32 desk device. The case has to hold the board, keep its Wi-Fi antenna clear, show the screen, let room air reach the sensor, and snap shut without tools.

This spec sets the requirements and starting dimensions. Every dimension lives in `params.json`, so changing one number rebuilds the parts.

## 1. Board frame

The board is 50 x 55 x 1.6 mm (`hardware/desk-node.kicad_pcb`). `desk-node-board.step` is the bare board with no parts on it.

Origin is the board's top-left corner. +X runs right, and +Y runs toward the USB edge. KiCad position minus (100, 100) gives these numbers.

| Feature | X | Y | Notes |
|---|---|---|---|
| H1 mounting hole | 4.0 | 11.0 | 3.2 mm |
| H2 mounting hole | 46.5 | 31.0 | 3.2 mm |
| H3 mounting hole | 4.0 | 51.0 | 3.2 mm |
| H4 mounting hole | 34.3 | 51.0 | 3.2 mm |
| J1 USB-C | 14.0 | 50.4 | Opens through the +Y edge |
| J2 expansion header | 21.5 | 51.0 | 4 pins, stays inside |
| J3 programming header | 46.6 | 12.6 | 6 pins, reached with the lid off |
| J4 screen header | 15.0 | 23.8 | 7 pins, short leads to the screen |
| SW1 RESET | 6.0 | 19.5 | Pinhole through the lid |
| SW2 BOOT | 38.0 | 30.5 | Under the screen, reached with the lid off |
| U1 ESP32 module | 25.0 | 6.56 | Antenna reaches Y = -6.19 |
| U3 room sensor | 44.5 | 49.5 | On the slotted peninsula |

The KiCad library has no 3D models for the USB-C, sensor and buttons. Use the manufacturer drawings for those heights, and mark them `MEASURE` until I've measured real parts.

## 2. Requirements

1. **Board mount.** Four bosses at H1 to H4 hold the board with M3 x 6 mm nylon screws. Check the underside parts before fixing the 4 mm boss height.
2. **Antenna.** Leave at least 15 mm of air from the antenna tip to the top inner wall, which puts that wall at Y = -21.19 or beyond. Keep screws, the screen and metal at least 15 mm from the antenna. H1 is 16.3 mm from its nearest corner, so a nylon screw there passes. Show this check on the drawing.
3. **Screen.** A 0.96 in SSD1306 module mounts to the lid, with its centre near (25, 30) so it stays clear of the antenna. Start from 27 x 27.8 mm with a 23.5 mm square hole pattern and a 21.7 x 10.9 mm active area. Mark all of these `MEASURE`.
4. **USB-C.** The wall opening has to clear the plug's overmould, starting at 12.5 x 7 mm centred on J1. Confirm the insertion depth with a real cable.
5. **Sensor air.** Vent slots in the lid and the +X and +Y walls sit around U3. An inner baffle separates that corner from the ESP32 and regulator, so their heat doesn't skew the reading. The baffle stays clear of the board's slot and of H4.
6. **Reset.** A 2 mm pinhole in the lid lines up with SW1.
7. **Closure.** Four snap fits, no tools, at least 10 open and close cycles.
8. **Walls.** 2.4 mm walls with 0.5 mm nominal clearance around the board. Inside height starts at 16 mm above the board for the header leads.
9. **Desk use.** The case sits flat with the screen readable. Round all outside edges and leave no sharp overhangs on the desk face.

## 3. Snap fit

Printed layers split easily, so a hook whose beam runs up through the layers would be the weak point. I put the flexing beam in the case wall, as a U-shaped cut with the beam running sideways. With the case printed floor-down, the beam lies along the layers. The hook tab is on the lid.

Sizing, for a constant rectangular cantilever:

`deflection = (2/3) x strain x length^2 / thickness`

Start with length 12 mm, thickness 1.6 mm and allowable strain 2% for printed PLA. That gives 1.2 mm of allowed deflection against a 1.0 mm undercut. Also report the root stress and the insertion force.

## 4. FEA

Run SolidWorks Simulation on one beam at full undercut deflection, using printed-PLA properties with the source named.

Report the mesh convergence (at least 3 mesh sizes), peak stress and strain, and the factor of safety. Require a factor of safety of at least 1.5, and agreement with the hand calculation within 15%. If the available study type can't handle the deflection, say so in the report. Note that the model treats the print as solid, so printed strength is lower and the physical test decides.

## 5. Tolerance stacks

Do each one as worst case and RSS. Name every contributor and where its value comes from.

1. USB-C shell to the wall opening in X and Z. Include board outline, hole position, boss position, connector placement and print error. The plug must clear at worst case.
2. Lid to case closure, and the snap hook's engagement at both extremes.
3. Screen active area to the lid window.

## 6. Drawings

ASME Y14.5 GD&T, with sheets for the case, the lid, and an exploded assembly with a parts list.

- Datum A: the board seat plane on the bosses. Datum B: the inner +Y wall. Datum C: the inner -X wall.
- Position tolerance on the boss pattern, flatness on the seats, and profile tolerances on the USB opening and screen window.
- Every tolerance must be one a 3D printer can hold, and must match the stacks in section 5.
- The educational licence may print a watermark on drawings. Leave it in place.

## 7. How the parts get built

`build_enclosure.py` drives SolidWorks through its COM API (Python with pywin32) and reads only from `params.json`. Running it rebuilds the parts, the assembly and the drawings, then exports STEP, STL and PDF.

`check_design.py` needs no SolidWorks. It checks the antenna distance, snap-fit numbers and tolerance stacks from `params.json`, with pytest tests that a CI workflow runs on every pull request.

## 8. What to commit

Everything goes in `mechanical/`: the two scripts, `params.json`, tests, native SolidWorks files, STEP, STL and drawing PDFs, the FEA report and hand calculations, and rendered images of the case open and closed.

## 9. Done means

- Rebuilding from `params.json` works from a clean SolidWorks start, with no rebuild errors.
- The assembly has no interference with the board, using the best part models available.
- The FEA and stacks meet the limits above.
- `mechanical/README.md` is written in first person: what it is and why, simple to technical, including what is still unmeasured.
- Physical results stay unclaimed until I've printed it and fitted a real board. They go in a results table with measured numbers afterward.
