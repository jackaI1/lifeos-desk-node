"""Net-SNMP pass_persist backend. No SNMP packets are hand-rolled here."""
import json
import sys
import time
from pathlib import Path

# Net-SNMP's local experimental subtree, not a claimed assigned enterprise OID.
BASE = '.1.3.6.1.4.1.8072.9999.1'
FIELDS = ('status', 'latency_ms', 'loss_percent', 'alarm')


def values(path, now=None):
    now = time.time() if now is None else now
    try:
        data = json.loads(Path(path).read_text())
        if not 0 <= now-data['updated'] <= 5: raise ValueError('stale monitor')
        rows = [int(data[k]) for k in FIELDS]
        if not all(0 <= x <= 2147483647 for x in rows): raise ValueError('invalid snapshot')
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        rows = [0, 0, 100, 1]
    return {BASE+f'.{i}.0': value for i, value in enumerate(rows, 1)}


def oid_key(oid): return tuple(int(x) for x in oid.strip('.').split('.'))


def serve(path, source=sys.stdin, out=sys.stdout):
    while line := source.readline():
        command = line.strip()
        if command == 'PING':
            print('PONG', file=out, flush=True)
            continue
        if command not in ('get', 'getnext'):
            print('NONE', file=out, flush=True)
            continue
        oid = source.readline().strip()
        try:
            rows = values(path)
            key = oid if command == 'get' and oid in rows else None
            if command == 'getnext':
                key = next((k for k in rows if oid_key(k) > oid_key(oid)), None)
            if key is None: print('NONE', file=out, flush=True)
            else: print(f'{key}\ninteger\n{rows[key]}', file=out, flush=True)
        except ValueError:
            print('NONE', file=out, flush=True)


if __name__ == '__main__': serve(sys.argv[1])
