import numpy as np
import pytest

from anomaly_int8 import data, quant


def test_synthetic_log_has_labelled_faults_in_range(tmp_path):
    timestamps, temperature, humidity, anomaly = data.make_log(days=3)
    assert len(timestamps) == 3 * 86400 // 300
    assert set(np.unique(anomaly)) == {0, 1, 2, 3, 4}
    assert temperature.min() >= -40000 and temperature.max() <= 130000
    assert humidity.min() >= 0 and humidity.max() <= 100000
    path = tmp_path / 'log.csv'
    data.write_log(path, timestamps, temperature, humidity, anomaly)
    back = data.read_log(path)
    assert np.array_equal(back[1], temperature)
    assert np.array_equal(back[3], anomaly)


def test_read_log_accepts_a_real_export_without_labels(tmp_path):
    path = tmp_path / 'real.csv'
    path.write_text('timestamp,temperature_mc,humidity_mpermil\n1,22100,45000\n2,22200,44000\n')
    timestamps, temperature, humidity, anomaly = data.read_log(path)
    assert list(temperature) == [22100, 22200]
    assert list(anomaly) == [0, 0]


@pytest.mark.parametrize('body, message', [
    ('timestamp,temperature_mc,humidity_mpermil\n', 'no readings'),
    ('timestamp,temperature_mc,humidity_mpermil\n2,22000,45000\n1,22000,45000\n', 'increase'),
    ('timestamp,temperature_mc,humidity_mpermil\n1,200000,45000\n', 'sensor range'),
    ('timestamp,temperature_mc,humidity_mpermil\n1,22000,120000\n', '0 to 100'),
    ('timestamp,temperature_mc,humidity_mpermil\n1,22.5,45000\n', 'integer'),
    ('timestamp,temperature_mc,humidity_mpermil,anomaly\n1,22000,45000,7\n', 'code'),
    ('timestamp,temp\n1,2\n', 'columns'),
])
def test_read_log_rejects_bad_input(tmp_path, body, message):
    path = tmp_path / 'bad.csv'
    path.write_text(body)
    with pytest.raises(ValueError, match=message):
        data.read_log(path)


def test_windows_are_chronological_and_contaminated_when_any_reading_is_injected():
    temperature = np.arange(10, dtype=np.int64) * 100 + 22000
    humidity = np.full(10, 45000, dtype=np.int64)
    anomaly = np.zeros(10, dtype=np.int64)
    anomaly[5] = 1
    rows, kind, contaminated = data.windows(temperature, humidity, anomaly)
    assert rows.shape == (7, 8)
    assert list(rows[0, :4]) == [0, 100, 200, 300]          # oldest reading first
    assert list(contaminated) == [False, False, True, True, True, True, False]
    assert kind[2] == 1 and kind[3] == 1 and kind[0] == 0


def test_device_rounding_is_half_up_and_matches_c_rule():
    # Ties go up at +0.05 C (half a 0.1 C step), and down-to-zero at -0.05 C.
    temps = np.array([[22050, 21950, 22049, 21951]], dtype=np.int64)
    hums = np.array([[45250, 44750, 45249, 44751]], dtype=np.int64)
    units = quant.quantise_readings(temps, hums)[0]
    assert list(units[:4]) == [1, 0, 0, 0]
    assert list(units[4:]) == [1, 0, 0, 0]


def test_quantised_inputs_saturate_at_int8_limits():
    temps = np.array([[-40000, 130000, 22000, 22000]], dtype=np.int64)
    hums = np.array([[0, 100000, 45000, 45000]], dtype=np.int64)
    units = quant.quantise_readings(temps, hums)[0]
    assert units[0] == -128 and units[1] == 127
    assert units[4] == -90 and units[5] == 110   # 0 %RH and 100 %RH, 45 %RH centre
