import json
from dataclasses import replace

import numpy as np
import pytest

from three_phase_fault import Network, Relay, Source, load_network
from three_phase_fault.sequences import A, phase_to_sequence, sequence_to_phase


def test_known_transform_and_round_trip():
    np.testing.assert_allclose(phase_to_sequence([1, A**2, A]), [0, 1, 0], atol=1e-15)
    np.testing.assert_allclose(phase_to_sequence([1, A, A**2]), [0, 0, 1], atol=1e-15)
    np.testing.assert_allclose(phase_to_sequence([1, 1, 1]), [1, 0, 0], atol=1e-15)
    rng = np.random.default_rng(2)
    for _ in range(100):
        abc = rng.normal(size=3) + 1j * rng.normal(size=3)
        np.testing.assert_allclose(sequence_to_phase(phase_to_sequence(abc)), abc, atol=1e-14)
        assert sum(abs(abc) ** 2) == pytest.approx(3 * sum(abs(phase_to_sequence(abc)) ** 2))


@pytest.mark.parametrize("bad", [[1, 2], [1, 2, float("nan")], [[1, 2, 3]]])
def test_bad_transform(bad):
    with pytest.raises(ValueError):
        phase_to_sequence(bad)


def test_relay_known_timing_and_time_dial():
    # IEC standard inverse: 10 x pickup, dial .1, t = 0.2970598624 s.
    relay = Relay(100, 0.1)
    check = relay.check(1000, 0.3)
    assert check["picked_up"] and check["meets_deadline"]
    assert check["trip_time_s"] == pytest.approx(0.2970598624)
    assert check["maximum_time_dial"] == pytest.approx(0.100989745822)
    assert Relay(100, 0.2).check(1000)["trip_time_s"] == pytest.approx(2 * check["trip_time_s"])
    assert not relay.check(1000, 0.2)["meets_deadline"]


@pytest.mark.parametrize("current", [0, 99, 100])
def test_relay_does_not_trip_at_or_below_pickup(current):
    check = Relay(100).check(current)
    assert check["trip_time_s"] is None
    assert check["maximum_time_dial"] is None
    assert not check["picked_up"] and not check["meets_deadline"]


@pytest.mark.parametrize("pickup,dial", [(0, 0.1), (100, 0), (-1, 0.1), (float("inf"), 0.1)])
def test_bad_relay(pickup, dial):
    with pytest.raises(ValueError):
        Relay(pickup, dial)


def test_bad_relay_measurement_and_deadline():
    for current, deadline in [(float("nan"), 1), (1000, 0)]:
        with pytest.raises(ValueError):
            Relay(100).check(current, deadline)


@pytest.mark.parametrize(
    "changes",
    [
        {"buses": ()},
        {"buses": ("x", "x")},
        {"buses": (2,)},
        {"base_mva": 0},
        {"frequency_hz": -60},
        {"base_kv_ll": float("inf")},
        {"prefault_voltage": 0},
        {"sources": ()},
        {"sources": (Source("s", "missing", 0.1j, 0.1j, 0.1j),)},
        {"sources": (Source("s", "supply", 0.1j, -0.1j, 0.1j),)},
        {"buses": ("supply", "plant", "workshop", "island")},
    ],
)
def test_network_validation(changes):
    with pytest.raises(ValueError):
        replace(load_network("examples/feeder.json"), **changes)


def test_element_validation():
    net = load_network("examples/feeder.json")
    for branch in [
        replace(net.branches[0], name="grid"),
        replace(net.branches[0], from_bus="plant"),
        replace(net.branches[0], z1=0),
    ]:
        with pytest.raises(ValueError):
            replace(net, branches=(branch,))
    with pytest.raises(ValueError):
        Network(("bus",), (), (Source("s", "bus", 0.1j, 0.1j, 0.1j),), True, 10)


@pytest.mark.parametrize("value", ["0.1j", [1], [True, 0], [0, "bad"], None])
def test_json_complex_validation(tmp_path, value):
    data = json.loads(open("examples/feeder.json").read())
    data["sources"][0]["z1"] = value
    path = tmp_path / "network.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_network(path)


def test_json_unknown_fields(tmp_path):
    path = tmp_path / "network.json"
    path.write_text('{"voltage": 10}')
    with pytest.raises(ValueError, match="Unknown"):
        load_network(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"buses": "supply"},
        {"sources": {}},
        {"branches": None},
        {"sources": ["grid"]},
        {"sources": [{"bus": "supply"}]},
    ],
)
def test_json_structure_rejected(tmp_path, changes):
    data = json.loads(open("examples/feeder.json").read())
    data.update(changes)
    path = tmp_path / "network.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_network(path)


def test_json_required_fields(tmp_path):
    path = tmp_path / "network.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="Missing network fields"):
        load_network(path)
