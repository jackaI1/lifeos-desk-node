"""Shared thermostat state; protocol adapters never own separate output values."""
from dataclasses import dataclass
import math


def bounded(value, low, high):
    if isinstance(value, bool) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Value must be finite and between {low} and {high}")
    return float(value)


@dataclass(frozen=True)
class Reading:
    temperature: float
    humidity: float
    timestamp: float


class Thermostat:
    def __init__(self, *, setpoint=22.0, deadband=1.0, max_age=900.0):
        self.setpoint = bounded(setpoint, 10, 30)
        self.deadband = bounded(deadband, 0.2, 5)
        self.max_age = bounded(max_age, 1, 86400)
        self.reading = None
        self.heat = self.fan = False
        self.fault = True
        self.age = 65535

    def configure(self, *, setpoint=None, deadband=None):
        # Validate the whole change before committing either field (FC16).
        sp = self.setpoint if setpoint is None else bounded(setpoint, 10, 30)
        db = self.deadband if deadband is None else bounded(deadband, 0.2, 5)
        self.setpoint, self.deadband = sp, db

    def update(self, reading, now):
        self.reading = reading
        self.fault = True
        self.age = 65535
        if reading is not None:
            try:
                bounded(reading.temperature, -45, 125)
                bounded(reading.humidity, 0, 100)
                bounded(reading.timestamp, 1, now)
                self.age = min(65535, int(now - reading.timestamp))
                self.fault = now - reading.timestamp > self.max_age
            except (ValueError, TypeError, OverflowError):
                pass
        if self.fault:
            self.heat = self.fan = False
            return
        # Full deadband width, centred on setpoint. Retain state inside it.
        if reading.temperature <= self.setpoint - self.deadband / 2:
            self.heat = True
        elif reading.temperature >= self.setpoint + self.deadband / 2:
            self.heat = False
        self.fan = self.heat

    def registers(self):
        # Zero before first sample; invalid readings never reach numeric points.
        t = h = 0
        if self.reading is not None:
            try:
                t = round(bounded(self.reading.temperature, -45, 125) * 100) & 0xFFFF
                h = round(bounded(self.reading.humidity, 0, 100) * 100)
            except (ValueError, TypeError, OverflowError):
                t = h = 0
        return [t, h, int(self.heat), int(self.fan), int(self.fault), self.age]
