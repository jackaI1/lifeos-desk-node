/* Host-only replay: exercise production desk_core without sensor or network I/O. */
#define _POSIX_C_SOURCE 200809L
#include "desk_core.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "replay.h"
#ifdef DESK_REPLAY_DEBUG
/* Debug fixture only: production replay never aborts on a sensor error. */
static void checksum_fault(const uint8_t raw[6]) {
    fprintf(stderr,"injected checksum crash: expected=%02x received=%02x\n",desk_crc8(raw,2),raw[2]);
    abort();
}
#endif

/* Exact lines, bounded storage, no hidden NUL suffix or silently ignored tail. */
int desk_replay_read_line(FILE *input, char out[80]) {
    size_t n = 0;
    int ch;
    while ((ch = fgetc(input)) != EOF && ch != '\n') {
        if (ch == 0 || n == 79) return -1;
        out[n++] = (char)ch;
    }
    out[n] = 0;
    if (ferror(input)) return -1;
    return ch == EOF && n == 0 ? 0 : 1;
}

static int hex_value(char ch) {
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
    return -1;
}

bool desk_replay_sensor_bytes(const char *line, uint8_t raw[6]) {
    if (strlen(line) != 14 || line[0] != 'S' || line[1] != ' ') return false;
    for (size_t i = 0; i < 6; ++i) {
        int hi = hex_value(line[2 + i * 2]), lo = hex_value(line[3 + i * 2]);
        if (hi < 0 || lo < 0) return false;
        raw[i] = (uint8_t)(hi * 16 + lo);
    }
    return true;
}

#ifndef DESK_REPLAY_LIBRARY
/* One ring slot holds one whole scenario wire. 4096 commands take about 61 KiB. */
#define SLOT_BYTES (64u * 1024u)
#define RING_SLOTS 8u
#define MAX_THREADS 64u
#define MAX_SCENARIOS 10000u
#define SUMMARY_BYTES 320
#define USAGE "usage: desk-replay [--pbm screen.pbm] [--uart-log log.txt] < scenario.wire\n" \
              "       desk-replay [--jobs N] scenario.wire..."

/* Everything one scenario leaves behind. Each stream owns its own copy. */
typedef struct {
    desk_ring_t ring;
    desk_reading_t latest;
    bool valid, online;
    uint32_t samples, faults, uploaded, commands;
} replay_run_t;

/* Where a wire stream comes from: stdin, or bytes already in memory. Workers use memory,
 * because stdio locks and flushes shared state on every read and would serialise them. */
typedef struct {
    FILE *file;          /* Used when non-NULL. */
    const char *cursor;  /* Otherwise: next unread byte, up to end. */
    const char *end;
} replay_input_t;

/* Same rules as desk_replay_read_line: exact lines, at most 79 bytes, no NUL bytes. */
static int next_line(replay_input_t *input, char out[80]) {
    if (input->file) return desk_replay_read_line(input->file, out);
    size_t n = 0;
    const char *p = input->cursor;
    while (p < input->end && *p != '\n') {
        if (*p == 0 || n == 79) return -1;
        out[n++] = *p++;
    }
    out[n] = 0;
    if (p < input->end) {
        input->cursor = p + 1;
        return 1;
    }
    input->cursor = p;
    return n == 0 ? 0 : 1;
}

/* Runs one wire stream. Returns NULL on success or a fixed reason string. */
static const char *replay_stream(replay_input_t *input, replay_run_t *run, char (*logs)[200]) {
    char line[80];
    memset(run, 0, sizeof *run);
    if (next_line(input, line) != 1 || strcmp(line, "DESK_REPLAY_V1") != 0)
        return "expected DESK_REPLAY_V1 header";
    /* Buffer until the complete stream is valid; no partial log on bad input. */
    int status;
    while ((status = next_line(input, line)) == 1) {
        if (++run->commands > 4096) return "more than 4096 commands";
        if (strcmp(line, "U") == 0) {
            /* Simulate successful acknowledgement of all currently queued readings. */
            while (run->ring.count) {
                uint32_t sequence = desk_ring_at(&run->ring, 0)->sequence;
                if (!desk_ring_pop(&run->ring, sequence)) return "queue invariant failed";
                ++run->uploaded;
            }
            run->online = true;
        } else {
            uint8_t raw[6];
            if (!desk_replay_sensor_bytes(line, raw)) return "expected S plus six hex bytes, or U";
            run->valid = desk_decode_sht31(raw, &run->latest);
            if (run->valid) {
                run->latest.sequence = ++run->samples;
                desk_ring_push(&run->ring, run->latest);
            } else {
                ++run->faults;
#ifdef DESK_REPLAY_DEBUG
                checksum_fault(raw);
#endif
            }
            run->online = false; /* Samples accumulate offline until the next U. */
        }
        if (logs && !desk_format_cycle_log(logs[run->commands - 1], sizeof logs[0],
                run->valid ? &run->latest : NULL, run->ring.count, run->ring.dropped, run->online))
            return "cannot format UART log";
    }
    if (status < 0 || run->commands == 0) return "invalid, overlong or empty command stream";
    return NULL;
}

