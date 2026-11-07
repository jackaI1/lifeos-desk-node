import subprocess
from pathlib import Path
import pytest
from network_lab.timed_tls import bits,contexts,decrypt_experiment,encrypt_experiment,node,probe,reconcile,paired_session


def test_actual_double_tls_nodes_exchange_timed_packets(tmp_path):
    subprocess.run(['networking/deploy/certificates.sh',str(tmp_path)],check=True,capture_output=True)
    server,client=contexts(tmp_path/'server.crt',tmp_path/'server.key',tmp_path/'ca.crt')
    with node(server) as first,node(server) as second:
        a=probe(first,client,8);b=probe(second,client,8)
        assert len(a)==len(b)==8
        assert all(x>0 for x in a+b)
        result=paired_session(first,client,count=14)
        assert result['confirmed'] and result['retained_bits']>=7
        assert result['received']=='desk temperature=21.5'
        assert result['outer_tls'] and result['inner_tls']
        # Exercise quantisation on actual packet timings; a stable local link may
        # supply zero usable variation. It never invents entropy from that case.
        threshold=sum(a)/len(a);quantised=bits(a,threshold,guard=0)
        assert set(quantised.values())<={0,1}


def test_guard_bands_reconciliation_and_nested_payload_cipher():
    assert bits([10,20,15],15,guard=1)=={0:0,1:1}
    source=[0,1,1,0,1,0,1]*8;peer=list(source)
    for i in range(0,len(peer),7):peer[i+2]^=1
    key=reconcile(source,peer);packet=encrypt_experiment(key,b'desk temperature 21.5 C')
    assert decrypt_experiment(key,packet)==b'desk temperature 21.5 C'
    peer[0]^=1
    with pytest.raises(ValueError):reconcile(source,peer)
    with pytest.raises(Exception):decrypt_experiment(bytes(32),packet)
