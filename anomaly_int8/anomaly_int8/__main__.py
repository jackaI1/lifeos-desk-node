"""Command line: make the example log, or train, quantize and compare the detector.

    python -m anomaly_int8 make-log --out data/desk_room_log.csv
    python -m anomaly_int8 run --log data/desk_room_log.csv
"""
import argparse
from pathlib import Path
import sys

from . import data, pipeline

HERE = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('make-log', help='write the synthetic room log with labelled faults')
    make.add_argument('--out', type=Path, default=HERE / 'data' / 'desk_room_log.csv')
    make.add_argument('--days', type=int, default=21)
    run = sub.add_parser('run', help='train, quantize, export headers and write the comparison')
    run.add_argument('--log', type=Path, default=HERE / 'data' / 'desk_room_log.csv')
    run.add_argument('--build', type=Path, default=HERE / 'build')
    run.add_argument('--docs', type=Path, default=HERE / 'docs')
    run.add_argument('--c', type=Path, default=HERE / 'c')
    args = parser.parse_args(argv)
    try:
        if args.command == 'make-log':
            timestamps, temperature, humidity, anomaly = data.make_log(days=args.days)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            data.write_log(args.out, timestamps, temperature, humidity, anomaly)
            print(f'wrote {len(timestamps)} readings to {args.out}')
        else:
            results = pipeline.build(args.log, args.build, args.docs, args.c)
            f, i = results['float'], results['int8']
            print(f"float accuracy {f['accuracy']:.4f}, int8 accuracy {i['accuracy']:.4f}, "
                  f"agreement {results['comparison']['decision_agreement']:.4f}, "
                  f"int8 bytes {i['int8_bytes']}")
    except ValueError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
