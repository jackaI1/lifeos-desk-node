#ifndef DESK_ALERT_H
#define DESK_ALERT_H
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define ALERT_OFF UINT8_C(0)
#define ALERT_READY UINT8_C(1)
#define ALERT_WARNING UINT8_C(2)
#define ALERT_LATCHED UINT8_C(3)
#define ALERT_CLEARING UINT8_C(4)
#define ALERT_ON UINT8_C(0)
#define ALERT_IGN_OFF UINT8_C(1)
#define ALERT_WARN UINT8_C(2)
#define ALERT_FAULT UINT8_C(3)
#define ALERT_CLEAR UINT8_C(4)
#define ALERT_TICK UINT8_C(5)
#define ALERT_TIMEOUT UINT8_C(6)
typedef struct { uint8_t state; bool ignition; uint32_t since; uint32_t clock; } alert_t;
void alert_init(alert_t *fsm);
void alert_step(alert_t *fsm, uint8_t event, uint32_t now);
bool alert_alarm(const alert_t *fsm);
#ifdef __cplusplus
}
#endif
#endif
