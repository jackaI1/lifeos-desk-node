/* Host-only replay: exercise production desk_core without sensor or network I/O. */
#include "desk_core.h"
#include <stdio.h>
#include <string.h>

/* Exact lines, bounded storage, no hidden NUL suffix or silently ignored tail. */
static int read_line(char out[80]) {
    size_t n = 0;
    int ch;
    while ((ch = getchar()) != EOF && ch != '\n') {
        if (ch == 0 || n == 79) return -1;
        out[n++] = (char)ch;
    }
    out[n] = 0;
    if (ferror(stdin)) return -1;
    return ch == EOF && n == 0 ? 0 : 1;
}

static int hex_value(char ch) {
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
    return -1;
}

static bool sensor_bytes(const char *line, uint8_t raw[6]) {
    if (strlen(line) != 14 || line[0] != 'S' || line[1] != ' ') return false;
    for (size_t i = 0; i < 6; ++i) {
        int hi = hex_value(line[2 + i * 2]), lo = hex_value(line[3 + i * 2]);
        if (hi < 0 || lo < 0) return false;
        raw[i] = (uint8_t)(hi * 16 + lo);
    }
    return true;
}

static bool bitmap(const char *path, const uint8_t frame[DESK_FRAME_SIZE]) {
    FILE *out = fopen(path, "w");
    if (!out) return false;
    bool ok = fprintf(out, "P1\n128 64\n") > 0;
    for (unsigned y = 0; ok && y < 64; ++y) {
        for (unsigned x = 0; ok && x < 128; ++x) {
            unsigned pixel = (frame[(y / 8) * 128 + x] >> (y % 8)) & 1u;
            ok = fprintf(out, "%u%c", pixel, x == 127 ? '\n' : ' ') > 0;
        }
    }
    if (fclose(out) != 0) ok = false;
    return ok;
}

static int fail(const char *reason) {
    fprintf(stderr, "replay: %s\n", reason);
    return 1;
}

int main(int argc, char **argv) {
    const char *image = NULL;
    if (argc == 3 && strcmp(argv[1], "--pbm") == 0) image = argv[2];
    else if (argc != 1) return fail("usage: desk-replay [--pbm screen.pbm] < scenario.wire");

    char line[80];
    if (read_line(line) != 1 || strcmp(line, "DESK_REPLAY_V1") != 0)
        return fail("expected DESK_REPLAY_V1 header");
    desk_ring_t ring = {0};
    desk_reading_t latest = {0};
    bool valid = false, online = false;
    uint32_t samples = 0, faults = 0, uploaded = 0, commands = 0;
    int status;
    while ((status = read_line(line)) == 1) {
        if (++commands > 4096) return fail("more than 4096 commands");
        if (strcmp(line, "U") == 0) {
            /* Simulate successful acknowledgement of all currently queued readings. */
            while (ring.count) {
                uint32_t sequence = desk_ring_at(&ring, 0)->sequence;
                if (!desk_ring_pop(&ring, sequence)) return fail("queue invariant failed");
                ++uploaded;
            }
            online = true;
        } else {
            uint8_t raw[6];
            if (!sensor_bytes(line, raw)) return fail("expected S plus six hex bytes, or U");
            valid = desk_decode_sht31(raw, &latest);
            if (valid) {
                latest.sequence = ++samples;
                desk_ring_push(&ring, latest);
            } else ++faults;
            online = false; /* Samples accumulate offline until the next U. */
        }
    }
    if (status < 0 || commands == 0) return fail("invalid, overlong or empty command stream");

    desk_event_t event = {.title = "Sensor replay", .when = "Simulated", .kind = "class"};
    uint8_t frame[DESK_FRAME_SIZE];
    desk_render(frame, &event, valid ? &latest : NULL, online, ring.dropped);
    if (image && !bitmap(image, frame)) return fail("cannot write screen bitmap");
    const desk_reading_t *oldest = desk_ring_at(&ring, 0);
    const desk_reading_t *newest = ring.count ? desk_ring_at(&ring, ring.count - 1) : NULL;
    printf("{\"samples\":%u,\"faults\":%u,\"uploaded\":%u,\"queued\":%u,\"dropped\":%u,"
           "\"oldest\":%u,\"newest\":%u,\"temperature_mc\":",
           samples, faults, uploaded, ring.count, ring.dropped,
           oldest ? oldest->sequence : 0, newest ? newest->sequence : 0);
    if (valid) printf("%ld,\"humidity_mpermil\":%ld", (long)latest.temperature_mc, (long)latest.humidity_mpermil);
    else printf("null,\"humidity_mpermil\":null");
    puts("}");
    return fflush(stdout) == 0 ? 0 : fail("cannot write summary");
}
