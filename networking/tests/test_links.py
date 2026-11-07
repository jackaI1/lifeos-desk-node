import io
import json
import time
import pytest
from networking.links import Link, poll, simulated_node
from networking.snmp import BASE, serve, values


def test_loss_and_latency_alarms_with_hysteresis():
    link = Link(window=3, min_samples=3)
    assert not link.observe(10)['alarm']
    assert not link.observe(10)['alarm']
    assert link.observe(None)['alarm']
    for _ in range(4): assert link.observe(10)['alarm']
    assert not link.observe(10)['alarm']
    for _ in range(3): link.observe(101)
    assert link.alarm


def test_threshold_boundaries():
    link = Link(window=5, min_samples=1)
    assert not link.observe(100)['alarm']
    for _ in range(3): link.observe(0)
    assert link.observe(None)['loss_percent'] == 20
    assert link.alarm
    with pytest.raises(ValueError): link.observe(float('nan'))


def test_real_tcp_loss_timeout_and_release():
    with simulated_node([0, None, .1, 0]) as address:
        assert poll(*address) is not None
        assert poll(*address) is None
        assert poll(*address, timeout=.02) is None
        assert poll(*address) is not None
    assert poll(*address, timeout=.02) is None


def test_snmp_backend_get_walk_and_stale_alarm(tmp_path):
    path = tmp_path/'snapshot.json'
    path.write_text(json.dumps(dict(status=1, latency_ms=25, loss_percent=20, alarm=1, updated=time.time())))
    out = io.StringIO()
    serve(path, io.StringIO(f'PING\nget\n{BASE}.2.0\ngetnext\n{BASE}\nget\n{BASE}.99.0\n'), out)
    assert out.getvalue() == f'PONG\n{BASE}.2.0\ninteger\n25\n{BASE}.1.0\ninteger\n1\nNONE\n'
    assert values(path, now=time.time()+6)[BASE+'.4.0'] == 1
    assert values(path, now=time.time()+6)[BASE+'.1.0'] == 0
