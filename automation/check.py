"""Read the live gateway, then exercise its thermostat through both protocols."""
import argparse
import asyncio
import json

from bacpypes3.pdu import Address
from pymodbus.client import AsyncModbusTcpClient
from .protocols import bacnet_application, bacnet_ready, close_bacnet


async def check(host='127.0.0.1', modbus_port=1502, bacnet_port=47808, client_port=47809,
                instance=12001):
    client = AsyncModbusTcpClient(host, port=modbus_port, timeout=2, retries=0)
    app = None
    original = None
    try:
        app = bacnet_application(f'127.0.0.1:{client_port}', instance + 1, 'Desk check client')
        await bacnet_ready(app)
        if not await client.connect():
            raise RuntimeError('Modbus server unavailable')
        target = Address(f'{host}:{bacnet_port}')
        devices = await app.who_is(instance, instance, address=target, timeout=1)
        assert any(int(d.iAmDeviceIdentifier[1]) == instance for d in devices), 'BACnet discovery failed'
        readings = await client.read_input_registers(0, count=6, device_id=1)
        assert not readings.isError() and readings.registers[4] == 0, 'No fresh sensor reading'
        temperature = readings.registers[0]
        temperature = (temperature if temperature < 32768 else temperature - 65536) / 100
        bac_temperature = float(await app.read_property(target, 'analog-input,0', 'present-value'))
        assert abs(temperature - bac_temperature) < 0.3, 'Protocol temperatures differ'
        settings = await client.read_holding_registers(0, count=2, device_id=1)
        assert not settings.isError()
        original = settings.registers
        # Heating demand through Modbus, visible immediately over BACnet.
        result = await client.write_register(0, 3000, device_id=1)
        assert not result.isError()
        assert float(await app.read_property(target, 'analog-value,0', 'present-value')) == 30
        assert str(await app.read_property(target, 'binary-value,0', 'present-value')) == 'active'
        # Release heat through BACnet, visible immediately over Modbus.
        await app.write_property(target, 'analog-value,0', 'present-value', '10')
        settings = await client.read_holding_registers(0, count=1, device_id=1)
        outputs = await client.read_discrete_inputs(0, count=3, device_id=1)
        assert settings.registers == [1000] and outputs.bits[:3] == [False, False, False]
        return {'discovered_device': instance, 'temperature_c': temperature,
                'humidity_percent': readings.registers[1] / 100,
                'checks': ['Modbus read', 'BACnet discovery/read', 'Modbus to BACnet write',
                           'BACnet to Modbus write', 'heat/fan on and off']}
    finally:
        try:
            if original is not None:
                await client.write_registers(0, original, device_id=1)
        finally:
            client.close()
            await close_bacnet(app)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--modbus-port', type=int, default=1502)
    parser.add_argument('--bacnet-port', type=int, default=47808)
    parser.add_argument('--client-port', type=int, default=47809)
    parser.add_argument('--instance', type=int, default=12001)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(check(**vars(args))), indent=2))


if __name__ == '__main__':
    main()
