"""SI-unit models for coaxial circular turns; derivations in docs/models.md."""

from dataclasses import dataclass
from math import asinh, cosh, isfinite, log, pi, sinh, sqrt
from numbers import Integral, Real

import mpmath
import numpy as np
from scipy.integrate import quad
from scipy.special import ellipe, ellipkm1

MU0 = 4 * pi * 1e-7  # Engineering approximation, H/m.


def _dimension(name: str, value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not isfinite(value)
        or not 1e-6 <= value <= 1000
    ):
        raise ValueError(f"{name} must be finite, from 0.000001 to 1000 metres.")


@dataclass(frozen=True)
class Coil:
    """Equal turn counts per layer, same direction, aligned axial turn centres.

    length_m = turns_per_layer * axial pitch, not first-to-last centre distance.
    mean_radius_m is the average of the innermost/outermost wire-centre radii.
    wire_diameter_m is bare round conductor diameter. Pitches include insulation.
    """

    mean_radius_m: float
    length_m: float
    turns_per_layer: int
    layers: int = 1
    wire_diameter_m: float = 0.001
    radial_pitch_m: float | None = None

    def __post_init__(self):
        for name in ("mean_radius_m", "length_m", "wire_diameter_m"):
            _dimension(name, getattr(self, name))
        for name, limit in (("turns_per_layer", 2000), ("layers", 20)):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or not 1 <= value <= limit
            ):
                raise ValueError(f"{name} must be a whole number from 1 to {limit}.")
        if self.turns > 2000:
            raise ValueError("At most 2000 total turns are supported.")
        pitch = self.wire_diameter_m if self.radial_pitch_m is None else self.radial_pitch_m
        _dimension("radial_pitch_m", pitch)
        object.__setattr__(self, "radial_pitch_m", pitch)
        if self.length_m / self.turns_per_layer < self.wire_diameter_m * (1 - 1e-12):
            raise ValueError(
                "Wire overlaps axially: increase winding length or reduce wire diameter."
            )
        if self.layers > 1 and pitch < self.wire_diameter_m:
            raise ValueError("Radial pitch must be at least the bare wire diameter.")
        if self.layer_radii[0] <= self.wire_diameter_m / 2:
            raise ValueError("The inner wire surface must stay outside the coil axis.")
        for radius in self.layer_radii:
            _dimension("layer radius", radius)
        if self.wire_diameter_m / (2 * self.layer_radii[0]) > 0.1:
            raise ValueError("The thin-wire model needs wire radius <= 10% of inner turn radius.")

    @property
    def turns(self) -> int:
        return self.turns_per_layer * self.layers

    @property
    def layer_radii(self) -> tuple[float, ...]:
        return tuple(
            self.mean_radius_m + (i - (self.layers - 1) / 2) * self.radial_pitch_m
            for i in range(self.layers)
        )

    @property
    def depth_m(self) -> float:
        return (self.layers - 1) * self.radial_pitch_m + self.wire_diameter_m


def wheeler_inductance(coil: Coil) -> float:
    """Wheeler 1928 formulas: inch dimensions, microhenry output converted to H."""
    r, length, depth = (x / 0.0254 for x in (coil.mean_radius_m, coil.length_m, coil.depth_m))
    if coil.layers == 1:
        return r * r * coil.turns**2 / (9 * r + 10 * length) * 1e-6
    return 0.8 * r * r * coil.turns**2 / (6 * r + 9 * length + 10 * depth) * 1e-6


def nagaoka_coefficient(radius_m: float, length_m: float) -> float:
    """Exact current-sheet end-effect coefficient, with elliptic parameter m=k².

    Local arbitrary precision avoids cancellation for very long/short solenoids;
    no process-global precision settings are changed in Flask's threaded use.
    """
    _dimension("radius_m", radius_m)
    _dimension("length_m", length_m)
    mp = mpmath.mp.clone()
    mp.dps = 60
    u = 2 * mp.mpf(radius_m) / mp.mpf(length_m)
    m = u * u / (1 + u * u)
    k, e = mp.ellipk(m), mp.ellipe(m)
    coefficient = (
        4 / (3 * mp.pi * mp.sqrt(1 - m)) * ((1 - m) / m * k + (2 * m - 1) / m * e - mp.sqrt(m))
    )
    return float(coefficient)


