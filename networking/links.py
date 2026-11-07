"""Poll desk-node TCP endpoints and publish bounded sliding-window health."""
import argparse
from collections import deque
from contextlib import contextmanager
import json
import math
import socket
import socketserver
import threading
import time
import uuid
from pathlib import Path
from .lifecycle import serving


class Link:
    def __init__(self, window=10, latency_ms=100, loss_percent=20, min_samples=3):
        if not 1 <= min_samples <= window <= 10000 or latency_ms <= 0 or not 0 <= loss_percent <= 100:
            raise ValueError('invalid link thresholds')
        self.samples = deque(maxlen=window)
        self.latency_ms, self.loss_percent, self.min_samples = latency_ms, loss_percent, min_samples
        self.alarm = False
        self.recovery = 0

    def observe(self, latency):
        if latency is not None and (not math.isfinite(latency) or latency < 0):
            raise ValueError('invalid latency')
        self.samples.append(latency)
        result = self.snapshot()
        degraded = result['loss_percent'] >= self.loss_percent or result['latency_ms'] > self.latency_ms
        if len(self.samples) >= self.min_samples and degraded:
            self.alarm, self.recovery = True, 0
        elif len(self.samples) >= self.min_samples:
            self.recovery += 1
            if self.recovery >= 3:
                self.alarm = False
        return self.snapshot()

    def snapshot(self):
        good = [x for x in self.samples if x is not None]
        return dict(status=int(bool(self.samples) and self.samples[-1] is not None),
                    latency_ms=sum(good) / len(good) if good else 0,
                    loss_percent=100 * (len(self.samples)-len(good))/len(self.samples) if self.samples else 0,
                    alarm=int(self.alarm), samples=len(self.samples))


def poll(host, port, timeout=.5):
    token = uuid.uuid4().hex[:8]
    expected = f'DESK/1 PONG {token}\n'.encode()
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(f'DESK/1 PING {token}\n'.encode())
            data = b''
            deadline = start + timeout
            while len(data) < len(expected):
                remaining = deadline - time.monotonic()
                if remaining <= 0: return None
                sock.settimeout(remaining)
                part = sock.recv(len(expected) - len(data))
                if not part: return None
                data += part
            return (time.monotonic()-start)*1000 if data == expected else None
    except OSError:
        return None


@contextmanager
def simulated_node(pattern=(0,), *, host='127.0.0.1'):
    """Delays in seconds; None closes a reply to model a lost application probe."""
    sequence = iter(pattern)
    lock = threading.Lock()
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            with lock:
                delay = next(sequence, 0)
            self.request.settimeout(.5)
            try:
                data = self.request.recv(64)
                if delay is None: return
                if not 0 <= delay <= 1: raise ValueError('simulation delay out of range')
                time.sleep(delay)
                if data.startswith(b'DESK/1 PING ') and data.endswith(b'\n') and len(data) == 21:
                    self.request.sendall(data.replace(b'PING', b'PONG'))
            except OSError:
                pass
    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = False
        block_on_close = True
    with Server((host, 0), Handler) as server:
        with serving(server, 'simulated ESP32 TCP node') as address:
            yield address


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8092)
    p.add_argument('--output', default='/tmp/desk-link.json')
    p.add_argument('--count', type=int, default=10)
    p.add_argument('--interval', type=float, default=1)
    p.add_argument('--demo', action='store_true')
    a = p.parse_args()
    if not 1 <= a.count <= 100000 or not .01 <= a.interval <= 3600: p.error('invalid polling bounds')
    def run(address):
        link = Link()
        for _ in range(a.count):
            result = link.observe(poll(*address))
            result['updated'] = time.time()
            output = Path(a.output)
            temporary = output.with_suffix('.tmp')
            temporary.write_text(json.dumps(result)+'\n')
            temporary.replace(output)
            print(json.dumps(result), flush=True)
            time.sleep(a.interval)
    if a.demo:
        with simulated_node([0, 0, None, .15, None, 0, 0, 0, 0, 0]) as address: run(address)
    else:
        run((a.host, a.port))


if __name__ == '__main__': main()
