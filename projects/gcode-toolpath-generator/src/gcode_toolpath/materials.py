"""Illustrative carbide starting values, not qualified machining recipes."""

from dataclasses import dataclass
from math import floor, pi


@dataclass(frozen=True)
class Material:
    surface_m_min: float
    chip_mm: float
    plunge_fraction: float
    max_stepdown_diameter: float


MATERIALS = {
    "aluminum_6061": Material(120, 0.015, 0.25, 0.25),
    "acetal": Material(150, 0.035, 0.30, 0.50),
    "mild_steel": Material(30, 0.008, 0.20, 0.15),
}


def cutting_data(material: str, diameter: float, flutes: int, max_rpm: float) -> dict:
    data = MATERIALS[material]
    rpm = min(floor(max_rpm), round(1000 * data.surface_m_min / (pi * diameter)))
    # Calculate feed from the integer spindle speed actually emitted in the program.
    feed = round(rpm * flutes * data.chip_mm, 3)
    return {"rpm": rpm, "feed": feed,
            "plunge": round(feed * data.plunge_fraction, 3)}
