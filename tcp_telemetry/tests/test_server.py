"""Actual concurrent Winsock/POSIX clients, malformed and slow peers."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import zlib
import pytest


def frame(payload):
    data=struct.pack('!H',len(payload))+payload
    return data+struct.pack('!I',zlib.crc32(data))


@contextmanager
def server(metadata_path):
    binary=os.getenv('DESK_TCP_BINARY','tcp_telemetry/build/desk-tcp')
    started=time.time()
    process=subprocess.Popen([binary,'0','4000'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        line=process.stdout.readline()
        assert line.startswith('PORT '), (line,process.stderr.read(2000))
        port=int(line.split()[1])
        import json
        metadata_path.write_text(json.dumps(dict(owner='TCP telemetry stress test',pid=process.pid,started=started,port=port,cleanup=f'terminate PID {process.pid} and wait')))
        yield port
        out,err=process.communicate(timeout=8)
        assert process.returncode==0,(out,err)
        assert 'accepted=' in out
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        process.stdout.close();process.stderr.close()


def exchange(port,payload,*,slow=False,truncated=False):
    with socket.create_connection(('127.0.0.1',port),timeout=2) as sock:
        sock.settimeout(2)
        if slow:
            sock.sendall(payload[:1]);time.sleep(.3)
            return sock.recv(20)
        sock.sendall(payload)
        if truncated: sock.shutdown(socket.SHUT_WR)
        result=b''
        while len(result)<14:
            try: data=sock.recv(14-len(result))
            except ConnectionResetError: break
            if not data: break
            result+=data
        return result


def test_many_clients_corruption_truncation_and_slow_connections(tmp_path):
    good=frame(struct.pack('!iI',21500,50000))
    with server(tmp_path/'owned-resource.json') as port:
        with ThreadPoolExecutor(max_workers=16) as pool:
            results=list(pool.map(lambda _:exchange(port,good),range(100)))
        assert results==[good]*100
        assert not exchange(port,good[:-1]+bytes([good[-1]^1]))
        assert not exchange(port,good[:5],truncated=True)
        assert not exchange(port,b'\xff\xff')
        assert not exchange(port,frame(b'x'))
        assert not exchange(port,frame(struct.pack('!iI',21500,100001)))
        assert not exchange(port,good,slow=True)
        assert exchange(port,good)==good
