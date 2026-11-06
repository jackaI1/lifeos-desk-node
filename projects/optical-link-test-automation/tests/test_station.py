import math
import pytest
from optical_station.station import Link, MockResource, Laser, PowerMeter, Analyser, clean_readings, run_plan, train_classifier, render_report
from optical_station.fixture import call_fixture
from optical_station.web import create_app


def test_scpi_link_and_failure_injection():
    link = Link(length_km=10, attenuation_db_km=0.2, connector_loss_db=1, splice_loss_db=0.5, noise_dbm=-45, seed=1)
    resource = MockResource(link)
    laser, meter, analyser = Laser(resource), PowerMeter(resource), Analyser(resource)
    laser.configure(1550, 0)
    assert meter.read() == pytest.approx(-3.5, abs=0.2)
    assert analyser.osnr() == pytest.approx(41.5, abs=0.3)
    resource.fail_next = True
    with pytest.raises(TimeoutError): meter.read()
    with pytest.raises(ValueError): resource.write('BAD 1')


def test_cleaning_rejects_dropouts_and_spikes():
    clean = clean_readings([1, 1.1, None, float('nan'), 100, 0.9, 1.0])
    assert len(clean) == 4
    assert max(clean) < 2


def test_plan_sweep_and_limits():
    plan = {'version': 1, 'wavelength_nm': [1550, 1560], 'launch_dbm': [0, 1], 'samples': 5, 'max_loss_db': 5, 'min_osnr_db': 20}
    results = run_plan(plan, MockResource(Link(seed=2)))
    assert len(results) == 4
    assert all(r['status'] == 'pass' for r in results)
    plan['max_loss_db'] = 0.1
    assert all(r['status'] == 'fail' for r in run_plan(plan, MockResource(Link(seed=2))))
    with pytest.raises(ValueError): run_plan({**plan, 'version': 2}, MockResource(Link()))


def test_classifier_and_report():
    model, evaluation = train_classifier()
    assert 0 <= evaluation['accuracy'] <= 1
    assert evaluation['test_count'] > 0
    assert set(model.classes_) == {'pass', 'marginal', 'fail'}
    assert '<html' in render_report([{'status': 'fail', 'wavelength_nm': 1550}])


def test_protobuf_fixture_and_api():
    response = call_fixture('READ_POWER', 1550, 0)
    assert response.ok and math.isfinite(response.value)
    assert not call_fixture('UNKNOWN', 1550, 0).ok
    client = create_app().test_client()
    result = client.post('/api/run', json={})
    assert result.status_code == 200
    assert result.json['results']
    assert client.post('/api/triage', json={'status': 'fail'}).json['advice']


def test_dropouts_and_outliers_are_removed_and_insufficient_data_fails():
    resource = MockResource(Link(seed=2))
    resource.dropout_next = True
    plan = {'version': 1, 'wavelength_nm': [1550], 'launch_dbm': [0], 'samples': 3, 'max_loss_db': 5, 'min_osnr_db': 20}
    assert run_plan(plan, resource)[0]['status'] == 'fail'
    resource = MockResource(Link(seed=2))
    resource.outlier_next = True
    plan['samples'] = 7
    result = run_plan(plan, resource)[0]
    assert result['loss_db'] == pytest.approx(3.5, abs=0.2)
    assert result['valid_power'] < 7


def test_fixture_serialization_and_http_errors():
    from optical_station.fixture import Fixture, Request, Response
    fixture = Fixture(MockResource(Link()))
    payload = Request(operation='READ_OSNR', wavelength_nm=1550, launch_dbm=0).SerializeToString()
    response = Response.FromString(fixture.handle(payload))
    assert response.ok and response.value == pytest.approx(41.5, abs=0.2)
    client = create_app().test_client()
    assert client.post('/api/fixture', data=payload).status_code == 200
    assert client.post('/api/run', json={'plan': {'version': 99}}).status_code == 400
    assert client.get('/dashboard.js').status_code == 200
