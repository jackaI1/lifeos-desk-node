import math
import shutil
import pytest
from hardware.simulation.spice import exported_values,run_leak,run_tia

pytestmark=pytest.mark.skipif(not shutil.which('ngspice') or not shutil.which('kicad-cli'),reason='requires CLI circuit tools')


def test_exported_circuit_dc_ac_step_and_ripple(tmp_path):
    rf,cf=exported_values();result=run_tia(tmp_path/'nominal',rf=rf,cf=cf)
    assert result['gain_ohm']==pytest.approx(rf,rel=.001)
    assert result['bandwidth_hz']==pytest.approx(1/(2*math.pi*rf*cf),rel=.12)
    assert result['step_final_v']==pytest.approx(1.65+1e-6*rf,abs=.001)
    assert run_tia(tmp_path/'ripple',ripple=True)['ripple_vpp']<.0001


@pytest.mark.parametrize('r_factor,c_factor',[(.99,.95),(1.01,1.05),(.99,1.05),(1.01,.95)])
def test_tolerance_corners(tmp_path,r_factor,c_factor):
    rf=100000*r_factor;cf=100e-12*c_factor
    result=run_tia(tmp_path,rf=rf,cf=cf)
    assert result['gain_ohm']==pytest.approx(rf,rel=.001)
    assert result['bandwidth_hz']==pytest.approx(1/(2*math.pi*rf*cf),rel=.12)


@pytest.mark.parametrize('supply',[3.,3.3,3.6])
def test_leak_threshold_over_supply(tmp_path,supply):
    expected=1/(1/1e6+1/10e6)
    assert run_leak(tmp_path,supply)==pytest.approx(expected,abs=10000)
