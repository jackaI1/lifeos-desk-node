"""Thin PyVISA wrappers for the bench supply and scope.

Only SCPI strings live here. Every setpoint is read back, because a real
supply can refuse or clamp a value without raising an error, and so can the
simulator. A mismatch stops the run instead of recording a result for a rail
that was never set.
"""

from dataclasses import dataclass
from typing import List

import pyvisa
from pyvisa.errors import VisaIOError

from bench.simulator import PSU_RESOURCE, SCOPE_RESOURCE


class InstrumentError(RuntimeError):
    """An instrument did not answer, or did not accept a setting."""


class SetpointError(InstrumentError):
    """The supply read back a different voltage from the one that was set."""


def _open(rm, resource: str, timeout_ms: int):
    try:
        handle = rm.open_resource(resource)
    except VisaIOError as exc:
        raise InstrumentError(f"cannot open {resource}: {exc}") from exc
    handle.read_termination = "\n"
    handle.write_termination = "\n"
    handle.timeout = timeout_ms
    return handle


class _Instrument:
    def __init__(self, rm: pyvisa.ResourceManager, resource: str, timeout_ms: int = 10_000):
        self.resource = resource
        self._handle = _open(rm, resource, timeout_ms)

    def _query(self, command: str) -> str:
        try:
            return self._handle.query(command).strip()
        except VisaIOError as exc:
            raise InstrumentError(f"{self.resource} did not answer {command!r}: {exc}") from exc

    def _write(self, command: str) -> None:
        try:
            self._handle.write(command)
        except VisaIOError as exc:
            raise InstrumentError(f"{self.resource} rejected {command!r}: {exc}") from exc

    def identify(self) -> str:
        return self._query("*IDN?")

    def close(self) -> None:
        self._handle.close()


class Supply(_Instrument):
    """Programmable DC supply: one rail, voltage setpoint, output switch and current readback."""

    def __init__(self, rm, resource: str = PSU_RESOURCE):
        super().__init__(rm, resource)

    def set_voltage(self, volts: float, tolerance_v: float) -> float:
        self._write(f"SOUR:VOLT {volts:.4f}")
        readback = float(self._query("SOUR:VOLT?"))
        if abs(readback - volts) > tolerance_v:
            raise SetpointError(f"supply set to {volts:.3f} V but reads back {readback:.3f} V")
        return readback

    def output(self, on: bool) -> None:
        self._write(f"OUTP {'ON' if on else 'OFF'}")

    def measure_current_a(self) -> float:
        return float(self._query("MEAS:CURR?"))


@dataclass(frozen=True)
class Waveform:
    channel: int
    dt_s: float
    t0_s: float
    samples: List[float]

    def times(self) -> List[float]:
        return [self.t0_s + i * self.dt_s for i in range(len(self.samples))]


class Scope(_Instrument):
    """Oscilloscope: fetches one channel at a time as ASCII, with its time base."""

    def __init__(self, rm, resource: str = SCOPE_RESOURCE, timeout_ms: int = 30_000):
        super().__init__(rm, resource, timeout_ms)

    def wait_complete(self) -> None:
        # *OPC? returns 1 once the last command and capture are finished.
        if self._query("*OPC?") != "1":
            raise InstrumentError(f"{self.resource} did not complete the capture")

    def waveform(self, channel: int) -> Waveform:
        if channel not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        points = int(self._query(":WAV:POIN?"))
        dt_s = float(self._query(":WAV:XINC?"))
        t0_s = float(self._query(":WAV:XORIG?"))
        raw = self._query(f":WAV:DATA? CHAN{channel}")
        samples = [float(x) for x in raw.split(",") if x]
        if len(samples) != points:
            raise InstrumentError(f"CHAN{channel} returned {len(samples)} points, expected {points}")
        return Waveform(channel, dt_s, t0_s, samples)
