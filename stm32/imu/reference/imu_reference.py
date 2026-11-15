"""Python reference for stm32/imu/src/imu_core.c.

It repeats the firmware's integer steps exactly. C divides toward zero and
shifts right with rounding toward minus infinity, so this file does the same.
The tests compare its output with the C replay byte for byte.

Usage: python3 imu_reference.py < trace.csv > out.csv
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import imu_tables as t  # noqa: E402

FLAG_SATURATED = 1 << 0
FLAG_GAP = 1 << 1
FLAG_RESET = 1 << 2
FLAG_BUMP = 1 << 3
FLAG_TILT = 1 << 4
FLAG_DUPLICATE = 1 << 5
UINT32 = 1 << 32


def div_trunc(numerator, denominator):
    """C integer division: rounds toward zero."""
    quotient = abs(numerator) // abs(denominator)
    return quotient if (numerator >= 0) == (denominator > 0) else -quotient


def clamp(value, low, high):
    return max(low, min(high, value))


def atan_ratio_mdeg(num, den):
    q = (num * 256 * 4096) // den
    i = q >> 12
    frac = q & 4095
    if i >= 256:
        return t.IMU_ATAN_TABLE[256]
    return t.IMU_ATAN_TABLE[i] + ((t.IMU_ATAN_TABLE[i + 1] - t.IMU_ATAN_TABLE[i]) * frac >> 12)


def atan2_mdeg(y, x):
    ay, ax = abs(y), abs(x)
    if ax == 0 and ay == 0:
        return 0
    if ay <= ax:
        angle = atan_ratio_mdeg(ay, ax)
    else:
        angle = 90000 - atan_ratio_mdeg(ax, ay)
    if x < 0:
        angle = 180000 - angle
    if y < 0:
        angle = -angle
    return angle


Q31_SHIFT = 14


def wrap64(value):
    return ((value + (1 << 63)) % (1 << 64)) - (1 << 63)


def wrap32(value):
    return ((value + (1 << 31)) % (1 << 32)) - (1 << 31)


def raw_to_q31(raw):
    return wrap32(raw * (1 << Q31_SHIFT))


class Biquad:
    """Mirror of arm_biquad_cascade_df1_q31 (generic C path) with postShift = 1.

    The CMSIS code keeps a 64-bit accumulator, shifts it right by 30 bits and keeps the
    low 32 bits. The states are x[n-1], x[n-2], y[n-1], y[n-2].
    """

    def __init__(self):
        self.x1 = self.x2 = self.y1 = self.y2 = 0

    def prime(self, x_q31):
        self.x1 = self.x2 = self.y1 = self.y2 = x_q31

    def step(self, x_q31):
        c0, c1, c2, c3, c4 = t.IMU_COEFFS_Q31
        acc = wrap64(c0 * x_q31 + c1 * self.x1 + c2 * self.x2 + c3 * self.y1 + c4 * self.y2)
        y = wrap32(acc >> 30)
        self.x2, self.x1 = self.x1, x_q31
        self.y2, self.y1 = self.y1, y
        return y


class Filter:
    def __init__(self):
        self.started = False
        self.last_seq = 0
        self.dropped = 0
        self.roll = 0
        self.pitch = 0
        self.base_roll = 0
        self.base_pitch = 0
        self.accel = [Biquad(), Biquad(), Biquad()]
        self.gyro = [Biquad(), Biquad(), Biquad()]

    def step(self, seq, raw_accel, raw_gyro):
        flags = 0
        for value in raw_accel + raw_gyro:
            if value in (32767, -32768):
                flags |= FLAG_SATURATED
        magnitude2 = sum(v * v for v in raw_accel)
        high = t.IMU_BUMP_HIGH_NUM * t.IMU_G_LSB
        low = t.IMU_BUMP_LOW_NUM * t.IMU_G_LSB
        if 4 * magnitude2 > high * high or 4 * magnitude2 < low * low:
            flags |= FLAG_BUMP
        for value in raw_gyro:
            if abs(div_trunc(value * 1000, t.IMU_GYRO_LSB_PER_DPS)) > t.IMU_SPIN_MDPS:
                flags |= FLAG_BUMP

        if not self.started:
            for axis in range(3):
                self.accel[axis].prime(raw_to_q31(raw_accel[axis]))
                self.gyro[axis].prime(raw_to_q31(raw_gyro[axis]))
            accel, gyro = list(raw_accel), list(raw_gyro)
        else:
            if seq <= self.last_seq:
                return {
                    "roll": self.roll, "pitch": self.pitch, "gyro": [0, 0, 0],
                    "accel": [0, 0, 0], "dropped": self.dropped, "flags": FLAG_DUPLICATE,
                }
            accel = [self.accel[a].step(raw_to_q31(raw_accel[a])) >> Q31_SHIFT for a in range(3)]
            gyro = [self.gyro[a].step(raw_to_q31(raw_gyro[a])) >> Q31_SHIFT for a in range(3)]

        accel_mg = [div_trunc(v * 1000, t.IMU_G_LSB) for v in accel]
        gyro_mdps = [div_trunc(v * 1000, t.IMU_GYRO_LSB_PER_DPS) for v in gyro]
        roll_accel = atan2_mdeg(accel[1], accel[2])
        pitch_accel = atan2_mdeg(accel[0], accel[2])

        if not self.started:
            self.started = True
            self.roll = roll_accel
            self.pitch = pitch_accel
            self.base_roll = roll_accel
            self.base_pitch = pitch_accel
            self.last_seq = seq
        else:
            gap = (seq - self.last_seq - 1) % UINT32
            if gap > 0:
                flags |= FLAG_GAP
                self.dropped = (self.dropped + gap) % UINT32
            self.last_seq = seq
            if gap > t.IMU_MAX_GAP:
                flags |= FLAG_RESET
                self.roll = roll_accel
                self.pitch = pitch_accel
            else:
                steps = gap + 1
                roll_gyro = self.roll + div_trunc(gyro_mdps[0] * t.IMU_SAMPLE_MS * steps, 1000)
                pitch_gyro = self.pitch + div_trunc(gyro_mdps[1] * t.IMU_SAMPLE_MS * steps, 1000)
                self.roll = (t.IMU_ALPHA_Q8 * roll_gyro + (256 - t.IMU_ALPHA_Q8) * roll_accel + 128) >> 8
                self.pitch = (t.IMU_ALPHA_Q8 * pitch_gyro + (256 - t.IMU_ALPHA_Q8) * pitch_accel + 128) >> 8

        if abs(self.roll - self.base_roll) > t.IMU_TILT_MDEG or \
                abs(self.pitch - self.base_pitch) > t.IMU_TILT_MDEG:
            flags |= FLAG_TILT

        return {
            "roll": self.roll, "pitch": self.pitch, "gyro": gyro_mdps,
            "accel": accel_mg, "dropped": self.dropped, "flags": flags,
        }


def run(lines):
    """Yield one output line per input sample line, given the CSV lines (header included)."""
    iterator = iter(lines)
    header = next(iterator, None)
    if header is None:
        return
    if not header.startswith("seq,"):
        raise ValueError("missing header line")
    state = Filter()
    for line in iterator:
        if not line.strip():
            continue
        seq, ax, ay, az, gx, gy, gz = (int(v) for v in line.split(","))
        for value in (ax, ay, az, gx, gy, gz):
            if value < -32768 or value > 32767:
                raise ValueError("value outside int16: " + line.strip())
        out = state.step(seq, [ax, ay, az], [gx, gy, gz])
        yield "%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d" % (
            seq, out["roll"], out["pitch"], out["gyro"][0], out["gyro"][1], out["gyro"][2],
            out["accel"][0], out["accel"][1], out["accel"][2], out["dropped"], out["flags"])


def main():
    for row in run(sys.stdin.read().splitlines()):
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
