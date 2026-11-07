#include "switch.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    switch_t s;switch_init(&s);
    assert(!switch_connect(&s,0,1,0));assert(!switch_connect(&s,1,17,0));assert(!switch_connect(&s,1,1,0));
    assert(switch_connect(&s,1,16,0));assert(!switch_connect(&s,1,2,0));assert(switch_ack(&s,1));
    assert(!switch_tick(&s,199));assert(switch_tick(&s,200));assert(s.fault[15]);assert(!s.fault[0]);
    assert(!switch_ack(&s,16));assert(switch_disconnect(&s,16));assert(!s.peer[0]);
    char small[2];assert(!switch_command(&s,"STATUS 1",small,sizeof small,0));
    puts("PASS: port bounds, conflicts, hardware ACK, watchdog, disconnect and output bounds");return 0;
}
