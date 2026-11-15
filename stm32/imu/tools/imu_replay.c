/* Host replay: read IMU trace CSV on stdin, write the filter output as CSV.
 *
 * Input lines:  seq,ax,ay,az,gx,gy,gz   (raw sensor counts; first line is a header)
 * Output lines: seq,roll_mdeg,pitch_mdeg,gx_mdps,gy_mdps,gz_mdps,
 *               ax_mg,ay_mg,az_mg,dropped,flags
 * The Python reference prints the same format, and the tests compare them byte for byte.
 */
#include "imu_core.h"

#include <stdio.h>
#include <string.h>

int main(void) {
    char line[256];
    imu_state_t state;
    imu_init(&state);
    if (!fgets(line, sizeof line, stdin))
        return 0;
    if (strncmp(line, "seq,", 4) != 0) {
        fprintf(stderr, "imu_replay: missing header line\n");
        return 2;
    }
    while (fgets(line, sizeof line, stdin)) {
        imu_sample_t sample;
        imu_out_t out;
        unsigned long seq;
        int ax, ay, az, gx, gy, gz;
        if (sscanf(line, "%lu,%d,%d,%d,%d,%d,%d", &seq, &ax, &ay, &az, &gx, &gy, &gz) != 7) {
            fprintf(stderr, "imu_replay: bad line: %s", line);
            return 2;
        }
        if (ax < -32768 || ax > 32767 || ay < -32768 || ay > 32767 || az < -32768 ||
            az > 32767 || gx < -32768 || gx > 32767 || gy < -32768 || gy > 32767 ||
            gz < -32768 || gz > 32767) {
            fprintf(stderr, "imu_replay: value outside int16: %s", line);
            return 2;
        }
        sample.seq = (uint32_t)seq;
        sample.ax = (int16_t)ax;
        sample.ay = (int16_t)ay;
        sample.az = (int16_t)az;
        sample.gx = (int16_t)gx;
        sample.gy = (int16_t)gy;
        sample.gz = (int16_t)gz;
        imu_step(&state, &sample, &out);
        printf("%lu,%d,%d,%d,%d,%d,%d,%d,%d,%u,%u\n", seq, out.roll_mdeg, out.pitch_mdeg,
               out.gyro_mdps[0], out.gyro_mdps[1], out.gyro_mdps[2], out.accel_mg[0],
               out.accel_mg[1], out.accel_mg[2], (unsigned)out.dropped, (unsigned)out.flags);
    }
    return 0;
}
