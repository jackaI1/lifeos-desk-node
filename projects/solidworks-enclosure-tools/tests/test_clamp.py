import pathlib,json,pytest
from clamp_check import check
ROOT=pathlib.Path(__file__).resolve().parents[1]
P=json.loads((ROOT/'specs/clamp.json').read_text())

def test_baseline_and_changed_parameters_positive():
    a=check(P)
    assert a['passes']
    assert a['clearances_mm']['pin_diametral_worst']==pytest.approx(.15)
    for case in P['parameter_cases']:
        assert check(dict(P,**case['overrides']))['passes']

def test_bad_pin_fit_and_short_bolt_flagged():
    assert not check(dict(P,locator_hole_mm=5.8))['passes']
    assert not check(dict(P,bolt_length_mm=30))['passes']

@pytest.mark.parametrize('relative,overrides',[
    ('',{}),
    ('cases/larger-base-taller-coupon',P['parameter_cases'][0]['overrides']),
])
def test_solidworks_rebuild_mates_and_clearances_after_parameter_change(relative,overrides):
    import numpy as np,trimesh
    from printcheck import load_mesh,ray_hits
    folder=ROOT/'cad/clamp'/relative
    saved=json.loads((folder/'native-assembly.json').read_text())
    reopened=json.loads((folder/'reopen-check.json').read_text())
    p=dict(P,**overrides)
    assert saved['rebuild'] and reopened['rebuild']
    assert saved['components']==reopened['component_count']==9
    assert saved['mates']==reopened['mates']==24
    assert reopened['floating_components']==8
    assert reopened['mate_references']==48
    assert saved['interferences']==reopened['interferences']==0
    expected={x['component']:x for x in saved['placements']}
    for component in reopened['components']:
        transform=component['transform']
        assert transform[:9]==pytest.approx([1,0,0,0,1,0,0,0,1],abs=1e-7)
        if component['fixed_component']:continue
        assert component['mate_references']==3
        wanted=expected[component['component']]
        assert wanted['error_mm']<.001
        assert [1000*x for x in transform[9:12]]==pytest.approx(wanted['expected_mm'],abs=.001)
    for key in ['base_length_mm','coupon_height_mm','locator_pin_mm','locator_hole_mm']:
        assert saved['parameters'][key]==p[key]
    assert check(saved['parameters'])['passes']
    base=trimesh.load_mesh(folder/'CL-001_base.STL')
    coupon=trimesh.load_mesh(folder/'CL-004_coupon.STL')
    assert base.is_watertight and coupon.is_watertight
    assert base.extents[0]==pytest.approx(p['base_length_mm'],abs=.001)
    pin=trimesh.load_mesh(folder/'CL-002_locator_pin.STL')
    tip=pin.vertices[np.abs(pin.vertices[:,2]-p['locator_pin_length_mm'])<.001]
    measured_pin=float(np.ptp(tip[:,0]))
    assert measured_pin==pytest.approx(p['locator_pin_mm'],abs=.001)
    center=np.array([p['base_length_mm']/2+p['locator_x_mm'],p['base_width_mm']/2+p['locator_y_mm']])
    radii=np.linalg.norm(base.vertices[:,:2]-center,axis=1)
    bottom=(np.abs(base.vertices[:,2])<.001)&(radii>2)&(radii<4)
    measured_hole=float(np.median(radii[bottom])*2)
    assert measured_hole==pytest.approx(p['locator_hole_mm'],abs=.001)
    assert measured_hole-measured_pin-p['hole_tolerance_mm']>0

    assert coupon.extents[2]==pytest.approx(p['coupon_height_mm'],abs=.001)
    # Ray lands on the recessed shoulder seat, proving that the counterbore is real.
    t=load_mesh(folder/'CL-001_base.STL')
    x=p['base_length_mm']/2+p['locator_x_mm']+3.5
    y=p['base_width_mm']/2+p['locator_y_mm']
    hit=ray_hits(np.array([x,y,100.]),np.array([0.,0.,-1.]),t).min()
    assert 100-hit==pytest.approx(p['base_thickness_mm']-p['locator_shoulder_thickness_mm'],abs=.001)

def test_all_native_clamp_part_meshes_are_closed_and_match_volume():
    import re,trimesh
    for folder in [ROOT/'cad/clamp',ROOT/'cad/clamp/cases/larger-base-taller-coupon']:
        records=re.findall(r'PART (\S+) bodies=1 volume_mm3=([\d.]+)',(folder/'build-results.txt').read_text())
        assert len(records)==7
        for name,volume in records:
            mesh=trimesh.load_mesh(folder/f'{name}.STL')
            assert mesh.is_watertight
            assert mesh.volume==pytest.approx(float(volume),rel=.01)
