/* Host unit tests for the IMU filter. Built with ASan and UBSan by the Makefile. */
#include "imu_core.h"
#include "imu_tables.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures = 0;

#define CHECK(cond)                                                      \
    do {                                                                 \
        if (!(cond)) {                                                   \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__,       \
                    __LINE__, #cond);                                    \
            ++failures;                                                  \
        }                                                                \
    } while (0)

static void near_int(int32_t got, int32_t want, int32_t tolerance, int line) {
    if (abs(got - want) > tolerance) {
        fprintf(stderr, "line %d: got %d want %d +-%d\n", line, got, want, tolerance);
        ++failures;
    }
}
#define NEAR(got, want, tol) near_int((int32_t)(got), (int32_t)(want), (int32_t)(tol), __LINE__)

static imu_sample_t sample(uint32_t seq, int ax, int ay, int az, int gx, int gy, int gz) {
    imu_sample_t s;
    s.seq = seq;
    s.ax = (int16_t)ax;
    s.ay = (int16_t)ay;
    s.az = (int16_t)az;
    s.gx = (int16_t)gx;
    s.gy = (int16_t)gy;
    s.gz = (int16_t)gz;
    return s;
}

/* Analytic checks: atan2 must match the exact angle to within 0.1 degree. */
static void test_atan2_analytic(void) {
    NEAR(imu_atan2_mdeg(0, 1000), 0, 1);
    NEAR(imu_atan2_mdeg(1000, 1000), 45000, 100);
    NEAR(imu_atan2_mdeg(1000, 0), 90000, 1);
    NEAR(imu_atan2_mdeg(-1000, 0), -90000, 1);
    NEAR(imu_atan2_mdeg(0, -1000), 180000, 1);
    NEAR(imu_atan2_mdeg(-1000, -1000), -135000, 100);
    NEAR(imu_atan2_mdeg(1000, -1000), 135000, 100);
    NEAR(imu_atan2_mdeg(0, 0), 0, 0);
    /* 15 degrees: tan(15) = 0.26795, so y = 0.26795 * x. */
    NEAR(imu_atan2_mdeg(26795, 100000), 15000, 100);
    /* Table range check across the whole circle, against libm. */
    for (int deg = -179; deg <= 180; deg += 7) {
        double rad = deg * 3.14159265358979323846 / 180.0;
        int32_t y = (int32_t)lround(sin(rad) * 20000.0);
        int32_t x = (int32_t)lround(cos(rad) * 20000.0);
        double want = atan2((double)y, (double)x) * 180000.0 / 3.14159265358979323846;
        NEAR(imu_atan2_mdeg(y, x), (int32_t)lround(want), 120);
    }
}

/* Steady state: a gravity-only sensor reads zero tilt and no bump. */
static void test_still_zero_tilt(void) {
    imu_state_t s;
    imu_out_t o;
    imu_init(&s);
    for (uint32_t i = 0; i < 500; ++i) {
        imu_sample_t in = sample(i, 0, 0, 16384, 0, 0, 0);
        imu_step(&s, &in, &o);
    }
    NEAR(o.roll_mdeg, 0, 5);
    NEAR(o.pitch_mdeg, 0, 5);
    CHECK(o.flags == 0);
    NEAR(o.accel_mg[2], 1000, 2);
}

/* DC gain of the low-pass is 1: a step of 1000 counts settles to 1000 counts. */
static void test_biquad_dc_gain(void) {
    imu_state_t s;
    imu_out_t o;
    imu_init(&s);
    imu_sample_t in = sample(0, 0, 0, 0, 0, 0, 0);
    imu_step(&s, &in, &o);
    for (uint32_t i = 1; i < 400; ++i) {
        in = sample(i, 1000, 0, 0, 0, 0, 0);
        imu_step(&s, &in, &o);
    }
    NEAR(o.accel_mg[0], 61, 1); /* 1000 counts is 61 mg of the 16384 LSB/g scale */
}

/* Drift: a 0.5 degree/second gyro bias must settle to a bounded offset, not grow without limit. */
static void test_gyro_bias_bounded(void) {
    imu_state_t s;
    imu_out_t o;
    imu_init(&s);
    for (uint32_t i = 0; i < 6000; ++i) {
        imu_sample_t in = sample(i, 0, 0, 16384, 66, 0, 0);
        imu_step(&s, &in, &o);
    }
    /* Steady offset = bias*dt*alpha/(1-alpha) = 0.5*0.01*0.98/0.02 deg = 0.245 deg. */
    CHECK(abs(o.roll_mdeg) < 300);
    CHECK(abs(o.roll_mdeg) > 200);
    CHECK((o.flags & IMU_FLAG_TILT) == 0);
}

/* The accelerometer pulls the estimate back after a real tilt. */
static void test_tilt_tracks_and_flags(void) {
    imu_state_t s;
    imu_out_t o;
    imu_init(&s);
    for (uint32_t i = 0; i < 100; ++i) {
        imu_sample_t in = sample(i, 0, 0, 16384, 0, 0, 0);
        imu_step(&s, &in, &o);
    }
    /* Roll 30 degrees: y = G sin30, z = G cos30, zero gyro. */
    uint32_t last_flags = 0;
    for (uint32_t i = 100; i < 1100; ++i) {
        imu_sample_t in = sample(i, 0, 8192, 14189, 0, 0, 0);
        imu_step(&s, &in, &o);
        last_flags = o.flags;
    }
    NEAR(o.roll_mdeg, 30000, 300);
    CHECK((last_flags & IMU_FLAG_TILT) != 0);
}

