# Design and reproduction

## Pipeline

The five stages are fetch (PC and combinational instruction RAM), decode (register read), execute (forwarding, ALU and branch decision), memory (combinational data RAM) and writeback. A separate retirement trace allows a sequential reference to compare instructions and written register values without copying the pipeline.

The memory-stage ALU result has priority over writeback when both match a source register. A load in execute stalls a dependent decode instruction for one cycle and inserts a bubble. The following execute cycle obtains that load through writeback forwarding. Writeback also bypasses the decode register read on the same edge. A redirect takes priority over a load stall and invalidates both younger stages.

The core implements integer arithmetic, shifts, comparisons, jumps, branches, byte/halfword/word loads and stores, LUI, AUIPC and fences. ECALL/EBREAK and unsupported opcodes produce a terminating trace event; this is not a privileged trap handler. FENCE.I redirects to PC+4 to refetch instructions after code stores. The test adapter places its pass/fail number in x3 and terminates with ECALL. Unsupported instruction encodings are outside the supported-program contract; this is not a security boundary.

The instruction port must supply the word at `imem_addr` combinationally. Instruction targets must be four-byte aligned; instruction-address misalignment traps are not implemented. The data port returns four little-endian bytes starting at `dmem_addr`; write strobes apply to bytes `addr+0` through `addr+3`. There is no ready signal and no backpressure. The test RAM supports unaligned accesses across word boundaries; an FPGA integration would need a real adapter with the same contract. Stores take effect on the rising edge. Reset suppresses memory transactions.

## PLL memory map

`rtl/pll_soc.sv` connects the real processor, PLL controller and eight-word sample queue. Other addresses pass through to external data RAM. Instruction memory is separate but can share the RAM model, as it does in the instruction tests.

| Address | Read | Write |
| --- | --- | --- |
| `0x10000000` | Divider ratio in bits 3:0, hold-reset in bit 8 | Change ratio/reset; reset before changing the ratio |
| `0x10000004` | Current status word | Ignored |
| `0x10000008` | Read and pop oldest sample; zero if empty | Capture current status; ignored if full |
| `0x1000000c` | Count in 3:0, empty in 4, full in 5 | Ignored |

Status packs ratio in bits 11:8, control in 7:4, locked/down/up/feedback in 3:0. MMIO accesses must be full-word and use the listed addresses. Samples describe the PLL state immediately before the capture edge. Overflow does not overwrite queued samples. Simultaneous push/pop at full capacity replaces the popped slot; an empty simultaneous request only pushes, with no fall-through pop. FIFO output is zero when empty.

`tests/soc_env.py` contains directly encoded RV32I firmware, avoiding a cross compiler for this check. It resets and releases each ratio, waits, captures three samples, then copies them to RAM at `0x4000`. Its independent PLL reference advances every cycle, including reset and sampling edges.

## Simulation

```sh
python -m pytest -q
python scripts/report.py --output build/report.json
yosys -c scripts/synth.tcl
```

Pytest builds disposable Verilator models in its temporary directories. `scripts/report.py` runs the PLL and FIFO simulations, parses their output, and exits nonzero unless every required run and bin is present. The seeded PLL divider bug is a successful negative test only if the scoreboard reports the specific divider/control mismatch. Core random programs include register dependencies, load-use stalls, wrong-path stores, conditional branches, jumps, shifts, comparisons and zero-register writes. Retirement order, instruction bits, destination registers and written values must match the independent sequential model.

## Public instruction suite

On Linux, install `gcc-riscv64-unknown-elf`, `binutils-riscv64-unknown-elf` and recent Verilator, then:

```sh
python scripts/riscv_suite.py
```

The script fetches [riscv-tests](https://github.com/riscv-software-src/riscv-tests) at commit `3df703cd52d5f0d8224e3c50bf03c6cb70efff98`, reads the RV32UI Makefrag manifest and runs every listed program. It preserves all test bodies and macros, including their license, under ignored `build/riscv-tests/upstream`. Only `tests/programs/riscv_test.h` replaces the privileged boot environment with a zero-address bare-metal entry and ECALL finish. Link relaxation is disabled. The adapter supports RV32I plus Zifencei for the instruction-fence case. These tests are useful instruction regression, not an official certification or a test of privileged instructions.

## Formal scope

```sh
python scripts/formal.py
```

Use [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build), including SymbiYosys, Yosys and Bitwuzla. The CI workflow pins its release. `formal/core.sby` runs 12-step bounded checking, induction up to eight steps, and 12-step reachability checks on the actual processor RTL. Only the first reset is assumed; instruction and data inputs remain unconstrained, and later reset pulses are allowed. Properties are under `FORMAL` in the core:

- x0 remains zero after reset.
- The PC takes a redirect target, holds on a load stall, or advances by four.
- Redirects discard both younger stages; stalls preserve decode and inject an execute bubble.
- Zero sources remain zero; the newest matching nonzero result wins over older forwarding data.

Cover statements require a redirect with a younger instruction, a load-use hazard and a simultaneous memory/writeback forwarding match. `FLUSH_BUG=1` intentionally retains the decode valid bit after a redirect. The same assertions must fail, and the script requires a counterexample testbench. A solver crash, unknown status, missing proof or timeout fails CI. These control invariants do not prove the ALU's ISA semantics, external RAM or the complete processor's functional correctness.

## Static timing experiment

```sh
sudo apt-get install tcl-dev swig bison flex libfl-dev libeigen3-dev
bash scripts/build_opensta.sh
OPENSTA="$PWD/build/tools/sta" python scripts/timing.py
```

These build commands target Ubuntu 24.04 with a C++ compiler, CMake and Yosys installed. `scripts/build_opensta.sh` builds OpenSTA commit `f8e13cbf12d02a07a2d1ec4a64f3e6985b747eab` with CUDD commit `f54f533303640afd5dbe47a05ebeabb3066f2a25`. CI caches the executable. Distribution packages can be too old for current netlists and report commands. A modern system OpenSTA also works with `python scripts/timing.py` directly.

The timing script downloads only the typical Sky130 HD Liberty file from [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) commit `c5310d7ffdd5f8a1eed83089697631548cc08a99`, records its SHA-256, maps both full cores, and runs identical constraints: 100 ns clock, 1 ns input/output delays, 0.1 ns input transition and 0.05 pF output load. Reset is excluded from functional data paths. The before/after reports name the startpoint, endpoint and individual timing arcs. The JSON records the worst constrained data arrival time and percentage reduction.

The baseline explicitly ripples carry across 32 bits. Its first OpenSTA path showed 21.0994 ns arrival, including a long chain of majority carry cells. I shortened the proposed carry-select groups from eight bits to four after reading that path. The revised adder computes two possible sums per four-bit group in parallel, then selects with the preceding carry. Both add and subtract, effective addresses and JALR use it. Both versions run the same Python model regression. Timing is pre-layout, typical-corner cell delay with pin capacitance only. It does not predict board speed, routed silicon timing or a maximum frequency across process/voltage/temperature corners. The baseline remains selectable so CI can repeat the experiment rather than comparing a new report with an unverifiable number.

## CI evidence

The macOS job runs simulation and synthesizes both the PLL alone and the complete processor/PLL/FIFO assembly. The Linux architecture job runs pytest, simulation coverage, the entire RV32UI manifest, formal tasks and both timing variants. Artifacts include JSON summaries, logs, STA paths and the negative test's counterexample. Missing tools or failed checks propagate as CI failures. No images, VM disks, large datasets or weights are needed locally.
