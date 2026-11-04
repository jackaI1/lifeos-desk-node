#ifndef DESK_CORE_H
#define DESK_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define DESK_RING_CAPACITY 64
#define DESK_FRAME_SIZE 1024
#define DESK_PAYLOAD_SIZE 12288

typedef struct {
    uint32_t sequence;
    int64_t timestamp; /* Unix seconds, 0 means unsynchronized. */
    int32_t temperature_mc;
    int32_t humidity_mpermil; /* 100000 = 100 percent RH. */
} desk_reading_t;
typedef struct {
    desk_reading_t readings[DESK_RING_CAPACITY];
    uint32_t head, count, dropped;
} desk_ring_t;
typedef struct { char title[96], when[32], kind[12]; } desk_event_t;
typedef struct { char *data; size_t capacity, length; bool overflow; } desk_body_t;
uint8_t desk_crc8(const uint8_t *data, size_t length);
bool desk_decode_sht31(const uint8_t raw[6], desk_reading_t *reading);
bool desk_ring_valid(const desk_ring_t *ring);
void desk_ring_push(desk_ring_t *ring, desk_reading_t reading);
const desk_reading_t *desk_ring_at(const desk_ring_t *ring, uint32_t offset);
bool desk_ring_pop(desk_ring_t *ring, uint32_t expected_sequence);
bool desk_parse_event(const char *json, desk_event_t *event);
void desk_body_init(desk_body_t *body, char *data, size_t capacity);
bool desk_body_append(desk_body_t *body, const char *data, size_t length);
bool desk_encode_readings(char *out, size_t capacity, const char *device,
                          const char *session, const desk_ring_t *ring);
bool desk_ack_matches(const char *json, uint32_t count, uint32_t last_sequence);
void desk_render(uint8_t frame[DESK_FRAME_SIZE], const desk_event_t *event,
                 const desk_reading_t *reading, bool online, uint32_t dropped);
#endif
