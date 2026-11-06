"""Generate a reproducible five-minute room log and compare it with its true values."""
import argparse
from pathlib import Path
import sys

from .core import analyze
from .report import write_report
from .simulate import simulate, write_csv


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('analysis/build/demo'))
    parser.add_argument('--seed', type=int, default=7)
    args = parser.parse_args(argv)
    try:
        data, manifest = simulate(args.seed)
        result = analyze(data, cutoff_hz=1/3600, median_window=5)
        write_report(args.output, data, result, synthetic=True, manifest=manifest)
        write_csv(args.output / 'input.csv', data)
    except (OSError, ValueError) as exc:
        print(f'analysis demo: {exc}', file=sys.stderr)
        return 2
    print(f"Synthetic RMSE: {result['truth']['raw_rmse']:.4f} -> "
          f"{result['truth']['filtered_rmse']:.4f} C; report: {args.output / 'report.md'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
