"""Build cutter-centre paths directly, then post explicit linear G-code."""

from math import ceil, hypot

from shapely.geometry import LineString, Point, Polygon, box

from .materials import cutting_data
from .model import Job


def depths(total: float, step: float) -> list[float]:
    """No repeated zero pass or overshoot when depth is not divisible by step."""
    return [-min(total, i * step) for i in range(1, ceil(total / step) + 1)]


def outline_path(job: Job) -> list[tuple[float, float]]:
    # Mitred corners deliberately avoid approximating arcs with gouging chords.
    return list(Polygon(job.outline).buffer(job.diameter / 2, join_style="mitre").exterior.coords)


def profile_entry(job: Job, path: list) -> tuple[float, float]:
    """Tangent extension before the longest edge; reorder to use that edge first."""
    edges = [(hypot(b[0] - a[0], b[1] - a[1]), i)
             for i, (a, b) in enumerate(zip(path, path[1:]))]
    _, index = max(edges)
    ring = path[:-1]
    ring = ring[index:] + ring[:index]
    path[:] = ring + [ring[0]]
    a, b = path[:2]
    length = hypot(b[0] - a[0], b[1] - a[1])
    entry = (a[0] - (b[0] - a[0]) / length * job.lead_length,
             a[1] - (b[1] - a[1]) / length * job.lead_length)
    r = job.diameter / 2
    if not box(r, r, job.stock[0] - r, job.stock[1] - r).covers(
        Point(entry)
    ):
        raise ValueError("Profile lead-in does not fit the stock; shorten lead_length")
    if LineString([entry, a]).distance(Polygon(job.outline)) < r - 1e-6:
        raise ValueError("Profile lead-in would gouge the outline; change the outline or lead")
    return entry


def generate(job: Job) -> str:
    job.validate()
    data = cutting_data(job.material, job.diameter, job.flutes, job.max_rpm)
    lines = ["(Bracket CAM - mm - stock top Z0 - corner XY0)",
             "(One centre-cutting end mill; hole diameter equals tool diameter)",
             "G21 G17 G90 G94 G40 G49 G80 G54", f"G0 Z{job.safe_z:.3f}",
             f"S{data['rpm']} M3"]

    def comment(label):
        lines.append(f"({label})")

    def move(code, *, x=None, y=None, z=None, feed=None):
        words = [code]
        for axis, value in (("X", x), ("Y", y), ("Z", z), ("F", feed)):
            if value is not None:
                words.append(f"{axis}{value:.3f}")
        lines.append(" ".join(words))

    def retract():
        # Feed out of stock: the checker intentionally treats every below-top rapid as unsafe.
        move("G1", z=job.safe_z, feed=data["plunge"])

    r = job.diameter / 2
    x0, y0, x1, y1 = job.pocket
    x0, y0, x1, y1 = x0 + r, y0 + r, x1 - r, y1 - r
    count = ceil((y1 - y0) / job.stepover)
    rows = [y0 + (y1 - y0) * i / count for i in range(count + 1)]
    comment("POCKET - ramp lead-in, raster clearing, wall finish")
    previous = 0.0
    for depth in depths(job.pocket_depth, job.stepdown):
        comment(f"POCKET depth {depth:.3f}")
        move("G0", x=x0, y=y0)
        move("G1", z=previous, feed=data["plunge"])
        # Repeated traverses limit the ramp to 3 degrees even in a narrow pocket.
        ramp_steps = max(1, ceil(abs(depth - previous) / ((x1 - x0) * 0.0524)))
        current_x = x0
        for i in range(1, ramp_steps + 1):
            current_x = x1 if current_x == x0 else x0
            move("G1", x=current_x, z=previous + (depth - previous) * i / ramp_steps,
                 feed=data["plunge"])
        move("G1", x=x0, feed=data["feed"])
        for i, y in enumerate(rows):
            move("G1", y=y, feed=data["feed"])
            move("G1", x=x1 if i % 2 == 0 else x0, feed=data["feed"])
        # Complete all four walls at full depth, leaving radius-r inside corners.
        for x, y in ((x1, y1), (x0, y1), (x0, y0), (x1, y0), (x1, y1)):
            move("G1", x=x, y=y, feed=data["feed"])
        retract()
        previous = depth

    comment("HOLES - explicit peck drilling with the same centre-cutting end mill")
    for x, y in job.holes:
        move("G0", x=x, y=y)
        for depth in depths(job.hole_depth, min(job.peck, job.stepdown)):
            move("G1", z=depth, feed=data["plunge"])
            retract()

    path = outline_path(job)
    entry = profile_entry(job, path)
    comment("OUTLINE - radius offset, tangent lead-in, retention floor")
    for depth in depths(job.profile_depth, job.stepdown):
        comment(f"OUTLINE depth {depth:.3f}")
        move("G0", x=entry[0], y=entry[1])
        move("G1", z=depth, feed=data["plunge"])
        for x, y in path:
            move("G1", x=x, y=y, feed=data["feed"])
        retract()
    lines.extend(["M5", "M30"])
    return "\n".join(lines) + "\n"
