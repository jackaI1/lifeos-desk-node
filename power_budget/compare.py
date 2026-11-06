"""Compare Rev A and Rev B; all values are calculated estimates."""
import argparse
import json
from .model import Assumptions, compare, sleep_seconds


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for field, value in Assumptions().__dict__.items():
        p.add_argument('--' + field.replace('_', '-'), type=float, default=value,
                       help='explicit assumption; see docs/power-and-battery.md')
    p.add_argument('--sdkconfig', help='read only CONFIG_DESK_UPDATE_SECONDS from this firmware config')
    p.add_argument('--json', action='store_true')
    args = vars(p.parse_args())
    config, as_json = args.pop('sdkconfig'), args.pop('json')
    try:
        result = compare(Assumptions(**args), sleep_seconds(config))
    except (ValueError, OSError) as e:
        p.error(str(e))
    if as_json:
        print(json.dumps(result, indent=2, allow_nan=False))
        return
    print(result['label'])
    print(f"Sleep {result['sleep_s']}s + assumed awake {result['assumptions']['awake_s']}s = {result['cycle_s']}s per cycle")
    print('Contribution (mA)                                     Rev A     Rev B')
    for k, v in result['boards']['A']['parts_ma'].items():
        print(f"{k:52s} {v:8.5f} {result['boards']['B']['parts_ma'][k]:8.5f}")
    for rev, board in result['boards'].items():
        print(f"Rev {rev}: {board['average_ma']:.4f} mA, {board['runtime_hours']:.2f} h; {board['runtime_basis']}")
    print(f"Calculated input-current reduction: {result['current_reduction_percent']:.2f}%")


if __name__ == '__main__':
    main()
