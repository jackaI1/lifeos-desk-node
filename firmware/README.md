# LifeOS desk-node firmware

ESP-IDF **v5.4.2**, embedded C, target **esp32**, ESP32-WROOM-32E (4 MB).
SHT31 uses I²C; SSD1306 128×64 OLED uses 4-wire SPI by default. UART0 emits
cycle diagnostics at 115200 baud. The original I²C OLED remains selectable in menuconfig. Follow [the pinout contract](../docs/pinout.md)
for exact wiring, pull-ups, programming and power assumptions.

## What runs

Each timer wake reads temperature/RH in a FreeRTOS sensor task, queues the reading,
and launches a separate Wi-Fi/API task. The coordinator owns the FIFO and cached
event, renders the display, shuts down Wi-Fi/I²C/SPI, drains UART output and enters timer deep sleep.
There is no concurrent mutation of the retained FIFO. Defaults:

| Item | Bound |
| --- | --- |
| Sleep interval | 300 s after each cycle |
| Offline FIFO | 64 readings (about 5 h at default interval) |
| Wi-Fi join | 15 s, at most 3 connection attempts |
| Initial time sync | 5 s |
| HTTP operation timeout | 5 s; 90 s outer network cycle deadline |
| Sensor I²C transaction | 100 ms; sample task deadline 2 s |
| HTTP response / batch | 2 KiB / 12 KiB |
| Display frame | 1024 bytes, 21 characters × 8 rows |

CRC failures do not enqueue fabricated readings. A full FIFO drops the oldest
sample and increments `LOST` on screen. Only a matching full-batch acknowledgment
removes samples. A reset/power loss loses RTC readings; this is not flash-backed
storage. A new boot uses a new session ID. A sample with unknown UTC has timestamp
`0`, and the adapter marks it unsynchronized. Successful SNTP sets RTC time for
later wakes; it does not rewrite unknown earlier sample timestamps.

An API failure preserves the cached event and marks the screen `OFFLINE`. Its time
is the last fetched schedule, so it may be stale. A successful empty response
clears the previous event. The uppercase ASCII font substitutes `?` for unsupported
characters and clips titles after 63 characters. OLED stays on during deep sleep;
this design is intended for USB desk power. See the pinout's estimated power budget.

## Build and flash

