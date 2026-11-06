#include "thermostat.h"

bool thermostat_init(Thermostat *t, int32_t low, int32_t high, uint32_t timeout)
{
    if (!t || low >= high || timeout == 0) return false;
    *t = (Thermostat){.low_milli_c = low, .high_milli_c = high, .timeout = timeout};
    return true;
}

void thermostat_step(Thermostat *t, bool valid, int32_t milli_c)
{
    if (valid) {
        t->missed = 0;
        t->fault = false;
        if (milli_c <= t->low_milli_c) t->heat = true;
        else if (milli_c >= t->high_milli_c) t->heat = false;
    } else {
        if (t->missed < t->timeout) ++t->missed;
        if (t->missed == t->timeout) {
            t->fault = true;
            t->heat = false;
        }
    }
}
