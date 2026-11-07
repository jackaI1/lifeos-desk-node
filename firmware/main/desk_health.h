#ifndef DESK_HEALTH_H
#define DESK_HEALTH_H
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#define DESK_HEALTH_STOP BIT2
#define DESK_HEALTH_DONE BIT3
void desk_health_task(void *argument);
#endif
