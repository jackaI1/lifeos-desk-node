"""Simulate the desk node on a python-can virtual bus and log what a listener sees.

No CAN hardware is needed. One python-can "virtual" bus is the transmitter, a
second bus on the same channel is the listener, and every frame the listener
receives is written with python-can's CanutilsLogWriter in candump format. Timestamps
are logical (start + k * period), so the same arguments always give the same log.

Usage:
    python -m can_monitor.virtual_node --seconds 120 --log desk_node.log
    python -m can_monitor.virtual_node --seconds 120 --silent 30:45 --log gap.log
"""

import argparse
import math
import os

import can
import cantools
from can.io import CanutilsLogWriter

from can_monitor.analyze import DEFAULT_DBC, HEARTBEAT_MESSAGE


def reading_at(k: int) -> dict:
    """Slow, deterministic room readings for frame k."""
    return {
        "Temperature": 21.0 + 0.8 * math.sin(k / 30.0),
        "Humidity": 44.0 + 6.0 * math.sin(k / 45.0 + 1.0),
        "Heartbeat": k % 256,
        "SensorFault": 0,
        "QueueLoss": 0,
    }


def parse_silences(specs):
    """Turn ['30:45'] into the set of frame indexes that are not sent."""
    silent = set()
    for spec in specs or ():
        start, _, end = spec.partition(":")
        first, last = int(start), int(end)
        if last < first:
            raise ValueError(f"silence {spec!r} ends before it starts")
        silent.update(range(first, last))
    return silent


def run(log_path: str, seconds: float, *, period: float = 1.0, start: float = 1700000000.0,
        silent=(), channel: str = "desk-sim", dbc_path: str = DEFAULT_DBC) -> int:
    """Send one DeskNode frame per period for `seconds`; return frames logged."""
    db = cantools.database.load_file(dbc_path)
    message = db.get_message_by_name(HEARTBEAT_MESSAGE)
    silent_frames = parse_silences(silent)
    transmitter = can.Bus(interface="virtual", channel=channel)
    listener = can.Bus(interface="virtual", channel=channel)
    logged = 0
    try:
        with CanutilsLogWriter(log_path, channel=channel) as writer:
            for k in range(int(round(seconds / period))):
                if k in silent_frames:
                    continue
                payload = db.encode_message(HEARTBEAT_MESSAGE, reading_at(k))
                transmitter.send(can.Message(arbitration_id=message.frame_id, data=payload,
                                             is_extended_id=False))
                received = listener.recv(timeout=1.0)
                if received is None:
                    raise RuntimeError(f"virtual bus delivered nothing for frame {k}")
                received.timestamp = start + k * period
                writer.on_message_received(received)
                logged += 1
    finally:
        transmitter.shutdown()
        listener.shutdown()
    return logged


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Simulate desk-node CAN frames and write a candump log.")
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--period", type=float, default=1.0, help="seconds between frames")
    parser.add_argument("--silent", action="append", metavar="FIRST:END",
                        help="frame indexes [FIRST, END) are not sent; repeat for more gaps")
    parser.add_argument("--channel", default="desk-sim", help="virtual channel name written to the log")
    parser.add_argument("--log", required=True, help="output candump file")
    args = parser.parse_args(argv)
    os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)
    frames = run(args.log, args.seconds, period=args.period, silent=args.silent, channel=args.channel)
    print(f"wrote {frames} frames to {args.log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
