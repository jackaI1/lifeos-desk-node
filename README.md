# LifeOS Desk Node

I built a small desk display and room monitor because I wanted to see my next class at a glance and keep temperature and humidity readings in LifeOS.

## Overview

Instead of opening my calendar, I want to look beside my desk and see what
is next. This personal project brings together a small screen, a room sensor
and LifeOS, my planning system. The screen is designed to show the next class
or task deadline alongside the latest temperature and humidity.

The device program, called firmware, wakes about every five minutes. It reads
the sensor, fetches the next event over Wi-Fi and sends readings to a small
program running beside LifeOS. That program saves daily room-log notes. I have
software checks and a circuit-board design, but I have not bench-tested an
assembled device. Screen operation, sensor accuracy and power draw still need
physical checks.

Before connecting a sensor, I can rehearse a long outage on my computer. I write
a short list of pretend readings, run it through the same reading queue and screen
code used by the device, and see which readings survive. I can also save an image
of the screen. The replay below needs no board, LifeOS account or network service.

I can also use the room readings to try a thermostat on my computer. I choose a
target temperature, watch simulated heating and fan outputs respond, and read or
change settings through the same kinds of connections used in building controls.
The computer can simulate the room too, so I can try this part without a board or
a LifeOS account. Start with the commands below; the parts and flashing steps
follow for the physical desk display.

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
The OLED stays powered while the ESP32 sleeps, so this is intended for USB desk
power. No measured battery-life claim is available.

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

## Checks and remaining hardware work

Run the software tests from the repository root:

```sh
firmware/tests/run_host_tests.sh
make -C replay test
.venv/bin/python -m unittest discover -s automation/tests -v
```

These run on a computer without an ESP32 toolchain. Continuous integration (CI), the
automated checks on GitHub, also builds the default SPI and legacy I²C display
firmware. The replay checks run Scheme scenarios and the C program on Linux and
macOS, checking for invalid memory access as well as the expected results.
The room-control tests use actual local network connections and need no
hardware. Neither suite proves that a physical board or HVAC system works.
The [bench checklist](firmware/README.md#tests-and-hardware-validation) covers
wiring, screen output, reconnects, sensor faults and measured current.
[Design notes](firmware/docs/design.md), the [device API](firmware/docs/api.md)
and [validation notes](firmware/docs/validation.md) explain the software behavior
and what remains unverified.
