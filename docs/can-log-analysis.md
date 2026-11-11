# Desk-node CAN link and log analysis

I built this because the desk node needs a wired link to the room sensors as a
backup for Wi-Fi, and I need to see when that link misses messages or goes
down. CAN is a bus: devices share two wires and send short numbered messages.
Every device hears every message, and a message with a bad checksum is dropped
by the receivers. A device that keeps sending bad frames is switched off by the
bus (bus-off), and the log shows that.

## What is in the repository

| Path | Purpose |
| --- | --- |
| `can_monitor/desk_node.dbc` | Message layout: ID 0x120 `DeskNode`, with Temperature, Humidity, Heartbeat, SensorFault and QueueLoss. |
| `can_monitor/candump.py` | Reads candump `-l` logs into python-can `Message` objects. Damaged lines are returned as `MalformedLine` values. |
| `can_monitor/analyze.py` | Decodes frames with the DBC (cantools) and reports the findings below. |
| `can_monitor/virtual_node.py` | Simulated desk node on python-can's virtual bus. It writes what a listener sees as a candump log. |
| `can_monitor/examples/candump/` | `desk_node_clean.log` (recorded in the simulator) and `desk_node_faults.log` (the same log, deliberately corrupted). |
| `can_monitor/examples/build_faults_log.py` | Rebuilds the corrupted log from the clean one, so the damage is documented in code. |
| `firmware/components/desk_can/` | ESP32 side: encodes the DeskNode payload and drives the TWAI controller at 500 kbit/s. |
| `firmware/tests/test_can.c` | Encoder test with fixed byte vectors (run on the Mac and in CI). |
| `can_monitor/tests/test_desk_node_contract.py` | Decodes the firmware's byte vectors with the DBC, so the C side and the DBC cannot drift apart. |

## Run the analyzer

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r can_monitor/requirements.txt
.venv/bin/python -m can_monitor.analyze can_monitor/examples/candump/desk_node_clean.log
.venv/bin/python -m can_monitor.analyze can_monitor/examples/candump/desk_node_faults.log --json faults.json
```

The clean log prints `findings=0` and exits 0. The corrupted log exits 1 and
prints one line per finding. `--heartbeat-timeout` sets how many seconds
without a DeskNode frame count as missing (default 10 s). Exit status 2 means
the log or DBC could not be read.

## Findings

| Kind | Meaning |
| --- | --- |
| `missing_heartbeat` | No DeskNode frame for longer than the timeout. This includes silence before the first frame and after the last frame in the log. |
| `heartbeat_skip` | The Heartbeat counter jumped, so frames were lost. The counter wraps from 255 to 0 without a finding. |
| `out_of_range` | A decoded value is outside its DBC minimum and maximum. The firmware sends raw 0xFFFF for "no valid reading", which decodes far outside the range. |
| `sensor_fault` | The node set SensorFault=1. |
| `queue_loss` | The node set QueueLoss=1, meaning readings were dropped on the device. |
| `bus_off` | An error frame with the CAN_ERR_BUSOFF bit (0x40). The controller stopped transmitting. |
| `error_frame` | Any other error frame. |
| `unknown_id`, `decode_error` | A frame with an ID not in the DBC, or with the wrong length for DeskNode. |
| `malformed_line` | A log line that is not valid candump, for example a 10-byte classic CAN payload. |
| `timestamp_reversed` | The time went backwards. The frame is reported once and left out of the heartbeat checks. |

Error frames keep their class bits. python-can's own log reader drops the
error flag, so `candump.py` reads that token directly. A standard candump
error frame looks like `20000040#0000000000000000`.

## Payload layout

All signals are little-endian (Intel order), as in the DBC.

| Signal | Bits | Scale and offset | Range |
| --- | --- | --- | --- |
| Temperature | 0-15 | raw × 0.01 − 40 °C | −40 to 125 °C |
| Humidity | 16-31 | raw × 0.01 %RH | 0 to 100 %RH |
| Heartbeat | 32-39 | raw | 0 to 255, wraps |
| SensorFault | 40 | bit | 0 or 1 |
| QueueLoss | 41 | bit | 0 or 1 |

The firmware encoder (`desk_can_encode`) and the DBC must give the same bytes.
`firmware/tests/test_can.c` checks seven vectors in C, and
`can_monitor/tests/test_desk_node_contract.py` checks the same bytes with
cantools. An out-of-range temperature or humidity, or a missing reading, is
sent as the 0xFFFF marker with SensorFault=1.

## Simulated bus

```sh
.venv/bin/python -m can_monitor.virtual_node --seconds 120 --log /tmp/desk.log
.venv/bin/python -m can_monitor.virtual_node --seconds 60 --silent 20:30 --log /tmp/gap.log
.venv/bin/python -m can_monitor.analyze /tmp/gap.log
```

Frames go out on python-can's `virtual` interface and are received on a second
bus object on the same channel. Timestamps are logical (start + k × period),
so the same arguments always write the same log. The tests check that the
committed clean log is exactly what the simulator writes.

## Firmware

The CAN code is off by default. Enable it in menuconfig under *Desk CAN link*
or with `CONFIG_DESK_CAN_ENABLE=y`. Default pins are GPIO 19 for TX and GPIO 4
for RX; both can be changed. Each wake cycle, after the sensor read, the node
starts the TWAI driver, sends one DeskNode frame and stops the driver again.
The heartbeat counter is kept in RTC memory, so it survives deep sleep.

The board needs an external 3.3 V CAN transceiver between the TWAI pins and
the differential bus wires (for example SN65HVD230 or a similar part). The
current desk board has no transceiver, so nothing here has been tested on a
real bus. CI builds the firmware with the CAN link enabled
(`firmware/sdkconfig.can.defaults`), so the code compiles against ESP-IDF 5.4.2.

A node with no other device on the bus gets no acknowledgement for its frames,
so the controller keeps retransmitting until it goes bus-off. The analyzer
reports that as `bus_off`. A second node on the same bus is needed to see
healthy traffic.

## Limits of this check

- The example logs come from the simulator, not from a recording of hardware.
- The analyzer checks what is in the log. It does not measure bit timing,
  termination, arbitration or electrical faults.
- Frames are not checked against a CRC. CAN's hardware CRC already drops bad
  frames before they reach software, and the DBC has no separate checksum.
