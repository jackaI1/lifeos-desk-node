import numpy as np
import pytest

from anomaly_int8 import model, quant


def test_multiplier_reproduces_real_scale_to_part_per_million():
    for real in [1e-6, 0.00371, 0.2, 0.9999, 1.5, 3.25]:
        m0, r = quant._multiplier(real)
        assert 2**30 <= m0 < 2**31
        assert abs(m0 / 2**r - real) <= real * 1e-6


def test_rounding_shift_is_round_half_up_for_negative_values():
    values = np.array([5, 6, 7, -5, -6, -7], dtype=np.int64)
    got = quant._rounding_shift(values, 1)
    # 2.5 -> 3, 3 -> 3, 3.5 -> 4; -2.5 -> -2, -3 -> -3, -3.5 -> -3
    assert list(got) == [3, 3, 4, -2, -3, -3]


def test_asymmetric_range_always_represents_zero_exactly():
    scale, zero = quant._asymmetric(0.0, 3.0)
    assert zero == -128
    assert scale == pytest.approx(3.0 / 255)
    scale, zero = quant._asymmetric(-2.0, 1.0)
    assert quant.INT8_MIN <= zero <= quant.INT8_MAX
    assert scale * (zero - (-128)) == pytest.approx(0.0 - (-2.0), abs=scale)


def test_quantised_layers_track_float_outputs():
    rng = np.random.default_rng(0)
    weights = [
        (rng.normal(0, 0.5, (8, 8)).astype(np.float32), rng.normal(0, 0.1, 8).astype(np.float32), True),
        (rng.normal(0, 0.5, (4, 8)).astype(np.float32), rng.normal(0, 0.1, 4).astype(np.float32), True),
        (rng.normal(0, 0.5, (8, 4)).astype(np.float32), rng.normal(0, 0.1, 8).astype(np.float32), False),
    ]
    units = rng.integers(-20, 20, size=(400, 8)).astype(np.float32)
    layers = quant.quantise(weights, units)
    assert [layer.in_scale for layer in layers][0] == 1.0
    assert layers[0].in_zero_point == 0
    assert layers[-1].out_scale == 1.0 and layers[-1].out_zero_point == 0
    int_out = quant.run_layers(layers, np.round(units).astype(np.int64))
    activation = np.round(units)
    for weight, bias, relu in weights:
        activation = model.affine(activation, weight, bias)
        activation = np.maximum(activation, 0) if relu else activation
    error = np.abs(int_out - activation)
    assert error.mean() < 1.0      # one unit is one device step
    for layer in layers:
        assert layer.weight.dtype == np.int8 and layer.bias.dtype == np.int32
        assert np.abs(layer.weight).max() <= 127


def test_memory_report_counts_every_stored_byte():
    weights = [(np.ones((2, 8), np.float32), np.zeros(2, np.float32), False)]
    layers = quant.quantise(weights, np.zeros((4, 8), np.float32))
    assert quant.memory_report(layers)['int8_bytes'] == 16 + 4 * 2 + 4 + 1
