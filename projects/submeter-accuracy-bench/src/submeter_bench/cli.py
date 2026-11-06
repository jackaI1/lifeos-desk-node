"""Run a reproducible simulated production batch without services or hardware."""

import argparse
from pathlib import Path

from .batch import BatchConfig, run_batch
from .report import write_report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Simulated electricity meter accuracy bench")
    parser.add_argument("--units", type=int, default=40)
    parser.add_argument("--baseline-units", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--gain-drift-pct",
        type=float,
        default=0.035,
        help="current gain percentage points added per successive unit (default .035)",
    )
    parser.add_argument(
        "--phase-drift-deg",
        type=float,
        default=0,
        help="additional current lag in degrees per successive unit",
    )
    parser.add_argument(
        "--offset-drift-w",
        type=float,
        default=0,
        help="residual active-power watts per element per successive unit",
    )
    parser.add_argument("--output", type=Path, default=Path("reports/demo"))
    parser.add_argument(
        "--fail-on-unit-failure",
        action="store_true",
        help="exit 1 if any unit fails an accuracy point; control alarms alone do not fail",
    )
    args = parser.parse_args(argv)
    try:
        config = BatchConfig(
            args.seed,
            args.units,
            args.baseline_units,
            args.gain_drift_pct,
            args.phase_drift_deg,
            args.offset_drift_w,
        )
        batch = run_batch(config)
        write_report(batch, args.output)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    summary = batch.summary
    print("SIMULATED DATA, not a certified test.")
    print(f"{summary['passed_units']}/{summary['total_units']} units passed all 24 points.")
    print(
        f"First control alarm: {summary['first_control_alarm']}; "
        f"first failed unit: {summary['first_failed_unit']}."
    )
    print(f"Reports: {args.output.resolve() / 'report.md'}")
    return int(args.fail_on_unit_failure and summary["failed_units"] > 0)
