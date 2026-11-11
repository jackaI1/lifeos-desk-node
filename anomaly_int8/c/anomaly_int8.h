/* Integer-only int8 anomaly detector for the desk node's temperature and humidity.
 *
 * The device turns four temperatures (milli-degrees C) and four humidities
 * (thousandths of %RH) into eight int8 units, runs three int8 layers, and
 * compares the reconstruction with the input. No floating point is used.
 * The model constants are in model_params.h, which `python -m anomaly_int8 run`
 * writes. The Python quantizer in anomaly_int8/quant.py has the same rules.
 */
#ifndef ANOMALY_INT8_H
#define ANOMALY_INT8_H

#include <stdint.h>

#define ANOMALY_INPUTS 8   /* four temperatures, then four humidities */
#define ANOMALY_LAYERS 3

typedef struct {
    int32_t in_dim;
    int32_t out_dim;
    int32_t in_zero_point;
    int32_t out_zero_point;
    uint32_t multiplier;   /* m0 in [2^30, 2^31) */
    int32_t shift;         /* r, so the requantization multiplier is about m0 / 2^r */
    int32_t relu;          /* 1: clamp at the output zero point */
    const int8_t *weight;  /* out_dim x in_dim, row-major, zero point 0 */
    const int32_t *bias;   /* out_dim, scale = input scale x weight scale */
} anomaly_layer_t;

/* Device units: temperature in 0.1 C steps from 22 C, humidity in 0.5 %RH steps from 45 %RH. */
void anomaly_quantise(const int32_t temperature_mc[4], const int32_t humidity_mpermil[4],
                      int8_t input[ANOMALY_INPUTS]);

/* Runs the three layers on int8 input and writes the int8 reconstruction. */
void anomaly_reconstruct(const int8_t input[ANOMALY_INPUTS], int8_t output[ANOMALY_INPUTS]);

/* Weighted sum of squared differences between input and reconstruction. */
int32_t anomaly_score(const int8_t input[ANOMALY_INPUTS]);

/* Returns 1 when the score is above the calibrated threshold. */
int anomaly_is_anomalous(const int8_t input[ANOMALY_INPUTS]);

#endif
