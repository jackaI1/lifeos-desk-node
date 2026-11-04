#include "desk_core.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int checks;
#define CHECK(x) do { assert(x); ++checks; } while (0)
int main(void) {
    const uint8_t vector[] = {0xbe, 0xef};
    CHECK(desk_crc8(vector, 2) == 0x92);
    uint8_t sample[] = {0x66,0x66,0x93,0x80,0x00,0xa2};
    desk_reading_t r = {0};
    CHECK(desk_decode_sht31(sample, &r));
    CHECK(r.temperature_mc == 25000 && r.humidity_mpermil == 50001);
    sample[5] ^= 1;
    CHECK(!desk_decode_sht31(sample, &r));
    sample[5] ^= 1; sample[2] ^= 1;
    CHECK(!desk_decode_sht31(sample, &r));

    desk_ring_t ring = {0};
    CHECK(desk_ring_valid(&ring));
    CHECK(!desk_ring_pop(&ring, 1));
    for (uint32_t i=1;i<=70;++i) {
        r.sequence=i; desk_ring_push(&ring, r);
    }
    CHECK(ring.count == 64 && ring.dropped == 6);
    CHECK(desk_ring_at(&ring, 0)->sequence == 7);
    CHECK(desk_ring_at(&ring, 63)->sequence == 70);
    CHECK(!desk_ring_at(&ring, 64));
    CHECK(!desk_ring_pop(&ring, 6));
    CHECK(desk_ring_pop(&ring, 7));
    CHECK(desk_ring_at(&ring, 0)->sequence == 8);
    ring.head=64; CHECK(!desk_ring_valid(&ring));

    desk_event_t event = {.title="cached"};
    CHECK(desk_parse_event("{\"next\":{\"kind\":\"class\",\"title\":\"Calculus\",\"when\":\"Mon 10:30\"}}", &event));
    CHECK(!strcmp(event.title,"Calculus") && !strcmp(event.when,"Mon 10:30"));
    CHECK(!desk_parse_event("{\"next\":42}",&event));
    CHECK(!strcmp(event.title,"Calculus"));
    CHECK(!desk_parse_event("{\"next\":{\"kind\":\"class\",\"title\":42,\"when\":\"x\"}}",&event));
    CHECK(!desk_parse_event("{\"next\":null}junk",&event));
    CHECK(desk_parse_event("{\"next\":null}",&event));
    CHECK(!strcmp(event.title,"No upcoming events"));
    CHECK(!desk_parse_event("{\"next\":{\"kind\":\"alien\",\"title\":\"x\",\"when\":\"x\"}}",&event));
    CHECK(!desk_parse_event("{\"next\":null,\"next\":null}",&event));
    CHECK(!desk_parse_event("{\"next\":{\"kind\":\"class\",\"title\":\"a\\u0000b\",\"when\":\"x\"}}",&event));

    uint8_t extreme[] = {0,0,0x81,0xff,0xff,0xac};
    CHECK(desk_decode_sht31(extreme,&r));
    CHECK(r.temperature_mc == -45000 && r.humidity_mpermil == 100000);
    CHECK(!desk_ack_matches("{\"accepted\":1,\"accepted\":1,\"last_sequence\":42}",1,42));
    CHECK(!desk_ack_matches("{\"accepted\":1,\"last_sequence\":-1}",1,42));
    char max_payload[DESK_PAYLOAD_SIZE];
    ring.head=0;
    CHECK(desk_encode_readings(max_payload,sizeof max_payload,"aabbccddeeff","0123456789abcdef",&ring));

    CHECK(!desk_parse_event("{\"next\":null,\"x\":[[[[[[[[[0]]]]]]]]]}",&event));
    CHECK(!desk_ack_matches("{\"accepted\":1,\"last_sequence\":42,\"x\":[[[[[[[[[0]]]]]]]]]}",1,42));
    CHECK(desk_parse_event("{\"next\":{\"kind\":\"class\",\"title\":\"Text [ ] { }\",\"when\":\"Wed 10:30\"}}",&event));

    char response[8]; desk_body_t body;
    desk_body_init(&body,response,sizeof response);
    CHECK(desk_body_append(&body,"1234",4));
    CHECK(desk_body_append(&body,"567",3));
    CHECK(!strcmp(response,"1234567"));
    CHECK(!desk_body_append(&body,"8",1));
    CHECK(body.overflow);
    CHECK(!desk_body_append(&body,"",0));
    desk_body_init(&body,response,sizeof response);
    CHECK(!desk_body_append(&body,"a\0b",3));

    desk_ring_t small = {0}; r=(desk_reading_t){.sequence=42,.timestamp=0,.temperature_mc=-500,.humidity_mpermil=50000};
    desk_ring_push(&small,r);
    char payload[1024];
    CHECK(desk_encode_readings(payload,sizeof payload,"aabbccddeeff","0123456789abcdef",&small));
    CHECK(strstr(payload,"\"temperature_mc\":-500") && strstr(payload,"\"timestamp\":0"));
    CHECK(!desk_encode_readings(payload,5,"aabbccddeeff","0123456789abcdef",&small));
    CHECK(desk_ack_matches("{\"accepted\":1,\"last_sequence\":42}",1,42));
    CHECK(!desk_ack_matches("{\"accepted\":0,\"last_sequence\":42}",1,42));
    CHECK(!desk_ack_matches("{\"accepted\":1,\"last_sequence\":43}",1,42));
    CHECK(!desk_ack_matches("{\"accepted\":1.5,\"last_sequence\":42}",1,42));
    CHECK(!desk_ack_matches("{\"accepted\":1,\"last_sequence\":42}x",1,42));

    uint8_t frame[1026]; memset(frame,0xa5,sizeof frame);
    desk_render(frame+1,&event,&r,true,6);
    CHECK(frame[0]==0xa5 && frame[1025]==0xa5);
    CHECK(memcmp(frame+1,frame+129,128)!=0);
    desk_event_t long_event; memset(&long_event,'X',sizeof long_event);
    long_event.title[sizeof long_event.title-1]=0; long_event.when[sizeof long_event.when-1]=0;
    desk_render(frame+1,&long_event,NULL,false,0);
    CHECK(frame[0]==0xa5 && frame[1025]==0xa5);
    printf("PASS: %d core checks (CRC, FIFO, JSON, bounds, rendering)\n",checks);
    return 0;
}
