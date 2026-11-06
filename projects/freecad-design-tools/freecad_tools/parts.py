"""Millimetre-based parts driven by native Spreadsheet expressions."""

import csv
import math
import re
from pathlib import Path

import FreeCAD as App
import Part

FIELDS = {
    "plate": ("length", "width", "thickness", "hole_diameter", "pitch"),
    "bracket": ("length", "width", "thickness", "height", "hole_diameter", "pitch"),
    "spacer": ("outer_diameter", "hole_diameter", "height"),
}


def validate(kind, dimensions):
    if kind not in FIELDS:
        raise ValueError(f"Unknown part kind: {kind}")
    values = {name: float(dimensions[name]) for name in FIELDS[kind]}
    if any(not math.isfinite(value) or value <= 0 for value in values.values()):
        raise ValueError("Dimensions must be finite and greater than zero")
    if kind == "spacer":
        if values["hole_diameter"] >= values["outer_diameter"]:
            raise ValueError("Spacer bore must be smaller than its outside diameter")
    else:
        if values["pitch"] + values["hole_diameter"] >= values["length"]:
            raise ValueError("Holes must fit within the length with positive edge clearance")
        if values["hole_diameter"] >= values["width"]:
            raise ValueError("Holes must fit within the width")
        if values["thickness"] >= min(values["length"], values["width"]):
            raise ValueError("Thickness must be smaller than length and width")
        if kind == "bracket":
            if values["height"] <= values["thickness"]:
                raise ValueError("Bracket height must exceed thickness")
            if values["width"] / 2 - values["hole_diameter"] / 2 <= values["thickness"]:
                raise ValueError("Bracket holes must clear the upright leg")
    return values


def load_dimensions(path):
    """Read spreadsheet-exported CSV; reject the whole table before generating files."""
    rows, seen = [], set()
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        for number, row in enumerate(csv.DictReader(stream), 2):
            part_id = row.get("part_id", "")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}", part_id):
                raise ValueError(f"Row {number}: invalid part ID")
            if part_id.casefold() in seen:
                raise ValueError(f"Duplicate part ID: {part_id}")
            seen.add(part_id.casefold())
            kind = row.get("kind", "")
            try:
                dimensions = validate(kind, row)
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f"Row {number} ({part_id}): {error}") from error
            rows.append({"part_id": part_id, "kind": kind, "dimensions": dimensions})
    if not rows:
        raise ValueError("Dimension table has no parts")
    return rows


def _shape(kind, d):
    if kind == "spacer":
        return Part.makeCylinder(d["outer_diameter"] / 2, d["height"]).cut(
            Part.makeCylinder(d["hole_diameter"] / 2, d["height"])
        )
    length, width, thickness = d["length"], d["width"], d["thickness"]
    shape = Part.makeBox(length, width, thickness)
    if kind == "bracket":
        shape = shape.fuse(Part.makeBox(length, thickness, d["height"])).removeSplitter()
    for x in ((length - d["pitch"]) / 2, (length + d["pitch"]) / 2):
        shape = shape.cut(
            Part.makeCylinder(d["hole_diameter"] / 2, thickness, App.Vector(x, width / 2, 0))
        )
    return shape.removeSplitter()


class ParametricPart:
    """Reloadable proxy: expressions update dimensions before execute builds the solid."""

    def __init__(self, obj):
        obj.Proxy = self

    def execute(self, obj):
        try:
            dimensions = validate(
                obj.Kind, {name: getattr(obj, name).Value for name in FIELDS[obj.Kind]}
            )
            shape = _shape(obj.Kind, dimensions)
            if not shape.isValid() or len(shape.Solids) != 1:
                raise ValueError("Generated part must be a single valid solid")
            obj.Shape = shape
            obj.GenerationError = ""
        except Exception as error:
            obj.Shape = Part.Shape()
            obj.GenerationError = str(error)
            raise

    def dumps(self):
        return None

    def loads(self, state):
        pass


def make_part(doc, part_id, kind, dimensions, revision=1):
    dimensions = validate(kind, dimensions)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}", part_id):
        raise ValueError("Invalid part ID")
    if any(getattr(obj, "PartId", None) == part_id for obj in doc.Objects):
        raise ValueError(f"Duplicate part ID: {part_id}")
    sheet = doc.addObject("Spreadsheet::Sheet", "Dimensions_" + part_id)
    sheet.Label = part_id + " dimensions (mm)"
    obj = doc.addObject("Part::FeaturePython", part_id)
    for name, value in {
        "PartId": part_id,
        "Kind": kind,
        "Material": "Aluminium",
        "DimensionSheet": sheet.Name,
        "GenerationError": "",
    }.items():
        obj.addProperty("App::PropertyString", name, "Toolkit")
        setattr(obj, name, value)
        obj.setEditorMode(name, 1)
    obj.addProperty("App::PropertyInteger", "Revision", "Toolkit")
    obj.Revision = revision
    for row, (name, value) in enumerate(dimensions.items(), 1):
        sheet.set(f"A{row}", name)
        sheet.set(f"B{row}", str(value))
        sheet.setAlias(f"B{row}", name)
        obj.addProperty("App::PropertyLength", name, "Dimensions")
        obj.setExpression(name, f"{sheet.Name}.{name}")
    ParametricPart(obj)
    doc.recompute()
    if obj.GenerationError:
        raise ValueError(obj.GenerationError)
    if App.GuiUp:
        obj.ViewObject.ShapeColor = {
            "plate": (0.7, 0.75, 0.8),
            "bracket": (0.3, 0.55, 0.7),
            "spacer": (0.8, 0.65, 0.3),
        }[kind]
    return obj


def build_project(table, output):
    """Generate all variants and an eight-occurrence, exploded mounting-stack example."""
    rows = load_dimensions(table)
    by_kind = {kind: [row for row in rows if row["kind"] == kind] for kind in FIELDS}
    if any(not variants for variants in by_kind.values()):
        raise ValueError("Example assembly needs at least one plate, bracket and spacer")
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty; preserve existing designs")
    library = output / "library"
    library.mkdir(parents=True, exist_ok=True)
    for row in rows:
        document = App.newDocument("LibraryPart")
        try:
            make_part(document, row["part_id"], row["kind"], row["dimensions"])
            document.saveAs(str(library / (row["part_id"] + ".FCStd")))
        finally:
            App.closeDocument(document.Name)
    document = App.newDocument("MountingStack")
    try:
        definitions = document.addObject("App::DocumentObjectGroup", "Library")
        assembly = document.addObject("App::Part", "Assembly")
        for kind, positions in {
            "plate": [(0, 0, 0), (0, 0, 65)],
            "bracket": [(0, -45, 0), (0, 65, 0)],
            "spacer": [(10, 10, 30), (70, 10, 30), (10, 30, 30), (70, 30, 30)],
        }.items():
            row = by_kind[kind][0]
            part = make_part(document, row["part_id"], kind, row["dimensions"])
            definitions.addObject(part)
            for position in positions:
                link = document.addObject("App::Link", "Occurrence_" + row["part_id"])
                link.setLink(part)
                assembly.addObject(link)
                link.LinkPlacement = App.Placement(App.Vector(*position), App.Rotation())
            part.Visibility = False
        document.recompute()
        document.saveAs(str(output / "assembly.FCStd"))
        from .bom import export_bom
        from .reuse import scan_library, write_report

        export_bom(assembly, output / "bom")
        write_report(scan_library(library), output / "reuse.csv")
    finally:
        App.closeDocument(document.Name)
    return output