/* The one-line JSON summary, without the trailing newline. */
static void format_summary(char out[SUMMARY_BYTES], const replay_run_t *run) {
    const desk_reading_t *oldest = desk_ring_at(&run->ring, 0);
    const desk_reading_t *newest = run->ring.count ? desk_ring_at(&run->ring, run->ring.count - 1) : NULL;
    int used = snprintf(out, SUMMARY_BYTES,
           "{\"samples\":%u,\"faults\":%u,\"uploaded\":%u,\"queued\":%u,\"dropped\":%u,"
           "\"oldest\":%u,\"newest\":%u,\"temperature_mc\":",
           run->samples, run->faults, run->uploaded, run->ring.count, run->ring.dropped,
           oldest ? oldest->sequence : 0, newest ? newest->sequence : 0);
    if (run->valid)
        snprintf(out + used, SUMMARY_BYTES - used, "%ld,\"humidity_mpermil\":%ld}",
                 (long)run->latest.temperature_mc, (long)run->latest.humidity_mpermil);
    else
        snprintf(out + used, SUMMARY_BYTES - used, "null,\"humidity_mpermil\":null}");
}

/* The result of one scenario. Only the owning thread writes it, then the merge reads it. */
typedef struct {
    uint32_t job;          /* Position of the scenario on the command line. */
    bool filled;
    const char *error;     /* NULL on success, otherwise a fixed reason. */
    char summary[SUMMARY_BYTES];
} job_result_t;

/* Pure work for one scenario. Reads only its own copy of the wire bytes. */
static void process_job(const char *wire, uint32_t length, const char *load_error, job_result_t *result) {
    result->error = load_error;
    if (load_error) return;
    replay_input_t input = {.file = NULL, .cursor = wire, .end = wire + length};
    replay_run_t run;
    result->error = replay_stream(&input, &run, NULL);
    if (!result->error) format_summary(result->summary, &run);
}

/* Reads one scenario file into data. Returns NULL on success or a fixed reason. */
static const char *load_scenario(const char *path, char *data, uint32_t *length) {
    FILE *in = fopen(path, "rb");
    if (!in) return "cannot open scenario";
    size_t n = fread(data, 1, SLOT_BYTES, in);
    bool more = fgetc(in) != EOF;
    bool bad = ferror(in) != 0;
    if (fclose(in) != 0) bad = true;
    if (bad) return "cannot read scenario";
    if (more) return "scenario is larger than 64 KiB";
    *length = (uint32_t)n;
    return NULL;
}

/* Bounded ring of scenario wires in a shared file mapping. The mutex and condition
 * variables live in the same mapping. A slot is FREE, then FILLED by the producer,
 * then TAKEN by one worker, then FREE again. Lock order: only ring->lock is used. */
typedef struct {
    uint32_t job;
    uint32_t length;
    const char *error;
    unsigned char state;
    char data[SLOT_BYTES];
} ring_slot_t;

enum { SLOT_FREE, SLOT_FILLED, SLOT_TAKEN };

typedef struct {
    pthread_mutex_t lock;
    pthread_cond_t slot_filled;  /* Producer published a slot, or finished: wakes workers. */
    pthread_cond_t slot_freed;   /* Worker released a slot: wakes the producer. */
    uint32_t total;              /* Number of scenarios to run. */
    uint32_t published;          /* Scenarios the producer has filled so far. */
    uint32_t next_take;          /* Next scenario a worker may take, in order. */
    ring_slot_t slots[RING_SLOTS];
} wire_ring_t;

