"""Balanced three-phase, bolted-fault, positive-sequence circuit example."""

from math import hypot, isfinite, pi, sqrt
from numbers import Real


def fault_current(
    inductance_h: float,
    *,
    voltage_kv: float = 11.0,
    base_mva: float = 10.0,
    frequency_hz: float = 60.0,
    source_r_pu: float = 0.01,
    source_x_pu: float = 0.1,
) -> dict[str, float]:
    """One identical series reactor per phase, 1 pu prefault Thevenin voltage.

    Zbase = V_LL²/S_3phase; Ibase = S_3phase/(sqrt(3)*V_LL).
    R+jX and j*2*pi*f*L are added on this same base. No DC offset, load, motor
    contribution, capacitance, thermal or mechanical ratings are modelled.
    """
    inputs = dict(
        inductance_h=inductance_h,
        voltage_kv=voltage_kv,
        base_mva=base_mva,
        frequency_hz=frequency_hz,
        source_r_pu=source_r_pu,
        source_x_pu=source_x_pu,
    )
    for name, value in inputs.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not isfinite(value)
            or not 0 <= value <= 1e9
        ):
            raise ValueError(f"{name} must be finite, from 0 to 1,000,000,000.")
    if min(voltage_kv, base_mva, frequency_hz) < 1e-9:
        raise ValueError("Voltage, power base and frequency must be at least 0.000000001.")
    if hypot(source_r_pu, source_x_pu) < 1e-12:
        raise ValueError("Source impedance magnitude must be at least 0.000000000001 pu.")
    z_base = voltage_kv**2 / base_mva  # kV²/MVA is ohms.
    i_base = base_mva * 1e3 / (sqrt(3) * voltage_kv)
    x_ohm = 2 * pi * frequency_hz * inductance_h
    x_pu = x_ohm / z_base
    before = 1 / hypot(source_r_pu, source_x_pu)
    after = 1 / hypot(source_r_pu, source_x_pu + x_pu)
    return dict(
        base_impedance_ohm=z_base,
        base_current_a=i_base,
        reactor_x_ohm=x_ohm,
        reactor_x_pu=x_pu,
        before_pu=before,
        after_pu=after,
        before_a=before * i_base,
        after_a=after * i_base,
        reduction_percent=100 * (1 - after / before),
    )
