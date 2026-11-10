# Parallel scenario replay: threading design

This document explains how `desk-replay --jobs N` runs many sensor scenarios on
POSIX threads. For how to use the replay, read the
[replay guide](sensor-replay.md). The code is in `replay/replay.c`; the tests are
in `replay/tests/test_pool.py`.

## What must hold

- The output for `--jobs N` is byte-for-byte the output for `--jobs 1`, for every N.
- Output lines appear in command-line order, never in the order threads finish.
- A failure reports the lowest-numbered bad file, prints nothing on stdout, and
  exits 1, with the same result for every thread count.
- Nothing races. ThreadSanitizer runs the pool tests in CI, and AddressSanitizer
  and UndefinedBehaviorSanitizer run them too.

## Parts

- **Scenario ring.** One shared mapping holds 8 slots. Each slot holds one whole
  wire file, up to 64 KiB. The mapping is a temporary file in `$TMPDIR` (or
  `/tmp`), opened with `mkstemp`, removed at once with `unlink`, sized with
  `ftruncate` and mapped with `mmap(MAP_SHARED)`. The mutex and the two condition
  variables live in the same mapping.
- **Producer.** The main thread walks the files in order. For each file it waits
  until the slot for that file is FREE, loads the file into the slot, then marks the
  slot FILLED and publishes it.
- **Workers.** Up to N threads, never more than there are files. A worker takes the
  next unclaimed file in order, marks its slot TAKEN, replays it, and marks the slot
  FREE again.
- **Per-thread results.** Each worker appends its results to its own growing array.
  No two threads write the same array.
- **Merge.** After all workers have been joined, each result is copied to the entry
  for its job number. Output is printed by job number, so the order is fixed.

## Lock and condition rules

There is one mutex, `ring->lock`. It guards the slot states, `published`,
`next_take` and the condition variables. Nothing else is shared.

| State | Who changes it | Who may touch the bytes |
| --- | --- | --- |
| FREE | worker, after replay | producer (waiting on `slot_freed` for FREE) |
| FILLED | producer, under lock | none until a worker takes it |
| TAKEN | worker, under lock | that one worker, until it sets FREE |

- The producer writes `slot->data` while the slot is FREE, without the lock. No
  worker reads a FREE slot, so the write does not race. It publishes the slot under
  the lock, so the workers see the bytes after they acquire the lock.
- A worker waits on `slot_filled` while `next_take == published` and there are
  still files to publish. It exits when `next_take == total`.
- The producer waits on `slot_freed` while its slot is not FREE. Workers broadcast
  after freeing a slot.
- Ordering is by job number. A worker never takes file k+1 before file k, and the
  producer can be at most 8 files ahead of the oldest file still in use.

## Why the workers avoid stdio

The first version used `fmemopen` and `fgetc`, which is simple. Sampling a running
four-thread replay showed the threads spent most of their time inside stdio: each
`fgetc` takes a per-file lock, and on macOS the read path also walks the global list
of open files. The workers ended up waiting on each other, so four threads gave no
speedup.

The current workers read the wire from memory with the same rules as
`desk_replay_read_line`: exact lines, at most 79 bytes, no NUL bytes, and an
unterminated last line is accepted. The stdin path still uses the stdio version.

## Error policy

- A file that cannot be opened or read, or that is larger than 64 KiB, is marked
  in its slot. The worker records the reason without replaying it.
- A malformed wire, a bad header, or too many commands is recorded as that file's
  reason. It does not stop the other workers.
- The first failure by job number is printed to stderr as
  `replay: <path>: <reason>`. Stdout stays empty.
- Limits: at most 64 threads and 10,000 files.

## What the tests check

`replay/tests/test_pool.py` builds 12 scenarios with the Scheme compiler, then runs
them in 240 jobs, shuffled.

- Thread counts 2, 3, 4, 5, 8, 16 and 64, three runs each, against the `--jobs 1`
  output. Stdout must be identical and stderr must be empty.
- Each line matches the stdin output for the same scenario.
- Output follows argument order when the list is reversed.
- More threads than files.
- A stress run of 1000 jobs at 4 and 8 threads.
- The first bad file is reported, for both serial and pooled runs.
- Bad options and oversized files are rejected.

`replay/tests/run.sh` builds the replay twice. One build uses AddressSanitizer and
UndefinedBehaviorSanitizer and runs every test. The other uses ThreadSanitizer and
runs the pool tests with `halt_on_error=1`. Any race stops the process with a
non-zero exit, which fails the test that ran it.

As a check that the race detector is effective, I built a scratch copy that updates
`next_take` after releasing the lock. Run on a six-file input, ThreadSanitizer reported
a data race in three of three runs and stopped with a non-zero exit, so a test like
these would fail.

## Measured speed on my Mac

2000 copies of one scenario with 4095 samples, on my Mac, which has 15 CPU cores. Times are wall-clock, from `/usr/bin/time -p`, median of three runs.

| Threads | Wall time |
| --- | --- |
| 1 (serial) | 0.17 s |
| 2 | 0.08 s |
| 4 | 0.04 s |
| 8 | 0.04 s |

The floor near 0.04 s is most likely the producer, which reads each file on the main
thread; I have not profiled it separately.
Larger files would benefit more from reading ahead; I have not added that.
