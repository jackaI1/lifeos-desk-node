#ifndef DESK_NETWORK_H
#define DESK_NETWORK_H
#include "desk_core.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
typedef struct {
    const desk_ring_t *ring; /* Immutable until result is received or deep sleep. */
    const char *device;
    const char *session;
    QueueHandle_t result_queue;
} desk_network_request_t;
typedef struct {
    bool event_valid, upload_acked;
    desk_event_t event;
} desk_network_result_t;
void desk_network_task(void *argument);
#endif
