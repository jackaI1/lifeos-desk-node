# Motion and tilt filter: design notes

This is the detail behind the [README section](../../../README.md#know-when-the-enclosure-gets-knocked).

## Units and scale

| Quantity | Raw counts | Converted |
| --- | --- | --- |
| Accelerometer, +-2 g | 16384 LSB per g | millig, truncated toward zero |
| Gyroscope, +-250 dps | 131 LSB per deg/s | millidegrees per second |
| Angles | none | millidegrees, from an atan2 table |

Every value is an `int32`. The biquad keeps its sum in 64 bits, rounds it, and clamps it to the 16-bit range. Division truncates toward zero, as in C. The Python reference uses the same rule, so both implementations agree bit for bit.

## Pipeline per sample

1. Saturation: any raw axis at 32767 or -32768 sets `IMU_FLAG_SATURATED`.
2. Bump: on the raw accelerometer, `4|a|^2` is compared with `(3 g)^2` and `(1 g)^2`. A gyro spike above 200 deg/s also sets BUMP.
3. Low-pass: a 2nd-order Butterworth filter at 10 Hz, sampled at 100 Hz, in Q30 direct form I. It runs on each accelerometer and gyro axis. The first sample primes the filter state, so there is no start-up transient.
4. Accelerometer angles: roll = atan2(ay, az), pitch = atan2(ax, az), from the filtered values.
5. Complementary filter: `angle = (251 * (angle + gyro * dt) + 5 * accel + 128) >> 8`. The gyro weight is 251/256, about 0.98. The rounding term keeps the steady drift from a floor shift near zero.
6. Gaps: a sequence number that skips n samples adds `n` to `dropped` and sets `GAP`. The gyro rate is held across the gap. A gap above 50 samples restarts the angle from the accelerometer and sets `RESET`.
7. Duplicates: a sequence number that is not new is reported with `DUPLICATE` and changes no state.
8. Tilt: an angle more than 5 degrees from the start pose sets `TILT`.

## Why the bias does not blow up

A gyro with a constant bias b adds a steady angle error of `b * dt * alpha / (1 - alpha)`. With b = 0.5 deg/s, dt = 10 ms and alpha = 0.98, that is about 0.25 degrees. The filter does not estimate the bias, so it stays at that offset while the desk is still. The test `test_gyro_bias_bounded` checks that offset.

## Where the constants come from

`tools/gen_tables.py` computes the biquad coefficients and the arctangent table, and writes both `src/imu_tables.h` and `reference/imu_tables.py`. The C and Python code read the same numbers. CI regenerates them and fails if the committed files differ.

## What is not done

- No physical IMU recording. The traces come from a seeded model in `tools/make_traces.py`.
- The HAL port is checked for compile errors on Cortex-M4 in CI. It has not run on a Nucleo board or been checked for sample timing on hardware.
- The biquad is written in plain C. The port does not call the CMSIS-DSP library.
- The desk-node enclosure has no mounting or wiring for the IMU yet.
