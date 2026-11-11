"""Supports and load cases: totals, locations and input checks."""
import math

import numpy as np
import pytest

from enclosure_fea.board import CaseParams
from enclosure_fea.geometry import mesh_box, mesh_case
from enclosure_fea.loads import (cantilever_loads, drop_loads, screw_down_loads, supports,
                                 traction_loads)


@pytest.fixture(scope='module')
def params():
    return CaseParams().validate()


@pytest.fixture(scope='module')
def case_mesh(params):
    return mesh_case(params, 1.0)


def _total(loads):
    return np.sum(list(loads.values()), axis=0)


def test_screw_down_total_equals_four_preloads(case_mesh, params):
    loads = screw_down_loads(case_mesh, params, 300.0)
    assert _total(loads) == pytest.approx([0.0, 0.0, -1200.0], abs=1e-6)


def test_screw_down_acts_only_on_post_tops(case_mesh, params):
    loads = screw_down_loads(case_mesh, params, 300.0)
    nodes = case_mesh['nodes']
    assert loads
    for n in loads:
        assert nodes[n][2] == pytest.approx(params.outer_height, abs=1e-6)


def test_drop_load_total_and_location(case_mesh, params):
    loads, load_nodes = drop_loads(case_mesh, params, 50.0)
    assert _total(loads) == pytest.approx([0.0, 0.0, -50.0], abs=1e-6)
    nodes = case_mesh['nodes']
    mid_x = params.outer_width / 2
    for n in load_nodes:
        assert nodes[n][2] == pytest.approx(params.outer_height, abs=1e-6)
        # The patch is picked by face centroid, so edge nodes can sit one 1 mm element outside it.
        assert abs(nodes[n][0] - mid_x) <= 3.0 + 1.0 + 1e-6
        assert 0 <= nodes[n][1] <= params.wall + 1e-6


def test_supports_sit_on_the_bottom_face(case_mesh, params):
    sup = supports(case_mesh, params)
    assert sup['fixed']
    for n in sup['fixed']:
        assert case_mesh['nodes'][n][2] == pytest.approx(0.0, abs=1e-6)


def test_supports_remove_rigid_body_motion(case_mesh, params):
    sup = supports(case_mesh, params)
    dofs = [d for fixed in sup['fixed'].values() for d in fixed]
    assert 1 in dofs and 2 in dofs and 3 in dofs


@pytest.mark.parametrize('force', [0, -5.0, float('nan')])
def test_screw_and_drop_reject_bad_forces(case_mesh, params, force):
    with pytest.raises(ValueError):
        screw_down_loads(case_mesh, params, force)
    with pytest.raises(ValueError):
        drop_loads(case_mesh, params, force)


def test_traction_rejects_bad_vector_and_empty_selection(case_mesh):
    with pytest.raises(ValueError):
        traction_loads(case_mesh, case_mesh['triangles'][:1], (1.0, 2.0))
    with pytest.raises(ValueError):
        traction_loads(case_mesh, [], (0.0, 0.0, -1.0))


def test_cantilever_loads_split_the_tip_force():
    mesh = mesh_box(20.0, 4.0, 3.0, 1.0)
    fixed, loads, tip = cantilever_loads(mesh, 10.0)
    assert all(mesh['nodes'][n][0] == pytest.approx(0.0, abs=1e-6) for n in fixed)
    assert _total(loads) == pytest.approx([0.0, 0.0, -10.0], abs=1e-6)
    assert all(mesh['nodes'][n][0] == pytest.approx(20.0, abs=1e-6) for n in tip)
    with pytest.raises(ValueError):
        cantilever_loads(mesh, math.inf)
