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

## Check the power-up on a bench

I built a bench check because I need the same power-up measurements every time I change the board, and I want them written down. The script drives a programmable power supply and an oscilloscope. It sets the 5 V input, turns it on, and records the ripple on the 3.3 V regulator's output (the small repeating wiggle on a supply line) and how long after the 5 V input that output comes up. It also reads how much current the board draws. Each result is compared with a limit in a text file, and each run is saved in a folder named with the time it ran.

I don't have the lab instruments here, so the check runs against simulated ones. It sends SCPI, the standard text commands most bench supplies and scopes use, through PyVISA, a Python library that talks to instruments. A second library, pyvisa-sim, answers those commands from a file that describes a simple board. To run it:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r bench/requirements.txt
.venv/bin/python -m bench
.venv/bin/python -m bench --inject ripple
```

The first run passes all five checks: 8 mVpp of ripple (limit 30), a 1.5 ms delay for the regulator (limit 0.2 to 10 ms) and 60 mA of input current (limit 150 mA). The `--inject` option adds a fault to the simulated board. `ripple` adds 60 mVpp, and `late-rail` starts the regulator 14 ms late. Each fault fails the check it targets and nothing else, and the tests check that. Each run writes a CSV of measurements, a CSV of the captured waveforms and a short report into `bench/build/runs/`. The limits in `bench/limits.toml` are bring-up targets I picked, not datasheet numbers. The [bench guide](docs/bench-automation.md) covers the commands, how the simulator models the board and how to point the script at real instruments.

## Export the light-input circuit for OrCAD

I built an OrCAD export because I wanted to learn Cadence OrCAD, a circuit
design and simulation program that many electronics teams use. My light-input
circuit is in KiCad, so I wrote a script that turns it into an OrCAD PSpice
netlist. A netlist is a plain text file that lists each part and the points it
connects to. The script takes the feedback resistor and capacitor values from the
KiCad drawing, so the netlist cannot drift from the drawing. It also refuses to
write a netlist if those two parts are not wired to the amplifier's output and
input pins.

To check the file, the script runs it in ngspice, a free simulator that runs on
my Mac. It runs DC, frequency and time-step analyses from the same file and
compares the results with my hand calculations.

```sh
python3 -m hardware.simulation.orcad --out hardware/simulation/build/orcad
```

This needs `kicad-cli` and `ngspice` installed. It writes `light-front-end.cir`,
the OrCAD netlist, and `check.json`, the measured results. On my last local run
the gain was 99,999 ohms, the bandwidth was 16.8 kHz against a hand value of
15.9 kHz, and the step settled at 1.74998 V. The [circuit report](hardware/simulation/report.md)
explains what the model leaves out. OrCAD is a desktop program, and I have not
opened this netlist in it yet, so the checks I have are the ngspice run and the
tests in `hardware/simulation/tests/test_orcad.py`.

Syntax note: the two behavioral sources (the supply reference and the output
clamp) are written as PSpice `VALUE {...}` cards, not the `V=` form that ngspice
accepts on its own. PSpice does not read `V=`, so I changed them. The tests check
the card shapes, but no PSpice program has read the file yet, so importing it into
OrCAD is still the next step.

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

## Read the room sensor from my phone

I added Bluetooth Low Energy to the desk node because I wanted to read the room temperature and humidity from my phone without needing Wi-Fi. Bluetooth Low Energy is a short-range radio that uses very little power. The desk node now advertises as `Desk room sensor`, so my phone can find it, connect and read the latest values. The default build leaves Bluetooth out, so existing builds work as before.

After each wake, the node takes its usual reading, uploads it over Wi-Fi as before, and then keeps Bluetooth on for a short window, 30 seconds by default. While a phone is connected, the node reads the sensor again every 10 seconds. It sends a notification only when the temperature has moved by 0.1 °C or the humidity by 0.5 %, and never more than one every 10 seconds. When the window ends, the radio shuts off until the next wake.

The values use the standard Environmental Sensing service from the Bluetooth standards group, so any generic Bluetooth app can read them. The firmware uses NimBLE, the small Bluetooth stack that ships with ESP-IDF, the official ESP32 software kit. Temperature is a signed 16-bit number in hundredths of a degree (characteristic `0x2A6E`). Humidity is an unsigned 16-bit number in hundredths of a percent (`0x2A6F`). The encoding and the notification rule are plain C in [`firmware/components/desk_ess`](firmware/components/desk_ess/). The host tests in [`firmware/tests/test_ess.c`](firmware/tests/test_ess.c) run them under AddressSanitizer and UBSan, with out-of-range values and bad checksums included: 37 checks.

How to try it:

1. Build the Bluetooth version with `idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.ble.defaults" set-target esp32`, then `idf.py build` and flash it.
2. On a phone, open nRF Connect (a free Bluetooth scanner app), scan, and tap `Desk room sensor` within 30 seconds of a wake. The node wakes every 5 minutes by default.
3. Read the temperature characteristic (`0x2A6E`). It shows two bytes such as `59 08`. Decode them with `python3 firmware/tools/ess_decode.py temperature "59 08"`, which prints `21.37 degC`.

