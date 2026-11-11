#include "desk_ess.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;

#define CHECK(expr)                                                                              \
    do {                                                                                         \
        if (!(expr)) {                                                                           \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #expr);             \
            ++failures;                                                                          \
        }                                                                                        \
    } while (0)

/* Builds a valid SHT31 frame: two data bytes, CRC, two data bytes, CRC. */
static void sht31_frame(uint16_t temperature_raw, uint16_t humidity_raw, uint8_t raw[6]) {
    raw[0] = (uint8_t)(temperature_raw >> 8);
    raw[1] = (uint8_t)temperature_raw;
    raw[2] = desk_crc8(raw, 2);
    raw[3] = (uint8_t)(humidity_raw >> 8);
    raw[4] = (uint8_t)humidity_raw;
    raw[5] = desk_crc8(raw + 3, 2);
}

#define READING(t, h) (&(desk_reading_t){.temperature_mc = (t), .humidity_mpermil = (h)})

static void test_encoding_and_rounding(void) {
    desk_ess_value_t value;
    uint8_t t[2], h[2];

    /* 21.37 degC and 45.12 %RH are sent as 2137 and 4512, little-endian. */
    CHECK(desk_ess_from_reading(&(desk_reading_t){.temperature_mc = 21370, .humidity_mpermil = 45120}, &value));
    desk_ess_encode(&value, t, h);
    CHECK(value.temperature_c100 == 2137 && value.humidity_c100 == 4512);
    CHECK(t[0] == 0x59 && t[1] == 0x08);
    CHECK(h[0] == 0xa0 && h[1] == 0x11);

    /* Half a hundredth rounds away from zero, on both signs. */
    CHECK(desk_ess_from_reading(&(desk_reading_t){.temperature_mc = 21375, .humidity_mpermil = 45125}, &value));
    CHECK(value.temperature_c100 == 2138 && value.humidity_c100 == 4513);
    CHECK(desk_ess_from_reading(&(desk_reading_t){.temperature_mc = -21375, .humidity_mpermil = 0}, &value));
    CHECK(value.temperature_c100 == -2138);

    /* Negative temperatures are two's complement on the air: -1.00 degC is 0xff9c. */
    CHECK(desk_ess_from_reading(&(desk_reading_t){.temperature_mc = -1000, .humidity_mpermil = 0}, &value));
    desk_ess_encode(&value, t, h);
    CHECK(t[0] == 0x9c && t[1] == 0xff);
}

static void test_range_limits(void) {
    desk_ess_value_t value;
    /* Edges of the accepted range are sent, one step beyond is rejected. */
    CHECK(desk_ess_from_reading(READING(-45000, 0), &value));
    CHECK(value.temperature_c100 == -4500);
    CHECK(desk_ess_from_reading(READING(125000, 100000), &value));
    CHECK(value.temperature_c100 == 12500 && value.humidity_c100 == 10000);
    CHECK(!desk_ess_from_reading(READING(-45001, 50000), &value));
    CHECK(!desk_ess_from_reading(READING(125001, 50000), &value));
    CHECK(!desk_ess_from_reading(READING(25000, 100001), &value));
    CHECK(!desk_ess_from_reading(READING(25000, -1), &value));
    CHECK(!desk_ess_from_reading(NULL, &value));
    CHECK(!desk_ess_from_reading(READING(0, 0), NULL));
}

static void test_sht31_frames(void) {
    desk_ess_value_t value;
    uint8_t raw[6];

    /* Datasheet-style frame: 0x6666 is 25.00 degC and 0x8000 is 50.00 %RH. */
    sht31_frame(0x6666, 0x8000, raw);
    CHECK(desk_ess_from_sht31(raw, &value));
    CHECK(value.temperature_c100 == 2500 && value.humidity_c100 == 5000);

    /* A CRC failure on either pair is rejected, even when the data bytes look plausible. */
    uint8_t bad[6];
    for (size_t i = 0; i < 6; ++i) {
        memcpy(bad, raw, sizeof bad);
        bad[i] ^= 0x01U;
        CHECK(!desk_ess_from_sht31(bad, &value));
    }

    /* Full-scale temperature decodes to 130 degC, outside the sensor range used for the service. */
    sht31_frame(0xffff, 0x8000, raw);
    CHECK(!desk_ess_from_sht31(raw, &value));
    /* A non-zero humidity is allowed at full scale, so only temperature is rejected here. */
    sht31_frame(0x0000, 0xffff, raw);
    CHECK(desk_ess_from_sht31(raw, &value));
    CHECK(value.temperature_c100 == -4500 && value.humidity_c100 == 10000);

    CHECK(!desk_ess_from_sht31(NULL, &value));
    CHECK(!desk_ess_from_sht31(raw, NULL));
}

static void test_notify_rule(void) {
    desk_ess_notify_t state;
    memset(&state, 0, sizeof state);
    desk_ess_value_t first = {.temperature_c100 = 2500, .humidity_c100 = 5000};
    desk_ess_value_t value;

    /* The first value always goes out. */
    CHECK(desk_ess_should_notify(&state, &first, 0, 10000));
    desk_ess_mark_notified(&state, &first, 0);

    /* Unchanged values never notify, however much time passes. */
    CHECK(!desk_ess_should_notify(&state, &first, 60000, 10000));

    /* A change below one step does not notify. */
    value = (desk_ess_value_t){.temperature_c100 = 2509, .humidity_c100 = 5049};
    CHECK(!desk_ess_should_notify(&state, &value, 60000, 10000));

    /* A temperature step notifies only once the minimum interval has passed. */
    value = (desk_ess_value_t){.temperature_c100 = 2510, .humidity_c100 = 5000};
    CHECK(!desk_ess_should_notify(&state, &value, 9999, 10000));
    CHECK(desk_ess_should_notify(&state, &value, 10000, 10000));

    /* A humidity step counts too. */
    desk_ess_mark_notified(&state, &value, 10000);
    value = (desk_ess_value_t){.temperature_c100 = 2510, .humidity_c100 = 5050};
    CHECK(desk_ess_should_notify(&state, &value, 20000, 10000));

    /* A clock that goes backwards never sends a burst. */
    CHECK(!desk_ess_should_notify(&state, &value, 5000, 10000));

    CHECK(!desk_ess_should_notify(NULL, &value, 20000, 10000));
    CHECK(!desk_ess_should_notify(&state, NULL, 20000, 10000));
}

int main(void) {
    test_encoding_and_rounding();
    test_range_limits();
    test_sht31_frames();
    test_notify_rule();
    if (failures) {
        fprintf(stderr, "%d ESS check(s) failed\n", failures);
        return EXIT_FAILURE;
    }
    puts("desk_ess tests passed");
    return EXIT_SUCCESS;
}
