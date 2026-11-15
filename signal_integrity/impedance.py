"""Closed-form impedance of a microstrip trace and of a through-hole via.

These are the standard published approximations, written out so each one can be
checked against its formula in the tests:

- Microstrip: Hammerstad-Jensen closed form (Pozar, "Microwave Engineering"),
  with the Wheeler thickness correction for finite copper.
- Via: coaxial approximation Z = 60/sqrt(er) * ln(D_antipad / D_drill). The
  antipad is the clearance hole in the ground plane around the via.

Lengths are in millimetres; impedances are in ohms.
"""

import math

ETA0 = 120.0 * math.pi   # free-space wave impedance, ohm


def thickness_corrected_width(w_mm: float, h_mm: float, t_mm: float) -> float:
    """Effective strip width for finite copper thickness t (Wheeler / Hammerstad).

    dw = (t / pi) (1 + ln(2 h / t)). Zero thickness returns the width unchanged.
    """
    if t_mm <= 0:
        return w_mm
    return w_mm + (t_mm / math.pi) * (1.0 + math.log(2.0 * h_mm / t_mm))


def effective_permittivity(u: float, er: float) -> float:
    """Effective relative permittivity of a microstrip with u = w/h (Pozar's form)."""
    term = (1.0 + 12.0 / u) ** -0.5
    if u < 1.0:
        term += 0.04 * (1.0 - u) ** 2
    return (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * term


def microstrip_z0(w_mm: float, h_mm: float, er: float, t_mm: float = 0.0) -> float:
    """Characteristic impedance of a microstrip over a ground plane (ohm).

    w_mm: trace width, h_mm: dielectric height, er: relative permittivity,
    t_mm: copper thickness (0 for a zero-thickness conductor).
    """
    if min(w_mm, h_mm, er) <= 0:
        raise ValueError("width, height and permittivity must be positive")
    w_eff = thickness_corrected_width(w_mm, h_mm, t_mm)
    u = w_eff / h_mm
    eps_eff = effective_permittivity(u, er)
    if u <= 1.0:
        return 60.0 / math.sqrt(eps_eff) * math.log(8.0 / u + u / 4.0)
    return ETA0 / (math.sqrt(eps_eff) * (u + 1.393 + 0.667 * math.log(u + 1.444)))


def width_for_z0(target_ohm: float, h_mm: float, er: float, t_mm: float = 0.0) -> float:
    """Trace width (mm) whose microstrip impedance equals target_ohm, by bisection.

    Impedance falls as the width grows, so the search is monotone.
    """
    lo, hi = 1e-3 * h_mm, 50.0 * h_mm
    if not microstrip_z0(hi, h_mm, er, t_mm) <= target_ohm <= microstrip_z0(lo, h_mm, er, t_mm):
        raise ValueError(f"no width in [{lo:.4g}, {hi:.4g}] mm gives {target_ohm} ohm")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if microstrip_z0(mid, h_mm, er, t_mm) > target_ohm:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def via_z0(drill_mm: float, antipad_mm: float, er: float) -> float:
    """Impedance of a through via in a ground-plane clearance hole (ohm).

    Coaxial approximation: the barrel is the inner conductor (drill diameter) and
    the antipad is the outer boundary, in the board's dielectric.
    """
    if not 0 < drill_mm < antipad_mm:
        raise ValueError("antipad must be larger than the drill")
    return 60.0 / math.sqrt(er) * math.log(antipad_mm / drill_mm)
