"""Small documented SCPI dialect over the same write/query/close API as PyVISA.

These commands are project-specific, not an implementation of a vendor manual.
All simulated resources share one bench, so BERT and DCA read the same capture.
"""
import json
from dataclasses import dataclass, field
from typing import Protocol

from .analysis import analyze_spectrum, count_errors
from .model import Capture, LinkConfig, acquire, simulate_spectrum


class Resource(Protocol):
    def write(self, command: str): ...
    def query(self, command: str) -> str: ...
    def close(self): ...


@dataclass
class _Bench:
    config: LinkConfig
    power_dbm: float = -20
    capture: Capture | None = None
    log: list = field(default_factory=list)


class SimResource:
    def __init__(self, bench: _Bench, role: str):
        self.bench, self.role, self.closed = bench, role, False

    def _record(self, operation, command):
        if self.closed:
            raise RuntimeError('resource is closed')
        command = command.strip().upper()
        self.bench.log.append(dict(resource=f'SIM::{self.role}',
                                   operation=operation, command=command))
        return command

    def write(self, command: str):
        command = self._record('write', command)
        if self.role == 'ATT' and command.startswith(':POW '):
            power = float(command.split()[1])
            if not -80 <= power <= 20:
                raise ValueError('power must be finite and -80..20 dBm')
            self.bench.power_dbm = power
            self.bench.capture = None
        elif self.role == 'BERT' and command == ':INIT':
            self.bench.capture = acquire(self.bench.config, self.bench.power_dbm)
        else:
            raise ValueError(f'unsupported {self.role} command: {command}')

    def query(self, command: str) -> str:
        command = self._record('query', command)
        if command == '*IDN?':
            return f'JackLai,SIMULATED-{self.role},0,0.1'
        if self.role == 'ATT' and command == ':POW?':
            return str(self.bench.power_dbm)
        if self.role == 'OSA' and command == ':TRAC:DATA?':
            x, y = simulate_spectrum()
            # Spectrum shape stays fixed, total nominal power follows attenuation.
            return json.dumps([x.tolist(), (y + self.bench.power_dbm).tolist()])
        if (self.role, command) not in [('BERT', ':FETC:BER?'), ('DCA', ':WAV:DATA?')]:
            raise ValueError(f'unsupported {self.role} query: {command}')
        capture = self.bench.capture
        if capture is None:
            raise RuntimeError('acquire with BERT :INIT after changing power')
        if self.role == 'BERT':
            return json.dumps(count_errors(capture.bits, capture.decisions))
        return json.dumps(dict(bits=capture.bits.tolist(), samples_mw=capture.samples_mw.tolist(),
                               decisions=capture.decisions.tolist(),
                               threshold_mw=capture.threshold_mw))

    def close(self):
        self.closed = True


class SimResourceManager:
    def __init__(self, config: LinkConfig):
        self.bench = _Bench(config)
        self.resources = []
        self.closed = False

    def open_resource(self, address: str) -> SimResource:
        if self.closed:
            raise RuntimeError('resource manager is closed')
        if address not in ('SIM::ATT', 'SIM::BERT', 'SIM::DCA', 'SIM::OSA'):
            raise ValueError('use SIM::ATT, SIM::BERT, SIM::DCA or SIM::OSA')
        resource = SimResource(self.bench, address.split('::')[1])
        self.resources.append(resource)
        return resource

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        for resource in self.resources:
            resource.close()
        self.bench.capture = None
        self.closed = True


class Attenuator:
    def __init__(self, resource: Resource):
        self.resource = resource

    def set_power(self, power_dbm: float):
        self.resource.write(f':POW {power_dbm:.12g}')


class Bert:
    def __init__(self, resource: Resource):
        self.resource = resource

    def measure(self) -> dict:
        self.resource.write(':INIT')
        return json.loads(self.resource.query(':FETC:BER?'))


class Dca:
    def __init__(self, resource: Resource):
        self.resource = resource

    def capture(self) -> Capture:
        import numpy as np
        data = json.loads(self.resource.query(':WAV:DATA?'))
        return Capture(np.array(data['bits'], dtype=np.uint8), np.array(data['samples_mw']),
                       np.array(data['decisions'], dtype=np.uint8), data['threshold_mw'])


class Osa:
    def __init__(self, resource: Resource):
        self.resource = resource

    def trace(self):
        import numpy as np
        return tuple(np.asarray(a) for a in json.loads(self.resource.query(':TRAC:DATA?')))

    def measure(self):
        return analyze_spectrum(*self.trace())
