"""Real Modbus TCP and BACnet/IP endpoints backed by one thermostat."""
from argparse import Namespace
import asyncio

from pymodbus.constants import ExcCodes
from pymodbus.datastore import ModbusServerContext
from pymodbus.datastore.context import ModbusBaseDeviceContext
from pymodbus.server import ModbusTcpServer
from bacpypes3.app import Application
from bacpypes3.errors import ExecutionError
from bacpypes3.local.analog import AnalogInputObject, AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject


class DeskRegisters(ModbusBaseDeviceContext):
    def __init__(self, bridge):
        self.bridge = bridge

    def getValues(self, func_code, address, count=1):
        self.bridge.refresh()
        model = self.bridge.model
        if func_code in (3, 6, 16):
            values = [round(model.setpoint * 100), round(model.deadband * 100)]
        elif func_code == 4:
            values = model.registers()
        elif func_code == 2:
            values = [model.heat, model.fan, model.fault]
        else:
            return ExcCodes.ILLEGAL_FUNCTION
        if address < 0 or count < 1 or address + count > len(values):
            return ExcCodes.ILLEGAL_ADDRESS
        return values[address:address + count]

    def setValues(self, func_code, address, values):
        if func_code not in (6, 16):
            return ExcCodes.ILLEGAL_FUNCTION
        if address < 0 or not values or address + len(values) > 2:
            return ExcCodes.ILLEGAL_ADDRESS
        fields = dict(zip(('setpoint', 'deadband')[address:], (v / 100 for v in values)))
        try:
            self.bridge.model.configure(**fields)
        except (ValueError, TypeError):
            return ExcCodes.ILLEGAL_VALUE
        self.bridge.refresh()


class ReadOnly:
    async def write_property(self, attr, value, index=None, priority=None):
        raise ExecutionError(errorClass='property', errorCode='writeAccessDenied')


class SensorPoint(ReadOnly, AnalogInputObject):
    pass


class OutputPoint(ReadOnly, BinaryValueObject):
    pass


class SettingPoint(AnalogValueObject):
    def __init__(self, bridge, field, **kwargs):
        super().__init__(**kwargs)
        self._bridge, self._field = bridge, field

    async def write_property(self, attr, value, index=None, priority=None):
        if getattr(attr, 'attr', attr) != 'presentValue' or index is not None or priority is not None:
            raise ExecutionError(errorClass='property', errorCode='writeAccessDenied')
        try:
            self._bridge.model.configure(**{self._field: float(value)})
        except (ValueError, TypeError):
            raise ExecutionError(errorClass='property', errorCode='valueOutOfRange') from None
        self._bridge.refresh()


class DeskApplication(Application):
    async def do_WritePropertyRequest(self, apdu):
        # Device identity and network-port settings are also read-only remotely.
        if not isinstance(self.get_object_id(apdu.objectIdentifier), SettingPoint):
            raise ExecutionError(errorClass='property', errorCode='writeAccessDenied')
        await super().do_WritePropertyRequest(apdu)


def bacnet_application(address, instance=12001, name='Desk room simulator'):
    # Explicit settings keep unrelated BACPYPES_* environment values out of the demo.
    return DeskApplication.from_args(Namespace(address=address, instance=instance, name=name,
        vendoridentifier=999, network=0, foreign=None, ttl=30, bbmd=None))


async def bacnet_ready(app):
    # BACpypes3 binds UDP asynchronously. Await its pinned transport interface so
    # clients never race startup. /32 loopback needs only the unicast socket.
    for link in app.link_layers.values():
        await asyncio.wait_for(link.server._local_transport_ready.wait(), 3)


async def close_bacnet(app):
    if app is None:
        return
    # Also cancel unfinished bind attempts on a failed startup. The pinned
    # library's close() alone only closes already-created transports.
    pending = []
    for link in app.link_layers.values():
        for task in link.server._transport_tasks:
            if not task.done():
                for callback, _ in list(task._callbacks or []):
                    task.remove_done_callback(callback)
                task.cancel()
                pending.append(task)
    await asyncio.gather(*pending, return_exceptions=True)
    app.close()
    await asyncio.sleep(0)


class ProtocolServers:
    def __init__(self, bridge, host='127.0.0.1', modbus_port=1502,
                 bacnet_port=47808, instance=12001):
        self.bridge = bridge
        self.host, self.modbus_port, self.bacnet_port = host, modbus_port, bacnet_port
        self.instance = instance
        self.modbus = self.bacnet = None
        self.points = []

    async def start(self):
        try:
            context = ModbusServerContext(devices={1: DeskRegisters(self.bridge)}, single=False)
            self.modbus = ModbusTcpServer(context, address=(self.host, self.modbus_port))
            await self.modbus.serve_forever(background=True)
            self.modbus_port = self.modbus.transport.sockets[0].getsockname()[1]
            self.bacnet = bacnet_application(f'{self.host}:{self.bacnet_port}', self.instance)
            common = dict(statusFlags=[0, 0, 0, 0], outOfService=False)
            self.points = [
                SensorPoint(objectIdentifier=('analog-input', 0), objectName='Room temperature',
                    presentValue=0, units='degreesCelsius', covIncrement=0.1, **common),
                SensorPoint(objectIdentifier=('analog-input', 1), objectName='Room humidity',
                    presentValue=0, units='percentRelativeHumidity', covIncrement=0.1, **common),
                SettingPoint(self.bridge, 'setpoint', objectIdentifier=('analog-value', 0),
                    objectName='Heating setpoint', presentValue=self.bridge.model.setpoint,
                    units='degreesCelsius', covIncrement=0.1, **common),
                SettingPoint(self.bridge, 'deadband', objectIdentifier=('analog-value', 1),
                    objectName='Full deadband width', presentValue=self.bridge.model.deadband,
                    units='degreesCelsius', covIncrement=0.1, **common),
            ]
            for i, name in enumerate(('Simulated heat output', 'Simulated fan output', 'Sensor fault')):
                self.points.append(OutputPoint(objectIdentifier=('binary-value', i),
                    objectName=name, presentValue='inactive', **common))
            for point in self.points:
                self.bacnet.add_object(point)
            await bacnet_ready(self.bacnet)
            self.refresh_points()
        except BaseException:
            await self.close()
            raise

    def refresh_points(self):
        if not self.points:
            return
        m = self.bridge.model
        registers = m.registers()
        temperature = registers[0] if registers[0] < 32768 else registers[0] - 65536
        values = (temperature / 100, registers[1] / 100, m.setpoint, m.deadband,
                  'active' if m.heat else 'inactive', 'active' if m.fan else 'inactive',
                  'active' if m.fault else 'inactive')
        for point, value in zip(self.points, values):
            point.presentValue = value
        for point in self.points[:2]:
            point.statusFlags = [0, int(m.fault), 0, 0]
            point.reliability = 'unreliableOther' if m.fault else 'noFaultDetected'

    async def close(self):
        await close_bacnet(self.bacnet)
        self.bacnet = None
        if self.modbus is not None:
            await self.modbus.shutdown()
            self.modbus = None
