# LifeOS Desk Node

I built software for a small desk screen and room sensor because I wanted to see my next class and keep room readings in LifeOS.

## Overview

I want to glance at what's next without opening my calendar, and keep a record
of the conditions at my desk. This personal project puts a small OLED screen
and a temperature/humidity sensor beside me. The screen shows the next LifeOS
class or task deadline, along with the latest room reading.

The firmware wakes about every five minutes, reads the sensor and uses Wi-Fi to
fetch the next event and send readings to a small program running beside LifeOS.
That program saves them in dedicated daily room-log notes. Start with the parts
and build steps below. The hardware has not been bench-tested; screen operation,
sensor accuracy and power draw still need checking on an assembled device.

## Parts and wiring

The current firmware targets an ESP32-WROOM-32E with 4 MB flash. It needs:

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

The [board](hardware/) holds the controller, temperature and humidity sensor, and
USB-C power supply. A small screen plugs into it to show the next LifeOS class or
deadline. A separate USB-to-UART adapter loads the firmware and lets you read its
logs. The [board guide](hardware/README.md) explains the connections, parts and
files needed to order or build one. This version has not been manufactured yet.

## Build and flash

Install [ESP-IDF v5.4.2](https://docs.espressif.com/projects/esp-idf/en/v5.4.2/esp32/get-started/index.html)
with its ESP32 toolchain. In an activated ESP-IDF shell, from this checkout:

```sh
cd firmware
idf.py set-target esp32
idf.py menuconfig
idf.py build
idf.py -p /dev/cu.YOUR_USB_UART flash monitor
```

In menuconfig, open LifeOS Desk Node and choose the display, Wi-Fi settings,
API address and device token. Replace the example serial port with the adapter's
port. The [firmware guide](firmware/README.md#build-and-flash) covers programming
mode, serial logging and configuration. Configured binaries contain the Wi-Fi
credentials and token; keep them and `sdkconfig` private.

## Connecting it to LifeOS

The ESP32 talks to the included [API adapter](firmware/tools/desk_api.py), not
directly to the LifeOS account. The adapter needs Python 3.9 or newer and stores
its readings in a local SQLite file. Follow the
[adapter setup](firmware/README.md#lifeos-api-adapter) to create a private device
token, try the isolated demo and then configure a real LifeOS connection.

Demo mode uses fictional events and never contacts LifeOS. Its default address,
`127.0.0.1:8091`, is for trying it on the computer. For the desk device, use a
network-reachable address and the HTTPS setup in the guide. Keep LifeOS account
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
```

These run on a computer without an ESP32 toolchain. CI also builds the default
SPI and legacy I²C display firmware. Neither proves that a physical board works.
The [bench checklist](firmware/README.md#tests-and-hardware-validation) covers
wiring, screen output, reconnects, sensor faults and measured current.
[Design notes](firmware/docs/design.md), the [device API](firmware/docs/api.md)
and [validation notes](firmware/docs/validation.md) explain the software behavior
and what remains unverified.
