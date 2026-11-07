# A simulated sensor behind a Linux device file

I built a sensor device file because I wanted to learn how the desk sensor's
checked readings could reach a Linux program through a driver. A small C++
program reads it like a file, asks for its status and injects damaged samples
so I can see that an alarm stays set until I clear it.

The computer pretends to be the sensor bus and the sensor. The driver and the
program are real compiled ARM code running inside QEMU, a machine emulator.
No physical sensor, Raspberry Pi or private LifeOS data is involved.

On Linux, from the repository root:

```sh
sudo apt-get install build-essential bc bison flex libssl-dev libncurses-dev cpio unzip rsync wget qemu-system-arm device-tree-compiler
linux_sensor/tests/build.sh
```

This builds a pinned Buildroot 2024.02.9 ARM system and Linux 6.6.63 using the
Bootlin armv7-eabihf glibc stable 2023.11-1 compiler, then boots
it without a desktop. The serial log must contain `DESK_QEMU_PASS`. Building the kernel takes time and several gigabytes on Linux; GitHub Actions runs
this work so I do not fill the Mac with toolchains. Outputs are CI artifacts.

## How the driver fits together

`desk-overlay.dts` adds a simulated I2C bus and a sensor at address 0x44 to the
machine's device tree, the description Linux uses to find hardware. `desk_bus.c`
registers an actual I2C adapter with the Linux core. `desk_sensor.c` binds to its
child sensor and transfers the six SHT31 bytes through normal I2C calls. It
registers `/dev/desk-sensor` as a restricted character device.

The eight-byte register block is six sensor bytes, a held-alarm byte and a zero
reserved byte. `read()` returns that block once per opened file. `DESK_GET`
returns a fresh block through ioctl, a device-specific command. `DESK_INJECT`
sets the simulated bus bytes and runs checksum validation; `DESK_CLEAR` clears
the held alarm. Mutating calls require `CAP_SYS_ADMIN`. A new healthy sample
cannot clear an earlier fault. Clearing while the sample is still corrupt
causes the next read to latch the alarm again. A mutex protects concurrent
reads and commands.

Inside the built system the startup script runs:

```sh
modprobe desk_bus
modprobe desk_sensor
/usr/bin/desk-sensor-service /dev/desk-sensor --self-test
rmmod desk_sensor
rmmod desk_bus
```

For a matching Linux kernel build tree, I can build the same modules out of
tree with `make -C linux_sensor KDIR=/path/to/linux-build`. I must use the
matching headers and booted kernel, not load an arbitrary CI module into a
host. The startup test compares read and ioctl, injects bad CRC bytes, confirms
the alarm remains held after healthy data, clears it and checks an unknown
command returns ENOTTY. QEMU is stopped after the test and its process metadata
is kept alongside the serial log.

For normal use, `desk-sensor-service /dev/desk-sensor` prints one JSON reading;
`--watch` polls once a second and exits cleanly on SIGTERM. `--replay file.wire`
feeds the existing `DESK_REPLAY_V1` sensor-wire format through the injection ioctl,
so a Scheme-generated outage can drive the actual kernel checks. Alarmed values
are printed as null and remain held until `--clear` is requested. The self-test
mode is explicit because it deliberately changes the simulated sensor state.
