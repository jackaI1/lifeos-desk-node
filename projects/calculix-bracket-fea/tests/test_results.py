import pytest
from fea.results import summarize, assess_convergence


def test_result_summary_preserves_peak_location_and_yield_margin():
    m={'nodes':{7:(0,0,0),42:(1,0,0)},'elements':[[7,42]],'fixed':[7]}
    d={'displacements':{7:(0,0,0),42:(0,3,4)},'forces':{7:(0,0,10)}}
    s={7:(100,0,0,0,0,0),42:(20,20,20,0,0,0)}
    r=summarize(m,d,s,(0,0,-10),yield_mpa=250)
    assert r['peak_vm_mpa'] == 100
    assert r['peak_xyz_mm'] == [0,0,0]
    assert r['max_displacement_mm'] == 5
    assert r['yield_margin'] == 1.5
    assert r['force_balance_error_fraction'] == 0


@pytest.mark.parametrize('values,passed', [([10,11,11.1,11.12],True),([10,12,15,20],False)])
def test_convergence_does_not_claim_growing_stress_has_settled(values,passed):
    r=assess_convergence(values)
    assert r['within_five_percent_last_two_changes'] is passed


@pytest.mark.parametrize('field', [{7:(100,0,0,0,0,0)},
    {7:(100,0,0,0,0,0),42:(20,0,0,0,0,0),99:(1000,0,0,0,0,0)}])
def test_peak_discovery_rejects_missing_or_unexpected_nodes(field):
    from fea.results import peak_node
    with pytest.raises(ValueError):
        peak_node(field,{7,42})
