import sqlite3

import numpy as np
import pytest

from analysis.core import analyze, lowpass, median_filter, spectrum, validate
from analysis.logs import load_csv, load_database
from analysis.simulate import simulate, write_csv


def test_lowpass_cutoff_and_stopband_against_known_tones():
    fs, cutoff = 1.0, 0.05
    t = np.arange(20000) / fs
    for frequency, expected in [(0.005, 1.0), (cutoff, 0.5), (0.2, 0.0)]:
        x = np.sin(2 * np.pi * frequency * t)
        y = lowpass(x, fs, cutoff)
        gain = np.sqrt(np.mean(y[1000:-1000] ** 2) / np.mean(x[1000:-1000] ** 2))
        assert gain == pytest.approx(expected, abs=0.005)


def test_median_rejects_isolated_spikes_and_preserves_constant_edges():
    x = np.full(100, 22.0)
    x[50] = 90
    assert np.array_equal(median_filter(x, 5), np.full(100, 22.0))


def test_fft_recovers_tones_and_integrated_power():
    fs, n = 1.0, 2000
    t = np.arange(n) / fs
    x = 22 + 2 * np.sin(2 * np.pi * .01 * t) + .5 * np.sin(2 * np.pi * .2 * t)
    result = spectrum(x, fs, .05)
    assert result['peaks'][0]['frequency_hz'] == pytest.approx(.01, abs=fs/n)
    assert result['noise_peaks'][0]['frequency_hz'] == pytest.approx(.2, abs=fs/n)
    assert np.sum(result['psd']) * fs/n == pytest.approx(2.125, rel=1e-8)
    assert result['band_snr_db'] == pytest.approx(10*np.log10(16), abs=.01)


def test_constant_has_no_invented_peaks_or_infinite_snr():
    result = spectrum(np.full(100, 22.), 1., .05)
    assert result['peaks'] == []
    assert result['band_snr_db'] is None


def test_seeded_real_cadence_simulator_improves_against_truth():
    data, manifest = simulate()
    again, _ = simulate()
    np.testing.assert_array_equal(data.values, again.values)
    result = analyze(data, cutoff_hz=1/3600, median_window=5)
    assert result['truth']['filtered_rmse'] < result['truth']['raw_rmse'] / 3
    assert result['truth']['filtered_snr_db'] > result['truth']['raw_snr_db'] + 10
    assert result['raw_spectrum']['noise_peaks'][0]['frequency_hz'] == pytest.approx(
        manifest['noise_tone_hz'], abs=result['resolution_hz'])
    assert result['raw_spectrum']['peaks'][0]['frequency_hz'] == pytest.approx(
        manifest['signal_tone_hz'], abs=result['resolution_hz'])


@pytest.mark.parametrize('times,values', [
    (np.arange(50)*300., np.full(50, np.nan)),
    (np.arange(50)*300., np.full(50, np.inf)),
    (np.arange(50)*300., np.zeros(49)),
    (np.zeros(50), np.zeros(50)),
    (np.arange(50)[::-1], np.zeros(50)),
    (np.r_[np.arange(49)*300., 16000], np.zeros(50)),
    (np.arange(10)*300., np.zeros(10)),
])
def test_rejects_invalid_or_gapped_logs(times, values):
    with pytest.raises(ValueError):
        validate(times, values)


@pytest.mark.parametrize('cutoff', [0, -.01, .5, .6, float('nan')])
def test_rejects_invalid_cutoffs(cutoff):
    with pytest.raises(ValueError):
        lowpass(np.zeros(100), 1, cutoff)


@pytest.mark.parametrize('window', [0, -1, 2, 101, 2.5])
def test_rejects_invalid_median_windows(window):
    with pytest.raises(ValueError):
        median_filter(np.zeros(100), window)


def test_csv_roundtrip_and_humidity_units(tmp_path):
    data, _ = simulate()
    path = tmp_path / 'samples.csv'
    write_csv(path, data)
    loaded = load_csv(path, 'temperature')
    np.testing.assert_allclose(loaded.values, data.values)
    np.testing.assert_allclose(loaded.truth, data.truth)
    humidity = load_csv(path, 'humidity')
    assert np.mean(humidity.values) == pytest.approx(45, abs=.1)


