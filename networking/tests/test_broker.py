"""Integration with the real containerised TLS broker, including reconnects."""
import json
import os
from pathlib import Path
import ssl
import subprocess
import threading
import time
import pytest
from networking.mqtt import Store, Subscriber, sample, tls_client

pytestmark = pytest.mark.skipif(os.getenv('DESK_BROKER') != '1', reason='CI owns Compose broker')
COMPOSE = ['docker', 'compose', '-f', 'networking/compose.yml']


def until(predicate, seconds=15):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(.05)
    assert predicate(), 'condition did not become true before deadline'


def test_tls_broker_ingestion_disconnect_reconnect_and_last_will(tmp_path):
    ca = 'networking/build/certs/ca.crt'
    store = Store(tmp_path/'room.sqlite3')
    sub = Subscriber(store, ca)
    publisher = tls_client(ca, 'test-node', status='desk/000000000001/status')
    observed = []
    watcher = tls_client(ca, 'status-reader')
    watcher.on_connect = lambda client, *args: client.subscribe('desk/000000000001/status', qos=1)
    watcher.on_message = lambda client, userdata, message: observed.append(message.payload)
    try:
        sub.start()
        assert sub.ready.wait(15)
        watcher.connect('localhost', 8883, 5); watcher.loop_start()
        publisher.connect('localhost', 8883, 5); publisher.loop_start()
        batch = sample()
        info = publisher.publish('desk/000000000001/readings', json.dumps(batch), qos=1)
        info.wait_for_publish(5)
        until(lambda: len(store.readings(batch['device'])) == 1)
        publisher.publish('desk/000000000001/readings', '{', qos=1).wait_for_publish(5)
        until(lambda: store.rejected == 1)
        subprocess.run(COMPOSE+['stop', 'broker'], check=True, capture_output=True)
        until(lambda: not sub.ready.is_set())
        subprocess.run(COMPOSE+['start', 'broker'], check=True, capture_output=True)
        until(lambda: sub.connections >= 2 and sub.ready.is_set(), 25)
        batch['readings'][0]['sequence'] = 2
        publisher.publish('desk/000000000001/readings', json.dumps(batch), qos=1).wait_for_publish(15)
        until(lambda: len(store.readings(batch['device'])) == 2)
        # Close TCP without MQTT DISCONNECT: broker must emit retained last will.
        publisher.reconnect_on_failure = False
        sock = publisher.socket()
        assert sock
        import socket
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()
        until(lambda: b'offline' in observed)
    finally:
        publisher.disconnect(); publisher.loop_stop()
        watcher.disconnect(); watcher.loop_stop()
        sub.close(); store.close()
        subprocess.run(COMPOSE+['start', 'broker'], capture_output=True, check=False)


def test_certificate_rejection():
    import socket
    context = ssl.create_default_context()  # system trust must reject the demo CA
    with socket.create_connection(('127.0.0.1', 8883), timeout=2) as raw:
        with pytest.raises(ssl.SSLCertVerificationError):
            context.wrap_socket(raw, server_hostname='localhost')
    context = ssl.create_default_context(cafile='networking/build/certs/ca.crt')
    with socket.create_connection(('127.0.0.1', 8883), timeout=2) as raw:
        with pytest.raises(ssl.SSLCertVerificationError):
            context.wrap_socket(raw, server_hostname='wrong.example.invalid')
