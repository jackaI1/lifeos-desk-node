"""Protobuf request/response boundary for the simulated fixture."""
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from .station import Link, MockResource, Laser, PowerMeter, Analyser

file = descriptor_pb2.FileDescriptorProto(name='fixture.proto', package='fixture', syntax='proto3')
for name, fields in [('Request', [('operation', 1, 9), ('wavelength_nm', 2, 1), ('launch_dbm', 3, 1)]), ('Response', [('ok', 1, 8), ('value', 2, 1), ('error', 3, 9)])]:
    msg = file.message_type.add(name=name)
    for field, number, kind in fields:
        msg.field.add(name=field, number=number, type=kind, label=1)
pool = descriptor_pool.DescriptorPool()
pool.Add(file)
Request = message_factory.GetMessageClass(pool.FindMessageTypeByName('fixture.Request'))
Response = message_factory.GetMessageClass(pool.FindMessageTypeByName('fixture.Response'))

class Fixture:
    def __init__(self, resource=None): self.resource = resource or MockResource(Link())
    def handle(self, payload):
        request = Request.FromString(payload)
        try:
            Laser(self.resource).configure(request.wavelength_nm, request.launch_dbm)
            if request.operation == 'READ_POWER': value = PowerMeter(self.resource).read()
            elif request.operation == 'READ_OSNR': value = Analyser(self.resource).osnr()
            else: raise ValueError('Unknown fixture operation')
            return Response(ok=True, value=value).SerializeToString()
        except (TimeoutError, ValueError) as exc:
            return Response(ok=False, error=str(exc)).SerializeToString()

def call_fixture(operation, wavelength_nm, launch_dbm, fixture=None):
    request = Request(operation=operation, wavelength_nm=wavelength_nm, launch_dbm=launch_dbm)
    return Response.FromString((fixture or Fixture()).handle(request.SerializeToString()))

class FixtureResource:
    """Translate driver commands into serialized fixture RPC calls."""
    def __init__(self, fixture):
        self.fixture = fixture
        self.wavelength = 1550.0
        self.launch = 0.0
    def write(self, command):
        name, value = command.split()
        if name == 'SOUR:WAV': self.wavelength = float(value)
        elif name == 'SOUR:POW': self.launch = float(value)
        else: raise ValueError('Unsupported command')
    def query(self, command):
        operations = {'MEAS:POW?': 'READ_POWER', 'MEAS:OSNR?': 'READ_OSNR'}
        if command not in operations: raise ValueError('Unsupported query')
        response = call_fixture(operations[command], self.wavelength, self.launch, self.fixture)
        if not response.ok: raise ValueError(response.error)
        return str(response.value)
