#include "alert.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    const uint8_t table[5][7]={{1,0,0,3,0,0,0},{1,0,2,3,1,1,2},{2,0,2,3,2,2,2},{3,3,3,3,4,3,3},{3,4,4,3,4,4,4}};
    unsigned tests=0;
    for (uint8_t state=0;state<5;++state) for(uint8_t event=0;event<7;++event) {
        alert_t fsm; alert_init(&fsm); fsm.state=state;
        alert_step(&fsm,event,1); assert(fsm.state==table[state][event]); ++tests;
    }
    alert_t f; alert_init(&f); alert_step(&f,ALERT_FAULT,1); alert_step(&f,ALERT_CLEAR,2);
    alert_step(&f,ALERT_TICK,501); assert(f.state==ALERT_CLEARING);
    alert_step(&f,ALERT_TICK,502); assert(f.state==ALERT_OFF); ++tests;
    uint32_t seed=42;
    for(uint32_t i=503;i<10503;++i) { seed=seed*UINT32_C(1664525)+UINT32_C(1013904223); alert_step(&f,(uint8_t)(seed%7U),i); assert(f.state<5); }
    ++tests;
    printf("%u state/transition and seeded replay checks passed\n",tests);
    FILE *out=fopen("test-results.xml","w");
    if (!out) return 1;
    fprintf(out,"<testsuites><testsuite name=\"vehicle-alert\" tests=\"%u\" failures=\"0\"><testcase name=\"all-transitions-and-replay\"/></testsuite></testsuites>\n",tests);
    return fclose(out)!=0;
}
