"""Synthetic room or read-only access to the existing ESP32 ingestion database."""
from pathlib import Path
from contextlib import closing
import sqlite3
from .control import Reading


class AdapterSource:
    def __init__(self, database, device):
        self.uri = Path(database).resolve().as_uri() + '?mode=ro'
        self.device = device

    def sample(self, now, heat):
        # A fresh, short read transaction sees new adapter commits without
        # locking its writer or changing its schema. Never create a missing DB.
        try:
            with closing(sqlite3.connect(self.uri, uri=True, timeout=0.1)) as db:
                row = db.execute('''SELECT temperature_mc, humidity_mpermil, timestamp
                    FROM readings WHERE device=? AND timestamp>0
                    ORDER BY timestamp DESC, rowid DESC LIMIT 1''', (self.device,)).fetchone()
            return Reading(row[0] / 1000, row[1] / 1000, row[2]) if row else None
        except (sqlite3.Error, TypeError, ValueError):
            return None


class SimulatedRoom:
    def __init__(self):
        self.temperature = 20.0
        self.last = None

    def sample(self, now, heat):
        # Accelerated first-order room: 18 C surroundings, 0.15 C/s heater,
        # heat loss proportional to temperature difference. No real actuators.
        dt = 0 if self.last is None else max(0, min(5, now - self.last))
        self.last = now
        self.temperature += dt * ((0.15 if heat else 0) - 0.02 * (self.temperature - 18))
        return Reading(self.temperature, 45.0, now)
