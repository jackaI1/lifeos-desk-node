#ifndef DESK_CAN_H
#define DESK_CAN_H

#include <stdbool.h>
#include <stdint.h>

#ifdef ESP_PLATFORM
#include "esp_err.h"
#endif

/* Message layout matches can_monitor/desk_node.dbc (DeskNode, ID 0x120). */
#define DESK_CAN_NODE_ID 0x120u
#define DESK_CAN_BITRATE_HZ 500000u
#define DESK_CAN_RAW_INVALID 0xFFFFu

typedef struct {
    bool reading_valid;       /* false when the sensor gave no usable reading */
    int32_t temperature_mc;   /* millidegrees Celsius */
    int32_t humidity_mpermil; /* 100000 = 100 %RH */
    uint8_t heartbeat;        /* increases by one per frame, wraps at 255 */
    bool queue_loss;          /* readings were dropped since the last frame */
} desk_can_status_t;

/* Writes the 8-byte DeskNode payload. Returns false when the reading is
   missing or outside the DBC range; the payload then carries 0xFFFF markers
   and SensorFault=1, so the analyzer flags it. */
bool desk_can_encode(const desk_can_status_t *status, uint8_t out[8]);

#ifdef ESP_PLATFORM
/* Installs the TWAI driver at 500 kbit/s and starts it. */
esp_err_t desk_can_start(int tx_gpio, int rx_gpio);
/* Stops the driver and frees it. Call before deep sleep. */
esp_err_t desk_can_stop(void);
/* Sends one DeskNode frame, recovering from bus-off first if needed. */
esp_err_t desk_can_send(const desk_can_status_t *status);
#endif

#endif
