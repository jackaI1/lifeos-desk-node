"""Check a candump log against a DBC file and report faults.

The analyzer decodes each DeskNode frame with the DBC (cantools) and flags:

- missing_heartbeat: no DeskNode frame for longer than the timeout, including
  before the first frame and after the last one in the log (a log cannot show
  silence after its final record),
- heartbeat_skip: the heartbeat counter jumped, so frames were lost,
- out_of_range: a decoded value is outside the DBC minimum and maximum,
- sensor_fault / queue_loss: the node reported its own fault bits,
- bus_off: an error frame with the bus-off class bit (CAN_ERR_BUSOFF),
- error_frame: any other error frame,
- unknown_id, decode_error, malformed_line, timestamp_reversed.

Usage: python -m can_monitor.analyze LOG.log [--heartbeat-timeout 10] [--json out.json]
Exit status: 0 clean, 1 findings, 2 the log or DBC could not be read.
"""

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Iterable, List, Optional

import cantools
from cantools.database.errors import DecodeError

from can_monitor.candump import CAN_ERR_BUSOFF, MalformedLine, Record, read_candump

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DBC = os.path.join(HERE, "desk_node.dbc")
HEARTBEAT_MESSAGE = "DeskNode"
DEFAULT_TIMEOUT_S = 10.0
MAX_PRINTED_FINDINGS = 20


@dataclass
class Finding:
    kind: str
    time: Optional[float]
    detail: str
    line: Optional[int] = None


@dataclass
class Report:
    frames: int = 0
    heartbeats: int = 0
    bus_off_events: int = 0
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "frames": self.frames,
            "heartbeats": self.heartbeats,
            "bus_off_events": self.bus_off_events,
            "findings": [asdict(f) for f in self.findings],
        }


def analyze(
    records: Iterable[Record],
    db,
    *,
    heartbeat_timeout: float = DEFAULT_TIMEOUT_S,
    message_name: str = HEARTBEAT_MESSAGE,
) -> Report:
    """Run every check over a stream of records and return a Report."""
    if heartbeat_timeout <= 0:
        raise ValueError("heartbeat_timeout must be positive")
    heartbeat = db.get_message_by_name(message_name)
    report = Report()
    first_ts = last_ts = None
    last_hb_ts = None
    last_counter = None

    def add(kind, time, detail, line=None):
        report.findings.append(Finding(kind, time, detail, line))

    for record in records:
        if isinstance(record, MalformedLine):
            add("malformed_line", None, record.reason, record.line_no)
            continue
        msg = record
        report.frames += 1
        if first_ts is None:
            first_ts = msg.timestamp
        if last_ts is not None and msg.timestamp < last_ts:
            # Out-of-order frames are reported once and kept out of the heartbeat checks.
            add("timestamp_reversed", msg.timestamp,
                f"time went back from {last_ts:.6f} to {msg.timestamp:.6f}")
            continue
        last_ts = msg.timestamp

        if msg.is_error_frame:
            if msg.arbitration_id & CAN_ERR_BUSOFF:
                report.bus_off_events += 1
                add("bus_off", msg.timestamp, "node entered bus-off (TX error limit reached)")
            else:
                add("error_frame", msg.timestamp,
                    f"error frame, class bits 0x{msg.arbitration_id:02x}")
            continue
        if msg.arbitration_id != heartbeat.frame_id or msg.is_extended_id != heartbeat.is_extended_frame:
            add("unknown_id", msg.timestamp, f"identifier 0x{msg.arbitration_id:x} is not in the DBC")
            continue
        if msg.is_remote_frame or msg.is_fd or len(msg.data) != heartbeat.length:
            add("decode_error", msg.timestamp,
                f"{heartbeat.name} expects {heartbeat.length} bytes, got {len(msg.data)}")
            continue
        try:
            values = db.decode_message(heartbeat.frame_id, msg.data, decode_choices=False)
        except (DecodeError, ValueError) as exc:
            add("decode_error", msg.timestamp, str(exc))
            continue

        report.heartbeats += 1
        for signal in heartbeat.signals:
            value = values[signal.name]
            if signal.minimum is not None and not (signal.minimum <= value <= signal.maximum):
                unit = f" {signal.unit}" if signal.unit else ""
                add("out_of_range", msg.timestamp,
                    f"{signal.name}={value:g}{unit} outside "
                    f"[{signal.minimum:g}, {signal.maximum:g}]")
        if values["SensorFault"]:
            add("sensor_fault", msg.timestamp, "node reports SensorFault=1")
        if values["QueueLoss"]:
            add("queue_loss", msg.timestamp, "node reports QueueLoss=1 (readings were dropped)")

        if last_hb_ts is None:
            if msg.timestamp - first_ts > heartbeat_timeout:
                add("missing_heartbeat", first_ts,
                    f"no heartbeat for the first {msg.timestamp - first_ts:.2f} s of the log")
        else:
            gap = msg.timestamp - last_hb_ts
            if gap > heartbeat_timeout:
                add("missing_heartbeat", last_hb_ts,
                    f"no heartbeat for {gap:.2f} s (timeout {heartbeat_timeout:g} s)")
            expected = (last_counter + 1) % 256
            if values["Heartbeat"] != expected:
                add("heartbeat_skip", msg.timestamp,
                    f"counter went from {last_counter} to {values['Heartbeat']}; "
                    f"expected {expected}")
        last_hb_ts = msg.timestamp
        last_counter = values["Heartbeat"]

    if first_ts is not None:
        if last_hb_ts is None and last_ts - first_ts > heartbeat_timeout:
            add("missing_heartbeat", first_ts,
                f"no heartbeat in {last_ts - first_ts:.2f} s of log")
        elif last_hb_ts is not None and last_ts - last_hb_ts > heartbeat_timeout:
            add("missing_heartbeat", last_hb_ts,
                f"no heartbeat for the last {last_ts - last_hb_ts:.2f} s of the log")
    return report


def analyze_file(path: str, dbc_path: str = DEFAULT_DBC, heartbeat_timeout: float = DEFAULT_TIMEOUT_S) -> Report:
    db = cantools.database.load_file(dbc_path)
    return analyze(read_candump(path), db, heartbeat_timeout=heartbeat_timeout)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check a candump log for missing heartbeats, bad values and bus-off.")
    parser.add_argument("log", help="candump -l file")
    parser.add_argument("--dbc", default=DEFAULT_DBC, help="DBC file (default: desk_node.dbc)")
    parser.add_argument("--heartbeat-timeout", type=float, default=DEFAULT_TIMEOUT_S,
                        help="seconds without a DeskNode frame before it is flagged")
    parser.add_argument("--json", help="write the full report to this file")
    args = parser.parse_args(argv)
    try:
        report = analyze_file(args.log, args.dbc, args.heartbeat_timeout)
    except (OSError, cantools.database.errors.Error, ValueError) as exc:
        print(f"cannot analyze: {exc}", file=sys.stderr)
        return 2
    print(f"frames={report.frames} heartbeats={report.heartbeats} "
          f"bus_off={report.bus_off_events} findings={len(report.findings)}")
    for finding in report.findings[:MAX_PRINTED_FINDINGS]:
        where = f"line {finding.line}" if finding.line else f"t={finding.time:.3f}"
        print(f"  {finding.kind:<18} {where:<14} {finding.detail}")
    if len(report.findings) > MAX_PRINTED_FINDINGS:
        print(f"  ... {len(report.findings) - MAX_PRINTED_FINDINGS} more in the JSON report")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report.to_dict(), handle, indent=2)
            handle.write("\n")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
