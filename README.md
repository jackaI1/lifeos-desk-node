# LifeOS Desk Node

I built a small desk display and room monitor because I wanted to see my next class at a glance and keep temperature and humidity readings in LifeOS.

The display is meant to show my next class or task beside the latest room
reading. LifeOS is my planning system. The device program wakes about every
five minutes, reads the sensor and sends readings over Wi-Fi to a small program
beside LifeOS, where they become daily room-log notes.

I can try the sensor queue and screen on my computer with the outage demo below.
It uses the same code as the device, with pretend readings and uploads. For the
physical display, I use the [parts and wiring](#parts-and-wiring) and
[build and flash](#build-and-flash) steps. I have software checks and a board
design; I still need to bench-test an assembled device, including its screen,
sensor accuracy and power draw.

## Try a sensor outage without a board

I use Guile, a program that runs Scheme, to turn a short scenario into sensor
bytes. A C program then feeds those bytes through the device's existing code.
Install Guile 3 with `brew install guile` on macOS or
`sudo apt-get install guile-3.0` on Ubuntu. With a C compiler and Make installed,
run these commands from the repository root:

```sh
make -C replay
guile --no-auto-compile -L replay/scheme replay/compile.scm < replay/examples/outage.scm > replay/build/outage.wire
replay/build/desk-replay --pbm replay/build/screen.pbm < replay/build/outage.wire
```

The example sends 70 good readings and one damaged reading before a simulated
upload. The result reports 64 uploaded, six dropped and one sensor fault. The
screen image is `replay/build/screen.pbm`, a plain black-and-white image file.
The [replay guide](docs/sensor-replay.md) explains how I change the readings,
repeat a sequence and view the image. These checks run the real sensor decoder,
queue and screen renderer, but the sensor and successful upload are simulated.

## Replay many scenarios at once

I built a parallel mode for the desk-node replay because I run a whole set of
sensor scenarios every time I change the firmware, and replaying them one after
another is slow. The replay now takes several scenario files and runs them on
several threads. A thread is a worker inside one program, so the workers can use
different processor cores at the same time. The program prints one summary line
per file, in the order I gave the files.

```sh
make -C replay
guile --no-auto-compile -L replay/scheme replay/compile.scm < replay/examples/outage.scm > replay/build/outage.wire
replay/build/desk-replay --jobs 4 replay/build/outage.wire replay/build/outage.wire
```

Each line is the same summary the single-file mode prints. `--jobs 1` runs
everything on one thread, and the output is byte-for-byte the same for any number
of threads. The tests run 240 jobs at 2 to 64 threads and compare every byte.
If one file is bad, the program prints the first bad file's name and reason to the
error output, prints nothing else, and exits with an error.

The main thread reads each file into one of eight slots in a block of shared
memory. Workers take the next file in order, replay it, and keep their results in
their own lists. At the end the results are put back in file order and printed.
One mutex, which is a lock, and two condition variables, which let a thread wait
for a signal, keep two threads from touching the same slot at once.

On my Mac, 2000 copies of a 4,095-sample scenario took 0.17 seconds on one thread,
0.08 seconds on two and 0.04 seconds on four. Past four threads, the main thread's
file reading is the likely limit. The parallel mode prints only the summaries. The
screen image (`--pbm`) and UART log (`--uart-log`) still need the single-file
mode, and each file must be under 64 KiB.

CI builds the replay with ThreadSanitizer, which reports threads that touch
shared memory without a lock, and with AddressSanitizer, which reports bad memory
access. Both run in the sensor replay job on Linux and macOS. The locking rules,
the shared memory block and the reasons for each choice are in the
[threading design](docs/parallel-replay.md).

## Check a wire recording without a board

I use sigrok, a tool that reads logic-analyzer recordings, to decode the sensor
messages and serial output. On macOS, install `brew install sigrok-cli guile`;
on Ubuntu, use `sudo apt-get install sigrok-cli guile-3.0 build-essential`.
With Python 3.11 or newer, Make and a C compiler, run from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m capture.demo
.venv/bin/python -m capture.decode replay/build/captures/clean.sr
```

The demo generates clean and deliberately damaged recordings from the same sensor
scenarios and serial-log code used by the replay. Each clean recording gives one
25 C / 50% reading and 83 serial bytes with no findings. Each damaged recording
reports a rejected address, a missing acknowledgement clock, a bad sensor checksum,
an unfinished message and a serial framing error, meaning a missing stop bit.
The recordings and readable JSON reports are in `replay/build/captures/`.

For a real recording, run `.venv/bin/python -m capture.decode wake.sr --report report.json`.
The tool accepts sigrok `.sr` sessions and uniformly sampled CSV exports. The
[capture guide](docs/capture-decoding.md) covers recording pins, channel names,
sample rates, changing scenarios and reading fault locations. Generated captures
are synthetic; they do not establish that an assembled board works.

## Try the room-control demo

From the repository root, with Python 3.11 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r automation/requirements.txt
.venv/bin/python -m automation.gateway --demo
```

Leave that running and open another terminal in the same folder:

```sh
.venv/bin/python -m automation.check
```

The check prints the room readings, asks for heat, then lowers the target and
checks that heat and fan turn off. It restores the previous settings when done.
Press Ctrl-C in the first terminal to stop the demo and release its connections.
The outputs are simulated; they do not switch a heater or fan in my room.

Modbus TCP and BACnet/IP are two network protocols, or sets of rules for exchanging
readings and commands. This demo exposes the same readings and thermostat through
both. The [building-control guide](docs/building-automation.md) explains the point
addresses, how to connect the existing desk-node readings, and how these protocols
fit into heating, ventilation, air conditioning and electrical systems.

## Check noisy room readings

I use a moving median, the middle reading in a small sliding group, to remove
isolated spikes. A low-pass filter then keeps slow changes and reduces faster
ones. An FFT, a calculation that separates repeating changes by frequency, helps
me find interference that repeats at a regular interval.

The demo above makes a week's worth of five-minute readings with a known room
temperature, a faster unwanted cycle, random noise and occasional spikes. With
the default seed, the typical error falls from 0.5232 C to 0.1109 C after
filtering. The [short comparison report](docs/signal-analysis-report.md) includes
the raw and filtered errors and the detected noise frequencies. These are
software results against a simulator, not measurements of the physical sensor.

For a real adapter database, I choose one device and analyze a continuous stretch
of readings. The database opens read-only; the report goes into a new folder:

```sh
.venv/bin/python -m analysis --database room.sqlite3 --device desk-1 \
  --channel temperature --cutoff-hz 0.000277777778 --output analysis/build/room
```

This example keeps changes slower than roughly an hour and removes faster ones.
The [guide](docs/signal-analysis.md) covers choosing that boundary, humidity and
CSV input, missing readings, the estimated noise ratio and the filter's limits.
The filters run after collection; they do not change live readings or thermostat
commands. Five-minute logs cannot identify rapid electrical noise such as mains
hum, and smoothing can remove a real rapid change too.

## Rehearse a controller or connection fault

I can check the sensor's Bluetooth packet, Wi-Fi retry decisions and damaged
GPS or vehicle-data recordings on my computer. I can also run the C++ sensor
program on an emulated STM32 and follow a deliberately triggered processor
fault back to its instruction. The [embedded guide](docs/embedded-lab.md)
explains the commands, what each check means and what is simulated.

For a longer control experiment, my [controller rehearsal](robot_controller/)
records timing and sensor data while a simulated heater and two-joint arm run.
Its saved readings feed the same controller-message decoder above. The
[connection rehearsal](network_lab/) tries two delayed or interrupted upload
links and a radio waveform with a simulated frequency shift. Both run without
physical machinery or a paid cloud account.

I also keep a [water-probe board](hardware/leak/) and a
[light-input circuit calculation](hardware/simulation/report.md) here while I
learn how to extend the node. They include circuit checks and simulation plots;
neither circuit has been manufactured. The [Linux sensor experiment](linux_sensor/)
puts the same checked sensor bytes behind a device file inside an emulated ARM
computer. The [concurrent receiver](tcp_telemetry/) and
[port-switch service](optical_switch/) are separate local networking experiments.

## Plan the board and connections

I can compare the original USB board with a smaller battery design before
ordering either one. From this folder, with Python 3.11 or newer, run:

```sh
python3 -m power_budget.compare
```

It shows where current goes and estimates battery life. With the documented
example assumptions, calculated average input current falls from 11.960 mA to
6.715 mA. These are datasheet calculations, not measurements. The new
[48 × 54 mm battery board](hardware/revb/README.md) has a charger and a regulator
that uses less current itself. I still need to build it and fill in the
[bench measurement sheet](docs/power-and-battery.md#bench-sheet-intentionally-empty).
I also have an [antenna matching calculator](docs/antenna-matching.md) that reads
radio measurements and suggests small components to reduce reflections. Its
included example uses clearly labelled synthetic data; I have not measured an antenna.

I use a wiring plan for removable sensor and programming leads so I can cut
and label each wire and check it before powering the board. With Python 3.11 or
newer, I can make the documents without a board or extra packages:

```sh
python3 -m harness.check harness/example.json
python3 -m harness.generate harness/example.json --output harness/build
```

Open `harness/build/harness.svg` for the drawing and the CSV files for the cut
list, labels and continuity and polarity test sheet. The example covers the J2
sensor expansion and J3 programming header. The [harness guide](docs/harness.md)
explains how to change lengths and pin assignments and check the real wiring.

I also keep a purchasing record for the board so I can check replacements and
missing material declarations before ordering parts. It covers all 31 components,
with nine replacement candidates and a spreadsheet for an assembler. With
Python 3.11+, KiCad 8 and its command-line tools installed, I can try it without
a board or an account:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r hardware/components/requirements.txt
.venv/bin/python -m hardware.components --boards 10
```

Open `hardware/build/components/desk-node-cm.xlsx`, or download the
[example spreadsheet](hardware/components/review/desk-node-cm.xlsx). The
[parts guide](docs/components.md) shows how I load the same records into InvenTree,
a free parts manager, and explains the risk report. RoHS and REACH are rules about
restricted substances; missing manufacturer evidence stays marked unverified.
The replacement parts are candidates that still need board testing.

I can also check whether sudden jumps in the room log are likely to be noise.
The analysis tool smooths isolated spikes and faster variations, then shows which
repeating changes remain. To try it without a board, with Python 3.11 or newer,
run from this folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r analysis/requirements.txt
.venv/bin/python -m analysis.demo
```

Open `analysis/build/demo/report.md` for the comparison against known true
readings. The [analysis guide](docs/signal-analysis.md) shows how I use the same
filters on my saved room logs. All demo readings are generated on the computer.

I can also rehearse damaged controller messages before connecting a controller.
The recording tool turns bytes into temperatures and heater/fan commands, reports
missing or damaged messages and turns simulated outputs off when a check fails.
CAN is a wired message network; its FD variant carries longer messages. To try it:

```sh
python3 -m venv .venv
.venv/bin/pip install -r can_monitor/requirements.txt
.venv/bin/python -m can_monitor.replay --generate /tmp/desk-can.jsonl --faults
.venv/bin/python -m can_monitor.replay /tmp/desk-can.jsonl --tail 3
```

The [controller recording guide](docs/can-control.md) explains the errors,
message rates and Linux virtual network. These are simulated messages, including
a 64-byte CAN FD snapshot. My current desk board has no CAN transceiver.

For missing room logs, I can separately test delayed or lost network replies and
save sensor batches through an encrypted message broker. The
[connection guide](docs/network-monitoring.md) gives the demo commands, network
layout and alarm rules. The [charging model](power_budget/charging.py) adds a
calculated charge-time estimate to the existing battery budget.

## Parts and wiring

The controller is an ESP32-WROOM-32E, a small computer with Wi-Fi and 4 MB of
program storage. I use an OLED, a compact light-emitting screen, for the display.
SPI and I²C are the wired connections to the screen and sensor; UART is the
serial connection used to load the program and read logs. The firmware needs:

- An SHT31 temperature/humidity sensor at address `0x44`.
- An SSD1306 128 by 64 OLED module with a seven-pin, four-wire SPI connection.
- A regulated 3.3 V supply for the controller and peripherals, from USB desk power.
- A 3.3 V USB-to-UART adapter for flashing and reading the serial log.

The [wiring guide](docs/pinout.md) gives the exact pins, power requirements and
pull-up resistors. A four-pin I²C OLED is a different variant; select the legacy
display option explicitly if using that wiring. Do not connect both displays.
The OLED stays powered while the ESP32 sleeps. Rev A uses USB desk power;
Rev B adds a battery option while retaining that display behavior. Neither has
a measured battery-life claim.

## Circuit board

I designed the [board](hardware/) to hold the controller, temperature and humidity
sensor, and USB-C power supply. The screen plugs into it. A separate USB-to-UART
adapter loads the firmware and lets me read its logs. The
[board guide](hardware/README.md) explains the connections, parts and files needed to order or build one. This version has not been manufactured yet.

## Build and flash

Install [ESP-IDF v5.4.2](https://docs.espressif.com/projects/esp-idf/en/v5.4.2/esp32/get-started/index.html)
with its ESP32 toolchain, the tools for building and loading the device program.
In an activated ESP-IDF shell, from this checkout:

```sh
cd firmware
idf.py set-target esp32
idf.py menuconfig
idf.py build
idf.py -p /dev/cu.YOUR_USB_UART flash monitor
```

In menuconfig, open LifeOS Desk Node and choose the display, Wi-Fi settings,
service address and device token. Replace the example serial port with the adapter's
port. The [firmware guide](firmware/README.md#build-and-flash) covers programming
mode, serial logging and configuration. Configured binaries contain the Wi-Fi
credentials and token; keep them and `sdkconfig` private.

## Connecting it to LifeOS

The ESP32 talks to the included [API adapter](firmware/tools/desk_api.py), a
small service that translates requests between the device and LifeOS. An API
is the set of requests programs use to communicate. The adapter needs Python
3.9 or newer and stores readings in SQLite, a database kept in a local file.
Follow the
[adapter setup](firmware/README.md#lifeos-api-adapter) to create a private device
token, try the isolated demo and then configure a real LifeOS connection.

Demo mode uses fictional events and never contacts LifeOS. Its default address,
`127.0.0.1:8091`, is for trying it on the computer. For the desk device, use a
network-reachable address and the HTTPS setup in the guide. HTTPS encrypts
the connection and checks the server's identity. Keep LifeOS account
credentials on the computer, not on the microcontroller.

The adapter picks the earliest upcoming school event or task deadline visible
through LifeOS. A date-only deadline says that its time is unknown. Readings go
into new daily notes named `Desk room <day> <device>`. Retries do not duplicate
readings, and edits to a managed note's text stop syncing rather than overwrite
the edit.

## When the connection is down

The screen keeps the last fetched event and marks it offline, so it can be stale.
Up to 64 readings wait for upload across sleep cycles. If that fills, the oldest
reading is dropped and the screen shows a loss count. Turning the power off loses
those pending readings; they are not saved to flash. Invalid sensor readings
are not turned into made-up values.

## Check the case before printing

I built a set of simulations for the case because I wanted to know whether it fits the board and survives being knocked before I print it. The scripts in [mechanical/](mechanical/README.md) draw the case from its dimensions, load it on a computer the way a lid screw or a drop would, and report the peak stress, how far it bends and its safety factor against yielding. A second script adds up the size errors of the board, the standoffs and the printed case to check the screw fit.

The first run found one thing to change: with the 3.2 mm mounting holes on my board, an M3 screw misses the worst-case fit by 0.115 mm, and a 3.5 mm hole passes. The numbers are in [mechanical/docs/study.md](mechanical/docs/study.md), and the setup steps are in the [mechanical README](mechanical/README.md). The checks run in GitHub Actions on every change to that folder.

## Checks and remaining hardware work

Run the software tests from the repository root:

```sh
python3 -m unittest discover -s harness/tests -v
firmware/tests/run_host_tests.sh
make -C replay test
.venv/bin/python -m unittest discover -s automation/tests -v
.venv/bin/python -m pip install -r capture/requirements-dev.txt
.venv/bin/python -m pytest capture/tests -q
.venv/bin/python -m pip install -r analysis/requirements-dev.txt
.venv/bin/python -m pytest analysis/tests -q
```

The harness suite checks seven example wires and rejects duplicate pins, missing grounds and undersized wire. These run on a computer without an ESP32 toolchain. Continuous integration (CI), the
automated checks on GitHub, also builds the default SPI and legacy I²C display
firmware. The replay checks run Scheme scenarios and the C program on Linux and
macOS, checking for invalid memory access, data races between threads, and the
expected results.
The room-control tests use actual local network connections and need no
hardware. Neither suite proves that a physical board or HVAC system works.
The capture suite adds 36 pytest cases using the real sigrok decoders, including
clean and damaged I2C/UART recordings in both file formats. Its CI jobs run on
Python 3.11 and 3.12 and save generated captures and reports for inspection.
The analysis suite checks filter gain at the chosen cutoff, known FFT tones,
spike rejection, power normalization, log imports and report commands. Its CI
jobs run on Python 3.11 and 3.12, reproduce the comparison report and save the
synthetic samples and spectra as downloadable files.
The component database adds 47 tests for the actual parts catalogue, BOM parsing,
internal numbering, alternate screening, missing evidence, placement identities
and the Excel handoff. Its CI job loads the pinned InvenTree database twice,
reads the stored values back through the API and checks for duplicate records.
The [bench checklist](firmware/README.md#tests-and-hardware-validation) covers
wiring, screen output, reconnects, sensor faults and measured current.
[Design notes](firmware/docs/design.md), the [device API](firmware/docs/api.md)
and [validation notes](firmware/docs/validation.md) explain the software behavior
and what remains unverified.

The battery and antenna tools add 28 checks for charge integration, firmware
sleep timing, runtime units, invalid inputs, independently calculated circuit
impedances, matching across the whole band, Touchstone formats, rounded values,
component tolerances, battery-jumper wiring and actual board size:

```sh
.venv/bin/python -m pip install -r antenna_matching/requirements.txt pytest==8.3.5
.venv/bin/python -m pytest power_budget/tests antenna_matching/tests hardware/revb/tests -q
hardware/revb/check.sh
```

CI checks both native KiCad boards with no ignored ERC/DRC violations and uploads
fabrication outputs. A separate calculation job runs on Python 3.11 and 3.12 and
saves the power report and predicted radio-reflection sweeps. These checks cover
the design and calculations; current, runtime, charging and radio performance
remain unmeasured.


## Other things I've built here

- [bms-hil-test-bench](projects/bms-hil-test-bench/)
- [calculix-bracket-fea](projects/calculix-bracket-fea/)
- [freecad-design-tools](projects/freecad-design-tools/)
- [gcode-toolpath-generator](projects/gcode-toolpath-generator/)
- [optical-link-test-analysis](projects/optical-link-test-analysis/)
- [optical-link-test-automation](projects/optical-link-test-automation/)
- [pdn-impedance-ngspice](projects/pdn-impedance-ngspice/)
- [rf-measurement-analysis](projects/rf-measurement-analysis/)
- [scheme-in-c](projects/scheme-in-c/)
- [semiconductor-process-doe](projects/semiconductor-process-doe/)
- [solidworks-enclosure-tools](projects/solidworks-enclosure-tools/)
- [submeter-accuracy-bench](projects/submeter-accuracy-bench/)
- [vue-electron-results-viewer](projects/vue-electron-results-viewer/)

- [three-phase-fault-analysis](projects/three-phase-fault-analysis/)
- [air-core-reactor-calculator](projects/air-core-reactor-calculator/)

- [pll-verification-testbench](projects/pll-verification-testbench/)

The new controller, link, packet, driver and circuit checks are described with
exact commands in their linked guides. Linux CI exercises the actual virtual
CAN interface, SNMP agent, encrypted broker, isolated firewall, ARM firmware and
kernel images. Host simulations never stand in for a manufactured-board result.

For a full local Python regression, I install the combined host dependencies and
build the three small programs used by its socket and replay tests. I need a C/C++
compiler and Make, plus the Guile and sigrok tools described above. The circuit
tests run when the KiCad and ngspice command-line tools are installed:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
make -C replay
make -C optical_switch test
.venv/bin/cmake -S tcp_telemetry -B tcp_telemetry/build
.venv/bin/cmake --build tcp_telemetry/build -j2
.venv/bin/python -m pytest -q
```

The checked local run passed 298 tests, with seven Linux integration cases reserved for CI.
The shared C/C++ Google Test runner passed ten cases under sanitizers; the alert
runner checks all 35 state/event pairs plus debounce and a seeded replay.
