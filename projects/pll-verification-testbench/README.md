# pll-verification-testbench

I built a programmable timing circuit checker to learn how the underlying idea works. This is a learning project.

I use generated signal patterns, small example programs and simulated circuit results.

## Try it

I use Python 3.10 through 3.14, Verilator 5.036 or newer, Yosys and a C++ compiler. On macOS:

```sh
brew install python@3.14 verilator yosys
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python scripts/report.py
yosys -c scripts/synth.tcl
```

I use a supported Python version explicitly because the newest system Python can be ahead of cocotb support. Activating the environment also lets Verilator find the same interpreter.

The report at `build/report.json` gives a pass/fail result and counts the required coverage cases. A failing simulation, missing case, duplicate result or missing random seed makes the report fail. Compiler output stays in `build/report.log`.

The Linux checks also run automatically in [GitHub Actions](https://github.com/jackaI1/pll-verification-testbench/actions). Each architecture run provides a downloadable `verification-evidence` artifact containing instruction-test results, formal counterexamples and timing reports. I do not need a container or a virtual machine to run the local checks.

## What the program controls

The phase-locked loop (PLL) model compares a reference pulse with a divided clock pulse. Its digital controller raises or lowers a four-bit value, and marks the signals as locked after four matching pulses. It models the digital decisions, rather than an analog oscillator or real clock jitter.

The processor can change the divider, hold the PLL in reset and capture status words. A first-in, first-out queue (FIFO) preserves the order of those words. My integration test runs firmware that sweeps divider ratios 2 through 8, captures three samples at each setting and reads all 21 samples back into memory. A Python PLL model checks the status values and the test checks every copied sample.

## Circuit and processor design

`rtl/sample_fifo.sv` is a parameterized sample queue. I test depths 1, 3 and 8 with three repeatable random seeds. A Python queue is the reference; seven required cases cover empty reads, full writes, simultaneous reads and writes, pointer wraparound, empty/full states and reset with queued data. SystemVerilog assertions check occupancy, pointer bounds and rejected operations.

`rtl/rv32_core.sv` implements the RV32I integer instructions in five stages: fetch, decode, execute, memory and writeback. Forwarding sends a result straight to the next instruction that needs it. A one-cycle stall handles a load dependency, and a taken branch discards younger instructions. Both the original ripple-carry adder and the carry-select version run against the same Python instruction model.

The public `riscv-tests` RV32UI instruction suite runs in Verilator using a small bare-metal adapter. The upstream instruction bodies stay unchanged, including the misaligned-data and instruction-fence tests. This is an educational bare-metal core: it has no interrupts, privileged mode, cache, bus wait states or operating-system support. Its memory adapter supplies a four-byte window starting at the requested byte address, including unaligned addresses. See [the design notes](docs/design.md) for ports, memory addresses and reproduction commands.

## Regression details

The project is [MIT licensed](LICENSE). Downloaded upstream tests retain their own license. Sources and limits are documented in [docs/design.md](docs/design.md).

## Tests and limits

I kept 12 files of test code and supporting test helpers in this copy. This is a file inventory, not an execution result. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `pll-verification-testbench-verify.yml`.

Workflows omitted during the move:

- `.github/workflows/architecture.yml`: Deployment or credential-dependent workflow requires separate validation.
