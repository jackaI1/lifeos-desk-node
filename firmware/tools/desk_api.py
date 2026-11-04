#!/usr/bin/env python3
"""Desk-node API adapter for LifeOS. Python 3.9+, standard library only.

Credentials are read from owner-provided files, never printed. Live mode only
writes dedicated desk-room log notes; demo mode never contacts LifeOS.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import signal
import sqlite3
import ssl
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

class UpstreamError(Exception):
    pass
class ConflictError(UpstreamError):
    pass

def utcnow():
    return datetime.now(timezone.utc)

def select_next(source, now, zone):
    tz = ZoneInfo(zone)
    candidates = []
    for row in source.get('today', {}).get('calendar', {}).get('events', []):
        try:
            start = datetime.fromisoformat(row['start'].replace('Z', '+00:00'))
            if not row.get('isSchool') or start.tzinfo is None or row.get('status') == 'cancelled' or row.get('allDay'):
                continue
            if start >= now:
                candidates.append((start, 'class', str(row.get('title') or 'Class'), False))
        except (KeyError, ValueError, TypeError):
            continue
    for item in source.get('records', {}).get('task', []):
        row = item.get('data', {})
        if row.get('status') in ('complete', 'cancelled') or row.get('archived'):
            continue
        try:
            unknown = not row.get('dueAt')
            if unknown:
                due = datetime.fromisoformat(row['dueDate']+'T00:00').replace(tzinfo=tz)
                if due.date() == now.astimezone(tz).date():
                    due = now
            else:
                due = datetime.fromisoformat(row['dueAt'].replace('Z','+00:00'))
                if due.tzinfo is None:
                    continue
            if due >= now:
                candidates.append((due, 'deadline', str(row.get('title') or 'Deadline'), unknown))
        except (KeyError, ValueError, TypeError):
            continue
    if not candidates:
        return {'next': None}
    at, kind, title, unknown = min(candidates)
    # OLED has a compact ASCII font. Transliteration is deliberately predictable.
    title = title.encode('ascii', 'replace').decode()[:95].strip() or 'Untitled'
    return {'next': {'kind': kind, 'title': title, 'when': at.astimezone(tz).strftime('%a time unknown' if unknown else '%a %H:%M')}}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class LifeOS:
    def __init__(self, url, cookie_file):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValueError('LifeOS URL must be an origin')
        if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('LifeOS requires HTTPS except on loopback')
        self.url = url.rstrip('/')
        self.cookie_file = Path(cookie_file)
        self.opener = urllib.request.build_opener(NoRedirect)
    def request(self, method, path, data=None):
        headers = {'Cookie': self.cookie_file.read_text().strip(), 'Accept': 'application/json'}
        if data is not None:
            session = self.request('GET', '/api/session')
            headers.update({'Origin':self.url, 'X-LifeOS-CSRF':session['csrf'], 'Content-Type':'application/json'})
        request = urllib.request.Request(self.url+path, method=method, headers=headers,
            data=None if data is None else json.dumps(data, allow_nan=False).encode())
        try:
            with self.opener.open(request, timeout=5) as response:
                raw = response.read(2*1024*1024+1)
                if len(raw) > 2*1024*1024:
                    raise UpstreamError('LifeOS response too large')
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and method == 'GET' and path.startswith('/api/private-notes/'):
                return None
            if exc.code == 409:
                raise ConflictError('LifeOS note version conflict') from None
            raise UpstreamError('LifeOS HTTP request failed') from None
        except (OSError, ValueError, KeyError) as exc:
            raise UpstreamError('LifeOS unavailable or invalid response') from exc

class DemoLifeOS:
    def __init__(self):
        self.notes = {}
    def request(self, method, path, data=None):
        if path == '/api/bootstrap':
            return {'records': {'task': [{'data': {'title':'Demo: review desk-node firmware',
                'dueDate':utcnow().strftime('%Y-%m-%d'), 'status':'todo'}}]}}
        if method == 'GET':
            return {'item':self.notes[path]} if path in self.notes else None
        self.notes[path] = {'version':data['version']+1, 'data':data['data']}
        return {'item':self.notes[path]}

class Gateway:
    def __init__(self, database, lifeos, now=utcnow, zone='America/Toronto'):
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute('''CREATE TABLE IF NOT EXISTS readings(
            device TEXT, session TEXT, sequence INTEGER, timestamp INTEGER,
            temperature_mc INTEGER, humidity_mpermil INTEGER, day TEXT,
            PRIMARY KEY(device,session,sequence))''')
        self.db.execute('CREATE TABLE IF NOT EXISTS generated_notes(path TEXT, hash TEXT, PRIMARY KEY(path,hash))')
        self.db.commit()
        self.lifeos, self.now, self.zone = lifeos, now, zone
        self.lock = threading.Lock()
    def close(self):
        self.db.close()
    def next_event(self):
        return select_next(self.lifeos.request('GET', '/api/bootstrap'), self.now(), self.zone)
    @staticmethod
    def integer(value, low, high):
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Integer outside allowed range')
    def validate(self, body):
        if type(body) is not dict or set(body) != {'device','session','dropped','readings'}:
            raise ValueError('Invalid batch fields')
        for key, length in [('device',12), ('session',16)]:
            if not isinstance(body[key],str) or not re.fullmatch('[0-9a-f]{'+str(length)+'}',body[key]):
                raise ValueError('Invalid identity')
        self.integer(body['dropped'],0,2**32-1)
        rows = body['readings']
        if type(rows) is not list or not 1 <= len(rows) <= 64:
            raise ValueError('Batch must contain 1..64 readings')
        previous = 0
        for row in rows:
            if type(row) is not dict or set(row) != {'sequence','timestamp','temperature_mc','humidity_mpermil'}:
                raise ValueError('Invalid reading fields')
            self.integer(row['sequence'],previous+1,2**32-1)
            previous = row['sequence']
            self.integer(row['timestamp'],0,int(self.now().timestamp())+300)
            self.integer(row['temperature_mc'],-45000,125000)
            self.integer(row['humidity_mpermil'],0,100000)
    def ingest(self, body):
        self.validate(body)
        device, session, rows = body['device'], body['session'], body['readings']
        with self.lock:
            days = set()
            # Commit receipt before contacting LifeOS. An upstream failure leaves a
            # durable dedup record, but never returns an acknowledgment to ESP32.
            with self.db:
                for row in rows:
                    values = tuple(row[k] for k in ('timestamp','temperature_mc','humidity_mpermil'))
                    old = self.db.execute('SELECT timestamp,temperature_mc,humidity_mpermil,day FROM readings WHERE device=? AND session=? AND sequence=?',
                        (device,session,row['sequence'])).fetchone()
                    if old:
                        if old[:3] != values:
                            raise ValueError('Reading identity reused with different data')
                        days.add(old[3]); continue
                    at = datetime.fromtimestamp(row['timestamp'],timezone.utc) if row['timestamp'] else self.now()
                    day = at.astimezone(ZoneInfo(self.zone)).strftime('%Y-%m-%d')
                    self.db.execute('INSERT INTO readings VALUES(?,?,?,?,?,?,?)',
                        (device,session,row['sequence'],*values,day))
                    days.add(day)
            for day in sorted(days):
                self.publish(device, day)
        return {'accepted':len(rows),'last_sequence':rows[-1]['sequence']}
    def publish(self, device, day):
        rows = self.db.execute('SELECT session,sequence,timestamp,temperature_mc,humidity_mpermil FROM readings WHERE device=? AND day=? ORDER BY session,sequence',
            (device,day)).fetchall()
        lines = ['Room readings — '+day, 'Device '+device, 'UTC sample time; unsynchronized = unknown, not upload time.']
        for session,seq,at,temp,rh in rows:
            stamp = datetime.fromtimestamp(at,timezone.utc).isoformat() if at else 'unsynchronized'
            lines.append(f'{session}/{seq} {stamp}: {temp/1000:.3f} C, {rh/1000:.3f} %RH')
        text = '\n'.join(lines)
        if len(text.encode()) > 90000:
            raise UpstreamError('Daily log full; increase wake interval or archive adapter data')
        path = '/api/private-notes/desk-room-'+device+'-'+day
        for attempt in range(3):
            existing = self.lifeos.request('GET',path)
            item = (existing or {}).get('item')
            if item and item['data'].get('text') == text:
                return
            if item:
                old_hash = hashlib.sha256(item['data'].get('text','').encode()).hexdigest()
                if not self.db.execute('SELECT 1 FROM generated_notes WHERE path=? AND hash=?',(path,old_hash)).fetchone():
                    raise ConflictError('Managed room note was edited; preserve owner changes')
            data = {'title':'Desk room '+day+' '+device, 'text':text}
            version = item['version'] if item else 0
            digest = hashlib.sha256((path+str(version)+text).encode()).hexdigest()
            # Persist the generated content fingerprint before the write. If the
            # response is lost, its known body can still be recognized next time.
            with self.db:
                self.db.execute('INSERT OR IGNORE INTO generated_notes VALUES(?,?)',
                    (path,hashlib.sha256(text.encode()).hexdigest()))
            try:
                self.lifeos.request('PUT',path,{'version':version,'mutationId':'desk-'+digest,'data':data})
                return
            except ConflictError:
                if attempt == 2:
                    raise

def handler(gateway, token):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'
        def log_message(self, *args):
            pass  # Do not log credentials or personal schedule content.
        def setup(self):
            super().setup()
            self.connection.settimeout(10)
        def reply(self, code, value):
            raw = json.dumps(value,allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            self.dispatch()
        def do_POST(self):
            self.dispatch()
        def dispatch(self):
            if not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token):
                return self.reply(401,{'error':'Unauthorized'})
            try:
                if self.command == 'GET' and self.path == '/v1/next':
                    return self.reply(200,gateway.next_event())
                if self.command != 'POST' or self.path != '/v1/readings':
                    return self.reply(404,{'error':'Not found'})
                length = int(self.headers.get('Content-Length','0'))
                if length < 1 or length > 12288 or self.headers.get('Transfer-Encoding'):
                    return self.reply(413,{'error':'Body must be 1..12288 bytes'})
                if self.headers.get_content_type() != 'application/json':
                    return self.reply(415,{'error':'JSON required'})
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('Incomplete body')
                body = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                return self.reply(200,gateway.ingest(body))
            except (ValueError,TypeError,KeyError,UnicodeError):
                self.reply(400,{'error':'Invalid request'})
            except (UpstreamError,sqlite3.Error,OSError):
                self.reply(503,{'error':'Retry later; readings not acknowledged'})
    return Handler

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8091)
    parser.add_argument('--database',type=Path,default=Path('desk-readings.sqlite3'))
    parser.add_argument('--demo',action='store_true')
    parser.add_argument('--cert',type=Path)
    parser.add_argument('--key',type=Path)
    parser.add_argument('--allow-http',action='store_true',help='development only: allow LAN HTTP')
    args = parser.parse_args()
    if args.host not in ('localhost','127.0.0.1','::1') and not args.cert and not args.allow_http:
        parser.error('LAN listening needs TLS cert/key or explicit --allow-http')
    if bool(args.cert) != bool(args.key):
        parser.error('--cert and --key must be used together')
    token = Path(os.environ['DESK_TOKEN_FILE']).read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', token):
        parser.error('device token must be 32..128 URL-safe characters')
    upstream = DemoLifeOS() if args.demo else LifeOS(os.environ['LIFEOS_URL'],os.environ['LIFEOS_COOKIE_FILE'])
    os.umask(0o077)
    gateway = Gateway(args.database,upstream)
    server = HTTPServer((args.host,args.port),handler(gateway,token))
    try:
        if args.cert:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(args.cert,args.key)
            server.socket = context.wrap_socket(server.socket,server_side=True)
        # Signal handlers end serve_forever without deadlocking its thread.
        def stop(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,stop)
        print(f'Desk API PID {os.getpid()}, started {utcnow().isoformat()}, port {server.server_port}; stop: kill -TERM {os.getpid()}',flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close(); gateway.close()

if __name__ == '__main__':
    main()
