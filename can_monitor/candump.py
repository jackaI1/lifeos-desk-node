"""Read and write candump log files as python-can messages.

A candump log has one frame per line, for example (a trailing R or T direction
flag, as python-can writes it, is also accepted)::

    (1700000000.000000) can0 120#0102030405060708
    (1700000001.000000) can0 120##10102   (CAN FD, first hex digit = flags)
    (1700000002.000000) can0 20000040#0000000000000000   (error frame)

python-can's own CanutilsLogReader drops the error-frame flag, so this reader
keeps it. Error frames set ``is_error_frame`` and keep the error-class bits in
``arbitration_id``, the same way SocketCAN reports them. Lines that do not parse
are returned as MalformedLine values instead of being dropped, so the analyzer
can report damaged log lines.
"""

import re
from dataclasses import dataclass
from typing import Iterable, Iterator, Union

import can

CAN_ERR_FLAG = 0x20000000
CAN_ERR_MASK = 0x1FFFFFFF
CAN_ERR_BUSOFF = 0x00000040
FD_LENGTHS = {0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64}

_LINE = re.compile(
    r"^\((?P<ts>\d+\.\d+)\)\s+(?P<chan>\S+)\s+"
    r"(?P<id>[0-9A-Fa-f]{3}|[0-9A-Fa-f]{8})(?P<sep>##|#)(?P<body>\S*?)(?:\s+[RT])?$"
)


@dataclass(frozen=True)
class MalformedLine:
    """A log line that could not be parsed, kept for the analyzer report."""

    line_no: int
    text: str
    reason: str


Record = Union[can.Message, MalformedLine]


def _parse_body(sep: str, body: str):
    """Return (data, is_fd, bitrate_switch, esi, is_remote) or raise ValueError."""
    if sep == "#":
        if body == "R":
            return b"", False, False, False, True
        if len(body) % 2 or not re.fullmatch(r"[0-9A-Fa-f]*", body):
            raise ValueError("payload is not an even-length hex string")
        data = bytes.fromhex(body)
        if len(data) > 8:
            raise ValueError(f"classic CAN payload has {len(data)} bytes (max 8)")
        return data, False, False, False, False
    # CAN FD: one flags digit, then payload. Bit 0 = BRS, bit 1 = ESI.
    if len(body) < 1 or not re.fullmatch(r"[0-9A-Fa-f][0-9A-Fa-f]*", body):
        raise ValueError("CAN FD body is not hex")
    flags = int(body[0], 16)
    payload = body[1:]
    if len(payload) % 2:
        raise ValueError("payload is not an even-length hex string")
    data = bytes.fromhex(payload)
    if len(data) not in FD_LENGTHS:
        raise ValueError(f"CAN FD payload length {len(data)} is not a valid DLC size")
    return data, True, bool(flags & 1), bool(flags & 2), False


def parse_candump_line(text: str, line_no: int = 1) -> Record:
    """Parse one candump -l line into a can.Message, or return MalformedLine."""
    match = _LINE.match(text.strip())
    if not match:
        return MalformedLine(line_no, text.rstrip("\n"), "not a candump -l frame")
    try:
        data, is_fd, brs, esi, remote = _parse_body(match["sep"], match["body"])
    except ValueError as exc:
        return MalformedLine(line_no, text.rstrip("\n"), str(exc))
    raw_id = int(match["id"], 16)
    timestamp = float(match["ts"])
    if raw_id & CAN_ERR_FLAG:
        if match["sep"] != "#" or remote or len(data) != 8:
            return MalformedLine(line_no, text.rstrip("\n"), "malformed error frame")
        return can.Message(
            timestamp=timestamp,
            arbitration_id=raw_id & CAN_ERR_MASK,
            is_extended_id=False,
            is_error_frame=True,
            data=data,
            channel=match["chan"],
        )
    extended = len(match["id"]) == 8
    limit = 0x1FFFFFFF if extended else 0x7FF
    if raw_id > limit:
        return MalformedLine(line_no, text.rstrip("\n"), "identifier is out of range")
    return can.Message(
        timestamp=timestamp,
        arbitration_id=raw_id,
        is_extended_id=extended,
        is_remote_frame=remote,
        is_fd=is_fd,
        bitrate_switch=brs,
        error_state_indicator=esi,
        dlc=len(data),
        data=data,
        channel=match["chan"],
    )


def parse_candump_lines(lines: Iterable[str]) -> Iterator[Record]:
    """Yield a message or MalformedLine for each non-blank, non-comment line."""
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield parse_candump_line(stripped, line_no)


def read_candump(path: str) -> Iterator[Record]:
    """Stream records from a candump -l file. Undecodable bytes become MalformedLine."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        yield from parse_candump_lines(handle)
