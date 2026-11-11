import os

import can
import pytest
from can.io import CanutilsLogReader

from can_monitor.candump import (
    CAN_ERR_BUSOFF,
    MalformedLine,
    parse_candump_line,
    parse_candump_lines,
    read_candump,
)

HERE = os.path.dirname(os.path.abspath(__file__))
CLEAN = os.path.join(HERE, "..", "examples", "candump", "desk_node_clean.log")


def test_classic_standard_frame():
    msg = parse_candump_line("(1700000000.250000) can0 120#0102030405060708")
    assert isinstance(msg, can.Message)
    assert msg.timestamp == pytest.approx(1700000000.25)
    assert msg.arbitration_id == 0x120
    assert not msg.is_extended_id and not msg.is_fd and not msg.is_error_frame
    assert msg.data == bytes(range(1, 9))
    assert msg.dlc == 8 and msg.channel == "can0"


def test_direction_flag_written_by_python_can_is_accepted():
    msg = parse_candump_line("(1.000000) vcan0 120#00 R")
    assert isinstance(msg, can.Message) and msg.data == b"\x00"


def test_extended_identifier_is_recognised_by_its_eight_digits():
    msg = parse_candump_line("(1.000000) can0 00001234#AA")
    assert msg.is_extended_id and msg.arbitration_id == 0x1234


def test_remote_frame():
    msg = parse_candump_line("(1.000000) can0 123#R")
    assert msg.is_remote_frame and msg.data == b""


def test_canfd_flags_and_64_byte_payload():
    msg = parse_candump_line("(1.000000) can0 101##3" + "AB" * 64)
    assert msg.is_fd and msg.bitrate_switch and msg.error_state_indicator
    assert len(msg.data) == 64 and msg.data[0] == 0xAB


def test_error_frame_keeps_bus_off_class_bit():
    msg = parse_candump_line("(1.000000) can0 20000040#0000000000000000")
    assert msg.is_error_frame
    assert msg.arbitration_id & CAN_ERR_BUSOFF
    assert msg.arbitration_id == 0x40


def test_matches_python_can_reader_for_every_clean_frame():
    ours = [r for r in read_candump(CLEAN) if isinstance(r, can.Message)]
    theirs = list(CanutilsLogReader(CLEAN))
    assert len(ours) == len(theirs) == 120
    for mine, reference in zip(ours, theirs):
        assert mine.timestamp == pytest.approx(reference.timestamp)
        assert mine.arbitration_id == reference.arbitration_id
        assert mine.data == reference.data
        assert mine.is_extended_id == reference.is_extended_id


@pytest.mark.parametrize("text, reason_fragment", [
    ("not a log line", "not a candump"),
    ("(1.0) can0 120#012", "even-length"),
    ("(1.0) can0 120#ZZ", "even-length"),
    ("(1.0) can0 120#0102030405060708090A", "max 8"),
    ("(1.0) can0 800#00", "out of range"),
    ("(1.0) can0 1FFFFFFFF#00", "not a candump"),
    ("(1.0) can0 101##3" + "AB" * 9, "DLC size"),
    ("(1.0) can0 20000040#00", "malformed error frame"),
    ("(1.0) can0 120##", "not hex"),
])
def test_damaged_lines_are_reported_not_raised(text, reason_fragment):
    result = parse_candump_line(text, line_no=7)
    assert isinstance(result, MalformedLine)
    assert result.line_no == 7
    assert reason_fragment in result.reason


def test_blank_and_comment_lines_are_skipped():
    records = list(parse_candump_lines(["", "# header", "(1.0) can0 120#00"]))
    assert len(records) == 1 and isinstance(records[0], can.Message)


def test_non_utf8_bytes_in_a_file_become_malformed_lines(tmp_path):
    path = tmp_path / "garbage.log"
    path.write_bytes(b"(1.0) can0 120#00\n\xff\xfe\x00junk\n(2.0) can0 120#01\n")
    records = list(read_candump(str(path)))
    assert [type(r) for r in records] == [can.Message, MalformedLine, can.Message]
