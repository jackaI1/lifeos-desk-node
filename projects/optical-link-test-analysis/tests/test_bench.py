import csv
import gzip
import json
import subprocess
import sys

import numpy as np
import pytest

from optical_link.analysis import analyze_eye, count_errors
from optical_link.instruments import Attenuator, Bert, Dca, Osa, SimResourceManager
from optical_link.model import LinkConfig
from optical_link.sweep import run_sweep


def test_shared_scpi_acquisition_and_cleanup():
    with SimResourceManager(LinkConfig(n_bits=1024)) as manager:
        att = Attenuator(manager.open_resource('SIM::ATT'))
        bert = Bert(manager.open_resource('SIM::BERT'))
        dca = Dca(manager.open_resource('SIM::DCA'))
        osa = Osa(manager.open_resource('SIM::OSA'))
        with pytest.raises(RuntimeError, match='acquire'):
            dca.capture()
        att.set_power(-30)
        weak = bert.measure()
        trace = dca.capture()
        assert count_errors(trace.bits, trace.decisions) == weak
        att.set_power(-12)
        with pytest.raises(RuntimeError, match='acquire'):
            dca.capture()
        assert bert.measure()['errors'] < weak['errors']
        assert osa.measure()['peak_wavelength_nm'] == pytest.approx(1550)
        resource = bert.resource
        with pytest.raises(ValueError):
            resource.write(':UNSUPPORTED 1')
        with pytest.raises(ValueError):
            resource.query(':POW?')
    with pytest.raises(RuntimeError, match='closed'):
        resource.query('*IDN?')
    assert all(r.closed for r in manager.resources)


def test_sweep_csv_can_be_reanalyzed_and_reproduced(tmp_path):
    config = LinkConfig(n_bits=1024, samples_per_bit=16)
    paths = [tmp_path / 'first', tmp_path / 'second']
    for path in paths:
        run_sweep(path, config, [-30, -15], target_ber=0.01)
    for name in ['ber.csv', 'eye.csv', 'spectrum_metrics.csv', 'sensitivity.csv']:
        assert (paths[0] / name).read_bytes() == (paths[1] / name).read_bytes()
    metadata = json.loads((paths[0] / 'metadata.json').read_text())
    assert metadata['simulated'] is True
    assert metadata['config']['seed'] == 2026
    rows = list(csv.DictReader((paths[0] / 'ber.csv').open()))
    assert len(rows) == 2
    assert int(rows[0]['errors']) > int(rows[1]['errors'])
    with gzip.open(paths[0] / 'point_000_waveform.csv.gz', 'rt') as stream:
        trace = np.loadtxt(stream, delimiter=',', skiprows=1)
    measured = count_errors(trace[:, 0], trace[:, 1])
    assert measured['errors'] == int(rows[0]['errors'])
    eye = analyze_eye(trace[:, 2:].ravel(), trace[:, 0], 16)
    eyes = list(csv.DictReader((paths[0] / 'eye.csv').open()))
    assert eye['eye_height_mw'] == pytest.approx(float(eyes[0]['eye_height_mw']), rel=1e-6)
    assert len(list(paths[0].glob('*_spectrum.csv'))) == 2
    commands = list(csv.DictReader((paths[0] / 'commands.csv').open()))
    assert any(row['command'] == ':INIT' for row in commands)
    assert (paths[0] / 'summary.png').stat().st_size > 1000
    with pytest.raises(FileExistsError):
        run_sweep(paths[0], config, [-15])


@pytest.mark.parametrize('powers,target', [([], .01), ([-10, -10], .01),
    ([float('nan')], .01), ([-100], .01), ([-10], 0)])
def test_invalid_sweep_does_not_create_output(tmp_path, powers, target):
    destination = tmp_path / 'invalid'
    with pytest.raises(ValueError):
        run_sweep(destination, LinkConfig(n_bits=127), powers, target)
    assert not destination.exists()


def test_cli_runs_without_hardware_and_rejects_bad_input(tmp_path):
    result = subprocess.run([sys.executable, '-m', 'optical_link', '--output',
        str(tmp_path / 'cli'), '--bits', '1024', '--powers', '-30', '-15'],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'SIMULATED' in result.stdout
    bad = subprocess.run([sys.executable, '-m', 'optical_link', '--bits', '0'],
                         capture_output=True, text=True)
    assert bad.returncode != 0
    assert 'n_bits' in bad.stderr


def test_failed_export_marks_partial_run_and_closes_resources(tmp_path, monkeypatch):
    import optical_link.sweep as sweep
    managers = []
    class TrackedManager(SimResourceManager):
        def __init__(self, config):
            super().__init__(config)
            managers.append(self)
    def fail_plot(*args):
        raise OSError('simulated disk failure')
    monkeypatch.setattr(sweep, 'SimResourceManager', TrackedManager)
    monkeypatch.setattr(sweep, '_plot', fail_plot)
    output = tmp_path / 'partial'
    with pytest.raises(OSError, match='disk failure'):
        run_sweep(output, LinkConfig(n_bits=127), [-15])
    assert all(r.closed for r in managers[0].resources)
    assert managers[0].bench.capture is None
    assert json.loads((output / 'metadata.json').read_text())['status'] == 'failed'
    assert (output / 'ber.csv').exists()
    assert (output / 'commands.csv').exists()


def test_command_log_write_failure_cannot_mark_run_complete(tmp_path, monkeypatch):
    import optical_link.sweep as sweep
    original = sweep._write_csv
    def fail_commands(path, rows):
        if path.name == 'commands.csv':
            raise OSError('command log unavailable')
        return original(path, rows)
    monkeypatch.setattr(sweep, '_write_csv', fail_commands)
    output = tmp_path / 'log-failure'
    with pytest.raises(OSError, match='command log unavailable'):
        run_sweep(output, LinkConfig(n_bits=127), [-15])
    assert json.loads((output / 'metadata.json').read_text())['status'] == 'failed'
