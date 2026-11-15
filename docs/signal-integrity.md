# Signal integrity of the desk board: stackup, closed forms and the 3D via model

This guide explains [`signal_integrity/`](../signal_integrity/), the check I run on
the Rev A board's copper before ordering. It reads the board file, works out the
impedance of its traces and vias from the stackup, solves a 3D model of a 50 Ω
trace with a via in openEMS, and reads the result with scikit-rf. The output is a
report with a table, two plots and a Touchstone file.

What is verified and what is not is stated up front, because the 3D part is not
finished:

- **Verified:** the closed-form impedances, the board-file parsing, the TDR math,
  and the 3D model's **return loss and TDR impedance**, which the CI run reproduces.
- **Not verified:** the 3D model's **insertion loss**. Its |S21| goes above 1, which
  a passive via cannot do. I have not found the cause.

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

This runs the 3D model in a separate process (about 10 minutes on a CI runner),
reads the Touchstone result with scikit-rf, and writes the report, the plots and
`desk_node_via.s2p`. The command exits with status 1 if a verified check fails.

## Stackup

| Item | Value | Source |
| --- | --- | --- |
| Board thickness (dielectric height) | 1.6 mm | The board file's `(general (thickness 1.6))` |
| Copper | 35 µm (1 oz) | [`hardware/docs/design.md`](../hardware/docs/design.md) |
| Permittivity, er | 4.5 | **Assumed**: a typical FR-4 value near 1 GHz |
| Loss tangent | 0.02 | **Assumed**: a typical FR-4 value |
| GND pour clearance | 0.3 mm | The GND zone's `connect_pads` clearance |
| Via pad and drill | 0.6 mm and 0.3 mm | Every via on the board |

The fabricator's stackup sheet should replace the two assumed values.

## Closed-form impedance

Two standard formulas, written out in
[`signal_integrity/impedance.py`](../signal_integrity/impedance.py) and tested
against their own equations:

- **Microstrip** (a trace on the top layer over the bottom ground): the
  Hammerstad-Jensen form from Pozar's *Microwave Engineering*, with the Wheeler
  correction for the 35 µm copper.
- **Via** (a barrel through the board in a clearance hole): the coaxial
  approximation `Z = 60/√er · ln(D_antipad / D_drill)`.

| Track width | Microstrip Z0 | Total length on the board |
| --- | --- | --- |
| 0.25 mm | 128.4 Ω | 784 mm |
| 0.30 mm | 123.0 Ω | 195 mm |
| 0.50 mm | 107.1 Ω | 29 mm |

- A 50 Ω trace needs a **2.97 mm** width on this stackup.
- The via has a 0.6 mm pad, 0.3 mm drill and a 1.2 mm antipad (pad plus two
  0.3 mm clearances). Its impedance is **39.2 Ω**.

So the board's ordinary 0.25 mm tracks are about 128 Ω, not controlled 50 Ω. Each
via is about 39 Ω, which is lower than the 50 Ω reference. The via is where a fast
edge meets its first impedance step.

## The 3D model

[`signal_integrity/fdtd.py`](../signal_integrity/fdtd.py) builds the model in
openEMS. It checks a **50 Ω** trace through one via, not the board's 0.25 mm
traces. A strip that narrow is far above 50 Ω on this stackup, and it is smaller
than the mesh cells a 3D model can practically use. The closed-form table still
reports the board's own widths.

```
  port 1 ----- 50 ohm trace (2.97 mm, top layer) ----- port 2
                              |
                          via (0.6 mm square)
                              |
                       bottom pad, in a 1.2 mm
                       square antipad in the GND pour
```

- The line is 24 mm long, with the via at its centre, so each device plane is 12 mm
  from the via.
- The substrate is one 1.6 mm FR-4 slab, with a loss tangent at 3 GHz. The bottom
  copper is a solid GND pour (30 mm wide) with a square antipad round the via.
- Each port is a microstrip port whose outer section is 10 mm long, so its
  measurement plane sits 5 mm from the absorbing boundary. The openEMS microstrip
  tutorial uses the same layout.
- All six faces are absorbing (PML). Air is 6 mm below the board and 8 mm above.
  See the note on the air below.
- The mesh is 0.5 mm, smoothed outward, with extra lines at the via's edges. Every
  mesh spacing is at least 0.3 mm. A finer spacing forces a time step too small for
  the run to finish in a sensible time.
- The excitation is a Gauss pulse centred at 3 GHz, with a 3 GHz width.
- The run is 25,000 time steps. It does not reach openEMS's energy target, which is
  why insertion loss is not verified.

scikit-rf builds the two-port from S11 and S21 and reads the Touchstone file back.
The model is a single run with port 1 excited; S22 and S12 are not computed.

## What the 3D run shows

The numbers below are from the openEMS job in CI, not from my laptop: the closed-form
run cannot produce them.

| Frequency | Return loss (S11) | Insertion loss (S21), not verified |
| --- | --- | --- |
| 0.5 GHz | 25.2 dB | −0.9 dB |
| 1 GHz | 22.0 dB | +6.0 dB |
| 2 GHz | 21.2 dB | +3.8 dB |
| 3 GHz | 18.7 dB | +1.8 dB |
| 4 GHz | 14.1 dB | −0.9 dB |
| 5 GHz | 10.9 dB | +2.8 dB |
| 6 GHz | 17.9 dB | +6.9 dB |

The insertion-loss column is S21 expressed as loss, so a positive value is gain. A
gain is impossible for a passive network, which is why this column is not verified.

- **Return loss at 1 GHz is 22 dB**, so the 50 Ω trace reflects little at its
  design frequency. Checked: above 10 dB.
- **TDR impedance** is 44.2 to 45.9 Ω over the 0.2 to 2 ns window, with its lowest
  point of 44.2 Ω at about 0.23 ns. That is a dip below the 50 Ω reference, toward the
  via's 39.2 Ω closed-form value, as the via should produce. Checked: below 47.5 Ω and
  not below 31.4 Ω (80 % of the via's value). The time resolution of this TDR
  estimate is about 0.2 ns, so the dip's exact position is not precise.

## What is not verified, and what I tried

The solver stops at its 25,000-step limit before the energy has decayed. The solver
reports energy relative to its peak, and at the end it is still about 8 dB below that
peak (roughly 16 % of it). openEMS's target is 30 dB below the peak. The transmitted
wave is therefore incomplete, and |S21| comes out above 1 by up to 9 dB.

What I tried, in order:

- **Feed resistors** (50 Ω at each port): the printed results did not change.
- **Longer run** (80,000 steps): the energy at the end was still about 4 dB below
  its peak, and |S21| still exceeded 1 by up to 15 dB. The run took about 21 minutes, so I did not
  keep it.
- **Mesh spacing**: spacings below 0.3 mm forced a time step too small to finish. I
  kept every spacing at 0.3 mm or more.
- **Air below the board**: with 8 mm of air below, a plain 50 Ω line gave a return loss
  of 0 dB at every frequency, and with 6 mm it gave −30 to −49 dB. I did not find the
  reason, and the model uses 6 mm.

I have not found the cause of the remaining energy. Until it is found, I do not
report insertion loss as a result.

## What the check does not show

- It is one 50 Ω trace with one via, not every net. The 0.25 mm board traces are
  described in closed form only.
- The permittivity and loss tangent are typical values, not the board's.
- The model has no solder mask, no via pads beyond the 0.6 mm square, and
  zero-thickness copper.
- A simulation is not a measurement. A time-domain reflectometer on an assembled
  board is the test that settles it, and I have not built one yet.
