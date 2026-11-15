/* Motion and tilt filter for the desk node IMU.
 *
 * Pure C with no heap, no floating point and no hardware access, so the same
 * file runs on the Nucleo board and under the host sanitizer tests.
 *
 * Each sample is one MPU-6050 reading in raw sensor counts (LSB). The filter
 * low-passes each axis with a 2nd-order biquad, then fuses the gyro (fast but
 * drifts) with the accelerometer (slow but knows which way is down) using a
 * complementary filter. It also raises flags for saturation, dropped or
 * duplicate samples, bumps and tilt.
 */
#ifndef IMU_CORE_H
#define IMU_CORE_H

#include <stdint.h>

enum {
    IMU_FLAG_SATURATED = 1u << 0, /* a raw axis reached the sensor rail */
    IMU_FLAG_GAP = 1u << 1,       /* one or more samples were dropped before this one */
    IMU_FLAG_RESET = 1u << 2,     /* gap too long; angle restarted from accelerometer */
    IMU_FLAG_BUMP = 1u << 3,      /* hard knock (over 1.5 g), free fall or fast spin */
    IMU_FLAG_TILT = 1u << 4,      /* angle is more than 5 degrees from the start pose */
    IMU_FLAG_DUPLICATE = 1u << 5, /* sequence number was not new; state unchanged */
};

typedef struct {
    uint32_t seq; /* sample counter from the sample timer, increases by 1 per tick */
    int16_t ax, ay, az;
    int16_t gx, gy, gz;
} imu_sample_t;

typedef struct {
    int32_t roll_mdeg;
    int32_t pitch_mdeg;
    int32_t accel_mg[3];  /* filtered accelerometer, millig */
    int32_t gyro_mdps[3]; /* filtered gyro, millidegrees per second */
    uint32_t dropped;     /* running total of samples missing before this one */
    uint32_t flags;       /* IMU_FLAG_* bits for this sample */
} imu_out_t;

typedef struct {
    int32_t x1, x2, y1, y2;
} imu_biquad_t;

typedef struct {
    uint8_t started;
    uint32_t last_seq;
    uint32_t dropped;
    int32_t roll_mdeg;
    int32_t pitch_mdeg;
    int32_t base_roll_mdeg;
    int32_t base_pitch_mdeg;
    imu_biquad_t accel[3];
    imu_biquad_t gyro[3];
} imu_state_t;

void imu_init(imu_state_t *state);

/* Feed one sample. Writes the estimate for it into out. */
void imu_step(imu_state_t *state, const imu_sample_t *sample, imu_out_t *out);

/* atan2 in millidegrees, range -180000..180000, from a table with no floating point. */
int32_t imu_atan2_mdeg(int32_t y, int32_t x);

#endif
