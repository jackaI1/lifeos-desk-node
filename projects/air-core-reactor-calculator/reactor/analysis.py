"""Model comparison and dimension-aware physical plausibility checks."""

from dataclasses import asdict
from math import isfinite, pi, sqrt

from .coils import (
    MU0,
    Coil,
    filament_inductance,
    nagaoka_inductance,
    self_inductance,
    wheeler_inductance,
)


def check_plausibility(coil: Coil, inductance_h: dict[str, float]) -> list[dict[str, str]]:
    """Flag impossible magnetic-energy bounds separately from model limitations.

    Same-direction coaxial loops have positive mutual inductance, so sum(self)
    is a lower bound. Cauchy-Schwarz gives Mij <= sqrt(Lii*Ljj), yielding an
    upper bound (sum sqrt(self))². A 2% allowance covers thin-wire approximation.
    These checks detect gross errors; they do not certify a physical reactor.
    """
    flags = []

    def flag(code, severity, message):
        flags.append(dict(code=code, severity=severity, message=message))

    self_terms = [self_inductance(r, coil.wire_diameter_m) for r in coil.layer_radii]
    lower = coil.turns_per_layer * sum(self_terms)
    upper = (coil.turns_per_layer * sum(sqrt(value) for value in self_terms)) ** 2
    long_sheet = MU0 * coil.turns**2 * pi * max(coil.layer_radii) ** 2 / coil.length_m
    for method, value in inductance_h.items():
        if not isfinite(value) or value <= 0:
            flag(
                "invalid_inductance", "error", f"{method}: inductance must be finite and positive."
            )
        elif method == "filament" and not 0.98 * lower <= value <= 1.02 * upper:
            flag(
                "energy_bound",
                "error",
                "Filament result is outside same-direction loop energy "
                "bounds. Check units, pair counts and the wire self term.",
            )
        elif method == "nagaoka" and value > long_sheet * 1.00001:
            flag(
                "sheet_bound",
                "error",
                "Nagaoka exceeds the outer-radius long-solenoid bound. Check geometry and units.",
            )
    valid = [value for value in inductance_h.values() if isfinite(value) and value > 0]
    if len(valid) > 1 and (max(valid) - min(valid)) / max(valid) > 0.1:
        flag(
            "model_disagreement",
            "warning",
            "Models differ by more than 10% of the largest "
            "estimate. Review winding density and formula assumptions before using a result.",
        )
    if coil.turns_per_layer < 10 or coil.length_m / coil.turns_per_layer > 0.1 * coil.mean_radius_m:
        flag(
            "sparse_winding",
            "warning",
            "Few or widely spaced turns: current sheets and Wheeler "
            "can disagree with the discrete winding. Prefer the filament estimate.",
        )
    if coil.wire_diameter_m / (2 * min(coil.layer_radii)) > 0.05:
        flag(
            "thick_wire",
            "warning",
            "Wire radius exceeds 5% of the inner turn radius. "
            "The thin-wire self and mutual approximations lose accuracy.",
        )
    if coil.layers == 1 and coil.length_m <= 0.8 * coil.mean_radius_m:
        flag(
            "wheeler_range",
            "warning",
            "Short winding: outside Wheeler single-layer stated 1% range (length > 0.8 × radius).",
        )
    if coil.layers > 1:
        terms = [6 * coil.mean_radius_m, 9 * coil.length_m, 10 * coil.depth_m]
        if max(terms) > 2 * min(terms):
            flag(
                "wheeler_range",
                "warning",
                "Multilayer Wheeler accuracy is best when its "
                "three denominator terms are similar; this winding is outside that region.",
            )
    return flags


def analyze(coil: Coil) -> dict:
    values = dict(
        wheeler=wheeler_inductance(coil),
        nagaoka=nagaoka_inductance(coil),
        filament=filament_inductance(coil),
    )
    return dict(
        geometry=asdict(coil),
        total_turns=coil.turns,
        inductance_h=values,
        max_disagreement_percent=100
        * (max(values.values()) - min(values.values()))
        / max(values.values()),
        flags=check_plausibility(coil, values),
    )
