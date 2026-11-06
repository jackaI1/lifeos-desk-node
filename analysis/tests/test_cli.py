import json
import subprocess
import sys

import pytest

from analysis.simulate import simulate, write_csv


def run(*args):
    return subprocess.run([sys.executable, '-m', *map(str, args)], text=True,
                          capture_output=True, timeout=30)


def test_demo_outputs_measured_report_and_truth(tmp_path):
    output = tmp_path / 'demo'
    result = run('analysis.demo', '--output', output)
    assert result.returncode == 0, result.stderr
    report = json.loads((output / 'report.json').read_text())
    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['synthetic'] is True
    assert report['truth']['filtered_rmse'] < .15
    assert report['sample_count'] == 2048
    text = (output / 'report.md').read_text()
    assert 'Synthetic' in text
    assert 'RMSE' in text
    assert 'proxy' in text
    assert len((output / 'samples.csv').read_text().splitlines()) == 2049
    assert len((output / 'spectrum.csv').read_text().splitlines()) == 1026
    assert 'frequency_hz' not in report['raw_spectrum']  # Arrays in CSV only.


def test_csv_without_truth_has_only_estimated_snr(tmp_path):
    data, _ = simulate()
    path = tmp_path / 'input.csv'
    write_csv(path, data)
    lines = path.read_text().splitlines()
    path.write_text('\n'.join(','.join(line.split(',')[:3]) for line in lines))
    output = tmp_path / 'analysis'
    result = run('analysis', '--csv', path, '--channel', 'humidity',
                 '--cutoff-hz', 1/3600, '--output', output)
    assert result.returncode == 0, result.stderr
    report = json.loads((output / 'report.json').read_text())
    assert report['truth'] is None
    assert report['unit'] == '%RH'
    assert 'Ground-truth comparison unavailable' in (output / 'report.md').read_text()


@pytest.mark.parametrize('extra', [[], ['--device', 'desk'], ['--cutoff-hz', '.1'],
                                     ['--median-window', '4'], ['--signal-max-hz', '1e-12']])
def test_cli_errors_do_not_create_outputs(tmp_path, extra):
    data, _ = simulate()
    path = tmp_path / 'input.csv'
    write_csv(path, data)
    output = tmp_path / 'output'
    args = ['analysis', '--output', output]
    if extra:
        args.extend(['--csv', path, '--cutoff-hz', 1/3600])
    result = run(*args, *extra)
    assert result.returncode == 2
    assert not output.exists()
    assert 'Traceback' not in result.stderr


def test_output_cannot_overwrite_existing_or_source_directory(tmp_path):
    data, _ = simulate()
    path = tmp_path / 'samples.csv'
    write_csv(path, data)
    before = path.read_bytes()
    result = run('analysis', '--csv', path, '--cutoff-hz', 1/3600, '--output', tmp_path)
    assert result.returncode == 2
    assert before == path.read_bytes()


def test_bad_csv_error_is_concise(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('timestamp,temperature_mc\n1,nope\n')
    result = run('analysis', '--csv', path, '--cutoff-hz', 1/3600,
                 '--output', tmp_path / 'out')
    assert result.returncode == 2
    assert 'Traceback' not in result.stderr


def test_oversized_csv_field_is_concise_input_error(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('timestamp,temperature_mc\n1,' + '9'*140000 + '\n')
    result = run('analysis', '--csv', path, '--cutoff-hz', 1/3600,
                 '--output', tmp_path / 'out')
    assert result.returncode == 2
    assert 'Traceback' not in result.stderr


def test_unresolvable_lowpass_cutoff_is_concise_input_error(tmp_path):
    data, _ = simulate()
    path = tmp_path / 'input.csv'
    write_csv(path, data)
    result = run('analysis', '--csv', path, '--cutoff-hz', '1e-12',
                 '--output', tmp_path / 'out')
    assert result.returncode == 2
    assert 'Traceback' not in result.stderr
