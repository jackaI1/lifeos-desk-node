"""Checks that the firmware encoder (firmware/components/desk_can) and the DBC agree.

firmware/tests/test_can.c asserts these same byte vectors in C. This test
decodes them with cantools and encodes the physical values again, so a change
to either side that breaks the layout fails in CI.
"""

import cantools
import can
import pytest

from can_monitor.analyze import DEFAULT_DBC, analyze

DB = cantools.database.load_file(DEFAULT_DBC)

# (payload from the C encoder test, expected physical values or None for markers)
NORMAL = bytes([0x06, 0x18, 0x94, 0x11, 0x07, 0x00, 0x00, 0x00])
LOW = bytes(8)
HIGH = bytes([0x74, 0x40, 0x10, 0x27, 0xFF, 0x02, 0x00, 0x00])
ROUNDED = bytes([0xD5, 0x17, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00])
HOT_MARKER = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x09, 0x01, 0x00, 0x00])


@pytest.mark.parametrize("payload, temperature, humidity, heartbeat, queue_loss, sensor_fault", [
    (NORMAL, 21.5, 45.0, 7, 0, 0),
    (LOW, -40.0, 0.0, 0, 0, 0),
    (HIGH, 125.0, 100.0, 255, 1, 0),
    (ROUNDED, 21.01, 0.0, 1, 0, 0),
])
def test_c_vectors_decode_to_the_expected_values(payload, temperature, humidity, heartbeat,
                                                 queue_loss, sensor_fault):
    values = DB.decode_message("DeskNode", payload)
    assert values["Temperature"] == pytest.approx(temperature, abs=0.005)
    assert values["Humidity"] == pytest.approx(humidity, abs=0.005)
    assert values["Heartbeat"] == heartbeat
    assert values["QueueLoss"] == queue_loss
    assert values["SensorFault"] == sensor_fault


def test_python_encoder_produces_the_same_bytes_as_the_firmware():
    payload = DB.encode_message("DeskNode", {"Temperature": 21.5, "Humidity": 45.0, "Heartbeat": 7,
                                             "SensorFault": 0, "QueueLoss": 0})
    assert payload == NORMAL


def test_firmware_invalid_marker_is_flagged_by_the_analyzer():
    msg = can.Message(timestamp=0.0, arbitration_id=0x120, data=HOT_MARKER, is_extended_id=False)
    report = analyze([msg], DB)
    kinds = {f.kind for f in report.findings}
    assert kinds == {"out_of_range", "sensor_fault"}
    details = " ".join(f.detail for f in report.findings)
    assert "Temperature=615.35" in details and "Humidity=655.35" in details


def test_firmware_humidity_marker_is_out_of_range_for_humidity():
    raw = bytes([0x94, 0x11, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00])
    report = analyze([can.Message(timestamp=0.0, arbitration_id=0x120, data=raw, is_extended_id=False)], DB)
    assert [f.kind for f in report.findings] == ["out_of_range"]
    assert "Humidity=655.35" in report.findings[0].detail
