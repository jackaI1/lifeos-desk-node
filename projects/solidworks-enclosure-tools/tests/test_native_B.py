import pathlib
import pytest
import trimesh
ROOT=pathlib.Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('name,volume,height',[
    ('ED-101_sensor_housing_B',63992.1872749251,36.2),
    ('ED-102_sensor_lid_B',14291.0495667735,3),
    ('ED-103_gasket_B',1033.6,2),
])
def test_native_enclosure_exports(name,volume,height):
    m=trimesh.load_mesh(ROOT/'cad/B'/f'{name}.STL')
    assert m.is_watertight
    assert m.volume==pytest.approx(volume,rel=.01)
    assert m.extents[2]==pytest.approx(height,abs=.001)

def test_mounting_posts_have_actual_blind_holes():
    import numpy as np
    from printcheck import load_mesh,ray_hits
    t=load_mesh(ROOT/'cad/B/ED-101_sensor_housing_B.STL')
    for x,y in [(70.,50.),(10.,10.),(61.,38.5),(19.,21.5)]:
        distance=ray_hits(np.array([x,y,100.]),np.array([0.,0.,-1.]),t).min()
        assert 100-distance==pytest.approx(2.4,abs=.001)
