"""Conservative, axis-aligned geometry comparison. Candidates require human review."""

import csv
import itertools
import math
import shutil
import tempfile
from pathlib import Path

import FreeCAD as App
import Part

from .bom import safe_text
from .geometry import require_current_solid


def signature(obj):
    shape = require_current_solid(obj)
    box = shape.BoundBox
    origin = App.Vector(box.XMin, box.YMin, box.ZMin)
    holes = []
    for face in shape.Faces:
        surface = face.Surface
        # Topological orientation alone differs between Boolean cuts and PartDesign pads.
        # A bore has material radially outside its surface and empty space towards its axis.
        if isinstance(surface, Part.Cylinder):
            u0, u1, v0, v1 = face.ParameterRange
            point_on_face = face.valueAt((u0 + u1) / 2, (v0 + v1) / 2)
            radial = point_on_face - surface.Center
            radial = radial - surface.Axis * radial.dot(surface.Axis)
            radial.normalize()
            epsilon = min(surface.Radius * 0.001, 0.01)
            if not shape.isInside(point_on_face + radial * epsilon, 1e-8, True) or shape.isInside(
                point_on_face - radial * epsilon, 1e-8, True
            ):
                continue
            axis = surface.Axis
            if next((v for v in (axis.x, axis.y, axis.z) if abs(v) > 1e-8), 1) < 0:
                axis = -axis
            center = surface.Center - origin
            point = center - axis * center.dot(axis)
            descriptor = (surface.Radius, point.x, point.y, point.z, axis.x, axis.y, axis.z)
            rounded = tuple(round(v, 7) for v in descriptor)
            if rounded not in holes:
                holes.append(rounded)
    return dict(
        box=(box.XLength, box.YLength, box.ZLength), volume=shape.Volume, holes=sorted(holes)
    )


def compare(a, b, *, box_tolerance=0.25, volume_tolerance=0.01, hole_tolerance=0.25):
    """Return measured differences if all gates pass, otherwise None.

    Length tolerances are absolute mm; volume tolerance is a relative fraction.
    Circular bores are compared in the part's axis-aligned bounding-box frame.
    """
    if any(
        not math.isfinite(v) or v < 0 for v in (box_tolerance, volume_tolerance, hole_tolerance)
    ):
        raise ValueError("Tolerances must be finite and nonnegative")
    box_delta = max(abs(x - y) for x, y in zip(a["box"], b["box"]))
    volume_delta = abs(a["volume"] - b["volume"]) / max(a["volume"], b["volume"])
    if box_delta > box_tolerance or volume_delta > volume_tolerance:
        return None
    if len(a["holes"]) != len(b["holes"]):
        return None
    # Match as a set rather than sorting by a noisy floating-point radius.
    remaining = list(b["holes"])
    for hole in a["holes"]:
        for index, other in enumerate(remaining):
            if (
                max(abs(x - y) for x, y in zip(hole[:4], other[:4])) <= hole_tolerance
                and max(abs(x - y) for x, y in zip(hole[4:], other[4:])) <= 1e-6
            ):
                remaining.pop(index)
                break
        else:
            return None
    return dict(
        box_delta_mm=box_delta, volume_delta_fraction=volume_delta, hole_count=len(a["holes"])
    )


def scan_library(directory, **tolerances):
    """Read real FCStd solids, close owned documents, fail visibly on unreadable files."""
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError("Library directory does not exist")
    files = sorted(directory.glob("*.FCStd"))
    if not files:
        raise ValueError("Library contains no FCStd files")
    # Opening an already-open filename returns the owner's document in FreeCAD.
    # Work on copied disk bytes, preserving both owner tabs and unsaved edits.
    records = []
    for path in files:
        with tempfile.TemporaryDirectory(prefix="freecad-library-") as temporary:
            copy = Path(temporary) / path.name
            shutil.copyfile(path, copy)
            document = None
            try:
                document = App.openDocument(str(copy))
                document.recompute()
                candidates = []
                for obj in document.Objects:
                    if (
                        not hasattr(obj, "Shape")
                        or obj.isDerivedFrom("App::Link")
                        or obj.isDerivedFrom("Sketcher::SketchObject")
                    ):
                        continue
                    # Body.Shape is the terminal solid; its sketches, axes and history are inputs.
                    parents = obj.InListRecursive
                    if any(parent.isDerivedFrom("PartDesign::Body") for parent in parents):
                        continue
                    if any(
                        hasattr(parent, "Shape") and not parent.isDerivedFrom("App::Part")
                        for parent in obj.InList
                    ):
                        continue
                    if obj.Shape.isNull() and not hasattr(obj, "PartId"):
                        continue
                    if not obj.Shape.Solids and not hasattr(obj, "PartId"):
                        continue
                    candidates.append(obj)
                if not candidates:
                    raise ValueError("No library solids")
                for obj in candidates:
                    records.append((f"{path.name}:{obj.Name}", signature(obj)))
            except Exception as error:
                raise ValueError(f"Could not inspect {path.name}: {error}") from error
            finally:
                if document is not None:
                    App.closeDocument(document.Name)
    results = []
    for (name_a, a), (name_b, b) in itertools.combinations(records, 2):
        differences = compare(a, b, **tolerances)
        if differences is not None:
            results.append(
                dict(
                    part_a=name_a,
                    part_b=name_b,
                    **differences,
                    decision="Review for reuse; not interchangeable approval",
                )
            )
    return results


def write_report(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = (
        "part_a",
        "part_b",
        "box_delta_mm",
        "volume_delta_fraction",
        "hole_count",
        "decision",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: safe_text(value) if isinstance(value, str) else value
                    for key, value in row.items()
                }
            )
