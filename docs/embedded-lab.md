# Rehearsing sensor and controller faults

I built these host and emulator checks because I wanted to learn what happens
when a sensor returns damaged data or a controller stops responding. They extend
the same desk-node sensor bytes, queue and replay format. They do not establish
that I have assembled or debugged a physical STM32 or ESP32 board.

## Reading a sample over Bluetooth

The ESP32 program starts a small Bluetooth Low Energy service for a valid sensor
sample during each wake window. It exposes a readable characteristic and sends
at most one notification per second when a client subscribes. The service uses
experimental UUIDs `FFF0` and `FFF1`; its client-configuration descriptor enables
notifications. The 16-byte payload contains version, flags, signed temperature in
millidegrees, humidity in thousandths of a percent, sequence and a CRC-16 checksum.
The BLE packet contains no calendar data. Deep sleep ends the connection, so a
phone must reconnect during the next wake window. It is not continuous streaming.

The existing Wi-Fi station path now uses the tested reconnect state machine,
with delays of 250, 500, 1000, 2000, 4000 and 8000 ms, then stops that wake's
attempts. A successful IP connection clears the retry count and logs RSSI, the
received signal strength. I use WPA2/WPA3 on the intended sensor network; the
actual access-point configuration has not been tested here. HTTPS certificate
checking and the offline reading queue remain in the existing upload path.
The larger two-megabyte application partition fits BLE alongside HTTPS in the
ESP32 module's four-megabyte flash. Flashing a changed partition layout requires
backing up any wanted device data first.

With the Python environment from the main README:

```sh
python3 -m firmware.tools.check_radio captured-radio.txt
firmware/tests/run_host_tests.sh
cmake -S host_tests -B host_tests/build -DCMAKE_BUILD_TYPE=Debug
cmake --build host_tests/build -j2
ctest --test-dir host_tests/build --output-on-failure
```

`captured-radio.txt` holds one hexadecimal BLE payload or one `WIFI connected
rssi=-65 attempts=3` line per row. The checker rejects wrong sizes, versions,
checksums and sensor ranges. The pure C encoder and retry logic used by the ESP32
also run inside the Google Test suite under AddressSanitizer and UBSan, which
check invalid memory use and undefined behaviour. The ESP-IDF CI builds both
display variants; it does not exercise a physical radio.

## The C replay and debugger

Google Test is the C++ test runner around the existing C core and replay parser.
It checks the real `replay/replay.c` line parser at its 79-character bound,
embedded zero bytes, sensor checksum corruption, FIFO overflow and response
buffer bounds. It also checks the new radio logic and vehicle-data parser.

```sh
ASAN_OPTIONS=detect_leaks=0 gdb -q -batch -x host_tests/checksum.gdb host_tests/build/replay-debug
```

I deliberately compile a separate `replay-debug` executable that aborts after
rejecting a bad-checksum sample. The script stops at that crash, finds the
`checksum_fault` stack frame and inspects the six received bytes and disassembly.
This is an injected debugging fixture, not an unhandled bug in normal replay.
LeakSanitizer is disabled only for this ptrace debugging session; memory checks
remain enabled for the ordinary tests.

## STM32 C++ firmware

I use a simulated STM32F4 in Renode, a command-line hardware emulator. The same
C++17 `Sensor` and `Logger` classes use small I2C and UART interfaces in both
host tests and the ARM firmware. I2C is the sensor's two-wire bus; UART is its
serial log. The STM32 adapter accesses the real emulated peripheral registers,
including bounded polling for transmit/receive flags and explicit NACK/timeout
returns. The sensor model returns SHT31 wire bytes with the same checksum as the
desk sensor. Host fake buses inject NACKs, timeouts and damaged CRC bytes.

With an ARM GCC toolchain, Renode 1.15.3 and `gdb-multiarch` on Linux:

```sh
make -C stm32 -j2
renode-test stm32/renode/firmware.robot --results-dir stm32/renode/results
stm32/renode/gdb-test.sh
```

`bare.elf` reads the sensor and waits for ten SysTick interrupts before reporting
success. `rtos.elf` executes that driver code in a FreeRTOS task, using static
task and stack storage. Both compile without exceptions, RTTI or dynamic task
allocation. Robot Framework asserts the actual emulated UART output for both
ELFs. The custom sensor is a simulation of bytes and protocol interaction, not
an electrical or conversion-time model.

The fault fixture executes the ARM `udf` instruction, an intentionally undefined
instruction. The hard-fault handler captures the stacked R0-R3, R12, LR, PC and
xPSR plus the fault-status registers. The scripted remote GDB session reads the
stacked PC, disassembles that address and requires it to be `udf`. CI archives
the ELF, UART assertions and GDB output. No desktop application is needed.

## Vehicle recordings and alert handling

The `telematics` C module reads checksummed GPS GGA/RMC sentences, which contain
position and fix information, and standard OBD-II replies for speed, engine RPM
and coolant temperature. NMEA fields, sentence length, coordinate ranges and
CAN response identifier/length are checked before results are returned. OBD-II
payloads have no application checksum of their own; a raw eight-byte input cannot
validate the CAN controller's on-wire CRC. I reject malformed service, PID and
length fields rather than invent that protection.

```sh
host_tests/build/telematics-replay < telematics/example.log
```

The example is a public standard NMEA example plus synthetic OBD bytes, not a
recording of Jack's movements or a real vehicle. The table-driven alert library
keeps warning and latched-fault states separate. Ignition must be off before a
clear request can start; a fault during its 500 ms debounce returns to the
latched state. A backwards clock or invalid event fails closed. The unit tests
cover all 35 state/event pairs and a seeded 10,000-event replay. The
[deviation notes](../vehicle_alert/deviations.md) explain the automated MISRA
subset check. This is not a MISRA compliance certification.

## Watching the same checks through Jenkins

Jenkins is a build server. Its declarative pipeline uses the same `make test`
and `make analyze` commands as GitHub Actions, publishes the unit-test result
and archives the static-analysis XML. On Linux with Docker Compose:

```sh
export JENKINS_ADMIN_PASSWORD='<choose a local demo password>'
docker compose -f vehicle_alert/compose.yml up --build -d
python3 vehicle_alert/jenkins/check.py
docker compose -f vehicle_alert/compose.yml down -v
```

The controller is accessible only at `http://127.0.0.1:8088`. Its job is loaded
as code and checks out this public repository. `DESK_BRANCH` selects another
branch for a rehearsal. CI starts the real controller, triggers the job and
requires `SUCCESS`, then deletes the container and volume even on failure.
This Mac has not hosted a Jenkins controller or pulled its container image.
