# Checking the sensor wires and serial log

I use the capture report when I need to tell a damaged sensor message from a
problem in my reading queue. A logic analyzer records whether each wire is high
or low over time. This tool opens that recording, asks sigrok to decode the wire
protocols, and checks the resulting sensor bytes. It never contacts LifeOS.

## Try it without hardware

From the repository root, install the command-line tools:

```sh
# macOS
brew install sigrok-cli guile
# Ubuntu alternative
# sudo apt-get install sigrok-cli guile-3.0 build-essential
python3 -m venv .venv
.venv/bin/python -m pip install -r capture/requirements-dev.txt
.venv/bin/python -m capture.demo
```

Python 3.11 or newer, Make and a C compiler are needed. The decoding tool itself
uses only Python's standard library; pytest is for the tests. I tested with
sigrok-cli 0.7.2, libsigrok 0.5.2 and libsigrokdecode 0.5.3. CI installs the real
Ubuntu packages and runs both Python 3.11 and 3.12.

The demo builds the existing C replay, compiles the two Scheme scenarios in
`capture/examples/`, and writes `replay/build/captures/`. It creates both sigrok
session files (`.sr`) and comma-separated sample tables (`.csv`). The clean
capture decodes one 25 C / 50% reading and 83 serial bytes with zero findings.
The damaged capture produces five findings in each format:

| Finding | What I changed |
| --- | --- |
| `unexpected_nack` | I made the sensor reject its write address. |
| `bad_crc` | The Scheme `fault` command flips the temperature checksum byte. |
| `missing_ack` | I left out the ninth clock pulse after the last sensor byte. |
| `incomplete_transaction` | That missing clock leaves the bus transaction unfinished at capture end. |
| `uart_framing` | I forced the first serial character's stop bit low. |

The serial log says the sample is unavailable because the existing C sensor
decoder also rejects that checksum. These are synthetic captures with deliberately
altered digital samples, not recordings of a physical board. Each `.sr.json` or
`.csv.json` manifest records that origin, the injected changes, sample rate and
sensor bytes. The decoder reads only the capture, never the manifest or the
scenario, so it must find the faults from the wire data.

Open `clean.sr` in PulseView to see the waveforms, or read the JSON reports:

```sh
.venv/bin/python -m capture.decode replay/build/captures/clean.sr
.venv/bin/python -m capture.decode replay/build/captures/corrupt.sr --report replay/build/faults.json
```

The second command returns exit status 1 because faults were found. Status 0
means the requested traffic decoded without findings; status 2 means invalid
input, a missing tool, or a sigrok failure. An idle recording does not pass.

## Record my board

The assembled board still needs bench validation. When I have one, I can connect
a **3.3 V compatible** logic analyzer's ground to board ground, and probe:

| Analyzer channel name | ESP32 pin | Signal |
| --- | --- | --- |
| `SCL` | GPIO22 | Sensor clock |
| `SDA` | GPIO21 | Sensor data |
| `TX` | GPIO1 | ESP32 serial output, not the adapter's transmit wire |

Use the [pinout](pinout.md) for power and I2C pull-ups. Sample at 2 MHz or faster
for the project's 100 kHz I2C bus and 115200-baud serial log. Capture a whole wake
cycle, including the `24 00` measurement command, the following 20 ms wait, the
six-byte sensor read and the serial log. Save the session in PulseView as `.sr`.
For example, with sigrok's FX2 driver and an analyzer attached:

```sh
sigrok-cli --driver fx2lafw --config samplerate=2m --channels 0=SCL,1=SDA,2=TX --time 10000 -o wake.sr
.venv/bin/python -m capture.decode wake.sr --report wake-report.json
```

That command records for ten seconds. Start it before waking the ESP32; normal
deep sleep is much longer than the capture window. A different analyzer needs its
own sigrok driver. The report includes the UART text, so inspect real captures
and reports for private log contents before sharing them.

Different channel names can be mapped explicitly:

```sh
.venv/bin/python -m capture.decode wake.sr --scl D0 --sda D1 --tx D2
.venv/bin/python -m capture.decode sensor.sr --protocols i2c --scl D0 --sda D1
.venv/bin/python -m capture.decode serial.sr --protocols uart --tx D2 --baudrate 115200
```

The session supplies its sample rate. The UART decoder is fixed to the device's
8N1 format: eight data bits, no parity check and one stop bit. `--baudrate` changes
the number of bits per second for a different firmware configuration.

## CSV recordings

I accept **uniformly sampled digital CSV**, with one row per sample and header
names matching the channels. For example:

```csv
SCL,SDA,TX
1,1,1
1,0,1
0,0,1
```

```sh
.venv/bin/python -m capture.decode samples.csv --samplerate 2000000 --report csv-report.json
```

