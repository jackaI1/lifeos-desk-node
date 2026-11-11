"""Checks for the host side of the iCEBreaker board: packing and reply parsing.

These run without a board. They also check that the frames the host builds are
the ones the Python reference (scripts/sht31_ref.py) calls good or bad.
"""
import importlib.util
from pathlib import Path

import pytest
import sht31_ref

HOST = Path(__file__).resolve().parents[1] / 'board' / 'icebreaker' / 'host.py'
spec = importlib.util.spec_from_file_location('board_host', HOST)
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def test_crc8_matches_reference():
    for data in [b'', b'\x00', b'\xbe\xef', b'\x6a\x5b', bytes(range(16))]:
        assert host.crc8(data) == sht31_ref.crc8(data)


def test_good_frame_is_classified_good_by_reference():
    frame = host.make_frame(0x6A5B, 0x8C2D)
    expected = sht31_ref.classify(frame)
    assert expected.good
    assert (expected.temp_raw, expected.hum_raw) == (0x6A5B, 0x8C2D)


def test_flipped_checksum_is_classified_bad_by_reference():
    frame = bytearray(host.make_frame(0x5F10, 0x4A00))
    frame[2] ^= 0x01
    expected = sht31_ref.classify(bytes(frame))
    assert expected.bad and not expected.temp_ok


def test_pack_transfer_puts_length_first():
    assert host.pack_transfer([0xAA, 0xBB]) == bytes([2, 0xAA, 0xBB])


def test_pack_transfer_accepts_255_and_rejects_empty_or_longer():
    assert host.pack_transfer(bytes(255))[0] == 255
    with pytest.raises(ValueError):
        host.pack_transfer([])
    with pytest.raises(ValueError):
        host.pack_transfer(bytes(256))


def test_parse_reply_reads_big_endian_counts():
    reply = bytes([0x01, 0x00, 0x00, 0x02, 0x00, 0x03])
    assert host.parse_reply(reply) == (256, 2, 3)


def test_parse_reply_needs_six_bytes():
    with pytest.raises(ValueError):
        host.parse_reply(bytes(5))
