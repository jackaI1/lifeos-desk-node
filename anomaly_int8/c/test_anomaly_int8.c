/* Checks the C routine against the Python integer reference on every test vector. */
#include <stdio.h>

#include "anomaly_int8.h"
#include "test_vectors.h"

static int failures = 0;

#define CHECK(condition, index)                                                      \
    do {                                                                             \
        if (!(condition)) {                                                          \
            fprintf(stderr, "vector %d failed: %s\n", (index), #condition);          \
            ++failures;                                                              \
        }                                                                            \
    } while (0)

int main(void) {
    for (int32_t v = 0; v < ANOMALY_VECTOR_COUNT; ++v) {
        const int32_t *raw = &anomaly_vec_raw[v * ANOMALY_INPUTS];
        const int8_t *expected_in = &anomaly_vec_input[v * ANOMALY_INPUTS];
        const int8_t *expected_out = &anomaly_vec_output[v * ANOMALY_INPUTS];
        int8_t input[ANOMALY_INPUTS];
        int8_t output[ANOMALY_INPUTS];

        anomaly_quantise(raw, raw + 4, input);
        for (int32_t i = 0; i < ANOMALY_INPUTS; ++i) {
            CHECK(input[i] == expected_in[i], v);
        }
        anomaly_reconstruct(expected_in, output);
        for (int32_t i = 0; i < ANOMALY_INPUTS; ++i) {
            CHECK(output[i] == expected_out[i], v);
        }
        CHECK(anomaly_score(expected_in) == anomaly_vec_score[v], v);
        CHECK(anomaly_is_anomalous(expected_in) == anomaly_vec_flag[v], v);
    }
    if (failures != 0) {
        fprintf(stderr, "%d checks failed\n", failures);
        return 1;
    }
    printf("anomaly_int8: %d vectors match the Python integer reference\n", ANOMALY_VECTOR_COUNT);
    return 0;
}
