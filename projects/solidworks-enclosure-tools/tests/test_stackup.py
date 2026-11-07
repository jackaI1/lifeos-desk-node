import pytest
from stackup import compression, worst_case, monte_carlo, thermal


def test_compression():
    assert compression(2,1.3,.2)==pytest.approx(.25)
    with pytest.raises(ValueError): compression(0,1,.2)

def test_worst_known_corners():
    r=worst_case(2,1.3,.2,.08,.06,.05)
    assert r['min']==pytest.approx((1.92-1.36-.25)/1.92)
    assert r['max']==pytest.approx((2.08-1.24-.15)/2.08)

def test_monte_carlo_bounded_and_reproducible():
    args=(2,1.3,.2,.08,.06,.05)
    a=monte_carlo(*args,samples=10000,seed=5)
    b=monte_carlo(*args,samples=10000,seed=5)
    assert a==b
    w=worst_case(*args)
    assert w['min']<=a['min']<=a['max']<=w['max']
    assert a['mean']==pytest.approx(.25,abs=.002)

def test_zero_tolerances_and_thermal():
    r=monte_carlo(2,1.3,.2,0,0,0,samples=1000,seed=5)
    assert r['std']==pytest.approx(0,abs=1e-12)
    assert thermal(2,.04,5)==10

def test_real_spec_uses_same_height_limits_for_gap_and_compression():
    import json
    import pathlib
    from stackup import run
    p=json.loads((pathlib.Path(__file__).resolve().parents[1]/'specs/enclosure-B.json').read_text())
    r=run(p)
    gap=r['lid_gap']
    assert gap['worst_min_mm']>0
    assert r['compression']['worst_case']['min']==pytest.approx(compression(
        p['gasket_thickness_mm']-p['gasket_tolerance_mm'],
        p['groove_depth_mm']+p['depth_tolerance_mm'],gap['worst_max_mm']))
    assert r['compression']['contributors'][0]['name']=='housing_height'
    assert not r['compression']['passes']
