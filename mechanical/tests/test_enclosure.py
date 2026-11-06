import pytest
from mechanical.enclosure_analysis import evaluate

def test_hand_calculated_compression_and_temperature():
    r = evaluate({'cord': 2.0, 'cord_tol': 0.1, 'groove_depth': 1.5, 'groove_tol': 0.05, 'lid_gap': 0.0, 'gap_tol': 0.02, 'power_w': 1.0, 'thermal_resistance_k_w': 12.0}, samples=40000, seed=7)
    assert r['compression_nominal'] == pytest.approx(.5)
    assert r['compression_worst'] == pytest.approx((.33, .67))
    assert r['compression_sigma'] == pytest.approx((.1**2+.05**2+.02**2)**.5 / 3)
    assert r['simulation_sigma'] == pytest.approx(r['compression_sigma'], rel=.025)
    assert r['ranked'][0][0] == 'cord'
    assert r['temperature_rise_c'] == 12

def test_invalid_geometry_fails():
    with pytest.raises(ValueError): evaluate({'cord': 1, 'groove_depth': 2, 'lid_gap': 0, 'cord_tol': 0, 'groove_tol': 0, 'gap_tol': 0, 'power_w': 1, 'thermal_resistance_k_w': 1})
