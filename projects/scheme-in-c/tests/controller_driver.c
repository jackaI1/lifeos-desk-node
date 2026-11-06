#include "thermostat.h"
#include <inttypes.h>
#include <stdio.h>

int main(void)
{
    Thermostat t;
    int valid;
    int32_t temperature;
    if (!thermostat_init(&t, 19000, 21000, 3)) return 1;
    while (scanf("%d %" SCNd32, &valid, &temperature) == 2) {
        if (valid != 0 && valid != 1) return 1;
        thermostat_step(&t, valid != 0, temperature);
        printf("%d %d\n", t.heat, t.fault);
    }
    return ferror(stdin) ? 1 : 0;
}
