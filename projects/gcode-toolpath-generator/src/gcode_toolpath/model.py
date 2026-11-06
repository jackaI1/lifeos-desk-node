"""Validated job inputs, in mm; XY origin at stock corner, Z zero on its top."""

import json
from dataclasses import dataclass
from math import ceil, isfinite
from pathlib import Path

from shapely.geometry import Point, Polygon, box

from .materials import MATERIALS, cutting_data


@dataclass(frozen=True)
class Job:
    stock: tuple[float, float, float]
    outline: tuple[tuple[float, float], ...]
    pocket: tuple[float, float, float, float]  # xmin, ymin, xmax, ymax
    pocket_depth: float
    profile_depth: float
    holes: tuple[tuple[float, float], ...]
    hole_depth: float
    diameter: float
    stepdown: float
    stepover: float
    safe_z: float
    material: str
    flutes: int = 2
    max_rpm: float = 12000
    lead_length: float = 2
    peck: float = 0.5

    @classmethod
    def load(cls, path: str | Path) -> "Job":
        raw = json.loads(Path(path).read_text())
        for key in ("stock", "outline", "pocket", "holes"):
            raw[key] = tuple(tuple(p) if isinstance(p, list) else p for p in raw[key])
        job = cls(**raw)
        job.validate()
        return job

    def validate(self) -> None:
        numeric = [*self.stock, *self.pocket, self.pocket_depth, self.profile_depth,
                   self.hole_depth, self.diameter, self.stepdown, self.stepover, self.safe_z,
                   self.max_rpm, self.lead_length, self.peck,
                   *(v for p in (*self.outline, *self.holes) for v in p)]
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and isfinite(v) for v in numeric):
            raise ValueError("All dimensions must be finite numbers")
        if len(self.stock) != 3 or len(self.pocket) != 4:
            raise ValueError("Stock needs three dimensions; pocket needs four bounds")
        if any(len(p) != 2 for p in (*self.outline, *self.holes)):
            raise ValueError("Outline vertices and holes need two coordinates")
        if min(*self.stock, self.pocket_depth, self.profile_depth, self.hole_depth,
               self.diameter, self.stepdown, self.safe_z, self.max_rpm,
               self.lead_length, self.peck) <= 0:
            raise ValueError("Dimensions, depths, feeds and clearance must be positive")
        if not isinstance(self.flutes, int) or isinstance(self.flutes, bool) or self.flutes < 1:
            raise ValueError("Flutes must be a positive integer")
        if self.material not in MATERIALS:
            raise ValueError(f"Unknown material; choose from {', '.join(MATERIALS)}")
        if self.stepdown > self.diameter * MATERIALS[self.material].max_stepdown_diameter:
            raise ValueError("Stepdown exceeds this material table's limit")
        if not 0 < self.stepover <= self.diameter / 2:
            raise ValueError("Stepover must be positive and at most half the diameter")
        if min(self.stepdown, self.stepover, self.peck, self.diameter, self.pocket_depth,
               self.hole_depth, self.profile_depth, self.safe_z, self.lead_length) < 0.01:
            raise ValueError("Minimum supported increment is 0.01 mm")
        data = cutting_data(self.material, self.diameter, self.flutes, self.max_rpm)
        if min(data.values()) <= 0:
            raise ValueError("Spindle speed and feeds must remain positive after output rounding")
        if max(self.pocket_depth, self.hole_depth) > self.profile_depth:
            raise ValueError("Pocket and holes must not extend below the profile floor")
        if self.profile_depth > self.stock[2] - 0.2 + 1e-9:
            raise ValueError("Leave at least 0.2 mm of stock under the profile for retention")
        poly = Polygon(self.outline)
        if not poly.is_valid or poly.area <= 0:
            raise ValueError("Outline must be a simple polygon with positive area")
        if not poly.equals(poly.convex_hull):
            raise ValueError("Outline must be convex; inward notches are not supported")
        x0, y0, x1, y1 = self.pocket
        if x1 - x0 <= self.diameter or y1 - y0 <= self.diameter:
            raise ValueError("Pocket width and height must exceed the cutter diameter")
        if min(x1 - x0, y1 - y0) - self.diameter < 0.01 - 1e-9:
            raise ValueError("Pocket needs at least 0.01 mm of cutter-centre travel in each axis")
        if not poly.buffer(-0.01).covers(box(*self.pocket)):
            raise ValueError("Pocket must lie strictly inside the outline")
        radius = self.diameter / 2
        for i, hole in enumerate(self.holes):
            disk = Point(hole).buffer(radius + 0.01)
            if not poly.covers(disk) or disk.intersects(box(*self.pocket)):
                raise ValueError("Holes must fit inside the outline and outside the pocket")
            if any(Point(hole).distance(Point(other)) <= self.diameter + 0.01
                   for other in self.holes[:i]):
                raise ValueError("Holes must not overlap")
        # The outside compensated path plus the entire cutter must fit the stock.
        path = poly.buffer(radius, join_style="mitre")
        usable = box(radius, radius, self.stock[0] - radius, self.stock[1] - radius)
        if path.geom_type != "Polygon" or not usable.covers(path):
            raise ValueError("Compensated outline and cutter do not fit within the stock")
        # Bound work to keep malformed jobs from allocating millions of moves.
        rows = ceil((y1 - y0 - self.diameter) / self.stepover) + 1
        ramp = ceil(min(self.stepdown, self.pocket_depth)
                    / ((x1 - x0 - self.diameter) * 0.0524))
        estimate = (
            1 + ceil(self.pocket_depth / self.stepdown) * (ramp + 2 * rows + 9)
            + ceil(self.profile_depth / self.stepdown) * (len(path.exterior.coords) + 3)
            + len(self.holes) * (1 + 2 * ceil(self.hole_depth / min(self.peck, self.stepdown)))
        )
        if estimate > 100000:
            raise ValueError("Job exceeds the 100,000 move planning budget")
