"""SI-unit inputs and an independent complex-impedance calculation."""

import json
import re
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np


def positive(name, value, *, zero=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not np.isfinite(value)
        or value < 0
        or (not zero and value == 0)
    ):
        raise ValueError(f"{name} must be finite and {'nonnegative' if zero else 'positive'}")


@dataclass(frozen=True)
class Bank:
    name: str
    node: str
    count: int
    capacitance_f: float
    esr_ohm: float
    esl_h: float

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError("bank name must contain lowercase letters, digits or underscores")
        if self.node not in ("board", "die"):
            raise ValueError("bank node must be board or die")
        if type(self.count) is not int or self.count < 0:
            raise ValueError("bank count must be a nonnegative integer")
        for name in ("capacitance_f", "esr_ohm", "esl_h"):
            positive(name, getattr(self, name))


@dataclass(frozen=True)
class Study:
    nominal_v: float = 0.9
    base_a: float = 20.0
    step_a: float = 40.0
    droop_budget_v: float = 0.045
    vrm_r_ohm: float = 0.00025
    vrm_l_h: float = 2e-9
    path_r_ohm: float = 0.0001
    path_l_h: float = 0.15e-9
    f_start_hz: float = 1e3
    f_stop_hz: float = 1e8
    points_per_decade: int = 200
    delay_s: float = 20e-6
    rise_s: float = 100e-9
    hold_s: float = 40e-6
    stop_s: float = 100e-6
    max_step_s: float = 10e-9
    banks: tuple[Bank, ...] = (
        Bank("bulk", "board", 4, 330e-6, 0.012, 2e-9),
        Bank("ceramic", "board", 24, 12e-6, 0.002, 0.6e-9),
        Bank("package", "die", 16, 1e-6, 0.003, 0.15e-9),
    )

    def __post_init__(self):
        for field in fields(self):
            if field.name not in ("banks", "points_per_decade"):
                positive(field.name, getattr(self, field.name), zero=field.name == "base_a")
        if type(self.points_per_decade) is not int or self.points_per_decade < 10:
            raise ValueError("points_per_decade must be an integer >= 10")
        if self.f_stop_hz <= self.f_start_hz:
            raise ValueError("f_stop_hz must exceed f_start_hz")
        if self.stop_s <= self.delay_s + 2 * self.rise_s + self.hold_s:
            raise ValueError("stop_s must include the complete pulse and recovery")
        if self.max_step_s > min(self.rise_s / 10, self.delay_s / 10, self.hold_s / 10):
            raise ValueError("max_step_s must resolve the rise, delay and hold with >= 10 steps")
        if not self.banks or not all(isinstance(bank, Bank) for bank in self.banks):
            raise ValueError("banks must contain Bank entries")
        if len({b.name for b in self.banks}) != len(self.banks):
            raise ValueError("bank names must be unique")
        if self.high_load_v <= 0:
            raise ValueError("DC rail voltage must remain positive at high load")

    @property
    def target_ohm(self):
        return self.droop_budget_v / self.step_a

    @property
    def baseline_v(self):
        return self.nominal_v - self.base_a * (self.vrm_r_ohm + self.path_r_ohm)

    @property
    def high_load_v(self):
        return self.nominal_v - (self.base_a + self.step_a) * (self.vrm_r_ohm + self.path_r_ohm)


def load_study(path: Path) -> Study:
    """Reject unknown keys rather than silently accepting misspelled units."""
    try:
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict):
            raise ValueError("configuration must be a JSON object")
        if "banks" in data:
            data["banks"] = tuple(Bank(**bank) for bank in data["banks"])
        return Study(**data)
    except (TypeError, KeyError) as exc:
        raise ValueError(f"invalid configuration: {exc}") from exc


def bank_impedance(bank: Bank, frequency):
    w = 2 * np.pi * np.asarray(frequency)
    if bank.count == 0:
        return np.full(w.shape, complex(np.inf, 0))
    return (bank.esr_ohm + 1j * (w * bank.esl_h - 1 / (w * bank.capacitance_f))) / bank.count


def impedance(model: Study, frequency):
    """Reduce the ladder from board to die; the ideal voltage source is AC ground."""
    w = 2 * np.pi * np.asarray(frequency)
    board_y = 1 / (model.vrm_r_ohm + 1j * w * model.vrm_l_h)
    die_y = np.zeros(w.shape, dtype=complex)
    for bank in model.banks:
        if bank.count:
            if bank.node == "board":
                board_y = board_y + 1 / bank_impedance(bank, frequency)
            else:
                die_y = die_y + 1 / bank_impedance(bank, frequency)
    source_path = 1 / board_y + model.path_r_ohm + 1j * w * model.path_l_h
    return 1 / (1 / source_path + die_y)