/* Saturation: rails raise the flag, and extreme values never overflow or go out of range. */
static void test_saturation(void) {
    imu_state_t s;
    imu_out_t o;
    imu_init(&s);
    imu_sample_t in = sample(0, 32767, 32767, 32767, 32767, 32767, 32767);
    imu_step(&s, &in, &o);
    CHECK((o.flags & IMU_FLAG_SATURATED) != 0);
    for (uint32_t i = 1; i < 200; ++i) {
        in = sample(i, -32768, 32767, -32768, -32768, 32767, -32768);
        imu_step(&s, &in, &o);
        CHECK((o.flags & IMU_FLAG_SATURATED) != 0);
        CHECK(o.roll_mdeg >= -180000 && o.roll_mdeg <= 180000);
        CHECK(o.pitch_mdeg >= -180000 && o.pitch_mdeg <= 180000);
        /* A 2nd-order Butterworth overshoots a full-scale step by about 4 percent. */
        CHECK(o.accel_mg[0] >= -2200 && o.accel_mg[0] <= 2200);
    }
}

/* Dropped samples: a 3-sample gap is counted and flagged, the angle keeps tracking. */
static void test_dropped_samples(void) {
    imu_state_t s;
    imu_out_t o;
    imu_init(&s);
    imu_sample_t in = sample(0, 0, 0, 16384, 0, 0, 0);
    imu_step(&s, &in, &o);
    in = sample(1, 0, 0, 16384, 0, 0, 0);
    imu_step(&s, &in, &o);
    in = sample(5, 0, 0, 16384, 0, 0, 0);
    imu_step(&s, &in, &o);
    CHECK(o.dropped == 3);
    CHECK((o.flags & IMU_FLAG_GAP) != 0);
    CHECK((o.flags & IMU_FLAG_RESET) == 0);
}

/* A gap longer than IMU_MAX_GAP restarts the angle from the accelerometer. */
static void test_long_gap_resets(void) {
    imu_state_t s;
    imu_out_t o;
    imu_init(&s);
    imu_sample_t in = sample(0, 0, 0, 16384, 0, 0, 0);
    imu_step(&s, &in, &o);
    /* Gyro-only drift before the outage: 100 dps for many steps would move the angle. */
    in = sample(1, 0, 0, 16384, 13100, 0, 0);
    imu_step(&s, &in, &o);
    in = sample(1 + IMU_MAX_GAP + 10, 0, 10000, 12000, 0, 0, 0);
    imu_step(&s, &in, &o);
    CHECK((o.flags & IMU_FLAG_RESET) != 0);
    CHECK((o.flags & IMU_FLAG_GAP) != 0);
    /* Samples 2..60 are missing: 59 in total. */
    CHECK(o.dropped == (uint32_t)(IMU_MAX_GAP + 9));
    /* The biquad lags a step, so the restarted angle sits between 0 and the raw angle. */
    CHECK(o.roll_mdeg > 0 && o.roll_mdeg < imu_atan2_mdeg(10000, 12000));
}

/* Duplicate or out-of-order samples change nothing. */
static void test_duplicate_ignored(void) {
    imu_state_t s;
    imu_out_t o, before, dup;
    imu_init(&s);
    for (uint32_t i = 0; i < 50; ++i) {
        imu_sample_t in = sample(i, 0, 0, 16384, 300, 0, 0);
        imu_step(&s, &in, &o);
    }
    before = o;
    imu_sample_t in = sample(10, 0, 0, 16384, 300, 0, 0);
    imu_step(&s, &in, &dup);
    CHECK((dup.flags & IMU_FLAG_DUPLICATE) != 0);
    CHECK(dup.roll_mdeg == before.roll_mdeg);
    CHECK(dup.dropped == before.dropped);
    /* The next real sample continues from the same state. */
    imu_sample_t next = sample(50, 0, 0, 16384, 300, 0, 0);
    imu_out_t after;
    imu_step(&s, &next, &after);
    CHECK((after.flags & (IMU_FLAG_DUPLICATE | IMU_FLAG_GAP)) == 0);
}

/* Bump: a 1.7 g knock and a 300 degree/second spin both raise BUMP. Free fall too. */
static void test_bump_and_free_fall(void) {
    imu_state_t s;
    imu_out_t o;
    imu_init(&s);
    imu_sample_t in = sample(0, 0, 0, 16384, 0, 0, 0);
    imu_step(&s, &in, &o);
    in = sample(1, 0, 0, 27853, 0, 0, 0);
    imu_step(&s, &in, &o);
    CHECK((o.flags & IMU_FLAG_BUMP) != 0);
    in = sample(2, 0, 0, 16384, 27000, 0, 0); /* 206 degrees/second */
    imu_step(&s, &in, &o);
    CHECK((o.flags & IMU_FLAG_BUMP) != 0);
    in = sample(3, 0, 0, 0, 0, 0, 0);
    imu_step(&s, &in, &o);
    CHECK((o.flags & IMU_FLAG_BUMP) != 0);
    in = sample(4, 0, 0, 16384, 0, 0, 0);
    imu_step(&s, &in, &o);
    CHECK((o.flags & IMU_FLAG_BUMP) == 0);
}

int main(void) {
    test_atan2_analytic();
    test_still_zero_tilt();
    test_biquad_dc_gain();
    test_gyro_bias_bounded();
    test_tilt_tracks_and_flags();
    test_saturation();
    test_dropped_samples();
    test_long_gap_resets();
    test_duplicate_ignored();
    test_bump_and_free_fall();
    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    printf("PASS: imu_core host tests\n");
    return 0;
}
