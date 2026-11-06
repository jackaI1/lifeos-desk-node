"""JSON-in, JSON-out fault study with optional plots and relay checks."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .faults import FAULT_TYPES, solve_fault
from .model import load_network
from .plots import plot_fault
from .relay import Relay


def _phasors(values):
    return [
        {
            "real": float(v.real),
            "imag": float(v.imag),
            "magnitude": float(abs(v)),
            "angle_deg": float(np.degrees(np.angle(v))),
        }
        for v in values
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("network", type=Path)
    parser.add_argument("--bus", required=True)
    parser.add_argument("--fault", choices=(*FAULT_TYPES, "all"), default="all")
    parser.add_argument("--zf", nargs=2, type=float, default=[0, 0], metavar=("R", "X"))
    parser.add_argument("--pickup-a", type=float, help="Primary phase pickup amperes")
    parser.add_argument("--time-dial", type=float, default=0.1)
    parser.add_argument("--max-time-s", type=float, default=1.0)
    parser.add_argument(
        "--relay-source", help="Check a source feeder instead of total fault current"
    )
    parser.add_argument("--plots", type=Path)
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout")
    args = parser.parse_args(argv)
    try:
        network = load_network(args.network)
        if args.relay_source and not args.pickup_a:
            raise ValueError("--relay-source requires --pickup-a")
        relay = Relay(args.pickup_a, args.time_dial) if args.pickup_a is not None else None
        studies = []
        for fault in FAULT_TYPES if args.fault == "all" else (args.fault,):
            result = solve_fault(network, args.bus, fault, complex(*args.zf))
            study = {
                "fault": fault,
                "bus": args.bus,
                "zf_pu": args.zf,
                "phase_current_pu": _phasors(result.phase_current_pu),
                "phase_current_a_rms": _phasors(result.phase_current_a),
                "sequence_current_pu_012": _phasors(result.sequence_current_pu),
                "residual_current_a_rms": _phasors([result.residual_current_a])[0],
                "bus_voltage_pu": {b: _phasors(v) for b, v in result.bus_voltage_pu.items()},
                "source_current_pu": {b: _phasors(v) for b, v in result.source_current_pu.items()},
                "branch_current_pu": {b: _phasors(v) for b, v in result.branch_current_pu.items()},
            }
            if relay:
                measured = result.phase_current_a
                if args.relay_source:
                    measured = result.source_current_pu[args.relay_source] * result.base_current_a
                study["relay"] = {
                    "location": args.relay_source or "total fault current",
                    "pickup_a": relay.pickup_a,
                    "time_dial": relay.time_dial,
                    "phases": {p: relay.check(i, args.max_time_s) for p, i in zip("abc", measured)},
                }
            if args.plots:
                study["plots"] = [
                    str(p) for p in plot_fault(result, network.frequency_hz, args.plots)
                ]
            studies.append(study)
        payload = json.dumps(
            {
                "base_current_a_rms": network.base_current_a,
                "phase_order": "abc",
                "studies": studies,
            },
            indent=2,
            allow_nan=False,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n")
        else:
            print(payload)
        return 0
    except (ValueError, TypeError, KeyError, OSError, np.linalg.LinAlgError) as error:
        print(f"three-phase-fault: {error}", file=sys.stderr)
        return 2
