"""Run: python -m automation.gateway --demo. Ctrl-C/SIGTERM releases both ports."""
import argparse
import asyncio
from datetime import datetime, timezone
import ipaddress
import json
import os
import re
import signal
import time

from .control import Thermostat
from .protocols import ProtocolServers
from .sources import AdapterSource, SimulatedRoom


class Bridge:
    def __init__(self, source, *, clock=time.time, max_age=900):
        self.source, self.clock = source, clock
        self.model = Thermostat(max_age=max_age)
        self.servers = None

    def refresh(self):
        now = self.clock()
        reading = self.source.sample(now, self.model.heat)
        self.model.update(reading, now)
        if self.servers:
            self.servers.refresh_points()


async def run(args):
    source = SimulatedRoom() if args.demo else AdapterSource(args.database, args.device)
    bridge = Bridge(source, max_age=args.max_age)
    servers = ProtocolServers(bridge, args.host, args.modbus_port, args.bacnet_port, args.instance)
    bridge.servers = servers
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        bridge.refresh()
        await servers.start()
        print(json.dumps({'owner': 'desk automation gateway', 'pid': os.getpid(),
            'started_utc': datetime.now(timezone.utc).isoformat(), 'host': args.host,
            'modbus_tcp_port': servers.modbus_port, 'bacnet_udp_port': args.bacnet_port,
            'stop': f'kill -TERM {os.getpid()}', 'source': 'simulation' if args.demo else 'adapter'}), flush=True)
        while not stop.is_set():
            bridge.refresh()
            try:
                await asyncio.wait_for(stop.wait(), 0.5)
            except TimeoutError:
                pass
    finally:
        await servers.close()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--demo', action='store_true', help='accelerated room with synthetic readings')
    source.add_argument('--database', help='existing desk_api.py SQLite file, opened read-only')
    parser.add_argument('--device', help='12 lowercase hex characters, required with --database')
    parser.add_argument('--host', default='127.0.0.1', help='IPv4 bind address')
    parser.add_argument('--allow-lan', action='store_true', help='explicitly allow unauthenticated LAN protocols')
    parser.add_argument('--modbus-port', type=int, default=1502)
    parser.add_argument('--bacnet-port', type=int, default=47808)
    parser.add_argument('--instance', type=int, default=12001)
    parser.add_argument('--max-age', type=float, default=900, help='sensor freshness limit, seconds')
    args = parser.parse_args()
    if args.database and not re.fullmatch('[0-9a-f]{12}', args.device or ''):
        parser.error('--database requires --device with 12 lowercase hex characters')
    try:
        addr = ipaddress.IPv4Address(args.host)
    except ValueError:
        parser.error('--host must be an IPv4 address')
    if not addr.is_loopback and not args.allow_lan:
        parser.error('non-loopback binding requires --allow-lan on an isolated test network')
    if not (1 <= args.modbus_port <= 65535 and 1 <= args.bacnet_port <= 65535 and 0 <= args.instance <= 4194302):
        parser.error('invalid port or BACnet device instance')
    if not 1 <= args.max_age <= 86400:
        parser.error('--max-age must be between 1 and 86400 seconds')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
