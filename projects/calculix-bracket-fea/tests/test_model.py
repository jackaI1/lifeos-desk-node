import numpy as np
import pytest
from fea.model import mesh_model, traction_loads


@pytest.mark.parametrize('kind', ['beam', 'bracket'])
def test_mesh_and_surface_loads_conserve_resultant_and_moment(kind):
    mesh = mesh_model(kind, 5)
    assert len(mesh['fixed']) > 6
    assert mesh['elements'].shape[1] == 10
    assert len(set(mesh['fixed']) & set(mesh['loaded'].ravel())) == 0
    loads = traction_loads(mesh, (0, 60, -100))
    np.testing.assert_allclose(sum(loads.values()), (0,60,-100), atol=1e-10)
    moment = sum(np.cross(mesh['nodes'][n], f) for n, f in loads.items())
    # Load face centroid: beam (100,0,0), bracket (80,0,3).
    centroid = (100,0,0) if kind == 'beam' else (80,0,3)
    np.testing.assert_allclose(moment, np.cross(centroid, (0,60,-100)), atol=1e-8)


@pytest.mark.solver
def test_real_beam_solver_matches_hand_calculation(tmp_path):
    from fea.study import solve_beam
    r = solve_beam(tmp_path)
    assert r['deflection_error_fraction'] < 0.03
    assert r['stress_error_fraction'] < 0.05
    assert r['force_balance_error_fraction'] < 1e-5


def test_refinement_keeps_physical_stress_probes_at_same_coordinates():
    for h in (4,3):
        m=mesh_model('bracket',h)
        xyz = np.array(list(m['nodes'].values()))
        for p in ((6,10,41.5),(6,-10,41.5),(7.757359312880715,0,7.757359312880715)):
            assert np.min(np.linalg.norm(xyz-p,axis=1)) < 1e-7


def test_no_construction_points_enter_solver_deck():
    m=mesh_model('bracket',4)
    assert set(m['nodes']) == set(m['elements'].ravel())


def test_reference_peak_can_be_embedded_on_a_curved_bore_edge():
    p=(6,10+3.5*__import__('math').sin(0.2),45-3.5*__import__('math').cos(0.2))
    m=mesh_model('bracket',4,extra_probes=[p])
    assert min(np.linalg.norm(np.array(v)-p) for v in m['nodes'].values()) < 1e-7


@pytest.mark.solver
def test_beam_stress_check_measures_field_error_not_only_fitted_scale(tmp_path):
    from fea.study import solve_beam
    r=solve_beam(tmp_path)
    assert r['stress_rms_error_fraction'] < 0.01
    assert r['stress_max_error_fraction'] < 0.05
