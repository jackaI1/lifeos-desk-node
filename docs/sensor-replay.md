# Replaying sensor readings

I use this when I want to reproduce a queue or display problem without waiting
for a real sensor or Wi-Fi outage. The scenario generator runs in Scheme through
Guile 3; the replay executable is C11 and links the same `desk_core.c` used by
the ESP32. Neither program connects to LifeOS or opens a network port.

## A first run

Install Guile 3, Make and a C compiler. On macOS I use `brew install guile` and
the command-line developer tools; on Ubuntu I use
`sudo apt-get install guile-3.0 build-essential`. From the repository root:

```sh
make -C replay
guile --no-auto-compile -L replay/scheme replay/compile.scm < replay/examples/outage.scm > replay/build/outage.wire
replay/build/desk-replay --pbm replay/build/screen.pbm < replay/build/outage.wire
```

The summary is:

```json
{"samples":70,"faults":1,"uploaded":64,"queued":0,"dropped":6,"oldest":0,"newest":0,"temperature_mc":null,"humidity_mpermil":null}
```

There is no live server here. An upload command means that all queued readings
receive a simulated successful acknowledgement and are removed. The six oldest
readings have already been lost, because the real queue holds only 64. The last
sample has a broken checksum, so the latest temperature and humidity are unknown.
Old queued readings are retained until upload; a fault never creates a reading.

`screen.pbm` is a Portable Bitmap, a simple image format. I can open it in an
image editor that supports PBM or convert it with ImageMagick, if installed:

```sh
magick replay/build/screen.pbm -scale 400% replay/build/screen.png
```

The image comes from the actual 128 by 64 pixel screen buffer, with a fixed
fictional event named Sensor replay. Only the final screen is saved. Nothing is
sent to a physical display.

## My own scenario

I save a text file with one `scenario` and run the same commands with that file
as the compiler input. A semicolon starts a comment. For example:

```scheme
(scenario
  (repeat 3
    (sample 21500 45000)
    (sample 23000 50000))
  (upload)
  (fault 25000 50000)
  (sample -500 60000))
```

- `sample` takes temperature in thousandths of a degree Celsius and humidity in
  thousandths of one percent. `21500 45000` means 21.5 C and 45% relative humidity.
- `fault` takes the same values but damages the temperature checksum, the small
  error-detection number attached to a sensor reading.
- `repeat` repeats its entire body in order, including any nested repeats.
- `upload` simulates acknowledging the current queue. Samples accumulate offline
  until the next upload. The screen says updated after an upload and offline after
  a sample; these are replay states, not measurements of a network connection.

The summary counts accepted samples and rejected faults separately. Sequence
numbers advance only for accepted samples; `oldest` and `newest` show the queued
range, or zero when empty. Counters reset on every invocation. Sensor numbers can
move slightly after conversion to and from the sensor's 16-bit wire format:
50% humidity becomes 50001 rather than 50000 in the known test vector.

## Boundaries and design

The compiler reads data with Scheme's `read`, never `eval` or `load`. It accepts
only `scenario`, `sample`, `fault`, `repeat` and `upload`, validates the complete
expansion before writing, and rejects extra top-level expressions. Values must
be exact integers. The temperature range is -45000 through 130000 and humidity
is 0 through 100000, representing the sensor encoding range rather than a claim
that every physical sensor is accurate across it. Input is limited to 65536
characters, eight nested repeats and 4096 expanded commands.

Scheme converts physical values to 16-bit sensor words with integer rounding.
It computes each CRC-8, an eight-bit checksum, with polynomial `0x31` and initial
value `0xff`. The C decoder checks those independently. A known 25 C / 50% vector
is `66 66 93 80 00 a2`; the lower and upper encoding limits have separate tests.

The intermediate text starts with `DESK_REPLAY_V1`. Each following line is either
`S ` and exactly 12 hex digits for six sensor bytes, or `U`. Lines use LF and the
last newline is optional. The C parser independently enforces the command limit,
rejects malformed or hidden NUL data, and keeps all state in bounded storage.
It uses `desk_decode_sht31`, `desk_ring_push`, `desk_ring_pop` and `desk_render`
directly instead of reimplementing their behavior. The bitmap exporter translates
the display's vertical eight-pixel pages into ordinary image rows.

This tool does not exercise I²C timing, HTTP uploads, real Wi-Fi reconnects,
deep-sleep retention or screen electronics. It provides deterministic inputs for
the shared C logic. It does not change the device firmware or add a Scheme
runtime to the ESP32.

## Checks

```sh
make -C replay test
firmware/tests/run_host_tests.sh
```

The first command runs 32 Scheme assertions and 12 Python integration tests that
launch the actual Scheme compiler and C executable. The C build uses address and
undefined-behavior sanitizers, which catch invalid memory access and certain
invalid operations. Tests cover repeat order and limits, known sensor bytes,
queue loss and recovery, malformed input, missing output paths, and the exact
pixel orientation of the screen image. Temporary test executables are deleted
on exit. GitHub runs this pipeline on Linux and macOS and saves the example wire
data and screen image as downloadable build artifacts. `make -C replay clean`
removes the local build output; neither command leaves a server running.
