#include "alert.h"
/* State table: 255 means keep current state. Fault input dominates debounce. */
void alert_init(alert_t *fsm) {
    fsm->state = ALERT_OFF;
    fsm->ignition = false;
    fsm->since = ((uint32_t)0U);
    fsm->clock = ((uint32_t)0U);
}
void alert_step(alert_t *fsm, uint8_t event, uint32_t now) {
    static const uint8_t transitions[5][7] = {
        {ALERT_READY, ALERT_OFF, ALERT_OFF, ALERT_LATCHED, ALERT_OFF, ALERT_OFF, ALERT_OFF},
        {ALERT_READY, ALERT_OFF, ALERT_WARNING, ALERT_LATCHED, ALERT_READY, ALERT_READY,
         ALERT_WARNING},
        {ALERT_WARNING, ALERT_OFF, ALERT_WARNING, ALERT_LATCHED, ALERT_WARNING, ALERT_WARNING,
         ALERT_WARNING},
        {ALERT_LATCHED, ALERT_LATCHED, ALERT_LATCHED, ALERT_LATCHED, ALERT_CLEARING, ALERT_LATCHED,
         ALERT_LATCHED},
        {ALERT_LATCHED, ALERT_CLEARING, ALERT_CLEARING, ALERT_LATCHED, ALERT_CLEARING,
         ALERT_CLEARING, ALERT_CLEARING}};
    uint8_t next = ALERT_LATCHED;
    if ((fsm->state < ((uint8_t)5U)) && (event < ((uint8_t)7U)) && (now >= fsm->clock)) {
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
            ((now - fsm->since) >= ((uint32_t)500U))) {
            next = ALERT_OFF;
        }
        if ((fsm->state == ALERT_READY) && (event == ALERT_TICK) &&
            ((now - fsm->since) >= ((uint32_t)1000U))) {
            next = ALERT_WARNING;
        }
        if (next != fsm->state) {
            fsm->since = now;
        }
    }
    fsm->state = next;
}
bool alert_alarm(const alert_t *fsm) {
    bool result = true;
    if ((fsm->state == ALERT_OFF) || (fsm->state == ALERT_READY)) {
        result = false;
    }
    return result;
}
