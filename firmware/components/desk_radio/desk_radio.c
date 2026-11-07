#include "desk_radio.h"
static void put32(uint8_t *p, uint32_t value) {
    for (size_t i = 0; i < 4; ++i) {
        p[i] = (uint8_t)(value & 255U);
        value >>= 8;
    }
}
static uint32_t get32(const uint8_t *p) {
    uint32_t value = 0;
    for (size_t i = 0; i < 4; ++i) {
        value |= (uint32_t)p[i] << (8U * i);
    }
    return value;
}
uint16_t desk_radio_crc(const uint8_t *data, size_t size) {
    uint16_t crc = UINT16_C(0xffff);
    for (size_t i = 0; i < size; ++i) {
        crc ^= (uint16_t)((uint16_t)data[i] << 8);
        for (uint8_t bit = 0; bit < 8U; ++bit) {
            crc = (uint16_t)((uint16_t)(crc << 1) ^
                             ((crc & UINT16_C(0x8000)) ? UINT16_C(0x1021) : 0U));
        }
    }
    return crc;
}
bool desk_ble_encode(uint8_t *out, size_t capacity, const desk_radio_reading_t *reading) {
    if (!out || !reading || capacity < DESK_BLE_SIZE || reading->temperature_mc < -45000 ||
        reading->temperature_mc > 125000 || reading->humidity_mpermil > 100000U)
        return false;
    out[0] = 1;
    out[1] = 0;
    put32(out + 2, (uint32_t)reading->temperature_mc);
    put32(out + 6, reading->humidity_mpermil);
    put32(out + 10, reading->sequence);
    uint16_t crc = desk_radio_crc(out, 14);
    out[14] = (uint8_t)crc;
    out[15] = (uint8_t)(crc >> 8);
    return true;
}
bool desk_ble_decode(const uint8_t *data, size_t size, desk_radio_reading_t *reading) {
    if (!data || !reading || size != DESK_BLE_SIZE || data[0] != 1 || data[1] != 0 ||
        desk_radio_crc(data, 14) != ((uint16_t)data[14] | (uint16_t)((uint16_t)data[15] << 8)))
        return false;
    uint32_t raw = get32(data + 2);
    int32_t temperature = raw <= INT32_MAX ? (int32_t)raw : -1 - (int32_t)(UINT32_MAX - raw);
    desk_radio_reading_t decoded = {get32(data + 10), temperature, get32(data + 6)};
    if (decoded.temperature_mc < -45000 || decoded.temperature_mc > 125000 ||
        decoded.humidity_mpermil > 100000U)
        return false;
    *reading = decoded;
    return true;
}
bool desk_notify_due(uint64_t now_ms, uint64_t *last_ms, bool *sent) {
    if (!last_ms || !sent || (*sent && (now_ms < *last_ms || now_ms - *last_ms < 1000U)))
        return false;
    *last_ms = now_ms;
    *sent = true;
    return true;
}
uint32_t desk_wifi_lost(desk_wifi_retry_t *retry, uint64_t now_ms) {
    retry->connected = false;
    if (retry->attempts < 6U)
        ++retry->attempts;
    uint32_t delay = 250U << (retry->attempts - 1U);
    retry->next_ms = now_ms > UINT64_MAX - delay ? UINT64_MAX : now_ms + delay;
    return delay;
}
void desk_wifi_connected(desk_wifi_retry_t *retry) {
    retry->connected = true;
    retry->attempts = 0;
    retry->next_ms = 0;
}
bool desk_wifi_due(const desk_wifi_retry_t *retry, uint64_t now_ms) {
    return !retry->connected && now_ms >= retry->next_ms;
}
