import pytest
from power_budget.charging import Cell, charge, check_trace, duty_cycle


def test_weighted_phases_and_capacity_derating():
    profile = [dict(seconds=8, ma=1), dict(seconds=2, ma=101)]
    result = duty_cycle(profile, capacity_mah=210)
    assert result['average_ma'] == 21
    assert result['runtime_hours'] == 10
    assert duty_cycle(profile, capacity_mah=210, temperature_c=0)['runtime_hours'] == 8
    assert duty_cycle(profile, voltage=3.4)['runtime_hours'] == 0


def test_cc_cv_charge_conserves_charge_and_terminates():
    result = charge()
    trace = result['trace']
    assert {row['stage'] for row in trace} == {'CC', 'CV'}
    assert trace[-1]['ma'] <= 10
    assert all(row['voltage'] <= 4.2 for row in trace)
    delivered = sum(row['ma']*5/3600 for row in trace[:-1])
    assert delivered == pytest.approx((trace[-1]['soc']-.2)*500, rel=1e-10)
    assert 3 < result['charge_hours'] < 8
    assert charge(Cell(temperature_c=5))['charge_hours'] > result['charge_hours']
    assert charge(Cell(initial_soc=1))['charge_hours'] == 0
    assert charge(step_s=1)['charge_hours'] == pytest.approx(result['charge_hours'], abs=.01)


@pytest.mark.parametrize('cell', [Cell(temperature_c=-1), Cell(temperature_c=46), Cell(initial_soc=-1), Cell(current_ma=0), Cell(capacity_mah=float('nan'))])
def test_unsafe_charging_rejected(cell):
    with pytest.raises(ValueError): charge(cell)


def test_trace_budget_brownout_and_heat():
    rows = [dict(seconds=0, ma=10, voltage=3.7, temperature_c=25), dict(seconds=10, ma=30, voltage=3.3, temperature_c=46)]
    result = check_trace(rows, budget_ma=19)
    assert result['average_ma'] == 20
    assert {x['error'] for x in result['alarms']} == {'budget', 'brownout', 'temperature'}
    assert not check_trace(rows[:1]+[dict(rows[0], seconds=10)], budget_ma=10)['alarms']
    with pytest.raises(ValueError): check_trace(rows[::-1], budget_ma=10)
