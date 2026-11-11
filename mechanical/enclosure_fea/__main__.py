"""Command line: python -m enclosure_fea {step,cantilever,study,stackup}."""
import argparse
import json
import sys
from pathlib import Path

from .board import CaseParams
from .stackup import report as stackup_report

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m enclosure_fea')
    sub = parser.add_subparsers(dest='command', required=True)
    step = sub.add_parser('step', help='write the parametric case as a STEP file')
    step.add_argument('--out', default=str(ROOT / 'cad' / 'desk-node-case.step'))
    cant = sub.add_parser('cantilever', help='compare CalculiX with the cantilever closed form')
    cant.add_argument('--work', default=str(ROOT / 'build' / 'cantilever'))
    study = sub.add_parser('study', help='run the load cases and wall sweep, write the report')
    study.add_argument('--work', default=str(ROOT / 'build' / 'study'))
    study.add_argument('--report', default=str(ROOT / 'docs' / 'study.md'))
    study.add_argument('--no-mesh-check', action='store_true')
    sub.add_parser('stackup', help='print the tolerance stack-up')
    args = parser.parse_args(argv)

    if args.command == 'step':
        from .geometry import export_step
        path = export_step(CaseParams().validate(), Path(args.out))
        print(f'wrote {path}')
    elif args.command == 'cantilever':
        from .studies import cantilever_check
        print(json.dumps(cantilever_check(Path(args.work)), indent=2))
    elif args.command == 'study':
        from .studies import run_study
        results = run_study(args.work, report=args.report, mesh_check=not args.no_mesh_check)
        print(f"wrote {args.report}")
        print(json.dumps(results['cantilever'], indent=2))
    elif args.command == 'stackup':
        print(json.dumps(stackup_report(), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