Digital values must be `0` or `1`. An optional `time`, `Time`, or `Time [s]`
column contains seconds; consecutive times must match `--samplerate` within 1%.
`--scl`, `--sda` and `--tx` also select CSV column names. Single-protocol mode only
requires the selected protocol's columns. Other columns are ignored.

Many analyzer CSV exports contain only rows where a wire changes. Those are
**edge-only exports**, not uniform samples; I reject their nonuniform timestamps
rather than quietly decode them at the wrong speed. Export uniform samples or
save `.sr` instead. CSV is capped at eight million samples, and generated captures
have the same cap. Shorten long scenarios or capture only the relevant wake cycle.

## Change the generated recording

The generator uses the same six sensor bytes as the queue/display replay and the
same UART formatter as the firmware. Here is the full path for a custom scenario:

```sh
make -C replay
# Replace clean.scm with my own scenario file if needed.
guile --no-auto-compile -L replay/scheme replay/compile.scm < capture/examples/clean.scm > replay/build/my.wire
replay/build/desk-replay --uart-log replay/build/my.uart.txt < replay/build/my.wire
.venv/bin/python -m capture.generate replay/build/my.wire --uart-log replay/build/my.uart.txt --output replay/build/my.sr --fault humidity-crc
.venv/bin/python -m capture.decode replay/build/my.sr
```

Use `.csv` for a sample-table output instead. Repeat `--fault` to combine `nack`,
`humidity-crc`, `uart-framing` and `missing-ack`. The first three modify the first
sensor cycle; `missing-ack` truncates the last sensor transaction so later cycles
do not accidentally supply its missing clock. The existing Scheme `fault`
command independently corrupts the temperature CRC. The UART log must come from
the same replay run. An `upload` stays a simulated successful queue upload; it
adds a serial log but does not create a sensor transaction.

## What the report checks

`capture/decode.py` invokes sigrok-cli's actual `i2c` and `uart` protocol decoders
with sample-number annotations. It does not implement a second bit decoder.
For CSV, it validates and packs uniform samples into a temporary `.sr` session
through sigrok, then uses the same decoding path as a recorded session.

The report groups I2C bytes into transactions, including repeated starts, and
pairs each address/data byte with its ACK or NACK. An ACK means the receiver pulled
the data line low during the ninth clock pulse. A NACK leaves it high. A master
normally sends a NACK after the final read byte to end a read, so that NACK is
listed in `normal_read_end_nacks` instead of reported as a fault. An early NACK,
a rejected write address, or a decoded byte without an ACK slot is a finding.

At the SHT31's seven-bit address `0x44`, this project's measurement read must have
six bytes: temperature high/low/CRC, humidity high/low/CRC. A CRC is a small
checksum that helps detect damaged bytes. I independently check each CRC-8 with
polynomial `0x31` and initial value `0xff`. The known good bytes are
`66 66 93 80 00 a2`. A bad CRC leaves both physical values null instead of
presenting a plausible reading as trustworthy. Other bus addresses remain visible
but do not receive the SHT31-specific length or CRC checks.

Findings contain a code, sample position and explanation. The report also keeps
transaction bytes and acknowledgement states, raw sensor bytes and decoded UART
text. Sample numbers start at zero in the capture. Divide a sample number by the
sample rate to locate its time in seconds. UART framing findings come directly
from sigrok's invalid-start/stop-bit warnings, not from checksums invented for
serial text. The existing firmware UART format has no message checksum.

I interpret address `0x44` reads as measurement reads for this firmware. A capture
of other SHT31 commands, such as its status register, needs different length rules.
A capture beginning halfway through a message, wrong channel wiring, a wrong
baud rate, or noise can produce incomplete data. A UART frame cut off before
sigrok emits a warning may not be detectable. This tool cannot measure voltage,
rise time, pull-up strength or sensor accuracy. Synthetic fault mutations also do
not simulate how the ESP32 would react after a bus error.

## Tests and cleanup

```sh
.venv/bin/python -m pytest capture/tests -q
firmware/tests/run_host_tests.sh
make -C replay test
.venv/bin/python -m unittest discover -s automation/tests -v
```

The capture suite runs real sigrok subprocesses, Guile scenarios and a freshly
compiled C replay. It checks both capture formats, each injected fault, both CRC
bytes, exact UART round trips, multi-cycle uploads, channel remapping, repeated
starts, missing final NACKs, malformed CSV and input/tool failures. CI runs these
checks on two Python versions, generates the documented demo and saves the
captures, source scenarios and JSON reports as artifacts. Existing firmware,
replay and building-control checks continue in their own workflows.

The tool opens no server or browser. Every sigrok subprocess has a 90-second
timeout and is reaped; temporary conversion files are scoped to a temporary
directory even on failure. Decoder output is spooled to disk and limited to
32 MB before parsing; diagnostics are bounded. `make -C replay clean` removes
local example captures, logs and reports. No physical board is needed for these
checks, and a passing software test does not establish physical bus reliability.
