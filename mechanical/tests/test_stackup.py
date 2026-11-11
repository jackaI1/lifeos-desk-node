"""Worst-case and root-sum-square stack-up on the committed spec."""
import json
import math

import pytest

from enclosure_fea.stackup import load_spec, radial_clearance, report, vertical_clearance


@pytest.fixture
def spec():
    return load_spec()


def test_vertical_nominal_and_worst_case(spec):
    v = vertical_clearance(spec)
    # 12.0 - 5.0 - 1.6 - 3.3 = 2.1 mm nominal; tolerances add 0.2 + 0.15 + 0.16 + 0.2 = 0.71 mm
    assert v['nominal_mm'] == pytest.approx(2.1)
    assert v['worst_case_mm'] == pytest.approx(1.39)
    assert v['worst_case_pass'] and v['rss_pass']
    assert v['rss_mm'] >= v['worst_case_mm']


def test_radial_with_3_2_mm_hole_fails_worst_case(spec):
    r = radial_clearance(spec)
    assert r['hole_min_mm'] == pytest.approx(3.15)
    assert r['slack_mm'] == pytest.approx(0.085)
    assert r['worst_case_mm'] == pytest.approx(-0.115)
    assert not r['worst_case_pass']
    assert r['hole_needed_worst_mm'] == pytest.approx(3.43)


def test_radial_with_3_5_mm_hole_passes(spec):
    r = radial_clearance(spec, hole_diameter=3.5)
    assert r['worst_case_pass'] and r['rss_pass']
    assert r['worst_case_mm'] == pytest.approx(0.035)


def test_report_is_json_serialisable(spec):
    text = json.dumps(report(spec))
    data = json.loads(text)
    assert set(data) == {'vertical', 'radial', 'radial_with_3_5_mm_hole'}


def test_rejects_non_mm_units(spec, tmp_path):
    bad = dict(spec, units='in')
    path = tmp_path / 'spec.json'
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        load_spec(path)


def test_rejects_negative_tolerance_and_bad_sign(spec):
    bad = json.loads(json.dumps(spec))
    bad['vertical']['items'][0]['tol'] = -0.1
    with pytest.raises(ValueError):
        vertical_clearance(bad)
    bad = json.loads(json.dumps(spec))
    bad['vertical']['items'][0]['sign'] = 2
    with pytest.raises(ValueError):
        vertical_clearance(bad)
    bad = json.loads(json.dumps(spec))
    bad['radial']['position_items'][0]['tol'] = math.nan
    with pytest.raises(ValueError):
        radial_clearance(bad)
