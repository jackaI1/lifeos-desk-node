"""Post-training int8 quantization and the integer reference the C code must match.

Every layer uses the same arithmetic as the C routine in `c/anomaly_int8.c`:

* Input: the readings become integers in device units. Temperature is counted in
  0.1 C steps from 22 C, humidity in 0.5 %RH steps from 45 %RH, both rounded half
  up with integer division. The first layer's input scale is therefore exactly
  one unit and its zero point is 0.
* Weights: symmetric int8 per layer, scale = max|W| / 127, zero point 0.
* Activations: asymmetric int8 per layer, scale and zero point chosen from the
  calibration range (zero is always representable). Hidden layers are ReLU,
  which is a clamp at the zero point. The output layer uses the same unit and
  zero point as the input, so the reconstruction error is a plain integer sum.
* Bias: int32 with scale = input scale x weight scale.
* Requantization: the real multiplier M = s_in * s_w / s_out is stored as a
  31-bit integer m0 and a right shift r, so M is approximately m0 / 2^r. The
  output is (acc * m0 + 2^(r-1)) >> r, which is round-half-up for every case.
"""
from dataclasses import dataclass

import numpy as np

from .data import STEPS
from .model import affine

INT8_MIN, INT8_MAX = -128, 127
# The anomaly score weights each reading by its size in real units: one temperature
# step is 0.1 C and one humidity step is 0.5 %RH, so the humidity error counts 25 times.
SCORE_WEIGHTS = np.array([1] * 4 + [25] * 4, dtype=np.int64)


@dataclass(frozen=True)
class QuantLayer:
    index: int
    in_scale: float          # real value per integer step of the input
    in_zero_point: int
    weight_scale: float      # symmetric, zero point 0
    out_scale: float
    out_zero_point: int
    weight: np.ndarray       # int8, shape (out, in)
    bias: np.ndarray         # int32, shape (out,)
    multiplier: int          # m0, in [2^30, 2^31)
    shift: int               # r, so M ~= multiplier / 2^shift
    relu: bool

    def memory_bytes(self):
        return self.weight.size + 4 * self.bias.size + 4 + 1  # weights, biases, m0, r


@dataclass(frozen=True)
class QuantModel:
    layers: tuple
    score_weights: np.ndarray
    threshold: int           # anomaly when the integer score is above this value


def quantise_readings(temperature_mc, humidity_mpermil):
    """Integer input units for each window, using the device's rounding rule.

    Both arguments are integer arrays of shape (N, 4). The rounding is
    floor((x + step/2) / step), which is round-half-up for negative numbers too.
    """
    from .data import CENTRE_MC, CENTRE_MPERMIL, HUMIDITY_STEP_MPERMIL, TEMP_STEP_MC, WINDOW
    t = temperature_mc - CENTRE_MC
    h = humidity_mpermil - CENTRE_MPERMIL
    qt = (t + TEMP_STEP_MC // 2) // TEMP_STEP_MC
    qh = (h + HUMIDITY_STEP_MPERMIL // 2) // HUMIDITY_STEP_MPERMIL
    out = np.concatenate([qt, qh], axis=1)
    assert out.shape[1] == 2 * WINDOW
    return np.clip(out, INT8_MIN, INT8_MAX).astype(np.int64)


def _asymmetric(low, high):
    """Scale and zero point that represent [low, high] (containing zero) in int8."""
    low = min(low, 0.0)
    high = max(high, 0.0)
    if high - low < 1e-9:
        high = low + 1e-9
    scale = (high - low) / 255.0
    zero_point = int(np.clip(np.round(INT8_MIN - low / scale), INT8_MIN, INT8_MAX))
    return float(scale), zero_point


def _multiplier(real):
    """Return (m0, r) with real ~= m0 / 2^r and m0 in [2^30, 2^31)."""
    fraction, exponent = np.frexp(real)
    multiplier = int(np.round(fraction * 2**31))
    shift = 31 - int(exponent)
    if multiplier == 2**31:          # rounding carried into a 32nd bit
        multiplier //= 2
        shift -= 1
    if not (2**30 <= multiplier < 2**31 and 1 <= shift <= 62):
        raise ValueError('requantization multiplier out of range')
    return multiplier, shift


def quantise(weights, calibration_units):
    """Turn float layers into a QuantModel.

    `weights` is [(weight, bias, relu)] in the float model's own units.
    `calibration_units` is a float array of windows in device units; the hidden
    activations are recorded on it to choose their scales.
    """
    # Record the float activations of every hidden layer to set its range.
    activation = calibration_units.astype(np.float32)
    hidden_activations = []
    for weight, bias, relu in weights[:-1]:
        activation = np.maximum(affine(activation, weight, bias), 0.0)
        hidden_activations.append((float(activation.min()), float(activation.max())))
    input_scale, input_zero = 1.0, 0            # one device unit per integer step
    layers = []
    in_scale, in_zero = input_scale, input_zero
    for index, (weight, bias, relu) in enumerate(weights):
        last = index == len(weights) - 1
        weight_scale = float(np.max(np.abs(weight)) / 127.0)
        q_weight = np.clip(np.round(weight / weight_scale), -127, 127).astype(np.int8)
        q_bias = np.round(bias / (in_scale * weight_scale)).astype(np.int32)
        if last:
            out_scale, out_zero = input_scale, input_zero   # reconstruct in the input's units
        else:
            low, high = hidden_activations[index]
            out_scale, out_zero = _asymmetric(low, high)
        multiplier, shift = _multiplier(in_scale * weight_scale / out_scale)
        layers.append(QuantLayer(index, in_scale, in_zero, weight_scale, out_scale, out_zero,
                                 q_weight, q_bias, multiplier, shift, relu))
        in_scale, in_zero = out_scale, out_zero
    return tuple(layers)


def _rounding_shift(value, shift):
    return (value + (np.int64(1) << (shift - 1))) >> shift


def run_layers(layers, x_int8):
    """Integer forward pass on int8 inputs, shape (N, 8). Returns int8 outputs (N, 8)."""
    a = np.asarray(x_int8, dtype=np.int64)
    for layer in layers:
        acc = (a - layer.in_zero_point) @ layer.weight.astype(np.int64).T + layer.bias.astype(np.int64)
        y = _rounding_shift(acc * layer.multiplier, layer.shift) + layer.out_zero_point
        if layer.relu:
            y = np.maximum(y, layer.out_zero_point)
        a = np.clip(y, INT8_MIN, INT8_MAX)
    return a


def integer_scores(layers, x_int8, score_weights=SCORE_WEIGHTS):
    """Weighted sum of squared differences between input and reconstruction."""
    x = np.asarray(x_int8, dtype=np.int64)
    y = run_layers(layers, x)
    diff = x - y
    return np.sum(score_weights * diff * diff, axis=1)


def float_unit_scores(weights, units, score_weights=SCORE_WEIGHTS):
    """The same score computed in float, for the float model."""
    x = units.astype(np.float64)
    activation = x.astype(np.float32)
    for weight, bias, relu in weights:
        activation = affine(activation, weight, bias)
        if relu:
            activation = np.maximum(activation, 0)
    diff = x - activation
    return np.sum(score_weights * diff * diff, axis=1)


def memory_report(layers):
    return {
        'layers': len(layers),
        'parameters': int(sum(layer.weight.size + layer.bias.size for layer in layers)),
        'int8_bytes': int(sum(layer.memory_bytes() for layer in layers)),
    }
