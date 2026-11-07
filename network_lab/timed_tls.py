"""Two TLS layers and an RTT-bit reconciliation experiment, not a key-entropy claim."""
from contextlib import contextmanager
import hashlib
import json
import math
import socket
import socketserver
import ssl
import struct
import threading
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def exact(sock,size):
    data=bytearray()
    while len(data)<size:
        part=sock.recv(size-len(data))
        if not part:raise EOFError('TLS peer closed')
        data.extend(part)
    return bytes(data)


class Nested:
    """Inner TLS uses MemoryBIO; records travel inside the outer TLS socket."""
    def __init__(self,outer,context,*,server=False,hostname='localhost'):
        self.outer=outer;self.incoming=ssl.MemoryBIO();self.outgoing=ssl.MemoryBIO()
        self.inner=context.wrap_bio(self.incoming,self.outgoing,server_side=server,server_hostname=None if server else hostname)
        while True:
            try:self.inner.do_handshake();self.flush();break
            except ssl.SSLWantReadError:self.pump()

    def flush(self):
        while self.outgoing.pending:
            data=self.outgoing.read(16384);self.outer.sendall(struct.pack('!I',len(data))+data)

    def pump(self):
        self.flush();size=int.from_bytes(exact(self.outer,4),'big')
        if not 0<size<=16384:raise ValueError('oversize inner TLS record')
        self.incoming.write(exact(self.outer,size))

    def write(self,data):
        if len(data)>8192:raise ValueError('application packet exceeds 8192 bytes')
        framed=struct.pack('!I',len(data))+data
        while framed:
            try:written=self.inner.write(framed);framed=framed[written:];self.flush()
            except ssl.SSLWantReadError:self.pump()

    def read_exact(self,size):
        data=bytearray()
        while len(data)<size:
            try:
                part=self.inner.read(size-len(data))
                if not part:raise EOFError('inner TLS closed')
                data.extend(part)
            except ssl.SSLWantReadError:self.pump()
        return bytes(data)

    def read(self):
        size=int.from_bytes(self.read_exact(4),'big')
        if size>8192:raise ValueError('oversize application packet')
        return self.read_exact(size)


def contexts(cert,key,ca):
    server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server.minimum_version=ssl.TLSVersion.TLSv1_2;server.load_cert_chain(cert,key)
    client=ssl.create_default_context(cafile=ca)
    return server,client


@contextmanager
def node(server_context,host='127.0.0.1',port=0):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(2)
            try:
                with server_context.wrap_socket(self.request,server_side=True) as outer:
                    connection=Nested(outer,server_context,server=True)
                    while True:
                        data=connection.read();request=json.loads(data)
                        if request.get('operation')=='close':break
                        if request.get('operation')!='probe' or type(request.get('sequence')) is not int:raise ValueError('bad probe')
                        connection.write(json.dumps(dict(sequence=request['sequence'],received_ns=time.monotonic_ns())).encode())
            except (OSError,EOFError,ValueError):pass
    class Server(socketserver.ThreadingTCPServer):daemon_threads=False
    with Server((host,port),Handler) as server:
        worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});worker.start()
        try:yield server.server_address
        finally:
            server.shutdown();worker.join(timeout=3)
            if worker.is_alive():raise RuntimeError('TLS node failed to stop')


def probe(address,context,count=32):
    if not 8<=count<=256:raise ValueError('probe count must be 8..256')
    readings=[]
    with socket.create_connection(address,timeout=2) as raw:
        with context.wrap_socket(raw,server_hostname='localhost') as outer:
            inner=Nested(outer,context)
            for sequence in range(count):
                start=time.monotonic_ns();inner.write(json.dumps(dict(operation='probe',sequence=sequence)).encode());reply=json.loads(inner.read())
                if reply['sequence']!=sequence:raise ValueError('reordered probe')
                readings.append((time.monotonic_ns()-start)/1e6)
            inner.write(b'{"operation":"close"}')
            assert outer.version() and inner.inner.version()
    return readings


def bits(samples,threshold,guard=.1):
    if not samples or not all(math.isfinite(x) and x>=0 for x in samples):raise ValueError('invalid RTT samples')
    return {i:int(value>threshold) for i,value in enumerate(samples) if abs(value-threshold)>guard}


def syndrome(block):
    if len(block)!=7 or any(x not in (0,1) for x in block):raise ValueError('seven bits required')
    value=0
    for i,bit in enumerate(block,1):
        if bit:value^=i
    return value


def reconcile(reference,peer):
    """Hamming syndrome corrects at most one differing bit per seven positions.

    Syndrome is public helper data and leaks information. The final digest is a
    confirmation, not a proof of secret entropy or a complete key-agreement scheme.
    """
    if len(reference)!=len(peer) or not reference or len(reference)%7:raise ValueError('equal multiples of seven required')
    corrected=list(peer)
    for offset in range(0,len(peer),7):
        index=syndrome(reference[offset:offset+7])^syndrome(peer[offset:offset+7])
        if index:corrected[offset+index-1]^=1
    if corrected!=list(reference):raise ValueError('too many mismatches; abort experiment')
    return hashlib.sha256(bytes(corrected)).digest()


def encrypt_experiment(key,payload):
    # Random nonce for the AES-GCM demonstration; nested TLS independently
    # authenticates the transport. Never treat RTT-derived bits as production keys.
    import os
    nonce=os.urandom(12);return nonce+AESGCM(key).encrypt(nonce,payload,b'desk-rtt-lab-v1')


def decrypt_experiment(key,packet):return AESGCM(key).decrypt(packet[:12],packet[12:],b'desk-rtt-lab-v1')


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cert',required=True);p.add_argument('--key',required=True)
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8443)
    a=p.parse_args();context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(a.cert,a.key)
    try:
        with node(context,a.host,a.port) as address:
            print(f'Nested TLS node listening on {address}',flush=True)
            while True:time.sleep(1)
    except KeyboardInterrupt:pass

if __name__=='__main__':main()
