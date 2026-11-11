"""Write a deliberately corrupted copy of the clean candump example.

Run from the repository root:
    .venv/bin/python -m can_monitor.examples.build_faults_log

Damage added to the clean log (frame k is the k-th line, starting at 0):
- frames 30-39 removed: heartbeat gap of 11 s and a counter skip,
- frame 50 humidity 105 %RH: out of the DBC range,
- frame 60 raw 0xFFFF temperature with SensorFault=1: no valid reading,
- frame 80 QueueLoss=1: the node dropped readings,
- a bus-off error frame (20000040#) after frame 70,
- a ten-byte classic CAN payload after frame 90: malformed,
- a line whose timestamp goes backwards after frame 95.
"""

import os

import cantools

from can_monitor.analyze import DEFAULT_DBC, HEARTBEAT_MESSAGE
from can_monitor.virtual_node import reading_at

HERE = os.path.dirname(os.path.abspath(__file__))
CLEAN = os.path.join(HERE, "candump", "desk_node_clean.log")
FAULTS = os.path.join(HERE, "candump", "desk_node_faults.log")


def raw_reading(k: int) -> dict:
    """Raw DBC values for frame k: reading_at(k) without scaling."""
    reading = reading_at(k)
    return {"Temperature": round((reading["Temperature"] + 40) * 100),
            "Humidity": round(reading["Humidity"] * 100),
            "Heartbeat": reading["Heartbeat"], "SensorFault": 0, "QueueLoss": 0}


def build(clean_path=CLEAN, out_path=FAULTS, dbc_path=DEFAULT_DBC) -> int:
    db = cantools.database.load_file(dbc_path)
    with open(clean_path, encoding="utf-8") as handle:
        clean = [line.rstrip("\n") for line in handle if line.strip()]
    channel = clean[0].split()[1]
    base = float(clean[0][1:].split(")")[0])

    def stamp(k: int, offset: float = 0.0) -> str:
        return f"({base + k + offset:.6f})"

    def frame(k: int, raw: dict, offset: float = 0.0) -> str:
        # strict=False keeps the bad values in the log; bit widths are still checked.
        payload = db.encode_message(HEARTBEAT_MESSAGE, raw, scaling=False, strict=False)
        return f"{stamp(k, offset)} {channel} 120#{payload.hex().upper()} R"

    out = []
    for k, line in enumerate(clean):
        if 30 <= k < 40:
            continue
        if k == 50:  # 10500 raw = 105.00 %RH, above the DBC maximum of 100
            line = frame(k, dict(raw_reading(k), Humidity=10500))
        elif k == 60:  # 0xFFFF is the "no valid reading" marker; SensorFault says so
            line = frame(k, dict(raw_reading(k), Temperature=0xFFFF, SensorFault=1))
        elif k == 80:
            line = frame(k, dict(raw_reading(k), QueueLoss=1))
        out.append(line)
        if k == 70:
            out.append(f"{stamp(k, 0.5)} {channel} 20000040#0000000000000000")
        if k == 90:
            out.append(f"{stamp(k, 0.5)} {channel} 120#0102030405060708090A")
        if k == 95:  # a line that goes back in time
            out.append(frame(94, raw_reading(94)))
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    return len(out)


if __name__ == "__main__":
    print(f"wrote {build()} lines to {FAULTS}")
