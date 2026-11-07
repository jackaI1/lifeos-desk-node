#include "telematics.h"
#include <stdio.h>
#include <string.h>
int main(void) {
    char line[84];
    unsigned accepted = 0, rejected = 0;
    while (fgets(line, sizeof line, stdin)) {
        size_t length = strlen(line);
        bool complete = length > 0 && line[length - 1] == '\n';
        if (!complete && !feof(stdin)) {
            int c;
            while ((c = getchar()) != '\n' && c != EOF) {
            }
            ++rejected;
            continue;
        }
        if (length && line[length - 1] == '\n')
            --length;
        if (length && line[length - 1] == '\r')
            --length;
        gps_fix_t fix;
        if (nmea_parse(line, length, &fix)) {
            ++accepted;
            printf("%s latitude=%.6f longitude=%.6f speed_kph=%.3f\n", fix.kind, fix.latitude,
                   fix.longitude, fix.speed_kph);
        } else {
            unsigned id, b[8];
            char extra;
            if (sscanf(line, "CAN %x %x %x %x %x %x %x %x %x %c", &id, &b[0], &b[1], &b[2], &b[3],
                       &b[4], &b[5], &b[6], &b[7], &extra) == 9) {
                uint8_t bytes[8];
                bool valid = true;
                for (size_t i = 0; i < 8; ++i) {
                    if (b[i] > 255)
                        valid = false;
                    bytes[i] = (uint8_t)b[i];
                }
                obd_value_t value;
                if (valid && obd_parse(id, bytes, 8, &value)) {
                    ++accepted;
                    printf("OBD pid=%02x value=%.2f\n", value.pid, value.value);
                    continue;
                }
            }
            ++rejected;
        }
    }
    fprintf(stderr, "accepted=%u rejected=%u\n", accepted, rejected);
    return ferror(stdin) ? 1 : 0;
}
