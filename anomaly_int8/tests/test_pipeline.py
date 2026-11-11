"""End to end: train, quantize, export headers, run the C test, and check the report."""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from anomaly_int8 import data, pipeline

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    work = tmp_path_factory.mktemp('anomaly')
    timestamps, temperature, humidity, anomaly = data.make_log(days=14, seed=5)
    log = work / 'log.csv'
    data.write_log(log, timestamps, temperature, humidity, anomaly)
    c_dir = work / 'c'
    shutil.copytree(ROOT / 'c', c_dir, ignore=shutil.ignore_patterns('build'))
    docs = work / 'docs'
    docs.mkdir()
    results = pipeline.build(log, work / 'build', docs, c_dir)
    return work, c_dir, results


def test_quantized_model_matches_float_on_held_out_faults(built):
    _, _, results = built
    assert results['float']['accuracy'] - results['int8']['accuracy'] <= 0.02
    assert results['comparison']['decision_agreement'] >= 0.98
    assert results['comparison']['output_mean_abs_gap_units'] < 1.0
    assert results['per_fault']['spike']['int8_recall'] == 1.0


def test_detector_catches_large_faults_but_states_its_limit(built):
    _, _, results = built
    assert results['per_fault']['dropout']['int8_recall'] == 1.0
    assert results['per_fault']['humidity_jump']['int8_recall'] == 1.0
    assert results['per_fault']['stuck']['int8_recall'] < 1.0   # four identical readings look normal


def test_int8_model_is_smaller_than_float(built):
    _, _, results = built
    assert results['int8']['int8_bytes'] < results['float']['bytes_float32']
    assert results['int8']['memory_ratio_vs_float32'] < 0.5


def test_no_test_window_is_used_for_training_or_threshold(built):
    _, _, results = built
    log = results['log']
    train, validation, test = data.split_indices(log['windows'])
    assert log['test_windows'] == test.stop - test.start
    assert log['train_windows'] <= train.stop and log['validation_windows'] <= validation.stop - validation.start


def test_report_and_json_are_written(built):
    work, _, _ = built
    payload = json.loads((work / 'build' / 'results.json').read_text())
    assert payload['int8']['layers'] == 3
    assert '| int8 (C integer routine)' in (work / 'docs' / 'results.md').read_text()


def test_c_routine_matches_python_reference(built):
    _, c_dir, _ = built
    if shutil.which('cc') is None:
        pytest.skip('no C compiler')
    build = c_dir / 'build'
    subprocess.run(['make', '-C', str(c_dir), f'BUILD={build}', 'test'], check=True,
                   capture_output=True, text=True)
    assert (build / 'test_anomaly_int8').exists()
