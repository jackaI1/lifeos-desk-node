# A simulated controller I can interrupt safely

I built a controller rehearsal because I wanted to learn how to keep sensor
faults from becoming heater commands. It also lets me try moving a simulated
two-joint arm around an obstacle while recording the timing of each control
step. No heater or robot is connected.

From the repository root, with Rust installed:

```sh
cargo test --manifest-path robot_controller/Cargo.toml
cargo run --manifest-path robot_controller/Cargo.toml -p desk-supervisor -- /tmp/desk-run.csv
.venv/bin/python -m can_monitor.thermal --rust-csv /tmp/desk-run.csv --output /tmp/desk-run.jsonl
.venv/bin/python -m can_monitor.replay /tmp/desk-run.jsonl
```

The run file must be new, so I cannot accidentally overwrite a recording. Each
run records 100 exchanges, temperature, heater percentage, target and actual
joint positions, and scheduling jitter, meaning how late a step starts. The
last two commands turn that actual run into the same CAN recording used by the
desk-node decoder. The shared [CAN guide](../docs/can-control.md) covers faults,
physical units, rate summaries and the 64-byte CAN FD test.

## Firmware and feedback

`core` compiles without Rust's standard library (`no_std`), so the feedback
logic does not depend on an operating system or heap. Small interfaces model
ADC supply-voltage sensing, SPI temperature sensing, a GPIO interlock, PWM
heater output and an I2C display. The firmware uses all five on each feedback
step. A sensor failure, low supply or open interlock sets heater output to zero.
The controller limits both its output and accumulated error to prevent windup.
These peripheral implementations are explicitly simulated, not chip drivers.

`embedded` builds an actual ARM ELF and executes that same logic in headless
QEMU. GitHub Actions cross-compiles for `thumbv7m-none-eabi`, runs the ELF and
requires its success exit. This checks the no_std target as well as host tests.

The Linux supervisor exchanges fixed-size, CRC-16-checked frames with the
firmware simulator through a real pseudo-terminal, the operating system's
virtual serial device. It checks counters, sizes, values and checksums. It uses
absolute deadlines based on a monotonic clock to avoid accumulating a full
period's drift on each step. `--fifo` requests Linux's SCHED_FIFO scheduling
policy and records whether the request succeeded. Ordinary runs need no special
permission. A CSV's measured jitter is evidence about that run, not a hard
real-time guarantee, especially on a shared CI runner.

## Motion simulation

The path planner finds the shortest four-neighbour route through a bounded grid
around blocked cells. Rest-to-rest cubic segments set their duration from
analytic speed and acceleration limits. Two PID loops drive a damped two-joint
plant, with bounded torque and integral terms. Tests check unreachable paths,
obstacle avoidance, trajectory limits and final tracking error. The supervisor's
short run records only the first part of the longer planned motion; the unit
test executes the whole trajectory and settling interval. Grid positions are
joint-space coordinates; this is not a physical arm's collision model or inverse
kinematics. The complete project remains a simulation, with no hardware timing
or electrical validation.
