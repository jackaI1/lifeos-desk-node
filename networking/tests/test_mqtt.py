import json
import threading
import urllib.request
import pytest
from networking.mqtt import Store, api, sample


def test_schema_dedup_storage_and_real_read_api(tmp_path):
    store = Store(tmp_path/'room.sqlite3')
    batch = sample()
    topic = f'desk/{batch["device"]}/readings'
    try:
        for _ in range(2): assert store.ingest(topic, json.dumps(batch).encode())
        assert len(store.readings(batch['device'])) == 1
        server = api(store, port=0)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/v1/readings/{batch["device"]}?limit=1') as response:
                assert json.load(response)[0]['temperature_mc'] == 21500
        finally:
            server.shutdown(); thread.join(timeout=2); server.server_close()
            assert not thread.is_alive()
    finally: store.close()


@pytest.mark.parametrize('fault', ['json', 'topic', 'range', 'identity', 'size', 'nan', 'type', 'reused'])
def test_rejects_malformed_batches(fault):
    store = Store(':memory:')
    batch = sample()
    topic = f'desk/{batch["device"]}/readings'
    if fault == 'topic': topic = 'desk/+/readings'
    if fault == 'range': batch['readings'][0]['temperature_mc'] = 125001
    if fault == 'identity': batch['device'] = '000000000002'
    if fault == 'nan': batch['readings'][0]['humidity_mpermil'] = float('nan')
    if fault == 'type': batch['readings'][0]['sequence'] = True
    if fault == 'reused':
        assert store.ingest(topic, json.dumps(batch).encode())
        batch['readings'][0]['temperature_mc'] += 1
    payload = b'{' if fault == 'json' else b' '*16385 if fault == 'size' else json.dumps(batch).encode()
    try:
        assert not store.ingest(topic, payload)
        assert store.rejected == 1
    finally: store.close()
