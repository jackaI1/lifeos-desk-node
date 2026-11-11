#ifndef DESK_BLE_H
#define DESK_BLE_H
#include "desk_core.h"
#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>

/* Reads one sensor sample for the BLE window. Returns false when the sample is unusable. */
typedef bool (*desk_ble_sampler_t)(void *context, desk_reading_t *reading);

/* Advertises for `seconds` after a wake, then stops. `first` is the sample taken for this
   wake; the sampler is called every ~10 s and notifies subscribed phones when the value
   moved enough. Requires CONFIG_DESK_BLE_ENABLE (NimBLE build). */
esp_err_t desk_ble_window(desk_ble_sampler_t sampler, void *context, const desk_reading_t *first,
                          uint32_t seconds);

#endif
