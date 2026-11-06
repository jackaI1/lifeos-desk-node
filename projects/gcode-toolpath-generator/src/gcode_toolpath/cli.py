"""Generate checked job bundles or check an edited G-code file."""

import argparse
import json
import sys
from pathlib import Path

from .materials import cutting_data
from .model import Job
from .planner import generate
from .preview import render
from .simulator import simulate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    build = subs.add_parser("generate", help="Write G-code, report, parsed moves and PNGs")
    build.add_argument("job", type=Path)
    build.add_argument("--out", type=Path, default=Path("build/bracket"))
    check = subs.add_parser("check", help="Check emitted or hand-edited G-code against a job")
    check.add_argument("job", type=Path)
    check.add_argument("gcode", type=Path)
    args = parser.parse_args()
    try:
        job = Job.load(args.job)
        text = generate(job) if args.command == "generate" else args.gcode.read_text()
        report = simulate(text, job.stock, job.diameter, job.safe_z)
        result = report.summary()
        result["cutting_data"] = cutting_data(job.material, job.diameter, job.flutes, job.max_rpm)
        if args.command == "generate" and report.ok:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "bracket.nc").write_text(text)
            (args.out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
            (args.out / "moves.json").write_text(json.dumps(report.move_dicts(), indent=2) + "\n")
            render(job, report, args.out)
        print(json.dumps(result, indent=2))
        return 0 if report.ok else 1
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
