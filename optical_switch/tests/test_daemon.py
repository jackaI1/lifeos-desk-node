from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import time


@contextmanager
def daemon(path):
    started=time.time()
    process=subprocess.Popen(['optical_switch/build/desk-switch','0',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        line=process.stdout.readline()
        assert line.startswith('PORT '),(line,process.stderr.read(2000))
        port=int(line.split()[1])
        (path.parent/'owned-resource.json').write_text(json.dumps(dict(owner='optical_switch pytest',pid=process.pid,started=started,port=port,cleanup=f'kill -TERM {process.pid}')))
        yield port
    finally:
        if process.poll() is None: process.terminate()
        _,err=process.communicate(timeout=5)
        assert process.returncode==0,err
        assert process.poll() is not None


def command(port,text):
    with socket.create_connection(('127.0.0.1',port),timeout=2) as sock:
        sock.settimeout(2);sock.sendall(text);return sock.recv(128).decode()


def test_socket_protocol_watchdog_and_atomic_restart(tmp_path):
    path=tmp_path/'switch.state'
    with daemon(path) as port:
        assert command(port,b'CONNECT 1 2\n')=='OK\n'
        assert command(port,b'CONNECT 1 3\n')=='ERR\n'
        for data in [b'CONNECT 0 2\n',b'STATUS 17\n',b'CONNECT 1 2 extra\n',b'X'*100+b'\n',b'STATUS 1\x00\n']:
            assert command(port,data).startswith('ERR')
        # Reconnect to a fresh pair and acknowledge the simulated hardware.
        assert command(port,b'CONNECT 3 4\n')=='OK\n'
        assert command(port,b'ACK 3\n')=='OK\n';assert command(port,b'ACK 4\n')=='OK\n'
        time.sleep(.3)
        assert 'FAULT 1' in command(port,b'STATUS 1\n')
        assert 'PEER 4 FAULT 0' in command(port,b'STATUS 3\n')
    assert len(path.read_bytes())==41
    with daemon(path) as port:
        assert 'PEER 4 FAULT 0' in command(port,b'STATUS 3\n')
        assert 'FAULT 1' in command(port,b'STATUS 1\n')
        assert command(port,b'DISCONNECT 1\n')=='OK\n'
        assert 'PEER 0 FAULT 0' in command(port,b'STATUS 2\n')
    path.write_bytes(b'corrupt')
    result=subprocess.run(['optical_switch/build/desk-switch','0',str(path)],capture_output=True,timeout=2)
    assert result.returncode==3
