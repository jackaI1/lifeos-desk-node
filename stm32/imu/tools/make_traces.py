"""Write the synthetic IMU traces used by the host tests.

There is no physical IMU recording in this repository yet, so these traces come
from a small seeded model of an MPU-6050 at +-2 g and +-250 dps, sampled at
100 Hz. Each trace is deterministic: rerun this script and you get the same files.

    python3 stm32/imu/tools/make_traces.py
"""
import math
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent.parent
G = 16384
GYRO_PER_DPS = 131
RAIL = 32767


def clip(value):
    return max(-32768, min(RAIL, int(round(value))))


def tilt_gravity(roll_deg):
    """Accelerometer counts for gravity tilted by roll_deg around the x axis."""
    rad = math.radians(roll_deg)
    return 0, clip(G * math.sin(rad)), clip(G * math.cos(rad))


def write(name, rows):
    path = ROOT / "traces" / name
    with path.open("w") as handle:
        handle.write("seq,ax,ay,az,gx,gy,gz\n")
        for row in rows:
            handle.write(",".join(str(v) for v in row) + "\n")


def still(rng, count, start_seq, roll_deg=0.0, bias_lsb=66):
    ax0, ay0, az0 = tilt_gravity(roll_deg)
    rows = []
    for i in range(count):
        rows.append((
            start_seq + i,
            clip(ax0 + rng.gauss(0, 10)),
            clip(ay0 + rng.gauss(0, 10)),
            clip(az0 + rng.gauss(0, 10)),
            clip(bias_lsb + rng.gauss(0, 2)),
            clip(rng.gauss(0, 2)),
            clip(rng.gauss(0, 2)),
        ))
    return rows


def make_still(rng):
    # One minute at rest with a 0.5 degree/second gyro bias, which the complementary filter must not drift on.
    write("still.csv", still(rng, 6000, 0))


def make_knock(rng):
    # Desk at rest, then a 1.7 g knock with a fast spin, then the enclosure settles 15 degrees over.
    rows = still(rng, 500, 0)
    seq = 500
    for _ in range(3):
        rows.append((seq, clip(rng.gauss(0, 200)), clip(rng.gauss(0, 200)), 27853,
                     clip(38000 + rng.gauss(0, 50)), clip(rng.gauss(0, 50)), clip(rng.gauss(0, 50))))
        seq += 1
    rows += still(rng, 1000, seq, roll_deg=15.0, bias_lsb=66)
    for i, row in enumerate(rows):
        rows[i] = (i,) + row[1:]
    write("knock.csv", rows)


def make_dropped(rng):
    # A tilt step at 10 seconds, random 5% lost samples, one 80-sample outage, and one duplicate line.
    base = still(rng, 3000, 0, roll_deg=0.0)
    tilted = still(rng, 3000, 0, roll_deg=20.0)
    rows = []
    seq = 0
    for i in range(3000):
        source = base[i] if i < 1000 else tilted[i]
        if 1500 <= i < 1580:
            seq += 1
            continue
        if rng.random() < 0.05:
            seq += 1
            continue
        rows.append((seq,) + source[1:])
        seq += 1
    rows.append(rows[len(rows) // 2])
    write("dropped.csv", rows)


def make_saturated(rng):
    # A gravity ramp into the +-2 g rails, then the gyro hits its negative rail.
    rows = []
    for i in range(300):
        value = int(-40000 + i * 300)
        rows.append((i, clip(value), clip(value // 3), clip(G * 0.2),
                     -32768 if i > 250 else 0, 0, 0))
    write("saturated.csv", rows)


def main():
    rng = random.Random(20260331)
    make_still(rng)
    make_knock(rng)
    make_dropped(rng)
    make_saturated(rng)


if __name__ == "__main__":
    main()
