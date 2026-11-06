"""Hand values catch unit, topology and aggregation mistakes."""

from dataclasses import replace

import numpy as np
import pytest

from pdn.model import Bank, Study, bank_impedance, impedance, load_study


def test_target_and_dc_estimates():
    model = Study()
    assert model.target_ohm == pytest.approx(0.001125)
    assert model.baseline_v == pytest.approx(0.893)
    assert model.high_load_v == pytest.approx(0.879)


def test_four_parallel_series_rlc_parts_at_resonance():
    bank = Bank("bulk", "board", 4, 100e-6, 0.02, 1e-9)
    f0 = 1 / (2 * np.pi * np.sqrt(100e-6 * 1e-9))
    assert bank_impedance(bank, np.array([f0]))[0] == pytest.approx(0.005, abs=1e-12)


def test_shared_package_path_is_in_series_with_board_network():
    # At 1 Hz the small capacitors are effectively open: only the source path conducts.
    model = replace(Study(), banks=(Bank("tiny", "die", 1, 1e-15, 1, 1e-9),))
    z = impedance(model, np.array([1.0]))[0]
    assert z.real == pytest.approx(0.00035, rel=1e-8)
    assert z.imag == pytest.approx(2 * np.pi * 2.15e-9, rel=1e-6)


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True])
def test_invalid_physical_values_rejected(value):
    with pytest.raises(ValueError):
        replace(Study(), rise_s=value)


@pytest.mark.parametrize(
    "changes",
    [
        {"stop_s": 1e-6},
        {"f_stop_hz": 100},
        {"step_a": 0},
        {"max_step_s": 1e-6},
        {"points_per_decade": 1.5},
    ],
)
def test_invalid_analysis_settings_rejected(changes):
    with pytest.raises(ValueError):
        replace(Study(), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"count": -1},
        {"count": 1.5},
        {"node": "elsewhere"},
        {"name": "bad\n.end"},
        {"esr_ohm": 0},
    ],
)
def test_invalid_bank_rejected(changes):
    with pytest.raises(ValueError):
        replace(Study().banks[0], **changes)


def test_disabled_bank_is_open():
    bank = replace(Study().banks[0], count=0)
    assert np.isinf(bank_impedance(bank, np.array([1000]))).all()


def test_config_round_trip_and_unknown_fields(tmp_path):
    import json
    from dataclasses import asdict

    path = tmp_path / "study.json"
    path.write_text(json.dumps(asdict(Study())))
    assert load_study(path) == Study()
    path.write_text('{"voltage_mv": 900}')
    with pytest.raises(ValueError, match="voltage_mv"):
        load_study(path)


def test_duplicate_bank_names_rejected():
    bank = Study().banks[0]
    with pytest.raises(ValueError, match="unique"):
        replace(Study(), banks=(bank, bank))
