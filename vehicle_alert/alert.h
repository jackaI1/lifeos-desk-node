#ifndef DESK_ALERT_H
#define DESK_ALERT_H
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define ALERT_OFF ((uint8_t)0U)
#define ALERT_READY ((uint8_t)1U)
#define ALERT_WARNING ((uint8_t)2U)
#define ALERT_LATCHED ((uint8_t)3U)
#define ALERT_CLEARING ((uint8_t)4U)
#define ALERT_ON ((uint8_t)0U)
#define ALERT_IGN_OFF ((uint8_t)1U)
#define ALERT_WARN ((uint8_t)2U)
#define ALERT_FAULT ((uint8_t)3U)
#define ALERT_CLEAR ((uint8_t)4U)
#define ALERT_TICK ((uint8_t)5U)
#define ALERT_TIMEOUT ((uint8_t)6U)
typedef struct { uint8_t state; bool ignition; uint32_t since; uint32_t clock; } alert_t;
void alert_init(alert_t *fsm);
void alert_step(alert_t *fsm, uint8_t event, uint32_t now);
bool alert_alarm(const alert_t *fsm);
#ifdef __cplusplus
}
#endif
#endif
