import json
from can_monitor.replay import replay
from can_monitor.monitor import make_frame


def test_replay_reports_errors_and_rates(tmp_path):
    frames = [make_frame(20, 0), make_frame(21, 2)]
    path = tmp_path / 'frames.jsonl'
    path.write_text(''.join(json.dumps({'time': i, 'id': f.arbitration_id, 'data': f.data.hex(), 'fd': f.is_fd}) + '\n' for i, f in enumerate(frames)))
    result = replay(path)
    assert result['frames'][1]['errors'] == ['counter']
    assert result['rates']['0x100'] == 1


def test_generator_covers_faults_and_fd(tmp_path):
    from can_monitor.replay import generate
    path = tmp_path / 'sample.jsonl'
    generate(path, faults=True)
    result = replay(path, tail=3)
    errors = {e for row in result['frames'] for e in row['errors']}
    assert {'length', 'unknown_id', 'checksum', 'counter'} <= errors
    assert result['summary']['outputs']['fault']
    assert result['summary']['silent'] == ['0x100', '0x101']
    assert result['summary']['rates']['0x101']['frames'] == 3


def test_replay_rejects_bad_timestamps_and_oversize(tmp_path):
    import pytest
    for bad in [dict(time=-1, id=256, data='00'), dict(time=0, id=256, data='00'*65)]:
        path = tmp_path / 'bad.jsonl'
        path.write_text(json.dumps(bad)+'\n')
        with pytest.raises(ValueError): replay(path)


def test_socketcan_replay(tmp_path):
    import os
    import pytest
    from can_monitor.replay import generate
    channel = os.environ.get('DESK_VCAN')
    if not channel:
        pytest.skip('Linux vcan integration enabled by DESK_VCAN')
    path = tmp_path / 'recording.jsonl'
    generate(path)
    report = replay(path, interface='socketcan', channel=channel)
    assert not any(row['errors'] for row in report['frames'])
    assert report['summary']['rates']['0x101']['frames'] == 3
    assert report['summary']['rates']['0x100']['hz'] == 10
