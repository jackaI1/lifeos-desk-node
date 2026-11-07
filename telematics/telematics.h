#ifndef DESK_TELEMATICS_H
#define DESK_TELEMATICS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    char kind[4];
    double latitude, longitude;
    double speed_kph;
    uint8_t fix, satellites;
} gps_fix_t;
typedef struct {
    uint8_t pid;
    double value;
} obd_value_t;
bool nmea_parse(const char *sentence, size_t length, gps_fix_t *out);
bool obd_parse(uint32_t id, const uint8_t *data, size_t length, obd_value_t *out);
#ifdef __cplusplus
}
#endif
#endif
