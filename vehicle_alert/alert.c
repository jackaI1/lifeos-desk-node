#include "alert.h"
/* State table: 255 means keep current state. Fault input dominates debounce. */
void alert_init(alert_t *fsm)
{
    fsm->state = ALERT_OFF;
    fsm->ignition = false;
    fsm->since = UINT32_C(0);
    fsm->clock = UINT32_C(0);
}
void alert_step(alert_t *fsm, uint8_t event, uint32_t now)
{
    static const uint8_t transitions[5][7] = {
        {ALERT_READY, ALERT_OFF, ALERT_OFF, ALERT_LATCHED, ALERT_OFF, ALERT_OFF, ALERT_OFF},
        {ALERT_READY, ALERT_OFF, ALERT_WARNING, ALERT_LATCHED, ALERT_READY, ALERT_READY, ALERT_WARNING},
        {ALERT_WARNING, ALERT_OFF, ALERT_WARNING, ALERT_LATCHED, ALERT_WARNING, ALERT_WARNING, ALERT_WARNING},
        {ALERT_LATCHED, ALERT_LATCHED, ALERT_LATCHED, ALERT_LATCHED, ALERT_CLEARING, ALERT_LATCHED, ALERT_LATCHED},
        {ALERT_LATCHED, ALERT_CLEARING, ALERT_CLEARING, ALERT_LATCHED, ALERT_CLEARING, ALERT_CLEARING, ALERT_CLEARING}
    };
    uint8_t next = ALERT_LATCHED;
    if ((fsm->state < UINT8_C(5)) && (event < UINT8_C(7)) && (now >= fsm->clock)) {
        fsm->clock = now;
        if (event == ALERT_ON) {
            fsm->ignition = true;
        } else if (event == ALERT_IGN_OFF) {
            fsm->ignition = false;
        } else {
            /* Other events do not change ignition. */
        }
        next = transitions[fsm->state][event];
        if ((next == ALERT_CLEARING) && (fsm->state != ALERT_CLEARING) && fsm->ignition) {
            next = ALERT_LATCHED;
        }
        if ((fsm->state == ALERT_CLEARING) && (event == ALERT_TICK) &&
            ((now - fsm->since) >= UINT32_C(500))) {
            next = ALERT_OFF;
        }
        if (next != fsm->state) {
            fsm->since = now;
        }
    }
    fsm->state = next;
}
bool alert_alarm(const alert_t *fsm)
{
    bool result = true;
    if ((fsm->state == ALERT_OFF) || (fsm->state == ALERT_READY)) {
        result = false;
    }
    return result;
}
