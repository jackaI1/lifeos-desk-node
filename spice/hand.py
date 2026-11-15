"""Hand calculations for the desk node's power and I2C netlists.

Each function is a textbook result written out in one line, so the ngspice
numbers have something independent to be compared against. Units are SI:
ohm, farad, henry, volt, ampere, second.
"""

import math

# 30 %-70 % rise time of a first-order RC step: t = RC (-ln 0.3 + ln 0.7) = RC ln(7/3).
RISE_30_70_FACTOR = math.log(7.0 / 3.0)   # 0.8473


def rc_time_constant(resistance_ohm: float, capacitance_f: float) -> float:
    """tau = R C, the time to reach 63 % of a step."""
    return resistance_ohm * capacitance_f


def inrush_peak_ramp(v_step: float, r_series: float, c_load: float, t_rise: float) -> float:
    """Peak charging current of C through R from a source that ramps linearly to v_step.

    While the source ramps, i(t) = (V C / t_r) (1 - e^(-t/RC)), which peaks at t = t_r.
    A step (t_r -> 0) would give V/R only if the RC is much shorter than the ramp, so
    the ramp time matters here.
    """
    tau = rc_time_constant(r_series, c_load)
    return (v_step * c_load / t_rise) * (1.0 - math.exp(-t_rise / tau))


def input_voltage_under_load(v_source: float, i_load: float, r_series: float) -> float:
    """Resistive divider from the USB source through the cable and fuse: V = V_s - I R."""
    return v_source - i_load * r_series


def load_step_droop(i_step: float, r_out: float) -> float:
    """Steady-state output drop for a load step behind an output resistance: dV = I R."""
    return i_step * r_out


def burst_ripple_pp(i_burst: float, r_out: float, c_out: float, t_on: float) -> float:
    """Peak-to-peak ripple from one burst of current on an RC output.

    The output follows I R (1 - e^(-t_on / RC)) during a burst of length t_on.
    """
    return i_burst * r_out * (1.0 - math.exp(-t_on / rc_time_constant(r_out, c_out)))


def rise_time_30_70(r_pullup: float, c_bus: float) -> float:
    """30 %-70 % rise time of an open-drain line pulled up through R_pu onto C_bus."""
    return RISE_30_70_FACTOR * rc_time_constant(r_pullup, c_bus)


def max_pullup_for_rise(t_limit_s: float, c_bus: float) -> float:
    """Largest pull-up that still meets a 30 %-70 % rise limit on a bus of c_bus."""
    return t_limit_s / (RISE_30_70_FACTOR * c_bus)


def min_pullup_for_sink(v_dd: float, v_ol_max: float, i_ol_min: float) -> float:
    """Smallest pull-up that lets the driver hold VOL at I_OL: R >= (VDD - VOL) / I_OL."""
    return (v_dd - v_ol_max) / i_ol_min
