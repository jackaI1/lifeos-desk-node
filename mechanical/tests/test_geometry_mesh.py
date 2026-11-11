"""Case geometry, STEP export and the tetrahedral mesh."""
import math
from dataclasses import replace

import gmsh
import pytest

from enclosure_fea.board import BOARD_D, BOARD_W, MOUNT_HOLES, CaseParams
from enclosure_fea.geometry import build_case, export_step, gmsh_model, mesh_box, mesh_case


@pytest.fixture(scope='module')
def design_mesh():
    return mesh_case(CaseParams().validate(), 1.0)


def test_default_case_is_valid_and_has_four_standoffs():
    p = CaseParams().validate()
    assert len(p.standoff_centres()) == 4
    assert len(p.post_centres()) == 4


def test_mount_holes_lie_on_the_board_with_margin():
    for x, y in MOUNT_HOLES:
        assert 3.0 <= x <= BOARD_W - 3.0
        assert 3.0 <= y <= BOARD_D - 3.0


def test_standoffs_follow_the_board_hole_pattern():
    p = CaseParams()
    centres = p.standoff_centres()
    for (bx, by), (cx, cy) in zip(MOUNT_HOLES, centres):
        assert cx - p.board_origin()[0] == pytest.approx(bx)
        assert cy - p.board_origin()[1] == pytest.approx(by)


@pytest.mark.parametrize('change', [
    dict(wall=0.0),
    dict(cavity_height=-1.0),
    dict(standoff_height=12.0),          # standoffs must be shorter than the cavity
    dict(side_clearance=0.2),            # board needs 0.5 mm to the walls
    dict(screw_hole_radius=2.6),         # hole bigger than its post
    dict(wall=float('nan')),
])
def test_validate_rejects_impossible_dimensions(change):
    with pytest.raises(ValueError):
        replace(CaseParams(), **change).validate()


def test_mesh_fills_the_solid(design_mesh):
    """Sum of tetrahedron volumes must match the CAD solid's own volume (within 2 %)."""
    with gmsh_model('volume_check') as occ:
        build_case(occ, CaseParams().validate())
        solid_volume = sum(gmsh.model.occ.getMass(3, tag) for _, tag in gmsh.model.getEntities(3))
    assert design_mesh['total_volume_mm3'] == pytest.approx(solid_volume, rel=0.02)


def test_every_tetrahedron_is_positively_oriented(design_mesh):
    assert design_mesh['min_volume_mm3'] > 0
    assert len(design_mesh['elements']) > 10000
    assert design_mesh['elements'].shape[1] == 10


def test_coarser_mesh_has_fewer_elements():
    coarse = mesh_case(CaseParams().validate(), 2.0)
    fine = mesh_case(CaseParams().validate(), 1.0)
    assert len(coarse['elements']) < len(fine['elements'])


@pytest.mark.parametrize('lc', [0, -1.0, float('inf')])
def test_mesh_size_must_be_positive_and_finite(lc):
    with pytest.raises(ValueError):
        mesh_case(CaseParams().validate(), lc)


def test_step_export_writes_an_iso_10303_file(tmp_path):
    path = export_step(CaseParams().validate(), tmp_path / 'case.step')
    text = path.read_text(errors='replace')
    assert text.startswith('ISO-10303-21')
    assert 'MANIFOLD_SOLID_BREP' in text or 'CLOSED_SHELL' in text


def test_box_mesh_records_its_size():
    mesh = mesh_box(20.0, 4.0, 3.0, 1.0)
    assert mesh['box'] == (20.0, 4.0, 3.0)
    assert math.isclose(mesh['total_volume_mm3'], 240.0, rel_tol=0.02)