def mutual_inductance(radius_a: float, radius_b: float, separation_m):
    """Maxwell's coaxial filament mutual inductance, scalar or array of z.

    Use the complementary parameter directly near coincident circles, and a
    small-m series in the far field to avoid subtracting nearly equal K and E.
    """
    _dimension("radius_a", radius_a)
    _dimension("radius_b", radius_b)
    z = np.asarray(separation_m, dtype=float)
    if not np.all(np.isfinite(z)):
        raise ValueError("Filament separation must be finite.")
    distance2 = (radius_a + radius_b) ** 2 + z * z
    complement = ((radius_a - radius_b) ** 2 + z * z) / distance2
    if np.any(complement == 0):
        raise ValueError("Use the finite-wire self model for coincident filaments.")
    m = np.clip(4 * radius_a * radius_b / distance2, 0.0, 1.0)
    small = m < 0.001
    # ((2-m)K(m)-2E(m))/sqrt(m) = pi*m**1.5/16*(1+3m/4+75m²/128+...).
    series = pi / 16 * m**1.5 * (1 + 0.75 * m + 75 / 128 * m * m + 245 / 512 * m**3)
    exact = ((2 - m) * ellipkm1(complement) - 2 * ellipe(m)) / np.sqrt(m)
    result = MU0 * sqrt(radius_a * radius_b) * np.where(small, series, exact)
    return float(result) if result.ndim == 0 else result


def self_inductance(radius_m: float, wire_diameter_m: float) -> float:
    """Thin circular loop, uniform low-frequency current, including internal L."""
    _dimension("radius_m", radius_m)
    _dimension("wire_diameter_m", wire_diameter_m)
    if wire_diameter_m / (2 * radius_m) > 0.1:
        raise ValueError("Wire radius must be <= 10% of loop radius.")
    return MU0 * radius_m * (log(16 * radius_m / wire_diameter_m) - 1.75)


def nagaoka_inductance(coil: Coil) -> float:
    """Nagaoka self sheets plus integrated interlayer sheet mutual inductance.

    One sheet per layer at the wire-centre radius. Integration over both axial
    coordinates reduces to 2/l² integral_0^l (l-z) M(r1,r2,z) dz.
    """
    length, n = coil.length_m, coil.turns_per_layer
    radii = coil.layer_radii
    total = sum(MU0 * n * n * pi * r * r / length * nagaoka_coefficient(r, length) for r in radii)
    for i, a in enumerate(radii):
        for b in radii[i + 1 :]:
            # A linear interval can miss all coupling near zero for long coils.
            # z = gap*sinh(u) resolves both radial gaps and the far-field tail.
            gap = b - a
            scale = MU0 * sqrt(a * b)

            def kernel(u, a=a, b=b, gap=gap, scale=scale):
                z = gap * sinh(u)
                return (
                    (1 - z / length) * (mutual_inductance(a, b, z) / scale) * gap * cosh(u) / length
                )

            sheet_mutual = (
                2 * scale * quad(kernel, 0.0, asinh(length / gap), epsabs=1e-20, epsrel=2e-9)[0]
            )
            total += 2 * n * n * sheet_mutual
    return total


def filament_inductance(coil: Coil) -> float:
    """Σ Lself + 2 Σ(i<j) Mij, grouping identical axial separations.

    Exact pair counts for the circular-turn approximation, O(layers²*turns/layer)
    work and O(turns/layer) storage. No singular self mutual-inductance call.
    """
    n = coil.turns_per_layer
    offsets = np.arange(1, n)
    z = offsets * coil.length_m / n
    weights = n - offsets
    radii = coil.layer_radii
    total = 0.0
    for i, a in enumerate(radii):
        total += n * self_inductance(a, coil.wire_diameter_m)
        total += 2 * float(np.sum(weights * mutual_inductance(a, a, z)))
        for b in radii[i + 1 :]:
            between = n * mutual_inductance(a, b, 0.0)
            between += 2 * float(np.sum(weights * mutual_inductance(a, b, z)))
            total += 2 * between
    return total
