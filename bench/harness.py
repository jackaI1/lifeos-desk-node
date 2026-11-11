"""Run the power-up check: set the rail, capture both rails, apply the limits, write results.

One run does these steps on the bench supply and scope:

1. identify both instruments,
2. set VBUS to the configured voltage and read it back,
3. turn the supply output on, wait for the scope (*OPC?),
4. read the input current,
5. capture CHAN1 (VBUS) and CHAN2 (3V3),
6. turn the output off and close the instruments.

Results go to a folder named by UTC time and the injected faults:
  <out>/<stamp>-<faults>/<stamp>_measurements.csv   one row per check
  <out>/<stamp>-<faults>/<stamp>_capture.csv        the sampled waveforms
  <out>/<stamp>-<faults>/report.md                  a short report
"""

import csv
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence

import pyvisa

from bench.instruments import InstrumentError, Scope, Supply
from bench.limits import Check, Limits, evaluate, load_limits
from bench.simulator import Scenario, apply_faults, write_device_file

HERE = Path(__file__).resolve().parent
DEFAULT_LIMITS = HERE / "limits.toml"
DEFAULT_OUT = HERE / "build" / "runs"
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"


@dataclass
class RunResult:
    run_dir: Path
    stamp: str
    faults: tuple
    scenario: Scenario
    checks: List[Check]
    steps: List[str] = field(default_factory=list)
    measurements_csv: Optional[Path] = None
    report: Optional[Path] = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def _shutdown(supply: Optional[Supply], scope: Optional[Scope], rm) -> List[str]:
    """Output off, close the instruments and the resource manager. Returns any problems."""
    problems = []
    if supply is not None:
        try:
            supply.output(False)
        except InstrumentError as exc:
            problems.append(f"output off failed: {exc}")
    for inst in (supply, scope):
        if inst is None:
            continue
        try:
            inst.close()
        except Exception as exc:  # close errors must not hide the measurement result
            problems.append(f"closing {inst.resource} failed: {exc}")
    rm.close()
    return problems


def capture(limits: Limits, scenario: Scenario, sim_dir: Path, steps: List[str]):
    """Run steps 1-6 against the simulated instruments. Returns (current_a, ch1, ch2)."""
    device_file = write_device_file(scenario, sim_dir / "bench-sim.yaml")
    rm = pyvisa.ResourceManager(f"{device_file}@sim")
    supply = scope = None
    try:
        supply = Supply(rm)
        scope = Scope(rm)
        steps.append(f"1. identified {supply.resource}: {supply.identify()}")
        steps.append(f"1. identified {scope.resource}: {scope.identify()}")
        readback = supply.set_voltage(limits.vbus_setpoint_v, limits.setpoint_tolerance_v)
        steps.append(f"2. set VBUS to {limits.vbus_setpoint_v:.3f} V, read back {readback:.3f} V")
        supply.output(True)
        scope.wait_complete()
        steps.append("3. output on, scope capture complete (*OPC? = 1)")
        current = supply.measure_current_a()
        steps.append(f"4. input current {current * 1000:.1f} mA")
        ch1 = scope.waveform(1)
        ch2 = scope.waveform(2)
        steps.append(f"5. captured CHAN1 (VBUS) and CHAN2 (3V3): {len(ch1.samples)} points, "
                     f"{ch1.dt_s * 1e6:.2f} us apart")
    except BaseException:
        _shutdown(supply, scope, rm)  # keep the original error
        raise
    problems = _shutdown(supply, scope, rm)
    steps.append("6. output off, instruments closed" if not problems else "6. " + "; ".join(problems))
    if problems:
        raise InstrumentError("; ".join(problems))
    return current, ch1, ch2


def run_bench(limits_path=DEFAULT_LIMITS, *, faults: Sequence[str] = (), out_root=DEFAULT_OUT,
              stamp: Optional[str] = None, limits: Optional[Limits] = None) -> RunResult:
    limits = limits or load_limits(limits_path)
    base = Scenario(vbus_setpoint_v=limits.vbus_setpoint_v, window_ms=limits.window_ms,
                    points=limits.points)
    scenario = apply_faults(base, faults)
    stamp = stamp or datetime.now(timezone.utc).strftime(STAMP_FORMAT)
    label = "+".join(scenario.faults) or "nominal"
    run_dir = Path(out_root) / f"{stamp}-{label}"
    steps: List[str] = []
    with tempfile.TemporaryDirectory(prefix="bench-sim-") as sim_dir:
        current, ch1, ch2 = capture(limits, scenario, Path(sim_dir), steps)
    checks = evaluate(limits,
                      vbus_times=ch1.times(), vbus_volts=ch1.samples,
                      v3_times=ch2.times(), v3_volts=ch2.samples,
                      input_current_a=current)
    result = RunResult(run_dir=run_dir, stamp=stamp, faults=scenario.faults,
                       scenario=scenario, checks=checks, steps=steps)
    run_dir.mkdir(parents=True, exist_ok=True)
    result.measurements_csv = write_measurements(result)
    write_capture(run_dir / f"{stamp}_capture.csv", ch1, ch2)
    result.report = write_report(result, limits)
    return result


def _fmt(value: Optional[float]) -> str:
    return "" if value is None else f"{value:.6g}"


def write_measurements(result: RunResult) -> Path:
    path = result.run_dir / f"{result.stamp}_measurements.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run", "faults", "check", "measured", "low", "high", "unit", "result"])
        for check in result.checks:
            writer.writerow([result.stamp, "+".join(result.faults) or "none", check.name,
                             _fmt(check.measured), _fmt(check.low), _fmt(check.high), check.unit,
                             "PASS" if check.passed else "FAIL"])
    return path


def write_capture(path: Path, ch1, ch2) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time_ms", "vbus_v", "v3v3_v"])
        for t, a, b in zip(ch1.times(), ch1.samples, ch2.samples):
            writer.writerow([f"{t * 1000:.4f}", f"{a:.5f}", f"{b:.5f}"])


def write_report(result: RunResult, limits: Limits) -> Path:
    verdict = "PASS" if result.passed else "FAIL"
    lines = [
        f"# Power-up bench check: {verdict}",
        "",
        f"- Run: {result.stamp} (UTC)",
        f"- Injected faults: {', '.join(result.faults) or 'none'}",
        f"- Scenario: {result.scenario.describe()}",
        "- Instruments: simulated SCPI supply and scope (pyvisa-sim). No lab hardware was used.",
        "",
        "## Steps",
        "",
        *[f"- {step}" for step in result.steps],
        "",
        "## Checks",
        "",
        "| check | measured | limit | result | meaning |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in result.checks:
        measured = "no crossing" if check.measured is None else f"{check.measured:.4g} {check.unit}"
        limit = f"{check.low:.4g} to {check.high:.4g} {check.unit}"
        lines.append(f"| {check.name} | {measured} | {limit} | "
                     f"{'PASS' if check.passed else 'FAIL'} | {check.description} |")
    failing = [c.name for c in result.checks if not c.passed]
    lines += [
        "",
        f"Failing checks: {', '.join(failing)}." if failing else "All checks passed.",
        "",
        "The limits come from `bench/limits.toml`. They are bring-up targets, not datasheet values.",
        "A pass here shows the check logic works on simulated rails; it is not a measurement of the board.",
        "",
    ]
    path = result.run_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
