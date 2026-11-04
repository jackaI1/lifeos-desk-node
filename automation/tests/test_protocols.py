import asyncio
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import socket
import sys
import tempfile
import unittest

from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.pdu import Address
from pymodbus.client import AsyncModbusTcpClient
from automation.check import check
from automation.control import Reading
from automation.gateway import Bridge
from automation.protocols import ProtocolServers, bacnet_application, bacnet_ready, close_bacnet
from automation.sources import AdapterSource
from test_sources import batch, desk_api


def udp_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class FixedSource:
    def __init__(self):
        self.reading = Reading(20, 45, 1000)

    def sample(self, now, heat):
        return self.reading


class WireTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 1000
        self.source = FixedSource()
        self.bridge = Bridge(self.source, clock=lambda: self.now)
        self.server = ProtocolServers(self.bridge, modbus_port=0, bacnet_port=udp_port())
        self.bridge.servers = self.server
        self.addAsyncCleanup(self.server.close)
        self.bridge.refresh()
        await self.server.start()
        self.client = AsyncModbusTcpClient('127.0.0.1', port=self.server.modbus_port, timeout=1, retries=0)
        self.addCleanup(self.client.close)
        self.assertTrue(await self.client.connect())
        self.app = bacnet_application(f'127.0.0.1:{udp_port()}', 12002, 'Wire test client')
        self.addAsyncCleanup(close_bacnet, self.app)
        await bacnet_ready(self.app)
        self.target = Address(f'127.0.0.1:{self.server.bacnet_port}')

    async def read(self, obj, prop='present-value'):
        return await asyncio.wait_for(self.app.read_property(self.target, obj, prop), 3)

    async def write(self, obj, value, **kwargs):
        return await asyncio.wait_for(self.app.write_property(self.target, obj, 'present-value', value, **kwargs), 3)

    async def test_actual_tcp_registers_and_discretes(self):
        values = await self.client.read_input_registers(0, count=6, device_id=1)
        self.assertEqual(values.registers, [2000, 4500, 1, 1, 0, 0])
        bits = await self.client.read_discrete_inputs(0, count=3, device_id=1)
        self.assertEqual(bits.bits[:3], [True, True, False])
        settings = await self.client.read_holding_registers(0, count=2, device_id=1)
        self.assertEqual(settings.registers, [2200, 100])

    async def test_bacnet_discovery_units_and_object_list(self):
        devices = await self.app.who_is(12001, 12001, address=self.target, timeout=0.1)
        self.assertEqual([int(d.iAmDeviceIdentifier[1]) for d in devices], [12001])
        self.assertEqual(float(await self.read('analog-input,0')), 20)
        self.assertEqual(float(await self.read('analog-input,1')), 45)
        self.assertEqual(str(await self.read('analog-input,0', 'units')), 'degrees-celsius')
        self.assertEqual(str(await self.read('analog-input,1', 'units')), 'percent-relative-humidity')
        objects = await self.read('device,12001', 'object-list')
        self.assertEqual(len(objects), 9)  # device, network port, seven room/control points

    async def test_modbus_write_visible_over_bacnet(self):
        result = await self.client.write_registers(0, [1800, 200], device_id=1)
        self.assertFalse(result.isError())
        self.assertEqual(float(await self.read('analog-value,0')), 18)
        self.assertEqual(float(await self.read('analog-value,1')), 2)
        self.assertEqual(str(await self.read('binary-value,0')), 'inactive')
        self.assertEqual(str(await self.read('binary-value,1')), 'inactive')

    async def test_bacnet_write_visible_over_modbus(self):
        await self.write('analog-value,0', '18')
        await self.write('analog-value,1', '2')
        result = await self.client.read_holding_registers(0, count=2, device_id=1)
        self.assertEqual(result.registers, [1800, 200])
        outputs = await self.client.read_discrete_inputs(0, count=3, device_id=1)
        self.assertEqual(outputs.bits[:3], [False, False, False])

    async def test_modbus_rejects_invalid_and_atomic_partial_write(self):
        for address, values, code in [(0, [2500, 0], 3), (0, [65535], 3),
                                       (1, [501], 3), (2, [2200], 2)]:
            with self.subTest(address=address, values=values):
                result = await self.client.write_registers(address, values, device_id=1)
                self.assertTrue(result.isError())
                self.assertEqual(result.exception_code, code)
        self.assertEqual(self.bridge.model.setpoint, 22)
        self.assertEqual(self.bridge.model.deadband, 1)

    async def test_modbus_no_sensor_or_output_write_paths(self):
        result = await self.client.write_coil(0, True, device_id=1)
        self.assertTrue(result.isError())
        result = await self.client.read_input_registers(6, count=1, device_id=1)
        self.assertEqual(result.exception_code, 2)
        with self.assertLogs('pymodbus', level='ERROR'):
            result = await self.client.read_input_registers(0, count=1, device_id=2)
        self.assertTrue(result.isError())

    async def test_bacnet_rejects_invalid_values_and_priority(self):
        for value in ('9', '31', 'nan', 'inf'):
            with self.subTest(value=value):
                with self.assertRaises(ErrorRejectAbortNack):
                    await self.write('analog-value,0', value)
        with self.assertRaises(ErrorRejectAbortNack):
            await self.write('analog-value,1', '0')
        with self.assertRaises(ErrorRejectAbortNack):
            await self.write('analog-value,0', '24', priority=8)
        self.assertEqual(self.bridge.model.setpoint, 22)

    async def test_bacnet_cannot_override_sensors_or_outputs(self):
        for obj, value in [('analog-input,0', '10'), ('analog-input,1', '90'),
                           ('binary-value,0', 'inactive'), ('binary-value,1', 'inactive'),
                           ('binary-value,2', 'inactive')]:
            with self.subTest(obj=obj):
                with self.assertRaises(ErrorRejectAbortNack):
                    await self.write(obj, value)
        with self.assertRaises(ErrorRejectAbortNack):
            await self.app.write_property(self.target, 'analog-input,0', 'out-of-service', 'true')
        with self.assertRaises(ErrorRejectAbortNack):
            await self.app.write_property(self.target, 'device,12001', 'object-name', 'Changed')

    async def test_stale_fault_both_protocols_and_recovery(self):
        self.now = 1901
        self.bridge.refresh()
        values = await self.client.read_input_registers(0, count=6, device_id=1)
        self.assertEqual(values.registers[2:], [0, 0, 1, 901])
        self.assertEqual(str(await self.read('binary-value,2')), 'active')
        self.assertEqual(str(await self.read('analog-input,0', 'reliability')), 'unreliable-other')
        self.source.reading = Reading(20, 45, self.now)
        self.bridge.refresh()
        self.assertEqual(str(await self.read('binary-value,0')), 'active')
        self.assertEqual(str(await self.read('binary-value,2')), 'inactive')

    async def test_signed_temperature_on_wire(self):
        self.source.reading = Reading(-5.25, 67.25, self.now)
        values = await self.client.read_input_registers(0, count=2, device_id=1)
        self.assertEqual(values.registers, [65011, 6725])
        self.assertEqual(float(await self.read('analog-input,0')), -5.25)

    async def test_existing_adapter_ingest_reaches_both_protocols(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'room.sqlite3'
            adapter = desk_api.Gateway(path, desk_api.DemoLifeOS(),
                now=lambda: datetime.fromtimestamp(3000, timezone.utc))
            try:
                self.bridge.source = AdapterSource(path, 'abcdef123456')
                adapter.ingest(batch(temp=19000))
                result = await self.client.read_input_registers(0, count=2, device_id=1)
                self.assertEqual(result.registers, [1900, 4525])
                self.assertEqual(float(await self.read('analog-input,0')), 19)
                adapter.ingest(batch(timestamp=1000, temp=24000, sequence=2))
                self.bridge.refresh()
                self.assertEqual(str(await self.read('binary-value,0')), 'inactive')
                self.assertEqual(float(await self.read('analog-input,0')), 24)
            finally:
                adapter.close()

    async def test_shipped_live_check(self):
        result = await check(modbus_port=self.server.modbus_port,
            bacnet_port=self.server.bacnet_port, client_port=udp_port())
        self.assertEqual(len(result['checks']), 5)
        self.assertEqual(self.bridge.model.setpoint, 22)

    async def test_ports_released_after_close(self):
        port = self.server.modbus_port
        udp = self.server.bacnet_port
        self.client.close()
        await self.server.close()
        await asyncio.sleep(0.05)
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', port))
        with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as sock:
            sock.bind(('127.0.0.1', udp))


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_udp_start_also_closes_tcp_and_bind_tasks(self):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as occupied:
            occupied.bind(('127.0.0.1', 0))
            server = ProtocolServers(Bridge(FixedSource(), clock=lambda: 1000),
                modbus_port=0, bacnet_port=occupied.getsockname()[1])
            self.addAsyncCleanup(server.close)
            with self.assertRaises(TimeoutError):
                await server.start()
            self.assertIsNone(server.bacnet)
            self.assertIsNone(server.modbus)
            with closing(socket.socket()) as sock:
                self.assertNotEqual(sock.connect_ex(('127.0.0.1', server.modbus_port)), 0)
            # No unfinished BACpypes bind tasks survive this failure path.
            self.assertFalse(any('retrying_create_datagram_endpoint' in repr(t.get_coro())
                for t in asyncio.all_tasks() if not t.done()))

    async def test_cli_sigterm_releases_ports(self):
        # Own this child by its process handle; always terminate/wait on failure.
        tcp = socket.socket()
        tcp.bind(('127.0.0.1', 0))
        port = tcp.getsockname()[1]
        tcp.close()
        udp = udp_port()
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'automation.gateway',
            '--demo', '--modbus-port', str(port), '--bacnet-port', str(udp),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            line = await asyncio.wait_for(process.stdout.readline(), 5)
            metadata = json.loads(line)
            self.assertEqual(metadata['pid'], process.pid)
            self.assertEqual(metadata['modbus_tcp_port'], port)
            self.assertEqual(metadata['stop'], f'kill -TERM {process.pid}')
            print('owned fixture:', json.dumps(metadata))
            process.send_signal(signal.SIGTERM)
            self.assertEqual(await asyncio.wait_for(process.wait(), 5), 0)
            with closing(socket.socket()) as sock:
                self.assertNotEqual(sock.connect_ex(('127.0.0.1', port)), 0)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as sock:
                sock.bind(('127.0.0.1', udp))
        finally:
            if process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), 5)
