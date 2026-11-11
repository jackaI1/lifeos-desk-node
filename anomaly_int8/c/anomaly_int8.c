/* Integer-only inference for the int8 anomaly detector. See anomaly_int8.h. */
#include "anomaly_int8.h"

#include "model_params.h"

#define TEMP_CENTRE_MC 22000
#define HUMIDITY_CENTRE_MPERMIL 45000
#define TEMP_STEP_MC 100
#define HUMIDITY_STEP_MPERMIL 500

/* Division that rounds toward negative infinity, for negative numerators too. */
static int32_t floor_div(int32_t numerator, int32_t denominator) {
    int32_t quotient = numerator / denominator;
    if ((numerator % denominator != 0) && ((numerator < 0) != (denominator < 0))) {
        --quotient;
    }
    return quotient;
}

static int32_t clamp_int8(int32_t value) {
    if (value < -128) return -128;
    if (value > 127) return 127;
    return value;
}

/* (value + 2^(r-1)) >> r: round half up. Right shift of a negative value is arithmetic. */
static int64_t rounding_shift(int64_t value, int32_t shift) {
    return (value + ((int64_t)1 << (shift - 1))) >> shift;
}

void anomaly_quantise(const int32_t temperature_mc[4], const int32_t humidity_mpermil[4],
                      int8_t input[ANOMALY_INPUTS]) {
    for (int32_t i = 0; i < 4; ++i) {
        int32_t t = floor_div(temperature_mc[i] - TEMP_CENTRE_MC + TEMP_STEP_MC / 2, TEMP_STEP_MC);
        int32_t h = floor_div(humidity_mpermil[i] - HUMIDITY_CENTRE_MPERMIL + HUMIDITY_STEP_MPERMIL / 2,
                              HUMIDITY_STEP_MPERMIL);
        input[i] = (int8_t)clamp_int8(t);
        input[4 + i] = (int8_t)clamp_int8(h);
    }
}

static void run_layer(const anomaly_layer_t *layer, const int8_t *in, int8_t *out) {
    for (int32_t o = 0; o < layer->out_dim; ++o) {
        int64_t acc = layer->bias[o];
        const int8_t *row = layer->weight + (int64_t)o * layer->in_dim;
        for (int32_t i = 0; i < layer->in_dim; ++i) {
            acc += (int64_t)(in[i] - layer->in_zero_point) * row[i];
        }
        int64_t y = rounding_shift(acc * (int64_t)layer->multiplier, layer->shift) + layer->out_zero_point;
        if (layer->relu && y < layer->out_zero_point) {
            y = layer->out_zero_point;
        }
        out[o] = (int8_t)clamp_int8((int32_t)y);
    }
}

void anomaly_reconstruct(const int8_t input[ANOMALY_INPUTS], int8_t output[ANOMALY_INPUTS]) {
    int8_t buffer_a[ANOMALY_INPUTS];
    int8_t buffer_b[ANOMALY_INPUTS];
    const int8_t *in = input;
    int8_t *out = buffer_a;
    for (int32_t n = 0; n < ANOMALY_LAYERS; ++n) {
        run_layer(&anomaly_layers[n], in, out);
        in = out;
        out = (out == buffer_a) ? buffer_b : buffer_a;
    }
    for (int32_t i = 0; i < ANOMALY_INPUTS; ++i) {
        output[i] = in[i];
    }
}

int32_t anomaly_score(const int8_t input[ANOMALY_INPUTS]) {
    int8_t reconstruction[ANOMALY_INPUTS];
    anomaly_reconstruct(input, reconstruction);
    int32_t score = 0;
    for (int32_t i = 0; i < ANOMALY_INPUTS; ++i) {
        int32_t diff = (int32_t)input[i] - (int32_t)reconstruction[i];
        score += anomaly_score_weights[i] * diff * diff;
    }
    return score;
}

int anomaly_is_anomalous(const int8_t input[ANOMALY_INPUTS]) {
    return anomaly_score(input) > ANOMALY_THRESHOLD;
}
