# Desk node case checks

I built a set of checks for the desk node's case because I wanted to know whether the case fits the board and survives being knocked around before I print it or machine it. The board is 50 mm by 55 mm, and its four mounting holes and two connectors have to line up with the case. A print takes hours, so I want the numbers first.

The checks draw the case from a short list of dimensions, load it on a computer the way a screw or a drop would, and report where it is most stressed, how far it bends, and how much safety margin it has against the material yielding (bending permanently). A second check adds up the small size errors of the board, the standoffs and the printed case, and asks whether the screw still fits.

## What it found

These numbers come from the committed run in [docs/study.md](docs/study.md). Stress is in megapascals (MPa). The safety factor (SF) is the material's yield stress divided by the peak stress. An SF of 1 means the peak is exactly at yield, and anything above 1 stays under it.

| Check | Result |
|---|---|
| Lid screws at 300 N each, 2.0 mm walls, printed PETG | Peak stress 24.3 MPa, SF 2.06 |
| 50 N drop push on the wall top (about 10 g), 2.0 mm walls | Peak 3.5 MPa, SF 14 |
| Harsher drop, 500 N (about 100 g), 2.0 mm walls | Peak 35.1 MPa, SF 1.42 |
| Same screw load in machined 6061 aluminium | Peak 24.4 MPa, SF 11.3 |
| Wall thickness 2.0 to 4.0 mm | Screw peak stays between 24 and 28 MPa, so thicker walls do not lower it; drop stress falls with thickness |
| Vertical room above the board (worst case) | 1.39 mm left, need 0.5 mm: passes |
| M3 screw through a 3.2 mm board hole (worst case) | Short by 0.115 mm: fails |
| M3 screw through a 3.5 mm board hole (worst case) | 0.035 mm to spare: passes |

The tolerance check shows a real problem. My board still uses 3.2 mm mounting holes, and with the hole and boss positions allowed to drift in the worst case, an M3 screw no longer clears the hole. The check reports this as a failure instead of hiding it. The fix is a larger hole in the board design, which I have not made yet.

The solver was checked on a simple beam with a known answer. The tip deflection is within 0.65 % of the textbook value, and the bending stress in the middle half of the beam is within 0.1 % of the textbook formula at every point.

## How to run it

You need Python 3.12 and the CalculiX solver (`ccx`). On Ubuntu, `sudo apt-get install calculix-ccx`. On a Mac, `brew install costerwi/homebrew-calculix/calculix-ccx`, which installs `ccx_2.23`. The scripts look for `ccx` and `ccx_2.23`; set `CCX` to another path if yours is elsewhere.

From this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python -m pytest                       # all checks, including a real CalculiX run (about 15 s)
python -m enclosure_fea stackup        # print the tolerance stack-up as JSON
python -m enclosure_fea step           # write cad/desk-node-case.step, a STEP file any CAD program opens
python -m enclosure_fea cantilever     # solver check against the beam formula
python -m enclosure_fea study          # all load cases, wall sweep and mesh check (about 13 minutes)
```

`study` writes `docs/study.md` and `docs/study.json`, and its raw solver files go in `build/`. When you are done, remove the temporary files with `rm -rf build .venv`.

To try a different design, change a number in `enclosure_fea/board.py` (the case dimensions) or in `specs/` (the materials and the tolerances), then run the same commands again. Every tolerance is in `specs/stackup.json`, and each one notes whether I measured it or assumed it.

## How the model is set up

The case is a box with a cavity, four solid posts for the lid screws, four standoffs under the board's mounting holes, and openings in the front wall for the USB-C port and the header. The mounting hole positions come from the board's KiCad file, `hardware/desk-node.kicad_pcb`. Gmsh, a meshing program, builds the solid and the STEP file. It then fills the solid with ten-node tetrahedra (small pyramids with curved edges), which CalculiX solves in the usual linear way.

Units are newtons, millimetres and megapascals throughout. The stress I compare against yield is von Mises stress, a single number that combines the stresses in all directions. Printed PETG is treated as one uniform material, which is an approximation: a printed part is weaker between its layers, so the printed numbers are optimistic for loads that pull the layers apart.

The case sits flat on the desk, with its whole bottom face held in place. The screw load is applied as a pressure ring around each post top, and the drop is a pressure patch on the top of the front wall. I use static loads, so a drop is modelled as a steady push of the size an impact would produce, not as an impact.

## What is in this folder

- `enclosure_fea/board.py`: the board's hole and connector positions and the case dimensions.
- `enclosure_fea/geometry.py`: builds the solid, writes the STEP file and meshes it.
- `enclosure_fea/loads.py`: the support and load patches for each case.
- `enclosure_fea/solver.py`: writes the CalculiX input file, runs `ccx`, and reads the results strictly (a missing or malformed table is an error, not a guess).
- `enclosure_fea/studies.py`: the cantilever check, the load cases, the wall sweep, the mesh check and the report.
- `enclosure_fea/stackup.py`: the worst-case and root-sum-square tolerance chains.
- `specs/`: materials and tolerances, in millimetres.
- `cad/desk-node-case.step`: the case as a STEP file.
- `docs/study.md` and `docs/study.json`: the committed study results.
- `tests/`: 42 checks for the geometry, the loads, the solver output, the stack-up and the command line.

## Tests and CI

The GitHub Actions workflow `.github/workflows/mechanical-enclosure-fea.yml` installs CalculiX from Ubuntu, runs all the tests, and writes the STEP file and the stack-up report. The full study is not run in CI because it takes about 13 minutes; its results are committed instead, and the tests include a coarse drop case and the beam check so the solver is exercised on every change.

## Limits

- The stress peaks sit at sharp inside corners and at the edge of each load patch. They change with mesh size. The peak moved 5.5 % between the last two meshes, and a 0.7 mm mesh did not finish on my Mac. Treat the peak as a screening value. The mesh table in `docs/study.md` shows how much it moves.
- Printed PETG is modelled as an isotropic material with a datasheet-style yield value. Layer direction matters for printed parts, and I have not tested prints.
- The lid screw load is a guess of 300 N per screw. I have not measured the torque or the preload on a real screw.
- The drop is static. It does not model the impact, the bounce or the screen and board inertia.
- Nothing here has been checked against a physical part yet. The first real test is a printed case under a load.
