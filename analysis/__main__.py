"""Read existing room logs without changing the originals."""
import argparse
from pathlib import Path
import sys

from .core import analyze
from .logs import CHANNELS, load_csv, load_database
from .report import write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--csv', type=Path, help='timestamp and adapter channel columns, in original integer units')
    source.add_argument('--database', type=Path, help='adapter SQLite file, opened read-only')
    parser.add_argument('--device', help='exact adapter device ID; required for database')
    parser.add_argument('--channel', choices=CHANNELS, default='temperature')
    parser.add_argument('--start', type=float, help='inclusive epoch seconds, database only')
    parser.add_argument('--end', type=float, help='inclusive epoch seconds, database only')
    parser.add_argument('--cutoff-hz', type=float, required=True, help='per-pass -3 dB cutoff, below half the sample rate')
    parser.add_argument('--median-window', type=int, default=5)
    parser.add_argument('--signal-max-hz', type=float, help='SNR signal-band edge; defaults to cutoff')
    parser.add_argument('--output', type=Path, required=True, help='new report directory (must not exist)')
    args = parser.parse_args(argv)
    if args.database and not args.device:
        parser.error('--database requires --device')
    if args.csv and (args.device is not None or args.start is not None or args.end is not None):
        parser.error('--device, --start and --end apply only to --database')
    try:
        data = (load_csv(args.csv, args.channel) if args.csv else
                load_database(args.database, args.device, args.channel, args.start, args.end))
        result = analyze(data, args.cutoff_hz, args.median_window, args.signal_max_hz)
        write_report(args.output, data, result)
    except (OSError, ValueError, UnicodeError) as exc:
        print(f'analysis: {exc}', file=sys.stderr)
        return 2
    print(f"Analyzed {len(data.values)} readings; report: {args.output / 'report.md'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
