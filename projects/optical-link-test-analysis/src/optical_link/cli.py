"""Command-line entry point for reproducible, simulation-only sweeps."""
import argparse
import json
from datetime import datetime, timezone

from .model import LinkConfig
from .sweep import run_sweep


def main():
    parser = argparse.ArgumentParser(description='Simulated optical BERT, DCA and OSA sweep')
    parser.add_argument('--output', default=None, help='new output directory; never overwritten')
    parser.add_argument('--powers', type=float, nargs='+', default=list(range(-30, -9, 2)),
                        help='received powers in dBm')
    parser.add_argument('--bits', type=int, default=32768)
    parser.add_argument('--samples-per-bit', type=int, default=32)
    parser.add_argument('--fiber-km', type=float, default=20)
    parser.add_argument('--noise-std-mw', type=float, default=.0015)
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--target-ber', type=float, default=.001)
    args = parser.parse_args()
    try:
        config = LinkConfig(n_bits=args.bits, samples_per_bit=args.samples_per_bit,
                            fiber_km=args.fiber_km, noise_std_mw=args.noise_std_mw,
                            seed=args.seed)
        output = args.output or datetime.now(timezone.utc).strftime('runs/%Y%m%dT%H%M%S%fZ')
        result = run_sweep(output, config, args.powers, args.target_ber)
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    print('SIMULATED DATA ONLY. No physical optical equipment was used.')
    print(f'Saved CSV traces, measurements and summary.png to {output}')
    print(json.dumps(result, indent=2))
