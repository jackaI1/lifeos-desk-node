# Temperature sweep bench harness

The sweep in [`bench/sweep.py`](../bench/sweep.py) qualifies the desk node over a
temperature range before I trust it in my room. It sets a chamber to each
temperature, waits for it to settle, captures the 3.3 V rail and the SDA line on
an oscilloscope, reads the SHT31's temperature from the board, and compares the
result with the chamber's reference probe. It then writes a Markdown report with
a table and plots.

Everything here runs on simulated instruments. The harness talks to them with
PyVISA and SCPI, the same way it would talk to real ones, so the simulation shows
that the harness works. It does not show that the board works.

## Instruments and their SCPI

| Role | Resource (simulated) | Commands the harness sends |
| --- | --- | --- |
| Environmental chamber | `TCPIP0::192.0.2.13::inst0::INSTR` | `:TEMP:SET <C>`, `:TEMP:SET?`, `:TEMP:PROBE?`, `:TEMP:STAT?` |
| Function generator | `TCPIP0::192.0.2.12::inst0::INSTR` | `SOUR1:FREQ <Hz>`, `SOUR1:FREQ?`, `OUTP1 ON/OFF` |
| Oscilloscope | `TCPIP0::192.0.2.11::inst0::INSTR` | `*OPC?`, `:WAV:POIN?`, `:WAV:XINC?`, `:WAV:XORIG?`, `:WAV:DATA? CHAN1`, `:WAV:DATA? CHAN2` |
| Desk node readback | `TCPIP0::192.0.2.14::inst0::INSTR` | `READ:TEMP?` |

The addresses are from 192.0.2.0/24, a range reserved for documentation, so they
do not point at anything on a real network. The simulated devices are defined in
[`bench/sweep_sim.py`](../bench/sweep_sim.py). For real hardware, give the four
strings on the command line (see below). The chamber and generator commands
above are the common SCPI forms; check your instrument's manual, because some
chambers use other names.

## One sweep step

For each setpoint in [`bench/sweep_limits.toml`](../bench/sweep_limits.toml):

1. **Set** the chamber setpoint and read it back. A refused value stops the run
   with a `SetpointError`.
2. **Settle.** Poll the chamber probe and status. The step passes this stage when
   the probe is within 0.3 °C of the setpoint and the status is `SETTLED`. If that
   does not happen within 600 s, the run stops with a `SettleTimeout`.
3. **Drive the bus.** Set the function generator to the I²C bus speed (100 kHz or
   400 kHz) and read it back.
4. **Capture.** Wait for the scope (`*OPC?`), then fetch CHAN1 (3.3 V rail) and
   CHAN2 (SDA).
5. **Read** the SHT31 temperature from the desk node.
6. **Judge** the four checks below, and write the row to the CSV.

| Check | Limit | Where it comes from |
| --- | --- | --- |
| SHT31 minus chamber reference | within ±1.0 °C | The SHT31 datasheet typical is ±0.3 °C; 1 °C leaves room for the probe and the room |
| 3.3 V rail mean | 3.135 to 3.465 V | ±5 % of nominal |
| 3.3 V ripple | at most 30 mVpp | The same limit as the power-up check in [`bench/limits.toml`](../bench/limits.toml) |
| SDA 30 %-70 % rise | at most 300 ns at 400 kHz, 1000 ns at 100 kHz | I²C fast-mode and standard-mode limits |

The rise time is measured from the captured SDA samples: the first rising edge
after the line goes low, between 30 % and 70 % of 3.3 V. It is not read from a
scope measurement command, so it works the same on any scope that returns its
samples.

A step that fails a check is recorded as `FAIL` with the check names, and the
sweep continues to the next setpoint. A settling timeout or an instrument error
stops the run: a bench problem is not a board result.

## Run it

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r bench/requirements.txt
.venv/bin/python -m bench.sweep
.venv/bin/python -m bench.sweep --inject sensor-drift
.venv/bin/python -m bench.sweep --inject ripple
.venv/bin/python -m bench.sweep --inject stuck-chamber
.venv/bin/python -m bench.sweep --bus-khz 100
```

Open `bench/build/sweeps/<stamp>-<faults>/report.md` for the table, the limits and
the steps the run took, and `sweep_plots.png` for the three plots. The
`measurements.csv` file has one row per setpoint.

Exit status: 0 every step passed, 1 at least one check failed, 2 the bench could
not run (settling timeout, an instrument that did not answer, a refused setpoint,
or a bad limits file).

Injected faults test the judging and error paths:

| Fault | What it does | Expected result |
| --- | --- | --- |
| `sensor-drift` | Adds 2 °C to the SHT31 reading at 40 °C and above | FAIL on `sht31_error` at 40 and 55 °C only |
| `ripple` | Raises the rail ripple to 60 mVpp | FAIL on `ripple_3v3` at every setpoint |
| `stuck-chamber` | Holds the chamber in `SETTLING`, 8 °C below the setpoint | Exit status 2 with a settling timeout |

The simulated devices run on a simulated clock, so a ten-minute settling timeout
takes no real time. Real instruments use the wall clock and the poll interval in
the limits file.

## Real instruments

Give all four resource strings, and the harness uses them instead of the
simulator:

```sh
.venv/bin/python -m bench.sweep \
  --chamber "TCPIP0::<chamber-ip>::inst0::INSTR" \
  --fgen "USB0::<vendor>::<model>::<serial>::INSTR" \
  --scope "TCPIP0::<scope-ip>::inst0::INSTR" \
  --dut "ASRL<port>::INSTR"
```

Use `python3 -c "import pyvisa; print(pyvisa.ResourceManager().list_resources())"`
to find the strings. Before a real run:

- **The desk node needs a readback.** The firmware logs its SHT31 readings over
  its UART, but it does not yet answer `READ:TEMP?`. A small serial bridge must
  print the latest reading when it receives that command. Until that bridge
  exists, the `--dut` option has nothing to answer.
- **Check the scope's channels.** CHAN1 is the 3.3 V rail, CHAN2 is SDA. Probe SDA
  with the probe's ground at the board's ground pin, not a long lead.
- **Use the bench's limits.** The limits are bring-up targets, not datasheet
  values, and the report says so.

## Limits of this harness

- It does not yet verify the chamber's own calibration. The reference is the
  chamber probe, so a probe error appears as an SHT31 error.
- The SDA capture is one edge per setpoint. A long-term or random error needs more
  records per step.
- A settled chamber with a still-warming board is possible. The settle check looks
  at the chamber probe, not the board's temperature.
