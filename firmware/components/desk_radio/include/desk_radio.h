#ifndef DESK_RADIO_H
#define DESK_RADIO_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define DESK_BLE_SIZE 16U
typedef struct { uint32_t sequence; int32_t temperature_mc; uint32_t humidity_mpermil; } desk_radio_reading_t;
typedef struct { uint32_t attempts; uint64_t next_ms; bool connected; } desk_wifi_retry_t;
uint16_t desk_radio_crc(const uint8_t *data, size_t size);
bool desk_ble_encode(uint8_t *out, size_t capacity, const desk_radio_reading_t *reading);
bool desk_ble_decode(const uint8_t *data, size_t size, desk_radio_reading_t *reading);
bool desk_notify_due(uint64_t now_ms, uint64_t *last_ms, bool *sent);
uint32_t desk_wifi_lost(desk_wifi_retry_t *retry, uint64_t now_ms);
void desk_wifi_connected(desk_wifi_retry_t *retry);
bool desk_wifi_due(const desk_wifi_retry_t *retry, uint64_t now_ms);
#endif
