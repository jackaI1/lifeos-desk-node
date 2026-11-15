"""Temperature sweep for the desk node: set the chamber, wait, capture, log, judge.

For each setpoint the sweep does, on the instruments it names:

1. Chamber: set the setpoint and read it back (a refused value stops the run).
2. Chamber: wait until the reference probe is inside the settling band and the
   chamber reports SETTLED. Give up after the timeout and raise SettleTimeout.
3. Function generator: set the bus frequency, read it back, turn the output on.
4. Scope: wait for capture complete (*OPC?), then fetch CHAN1 (3V3 rail) and
   CHAN2 (SDA line).
5. DUT: read the SHT31 temperature (READ:TEMP?).
6. Compute: SHT31 error against the chamber reference, rail mean and ripple,
   SDA 30 %-70 % rise time from the captured samples.
7. Judge each step against bench/sweep_limits.toml and write the results.

Results go to bench/build/sweeps/<stamp>-<label>/:
  measurements.csv   one row per step and check
  report.md          table, plots, steps and limits
  sweep_plots.png    SHT31 error, 3V3 rail and ripple, SDA rise against temperature

The chamber, function generator, scope and DUT are simulated by default
(bench/sweep_sim.py). Pass real resource strings to use hardware.
"""

from __future__ import annotations

import csv
import tempfile
import time
import tomllib
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import pyvisa
from pyvisa.errors import VisaIOError

from bench.instruments import InstrumentError, Scope, _Instrument
from bench.sweep_sim import (CHAMBER_RESOURCE, DUT_RESOURCE, FGEN_RESOURCE, SWEEP_FAULTS,
                             StepModel, parse_faults, write_device_file)
from bench.simulator import SCOPE_RESOURCE

HERE = Path(__file__).resolve().parent
DEFAULT_LIMITS = HERE / "sweep_limits.toml"
DEFAULT_OUT = HERE / "build" / "sweeps"
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
I2C_RISE_LIMIT_S = {100_000.0: 1.0e-6, 400_000.0: 300e-9}


class SweepError(InstrumentError):
    """The sweep cannot judge a step: no edge in the capture, a bad limits file, and so on."""


class SettleTimeout(InstrumentError):
    """The chamber did not reach the setpoint and settle within the timeout."""


class SetpointError(InstrumentError):
    """An instrument read back a different setting from the one it was given."""


@dataclass(frozen=True)
class SweepLimits:
    setpoints_c: Tuple[float, ...]
    bus_hz: float
    settle_timeout_s: float
    settle_poll_s: float
    settle_band_c: float
    sht_max_error_c: float
    rail_nominal_v: float
    rail_tolerance_fraction: float
    ripple_max_mvpp: float
    rise_max_s: float

    @property
    def rail_low_v(self) -> float:
        return self.rail_nominal_v * (1.0 - self.rail_tolerance_fraction)

    @property
    def rail_high_v(self) -> float:
        return self.rail_nominal_v * (1.0 + self.rail_tolerance_fraction)


