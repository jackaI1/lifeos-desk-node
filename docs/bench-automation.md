# Automated power-up check on the bench

I built this bench check because I want to see whether the board's 3.3 V
regulator comes up after the 5 V input, how much ripple is on 3.3 V, and how
much current the board draws. I'll repeat those checks on every board revision,
and doing them by hand with a meter and a scope means I can miss a step. The
script sets the supply, turns it on, captures both rails, compares the results
with limits in a file, and writes the results to a timestamped folder.

Right now it runs against simulated instruments, so it works without any lab
hardware. The same code path is meant for the real supply and scope later.

## Words used here

- **SCPI** (Standard Commands for Programmable Instruments) is the text
  command set most bench supplies and scopes use, for example `SOUR:VOLT 5.0`
  sets the output voltage.
- **PyVISA** is a Python library that opens an instrument and sends it SCPI
  commands. **pyvisa-sim** is a PyVISA backend that answers those commands from
  a device file, so no instrument is needed.
- **Ripple** is the small repeating wiggle on a DC rail. I measure it as
  peak-to-peak, the difference between the highest and lowest voltage in a
  steady part of the capture.

## Run it

From the repository root, with Python 3.11 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r bench/requirements.txt
.venv/bin/python -m bench
.venv/bin/python -m bench --inject ripple
.venv/bin/python -m bench --inject late-rail
.venv/bin/python -m pytest bench/tests -q
```

Each run creates a folder `bench/build/runs/<UTC time>-<faults>/` with:

- `<time>_measurements.csv`: one row per check, with the measured value, the
  limits and PASS or FAIL,
- `<time>_capture.csv`: the sampled VBUS and 3V3 waveforms (6000 points),
- `report.md`: the steps taken, the readback values, the checks and a verdict.

Exit status: 0 when every check passes, 1 when a check fails, 2 when the bench
cannot run (bad config, an instrument refuses a setting, or no response).

## What a run does

1. Open the simulated supply and scope through PyVISA, and read their `*IDN?`.
2. Set VBUS to 5.000 V and read the setpoint back. A supply that does not
   accept the setting stops the run, so no result is recorded for a rail that
   was never set.
3. Turn the output on and wait for the scope (`*OPC?`).
4. Read the input current from the supply.
5. Capture CHAN1 (VBUS) and CHAN2 (3V3) as ASCII samples with the time base
   (`:WAV:XINC?`, `:WAV:XORIG?`).
6. Turn the output off and close the instruments, even when an earlier step
   failed. Temporary device files are deleted.

Then the limit logic checks these values against `bench/limits.toml`:

| Check | Limit (from `limits.toml`) |
| --- | --- |
| `rail_vbus_mean_v` | steady VBUS within ±5 % of 5.0 V |
| `rail_3v3_mean_v` | steady 3V3 within ±5 % of 3.3 V |
| `rail_3v3_ripple_mvpp` | at most 30 mVpp in the last 5 ms of the capture |
| `sequence_3v3_after_vbus_ms` | 3V3 reaches 90 % between 0.2 and 10 ms after VBUS reaches 90 % |
| `input_current_ma` | at most 150 mA from the 5 V supply |

The limits are bring-up targets I chose for this check. They are not datasheet
values. Before a measured result counts as a board pass, they should be
replaced with the numbers from the final power budget and the regulator
datasheet.

## Fault injection

`--inject` adds a fault to the simulated board, so I can see the check flag it:

| Fault | What the simulated board does | Expected result |
| --- | --- | --- |
| `ripple` | 60 mVpp on 3V3 | `rail_3v3_ripple_mvpp` FAIL (60 mVpp) |
| `late-rail` | the 3V3 regulator starts 14 ms late | `sequence_3v3_after_vbus_ms` FAIL (14 ms) |

Both can be combined with a comma, for example `--inject ripple,late-rail`.
The tests check that each fault fails exactly the check it targets and no other.

## How the simulator works

`bench/simulator.py` writes a pyvisa-sim device file for each run. The file
has two instruments:

- a supply with a stateful voltage setpoint, output switch and current reading.
  The simulated supply ignores setpoints above 6 V, as a real one might
  silently clamp them, and the harness catches this by reading the value back.
- a scope with record length, time step and two waveforms. Each waveform is
  one query (`:WAV:DATA? CHAN1`), which is how pyvisa-sim matches responses.
  A real scope would select the channel with `:WAV:SOURCE` first.

The rails come from a small model. VBUS rises over 1 ms after the output turns
on. The 3V3 regulator starts after 1.5 ms and rises over 1 ms, and 8 mVpp of
ripple at 230 kHz sits on it once it is up. The ripple frequency is not a
divisor of the 5 µs sample step. At 200 kHz the samples would land on the same
phase every time, and the ripple would vanish from the record.

## Using real instruments later

Only `bench/instruments.py` knows the resource names, and the harness takes
them from `bench/simulator.py`. To use a real supply and scope:

1. Install NI-VISA or another VISA library, and open the instruments with
   `pyvisa.ResourceManager()` instead of the `@sim` file.
2. Replace the resource strings with the instrument addresses shown by
   `ResourceManager().list_resources()`.
3. Check the SCPI commands against the instrument's programming manual. The
   scope commands in this file are a generic subset and may need changes for a
   specific model.
4. Set the scope's bandwidth and sample rate high enough that the ripple you
   care about is not filtered or aliased. The simulator keeps the ripple
   amplitude for one tone, but a real capture needs a scope that resolves the
   switching frequency.

## Limits of this check

- It is a simulation. A pass shows that the check logic works on simulated
  rails, not that the board works.
- The sequencing model has no load, inrush or start-up current, so it cannot
  show brownout or current limiting.
- Ripple is measured from one 30 ms capture. It does not separate
  switching ripple from noise, and it does not check load-step response.