The phone only sees the node during the window after each wake. It is not a live stream. A shorter sleep interval gives more windows but uses more power. I have not run this on a real board yet. CI builds the Bluetooth version next to the default one, and runs the encoder tests on every push. The [firmware README](firmware/README.md#bluetooth-low-energy-optional-build) has the build details.

## Send readings over a wired CAN link

I built a wired CAN link for the desk node because Wi-Fi drops, and when it does I lose the room readings until it comes back. CAN is a wired message bus: devices share two wires, and each short message reaches every device on the bus. The node sends its latest temperature, humidity and fault flags once per wake cycle, using the ESP32's built-in CAN controller. A second device on the bus, or my laptop with a recording, can read them later.

The analyzer reads a recorded CAN log and flags what I care about: a gap in the heartbeat (the regular message that shows the node is alive), values outside the range the message layout allows, the node's own sensor and queue fault flags, and bus-off, when the controller stops sending because too many of its messages failed. It runs on a computer with no board attached:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r can_monitor/requirements.txt
.venv/bin/python -m can_monitor.analyze can_monitor/examples/candump/desk_node_clean.log
.venv/bin/python -m can_monitor.analyze can_monitor/examples/candump/desk_node_faults.log
```

The clean log passes. The second file is the same log with damage I added on purpose: 10 readings missing, a humidity of 105 %, a sensor fault, a bus-off event, a damaged line and a time that goes backwards. The analyzer reports each one and exits with status 1. Both logs come from a simulated node on a virtual bus, not from a real board. The [CAN guide](docs/can-log-analysis.md) lists every finding, the byte layout and the firmware switch (`CONFIG_DESK_CAN_ENABLE`). The desk board has no CAN transceiver yet, so the link has not run on a real bus. CI builds the firmware with the CAN link enabled, runs the C encoder tests, and checks the same bytes against the message file in Python.

## Check the case before printing

I built a set of simulations for the case because I wanted to know whether it fits the board and survives being knocked before I print it. The scripts in [mechanical/](mechanical/README.md) draw the case from its dimensions, load it on a computer the way a lid screw or a drop would, and report the peak stress, how far it bends and its safety factor against yielding. A second script adds up the size errors of the board, the standoffs and the printed case to check the screw fit.

The first run found one thing to change: with the 3.2 mm mounting holes on my board, an M3 screw misses the worst-case fit by 0.115 mm, and a 3.5 mm hole passes. The numbers are in [mechanical/docs/study.md](mechanical/docs/study.md), and the setup steps are in the [mechanical README](mechanical/README.md). The checks run in GitHub Actions on every change to that folder.

## Check my room readings for odd values

I built a small anomaly check for the temperature and humidity readings because I want the desk node to notice a sensor spike or a stuck value itself, before it reaches my room log. A small neural network learns what a normal reading looks like from a log, and a window of four readings gets a high score when it looks wrong. I shrank the model to eight-bit integers, so it could run on the ESP32 later. The C code uses only integer arithmetic.

On a simulated log with known faults, the eight-bit model gets the same accuracy as the full-precision model (0.968 on the held-out part), agrees with it on 99.56 % of windows, and uses 223 bytes for its weights instead of 592. It catches spikes, humidity jumps and dropouts every time. It misses stuck readings, because four identical values look like a calm room. The [anomaly README](anomaly_int8/README.md) has the numbers and the per-layer scales, and [anomaly_int8/docs/results.md](anomaly_int8/docs/results.md) has the full report. To run it:

```sh
cd anomaly_int8 && python3 -m venv .venv && . .venv/bin/activate
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.9.1 && python -m pip install -r requirements.txt
python -m pytest && python -m anomaly_int8 run
```

## Check the sensor checksum in hardware

The sensor sends a checksum with each reading, and the firmware throws away readings whose checksum does not match. I wrote the same check as logic blocks in Verilog, the language that describes chips and FPGAs, because a hardware version is one option for the sensor path later. The blocks are tested in simulation against the same scenario files the firmware tests use, including the ones with deliberately corrupted checksums. The [rtl README](rtl/README.md) explains each block.

The word checker agrees with the replay tool on all 2,204 words I tested, and the reading buffer's built-in self-test finds all 512 memory stuck-at faults I injected, and all 22 scan-chain faults. The sensor path also maps onto 588 LUT4 cells and 440 flip-flops in Yosys for an iCE40 FPGA.

```sh
cd rtl && python3 -m venv .venv && . .venv/bin/activate && python -m pip install -r requirements.txt
make test PY=python3     # lint, cocotb frame tests, Verilator benches, cross-checks
make synth               # FPGA-style synthesis and logic depth
```

## Place and route the sensor block

I ran the sensor block through OpenROAD, an open-source chip design flow, to check that it can run at the speeds I would need for a chip or an FPGA version of the sensor path. The flow does synthesis, placement and routing on the open Nangate45 cell library. I swept the clock period and the core utilization and recorded the timing slack, area and power for each run. Every run meets timing, the tightest at 1.2 ns with 0.080 ns to spare, and CI fails if the chosen 1.2 ns constraint ever stops closing. The table and the commands are in [rtl/README.md](rtl/README.md) and [rtl/docs/openroad-sweep.md](rtl/docs/openroad-sweep.md).

## Run the sensor check on an FPGA board

I wanted the sensor checksum logic to run on a real FPGA, a chip you can reprogram, and not only in a simulator. The sensor check in `rtl/` is written in Verilog, so I added a board version of it for the iCEBreaker, a small board with an iCE40 UltraPlus FPGA, a 12 MHz clock and a USB serial port. Its FPGA is one of the open-source chip families, so I can build the program for it with free tools.

The computer sends sensor bytes over the USB serial port. Each transfer starts with a length byte, then the bytes. The board checks each six-byte frame in the same hardware block as before, keeps the good ones and sends back six bytes with the good, bad and cut-short counts. The green LED is on while a transfer is arriving. The red LED comes on after any bad or cut-short frame.

```sh
cd rtl && python3 -m venv .venv && . .venv/bin/activate && python -m pip install pyserial
python3 board/icebreaker/host.py --port /dev/tty.usbserial-XXXX --demo
```

Replace the port with the one your computer shows for the board. The demo sends one good frame, one frame with a wrong checksum and one cut-short frame. The counts are running totals, so the three lines should read `good=1 bad=0 truncated=0`, then `good=1 bad=1 truncated=0`, then `good=1 bad=1 truncated=1`. I have not yet flashed an assembled board from this build; the FPGA file is built and checked in CI, and the simulation runs the same logic the board runs.

The FPGA top level is `rtl/board/icebreaker/desk_board_top.v`. It reuses the frame checker and reading buffer from `rtl/src/`, and two small serial blocks, `uart_rx.v` and `uart_tx.v`, which receive and send bytes at 115200 baud. The pin file `icebreaker.pcf` maps the clock, serial lines and LEDs to the board's pins. A Verilator testbench (`rtl/tests/verilator/board_tb.cpp`) plays the computer side: it sends six transfers, including a zero length byte, a cut-short frame and two frames in one transfer, and checks every reply and the LEDs. CI runs that testbench on macOS, and a separate Ubuntu job runs Yosys, nextpnr and icepack to build the bitstream and fails if the design misses the 12 MHz clock. The [rtl README](rtl/README.md) has the register-level details and the pin list.

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

The anomaly detector runs 23 pytest checks, including the C routine against the Python reference. The RTL folder runs its cocotb and Verilator benches and the replay cross-checks, and CI runs them on macOS.

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


The CAN log analyzer adds 45 pytest checks, covering the candump reader, every finding, the simulator's output and the byte vectors the firmware test uses. The whole CAN folder runs 80 tests, and one Linux-only socket test is skipped on macOS. The bench check adds 36 tests for the limit logic, the simulated runs and the command-line exit codes:

```sh
.venv/bin/python -m pytest can_monitor/tests -q
.venv/bin/python -m pip install -r bench/requirements.txt
.venv/bin/python -m pytest bench/tests -q
```

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
