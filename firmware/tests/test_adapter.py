"""Synthetic fixtures only; every socket is closed by its context manager."""
import contextlib
import importlib.util
import json
import os
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone

spec = importlib.util.spec_from_file_location('desk_api', pathlib.Path(__file__).parents[1] / 'tools/desk_api.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

class LifeOSFixture:
    def __init__(self):
        self.notes = {}
        self.fail = False
        self.conflict = False
    def request(self, method, path, data=None):
        if self.fail:
            raise api.UpstreamError('offline')
        if path == '/api/bootstrap':
            return {'records': {'task': [
                {'data': {'title': 'Later task', 'dueDate': '2026-11-06', 'status': 'todo'}},
                {'data': {'title': 'Next deadline', 'dueDate': '2026-11-04', 'dueAt': '2026-11-04T11:00:00-05:00', 'status': 'todo'}},
                {'data': {'title': 'Complete', 'dueDate': '2026-11-04', 'dueAt': '2026-11-04T10:00:00-05:00', 'status': 'complete'}},
            ]}, 'today': {'calendar': {'events': [
                {'isSchool': True, 'title': 'Calculus', 'start': '2026-11-04T10:30:00-05:00', 'end': '2026-11-04T11:30:00-05:00'},
                {'isSchool': True, 'title': 'Past', 'start': '2026-11-03T10:30:00-05:00'},
            ]}}}
        if method == 'GET':
            return {'item': self.notes[path]} if path in self.notes else None
        if self.conflict:
            self.conflict = False
            raise api.ConflictError('version changed')
        self.notes[path] = {'version': data['version']+1, 'data': data['data']}
        return {'item': self.notes[path]}

@contextlib.contextmanager
def running(server):
    port = server.server_port
    started = datetime.now(timezone.utc).isoformat()
    t = threading.Thread(target=server.serve_forever)
    t.start()
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        server.shutdown(); server.server_close(); t.join(timeout=2)
        assert not t.is_alive()
        import socket
        with socket.socket() as s:
            assert s.connect_ex(('127.0.0.1', port)) != 0, 'owned test port still open'
        print(f'Closed test_adapter fixture: PID {os.getpid()}, start {started}, port {port}; cleanup server.shutdown()/server_close()/thread.join(); listener verified closed')

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lifeos = LifeOSFixture()
        self.gateway = api.Gateway(pathlib.Path(self.tmp.name)/'readings.sqlite3', self.lifeos,
            now=lambda: datetime(2026,11,4,15,tzinfo=timezone.utc))
        self.addCleanup(self.gateway.close)
        self.payload = {'device':'aabbccddeeff','session':'0123456789abcdef','dropped':0,'readings':[
            {'sequence':1,'timestamp':0,'temperature_mc':22500,'humidity_mpermil':45000}]}
    def test_selects_earliest_future_class_or_deadline(self):
        event = self.gateway.next_event()['next']
        self.assertEqual(event, {'kind':'class','title':'Calculus','when':'Wed 10:30'})
    def test_missing_or_completed_events_are_not_invented(self):
        self.assertEqual(api.select_next({}, datetime.now(timezone.utc), 'America/Toronto'), {'next':None})
    def test_deadline_precedes_class(self):
        source = self.lifeos.request('GET','/api/bootstrap')
        source['records']['task'][1]['data']['dueAt'] = '2026-11-04T10:15:00-05:00'
        event = api.select_next(source,datetime(2026,11,4,15,tzinfo=timezone.utc),'America/Toronto')['next']
        self.assertEqual(event['kind'],'deadline')
        self.assertEqual(event['title'],'Next deadline')
    def test_date_only_deadline_does_not_invent_cutoff(self):
        source={'records':{'task':[{'data':{'title':'Due today','dueDate':'2026-11-04'}}]}}
        event=api.select_next(source,datetime(2026,11,4,15,tzinfo=timezone.utc),'America/Toronto')['next']
        self.assertEqual(event['when'],'Wed time unknown')
    def test_retry_deduplicates_daily_lifeos_note(self):
        self.assertEqual(self.gateway.ingest(self.payload), {'accepted':1,'last_sequence':1})
        self.gateway.ingest(self.payload)
        note = next(iter(self.lifeos.notes.values()))
        self.assertEqual(len(self.lifeos.notes),1)
        self.assertEqual(note['version'],1)
        self.assertIn('22.500 C',note['data']['text'])
        self.assertIn('unsynchronized',note['data']['text'])
    def test_upstream_failure_keeps_reading_for_later_retry(self):
        self.lifeos.fail = True
        with self.assertRaises(api.UpstreamError): self.gateway.ingest(self.payload)
        self.lifeos.fail = False
        self.gateway.ingest(self.payload)
        self.assertIn('22.500 C',next(iter(self.lifeos.notes.values()))['data']['text'])
    def test_retry_after_restart_preserves_dedup(self):
        self.gateway.ingest(self.payload)
        self.gateway.close()
        self.gateway = api.Gateway(pathlib.Path(self.tmp.name)/'readings.sqlite3',self.lifeos)
        self.addCleanup(self.gateway.close)
        self.gateway.ingest(self.payload)
        self.assertEqual(next(iter(self.lifeos.notes.values()))['version'],1)
    def test_conflict_retries_without_losing_data(self):
        self.lifeos.conflict = True
        self.gateway.ingest(self.payload)
        self.assertEqual(len(self.lifeos.notes),1)
    def test_payload_range_duplicate_and_identity_validation(self):
        for change in [dict(device='../bad'), dict(readings=[]), dict(dropped=-1), dict(dropped=True)]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.gateway.ingest({**self.payload, **change})
        for key,value in [('temperature_mc',126000),('humidity_mpermil',100001),('timestamp',-1),('sequence',True)]:
            body={**self.payload,'readings':[{**self.payload['readings'][0],key:value}]}
            with self.subTest(key=key), self.assertRaises(ValueError): self.gateway.ingest(body)
        with self.assertRaises(ValueError):
            self.gateway.ingest({**self.payload,'readings':self.payload['readings']*2})
        self.assertEqual(len(self.lifeos.notes),0)
    def test_manual_note_edits_are_preserved(self):
        self.gateway.ingest(self.payload)
        note=next(iter(self.lifeos.notes.values()))
        note['data']['text'] += '\nOwner annotation to preserve'
        self.payload['readings'][0]['sequence']=2
        with self.assertRaises(api.ConflictError): self.gateway.ingest(self.payload)
        self.assertIn('Owner annotation to preserve',note['data']['text'])
    def test_owner_metadata_is_preserved_on_next_upload(self):
        self.gateway.ingest(self.payload)
        note=next(iter(self.lifeos.notes.values()))
        note['data'].update(title='Owner room title',folderId='owner-folder',pinned=True,imageIds=['owner-photo'])
        self.payload['readings'][0]['sequence']=2
        self.gateway.ingest(self.payload)
        data=next(iter(self.lifeos.notes.values()))['data']
        self.assertEqual(data['title'],'Owner room title')
        self.assertEqual(data['folderId'],'owner-folder')
        self.assertTrue(data['pinned'])
        self.assertEqual(data['imageIds'],['owner-photo'])
    def test_owner_document_formatting_is_preserved(self):
        self.gateway.ingest(self.payload)
        note=next(iter(self.lifeos.notes.values()))
        note['data']['document']={'type':'doc','content':[{'type':'paragraph','content':[{'type':'text','text':note['data']['text'],'marks':[{'type':'italic'}]}]}]}
        self.payload['readings'][0]['sequence']=2
        with self.assertRaises(api.ConflictError): self.gateway.ingest(self.payload)
        self.assertEqual(note['data']['document']['content'][0]['content'][0]['marks'],[{'type':'italic'}])
    def test_same_id_different_reading_is_rejected(self):
        self.gateway.ingest(self.payload)
        self.payload['readings'][0]['temperature_mc']=23000
        with self.assertRaises(ValueError): self.gateway.ingest(self.payload)
    def test_http_auth_body_bounds_and_ack(self):
        server = ThreadingHTTPServer(('127.0.0.1',0), api.handler(self.gateway,'test-device-token'))
        with running(server) as url:
            with self.assertRaises(urllib.error.HTTPError) as e: urllib.request.urlopen(url+'/v1/next')
            self.assertEqual(e.exception.code,401)
            req=urllib.request.Request(url+'/v1/readings',data=json.dumps(self.payload).encode(),
                headers={'Authorization':'Bearer test-device-token','Content-Type':'application/json'})
            with urllib.request.urlopen(req) as response:
                self.assertEqual(json.load(response),{'accepted':1,'last_sequence':1})
            req=urllib.request.Request(url+'/v1/readings',data=b'x'*13000,
                headers={'Authorization':'Bearer test-device-token','Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as e: urllib.request.urlopen(req)
            self.assertEqual(e.exception.code,413)
    def test_sensor_stale_and_unknown_extra_fields_rejected(self):
        body={**self.payload,'readings':[{**self.payload['readings'][0],'timestamp':999999999999}]}
        with self.assertRaises(ValueError): self.gateway.ingest(body)
        with self.assertRaises(ValueError): self.gateway.ingest({**self.payload,'extra':'x'})

class UpstreamHTTPTests(unittest.TestCase):
    def test_authenticated_upstream_note_write_and_missing_note(self):
        saved={}
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def send_json(self,status,data):
                raw=json.dumps(data).encode()
                self.send_response(status); self.end_headers(); self.wfile.write(raw)
            def do_GET(self):
                if self.headers.get('Cookie') != 'lifeos-local=synthetic-test':
                    return self.send_json(401,{})
                if self.path == '/api/session': return self.send_json(200,{'csrf':'synthetic-csrf'})
                return self.send_json(404,{})
            def do_PUT(self):
                expected_origin='http://127.0.0.1:'+str(self.server.server_port)
                if self.headers.get('X-LifeOS-CSRF') != 'synthetic-csrf' or self.headers.get('Origin') != expected_origin or self.headers.get('Cookie') != 'lifeos-local=synthetic-test':
                    return self.send_json(403,{})
                saved.update(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                return self.send_json(200,{'item':saved})
        with tempfile.TemporaryDirectory() as tmp, running(ThreadingHTTPServer(('127.0.0.1',0),Upstream)) as url:
            cookie=pathlib.Path(tmp)/'cookie'; cookie.write_text('lifeos-local=synthetic-test')
            client=api.LifeOS(url,cookie)
            self.assertIsNone(client.request('GET','/api/private-notes/new'))
            result=client.request('PUT','/api/private-notes/new',{'version':0,'mutationId':'synthetic-test-12345','data':{'title':'Desk room','text':'22.500 C'}})
            self.assertEqual(result['item']['data']['text'],'22.500 C')
            self.assertEqual(saved['version'],0)
            with self.assertRaises(api.UpstreamError): client.request('GET','/api/bootstrap')
    def test_redirect_and_malformed_response_fail_closed(self):
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302); self.send_header('Location','/sink'); self.end_headers()
                elif self.path == '/sink':
                    self.server.leaked=True
                    self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
                else:
                    self.send_response(200); self.end_headers(); self.wfile.write(b'{broken')
        server=ThreadingHTTPServer(('127.0.0.1',0),Upstream); server.leaked=False
        with tempfile.TemporaryDirectory() as tmp, running(server) as url:
            cookie=pathlib.Path(tmp)/'cookie'; cookie.write_text('synthetic-test')
            client=api.LifeOS(url,cookie)
            with self.assertRaises(api.UpstreamError): client.request('GET','/redirect')
            self.assertFalse(server.leaked)
            with self.assertRaises(api.UpstreamError): client.request('GET','/malformed')

if __name__ == '__main__': unittest.main()