def load_sweep_limits(path=DEFAULT_LIMITS) -> SweepLimits:
    try:
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SweepError(f"cannot read limits file {path}: {exc}") from exc
    try:
        chamber, sht, rail, i2c = raw["chamber"], raw["sht31"], raw["rail_3v3"], raw["i2c"]
        bus_hz = float(i2c["bus_hz"])
        setpoints = tuple(float(v) for v in chamber["setpoints_c"])
        settle_timeout_s = float(chamber["settle_timeout_s"])
        settle_poll_s = float(chamber["settle_poll_s"])
        settle_band_c = float(chamber["settle_band_c"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SweepError(f"limits file {path} is missing or has a bad value: {exc}") from exc
    if bus_hz not in I2C_RISE_LIMIT_S:
        raise SweepError(f"bus_hz must be 100000 or 400000, not {bus_hz:g}")
    if not setpoints:
        raise SweepError("setpoints_c is empty")
    if settle_timeout_s <= 0 or settle_poll_s < 0 or settle_band_c <= 0:
        raise SweepError("settling timeout and band must be positive; the poll may be 0")
    return SweepLimits(
        setpoints_c=setpoints,
        bus_hz=bus_hz,
        settle_timeout_s=settle_timeout_s,
        settle_poll_s=settle_poll_s,
        settle_band_c=settle_band_c,
        sht_max_error_c=float(sht["max_error_c"]),
        rail_nominal_v=float(rail["nominal_v"]),
        rail_tolerance_fraction=float(rail["tolerance_fraction"]),
        ripple_max_mvpp=float(rail["max_ripple_mvpp"]),
        rise_max_s=I2C_RISE_LIMIT_S[bus_hz],
    )


class SimClock:
    """Simulated time for the simulated instruments: sleeping advances it, so no real time passes."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------------------------------------------- instruments

class _SweepInstrument(_Instrument):
    """Treats a blank reply as no answer. Some VISA backends return '' rather than a timeout."""

    def _query(self, command: str) -> str:
        reply = super()._query(command)
        if reply == "":
            raise InstrumentError(f"{self.resource} gave no reply to {command!r}")
        return reply


class Chamber(_SweepInstrument):
    """Programmable environmental chamber: setpoint, reference probe and settled status."""

    def set_setpoint(self, celsius: float) -> float:
        self._write(f":TEMP:SET {celsius:.2f}")
        readback = float(self._query(":TEMP:SET?"))
        if abs(readback - celsius) > 0.05:
            raise SetpointError(f"chamber set to {celsius:.2f} C but reads back {readback:.2f} C")
        return readback

    def probe(self) -> float:
        return float(self._query(":TEMP:PROBE?"))

    def status(self) -> str:
        return self._query(":TEMP:STAT?").strip().upper()


class FunctionGenerator(_SweepInstrument):
    """Function generator that drives the bus clock for the I2C capture."""

    def set_frequency(self, hz: float) -> float:
        self._write(f"SOUR1:FREQ {hz:.1f}")
        readback = float(self._query("SOUR1:FREQ?"))
        if abs(readback - hz) > 0.5:
            raise SetpointError(f"generator set to {hz:.1f} Hz but reads back {readback:.1f} Hz")
        return readback

    def output(self, on: bool) -> None:
        self._write(f"OUTP1 {'ON' if on else 'OFF'}")


class Dut(_SweepInstrument):
    """The desk node's SHT31 reading, read back over its serial bridge."""

    def read_temperature(self) -> float:
        return float(self._query("READ:TEMP?"))


# ---------------------------------------------------------------- measurements

def wait_for_settle(chamber: Chamber, setpoint: float, *, band_c: float, timeout_s: float,
                    poll_s: float, clock: Callable[[], float] = time.monotonic,
                    sleep: Callable[[float], None] = time.sleep) -> float:
    """Poll the chamber until its probe is inside the band and it reports SETTLED.

    Returns the seconds it took. Raises SettleTimeout if that does not happen in time.
    """
    start = clock()
    last = None
    while True:
        probe = chamber.probe()
        status = chamber.status()
        last = (probe, status)
        if abs(probe - setpoint) <= band_c and status == "SETTLED":
            return clock() - start
        if clock() - start >= timeout_s:
            raise SettleTimeout(
                f"chamber did not settle at {setpoint:.1f} C within {timeout_s:.0f} s "
                f"(last probe {last[0]:.2f} C, status {last[1]})")
        sleep(poll_s)


def rise_time_s(times_s: List[float], volts: List[float], vdd: float = 3.3) -> float:
    """30 %-70 % rise time of the first rising edge after the line goes low."""
    lo, hi = 0.3 * vdd, 0.7 * vdd
    n = len(volts)
    if n < 3 or len(times_s) != n:
        raise SweepError("capture too short to measure a rise")
    try:
        first_low = next(k for k in range(n) if volts[k] < lo)
        cross_lo = next(k for k in range(first_low + 1, n) if volts[k - 1] < lo <= volts[k])
        cross_hi = next(k for k in range(cross_lo, n) if volts[k - 1] < hi <= volts[k])
    except StopIteration as exc:
        raise SweepError("no complete rising edge in the SDA capture") from exc

    def at(level: float, k: int) -> float:
        dv = volts[k] - volts[k - 1]
        frac = (level - volts[k - 1]) / dv
        return times_s[k - 1] + frac * (times_s[k] - times_s[k - 1])

    return at(hi, cross_hi) - at(lo, cross_lo)


# ---------------------------------------------------------------- the sweep

@dataclass
class StepResult:
    setpoint_c: float
    probe_c: float
    sht_c: float
    sht_error_c: float
    rail_mean_v: float
    ripple_mvpp: float
    rise_s: float
    settle_s: float
    passed: bool
    failing: List[str] = field(default_factory=list)


@dataclass
class SweepResult:
    run_dir: Path
    stamp: str
    faults: Tuple[str, ...]
    limits: SweepLimits
    steps: List[StepResult]
    log: List[str]
    report: Optional[Path] = None

    @property
    def passed(self) -> bool:
        return bool(self.steps) and all(s.passed for s in self.steps)


def _judge(step: StepResult, limits: SweepLimits) -> None:
    checks = [
        ("sht31_error", abs(step.sht_error_c) <= limits.sht_max_error_c),
        ("rail_3v3", limits.rail_low_v <= step.rail_mean_v <= limits.rail_high_v),
        ("ripple_3v3", step.ripple_mvpp <= limits.ripple_max_mvpp),
        ("sda_rise", step.rise_s <= limits.rise_max_s),
    ]
    step.failing = [name for name, ok in checks if not ok]
    step.passed = not step.failing


def _shutdown(fgen: Optional[FunctionGenerator], chamber: Optional[Chamber], scope: Optional[Scope],
              dut: Optional[Dut], rm) -> List[str]:
    problems = []
    if fgen is not None:
        try:
            fgen.output(False)
        except InstrumentError as exc:
            problems.append(f"generator output off failed: {exc}")
    for inst in (fgen, chamber, scope, dut):
        if inst is None:
            continue
        try:
            inst.close()
        except Exception as exc:  # close errors must not hide the measurement result
            problems.append(f"closing {inst.resource} failed: {exc}")
    rm.close()
    return problems


def run_sweep(*, limits: SweepLimits, faults=(), out_root=DEFAULT_OUT, stamp: Optional[str] = None,
              resources: Optional[dict] = None, clock=None, sleep=None) -> SweepResult:
    """Run every setpoint and return the results. Writes the report folder as well.

    resources=None runs the simulated instruments on a simulated clock. Pass a dict with
    keys chamber, fgen, scope and dut (VISA resource strings) to use real instruments;
    those use the wall clock unless clock and sleep are given.
    """
    chosen = parse_faults(faults)
    simulated = resources is None
    resources = resources or {}
    if simulated:
        sim_clock = SimClock()
        clock = clock or sim_clock
        sleep = sleep or sim_clock.advance
    else:
        clock = clock or time.monotonic
        sleep = sleep or time.sleep
    stamp = stamp or datetime.now(timezone.utc).strftime(STAMP_FORMAT)
    label = "+".join(chosen) or "nominal"
    run_dir = Path(out_root) / f"{stamp}-{label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    steps: List[StepResult] = []
    log: List[str] = []
    sim_dir = Path(tempfile.mkdtemp(prefix="bench-sweep-sim-"))
    try:
        for setpoint in limits.setpoints_c:
            model = StepModel(setpoint_c=setpoint, bus_hz=limits.bus_hz, faults=chosen)
            if simulated:
                device_file = write_device_file(model, sim_dir / f"step-{setpoint:g}.yaml")
                rm = pyvisa.ResourceManager(f"{device_file}@sim")
                names = (CHAMBER_RESOURCE, FGEN_RESOURCE, SCOPE_RESOURCE, DUT_RESOURCE)
            else:
                rm = pyvisa.ResourceManager()
                names = (resources["chamber"], resources["fgen"], resources["scope"], resources["dut"])
            step = _run_one(rm, model, limits, log, clock, sleep, *names)
            steps.append(step)
    finally:
        for child in sim_dir.glob("*.yaml"):
            child.unlink(missing_ok=True)
        try:
            sim_dir.rmdir()
        except OSError:
            pass
    result = SweepResult(run_dir=run_dir, stamp=stamp, faults=chosen, limits=limits, steps=steps,
                         log=log)
    result.report = write_outputs(result)
    return result


def _run_one(rm, model: StepModel, limits: SweepLimits, log: List[str], clock, sleep,
             chamber_res: str, fgen_res: str, scope_res: str, dut_res: str) -> StepResult:
    chamber = fgen = scope = dut = None
    try:
        chamber = Chamber(rm, chamber_res)
        fgen = FunctionGenerator(rm, fgen_res)
        scope = Scope(rm, scope_res)
        dut = Dut(rm, dut_res)
        log.append(f"{model.setpoint_c:g} C: identified {chamber.identify()} / {dut.identify()}")
        chamber.set_setpoint(model.setpoint_c)
        log.append(f"{model.setpoint_c:g} C: setpoint set and read back")
        settle_s = wait_for_settle(chamber, model.setpoint_c, band_c=limits.settle_band_c,
                                   timeout_s=limits.settle_timeout_s, poll_s=limits.settle_poll_s,
                                   clock=clock, sleep=sleep)
        log.append(f"{model.setpoint_c:g} C: settled in {settle_s:.1f} s")
        probe = chamber.probe()
        fgen.set_frequency(limits.bus_hz)
        fgen.output(True)
        scope.wait_complete()
        rail = scope.waveform(1)
        sda = scope.waveform(2)
        sht = dut.read_temperature()
        rise = rise_time_s(sda.times(), sda.samples)
        mean = sum(rail.samples) / len(rail.samples)
        ripple = (max(rail.samples) - min(rail.samples)) * 1000.0
        log.append(f"{model.setpoint_c:g} C: captured 3V3 and SDA, SHT31 read {sht:.2f} C")
    except BaseException:
        _shutdown(fgen, chamber, scope, dut, rm)
        raise
    problems = _shutdown(fgen, chamber, scope, dut, rm)
    if problems:
        raise InstrumentError("; ".join(problems))
    step = StepResult(setpoint_c=model.setpoint_c, probe_c=probe, sht_c=sht,
                      sht_error_c=sht - probe, rail_mean_v=mean, ripple_mvpp=ripple,
                      rise_s=rise, settle_s=settle_s, passed=False)
    _judge(step, limits)
    return step


# ---------------------------------------------------------------- outputs

def write_csv(result: SweepResult) -> Path:
    path = result.run_dir / "measurements.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["setpoint_c", "probe_c", "sht31_c", "sht31_error_c", "rail_3v3_mean_v",
                         "ripple_mvpp", "sda_rise_ns", "settle_s", "result", "failing"])
        for s in result.steps:
            writer.writerow([f"{s.setpoint_c:g}", f"{s.probe_c:.3f}", f"{s.sht_c:.3f}",
                             f"{s.sht_error_c:+.3f}", f"{s.rail_mean_v:.4f}", f"{s.ripple_mvpp:.2f}",
                             f"{s.rise_s * 1e9:.1f}", f"{s.settle_s:.1f}",
                             "PASS" if s.passed else "FAIL", "+".join(s.failing)])
    return path


