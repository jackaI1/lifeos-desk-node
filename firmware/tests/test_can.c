/* Host test for the DeskNode payload encoder (can_monitor/desk_node.dbc).
   The same vectors are checked from Python in can_monitor/tests/test_desk_node_contract.py. */
#include "desk_can.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void expect_payload(const desk_can_status_t *status, const uint8_t want[8], bool valid) {
    uint8_t got[8];
    bool ok = desk_can_encode(status, got);
    assert(ok == valid);
    assert(memcmp(got, want, 8) == 0);
}

int main(void) {
    /* 21.5 C -> raw 6150 (0x1806); 45.0 %RH -> raw 4500 (0x1194); heartbeat 7. */
    desk_can_status_t normal = {.reading_valid = true, .temperature_mc = 21500,
                                .humidity_mpermil = 45000, .heartbeat = 7, .queue_loss = false};
    const uint8_t normal_bytes[8] = {0x06, 0x18, 0x94, 0x11, 0x07, 0x00, 0x00, 0x00};
    expect_payload(&normal, normal_bytes, true);

    /* Range ends are inclusive: -40 C = raw 0, 125 C = raw 16500 (0x4074), 100 %RH = 10000 (0x2710). */
    desk_can_status_t low = {.reading_valid = true, .temperature_mc = -40000,
                             .humidity_mpermil = 0, .heartbeat = 0, .queue_loss = false};
    const uint8_t low_bytes[8] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
    expect_payload(&low, low_bytes, true);
    desk_can_status_t high = {.reading_valid = true, .temperature_mc = 125000,
                              .humidity_mpermil = 100000, .heartbeat = 255, .queue_loss = true};
    const uint8_t high_bytes[8] = {0x74, 0x40, 0x10, 0x27, 0xFF, 0x02, 0x00, 0x00};
    expect_payload(&high, high_bytes, true);

    /* Rounding: 21.005 C is 21005 mc -> raw 6100.5, rounded half up to 6101 (0x17D5). */
    desk_can_status_t rounded = {.reading_valid = true, .temperature_mc = 21005,
                                 .humidity_mpermil = 4, .heartbeat = 1, .queue_loss = false};
    const uint8_t rounded_bytes[8] = {0xD5, 0x17, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00};
    expect_payload(&rounded, rounded_bytes, true);

    /* 125.01 C is outside the DBC range: both fields become markers, SensorFault=1. */
    desk_can_status_t hot = {.reading_valid = true, .temperature_mc = 125010,
                             .humidity_mpermil = 45000, .heartbeat = 9, .queue_loss = false};
    const uint8_t hot_bytes[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0x09, 0x01, 0x00, 0x00};
    expect_payload(&hot, hot_bytes, false);

    /* No reading at all: both markers, SensorFault and QueueLoss both set. */
    desk_can_status_t none = {.reading_valid = false, .temperature_mc = 21500,
                              .humidity_mpermil = 45000, .heartbeat = 10, .queue_loss = true};
    const uint8_t none_bytes[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0x0A, 0x03, 0x00, 0x00};
    expect_payload(&none, none_bytes, false);

    /* Negative humidity is invalid too. */
    desk_can_status_t wet = {.reading_valid = true, .temperature_mc = 20000,
                             .humidity_mpermil = -1, .heartbeat = 11, .queue_loss = false};
    uint8_t wet_out[8];
    assert(!desk_can_encode(&wet, wet_out));
    assert(wet_out[2] == 0xFF && wet_out[3] == 0xFF && wet_out[5] == 0x01);

    printf("test_can: 7 encoder vectors passed\n");
    return 0;
}