static wire_ring_t *ring_create(uint32_t total) {
    const char *dir = getenv("TMPDIR");
    if (!dir || !*dir) dir = "/tmp";
    char path[1024];
    if (snprintf(path, sizeof path, "%s/desk-replay-ring.XXXXXX", dir) >= (int)sizeof path) return NULL;
    int fd = mkstemp(path);
    if (fd < 0) return NULL;
    /* The mapping keeps the storage alive; the name is removed at once. */
    unlink(path);
    wire_ring_t *ring = NULL;
    if (ftruncate(fd, (off_t)sizeof *ring) == 0) {
        void *mapped = mmap(NULL, sizeof *ring, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        if (mapped != MAP_FAILED) ring = mapped;
    }
    close(fd);
    if (!ring) return NULL;
    /* Zeroed mapping: every slot starts FREE. */
    if (pthread_mutex_init(&ring->lock, NULL) != 0) goto fail_map;
    if (pthread_cond_init(&ring->slot_filled, NULL) != 0) goto fail_mutex;
    if (pthread_cond_init(&ring->slot_freed, NULL) != 0) goto fail_filled;
    ring->total = total;
    return ring;
fail_filled:
    pthread_cond_destroy(&ring->slot_filled);
fail_mutex:
    pthread_mutex_destroy(&ring->lock);
fail_map:
    munmap(ring, sizeof *ring);
    return NULL;
}

static void ring_destroy(wire_ring_t *ring) {
    pthread_cond_destroy(&ring->slot_freed);
    pthread_cond_destroy(&ring->slot_filled);
    pthread_mutex_destroy(&ring->lock);
    munmap(ring, sizeof *ring);
}

/* Per-thread result buffer. Each worker appends only to its own buffer. */
typedef struct {
    wire_ring_t *ring;
    job_result_t *results;
    uint32_t count, capacity;
    bool out_of_memory;
} worker_t;

static void worker_store(worker_t *worker, const job_result_t *result) {
    if (worker->count == worker->capacity) {
        uint32_t next = worker->capacity ? worker->capacity * 2 : 16;
        job_result_t *grown = realloc(worker->results, next * sizeof *grown);
        if (!grown) {
            worker->out_of_memory = true;
            return;
        }
        worker->results = grown;
        worker->capacity = next;
    }
    worker->results[worker->count++] = *result;
}

static void *worker_main(void *argument) {
    worker_t *worker = argument;
    wire_ring_t *ring = worker->ring;
    for (;;) {
        pthread_mutex_lock(&ring->lock);
        while (ring->next_take == ring->published && ring->published < ring->total)
            pthread_cond_wait(&ring->slot_filled, &ring->lock);
        if (ring->next_take == ring->total) {
            pthread_mutex_unlock(&ring->lock);
            break;
        }
        ring_slot_t *slot = &ring->slots[ring->next_take % RING_SLOTS];
        slot->state = SLOT_TAKEN;
        uint32_t job = slot->job, length = slot->length;
        const char *load_error = slot->error;
        ring->next_take++;
        pthread_mutex_unlock(&ring->lock);

        /* The slot is TAKEN, so only this thread touches its bytes until it is freed. */
        job_result_t result = {.job = job, .filled = true};
        process_job(slot->data, length, load_error, &result);
        worker_store(worker, &result);

        pthread_mutex_lock(&ring->lock);
        slot->state = SLOT_FREE;
        pthread_cond_broadcast(&ring->slot_freed);
        pthread_mutex_unlock(&ring->lock);
    }
    return NULL;
}

/* Main thread: loads each file into the next slot, waiting while that slot is busy. */
static void produce(wire_ring_t *ring, char *const *paths) {
    for (uint32_t job = 0; job < ring->total; ++job) {
        ring_slot_t *slot = &ring->slots[job % RING_SLOTS];
        pthread_mutex_lock(&ring->lock);
        while (slot->state != SLOT_FREE) pthread_cond_wait(&ring->slot_freed, &ring->lock);
        pthread_mutex_unlock(&ring->lock);
        /* FREE means no worker touches this slot, so the producer may write it unlocked. */
        uint32_t length = 0;
        const char *load_error = load_scenario(paths[job], slot->data, &length);
        pthread_mutex_lock(&ring->lock);
        slot->job = job;
        slot->length = length;
        slot->error = load_error;
        slot->state = SLOT_FILLED;
        ring->published = job + 1;
        pthread_cond_broadcast(&ring->slot_filled);
        pthread_mutex_unlock(&ring->lock);
    }
}

/* Serial reference: the same loader and job code, on the calling thread only. */
static void run_serial(char *const *paths, uint32_t count, job_result_t *results) {
    char *buffer = malloc(SLOT_BYTES);
    for (uint32_t job = 0; job < count; ++job) {
        uint32_t length = 0;
        const char *load_error = buffer ? load_scenario(paths[job], buffer, &length) : "out of memory";
        results[job].job = job;
        results[job].filled = true;
        process_job(buffer, length, load_error, &results[job]);
    }
    free(buffer);
}

/* Runs scenarios on worker threads. Results are merged by job number, not finish order. */
static const char *run_pool(char *const *paths, uint32_t count, unsigned requested, job_result_t *results) {
    unsigned threads = requested < count ? requested : (unsigned)count;
    wire_ring_t *ring = ring_create(count);
    if (!ring) return "cannot map ring buffer";
    worker_t *workers = calloc(threads, sizeof *workers);
    pthread_t *ids = calloc(threads, sizeof *ids);
    if (!workers || !ids) {
        free(workers);
        free(ids);
        ring_destroy(ring);
        return "out of memory";
    }
    unsigned started = 0;
    for (unsigned i = 0; i < threads; ++i) {
        workers[started].ring = ring;
        if (pthread_create(&ids[started], NULL, worker_main, &workers[started]) == 0) ++started;
    }
    if (started == 0) {
        free(workers);
        free(ids);
        ring_destroy(ring);
        return "cannot start worker threads";
    }
    produce(ring, paths);
    for (unsigned i = 0; i < started; ++i) pthread_join(ids[i], NULL);

    const char *error = NULL;
    for (unsigned i = 0; i < started; ++i) {
        if (workers[i].out_of_memory) error = "out of memory";
        for (uint32_t k = 0; k < workers[i].count; ++k) {
            job_result_t *item = &workers[i].results[k];
            if (item->job >= count || results[item->job].filled) error = "internal result merge failed";
            else results[item->job] = *item;
        }
        free(workers[i].results);
    }
    free(workers);
    free(ids);
    ring_destroy(ring);
    for (uint32_t job = 0; job < count && !error; ++job)
        if (!results[job].filled) error = "missing scenario result";
    return error;
}

static int fail(const char *reason) {
    fprintf(stderr, "replay: %s\n", reason);
    return 1;
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

/* Original single-scenario mode: one wire on stdin, optional screen and UART logs. */
static int run_stdin(const char *image, const char *uart_path) {
    /* Buffer until the complete stream is valid; no partial log on bad input. */
    char logs[4096][200];
    replay_run_t run;
    replay_input_t input = {.file = stdin, .cursor = NULL, .end = NULL};
    const char *error = replay_stream(&input, &run, uart_path ? logs : NULL);
    if (error) return fail(error);

    desk_event_t event = {.title = "Sensor replay", .when = "Simulated", .kind = "class"};
    uint8_t frame[DESK_FRAME_SIZE];
    desk_render(frame, &event, run.valid ? &run.latest : NULL, run.online, run.ring.dropped);
    if (image && !bitmap(image, frame)) return fail("cannot write screen bitmap");
    if (uart_path) {
        FILE *uart = fopen(uart_path, "wb");
        if (!uart) return fail("cannot open UART log");
        bool ok = true;
        for (uint32_t i = 0; i < run.commands; ++i)
            if (fputs(logs[i], uart) == EOF) { ok = false; break; }
        if (fclose(uart) != 0) ok = false;
        if (!ok) return fail("cannot write UART log");
    }
    char summary[SUMMARY_BYTES];
    format_summary(summary, &run);
    puts(summary);
    return fflush(stdout) == 0 ? 0 : fail("cannot write summary");
}

/* Scenario files: one summary line per file, in argument order, or nothing on failure. */
static int run_files(char *const *paths, uint32_t count, unsigned jobs) {
    job_result_t *results = calloc(count, sizeof *results);
    if (!results) return fail("out of memory");
    const char *error = NULL;
    if (jobs == 1) run_serial(paths, count, results);
    else error = run_pool(paths, count, jobs, results);
    if (error) {
        free(results);
        return fail(error);
    }
    for (uint32_t job = 0; job < count; ++job) {
        if (results[job].error) {
            fprintf(stderr, "replay: %s: %s\n", paths[job], results[job].error);
            free(results);
            return 1;
        }
    }
    for (uint32_t job = 0; job < count; ++job) puts(results[job].summary);
    free(results);
    return fflush(stdout) == 0 ? 0 : fail("cannot write summary");
}

static bool parse_jobs(const char *text, unsigned *jobs) {
    unsigned value = 0;
    if (!*text) return false;
    for (const char *p = text; *p; ++p) {
        if (*p < '0' || *p > '9') return false;
        value = value * 10 + (unsigned)(*p - '0');
        if (value > MAX_THREADS) return false;
    }
    if (value == 0) return false;
    *jobs = value;
    return true;
}

int main(int argc, char **argv) {
    const char *image = NULL, *uart_path = NULL, *jobs_text = NULL;
    int first_file = argc;
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--pbm") == 0 && i + 1 < argc && !image) image = argv[++i];
        else if (strcmp(argv[i], "--uart-log") == 0 && i + 1 < argc && !uart_path) uart_path = argv[++i];
        else if (strcmp(argv[i], "--jobs") == 0 && i + 1 < argc && !jobs_text) jobs_text = argv[++i];
        else if (argv[i][0] != '-') { first_file = i; break; }
        else return fail(USAGE);
    }
    if (first_file == argc) {
        if (jobs_text) return fail("--jobs needs scenario files");
        return run_stdin(image, uart_path);
    }
    if (image || uart_path) return fail("--pbm and --uart-log work only with stdin");
    unsigned jobs = 1;
    if (jobs_text && !parse_jobs(jobs_text, &jobs)) return fail("--jobs needs a number from 1 to 64");
    uint32_t count = (uint32_t)(argc - first_file);
    if (count > MAX_SCENARIOS) return fail("more than 10000 scenario files");
    return run_files(argv + first_file, count, jobs);
}

#endif
