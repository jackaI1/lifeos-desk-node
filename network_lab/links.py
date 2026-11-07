"""Replay cellular/LEO-style traces through real UDP links before desk upload."""
from contextlib import contextmanager
from collections import deque
import csv
import json
import math
from pathlib import Path
import socket
import socketserver
import struct
import threading
import time
import zlib
from networking.links import Link


def encode(sequence,payload):
    if len(payload)>512:raise ValueError('payload exceeds 512 bytes')
    body=struct.pack('!I',sequence)+payload
    return body+struct.pack('!I',zlib.crc32(body))


def decode(data):
    if not 8<=len(data)<=520 or zlib.crc32(data[:-4])!=int.from_bytes(data[-4:],'big'):raise ValueError('bad frame')
    return int.from_bytes(data[:4],'big'),data[4:-4]


def trace(path):
    rows=[]
    with open(path,newline='') as stream:
        for row in csv.DictReader(stream):
            delay=float(row['delay_ms']);lost=int(row['outage'])
            if not math.isfinite(delay) or not 0<=delay<=2000 or lost not in (0,1):raise ValueError('invalid trace')
            rows.append(None if lost else delay/1000)
    if not rows:raise ValueError('empty trace')
    return rows


@contextmanager
def channel(delays):
    sequence=iter(delays);lock=threading.Lock()
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            with lock:delay=next(sequence,0)
            data,sock=self.request
            if delay is None:return
            try:
                decode(data)
                time.sleep(delay)
                sock.sendto(data,self.client_address)
            except (OSError,ValueError):pass
    class Server(socketserver.ThreadingUDPServer):
        daemon_threads=False
    with Server(('127.0.0.1',0),Handler) as server:
        worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});worker.start()
        try:yield server.server_address
        finally:
            server.shutdown();worker.join(timeout=3)
            if worker.is_alive():raise RuntimeError('link server failed to stop')


class Manager:
    def __init__(self,addresses,timeout=.1):
        self.addresses=addresses;self.timeout=timeout
        self.windows={name:deque(maxlen=5) for name in addresses}
        self.active=next(iter(addresses));self.sequence=0
        self.health={name:Link() for name in addresses}
        self.delivered=set();self.order=deque(maxlen=1024)

    def probe(self,name,payload=b'probe'):
        start=time.monotonic();message=encode(self.sequence,payload);self.sequence=(self.sequence+1)&0xffffffff
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout);sock.connect(self.addresses[name]);sock.send(message)
            try:
                data=sock.recv(521)
                if data!=message:raise ValueError('wrong reply')
                result=(time.monotonic()-start)*1000
            except (OSError,ValueError):result=None
        self.windows[name].append(result);self.health[name].observe(result);return result

    def score(self,name):
        window=self.windows[name];good=[x for x in window if x is not None]
        return sum(good)/len(good)+500*(len(window)-len(good))/len(window) if window and good else math.inf

    def select(self):
        best=min(self.addresses,key=self.score)
        # Require a 10 ms advantage to avoid switching for tiny fluctuations.
        if self.score(best)+10<self.score(self.active):self.active=best
        return self.active

    def send(self,payload,*,duplicate=False):
        sequence=self.sequence;self.sequence=(self.sequence+1)&0xffffffff
        message=encode(sequence,payload);targets=list(self.addresses) if duplicate else [self.select()]
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout)
            for name in targets:sock.sendto(message,self.addresses[name])
            deadline=time.monotonic()+self.timeout
            while time.monotonic()<deadline:
                sock.settimeout(max(.001,deadline-time.monotonic()))
                try:data,source=sock.recvfrom(521)
                except OSError:break
                if source not in [self.addresses[name] for name in targets]:continue
                try:received,body=decode(data)
                except ValueError:continue
                if received!=sequence or body!=payload:continue
                if received not in self.delivered:
                    if len(self.order)==self.order.maxlen:self.delivered.discard(self.order.popleft())
                    self.order.append(received);self.delivered.add(received)
                    return body
        raise TimeoutError('all selected links lost the message')


def android_measurements(path):
    rows=[json.loads(line) for line in Path(path).read_text().splitlines()]
    if not rows:raise ValueError('empty Android measurement file')
    for row in rows:
        if row['transport'] not in ('cellular','wifi') or type(row['rtt_ms']) not in (int,float) or not math.isfinite(row['rtt_ms']) or not 0<=row['rtt_ms']<=10000:
            raise ValueError('invalid Android measurement')
    return rows


def main():
    base=Path(__file__).with_name('traces')
    with channel(trace(base/'cellular.csv')) as cellular,channel(trace(base/'leo.csv')) as leo:
        manager=Manager(dict(cellular=cellular,leo=leo))
        for _ in range(6):
            rtt={name:manager.probe(name) for name in manager.addresses}
            selected=manager.select();snapshot=manager.health[selected].snapshot();snapshot['updated']=time.time();Path('/tmp/desk-link.json').write_text(json.dumps(snapshot))
            try:result=manager.send(b'desk temperature=21.5',duplicate=any(x is None for x in rtt.values()))
            except TimeoutError:
                print(json.dumps(dict(rtt_ms=rtt,selected=selected,delivered=None,error='all selected links lost this upload')))
                continue
            print(json.dumps(dict(rtt_ms=rtt,selected=selected,delivered=result.decode())))


if __name__=='__main__':main()