def test_database_uses_existing_adapter_schema_read_only_and_device(tmp_path):
    # Use the real adapter to establish the schema instead of a lookalike fixture.
    import importlib.util
    spec = importlib.util.spec_from_file_location('desk_api', 'firmware/tools/desk_api.py')
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    path = tmp_path / 'room.sqlite3'
    store = adapter.Gateway(path, adapter.DemoLifeOS())
    with store.db:
        for i in range(50):
            for device, temperature in [('desk', 22000+i), ('other', 99000)]:
                store.db.execute('INSERT INTO readings VALUES(?,?,?,?,?,?,?)',
                                 (device, 'session', i, 1700000000+i*300, temperature, 45000, 'synthetic'))
    store.db.close()
    before = path.read_bytes()
    data = load_database(path, 'desk', 'temperature')
    assert data.values[0] == 22
    assert data.values[-1] == 22.049
    assert data.truth is None
    assert path.read_bytes() == before
    assert not (tmp_path / 'missing.sqlite3').exists()
    with pytest.raises(ValueError):
        load_database(tmp_path / 'missing.sqlite3', 'desk', 'temperature')
    assert not (tmp_path / 'missing.sqlite3').exists()


def test_csv_bad_header_and_nonfinite_truth_rejected(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('timestamp,wrong\n1,2\n')
    with pytest.raises(ValueError):
        load_csv(path, 'temperature')
    data, _ = simulate()
    write_csv(path, data)
    rows = path.read_text().splitlines()
    fields = rows[1].split(',')
    fields[3] = 'nan'
    rows[1] = ','.join(fields)
    path.write_text('\n'.join(rows))
    with pytest.raises(ValueError):
        load_csv(path, 'temperature')
    with pytest.raises(ValueError):
        validate(data.times, data.values, np.full(len(data.values), np.nan))


def test_one_percent_jitter_allowed_but_missing_time_rejected():
    t = 1700000000 + np.arange(100)*300.
    t[30] += 1
    assert validate(t, np.ones(100)) == pytest.approx(1/300)
    t[0] = 0
    with pytest.raises(ValueError, match='synchronized'):
        validate(t, np.ones(100))


def test_short_signal_band_rejected_and_nyquist_peak_retained():
    with pytest.raises(ValueError, match='FFT bin'):
        spectrum(np.zeros(100), 1., .001)
    result = spectrum((-1.)**np.arange(100), 1., .05)
    assert result['noise_peaks'][0]['frequency_hz'] == .5


def test_truth_metrics_are_undefined_for_zero_error_or_zero_signal():
    from analysis.core import Samples
    data = Samples(1700000000+np.arange(100)*300., np.full(100, 22.), np.full(100, 22.))
    result = analyze(data, 1/3600)
    assert result['truth']['raw_rmse'] == 0
    assert result['truth']['raw_snr_db'] is None


def test_database_interval_selection_and_duplicate_time(tmp_path):
    path = tmp_path / 'readings.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE readings(device, timestamp, temperature_mc, humidity_mpermil)')
        db.executemany('INSERT INTO readings VALUES(?,?,?,?)',
                       [('desk', 1700000000+i*300, 22000, 45000) for i in range(100)])
    data = load_database(path, 'desk', 'humidity', 1700000300, 1700000300+40*300)
    assert len(data.values) == 41
    np.testing.assert_array_equal(data.values, np.full(41, 45.))
    with pytest.raises(ValueError):
        load_database(path, 'absent', 'temperature')
    with pytest.raises(ValueError):
        load_database(path, 'desk', 'temperature', start=20, end=10)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO readings VALUES(?,?,?,?)', ('desk', 1700000300, 22000, 45000))
    with pytest.raises(ValueError, match='cadence'):
        load_database(path, 'desk', 'temperature')


def test_csv_row_limit_is_enforced_before_unbounded_allocation(tmp_path, monkeypatch):
    import analysis.logs as logs
    data, _ = simulate()
    path = tmp_path / 'samples.csv'
    write_csv(path, data)
    monkeypatch.setattr(logs, 'MAX_SAMPLES', 40)
    with pytest.raises(ValueError, match='200000'):
        load_csv(path)


def test_median_window_resource_bound():
    with pytest.raises(ValueError):
        median_filter(np.ones(1000), 999)


@pytest.mark.parametrize('constant', [22.0, 22.1, 22.3, 45.1, 100.1])
def test_nonbinary_constant_has_zero_spectral_power_and_undefined_truth_snr(constant):
    from analysis.core import Samples
    values = np.full(100, constant)
    result = spectrum(values, 1., .05)
    assert result['band_snr_db'] is None
    assert result['peaks'] == []
    assert np.all(result['psd'] == 0)
    report = analyze(Samples(1700000000 + np.arange(100)*300., values, values.copy()), 1/3600)
    assert report['truth']['raw_snr_db'] is None
    assert report['truth']['filtered_snr_db'] is None
    np.testing.assert_array_equal(report['filtered'], values)
    assert report['filtered_spectrum']['peaks'] == []
    assert report['filtered_spectrum']['band_snr_db'] is None
