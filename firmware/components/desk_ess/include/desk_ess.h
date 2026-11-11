#ifndef DESK_ESS_H
#define DESK_ESS_H
#include "desk_core.h"
#include <stdbool.h>
#include <stdint.h>

/* Values for the Bluetooth SIG Environmental Sensing service (0x181A):
   temperature (0x2A6E) is sint16 in 0.01 degC, humidity (0x2A6F) is uint16 in 0.01 %RH.
   Both are little-endian on the air. */
#define DESK_ESS_TEMPERATURE_MIN_C100 (-4500)
#define DESK_ESS_TEMPERATURE_MAX_C100 12500
#define DESK_ESS_HUMIDITY_MAX_C100 10000U
/* A notification is worth sending only after the value moved this much (0.10 degC, 0.50 %RH). */
#define DESK_ESS_TEMPERATURE_STEP 10
#define DESK_ESS_HUMIDITY_STEP 50

typedef struct {
    int16_t temperature_c100;
    uint16_t humidity_c100;
} desk_ess_value_t;

typedef struct {
    bool notified;
    uint64_t last_ms;
    desk_ess_value_t last;
} desk_ess_notify_t;

/* Converts a validated reading (millidegrees, 0.001 %RH) to service units, rounding half away from zero.
   Returns false when the value is outside the range the service can describe. */
bool desk_ess_from_reading(const desk_reading_t *reading, desk_ess_value_t *value);
/* Decodes raw SHT31 bytes. A CRC failure or a full-scale value outside the sensor
   range (for example a stuck 0xffff reading) returns false and leaves *value unchanged. */
bool desk_ess_from_sht31(const uint8_t raw[6], desk_ess_value_t *value);
void desk_ess_encode(const desk_ess_value_t *value, uint8_t temperature[2], uint8_t humidity[2]);
/* True for the first value, and afterwards only when the value moved by a step
   and at least min_interval_ms passed since the last notification. */
bool desk_ess_should_notify(const desk_ess_notify_t *state, const desk_ess_value_t *value,
                            uint64_t now_ms, uint32_t min_interval_ms);
void desk_ess_mark_notified(desk_ess_notify_t *state, const desk_ess_value_t *value, uint64_t now_ms);

#endif
