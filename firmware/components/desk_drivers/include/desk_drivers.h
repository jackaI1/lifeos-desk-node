#ifndef DESK_DRIVERS_H
#define DESK_DRIVERS_H
#include "desk_core.h"
#include "esp_err.h"
#include "driver/i2c_master.h"
#include "driver/spi_master.h"
typedef struct {
    i2c_master_bus_handle_t bus;
    i2c_master_dev_handle_t sensor, display_i2c;
    spi_device_handle_t display_spi;
    bool spi_initialized, display_gpio_initialized;
} desk_drivers_t;
/* Initializes sensor and display independently; a failed peripheral does not
   discard successfully initialized handles. Check each handle before use. */
esp_err_t desk_drivers_init(desk_drivers_t *drivers);
esp_err_t desk_sensor_read(desk_drivers_t *drivers, desk_reading_t *reading);
esp_err_t desk_display_frame(desk_drivers_t *drivers, const uint8_t frame[DESK_FRAME_SIZE]);
void desk_drivers_deinit(desk_drivers_t *drivers);
esp_err_t desk_uart_init(void);
esp_err_t desk_uart_log_cycle(const desk_reading_t *reading,uint32_t queued,uint32_t dropped,bool upload_acked);
void desk_uart_drain(void);
#endif
