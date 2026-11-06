#ifndef THERMOSTAT_H
#define THERMOSTAT_H

#include <stdbool.h>
#include <stdint.h>

/* Caller owns this state. Call once per fixed sampling interval. */
typedef struct {
    int32_t low_milli_c, high_milli_c;
    uint32_t timeout, missed;
    bool heat, fault;
} Thermostat;

/* Returns false for invalid configuration. Initially heat and fault are off. */
bool thermostat_init(Thermostat *t, int32_t low, int32_t high, uint32_t timeout);
void thermostat_step(Thermostat *t, bool valid, int32_t milli_c);
#endif
