#include "desk_ess.h"

/* d must be positive; n is bounded by the callers' range checks, so the arithmetic cannot overflow. */
static int32_t divide_round(int32_t n, int32_t d) {
    return n >= 0 ? (n + d / 2) / d : -((-n + d / 2) / d);
}

static int32_t abs_diff(int32_t a, int32_t b) {
    return a > b ? a - b : b - a;
}

bool desk_ess_from_reading(const desk_reading_t *reading, desk_ess_value_t *value) {
    if (!reading || !value || reading->temperature_mc < -45000 || reading->temperature_mc > 125000 ||
        reading->humidity_mpermil < 0 || reading->humidity_mpermil > 100000)
        return false;
    /* 1 unit = 10 millidegrees (0.01 degC) and 10 millipercent (0.01 %RH). */
    int32_t temperature = divide_round(reading->temperature_mc, 10);
    int32_t humidity = divide_round(reading->humidity_mpermil, 10);
    if (temperature < DESK_ESS_TEMPERATURE_MIN_C100 || temperature > DESK_ESS_TEMPERATURE_MAX_C100 ||
        humidity < 0 || (uint32_t)humidity > DESK_ESS_HUMIDITY_MAX_C100)
        return false;
    value->temperature_c100 = (int16_t)temperature;
    value->humidity_c100 = (uint16_t)humidity;
    return true;
}

bool desk_ess_from_sht31(const uint8_t raw[6], desk_ess_value_t *value) {
    desk_reading_t reading;
    if (!raw || !value || !desk_decode_sht31(raw, &reading))
        return false;
    return desk_ess_from_reading(&reading, value);
}

void desk_ess_encode(const desk_ess_value_t *value, uint8_t temperature[2], uint8_t humidity[2]) {
    uint16_t t = (uint16_t)value->temperature_c100;
    temperature[0] = (uint8_t)(t & 0xffU);
    temperature[1] = (uint8_t)(t >> 8);
    humidity[0] = (uint8_t)(value->humidity_c100 & 0xffU);
    humidity[1] = (uint8_t)(value->humidity_c100 >> 8);
}

bool desk_ess_should_notify(const desk_ess_notify_t *state, const desk_ess_value_t *value,
                            uint64_t now_ms, uint32_t min_interval_ms) {
    if (!state || !value)
        return false;
    if (!state->notified)
        return true;
    if (now_ms < state->last_ms || now_ms - state->last_ms < min_interval_ms)
        return false;
    return abs_diff(value->temperature_c100, state->last.temperature_c100) >= DESK_ESS_TEMPERATURE_STEP ||
           abs_diff(value->humidity_c100, state->last.humidity_c100) >= DESK_ESS_HUMIDITY_STEP;
}

void desk_ess_mark_notified(desk_ess_notify_t *state, const desk_ess_value_t *value, uint64_t now_ms) {
    if (!state || !value)
        return;
    state->notified = true;
    state->last_ms = now_ms;
    state->last = *value;
}
