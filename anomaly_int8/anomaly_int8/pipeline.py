"""Train, quantize, export and compare the anomaly detector in one reproducible run."""
import json
from pathlib import Path

import numpy as np

from . import data, export, model, quant

THRESHOLD_QUANTILE = 0.995     # about 0.5 % of normal validation windows may be flagged
TEST_VECTOR_STRIDE = 7         # every seventh held-out window goes into the C test
EDGE_READINGS = [              # (four temperatures, four humidities) in milli-units
    ([22050, 21950, 22049, 21951], [45250, 44750, 45249, 44751]),   # half-step ties and just below
    ([22000, 22000, 22000, 22000], [45000, 45000, 45000, 45000]),   # exact centre
    ([-40000, -40000, -40000, -40000], [0, 0, 0, 0]),               # dropout: far below the room
    ([130000, 130000, 130000, 130000], [100000, 100000, 100000, 100000]),  # sensor limits
    ([21000, 22600, 23000, 22000], [46000, 44200, 45000, 40000]),
]


def _metrics(truth, flagged):
    truth = truth.astype(bool)
    tp = int(np.sum(flagged & truth))
    fp = int(np.sum(flagged & ~truth))
    fn = int(np.sum(~flagged & truth))
    tn = int(np.sum(~flagged & ~truth))
    total = tp + fp + fn + tn
    return {
        'accuracy': (tp + tn) / total,
        'precision': tp / (tp + fp) if tp + fp else 0.0,
        'recall': tp / (tp + fn) if tp + fn else 0.0,
        'false_alarm_rate': fp / (fp + tn) if fp + tn else 0.0,
        'confusion': {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn},
    }


def _recall(in_group, flagged):
    if not np.any(in_group):
        return None
    return float(np.mean(flagged[in_group]))


def build(log_path, out_dir, docs_dir, c_dir):
    """Run the whole pipeline. Returns the results dictionary and writes the files."""
    timestamps, temperature, humidity, anomaly = data.read_log(log_path)
    dev, kind, contaminated = data.windows(temperature, humidity, anomaly)
    train, validation, test = data.split_indices(len(kind))
    normal = ~contaminated

    # Training and threshold use normal windows only. The test split is never used for either.
    train_rows = np.flatnonzero(normal[train]) + train.start
    valid_rows = np.flatnonzero(normal[validation]) + validation.start
    train_units = data.unit_features(dev[train_rows])
    valid_units = data.unit_features(dev[valid_rows])

    torch_model = model.train(train_units)
    float_w = model.float_weights(torch_model)

    # The device sees integers, so calibration and the test both use quantized inputs.
    train_int = quant.quantise_readings(*_readings(temperature, humidity, train_rows))
    layers = quant.quantise(float_w, train_int.astype(np.float32))
    score_w = quant.SCORE_WEIGHTS

    valid_float = quant.float_unit_scores(float_w, valid_units)
    valid_int_inputs = quant.quantise_readings(*_readings(temperature, humidity, valid_rows))
    valid_int = quant.integer_scores(layers, valid_int_inputs, score_w)
    float_threshold = float(np.quantile(valid_float, THRESHOLD_QUANTILE))
    int_threshold = int(np.floor(np.quantile(valid_int, THRESHOLD_QUANTILE)))
    qmodel = quant.QuantModel(layers, score_w, int_threshold)

    test_rows = np.arange(test.start, test.stop)
    test_units = data.unit_features(dev[test_rows])
    test_int_inputs = quant.quantise_readings(*_readings(temperature, humidity, test_rows))
    test_float = quant.float_unit_scores(float_w, test_units)
    test_int = quant.integer_scores(layers, test_int_inputs, score_w)
    truth = contaminated[test_rows]
    float_flags = test_float > float_threshold
    int_flags = test_int > int_threshold
    float_metrics = _metrics(truth, float_flags)
    int_metrics = _metrics(truth, int_flags)
    test_kind = kind[test_rows]
    per_kind = {name: {'windows': int(np.sum(test_kind == code)),
                       'float_recall': _recall(test_kind == code, float_flags),
                       'int8_recall': _recall(test_kind == code, int_flags)}
                for code, name in data.ANOMALY_NAMES.items()}

    # Reconstruction error between the two models on the same quantized windows.
    float_outputs = _float_outputs(float_w, test_int_inputs)
    int_outputs = quant.run_layers(layers, test_int_inputs)
    output_gap = np.abs(float_outputs - int_outputs)

    results = {
        'log': {'readings': int(len(timestamps)), 'windows': int(len(kind)),
                'injected_anomaly_readings': int(np.count_nonzero(anomaly)),
                'train_windows': int(len(train_rows)), 'validation_windows': int(len(valid_rows)),
                'test_windows': int(len(test_rows)), 'test_anomaly_windows': int(truth.sum()),
                'source': Path(log_path).name, 'labelled_anomalies': bool(np.any(anomaly))},
        'float': {'threshold': float_threshold, **float_metrics,
                  'parameters': int(sum(w.size + b.size for w, b, _ in float_w)),
                  'bytes_float32': int(sum(4 * (w.size + b.size) for w, b, _ in float_w))},
        'int8': {'threshold': int_threshold, **int_metrics,
                 **quant.memory_report(layers)},
        'per_fault': per_kind,
        'comparison': {
            'accuracy_loss': float_metrics['accuracy'] - int_metrics['accuracy'],
            'decision_agreement': float(np.mean(float_flags == int_flags)),
            'output_max_abs_gap_units': float(output_gap.max()),
            'output_mean_abs_gap_units': float(output_gap.mean()),
        },
    }
    results['int8']['memory_ratio_vs_float32'] = (
        results['int8']['int8_bytes'] / results['float']['bytes_float32'])

    export.write_model_header(Path(c_dir) / 'model_params.h', qmodel)
    # The C test also checks hand-picked readings: rounding ties, the sensor limits and dropouts.
    vector_rows = test_rows[::TEST_VECTOR_STRIDE]
    vt, vh = _readings(temperature, humidity, vector_rows)
    vt = np.concatenate([vt, np.array([t for t, _ in EDGE_READINGS], dtype=np.int64)])
    vh = np.concatenate([vh, np.array([h for _, h in EDGE_READINGS], dtype=np.int64)])
    export.write_vectors_header(Path(c_dir) / 'test_vectors.h', qmodel, (vt, vh),
                                quant.quantise_readings(vt, vh))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    report = export.render_report(results, layers)
    (Path(docs_dir) / 'results.md').write_text(report)
    return results


def _readings(temperature, humidity, window_rows):
    """Raw integer readings, shape (N, 4) per channel, for the given window numbers."""
    index = np.asarray(window_rows)[:, None] + np.arange(data.WINDOW)[None, :]
    return temperature[index], humidity[index]


def _float_outputs(float_w, int_inputs):
    activation = int_inputs.astype(np.float32)   # device units, the same numbers the float model saw
    for weight, bias, relu in float_w:
        activation = model.affine(activation, weight, bias)
        if relu:
            activation = np.maximum(activation, 0)
    return activation
