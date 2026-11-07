import can
import pytest
from crccheck.crc import Crc8SaeJ1850
from can_monitor.monitor import Monitor, checksum, crc8, make_frame


@pytest.mark.parametrize('fd', [False, True])
@pytest.mark.parametrize('temperature', [-40, 0, 21.3, 200])
def test_round_trip_physical_units(fd, temperature):
    f = make_frame(temperature, 255, fd=fd, setpoint=24, heater=75, fan=10)
    m = Monitor(expected=(f.arbitration_id,))
    result = m.process(f, 0)
    assert not result['errors']
    assert result['signals']['Temperature'] == pytest.approx(temperature)
    assert result['signals']['Setpoint'] == 24
    assert result['signals']['Heater'] == 75
    assert len(f.data) == (64 if fd else 8)
    assert not m.process(make_frame(20, 0, fd=fd), .1)['errors']


def test_crc_independent_reference_and_standard_vector():
    assert crc8(b'123456789') == 0x4b
    assert crc8(bytes(range(64))) == Crc8SaeJ1850.calc(bytes(range(64)))
    f = make_frame(20, 0)
    before = checksum(f)
    f.arbitration_id = 0x101
    assert checksum(f) != before


@pytest.mark.parametrize('fault', ['checksum', 'length', 'dlc', 'unknown_id', 'extended', 'remote', 'error', 'fd', 'classic_brs', 'brs', 'counter', 'range'])
def test_each_fault_forces_safe_outputs(fault):
    m = Monitor()
    assert m.process(make_frame(19, 0, heater=90, fan=80), 0)['safe']['heater'] == 90
    f = make_frame(20, 1, fd=fault == 'brs')
    if fault == 'checksum': f.data[0] ^= 1
    elif fault == 'length': f.data = f.data[:-1]
    elif fault == 'dlc': f.dlc = 7
    elif fault == 'unknown_id': f.arbitration_id = 0x777
    elif fault == 'extended': f.is_extended_id = True
    elif fault == 'remote': f.is_remote_frame = True
    elif fault == 'error': f.is_error_frame = True
    elif fault == 'fd': f.is_fd = True
    elif fault == 'brs': f.bitrate_switch = False
    elif fault == 'classic_brs': f.bitrate_switch = True
    elif fault == 'counter': f = make_frame(20, 3)
    elif fault == 'range':
        f.data[5] = 101
        f.data[-1] = checksum(f)
    result = m.process(f, .1)
    assert result['errors']
    assert result['signals'] == {}
    assert result['safe'] == dict(fault=True, heater=0, fan=0)


def test_gap_resynchronises_without_accepting_gap_frame():
    m = Monitor()
    m.process(make_frame(20, 0), 0)
    assert m.process(make_frame(20, 2, heater=90), .1)['errors'] == ['counter']
    assert m.process(make_frame(20, 3, heater=10), .2)['safe']['heater'] == 10


def test_bad_crc_does_not_poison_counter_or_refresh_deadline():
    m = Monitor(timeout=1)
    m.process(make_frame(20, 0), 0)
    bad = make_frame(20, 90)
    bad.data[0] ^= 1
    m.process(bad, .9)
    assert m.silent(1) == [0x100]
    assert not m.process(make_frame(20, 1), 1.1)['errors']


def test_repeated_counter_rejected_and_startup_silence_detected():
    m = Monitor(timeout=1)
    assert m.outputs(0)['fault']
    assert m.silent(1) == [0x100]
    m.process(make_frame(20, 0, heater=90), 1)
    assert m.process(make_frame(20, 0, heater=90), 1.1)['errors'] == ['counter']
    assert m.outputs(2)['heater'] == 0


def test_deadline_safe_and_bounded_rate_statistics():
    m = Monitor(timeout=.5)
    for i in range(1000):
        m.process(make_frame(20, i % 256, heater=45), i / 10)
    assert m.rates()[0x100] == pytest.approx(10)
    assert m.times[0x100].count == 1000
    assert m.outputs(100.4)['heater'] == 0
    assert m.summary(100.4)['silent'] == ['0x100']


@pytest.mark.parametrize('now', [-1, float('nan'), float('inf')])
def test_invalid_clock(now):
    with pytest.raises(ValueError): Monitor().process(make_frame(20, 0), now)


def test_fd_virtual_bus_and_rates():
    with can.Bus(interface='virtual', channel='desk-test', receive_own_messages=True, ignore_config=True) as bus:
        bus.send(make_frame(22, 0, fd=True))
        f = bus.recv(1)
        assert f.is_fd and f.bitrate_switch and len(f.data) == 64
        m = Monitor()
        assert not m.process(f, 0)['errors']
        m.process(make_frame(23, 1, fd=True), 1)
        assert m.rates()[0x101] == 1
