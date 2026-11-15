#include "imu_core.h"

#include "imu_tables.h"

#include "arm_math.h"

#include <string.h>

/* C division truncates toward zero. The Python reference uses the same rule. */
static int64_t div_trunc(int64_t numerator, int64_t denominator) {
    return numerator / denominator;
}

static int64_t abs64(int64_t value) {
    return value < 0 ? -value : value;
}

/* atan(num / den) in millidegrees for 0 <= num <= den, den > 0. */
static int64_t atan_ratio_mdeg(int64_t num, int64_t den) {
    int64_t q = (num * 256 * 4096) / den; /* index in 1/4096 steps of 1/256 */
    int64_t i = q >> 12;
    int64_t frac = q & 4095;
    if (i >= 256)
        return IMU_ATAN_TABLE[256];
    return IMU_ATAN_TABLE[i] +
           (((int64_t)IMU_ATAN_TABLE[i + 1] - IMU_ATAN_TABLE[i]) * frac >> 12);
}

int32_t imu_atan2_mdeg(int32_t y, int32_t x) {
    int64_t ay = abs64(y);
    int64_t ax = abs64(x);
    int64_t angle;
    if (ax == 0 && ay == 0)
        return 0;
    if (ay <= ax)
        angle = atan_ratio_mdeg(ay, ax);
    else
        angle = 90000 - atan_ratio_mdeg(ax, ay);
    if (x < 0)
        angle = 180000 - angle;
    if (y < 0)
        angle = -angle;
    return (int32_t)angle;
}

void imu_init(imu_state_t *state) {
    memset(state, 0, sizeof *state);
}

/* Raw counts are scaled into q31 so the full +-32768 range sits at +-0.25, which is
 * the input range the CMSIS q31 biquad is specified for (it wraps above that). */
#define IMU_Q31_SHIFT 14

static int32_t raw_to_q31(int32_t raw) {
    return (int32_t)(raw * (1 << IMU_Q31_SHIFT));
}

/* arm_biquad_cascade_df1_q31 with postShift = 1: the 2nd-order Butterworth low-pass.
 * The output keeps the q31 scale, so shifting back gives counts again. */
static int32_t biquad_step(imu_biquad_t *f, int32_t raw) {
    q31_t in = raw_to_q31(raw);
    q31_t out = 0;
    arm_biquad_cascade_df1_q31(&f->inst, &in, &out, 1);
    return out >> IMU_Q31_SHIFT;
}

/* A constant input at steady state (DC gain 1) means every state equals that input,
 * so the filter starts with no step transient. */
static void biquad_prime(imu_biquad_t *f, int32_t raw) {
    q31_t x = raw_to_q31(raw);
    arm_biquad_cascade_df1_init_q31(&f->inst, 1, IMU_COEFFS_Q31, f->state, 1);
    f->state[0] = f->state[1] = f->state[2] = f->state[3] = x;
}

static int32_t lsb_to_mg(int32_t lsb) {
    return (int32_t)div_trunc((int64_t)lsb * 1000, IMU_G_LSB);
}

static int32_t lsb_to_mdps(int32_t lsb) {
    return (int32_t)div_trunc((int64_t)lsb * 1000, IMU_GYRO_LSB_PER_DPS);
}

static int32_t blend_angle(int32_t gyro_angle, int32_t accel_angle) {
    /* Round to nearest: a plain floor shift loses up to one count per step, which the
     * feedback multiplies by about 50 and shows up as a steady drift of tens of millidegrees. */
    int64_t mixed = (int64_t)IMU_ALPHA_Q8 * gyro_angle +
                    (int64_t)(256 - IMU_ALPHA_Q8) * accel_angle + 128;
    return (int32_t)(mixed >> 8);
}

