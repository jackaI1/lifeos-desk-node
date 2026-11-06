import json
import subprocess
import sys

import numpy as np
import pytest
import skrf as rf

from antenna_matching.match import apply, design, element, load, return_loss
from antenna_matching.examples.generate import generate


@pytest.fixture(scope='module')
def antenna(tmp_path_factory):
    file = tmp_path_factory.mktemp('rf')/'synthetic.s1p'
    generate(file)
    return load(file)


@pytest.mark.parametrize('connection', ['series','shunt'])
@pytest.mark.parametrize('kind,value', [('L',3.3e-9), ('C',2.2e-12)])
def test_abcd_against_independent_impedance(connection,kind,value):
    f = rf.Frequency(2.4,2.5,3,'ghz')
    zload = 25 + 20j
    antenna = rf.Network(frequency=f,s=np.full((3,1,1),(zload-50)/(zload+50)),z0=50)
    w = 2*np.pi*f.f
    x = w*value if kind == 'L' else -1/(w*value)
    z = abs(x)/50 + 1j*x
    expected = z + zload if connection == 'series' else 1/(1/z + 1/zload)
    matched = apply(antenna,[dict(connection=connection,kind=kind,value_si=value)],50)
    np.testing.assert_allclose(matched.z[:,0,0],expected,rtol=1e-10)


def test_pi_order_matches_hand_calculation(antenna):
    parts=[dict(connection='shunt',kind='C',value_si=1e-12),dict(connection='series',kind='L',value_si=2e-9),dict(connection='shunt',kind='C',value_si=2e-12)]
    w=2*np.pi*antenna.f
    zin=antenna.z[:,0,0]
    for part in reversed(parts):
        x=w*part['value_si'] if part['kind']=='L' else -1/(w*part['value_si'])
        z=abs(x)/50+1j*x
        zin=zin+z if part['connection']=='series' else 1/(1/zin+1/z)
    np.testing.assert_allclose(apply(antenna,parts,50).z[:,0,0],zin)


@pytest.mark.parametrize('topology',['L','pi'])
def test_optimized_network_improves_whole_band(antenna,topology):
    report,matched=design(antenna,topology)
    assert report['after_worst_band_rl_db'] > 20
    assert report['after_mean_reflected_power'] < report['before_mean_reflected_power']/20
    assert report['worst_tolerance_corner_rl_db'] > 18
    assert len(report['parts_source_to_antenna']) == (2 if topology=='L' else 3)
    assert np.all(abs(matched.s[:,0,0]) <= 1)


def test_touchstone_reference_impedance_and_formats(tmp_path):
    for fmt in ['ri','ma','db']:
        file=tmp_path/f'{fmt}.s1p'
        f=rf.Frequency(2.3,2.6,7,'ghz')
        # 100 ohms at a 75 ohm calibration reference.
        n=rf.Network(frequency=f,s=np.full((7,1,1),1/7),z0=75)
        n.write_touchstone(str(file),form=fmt)
        np.testing.assert_allclose(load(file).s[:,0,0],1/3,rtol=1e-10)


def test_invalid_sweeps_and_band(antenna,tmp_path):
    bad=tmp_path/'bad.s1p'
    bad.write_text('# GHz S RI R 50\n2.4 2 0\n2.45 2 0\n2.5 2 0\n')
    with pytest.raises(ValueError,match='passive'):
        load(bad)
    for low,high in [(2e9,2.5e9),(2.5e9,2.4e9),(2.4001e9,2.4002e9)]:
        with pytest.raises(ValueError):
            design(antenna,'L',low,high)
    with pytest.raises(ValueError):
        element(antenna.frequency,'series','L',1e-9,0)


def test_cli_exports_reusable_predictions(tmp_path):
    file=tmp_path/'synthetic.s1p'; generate(file)
    out=tmp_path/'report'
    subprocess.run([sys.executable,'-m','antenna_matching.match',str(file),'--source-kind','synthetic','--output',str(out)],check=True,capture_output=True)
    report=json.loads((out/'report.json').read_text())
    assert report['source_kind']=='synthetic'
    assert len(report['input_sha256'])==64
    for name in ['L','pi']:
        predicted=load(out/f'{name}-predicted.s1p')
        r=next(x for x in report['designs'] if x['topology']==name)
        mask=(predicted.f>=2.4e9)&(predicted.f<=2.5e9)
        assert min(return_loss(predicted)[mask])==pytest.approx(r['after_worst_band_rl_db'])
    assert len((out/'sweep.csv').read_text().splitlines())==62
