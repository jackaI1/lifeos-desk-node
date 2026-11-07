import json
import pytest
from network_lab.links import Manager,android_measurements,channel,decode,encode


def test_real_udp_failover_duplicate_and_crc():
    with channel([0,None,None,0,0]) as a,channel([.001]*8) as b:
        manager=Manager(dict(cellular=a,leo=b),timeout=.03)
        manager.probe('cellular');manager.probe('leo')
        assert manager.select()=='cellular'
        manager.probe('cellular');manager.probe('leo')
        assert manager.select()=='leo'
        assert manager.send(b'sensor reading',duplicate=True)==b'sensor reading'
        assert len(manager.delivered)==1
    with pytest.raises(ValueError):decode(encode(1,b'x')[:-1]+b'\x00')


def test_all_links_down():
    with channel([None]*3) as a,channel([None]*3) as b:
        manager=Manager(dict(cellular=a,leo=b),timeout=.01)
        with pytest.raises(TimeoutError):manager.send(b'test',duplicate=True)


def test_android_schema(tmp_path):
    path=tmp_path/'phone.jsonl';path.write_text(json.dumps(dict(transport='cellular',rtt_ms=42.5))+'\n')
    assert android_measurements(path)[0]['rtt_ms']==42.5
    path.write_text(json.dumps(dict(transport='unknown',rtt_ms=-1)))
    with pytest.raises(ValueError):android_measurements(path)
