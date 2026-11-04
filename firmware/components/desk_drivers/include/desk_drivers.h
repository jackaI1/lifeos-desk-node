#ifndef DESK_DRIVERS_H
#define DESK_DRIVERS_H
#include "desk_core.h"
#include "esp_err.h"
#include "driver/i2c_master.h"
typedef struct {
    i2c_master_bus_handle_t bus;
    i2c_master_dev_handle_t sensor, display;
} desk_drivers_t;
esp_err_t desk_drivers_init(desk_drivers_t *drivers);
esp_err_t desk_sensor_read(desk_drivers_t *drivers, desk_reading_t *reading);
esp_err_t desk_display_frame(desk_drivers_t *drivers, const uint8_t frame[DESK_FRAME_SIZE]);
void desk_drivers_deinit(desk_drivers_t *drivers);
#endif
