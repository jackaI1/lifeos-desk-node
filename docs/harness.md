# Harness documentation

The example describes two separate removable leads: J2 to an optional external
I2C sensor module and J3 to a 3.3 V USB-to-UART adapter. The SHT31 is already
on the board. An extra sensor must have a compatible address and pin order; the
example is a wiring plan, not proof of compatibility. J3 pin 2 is a voltage
reference, not an adapter power connection when USB powers the board. The TX
and RX leads cross. Use the board's BOOT and RESET buttons to flash; RTS and
DTR require an appropriate auto-reset circuit and are not wired in this example.
Consult [the pinout](pinout.md) and your actual module documentation before wiring.

Copy `harness/example.json` and edit its connector names and wires. Each wire
has a unique ID, net name, two `[connector, pin]` endpoints, cut length in mm,
AWG (American Wire Gauge), color and maximum expected current in amperes. The
length is the actual cut length, including any desired stripping and routing
allowance; measure the route and update it before cutting. Set `requires_ground`
on each connector that needs a ground. This point-to-point format intentionally
rejects a pin used twice: describe splices with separate connector pins and
verify the splice separately. The check verifies declared grounds, not complete
electrical connectivity or correctness against the board schematic.

Run the check and generator shown in the main README. The generator refuses an
invalid map. `cut-list.csv` is the cutting schedule; `labels.csv` has one row
per end and can be printed or imported into label software. Open `harness.svg`
in a browser and print it as a connection drawing. Open `test-sheet.csv` in a
spreadsheet and print it to record measurements and initials. Check continuity
with all supplies disconnected, then check for a 3V3-to-ground short. Inspect
polarity before applying a single supply, then measure the voltage. These are
manual checks; generated expected results are not measured results.

Current limits are deliberately conservative planning thresholds for individual
wires (20: 1 A, 22: 0.7 A, 24: 0.5 A, 26: 0.3 A, 28: 0.2 A). They are not
manufacturer ratings. Confirm insulation, terminal compatibility, bundling,
temperature, voltage drop, fault protection and actual peak current for the
chosen wire and application. This tool does not size connectors or fuses, test
hardware, infer shared grounds or prevent all wiring mistakes.
