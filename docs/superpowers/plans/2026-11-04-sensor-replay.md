# Sensor replay implementation plan

**Goal:** Reproduce sensor errors and offline queue loss on a computer using the desk node's real C core.

**Design:** I chose a Scheme scenario compiler plus a C replay executable. A Python-only simulator would duplicate the firmware behavior; putting Scheme on the ESP32 would increase its runtime footprint. The host pipeline exercises the existing sensor decoder, queue and display renderer without changing the device firmware or claiming hardware validation.

**Architecture:** `replay/scheme/desk/scenario.scm` validates a small data language and expands repeats into SHT31 sensor bytes. `replay/replay.c` consumes those bytes through `desk_core`, simulates successful queue uploads, reports counts as JSON and optionally exports the actual screen buffer as a portable bitmap. No network services, credentials, real device or personal records are needed.

**Constraints:** Guile 3, C11 and Python 3 for integration tests; no new firmware dependency. At most 4096 expanded commands, eight nested repeats and 64 KiB input. Sensor values use integer milli-degrees Celsius and thousandths of percent humidity. Upload is explicitly simulated, not an HTTP transaction.

**Review focus:** Reject arbitrary expressions, invalid sensor ranges, repeat expansion overflow, malformed byte streams and output-file failures. Verify exact quantization, independent CRC vectors, FIFO loss, invalid samples, post-upload sequences and actual framebuffer pixels.

## Task 1: Compiler, replay and automated checks

- [x] Write Scheme unit tests and Python subprocess integration tests first. Pin known sensor bytes, nested repeats, validation errors, 70-reading overflow (6 lost, 64 uploaded), sensor CRC faults and PBM output.
- [x] Run tests to observe missing compiler and replay executable failures.
- [x] Implement `(compile-scenario datum)` returning a bounded list of command strings and `(write-scenario datum port)` writing `DESK_REPLAY_V1` plus commands. Read input as data, never evaluate it.
- [x] Implement a strict bounded C parser for `S <12 hex digits>` and `U`. Use `desk_decode_sht31`, `desk_ring_push`, `desk_ring_pop`, `desk_render`, and fixed-size storage. Report samples, faults, uploaded, queued, dropped and oldest/newest sequence; export the 128x64 buffer as PBM when requested.
- [x] Add build/test commands, an overflow example, a quick-start README and a technical guide. Preserve all existing features and honest hardware limitations.
- [x] Run Scheme tests, sanitizer-enabled C integration tests and existing host tests. Add Linux and macOS CI for the complete Scheme-to-C pipeline.
- [ ] Review the branch independently, fix material findings, open a plain-language PR, watch CI, merge through GitHub, and verify green merge CI.
- [ ] Run the required independent Sol verifier and address any FAIL through a further PR before writing the result JSON.

## Local evidence

`make -C replay test` passes 32 Scheme assertions and 12 integration tests under
address/undefined-behavior sanitizers. Existing host tests pass 74 C checks and
17 adapter tests. A fresh Sol review found one output-error issue: Guile can
replace unusable stdout with a void port. The added regression failed first;
explicit descriptor opening and flushing now report the error and the full suite
passes. There were no other review findings. The documented outage produces
70 accepted samples, one fault, 64 uploaded readings and six dropped readings.
