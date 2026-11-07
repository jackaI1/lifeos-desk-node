#ifndef DESK_BLE_H
#define DESK_BLE_H
#include "desk_core.h"
#include "esp_err.h"
esp_err_t desk_ble_start(const desk_reading_t *sample);
#endif
