"""DBC-defined thermal control with bounded statistics and fail-closed outputs.

CRC-8/SAE-J1850 parameters are used as a *project* protocol, not a vehicle OEM
format. Coverage binds the identifier, frame format, length and payload.
"""
from dataclasses import dataclass
from pathlib import Path
import math
import can
import cantools

DB = cantools.database.load_file(str(Path(__file__).with_name('desk.dbc')))


def crc8(data):
    crc = 0xff
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1d if crc & 0x80 else 0)) & 0xff
    return crc ^ 0xff


def checksum(frame):
    return crc8(frame.arbitration_id.to_bytes(2, 'big') +
                bytes([int(frame.is_fd), len(frame.data)]) + frame.data[:-1])


def make_frame(temperature, counter, fd=False, *, setpoint=22, heater=0, fan=0):
    spec = DB.get_message_by_name('ThermalFD' if fd else 'Thermal')
    data = spec.encode(dict(Temperature=temperature, Counter=counter, Checksum=0,
                            Setpoint=setpoint, Heater=heater, Fan=fan))
    frame = can.Message(arbitration_id=spec.frame_id, data=data,
                        is_extended_id=False, is_fd=fd, bitrate_switch=fd, check=True)
    frame.data[-1] = checksum(frame)
    return frame


@dataclass
class Rate:
    count: int = 0
    first: float = 0
    last: float = 0

    def add(self, now):
        if not self.count:
            self.first = now
        self.last = now
        self.count += 1

    @property
    def hz(self):
        return (self.count - 1) / (self.last - self.first) if self.last > self.first else 0


class Monitor:
    def __init__(self, timeout=2.0, *, expected=(0x100,), start=0.0):
        if not math.isfinite(timeout) or timeout <= 0 or not math.isfinite(start):
            raise ValueError('finite positive timeout and finite start required')
        self.timeout, self.start = timeout, start
        self.expected = set(expected)
        if not self.expected <= {m.frame_id for m in DB.messages}:
            raise ValueError('expected identifiers must be in the DBC')
        self.last_seen, self.counters, self.times, self.latest = {}, {}, {}, {}
        self.faults = set(self.expected)
        self.transport_fault = False
        self.clock = start

    def _time(self, now):
        if not math.isfinite(now) or now < self.clock:
            raise ValueError('time must be finite and nondecreasing')
        self.clock = now

    def process(self, frame, now):
        self._time(now)
        errors = []
        signals = {}
        key = frame.arbitration_id
        try:
            spec = DB.get_message_by_frame_id(key)
        except KeyError:
            self.transport_fault = True
            return {'errors': ['unknown_id'], 'signals': {}, 'safe': self.outputs(now)}
        self.times.setdefault(key, Rate()).add(now)
        if frame.is_extended_id or frame.is_remote_frame or frame.is_error_frame:
            errors.append('format')
        if len(frame.data) != spec.length or frame.dlc != spec.length:
            errors.append('length')
        if frame.is_fd != spec.is_fd or (frame.is_fd and not frame.bitrate_switch):
            errors.append('format')
        if not errors:
            if checksum(frame) != frame.data[-1]:
                errors.append('checksum')
            else:
                signals = spec.decode(frame.data)
                if any(s.minimum is not None and not s.minimum <= signals[s.name] <= s.maximum
                       for s in spec.signals):
                    errors.append('range')
                counter = signals['Counter']
                if key in self.counters and counter != (self.counters[key] + 1) % 256:
                    errors.append('counter')
                # Resynchronise only from structurally valid, CRC-checked data.
                # The gap frame stays rejected; the next sequential frame recovers.
                self.counters[key] = counter
        if errors:
            self.faults.add(key)
        else:
            self.faults.discard(key)
            self.last_seen[key] = now
            self.latest[key] = signals
            if key == 0x100:
                self.transport_fault = False
        return {'errors': errors, 'signals': signals if not errors else {}, 'safe': self.outputs(now)}

    def silent(self, now):
        self._time(now)
        return sorted(key for key in self.expected | set(self.last_seen)
                      if now - self.last_seen.get(key, self.start) >= self.timeout)

    def outputs(self, now):
        fault = bool(self.faults or self.transport_fault or self.silent(now) or 0x100 not in self.latest)
        signals = self.latest.get(0x100, {})
        return dict(fault=fault, heater=0 if fault else signals['Heater'],
                    fan=0 if fault else signals['Fan'])

    def rates(self):
        return {key: rate.hz for key, rate in self.times.items()}

    def summary(self, now):
        return {'rates': {hex(k): {'frames': v.count, 'hz': v.hz} for k, v in self.times.items()},
                'silent': [hex(k) for k in self.silent(now)], 'outputs': self.outputs(now)}
