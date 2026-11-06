"""Solve sequence-network equations together with physical fault boundaries."""

from dataclasses import dataclass

import numpy as np

from .model import Network, impedance
from .sequences import TO_PHASE, sequence_to_phase

FAULT_TYPES = ("3ph", "lg", "ll", "llg")


@dataclass
class FaultResult:
    fault_type: str
    bus: str
    impedance_pu: complex
    sequence_current_pu: np.ndarray
    phase_current_pu: np.ndarray
    bus_voltage_pu: dict[str, np.ndarray]
    source_current_pu: dict[str, np.ndarray]
    branch_current_pu: dict[str, np.ndarray]
    base_current_a: float

    @property
    def phase_current_a(self):
        return self.phase_current_pu * self.base_current_a

    @property
    def residual_current_a(self):
        """Ground return current Ia+Ib+Ic, also 3 I0, in primary amperes."""
        return 3 * self.sequence_current_pu[0] * self.base_current_a


def solve_fault(network: Network, bus: str, fault_type: str, zf=0j):
    """3ph: per-phase Zf; LG: a-ground; LL: b-c; LLG: b,c-common Zf-ground.

    LL Zf is the total impedance between b and c. Source and branch currents
    point toward the bus and from_bus to to_bus respectively.
    """
    if bus not in network.buses:
        raise ValueError(f"Unknown fault bus: {bus}")
    if fault_type not in FAULT_TYPES:
        raise ValueError(f"fault_type must be one of {FAULT_TYPES}")
    zf = impedance(zf, "fault impedance", allow_zero=True)
    columns = [network.driving_column(bus, seq) for seq in range(3)]
    # Unknowns: [I0, I1, I2, V0, V1, V2] at the fault bus.
    matrix = np.zeros((6, 6), dtype=complex)
    rhs = np.zeros(6, dtype=complex)
    rhs[1] = network.prefault_voltage
    for seq, column in enumerate(columns):
        if column is None:
            matrix[seq, seq] = 1  # No zero-sequence return: I0 = 0; V0 is free.
        else:
            matrix[seq, seq] = column[bus]
            matrix[seq, seq + 3] = 1
    a, b, c = TO_PHASE
    if fault_type == "3ph":
        matrix[3:, :3] = -zf * TO_PHASE
        matrix[3:, 3:] = TO_PHASE
    elif fault_type == "lg":
        matrix[3, :3], matrix[4, :3] = b, c
        matrix[5, :3], matrix[5, 3:] = -zf * a, a
    elif fault_type == "ll":
        matrix[3, :3], matrix[4, :3] = a, b + c
        if columns[0] is None:
            # Ia=0 and I0=0 already imply Ib+Ic=0. An ungrounded LL fault
            # leaves neutral voltage arbitrary; choose the prefault reference.
            matrix[4, :3] = 0
            matrix[4, 3] = 1
        matrix[5, :3], matrix[5, 3:] = -zf * b, b - c
    else:
        matrix[3, :3] = a
        matrix[4, 3:] = b - c
        matrix[5, :3], matrix[5, 3:] = -zf * (b + c), b
    solution = np.linalg.solve(matrix, rhs)
    current, voltage = solution[:3], solution[3:]
    bus_seq = {}
    floating_component = network.component(bus, 0)
    for name in network.buses:
        values = np.array([0j, network.prefault_voltage, 0j])
        for seq, column in enumerate(columns):
            if column is not None:
                values[seq] -= column[name] * current[seq]
            elif name in floating_component:
                values[seq] = voltage[seq]
        bus_seq[name] = values
    source_currents = {}
    for source in network.sources:
        values = np.zeros(3, dtype=complex)
        for seq in range(3):
            z = getattr(source, f"z{seq}")
            if z is not None:
                e = network.prefault_voltage if seq == 1 else 0j
                values[seq] = (e - bus_seq[source.bus][seq]) / z
        source_currents[source.name] = sequence_to_phase(values)
    branch_currents = {}
    for branch in network.branches:
        values = np.zeros(3, dtype=complex)
        for seq in range(3):
            z = getattr(branch, f"z{seq}")
            if z is not None:
                values[seq] = (bus_seq[branch.from_bus][seq] - bus_seq[branch.to_bus][seq]) / z
        branch_currents[branch.name] = sequence_to_phase(values)
    return FaultResult(
        fault_type,
        bus,
        zf,
        current,
        sequence_to_phase(current),
        {name: sequence_to_phase(v) for name, v in bus_seq.items()},
        source_currents,
        branch_currents,
        network.base_current_a,
    )
