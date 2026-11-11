"""Python reference for the SHT31 checks, independent of the RTL.

The CRC is the one the sensor uses and that firmware/components/desk_core
computes in desk_crc8(): polynomial 0x31, initial value 0xFF, most significant
bit first, no final XOR. Frames are six bytes, temperature MSB, LSB, CRC,
humidity MSB, LSB, CRC, as the replay tool writes them.
"""
import random
from dataclasses import dataclass
from pathlib import Path


def crc8(data):
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


@dataclass(frozen=True)
class Expected:
    """What the RTL must report for one transfer."""
    truncated: bool
    good: bool
    bad: bool
    temp_ok: bool
    hum_ok: bool
    temp_raw: int
    hum_raw: int


def classify(payload):
    """Classify one transfer of 1 to 6 bytes the way the RTL should."""
    if len(payload) < 6:
        return Expected(True, False, False, False, False, 0, 0)
    if len(payload) != 6:
        raise ValueError('a transfer is at most one six-byte frame')
    temp_ok = crc8(payload[0:2]) == payload[2]
    hum_ok = crc8(payload[3:5]) == payload[5]
    good = temp_ok and hum_ok
    return Expected(False, good, not good, temp_ok, hum_ok,
                    (payload[0] << 8) | payload[1] if good else 0,
                    (payload[3] << 8) | payload[4] if good else 0)


def parse_wire(text):
    """Return the six-byte frames in a DESK_REPLAY_V1 wire recording.

    Only the `S` lines carry sensor bytes; `U` lines are uploads. The same rules
    as replay/replay.c: exact header, exactly 14 characters per sample line.
    """
    lines = text.splitlines()
    if not lines or lines[0] != 'DESK_REPLAY_V1':
        raise ValueError('expected DESK_REPLAY_V1 header')
    frames = []
    for line in lines[1:]:
        if line == 'U':
            continue
        if len(line) != 14 or not line.startswith('S '):
            raise ValueError(f'malformed sample line: {line!r}')
        frames.append(bytes.fromhex(line[2:]))
    return frames


def wire_frames(path):
    return parse_wire(Path(path).read_text())


def random_transfers(rng, count, corrupt_rate=0.3, truncate_rate=0.1):
    """Random transfers: good frames, corrupted frames and truncated ones."""
    transfers = []
    for _ in range(count):
        if rng.random() < truncate_rate:
            length = rng.randint(1, 5)
            payload = bytes(rng.randrange(256) for _ in range(length))
        else:
            payload = bytearray(_good_frame(rng))
            if rng.random() < corrupt_rate:
                # One flipped bit in either word; sometimes both words are hit.
                words = [0, 1] if rng.random() < 0.3 else [rng.randrange(2)]
                for word in words:
                    position = rng.randrange(3) + 3 * word
                    payload[position] ^= 1 << rng.randrange(8)
            payload = bytes(payload)
        transfers.append(payload)
    return transfers


def _good_frame(rng):
    temp = bytes([rng.randrange(256), rng.randrange(256)])
    hum = bytes([rng.randrange(256), rng.randrange(256)])
    return temp + bytes([crc8(temp)]) + hum + bytes([crc8(hum)])
