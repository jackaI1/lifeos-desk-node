# Measured verification results

I measured the complete processor before and after shortening its carry path. These are the original reports from [the successful Linux run](https://github.com/jackaI1/pll-verification-testbench/actions/runs/42309974365) at source commit `bbe951bad5549a8d7d66d81e8a9b3ba856070a46`.

| Check | Measured result |
| --- | --- |
| Pytest regression | 32 passed |
| PLL required coverage | 11/11 bins |
| Sample FIFO required coverage | 7/7 bins in all 9 depth/seed runs |
| Public RV32UI instruction suite | 42/42 programs passed; failure-adapter negative check passed |
| Formal bounded checking / induction / reachability | PASS / PASS / PASS |
| Seeded flush bug | Expected FAIL at step 5; saved waveform and assertion location |
| Original serial-carry core, worst constrained arrival | 21.0994 ns |
| Four-bit carry-select core, worst constrained arrival | 19.5514 ns |
| Reduction | 1.5480 ns, or 7.34% |

The original path contains a long chain of `sky130_fd_sc_hd__maj3_1` carry cells. The revised core computes both possible carries within four-bit groups before selecting a result. The longest remaining path includes multiplexers and several slow arcs, so this is a reduction in the whole core's worst path, not just a separate adder benchmark.

Both timing runs use Sky130 HD at the typical 25 C, 1.80 V corner: 100 ns clock, 1 ns input and output delays, 0.1 ns input transition and 0.05 pF output load. Clock paths are ideal and reset is excluded from functional data paths. These reports use cell timing and pin loads before placement, without extracted wire delays. They do not establish a routed-chip maximum frequency or performance across other voltage, temperature or process corners.

`timing.json` records the pinned library revision, SHA-256 and tool versions. `before-opensta.txt` and `after-opensta.txt` retain the original timing arcs and slack calculations. `simulation.json`, `riscv-tests.json` and `formal.json` are the generated summaries. The formal summary's `bug: FAIL` is intentional: `flush-failure.txt` identifies the failed younger-stage invalidation assertion, and `flush-counterexample.vcd` is its waveform.

The CI artifact also contains the full formal logs and generated counterexample testbench. Re-run `python scripts/formal.py` to regenerate those files, or follow [the design notes](../design.md) to repeat the complete experiment. Every push reruns the checks and requires a positive timing improvement.
