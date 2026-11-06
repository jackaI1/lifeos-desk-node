"""Command-line entry point; run geometry commands in a FreeCAD-enabled Python."""

import argparse
import json
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate mounting parts, BOMs and reuse reports")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser(
        "generate", help="Generate a library and exploded sample assembly"
    )
    generate.add_argument("table", type=Path)
    generate.add_argument("output", type=Path)
    bom = commands.add_parser("bom", help="Export the Assembly object's CSV and Excel BOM")
    bom.add_argument("document", type=Path)
    bom.add_argument("output_stem", type=Path)
    reuse = commands.add_parser("reuse", help="Flag near-duplicate FCStd library solids")
    reuse.add_argument("library", type=Path)
    reuse.add_argument("report", type=Path)
    reuse.add_argument("--box-mm", type=float, default=0.25)
    reuse.add_argument("--hole-mm", type=float, default=0.25)
    reuse.add_argument("--volume-fraction", type=float, default=0.01)
    checkin = commands.add_parser("check-in", help="Check a file into a local revision vault")
    transition = commands.add_parser("transition", help="Change draft/review/released state")
    history = commands.add_parser("history", help="Show revision history")
    for command in (checkin, transition, history):
        command.add_argument("vault", type=Path)
        command.add_argument("part_id")
    checkin.add_argument("source", type=Path)
    transition.add_argument("state", choices=("draft", "review", "released"))
    for command in (checkin, transition):
        command.add_argument(
            "--expected", type=int, required=True, help="Last observed version, 0 for new"
        )
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            from .parts import build_project

            print(build_project(args.table, args.output))
        elif args.command == "bom":
            import FreeCAD as App

            from .bom import export_bom

            document = App.openDocument(str(args.document.resolve()))
            try:
                root = document.getObject("Assembly")
                if root is None:
                    raise ValueError("Document needs an Assembly root object")
                rows = export_bom(root, args.output_stem)
                print(f"{len(rows)} BOM lines; {sum(row['quantity'] for row in rows)} occurrences")
            finally:
                App.closeDocument(document.Name)
        elif args.command == "reuse":
            from .reuse import scan_library, write_report

            if not args.library.is_dir():
                raise ValueError("Library directory does not exist")
            rows = scan_library(
                args.library,
                box_tolerance=args.box_mm,
                hole_tolerance=args.hole_mm,
                volume_tolerance=args.volume_fraction,
            )
            write_report(rows, args.report)
            print(f"{len(rows)} candidate pairs for review")
        else:
            from .workflow import Vault

            vault = Vault(args.vault)
            if args.command == "check-in":
                result = vault.check_in(args.part_id, args.source, expected_version=args.expected)
            elif args.command == "transition":
                result = vault.transition(args.part_id, args.state, expected_version=args.expected)
            else:
                result = vault.history(args.part_id)
            print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError, ImportError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
