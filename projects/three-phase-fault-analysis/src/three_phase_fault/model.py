"""Common-base, passive sequence networks with equal balanced source voltages."""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def positive(value, name):
    if isinstance(value, bool) or not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def impedance(value, name, allow_zero=False):
    z = complex(value)
    if not np.isfinite(z) or z.real < 0 or z.imag < 0 or (z == 0 and not allow_zero):
        raise ValueError(f"{name} must be finite, passive R+jX with X >= 0")
    return z


@dataclass(frozen=True)
class Branch:
    name: str
    from_bus: str
    to_bus: str
    z0: complex | None
    z1: complex
    z2: complex


@dataclass(frozen=True)
class Source:
    name: str
    bus: str
    z0: complex | None
    z1: complex
    z2: complex


@dataclass(frozen=True)
class Network:
    buses: tuple[str, ...]
    branches: tuple[Branch, ...]
    sources: tuple[Source, ...]
    base_mva: float
    base_kv_ll: float
    prefault_voltage: complex = 1 + 0j
    frequency_hz: float = 60

    def __post_init__(self):
        if not self.buses or len(set(self.buses)) != len(self.buses):
            raise ValueError("buses must be nonempty and unique")
        if any(not isinstance(b, str) or not b for b in self.buses):
            raise ValueError("bus names must be nonempty strings")
        for field in ("base_mva", "base_kv_ll", "frequency_hz"):
            positive(getattr(self, field), field)
        if not np.isfinite(self.prefault_voltage) or abs(self.prefault_voltage) == 0:
            raise ValueError("prefault_voltage must be finite and nonzero")
        names = [item.name for item in (*self.branches, *self.sources)]
        if len(set(names)) != len(names) or any(not n for n in names):
            raise ValueError("element names must be nonempty and unique")
        if not self.sources:
            raise ValueError("At least one source is required")
        for item in (*self.branches, *self.sources):
            endpoints = (item.from_bus, item.to_bus) if isinstance(item, Branch) else (item.bus,)
            if any(b not in self.buses for b in endpoints):
                raise ValueError(f"Unknown bus on {item.name}")
            if isinstance(item, Branch) and item.from_bus == item.to_bus:
                raise ValueError("A branch must connect different buses")
            for seq in range(3):
                z = getattr(item, f"z{seq}")
                if z is None and seq == 0:
                    continue
                impedance(z, f"{item.name}.z{seq}")
        for seq in (1, 2):
            for bus in self.buses:
                component = self.component(bus, seq)
                if not any(s.bus in component for s in self.sources):
                    raise ValueError(f"Bus {bus} has no sequence-{seq} source path")

    @property
    def base_current_a(self):
        return self.base_mva * 1000 / (np.sqrt(3) * self.base_kv_ll)

    def component(self, bus, seq):
        reached = {bus}
        while True:
            previous = len(reached)
            for branch in self.branches:
                if getattr(branch, f"z{seq}") is not None:
                    if branch.from_bus in reached or branch.to_bus in reached:
                        reached.update((branch.from_bus, branch.to_bus))
            if len(reached) == previous:
                return reached

    def driving_column(self, bus, seq):
        """Zbus column for the fault component; None means an open zero path."""
        component = self.component(bus, seq)
        sources = [
            s for s in self.sources if s.bus in component and getattr(s, f"z{seq}") is not None
        ]
        if not sources:
            return None
        buses = [b for b in self.buses if b in component]
        indices = {b: i for i, b in enumerate(buses)}
        y = np.zeros((len(buses), len(buses)), dtype=complex)
        for source in sources:
            y[indices[source.bus], indices[source.bus]] += 1 / getattr(source, f"z{seq}")
        for branch in self.branches:
            z = getattr(branch, f"z{seq}")
            if branch.from_bus not in component or z is None:
                continue
            i, j = indices[branch.from_bus], indices[branch.to_bus]
            y[i, i] += 1 / z
            y[j, j] += 1 / z
            y[i, j] -= 1 / z
            y[j, i] -= 1 / z
        injection = np.zeros(len(buses), dtype=complex)
        injection[indices[bus]] = 1
        column = np.linalg.solve(y, injection)
        return {b: column[indices[b]] if b in component else 0j for b in self.buses}


def _complex_pair(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Complex values must be [real, imaginary]")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
        raise ValueError("Complex parts must be numbers")
    return complex(*value)


def load_network(path: str | Path):
    """Read the strict JSON format documented in docs/model.md."""
    data = json.loads(Path(path).read_text())
    allowed = {
        "buses",
        "branches",
        "sources",
        "base_mva",
        "base_kv_ll",
        "prefault_voltage",
        "frequency_hz",
    }
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError("Unknown network fields")
    required = {"buses", "sources", "base_mva", "base_kv_ll"}
    if required - set(data):
        raise ValueError(f"Missing network fields: {', '.join(sorted(required - set(data)))}")
    if not isinstance(data["buses"], list):
        raise ValueError("buses must be an array of names")
    for key, cls in (("branches", Branch), ("sources", Source)):
        if not isinstance(data.get(key, []), list):
            raise ValueError(f"{key} must be an array of objects")
        elements = []
        for record in data.get(key, []):
            fields = set(cls.__dataclass_fields__)
            if not isinstance(record, dict) or set(record) != fields:
                raise ValueError(
                    f"Each {key} entry must contain exactly: {', '.join(sorted(fields))}"
                )
            record = dict(record)
            for seq in range(3):
                field = f"z{seq}"
                record[field] = (
                    None if record[field] is None and seq == 0 else _complex_pair(record[field])
                )
            elements.append(cls(**record))
        data[key] = tuple(elements)
    data["buses"] = tuple(data["buses"])
    if "prefault_voltage" in data:
        data["prefault_voltage"] = _complex_pair(data["prefault_voltage"])
    return Network(**data)