Install [ESP-IDF v5.4.2](https://docs.espressif.com/projects/esp-idf/en/v5.4.2/esp32/get-started/index.html)
with the ESP32 toolchain, then in an activated IDF shell:

```sh
cd firmware
idf.py set-target esp32
idf.py menuconfig  # LifeOS Desk Node: display interface, SSID, password, API origin/token
idf.py build
idf.py -p /dev/cu.YOUR_USB_UART flash monitor
```

Default display is the revision 2 seven-pin **SPI** module on J4: SCLK18, MOSI23,
RESET25, D/C26, CS27, plus 3V3 and GND. A four-pin I²C module is not a substitute;
select **Legacy I2C** explicitly for the earlier J2 wiring. Never wire both display
variants at once. SPI uses mode 0, 4 MHz, MSB first, no MISO. Hardware pull-ups on
CS/RESET and pull-down on D/C preserve the display frame during CPU sleep.

UART0 uses TX GPIO1 and RX GPIO3, **115200 8N1**, no flow control. The firmware
installs the IDF UART driver, routes console logging through it, sends structured
sample/FIFO/API diagnostics, and waits up to 250 ms for TX completion before sleep.
A typical cycle line is:

```text
desk sample=42 utc=0 temp_mc=22500 rh_mpermil=45000 queued=1 lost=0 upload=pending
```

Values are integer milli-degrees C and thousandths of a percent RH, matching the
API; UTC zero means unsynchronized. No schedule titles, Wi-Fi credentials or API
tokens are logged. Connect J3 TX to a **3.3 V** USB–UART adapter RX and share GND.
USB-C on the PCB supplies power only and does not carry this serial console.

Hold BOOT and reset for UART download mode if needed. Use a 3.3 V USB–UART adapter.
The API origin has no trailing slash and points at the adapter below. HTTPS uses
the ESP certificate bundle and hostname checks; redirects are rejected. For a
private CA, add its root through ESP-IDF's custom certificate bundle configuration.
For isolated LAN demo only, enable `DESK_ALLOW_HTTP` explicitly. SNTP requires
network access (or configure an accessible SNTP server); valid time is needed for
TLS validation. SSID length ≤32, password ≤63, device token 32–128 URL-safe characters.

`sdkconfig`, local builds, SQLite logs and `.env` are ignored. Wi-Fi credentials and
the device token are compiled into local binaries: **never publish configured
binaries or sdkconfig**. CI uses public synthetic compile-only settings to retain Wi-Fi/TLS paths;
its artifacts require
local configuration/rebuild before deployment. It never connects to an account.

Reproduce the default SPI CI build with Docker (substitute `sdkconfig.i2c.defaults`
for the legacy variant; no server launched):

```sh
docker run --rm -v "$PWD:/project" -w /project/firmware espressif/idf:v5.4.2 \
  bash -c '. "$IDF_PATH/export.sh" && idf.py -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.ci.defaults;sdkconfig.spi.defaults" set-target esp32 && idf.py build && idf.py size'
```

## LifeOS API adapter

LifeOS currently exposes `/api/bootstrap`, `/api/session`, and versioned
`/api/private-notes/<id>` rather than a native room sensor endpoint. The bundled
[adapter](tools/desk_api.py) translates those APIs to [the small device contract](docs/api.md).
It selects the earliest future school calendar event or task deadline. Date-only
deadlines say `time unknown`, not an invented cutoff. Bootstrap's calendar window
is limited by LifeOS; this adapter does not expand recurring events itself.

Run it with Python 3.9+ (IANA timezone database required). In a private directory
outside this public checkout, create a URL-safe random token file (32–128
characters) with mode 600. Set `DESK_TOKEN_FILE` to that path. The same token goes
in local ESP32 menuconfig. Start with the isolated demo:

```sh
export DESK_TOKEN_FILE=/absolute/private/path/desk-token
python3 firmware/tools/desk_api.py --demo --database /absolute/private/path/demo.sqlite3
```

It prints its PID, start time, port and exact termination command. Default bind is
loopback port 8091; Ctrl-C / SIGTERM closes the listener and database. Demo mode uses
synthetic events and an in-memory LifeOS note store; its SQLite readings persist,
but demo notes do not. No LifeOS request occurs in demo mode.

For real LifeOS, set `LIFEOS_URL` to the HTTPS origin (loopback HTTP supported for
a local development instance) and `LIFEOS_COOKIE_FILE` to a private mode-600 file
containing the owner's existing authenticated Cookie header. The adapter fetches
CSRF from `/api/session`; cookies never leave that origin, and redirects are
rejected. Refresh the cookie file after the session expires. **Do not put the
LifeOS cookie on the microcontroller.** Omit `--demo`:

```sh
export LIFEOS_URL=https://YOUR_LIFEOS_HOST
export LIFEOS_COOKIE_FILE=/absolute/private/path/lifeos-cookie
python3 firmware/tools/desk_api.py --database /absolute/private/path/room.sqlite3
```

Expose the adapter through a configured HTTPS reverse proxy, or use `--host` plus
`--cert` and `--key` for direct TLS. For an isolated LAN demo only, use
`--host 0.0.0.0 --allow-http` together with firmware's explicit HTTP opt-in. This
transmits the device token in cleartext and is unsuitable for shared networks.
The API token authorizes only desk schedule reads and room reading ingestion;
keep the adapter private to your network. This task does not deploy a live service
or modify the owner's records.

The adapter commits incoming sample identities to SQLite before contacting LifeOS.
It writes **new dedicated daily notes** named `Desk room <day> <device>` through
the normal LifeOS API. A reading's device/session/sequence tuple deduplicates
retries, including restart and lost-response cases. A changed payload reusing an
identity is rejected. Acknowledgment is returned only after all relevant notes
reach LifeOS. Note writes use version checks and stable mutation IDs, retrying up
to three conflicts. Owner changes to title, folder, pin state and image attachments are preserved.
If an owner edits note text or document formatting, syncing refuses to overwrite it; export/preserve that note and resolve the managed note deliberately.
Do not delete the adapter database while continuing the same device history: it
contains dedup and generated-note ownership fingerprints. Back it up and monitor
its size. A day over 90 KiB stops uploads rather than silently truncating data;
increase the wake interval or split the deployment before that limit. Default
300-second sampling is about 288 readings/day plus active cycle time.

## Tests and hardware validation

```sh
firmware/tests/run_host_tests.sh
```

No ESP toolchain is needed for host tests. The script compiles the production C
core and shared SSD1306 protocol writer under strict warnings, AddressSanitizer and UBSan and runs Python adapter
unit/HTTP integration tests. Its temporary binary directory and owned HTTP test
socket are closed even on failure. Vendored cJSON v1.7.18 in `tests/vendor` is used
only by host tests with its MIT license; target builds use ESP-IDF's json component.

CI runs those tests and builds both SPI and legacy I²C variants of the complete firmware in the pinned ESP-IDF Docker
image, then uploads credential-free flash artifacts and reports firmware size.
No hardware is connected to CI. Before claiming physical operation:

1. Check 3V3, module/header orientation and SHT31 at I²C 0x44. Default SPI OLED
   has no I²C address; legacy I²C OLED is at 0x3C. Confirm J4 CS/RESET pulls.
2. Flash a locally configured build; confirm class/deadline, units, clipping and
   readability on the OLED against a synthetic LifeOS/demo fixture. Capture J4
   SCLK/MOSI/CS/D-C/RESET with a logic analyzer: mode 0 at 4 MHz, reset before
   commands, 1024 frame bytes with D/C high. Verify UART0 cycle lines at 115200
   8N1 and complete sleep diagnostics before TX goes idle.
3. Disconnect Wi-Fi for several wakes, restore it, and confirm FIFO upload without
   duplicate sample IDs. Test >64 wakes/shortened intervals to confirm loss count.
4. Remove the sensor/display in turn: other work must continue and deep sleep must
   still happen. Confirm CRC fault handling with a bus exerciser if available.
5. Verify a full power cycle clears RTC samples and gets a different session ID;
   timer wake retains them. Test expired token/certificate and unreachable API.
6. Measure active current, idle OLED current and cycle energy on the assembled
   board. Compare SHT31 with a reference away from MCU/regulator heat.

The test results establish software behavior and compilation, not physical sensor
accuracy, OLED appearance, Wi-Fi reliability or measured power draw.
