# Library attribution

Symbols, stock footprints and 3D models use the installed **KiCad 8** libraries:
[kicad-symbols](https://gitlab.com/kicad/libraries/kicad-symbols),
[kicad-footprints](https://gitlab.com/kicad/libraries/kicad-footprints), and
[kicad-packages3D](https://gitlab.com/kicad/libraries/kicad-packages3D).
They are licensed under [CC BY-SA 4.0 with KiCad's library exception](https://www.kicad.org/libraries/license/).

`DeskNode.pretty/ESP32-WROOM-32E.kicad_mod` derives from the KiCad 8.0.9
`RF_Module:ESP32-WROOM-32E` footprint, under that same license. Changes:

- Thermal pad 39's twelve through holes: **0.2 → 0.3 mm** drill, retaining the
  0.6 mm pad diameter (0.15 mm annular ring).
- Antenna rule area: `*.Cu` → `F.Cu,B.Cu`, matching this two-layer board and
  avoiding an internal-layer normalization difference in KiCad 8's parity check.

No third-party 3D models are copied into this repository. README images are
renders of the PCB and its available stock KiCad models. The exact USB-C, SHT31
and TS-1187A switch models are absent from the stock 8.0.9 package library; their
pads remain visible, and the hardware guide documents the limitation.
