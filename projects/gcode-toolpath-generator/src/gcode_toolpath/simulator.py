"""Independent, fail-closed parser and swept cutter-envelope check.

This deliberately does not model removed material: any rapid below the original
stock top is flagged, even in a previously cleared pocket. Start parked at
(radius, radius, safe_z) in the selected G54 work coordinate system.
"""

import re
from dataclasses import asdict, dataclass, field
from math import dist, isfinite

WORD = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))")
SETUP = {17, 21, 90, 94, 40, 49, 80, 54}


@dataclass(frozen=True)
class Move:
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    rapid: bool
    feed: float
    line: int


@dataclass
class Report:
    moves: list[Move] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    cutting_mm: float = 0
    rapid_mm: float = 0
    estimated_minutes: float = 0

    @property
    def ok(self) -> bool:
        return not self.issues

    def summary(self) -> dict:
        return {"ok": self.ok, "moves": len(self.moves), "issues": self.issues,
                "cutting_mm": round(self.cutting_mm, 3), "rapid_mm": round(self.rapid_mm, 3),
                "estimated_minutes": round(self.estimated_minutes, 3),
                "bounds": {axis: [min(p[i] for m in self.moves for p in (m.start, m.end)),
                                   max(p[i] for m in self.moves for p in (m.start, m.end))]
                           for i, axis in enumerate("XYZ")} if self.moves else {},
                "assumptions": "solid stock envelope; no fixtures, holder or material removal; "
                               "initial XYZ = (tool radius, tool radius, safe_z); "
                               "rapid speed assumed 2000 mm/min; setup time excluded"}

    def move_dicts(self) -> list[dict]:
        return [asdict(m) for m in self.moves]


def simulate(program: str, stock: tuple, diameter: float, safe_z: float) -> Report:
    if (len(stock) != 3 or not all(isfinite(v) and v > 0 for v in (*stock, diameter, safe_z))
            or diameter > min(stock[:2])):
        raise ValueError("Invalid simulation stock, diameter or clearance")
    report = Report()
    radius = diameter / 2
    position = (radius, radius, safe_z)
    modal = None
    feed = 0.0
    spindle = False
    rpm = 0.0
    setup = set()
    ended = False
    for number, raw in enumerate(program.splitlines(), 1):
        def issue(message):
            report.issues.append(f"Line {number}: {message}")

        # Nested/unclosed comments are rejected rather than masking code.
        text = re.sub(r"\([^()]*\)", "", raw.upper()).split(";", 1)[0].strip()
        if not text:
            continue
        words = list(WORD.finditer(text))
        remainder = WORD.sub("", text).strip()
        if remainder or not words:
            issue("Unsupported or malformed syntax")
            break
        if ended:
            issue("Code after M30")
            break
        values = {}
        gcodes, mcodes = [], []
        invalid = False
        for word in words:
            letter, value = word.group(1), float(word.group(2))
            if not isfinite(value) or letter not in "GMXYZFS":
                invalid = True
            elif letter == "G":
                gcodes.append(value)
            elif letter == "M":
                mcodes.append(value)
            elif letter in values:
                invalid = True
            else:
                values[letter] = value
        if (invalid or any(g not in SETUP | {0, 1} for g in gcodes)
                or any(m not in {3, 5, 30} for m in mcodes)
                or len(set(gcodes)) != len(gcodes)
                or sum(g in {0, 1, 80} for g in gcodes) > 1 or len(mcodes) > 1):
            issue("Unsupported or conflicting words; only the documented G0/G1 dialect is checked")
            break
        setup.update(g for g in gcodes if g in SETUP)
        if "S" in values:
            rpm = values["S"]
            if rpm <= 0:
                issue("Spindle speed must be positive")
        if 3 in mcodes:
            spindle = True
        if 5 in mcodes:
            spindle = False
        if 30 in mcodes:
            ended = True
            if any(a in values for a in "XYZ"):
                issue("Motion on M30 is not supported")
                break
        if "F" in values:
            feed = values["F"]
            if feed <= 0:
                issue("Feed must be positive")
        for g in gcodes:
            if g == 80:
                modal = None
            elif g in {0, 1}:
                modal = g
        if not any(axis in values for axis in "XYZ"):
            continue
        if not SETUP.issubset(setup) or modal is None:
            issue("Motion requires explicit G21 G17 G90 G94 G40 G49 G80 G54 and G0/G1")
            break
        target = tuple(values.get(axis, position[i]) for i, axis in enumerate("XYZ"))
        rapid = modal == 0
        if not rapid and (feed <= 0 or not spindle or rpm <= 0):
            issue("Feed move requires positive F and S with M3 spindle on")
        # Linear interpolation and a rectangular stock make endpoint bounds sufficient.
        # Check the whole cutter disk in XY, not just its centre.
        for point in (position, target):
            if (point[0] < radius - 1e-3 or point[0] > stock[0] - radius + 1e-3
                    or point[1] < radius - 1e-3 or point[1] > stock[1] - radius + 1e-3
                    or point[2] < -stock[2] - 1e-3 or point[2] > safe_z + 1e-3):
                issue("Cutter envelope leaves stock XY, stock bottom or clearance ceiling")
                break
        if rapid and min(position[2], target[2]) < -1e-6:
            issue("Rapid through original stock envelope below Z0")
        distance = dist(position, target)
        report.moves.append(Move(position, target, rapid, feed, number))
        if rapid:
            report.rapid_mm += distance
        else:
            report.cutting_mm += distance
        speed = 2000 if rapid else feed
        if speed > 0:
            report.estimated_minutes += distance / speed
        position = target
    if not ended:
        report.issues.append("Missing M30 program end")
    if not report.moves:
        report.issues.append("Program contains no moves")
    if ended and (position[2] < safe_z - 1e-3 or spindle):
        report.issues.append("Program must finish at clearance height with spindle stopped")
    return report
