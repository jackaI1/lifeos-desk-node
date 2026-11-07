# Checking my simulated controller network

I built a recording decoder because I wanted to see what damaged or missing
controller readings would do before connecting anything to my desk node. CAN is
a wired message network used to share small readings and commands between
controllers. I use eight-byte classic CAN messages for temperatures and outputs,
and a 64-byte CAN FD message for a longer diagnostic snapshot. A DBC file is a
message dictionary: it tells the decoder which bytes mean a temperature or
percentage. The FD message also sets the bit-rate-switch flag, which requests a
faster data phase on real hardware; a virtual bus checks the flag, not physical
speed. Everything here is a computer simulation. There is no CAN transceiver on
my current ESP32 board.

From the repository root, with Python 3.11 or newer:

```sh
python3 -m venv .venv
.venv/bin/pip install -r can_monitor/requirements.txt
.venv/bin/python -m can_monitor.replay --generate /tmp/desk-can.jsonl --faults
.venv/bin/python -m can_monitor.replay /tmp/desk-can.jsonl --tail 3
.venv/bin/python -m pytest can_monitor/tests -q
```

I get each decoded temperature in degrees Celsius, the target temperature and
heater/fan percentages, errors for each frame, and a final report. `rates` counts
all observed DBC identifiers, including rejected frames: frequency is (count - 1)
divided by the span between their first and last arrival. Unknown identifiers
are rejected without growing the statistics table. Statistics use constant space.

## Linux virtual CAN

This runs the actual Linux CAN socket path. GitHub Actions creates its own
interface and removes it even on failure. On a Linux machine I can do the same:

```sh
sudo modprobe vcan
sudo ip link add dev deskcan0 type vcan
sudo ip link set dev deskcan0 mtu 72 up
DESK_VCAN=deskcan0 .venv/bin/python -m pytest can_monitor/tests -q
.venv/bin/python -m can_monitor.replay can_monitor/examples/faults.jsonl --interface socketcan --channel deskcan0 --tail 3
.venv/bin/python -m can_monitor.replay --listen 5 --channel deskcan0
sudo ip link delete deskcan0
```

`--listen` uses the real monotonic clock and checks silence even without traffic.
Replay uses the recording's logical time, so an hours-long recording needs no
hours-long wait. Invalid DLC/byte-count combinations cannot cross a CAN socket;
I diagnose those directly before sending other frames over the selected bus.
My macOS tests use python-can's in-process virtual bus; Linux CI additionally
uses SocketCAN. Virtual interfaces verify software and flags, not arbitration,
physical bit timing, electrical faults or actual bit-rate switching speed.

## Message and safety rules

`can_monitor/desk.dbc` is the message description, including positions, scale,
units and physical ranges. Identifier 0x100 carries an eight-byte command/sample;
0x101 carries a 64-byte diagnostic snapshot with CAN FD and the bit-rate-switch
flag set. The remaining FD bytes are reserved zeros, protected by the CRC.

The project protocol uses CRC-8/SAE-J1850 parameters (polynomial 0x1d, initial
0xff, final XOR 0xff), covering the two-byte identifier, FD flag, byte length and
all payload bytes except the final CRC byte. This is a sample project protocol,
not a claim of compatibility with any vehicle. Each identifier has an independent
8-bit rolling counter, including wrap from 255 to zero. A gap or repeat rejects
that sample; a CRC-valid gap resynchronises the expected counter so the next
sequential frame can recover. Bad checksums never move the counter or deadline.

At startup, after a two-second silence, or on an invalid frame, outputs are
heater=0, fan=0, fault=true. Range, frame type, identifier and DLC checks happen
before physical values can reach outputs. A clean primary sample recovers a
transport fault. An identifier-specific fault needs a clean sample of that ID.
`Monitor.outputs(now)` is the control simulation's fail-closed boundary, not a
physical safety interlock or a certified safety controller.

The included generator injects unknown identifiers, short data, counter gaps,
CRC corruption and silence. The suite also covers replayed timestamps, counter
wrap, repeated counters, startup silence, invalid frame flags, physical-range
violations and comparison with an independent CRC implementation.
