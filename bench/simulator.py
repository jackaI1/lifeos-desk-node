"""Simulated bench: a SCPI power supply and oscilloscope with a power-up model.

The harness talks to these instruments over PyVISA exactly as it would talk to
real ones. pyvisa-sim answers the SCPI commands from a device file, and this
module writes that file for each run. The file holds:

- the supply: stateful voltage setpoint, output on/off and a current reading,
- the scope: record length, time step and two channel waveforms.

The waveforms come from a small model, not from a circuit simulator: VBUS
ramps up when the output turns on, the 3V3 regulator starts after a delay and
ramps to nominal, and ripple rides on the 3V3 rail once it is up. Fault
injection changes those parameters (more ripple, or a regulator that starts
late). Nothing here talks to real hardware.
"""

import math
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

PSU_RESOURCE = "TCPIP0::192.0.2.10::inst0::INSTR"    # 192.0.2.0/24 is a documentation range
SCOPE_RESOURCE = "TCPIP0::192.0.2.11::inst0::INSTR"
TERMINATION = {"q": "\n", "r": "\n"}
FAULT_NAMES = ("ripple", "late-rail")


@dataclass(frozen=True)
class Scenario:
    vbus_setpoint_v: float = 5.0
    vbus_ramp_ms: float = 1.0          # VBUS rise time after the output turns on
    regulator_delay_ms: float = 1.5    # 3V3 starts this long after the output turns on
    regulator_ramp_ms: float = 1.0
    v3v3_nominal_v: float = 3.3
    ripple_mvpp: float = 8.0
    # Not a divisor of the sample rate: at 200 kHz with 5 us points every sample
    # lands on the same phase and the ripple disappears from the record.
    ripple_hz: float = 230_000.0
    load_a: float = 0.060              # steady current drawn from the supply
    window_ms: float = 30.0
    points: int = 6000
    supply_max_v: float = 6.0          # the simulated supply ignores setpoints above this
    faults: tuple = ()

    def describe(self) -> str:
        bits = [f"VBUS {self.vbus_setpoint_v:g} V", f"3V3 delay {self.regulator_delay_ms:g} ms",
                f"ripple {self.ripple_mvpp:g} mVpp", f"load {self.load_a * 1000:g} mA"]
        if self.faults:
            bits.append("injected: " + ", ".join(self.faults))
        return "; ".join(bits)


def apply_faults(scenario: Scenario, faults) -> Scenario:
    """Return a copy of the scenario with the named faults injected."""
    names = tuple(sorted({f.strip() for f in faults if f and f.strip() != "none"}))
    unknown = set(names) - set(FAULT_NAMES)
    if unknown:
        raise ValueError(f"unknown fault(s) {sorted(unknown)}; choose from {list(FAULT_NAMES)}")
    changed = scenario
    if "ripple" in names:
        changed = replace(changed, ripple_mvpp=60.0)    # twice the 30 mVpp limit
    if "late-rail" in names:
        changed = replace(changed, regulator_delay_ms=14.0)  # past the 10 ms limit
    return replace(changed, faults=names)


def rail_waveforms(scenario: Scenario):
    """Return (times_s, vbus_volts, v3v3_volts) sampled on the scope's time base."""
    step_s = scenario.window_ms / scenario.points / 1000.0
    times = [i * step_s for i in range(scenario.points)]
    vbus, v3 = [], []
    ramp_s = scenario.vbus_ramp_ms / 1000.0
    delay_s = scenario.regulator_delay_ms / 1000.0
    reg_ramp_s = scenario.regulator_ramp_ms / 1000.0
    ripple_amp = scenario.ripple_mvpp / 1000.0 / 2.0
    for t in times:
        vbus.append(min(t / ramp_s, 1.0) * scenario.vbus_setpoint_v)
        frac = min(max((t - delay_s) / reg_ramp_s, 0.0), 1.0)
        ripple = ripple_amp * frac * math.sin(2 * math.pi * scenario.ripple_hz * t)
        v3.append(frac * scenario.v3v3_nominal_v + ripple)
    return times, vbus, v3


def device_definition(scenario: Scenario) -> dict:
    """pyvisa-sim device file (YAML) for the supply and the scope."""
    times, vbus, v3 = rail_waveforms(scenario)
    dt_s = times[1] - times[0]

    def eom():
        return {"TCPIP INSTR": dict(TERMINATION), "TCPIP SOCKET": dict(TERMINATION)}

    supply = {
        "eom": eom(),
        "dialogues": [
            {"q": "*IDN?", "r": "SIM,DESK-BENCH-PSU,0001,1.0"},
            {"q": "*OPC?", "r": "1"},
            {"q": "*RST"},
        ],
        "properties": {
            "voltage": {
                "default": "0.0",
                "getter": {"q": "SOUR:VOLT?", "r": "{}"},
                "setter": {"q": "SOUR:VOLT {}"},
                "specs": {"type": "float", "min": 0.0, "max": scenario.supply_max_v},
            },
            "output": {
                "default": "OFF",
                "getter": {"q": "OUTP?", "r": "{}"},
                "setter": {"q": "OUTP {}"},
            },
            "current": {
                "default": f"{scenario.load_a:.6f}",
                "getter": {"q": "MEAS:CURR?", "r": "{}"},
            },
        },
    }
    scope = {
        "eom": eom(),
        "dialogues": [
            {"q": "*IDN?", "r": "SIM,DESK-BENCH-SCOPE,0002,1.0"},
            {"q": "*OPC?", "r": "1"},
            {"q": ":WAV:POIN?", "r": str(scenario.points)},
            {"q": ":WAV:XINC?", "r": f"{dt_s:.9g}"},
            {"q": ":WAV:XORIG?", "r": "0"},
            {"q": ":WAV:DATA? CHAN1", "r": ",".join(f"{v:.6f}" for v in vbus)},
            {"q": ":WAV:DATA? CHAN2", "r": ",".join(f"{v:.6f}" for v in v3)},
        ],
    }
    return {
        "spec": "1.1",
        "devices": {"bench-psu": supply, "bench-scope": scope},
        "resources": {PSU_RESOURCE: {"device": "bench-psu"},
                      SCOPE_RESOURCE: {"device": "bench-scope"}},
    }


def write_device_file(scenario: Scenario, path) -> Path:
    path = Path(path)
    path.write_text(yaml.safe_dump(device_definition(scenario), sort_keys=False), encoding="utf-8")
    return path
