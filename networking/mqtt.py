"""Certificate-checked MQTT transport into the existing desk readings database."""
import argparse
import json
import re
import sqlite3
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import paho.mqtt.client as mqtt
from firmware.tools.desk_api import Gateway, DemoLifeOS

TOPIC = re.compile(r'desk/([0-9a-f]{12})/readings')


class Store:
    def __init__(self, path):
        self.gateway = Gateway(path, DemoLifeOS())
        self.accepted = self.rejected = 0

    def ingest(self, topic, payload):
        try:
            if len(payload) > 16384: raise ValueError('oversized batch')
            match = TOPIC.fullmatch(topic)
            if not match: raise ValueError('invalid topic')
            batch = json.loads(payload)
            if batch['device'] != match[1]: raise ValueError('device does not match topic')
            result = self.gateway.ingest(batch)
            self.accepted += result['accepted']
            return True
        except (ValueError, KeyError, TypeError, UnicodeError):
            self.rejected += 1
            return False

    def readings(self, device, limit=100):
        if not re.fullmatch('[0-9a-f]{12}', device) or not 1 <= limit <= 1000:
            raise ValueError('invalid device or limit')
        with self.gateway.lock:
            cursor = self.gateway.db.execute('SELECT session,sequence,timestamp,temperature_mc,humidity_mpermil FROM readings WHERE device=? ORDER BY timestamp DESC,sequence DESC LIMIT ?', (device, limit))
            keys = [x[0] for x in cursor.description]
            return [dict(zip(keys, row)) for row in cursor]

    def close(self): self.gateway.close()


def tls_client(ca, identity, *, status=None):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=identity)
    client.tls_set_context(ssl.create_default_context(cafile=ca))
    client.reconnect_delay_set(min_delay=1, max_delay=8)
    client.max_queued_messages_set(64)
    if status:
        client.will_set(status, 'offline', qos=1, retain=True)
    return client


class Subscriber:
    def __init__(self, store, ca, *, identity='desk-gateway'):
        self.store = store
        self.ready = threading.Event()
        self.client = tls_client(ca, identity, status='desk/gateway/status')
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.connections = 0

    def on_connect(self, client, userdata, flags, reason, properties):
        if reason == 0:
            self.connections += 1
            client.subscribe('desk/+/readings', qos=1)
            client.publish('desk/gateway/status', 'online', qos=1, retain=True)
            # Ready is set after SUBACK so tests and senders cannot race subscription.
            client.on_subscribe = lambda *args: self.ready.set()

    def on_disconnect(self, client, userdata, flags, reason, properties): self.ready.clear()

    def on_message(self, client, userdata, message):
        self.store.ingest(message.topic, message.payload)

    def start(self, host='localhost', port=8883):
        self.client.connect_async(host, port, keepalive=5)
        self.client.loop_start()

    def close(self):
        self.client.publish('desk/gateway/status', 'offline', qos=1, retain=True)
        self.client.disconnect()
        self.client.loop_stop()


def api(store, host='127.0.0.1', port=8093):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            parts = parsed.path.strip('/').split('/')
            try:
                if len(parts) != 3 or parts[:2] != ['v1', 'readings']: raise ValueError('unknown path')
                limit = int(parse_qs(parsed.query).get('limit', ['100'])[0])
                data = store.readings(parts[2], limit)
                status = 200
            except (ValueError, TypeError):
                data, status = {'error': 'use /v1/readings/<12 hex device>?limit=1..1000'}, 400
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args): pass
    return ThreadingHTTPServer((host, port), Handler)


def sample():
    return dict(device='000000000001', session='0000000000000001', dropped=0,
        readings=[dict(sequence=1, timestamp=int(time.time()), temperature_mc=21500, humidity_mpermil=48000)])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['gateway', 'publish'])
    p.add_argument('--ca', required=True)
    p.add_argument('--host', default='localhost')
    p.add_argument('--port', type=int, default=8883)
    p.add_argument('--database', default='room.sqlite3')
    p.add_argument('--source', help='JSON batch from the adapter schema; omitted uses labelled synthetic sample')
    a = p.parse_args()
    if a.mode == 'publish':
        from pathlib import Path
        batch = json.loads(Path(a.source).read_text()) if a.source else sample()
        # Validate before sending, using exactly the firmware API schema.
        with sqlite3.connect(':memory:'): pass
        validator = Store(':memory:')
        try:
            topic = f'desk/{batch["device"]}/readings'
            if not validator.ingest(topic, json.dumps(batch).encode()): p.error('invalid sensor batch')
        finally: validator.close()
        client = tls_client(a.ca, 'desk-'+batch['device'], status=f'desk/{batch["device"]}/status')
        try:
            client.connect(a.host, a.port, keepalive=5)
            client.loop_start()
            client.publish(f'desk/{batch["device"]}/status', 'online', qos=1, retain=True).wait_for_publish(5)
            info = client.publish(topic, json.dumps(batch), qos=1)
            info.wait_for_publish(5)
            if not info.is_published(): raise TimeoutError('broker did not acknowledge')
        finally:
            client.publish(f'desk/{batch["device"]}/status', 'offline', qos=1, retain=True)
            client.disconnect()
            client.loop_stop()
    else:
        store = Store(a.database)
        subscriber = Subscriber(store, a.ca)
        server = api(store, host='0.0.0.0')
        try:
            subscriber.start(a.host, a.port)
            server.serve_forever(poll_interval=.1)
        except KeyboardInterrupt: pass
        finally:
            server.server_close()
            subscriber.close()
            store.close()


if __name__ == '__main__': main()
