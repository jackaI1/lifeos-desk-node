#include "desk_core.h"
#include "desk_ssd1306.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int checks;
#define CHECK(x) do { assert(x); ++checks; } while (0)
typedef struct { unsigned calls, fail_at; const uint8_t *frame; } capture_t;
static bool capture(void *context,bool data,const uint8_t *bytes,size_t length) {
    capture_t *c=context;
    ++c->calls;
    if (c->calls==1) {
        /* Controller commands contain no I2C transport control byte. */
        const uint8_t expected[]={0xae,0xd5,0x80,0xa8,0x3f,0xd3,0,0x40,0x8d,0x14,
            0x20,0,0xa1,0xc8,0xda,0x12,0x81,0x40,0xd9,0xf1,0xdb,0x40,0xa4,0xa6,0x2e,
            0x21,0,127,0x22,0,7};
        CHECK(!data && length==sizeof expected && !memcmp(bytes,expected,length));
    } else if (c->calls==2) {
        CHECK(data && length==1024 && !memcmp(bytes,c->frame,length));
    } else {
        CHECK(c->calls==3 && !data && length==1 && bytes[0]==0xaf);
    }
    return c->calls!=c->fail_at;
}
int main(void) {
    uint8_t frame[1024];
    for (size_t i=0;i<sizeof frame;++i) frame[i]=(uint8_t)i;
    capture_t c={.frame=frame};
    CHECK(desk_ssd1306_frame(frame,capture,&c));
    CHECK(c.calls==3);
    for (unsigned failure=1;failure<=3;++failure) {
        c=(capture_t){.frame=frame,.fail_at=failure};
        CHECK(!desk_ssd1306_frame(frame,capture,&c));
        CHECK(c.calls==failure);
    }
    desk_reading_t sample={.sequence=42,.timestamp=0,.temperature_mc=-500,.humidity_mpermil=50000};
    char line[200];
    CHECK(desk_format_cycle_log(line,sizeof line,&sample,64,6,false));
    CHECK(!strcmp(line,"desk sample=42 utc=0 temp_mc=-500 rh_mpermil=50000 queued=64 lost=6 upload=pending\r\n"));
    CHECK(desk_format_cycle_log(line,sizeof line,NULL,0,0,true));
    CHECK(!strcmp(line,"desk sample=unavailable queued=0 lost=0 upload=acked\r\n"));
    CHECK(!desk_format_cycle_log(line,10,&sample,64,6,false));
    printf("PASS: %d peripheral checks (SSD1306 transport, failure propagation, UART log bounds)\n",checks);
    return 0;
}