void imu_step(imu_state_t *state, const imu_sample_t *sample, imu_out_t *out) {
    int16_t raw_accel[3] = {sample->ax, sample->ay, sample->az};
    int16_t raw_gyro[3] = {sample->gx, sample->gy, sample->gz};
    int32_t accel[3], gyro[3];
    uint32_t flags = 0;
    int64_t magnitude2;
    int32_t roll_accel, pitch_accel;
    int i;

    memset(out, 0, sizeof *out);

    for (i = 0; i < 3; ++i) {
        if (raw_accel[i] == 32767 || raw_accel[i] == -32768)
            flags |= IMU_FLAG_SATURATED;
        if (raw_gyro[i] == 32767 || raw_gyro[i] == -32768)
            flags |= IMU_FLAG_SATURATED;
    }

    /* Bump and free-fall check, on the unfiltered accelerometer. */
    magnitude2 = (int64_t)sample->ax * sample->ax + (int64_t)sample->ay * sample->ay +
                 (int64_t)sample->az * sample->az;
    {
        /* Compare 4*|a|^2 with (3 g)^2 and (1 g)^2, i.e. |a| against 1.5 g and 0.5 g. */
        int64_t high = (int64_t)IMU_BUMP_HIGH_NUM * IMU_G_LSB;
        int64_t low = (int64_t)IMU_BUMP_LOW_NUM * IMU_G_LSB;
        if (4 * magnitude2 > high * high || 4 * magnitude2 < low * low)
            flags |= IMU_FLAG_BUMP;
    }
    for (i = 0; i < 3; ++i)
        if (abs64(lsb_to_mdps(raw_gyro[i])) > IMU_SPIN_MDPS)
            flags |= IMU_FLAG_BUMP;

    if (!state->started) {
        for (i = 0; i < 3; ++i) {
            biquad_prime(&state->accel[i], raw_accel[i]);
            biquad_prime(&state->gyro[i], raw_gyro[i]);
            accel[i] = raw_accel[i];
            gyro[i] = raw_gyro[i];
        }
    } else {
        if (sample->seq <= state->last_seq) {
            /* Duplicate or out-of-order: report the current estimate, change nothing. */
            out->roll_mdeg = state->roll_mdeg;
            out->pitch_mdeg = state->pitch_mdeg;
            out->dropped = state->dropped;
            out->flags = IMU_FLAG_DUPLICATE;
            for (i = 0; i < 3; ++i) {
                out->accel_mg[i] = 0;
                out->gyro_mdps[i] = 0;
            }
            return;
        }
        for (i = 0; i < 3; ++i) {
            accel[i] = biquad_step(&state->accel[i], raw_accel[i]);
            gyro[i] = biquad_step(&state->gyro[i], raw_gyro[i]);
        }
    }

    for (i = 0; i < 3; ++i) {
        out->accel_mg[i] = lsb_to_mg(accel[i]);
        out->gyro_mdps[i] = lsb_to_mdps(gyro[i]);
    }

    /* Roll is the angle of the y-z plane from gravity, pitch the x-z plane. */
    roll_accel = imu_atan2_mdeg(accel[1], accel[2]);
    pitch_accel = imu_atan2_mdeg(accel[0], accel[2]);

    if (!state->started) {
        state->started = 1;
        state->roll_mdeg = roll_accel;
        state->pitch_mdeg = pitch_accel;
        state->base_roll_mdeg = roll_accel;
        state->base_pitch_mdeg = pitch_accel;
        state->last_seq = sample->seq;
    } else {
        uint32_t gap = sample->seq - state->last_seq - 1u;
        if (gap > 0) {
            flags |= IMU_FLAG_GAP;
            state->dropped += gap;
        }
        state->last_seq = sample->seq;

        if (gap > IMU_MAX_GAP) {
            flags |= IMU_FLAG_RESET;
            state->roll_mdeg = roll_accel;
            state->pitch_mdeg = pitch_accel;
        } else {
            /* A missing sample is covered by holding the last gyro rate over the gap. */
            int64_t steps = (int64_t)gap + 1;
            int32_t roll_gyro =
                state->roll_mdeg +
                (int32_t)div_trunc((int64_t)out->gyro_mdps[0] * IMU_SAMPLE_MS * steps, 1000);
            int32_t pitch_gyro =
                state->pitch_mdeg +
                (int32_t)div_trunc((int64_t)out->gyro_mdps[1] * IMU_SAMPLE_MS * steps, 1000);
            state->roll_mdeg = blend_angle(roll_gyro, roll_accel);
            state->pitch_mdeg = blend_angle(pitch_gyro, pitch_accel);
        }
    }

    if (abs64((int64_t)state->roll_mdeg - state->base_roll_mdeg) > IMU_TILT_MDEG ||
        abs64((int64_t)state->pitch_mdeg - state->base_pitch_mdeg) > IMU_TILT_MDEG)
        flags |= IMU_FLAG_TILT;

    out->roll_mdeg = state->roll_mdeg;
    out->pitch_mdeg = state->pitch_mdeg;
    out->dropped = state->dropped;
    out->flags = flags;
}