def write_plots(result: SweepResult) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = [s.setpoint_c for s in result.steps]
    limits = result.limits
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    axes[0].plot(x, [s.sht_error_c for s in result.steps], "o-", color="#1f77b4")
    axes[0].axhline(limits.sht_max_error_c, color="#d62728", linestyle="--", linewidth=1)
    axes[0].axhline(-limits.sht_max_error_c, color="#d62728", linestyle="--", linewidth=1)
    axes[0].set_title("SHT31 minus chamber reference (C)")
    axes[1].plot(x, [s.rail_mean_v for s in result.steps], "o-", color="#2ca02c")
    axes[1].axhline(limits.rail_low_v, color="#d62728", linestyle="--", linewidth=1)
    axes[1].axhline(limits.rail_high_v, color="#d62728", linestyle="--", linewidth=1)
    axes[1].set_title("3V3 rail mean (V)")
    axes[2].plot(x, [s.rise_s * 1e9 for s in result.steps], "o-", color="#9467bd", label="SDA rise")
    axes[2].axhline(limits.rise_max_s * 1e9, color="#d62728", linestyle="--", linewidth=1,
                    label="I2C limit")
    axes[2].set_title(f"SDA 30-70 % rise at {limits.bus_hz / 1000:g} kHz (ns)")
    axes[2].legend(fontsize=8)
    for ax in axes:
        ax.set_xlabel("chamber setpoint (C)")
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = result.run_dir / "sweep_plots.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def write_outputs(result: SweepResult) -> Path:
    write_csv(result)
    write_plots(result)
    verdict = "PASS" if result.passed else "FAIL"
    lines = [
        f"# Temperature sweep: {verdict}",
        "",
        f"- Run: {result.stamp} (UTC); injected faults: {', '.join(result.faults) or 'none'}",
        f"- Setpoints: {', '.join(f'{s:g}' for s in result.limits.setpoints_c)} C, "
        f"bus {result.limits.bus_hz / 1000:g} kHz",
        "- Instruments: simulated chamber, function generator, scope and DUT (pyvisa-sim). "
        "No lab hardware was used, so these numbers show the harness works, not the board.",
        "",
        "| setpoint | probe | SHT31 | error | 3V3 mean | ripple | SDA rise | settle | result |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in result.steps:
        lines.append(
            f"| {s.setpoint_c:g} C | {s.probe_c:.2f} C | {s.sht_c:.2f} C | {s.sht_error_c:+.2f} C | "
            f"{s.rail_mean_v:.3f} V | {s.ripple_mvpp:.1f} mVpp | {s.rise_s * 1e9:.0f} ns | "
            f"{s.settle_s:.0f} s | {'PASS' if s.passed else 'FAIL: ' + ', '.join(s.failing)} |")
    limits = result.limits
    lines += [
        "",
        "## Limits",
        "",
        f"- SHT31 against the chamber reference: within +/-{limits.sht_max_error_c:g} C "
        f"(bring-up target; the SHT31 datasheet typical is +/-0.3 C).",
        f"- 3V3 rail mean: {limits.rail_low_v:.3f} to {limits.rail_high_v:.3f} V; ripple at most "
        f"{limits.ripple_max_mvpp:g} mVpp (same as the power-up bench check).",
        f"- SDA 30 %-70 % rise: at most {limits.rise_max_s * 1e9:.0f} ns at "
        f"{limits.bus_hz / 1000:g} kHz (I2C fast-mode 300 ns, standard-mode 1000 ns).",
        f"- Settling: probe within {limits.settle_band_c:g} C and status SETTLED, "
        f"within {limits.settle_timeout_s:g} s.",
        "",
        "## Steps",
        "",
        *[f"- {line}" for line in result.log],
        "",
        "![Sweep plots](sweep_plots.png)",
        "",
    ]
    path = result.run_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv=None) -> int:
    """python -m bench.sweep [--inject sensor-drift,ripple] [--bus-khz 100|400] [--out DIR]

    Simulated instruments run by default. To use real instruments, give all four resource
    strings: --chamber, --fgen, --scope and --dut.

    Exit status: 0 every step passed, 1 at least one check failed, 2 the bench could not
    run (settle timeout, instrument error, setpoint refused, bad limits).
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Temperature sweep of the desk node.")
    parser.add_argument("--limits", default=str(DEFAULT_LIMITS), help="limits file")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="folder for timestamped results")
    parser.add_argument("--inject", default="none", help=f"faults: {', '.join(SWEEP_FAULTS)}")
    parser.add_argument("--bus-khz", type=float, choices=(100.0, 400.0),
                        help="override the bus speed from the limits file")
    for name in ("chamber", "fgen", "scope", "dut"):
        parser.add_argument(f"--{name}", help=f"VISA resource for the {name} (real hardware)")
    args = parser.parse_args(argv)
    real = [getattr(args, n) for n in ("chamber", "fgen", "scope", "dut")]
    if any(real) and not all(real):
        parser.error("real hardware needs all four of --chamber, --fgen, --scope and --dut")
    resources = dict(zip(("chamber", "fgen", "scope", "dut"), real)) if all(real) else None
    faults = [name for name in args.inject.split(",") if name.strip()]
    try:
        limits = load_sweep_limits(args.limits)
        if args.bus_khz:
            limits = replace(limits, bus_hz=args.bus_khz * 1000.0,
                             rise_max_s=I2C_RISE_LIMIT_S[args.bus_khz * 1000.0])
        result = run_sweep(limits=limits, faults=faults, out_root=args.out, resources=resources)
    except (SweepError, ValueError, InstrumentError, VisaIOError, OSError) as exc:
        print(f"bench error: {exc}", file=sys.stderr)
        return 2
    print(f"sweep {result.stamp} faults={'+'.join(result.faults) or 'none'}")
    for step in result.steps:
        print(f"  {step.setpoint_c:>5g} C  SHT31 error {step.sht_error_c:+.2f} C  "
              f"ripple {step.ripple_mvpp:5.1f} mVpp  SDA {step.rise_s * 1e9:6.0f} ns  "
              f"{'PASS' if step.passed else 'FAIL: ' + ', '.join(step.failing)}")
    print(f"result: {'PASS' if result.passed else 'FAIL'}; report: {result.report}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
