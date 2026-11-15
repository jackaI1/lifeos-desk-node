"""Simulated instruments for the temperature sweep: chamber, function generator, scope, supply, DUT.

Each sweep step gets its own pyvisa-sim device file, written from a small model of
the board at that temperature and bus speed. The harness talks to these over
PyVISA with the same SCPI it would use on real hardware. Only the resource strings
change for real instruments (see docs/bench-automation.md).

The model, in plain terms:

- The chamber reference probe reads the setpoint plus a 0.1 C chamber offset.
- The SHT31 reads the true temperature plus its own bias (0.25 C at 25 C, growing
  0.005 C per degree). Fault "sensor-drift" adds 2 C above 40 C.
- The 3V3 rail sits at 3.3 V with a small temperature coefficient, plus the
  ripple. Fault "ripple" raises the ripple to 60 mVpp.
- The SDA line is an RC rise from the release point, with the bus capacitance
  rising 0.2 % per degree. Its rise time is then checked against the I2C limit.
- Fault "stuck-chamber" keeps the chamber in SETTLING and never reaches the setpoint.

Nothing here talks to hardware, and none of the readings is a measurement.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import yaml

from bench.simulator import SCOPE_RESOURCE, TERMINATION

CHAMBER_RESOURCE = "TCPIP0::192.0.2.13::inst0::INSTR"   # 192.0.2.0/24 is a documentation range
FGEN_RESOURCE = "TCPIP0::192.0.2.12::inst0::INSTR"
DUT_RESOURCE = "TCPIP0::192.0.2.14::inst0::INSTR"

SWEEP_FAULTS = ("sensor-drift", "ripple", "stuck-chamber")
RESISTOR_OHM = 4700.0
BUS_CAP_F = 50e-12
RECORD_POINTS = 2000


@dataclass(frozen=True)
class StepModel:
    """Everything the simulated instruments report at one setpoint and bus speed."""
    setpoint_c: float
    bus_hz: float
    faults: Tuple[str, ...] = ()

    @property
    def probe_c(self) -> float:
        return self.setpoint_c + (-8.0 if "stuck-chamber" in self.faults else 0.1)

    @property
    def sht_c(self) -> float:
        bias = 0.25 + 0.005 * (self.setpoint_c - 25.0)
        if "sensor-drift" in self.faults and self.setpoint_c >= 40.0:
            bias += 2.0
        return self.setpoint_c + bias

    @property
    def status(self) -> str:
        return "SETTLING" if "stuck-chamber" in self.faults else "SETTLED"

    @property
    def rail_v(self) -> float:
        return 3.3 - 0.0002 * (self.setpoint_c - 25.0)

    @property
    def ripple_mvpp(self) -> float:
        return 60.0 if "ripple" in self.faults else 8.0

    @property
    def sda_tau_s(self) -> float:
        c_bus = BUS_CAP_F * (1.0 + 0.002 * (self.setpoint_c - 25.0))
        return RESISTOR_OHM * c_bus

    @property
    def period_s(self) -> float:
        return 1.0 / self.bus_hz

    def waveforms(self) -> Tuple[float, list, list]:
        """(dt_s, rail_samples_v, sda_samples_v) for a two-period record."""
        record_s = 2.0 * self.period_s
        dt = record_s / RECORD_POINTS
        t_release = 0.5 * self.period_s
        amp = self.ripple_mvpp / 1000.0 / 2.0
        rail, sda = [], []
        for i in range(RECORD_POINTS):
            t = i * dt
            rail.append(self.rail_v + amp * math.sin(2 * math.pi * 230_000.0 * t))
            phase = t % self.period_s
            if phase < t_release:
                sda.append(0.0)
            else:
                sda.append(3.3 * (1.0 - math.exp(-(phase - t_release) / self.sda_tau_s)))
        return dt, rail, sda


def _eom() -> Dict[str, Dict[str, str]]:
    return {"TCPIP INSTR": dict(TERMINATION), "TCPIP SOCKET": dict(TERMINATION)}


def device_definition(step: StepModel) -> dict:
    """pyvisa-sim device file for every instrument at one sweep step."""
    dt, rail, sda = step.waveforms()
    chamber = {
        "eom": _eom(),
        "dialogues": [
            {"q": "*IDN?", "r": "SIM,DESK-BENCH-CHAMBER,0003,1.0"},
            {"q": ":TEMP:PROBE?", "r": f"{step.probe_c:.3f}"},
            {"q": ":TEMP:STAT?", "r": step.status},
            {"q": "*RST"},
        ],
        "properties": {
            "setpoint": {
                "default": "25.0",
                "getter": {"q": ":TEMP:SET?", "r": "{}"},
                "setter": {"q": ":TEMP:SET {}"},
                "specs": {"type": "float", "min": -40.0, "max": 125.0},
            },
        },
    }
    fgen = {
        "eom": _eom(),
        "dialogues": [
            {"q": "*IDN?", "r": "SIM,DESK-BENCH-FGEN,0004,1.0"},
            {"q": "*OPC?", "r": "1"},
        ],
        "properties": {
            "frequency": {
                "default": f"{step.bus_hz:.1f}",
                "getter": {"q": "SOUR1:FREQ?", "r": "{}"},
                "setter": {"q": "SOUR1:FREQ {}"},
                "specs": {"type": "float", "min": 1.0, "max": 1e6},
            },
            "output": {
                "default": "OFF",
                "getter": {"q": "OUTP1?", "r": "{}"},
                "setter": {"q": "OUTP1 {}"},
            },
        },
    }
    scope = {
        "eom": _eom(),
        "dialogues": [
            {"q": "*IDN?", "r": "SIM,DESK-BENCH-SCOPE,0002,1.0"},
            {"q": "*OPC?", "r": "1"},
            {"q": ":WAV:POIN?", "r": str(RECORD_POINTS)},
            {"q": ":WAV:XINC?", "r": f"{dt:.9g}"},
            {"q": ":WAV:XORIG?", "r": "0"},
            {"q": ":WAV:DATA? CHAN1", "r": ",".join(f"{v:.6f}" for v in rail)},
            {"q": ":WAV:DATA? CHAN2", "r": ",".join(f"{v:.6f}" for v in sda)},
        ],
    }
    dut = {
        "eom": _eom(),
        "dialogues": [
            {"q": "*IDN?", "r": "SIM,DESK-NODE-DUT,0005,1.0"},
            {"q": "READ:TEMP?", "r": f"{step.sht_c:.3f}"},
        ],
    }
    return {
        "spec": "1.1",
        "devices": {"bench-chamber": chamber, "bench-fgen": fgen, "bench-scope": scope,
                    "desk-node": dut},
        "resources": {
            CHAMBER_RESOURCE: {"device": "bench-chamber"},
            FGEN_RESOURCE: {"device": "bench-fgen"},
            SCOPE_RESOURCE: {"device": "bench-scope"},
            DUT_RESOURCE: {"device": "desk-node"},
        },
    }


def write_device_file(step: StepModel, path) -> Path:
    path = Path(path)
    path.write_text(yaml.safe_dump(device_definition(step), sort_keys=False), encoding="utf-8")
    return path


def parse_faults(names) -> Tuple[str, ...]:
    chosen = tuple(sorted({n.strip() for n in names if n and n.strip() not in ("", "none")}))
    unknown = set(chosen) - set(SWEEP_FAULTS)
    if unknown:
        raise ValueError(f"unknown sweep fault(s) {sorted(unknown)}; choose from {list(SWEEP_FAULTS)}")
    return chosen
