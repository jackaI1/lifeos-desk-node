import numpy as np
import pytest
import trimesh
from printcheck import analyze, load_mesh

PROFILE = dict(build_mm=[220,220,250], min_wall_mm=1.2, overhang_deg=45,
               max_bridge_mm=10, density_g_cm3=1.27, cost_per_kg=25,
               layer_mm=0.2, extrusion_width_mm=0.45, speed_mm_s=40,
               support_fraction=0.2, grid_mm=1)

def box(size, center=(0,0,0)):
    m=trimesh.creation.box(extents=size);m.apply_translation(center);return m

def test_thin_wall_measured_from_mesh():
    r=analyze(box([20,10,0.8]).triangles, PROFILE, 'flat')
    assert r['minimum_wall_mm']==pytest.approx(.8)
    assert len(r['thin_faces'])>0
    assert r['support_volume_mm3']==0

def test_thick_wall_and_bed_not_overhang():
    r=analyze(box([20,10,2]).triangles, PROFILE, 'flat')
    assert r['minimum_wall_mm']==pytest.approx(2)
    assert r['thin_faces']==[]
    assert r['overhang_faces']==[]

def test_known_overhang_and_orientation():
    m=trimesh.util.concatenate([box([4,10,20],(0,0,10)),box([20,10,2],(8,0,21))])
    a=analyze(m.triangles,PROFILE,'upright')
    t=m.triangles.copy();t=t[:,:,[0,2,1]];t[:,:,2]*=-1
    b=analyze(t,PROFILE,'side')
    assert len(a['overhang_faces'])>0
    assert a['support_volume_mm3']>100
    assert a['max_bridge_mm']>10
    assert b['support_volume_mm3']<a['support_volume_mm3']

def test_build_volume_and_cost():
    r=analyze(box([221,10,2]).triangles, PROFILE,'oversize')
    assert not r['fits_printer']
    assert r['material_cost']>0 and r['time_hours']>0

def test_binary_stl_roundtrip(tmp_path):
    p=tmp_path/'known.stl';box([20,10,2]).export(p)
    assert load_mesh(p).shape==(12,3,3)

def test_native_exports_have_expected_volume_and_orientation():
    import json
    import pathlib
    root=pathlib.Path(__file__).resolve().parents[1]
    data=json.loads((root/'reports/print-A/results.json').read_text())['parts']
    assert data['ED-001_case_A.STL']['recommended']=='base-down'
    assert data['ED-002_lid_A.STL']['recommended']=='top-down'
    for filename,volume in [('ED-001_case_A.STL',33363.456),('ED-002_lid_A.STL',9544.3072597359)]:
        t=load_mesh(root/'cad/print-check'/filename)
        r=analyze(t,PROFILE,'base-down')
        assert r['volume_mm3']==pytest.approx(volume,rel=.01)
        saved=data[filename]['orientations'][0]
        assert r['support_volume_mm3']==pytest.approx(saved['support_volume_mm3'])
        assert r['overhang_faces']==saved['overhang_faces']

def test_solidworks_bracket_revision_removes_flags():
    import pathlib
    root=pathlib.Path(__file__).resolve().parents[1]
    before=analyze(load_mesh(root/'cad/bracket/BR-001_before.STL'),PROFILE,'base-down')
    after=analyze(load_mesh(root/'cad/bracket/BR-002_after.STL'),PROFILE,'base-down')
    assert before['minimum_wall_mm']==pytest.approx(.8,abs=1e-4)
    assert before['thin_faces'] and before['overhang_faces']
    assert before['support_volume_mm3']>10000
    assert after['minimum_wall_mm']==pytest.approx(3)
    assert after['thin_faces']==[] and after['overhang_faces']==[]
    assert after['support_volume_mm3']==0
    assert before['volume_mm3']==pytest.approx(1510.4,rel=.001)
    assert after['volume_mm3']==pytest.approx(10920,rel=.001)
