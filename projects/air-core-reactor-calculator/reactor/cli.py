"""JSON-in, JSON-out command line interface."""

import argparse
import json
from pathlib import Path

from .analysis import analyze
from .circuit import fault_current
from .coils import Coil


def main():
    parser = argparse.ArgumentParser(description="Compare air-core coil models from SI geometry.")
    parser.add_argument("input", type=Path, help="JSON file with coil and optional circuit objects")
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text())
        if not isinstance(data, dict) or not set(data) <= {"coil", "circuit"}:
            raise ValueError("Expected an object containing coil and optional circuit.")
        if not isinstance(data.get("coil"), dict):
            raise ValueError("coil must be a geometry object; see examples/.")
        result = analyze(Coil(**data["coil"]))
        if "circuit" in data:
            if not isinstance(data["circuit"], dict):
                raise ValueError("circuit must be an object.")
            result["fault_current"] = fault_current(
                result["inductance_h"]["filament"], **data["circuit"]
            )
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        parser.error(str(exc))
