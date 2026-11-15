# SPICE checks for the power input and the I²C line

This guide covers the netlists in [`spice/`](../spice/) for the Rev A desk board
([`hardware/desk-node.kicad_sch`](../hardware/desk-node.kicad_sch)). They check
three things: the 5 V input and the 3.3 V regulator under load, ripple and
plug-in current; and the rise time of the SHT31 data line (SDA) at 100 kHz and
400 kHz. Every simulated result is compared with a hand calculation, and the
pull-up resistors from the schematic are checked against the I²C limits.

## Run it

Needs ngspice (`brew install ngspice` on macOS, `sudo apt-get install ngspice` on
Ubuntu) and KiCad 8's command-line tool `kicad-cli` on the path. From the
repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r spice/requirements.txt
.venv/bin/python -m pytest spice/tests -q
.venv/bin/python -m spice.checks --out spice/build
```

The last command writes `spice/build/report.md`, `results.json`, the KiCad
netlist it read (`netlist.xml`) and the exact decks it ran (`decks/`). Exit status
0 means every check passed, 1 means a check failed and 2 means the checks could
not run.

## What the netlists model

| Netlist | Circuit | What it runs |
| --- | --- | --- |
| [`usb_5v_regulator.cir`](../spice/usb_5v_regulator.cir) | VBUS through the fuse to +5V, C1, the AZ1117CH-3.3 LDO and the +3V3 capacitors | Plug-in inrush, 600 mA load step, a 250 mA burst pattern |
| [`i2c_pullup.cir`](../spice/i2c_pullup.cir) | R6 pull-up on SDA, the bus capacitance, an open-drain driver | A release at 100 kHz and at 400 kHz, measured 30 %-70 % |

Values come from the schematic. The checker reads the KiCad netlist and takes
C1 (+5V), the capacitors on +3V3 and R6/R7 from it. It also confirms the wiring
(C1 across +5V and GND, U2 from +5V to +3V3, R6 and R7 from +3V3 to SDA and SCL).
If someone moves a part, the run stops and says which connection changed.

Some values are not on the schematic. They are marked `ASSUMED` in the netlist
and in `spice/checks.py`:

| Value | Used as | Why it is an assumption |
| --- | --- | --- |
| USB cable and host path, 0.1 Ω | series resistance | Depends on the cable and the computer |
| Resettable fuse, 0.2 Ω | series resistance | Replace with the datasheet value for the 1206L075 part |
| LDO output resistance, 0.1 Ω | load regulation and ripple | The regulator's real output impedance is not on the schematic |
| LDO quiescent current, 5 mA | small load | Datasheet typical |
| Bus capacitance, 50 pF | I²C rise time | Pin, traces and the J2 header; a module on J2 adds more |
| Open-drain on-resistance, 20 Ω | driver | Only affects the falling edge |

The regulator is an idealised LDO: 3.3 V behind the output resistance, with a
dropout of 0.3 V below an undervoltage lock-out at 3.5 V. It has no loop
bandwidth or power-supply rejection, so the ripple result checks the RC network,
not the real regulator's rejection of input noise.

## Results and hand calculations

Simulated values and hand values agree to better than 0.1 % in every row. These
are the numbers from the local run that generated `spice/build/report.md`.

| Check | Simulated | Hand calculation | Limit | Margin on the board |
| --- | --- | --- | --- | --- |
| Inrush current into C1 at plug-in | 14.17 A | `V C/t_r (1 - e^(-t_r/RC))` = 14.17 A | none (informational) | Set by the 0.3 Ω path; the USB source limit decides whether this is a problem |
| +5V with 615 mA drawn | 4.816 V | `5 - I R` = 4.816 V | at least 4.75 V (USB minimum) | 66 mV |
| 3V3 at idle | 3.299 V | `3.3 - 10 mA × 0.1 Ω` = 3.299 V | none | none |
| 3V3 droop for the 600 mA step | 60 mV | `I R` = 60 mV | 3.135 to 3.465 V while loaded | 104 mV above the lower limit |
| 3V3 ripple, 250 mA burst | 25 mVpp | `I R (1 - e^(-t_on/RC))` = 25 mVpp | at most 30 mVpp | 5 mVpp |
| SDA 30 %-70 % rise, 100 kHz | 199 ns | `ln(7/3) R C` = 199.1 ns | at most 1000 ns | 801 ns |
| SDA 30 %-70 % rise, 400 kHz | 199 ns | 199.1 ns | at most 300 ns | 101 ns |
| Pull-up R6 and R7 window | 4.7 kΩ | 967 Ω (sink) to 7.08 kΩ (400 kHz rise) | inside the window | 1.5× the upper limit |

The limits are the 5 V minimum at the device (USB 2.0), ±5 % on the 3.3 V rail,
the bench ripple limit from [`bench/limits.toml`](../bench/limits.toml), and the
I²C fast-mode (300 ns) and standard-mode (1000 ns) rise limits. The 967 Ω lower
bound comes from the fast-mode sink requirement of 3 mA at 0.4 V.

### Pull-up sensitivity

The rise time scales with the bus capacitance, so the pull-up margin depends on
how much capacitance the board really has. The report gives the largest pull-up
that still meets 300 ns:

| Bus capacitance | Largest pull-up | R6 margin |
| --- | --- | --- |
| 50 pF (assumed) | 7.08 kΩ | 1.51× |
| 100 pF | 3.54 kΩ | **0.75×, fails** |

With the 4.7 kΩ pull-ups, the board passes fast mode if the bus stays near 50 pF.
A 100 pF bus, which a sensor module on J2 could add, fails. Lowering the pull-ups
to about 2.2 kΩ restores the margin for that case; that change needs a new
netlist run and a board change, and I have not made it.

## What these results do not show

- They are simulations of simplified models with assumed values. They do not
  measure the board. The first bench test on an assembled board should measure
  the same five quantities with a scope, and the [temperature sweep](temperature-sweep.md)
  does that on simulated instruments.
- The fuse, cable and regulator output impedance decide the inrush and ripple
  numbers. Replace the assumed values with datasheet numbers and re-run before
  trusting the margins.
- The SDA check uses a single pull-up on a lumped capacitance. It does not model
  the SHT31's own input stage, the ESP32's pad, or ringing on a long wire.

## Adding a check

Add a `.param` line (for the power netlist) or a `@TOKEN@` (for the I²C template)
in the netlist, fill it in `spice/checks.py`, and add a row in `power_checks` or
`i2c_checks` with its hand calculation in `spice/hand.py`. The test file
`spice/tests/test_checks.py` shows how the drift tests change a netlist and
confirm that the check fails.
