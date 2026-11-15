# Signal integrity of the desk board: stackup, closed forms and the 3D model

This guide explains [`signal_integrity/`](../signal_integrity/), the check I run
on the Rev A board's copper before ordering. It reads the board file, computes
the impedance of its traces and vias from the stackup, solves a 3D model of one
trace through a via pair in openEMS, and reads the result with scikit-rf. The
output is a report with a table, two plots and a Touchstone file.

## Run it

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r signal_integrity/requirements.txt
.venv/bin/python -m signal_integrity              # closed forms only, no openEMS needed
```

The closed-form run writes `signal_integrity/build/report.md`. The 3D run needs
openEMS and CSXCAD. On Ubuntu 22.04 they come from apt (`openems` and
`python3-openems`); there is no Homebrew formula. Then:

```sh
python3 -m signal_integrity --simulate --out signal_integrity/build/openems
```

This adds the S-parameters, the TDR and two plots to the report, and writes
`desk_node_via.s2p`. Tests run the same way: `python3 -m pytest signal_integrity/tests -q`.
The openEMS test is skipped where openEMS is not installed.

## Stackup

| Item | Value | Source |
| --- | --- | --- |
| Board thickness (dielectric height) | 1.6 mm | The board file's `(general (thickness 1.6))` |
| Copper | 35 µm (1 oz) | [`hardware/docs/design.md`](../hardware/docs/design.md) |
| Permittivity, er | 4.5 | **Assumed**: a typical FR-4 value near 1 GHz |
| Loss tangent | 0.02 | **Assumed**: a typical FR-4 value |
| GND pour clearance | 0.3 mm | The GND zone's `connect_pads` clearance |
| Via pad and drill | 0.6 mm and 0.3 mm | Every via on the board |

The fabricator's stackup sheet should replace the two assumed values. A different
permittivity changes the impedances by a few percent; the report says which values
are assumed.

## Closed-form impedance

Two standard formulas, both written out in
[`signal_integrity/impedance.py`](../signal_integrity/impedance.py) and tested
against their own equations:

- **Microstrip** (a trace on the top layer over the bottom ground): the
  Hammerstad-Jensen form from Pozar's *Microwave Engineering*, with the Wheeler
  correction for the 35 µm copper.
- **Via** (a barrel through the board in a clearance hole): the coaxial
  approximation `Z = 60/√er · ln(D_antipad / D_drill)`.

| Track width | Microstrip Z0 | Length on the board |
| --- | --- | --- |
| 0.25 mm | 128.4 Ω | 784 mm |
| 0.30 mm | 123.0 Ω | 195 mm |
| 0.50 mm | 107.1 Ω | 29 mm |

- A 50 Ω trace needs a **2.97 mm** width on this stackup.
- The via has a 0.6 mm pad, 0.3 mm drill and a 1.2 mm antipad (pad plus two
  0.3 mm clearances). Its impedance is **39.2 Ω**.

So the board's ordinary tracks are high impedance (about 120 Ω), and every via is
low impedance (about 40 Ω). The via is the discontinuity a fast edge meets first.
The 3D model measures how much of the edge it reflects.

## The 3D model

[`signal_integrity/fdtd.py`](../signal_integrity/fdtd.py) builds the model in
openEMS. The representative trace is the signal net with the most track length (`/I2C_SCL`)
at its most common width (0.25 mm). Power and ground nets are skipped, because
their widths are set by current. The board has no fast digital bus, so this is a
representative geometry, not a net that needs 50 Ω.

```
  port 1  ------ top trace (0.25 mm, z = 1.6 mm) ------ via 1 (x = 8 mm)
                                                          |
             bottom trace across a slot in the GND pour (z = 0), 8 mm
                                                          |
                             via 2 (x = 16 mm) ----- top trace ------ port 2
```

- The substrate is one 1.6 mm FR-4 slab, with a loss tangent at the centre
  frequency. Air sits above it, with a PML absorbing boundary at the top.
- The bottom copper is the GND pour, with an antipad around each via and a slot
  around the bottom trace. The slot's width is the trace width plus two clearances.
- Each via is a PEC barrel through the substrate. The model leaves out the via
  pads and the solder mask.
- The mesh is 0.25 mm, smoothed outward, with lines at every feature edge.
- The gauss excitation is centred at 3 GHz and covers 0 to 6 GHz. The solver
  runs until the energy criterion is met (1 × 10⁻⁴).
- The structure is symmetric about its centre, so S22 equals S11 and S12 equals
  S21. One run with port 1 excited gives the full two-port.

scikit-rf then builds the two-port from S11 and S21 and reads the Touchstone file
back, so the same numbers come out of the file a reader can open.

## Results

The numbers below come from the openEMS job in CI, not from my laptop: the
closed-form run cannot produce them. The CI artifact `signal-integrity-openems`
holds the report, the plots and the Touchstone file from the run that produced them.

<!-- SIM-RESULTS -->

## The TDR-style response

The step response comes from the inverse FFT of S11, with a Hann window in
frequency. A step in the impedance appears at the round-trip time to the
discontinuity. [`signal_integrity/tdr.py`](../signal_integrity/tdr.py) checks the
inversion against a reflection of known impedance (40, 50 and 75 Ω): the recovered
value is within 1 % of the true value after the step.

## What the check does not show

- It is one representative trace, not every net. The power nets carry current, not
  impedance, so their widths are not judged here.
- The permittivity and loss tangent are typical values, not the board's.
- The model has no solder mask, no via pads and no copper roughness. These change
  the via's impedance and the loss at the top of the band.
- A simulation is not a measurement. A time-domain reflectometer on an assembled
  board is the test that settles it, and I have not built one yet.
