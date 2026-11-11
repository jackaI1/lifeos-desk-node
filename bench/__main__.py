"""Command-line entry point: python -m bench [--inject ripple,late-rail] [--out DIR]

Exit status: 0 every check passed, 1 at least one check failed, 2 the bench
could not run (bad config, instrument error, setpoint refused).
"""

import argparse
import sys

from bench.harness import DEFAULT_LIMITS, DEFAULT_OUT, run_bench
from bench.instruments import InstrumentError
from bench.limits import ConfigError
from bench.simulator import FAULT_NAMES


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Power-up and ripple check on simulated bench instruments.")
    parser.add_argument("--config", default=str(DEFAULT_LIMITS), help="limits file (default: bench/limits.toml)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="folder for timestamped results")
    parser.add_argument("--inject", default="none",
                        help=f"comma-separated faults to add: {', '.join(FAULT_NAMES)} (default: none)")
    args = parser.parse_args(argv)
    faults = [name for name in args.inject.split(",") if name.strip()]
    try:
        result = run_bench(args.config, faults=faults, out_root=args.out)
    except (ConfigError, ValueError, InstrumentError, OSError) as exc:
        print(f"bench error: {exc}", file=sys.stderr)
        return 2
    print(f"run {result.stamp} faults={'+'.join(result.faults) or 'none'}")
    for check in result.checks:
        measured = "no crossing" if check.measured is None else f"{check.measured:.4g}"
        print(f"  {check.name:<28} {measured:>12} {check.unit:<5} {'PASS' if check.passed else 'FAIL'}")
    print(f"result: {'PASS' if result.passed else 'FAIL'}; report: {result.report}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
