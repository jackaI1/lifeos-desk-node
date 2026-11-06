"""Selected positive-flow OIML R 46:2012 class B checks at reference conditions."""

import math
from dataclasses import dataclass

SOURCE_URL = "https://www.oiml.org/en/files/pdf_r/r046-1-2-e12.pdf"
I_MIN, I_TR, I_MAX = 0.4, 1.0, 50.0  # Chosen direct-connected simulation rating, amperes.


def class_b_limit(current_a: float, power_factor: float, leading: bool = False) -> float:
    """Table 2, printed page 17. Return a percent, not a fractional error."""
    minimum_pf = 0.8 if leading else 0.5
    if not (I_MIN <= current_a <= I_MAX and minimum_pf <= power_factor <= 1):
        raise ValueError("point outside the selected class B current or power-factor range")
    low_current = current_a < I_TR
    if power_factor == 1:
        return 1.5 if low_current else 1.0
    return 1.8 if low_current else 1.5


@dataclass(frozen=True)
class TestPoint:
    __test__ = False
    id: str
    phases: int
    current_a: float
    power_factor: float
    leading: bool = False
    point_source: str = "OIML R 46:2012 Table 10, p.34; selected positive-flow point"

    def __post_init__(self):
        if (
            self.phases not in (1, 3)
            or not math.isfinite(self.current_a)
            or self.current_a < 0
            or not 0 < self.power_factor <= 1
        ):
            raise ValueError("expected 1 or 3 phases, nonnegative current and 0 < PF <= 1")

    @property
    def limit_pct(self) -> float:
        return class_b_limit(self.current_a, self.power_factor, self.leading)

    @property
    def limit_source(self) -> str:
        band = "Imin <= I < Itr" if self.current_a < I_TR else "Itr <= I <= Imax"
        pf = "unity" if self.power_factor == 1 else "non-unity"
        return f"OIML R 46:2012 Table 2, p.17; class B, {band}, {pf}"

    @property
    def source_url(self) -> str:
        return SOURCE_URL


def default_points() -> tuple[TestPoint, ...]:
    points = []
    for phases in (1, 3):
        for current in (I_MIN, I_TR, 10.0, I_MAX):
            for pf, leading, name in (
                (1.0, False, "unity"),
                (0.5, False, "lag"),
                (0.8, True, "lead"),
            ):
                source = "OIML R 46:2012 Table 10, p.34; selected positive-flow point"
                if current == I_MIN and pf != 1:
                    source = "additional low-current check within OIML R 46:2012 Table 2 range"
                elif current == 10:
                    source += "; 10 A is my interior choice, not an authority selection"
                points.append(
                    TestPoint(
                        f"{phases}ph-{current:g}A-{name}", phases, current, pf, leading, source
                    )
                )
    return tuple(points)
