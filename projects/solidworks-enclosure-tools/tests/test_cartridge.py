import pathlib,json
from cartridge_check import check,sweep
P=json.loads((pathlib.Path(__file__).resolve().parents[1]/'specs/cartridge.json').read_text())

def test_nominal_and_wall_sweep():
    assert check(P)['passes']
    rows=sweep(P)
    assert not rows[0]['passes']
    assert rows[-1]['passes']

def test_each_dfm_dfa_rule_can_fail():
    assert 'wall' in check(dict(P,wall_mm=1))['flags']
    assert 'draft' in check(dict(P,draft_deg=0))['flags']
    assert 'assembly_access' in check(dict(P,driver_diameter_mm=40))['flags']
    assert 'assembly_access' in check(dict(P,release_slot_width_mm=3))['flags']

def test_native_port_has_a_real_open_bore():
    import numpy as np,pytest,math
    from printcheck import load_mesh,ray_hits
    root=pathlib.Path(__file__).resolve().parents[1]
    for name in ['FC-003_inlet','FC-004_outlet']:
        t=load_mesh(root/'cad/cartridge'/f'{name}.STL')
        assert np.isinf(ray_hits(np.array([7.,7.,-1.]),np.array([0.,0.,1.]),t)).all()
        v=abs(np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6)
        assert v==pytest.approx(math.pi*300,rel=.01)

def test_native_shell_has_measured_draft_and_thickness():
    import pytest
    from cartridge_check import measure_shell
    root=pathlib.Path(__file__).resolve().parents[1]
    r=measure_shell(root/'cad/cartridge/FC-001_body.STL',P)
    assert r['shell_face_samples']>=8
    assert r['minimum_draft_deg']==pytest.approx(1.5,abs=.001)
    assert r['minimum_wall_sample_mm']>=P['minimum_wall_mm']
    assert r['passes']


def test_all_cartridge_meshes_closed_and_match_native_volume():
    import re,trimesh,pytest
    root=pathlib.Path(__file__).resolve().parents[1]
    text=(root/'cad/cartridge/build-results.txt').read_text()
    for name,volume in re.findall(r'PART (\S+) bodies=1 volume_mm3=([\d.]+)',text):
        m=trimesh.load_mesh(root/'cad/cartridge'/f'{name}.STL')
        assert m.is_watertight
        assert m.volume==pytest.approx(float(volume),rel=.01)
