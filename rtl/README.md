# Desk node checksum and reading buffer in hardware

I wrote these small hardware blocks because the desk node checks the sensor's checksums in software, and I wanted to know the same check works as logic, the way it would on an FPGA (a reprogrammable chip) or a custom chip. The sensor sends each reading as six bytes with two checksum bytes. The firmware throws away a reading whose checksum does not match, and I deliberately corrupt some checksums in my test scenarios to check that.

These blocks do the same job in Verilog and SystemVerilog, which are hardware description languages. I test them with simulators on my computer and in CI, against the same scenario files the firmware tests use.

## What is here

| Block | What it does |
|---|---|
| `src/sht31_crc8_step.v` | One byte of the sensor's CRC-8 checksum (polynomial 0x31). It is the same rule as `desk_crc8()` in the firmware. |
| `src/crc8_word_stream.v` | Checks one 16-bit sensor word against its checksum byte, one word per clock. |
| `src/sht31_frame_check.sv` | Takes a six-byte frame one byte per clock, checks both checksums, and counts good, bad and cut-short frames. |
| `src/reading_buffer.v` | Keeps the last eight good readings. Its control flops form a scan chain, and a March C- self-test checks its memory. |
| `src/march_bist.v` | The March C- memory self-test: six passes that write and read every word. |
| `src/sensor_path.v` | The top block: the frame check feeding the buffer. |
| `src/uart_rx.v`, `src/uart_tx.v` | Serial receiver and transmitter, 8N1 (8 data bits, no parity, 1 stop bit), with the divider as a parameter. |
| `board/icebreaker/desk_board_top.v` | Board top for the iCEBreaker (iCE40UP5K, 12 MHz). Serial transfers in, the three frame counts out, LEDs. |
| `board/icebreaker/icebreaker.pcf` | Pins: clock 35, serial RX 6, serial TX 9, green LED 37, red LED 11. |
| `board/icebreaker/host.py` | Computer side: builds frames with the sensor checksum, sends transfers, prints the counts. |

## How it is checked

- `make lint` runs Verilator's linter on every top block.
- `make test-frame` runs a cocotb testbench (Python code that drives the simulated hardware) on the frame checker. It replays the desk-node scenarios from `replay/examples/outage.scm` and `capture/examples/*.scm`, plus `scenarios/mixed-corruption.scm`, which I wrote with good and corrupted frames. It also runs 3,000 random frames with idle gaps, some corrupted in one or both words and some cut short. The results must match a Python reference model on every frame, and the counters must match too.
- `make test-crc` runs a Verilator testbench on the word checker. It uses every word from the replay scenarios and 2,000 random words with flipped checksum bits, so both good and bad verdicts are tested. The test also checks that the number of bad frames equals the `faults` count that the replay tool prints for the same files.
- `make test-dft` runs a Verilator testbench on the reading buffer. It checks the buffer against a software queue for 20,000 random cycles, shifts patterns through the scan chain, and then injects each stuck-at fault, forced to 0 or to 1, into every memory bit and every control flop. The self-test has to report each one at the right word.
- `make synth` runs Yosys to map the sensor path onto iCE40 FPGA cells and reports the logic depth.
- `make test-board` runs a Verilator testbench on the board top. It acts as the computer: it sends serial bytes at 115200 baud and decodes the six reply bytes. It checks good, bad, cut-short and zero-length transfers, two frames in one transfer, and the red LED.
- `make board` builds the iCEBreaker bitstream: Yosys for synthesis, nextpnr-ice40 for place and route at a 12 MHz target, and icepack. `scripts/board_report.py` fails the build if the clock target is missed. This needs `yosys`, `nextpnr-ice40` and `fpga-icestorm`. The Ubuntu job in CI runs it.

The CI workflow `.github/workflows/rtl-checksum-selftest.yml` runs all of this on macOS. The OpenROAD place-and-route flow has its own folder, `flow/`, and workflow.

## Results

These numbers come from my last local run and CI runs the same checks.

| Check | Result |
|---|---|
| Word checker against the replay bytes | 2,204 words, 1,196 good, 1,008 bad, 0 mismatches |
| Frame checker against the reference | Scenario frames and 3,000 random transfers match on every event |
| Memory stuck-at faults in the buffer | 512 of 512 detected (100 %), and the faulty word is named in each case |
| Scan chain stuck-at faults | 22 of 22 detected (100 %) |
| iCE40 mapping (`make synth`) | 588 LUT4, 440 flip-flops, 82 carry cells, logic depth 79 cells |

The 440 flip-flops are mostly the eight-word buffer, which I store in flops rather than block RAM.

The March C- test finds any stuck-at fault in a memory cell, which is what the table shows. It does not find every kind of memory fault, for example coupling between two cells.

## Place and route with OpenROAD

OpenROAD is an open-source chip design flow. It is the free equivalent of the Synopsys and Cadence tools, and it runs here on the open Nangate45 cell library. The folder `flow/` runs the whole flow on `sensor_path`: Yosys synthesis, floorplan, placement, clock tree and routing. `flow/run_sweep.sh` repeats it for clock periods of 2.0, 1.6 and 1.2 ns and for core utilizations of 30 % and 50 %. `flow/collect.py` reads the final metrics for each run and writes [docs/openroad-sweep.md](docs/openroad-sweep.md). The CI job `.github/workflows/openroad-sensor-path.yml` runs the sweep in the `openroad/orfs` container and fails if the chosen constraint, 1.2 ns at 30 % utilization, has negative setup slack.

| Period | Utilization | Worst setup slack | Cell area | Power |
|---|---|---|---|---|
| 2.0 ns | 30 % | 0.688 ns | 4516 um^2 | 3.5 mW |
| 1.6 ns | 30 % | 0.408 ns | 4525 um^2 | 4.4 mW |
| 1.2 ns | 30 % | 0.113 ns | 4541 um^2 | 5.9 mW |
| 1.2 ns | 50 % | 0.080 ns | 4504 um^2 | 5.7 mW |

Every run meets timing. The 1.2 ns runs leave little margin, so a slower clock is safer for a real board. Power is OpenROAD's estimate with its default switching activity, not a measurement.

## Board

The board top runs the sensor path on an iCEBreaker: the computer sends `N` (1 to 255), then `N` sensor bytes, at 115200 baud over the board's USB serial port. The board replies with six bytes: good, bad and truncated counts, each high byte first. Wait for the reply before sending the next transfer. Run it from a computer with `python3 board/icebreaker/host.py --port <port> --demo`.

The serial lines and the LEDs use the pins in `board/icebreaker/icebreaker.pcf`, which follow the icestorm example file for this board. Check them against your board revision before you flash.

## Limits

- The board build has been simulated and built into a bitstream in CI. I have not yet flashed an assembled board from this build.
- The reading buffer's self-test overwrites the stored readings, so I would run it only when the buffer is empty.
- The fault injection hooks (`mem_fault_*` and `scan_fault_*`) exist for the testbench. Tie them to zero in a real design.
