import numpy as np
import pytest

from pdn.analysis import ac_metrics, transient_metrics
from pdn.model import Study


def test_peaks_and_crossings_are_found_in_log_frequency():
    f = np.array([1, 10, 100, 1000, 10000], dtype=float)
    z = np.array([1, 3, 1, 4, 2], dtype=float)
    result = ac_metrics(f, z, 2)
    assert [p["frequency_hz"] for p in result["peaks"]] == [10, 1000]
    assert result["max_ohm"] == 4
    assert not result["meets_target"]
    # Crossing interpolation uses magnitude linear in log10(f).
    assert result["above_target_bands_hz"][0] == pytest.approx([10**0.5, 10**1.5])


def test_whole_band_fail_and_whole_band_pass():
    f = np.array([100, 1000, 10000])
    assert ac_metrics(f, np.ones(3) * 3, 2)["above_target_bands_hz"] == [[100, 10000]]
    assert ac_metrics(f, np.ones(3), 2)["meets_target"]


def test_droop_is_relative_to_loaded_baseline_not_nominal():
    t = np.array([0, 10e-6, 20e-6, 21e-6, 40e-6, 60e-6, 80e-6, 100e-6])
    v = np.array([0.893, 0.893, 0.893, 0.85, 0.879, 0.88, 0.91, 0.893])
    result = transient_metrics(Study(), t, v)
    assert result["baseline_v"] == pytest.approx(0.893)
    assert result["droop_v"] == pytest.approx(0.043)
    assert result["nominal_drop_v"] == pytest.approx(0.05)
    assert result["overshoot_v"] == pytest.approx(0.017)
    assert result["meets_droop_budget"]
