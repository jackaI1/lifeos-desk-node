#include "desk_can.h"

#include <string.h>

#ifdef ESP_PLATFORM
#include "driver/twai.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
static const char *TAG = "desk_can";
#endif

/* Raw = (C + 40) / 0.01, so C = -40..125 maps to 0..16500 (round half up). */
static bool temperature_raw(int32_t millidegrees, uint16_t *raw) {
    if (millidegrees < -40000 || millidegrees > 125000) return false;
    *raw = (uint16_t)((millidegrees + 40000 + 5) / 10);
    return true;
}

/* Raw = %RH / 0.01, so 0..100 %RH maps to 0..10000 (round half up). */
static bool humidity_raw(int32_t mpermil, uint16_t *raw) {
    if (mpermil < 0 || mpermil > 100000) return false;
    *raw = (uint16_t)((mpermil + 5) / 10);
    return true;
}

bool desk_can_encode(const desk_can_status_t *status, uint8_t out[8]) {
    uint16_t temperature = DESK_CAN_RAW_INVALID, humidity = DESK_CAN_RAW_INVALID;
    bool valid = status->reading_valid &&
                 temperature_raw(status->temperature_mc, &temperature) &&
                 humidity_raw(status->humidity_mpermil, &humidity);
    if (!valid) {
        temperature = DESK_CAN_RAW_INVALID;
        humidity = DESK_CAN_RAW_INVALID;
    }
    memset(out, 0, 8);
    out[0] = (uint8_t)(temperature & 0xFFu);  /* little-endian, as in the DBC (@1+) */
    out[1] = (uint8_t)(temperature >> 8);
    out[2] = (uint8_t)(humidity & 0xFFu);
    out[3] = (uint8_t)(humidity >> 8);
    out[4] = status->heartbeat;
    out[5] = (uint8_t)((valid ? 0u : 1u) | (status->queue_loss ? 2u : 0u));
    return valid;
}

#ifdef ESP_PLATFORM
esp_err_t desk_can_start(int tx_gpio, int rx_gpio) {
    twai_general_config_t general = TWAI_GENERAL_CONFIG_DEFAULT(
        (gpio_num_t)tx_gpio, (gpio_num_t)rx_gpio, TWAI_MODE_NORMAL);
    twai_timing_config_t timing = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t filter = TWAI_FILTER_CONFIG_ACCEPT_ALL();
    esp_err_t err = twai_driver_install(&general, &timing, &filter);
    if (err != ESP_OK) return err;
    return twai_start();
}

esp_err_t desk_can_stop(void) {
    esp_err_t stop = twai_stop();
    esp_err_t uninstall = twai_driver_uninstall();
    return stop != ESP_OK ? stop : uninstall;
}

esp_err_t desk_can_send(const desk_can_status_t *status) {
    twai_status_info_t info;
    esp_err_t err = twai_get_status_info(&info);
    if (err != ESP_OK) return err;
    if (info.state == TWAI_STATE_BUSOFF) {
        /* Recovery completes in the background; the next cycle restarts the driver. */
        ESP_LOGW(TAG, "bus-off; starting recovery");
        twai_initiate_recovery();
        return ESP_ERR_INVALID_STATE;
    }
    if (info.state == TWAI_STATE_STOPPED) {
        err = twai_start();
        if (err != ESP_OK) return err;
    }
    twai_message_t message = {0};
    message.identifier = DESK_CAN_NODE_ID;
    message.data_length_code = 8;
    desk_can_encode(status, message.data);
    return twai_transmit(&message, pdMS_TO_TICKS(100));
}
#endif
