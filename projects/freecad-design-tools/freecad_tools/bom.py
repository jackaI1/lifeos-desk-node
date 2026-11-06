"""Walk assembly occurrences, including repeated links to nested subassemblies."""

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .geometry import require_current_solid

COLUMNS = ("part_id", "revision", "material", "quantity", "unit_volume_mm3", "total_volume_mm3")


def safe_text(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def collect_bom(root):
    rows, shapes = {}, {}

    def visit(obj, ancestors):
        identity = (obj.Document.Name, obj.Name)
        if identity in ancestors:
            raise ValueError("Cyclic assembly reference")
        ancestors = ancestors | {identity}
        if obj.isDerivedFrom("App::Link"):
            scale = getattr(obj, "ScaleVector", None)
            if abs(getattr(obj, "Scale", 1.0) - 1.0) > 1e-9 or (
                scale is not None
                and any(abs(value - 1) > 1e-9 for value in (scale.x, scale.y, scale.z))
            ):
                raise ValueError("Scaled links need a separate part definition before BOM export")
            if getattr(obj, "ElementCount", 0):
                raise ValueError("Expand link arrays into individual assembly links before export")
            target = obj.LinkedObject
            if target is None:
                raise ValueError("Broken assembly link")
            visit(target, ancestors)
            return
        if hasattr(obj, "Group"):
            for child in obj.Group:
                visit(child, ancestors)
            return
        if not hasattr(obj, "Shape"):
            raise ValueError(f"Assembly leaf {obj.Name} has no part metadata or solid")
        if not all(hasattr(obj, name) for name in ("PartId", "Revision", "Material")):
            raise ValueError(f"Missing BOM metadata on {obj.Name}")
        if not obj.PartId or obj.Revision < 1:
            raise ValueError(f"Invalid BOM metadata on {obj.Name}")
        require_current_solid(obj)
        key = (obj.PartId, obj.Revision)
        shape = obj.Shape.copy()
        # Part placements locate occurrences; compare definitions in their local coordinate frame.
        shape.Placement = obj.Placement.inverse().multiply(shape.Placement)
        if key in rows:
            original = shapes[key]
            tolerance = max(original.Volume, shape.Volume) * 1e-8
            if (
                rows[key]["material"] != obj.Material
                or abs(original.Volume - shape.Volume) > tolerance
                or original.cut(shape).Volume > tolerance
                or shape.cut(original).Volume > tolerance
            ):
                raise ValueError(f"Conflicting definitions for {key[0]} revision {key[1]}")
            rows[key]["quantity"] += 1
        else:
            shapes[key] = shape
            rows[key] = dict(
                part_id=obj.PartId,
                revision=obj.Revision,
                material=obj.Material,
                quantity=1,
                unit_volume_mm3=shape.Volume,
            )

    visit(root, set())
    for row in rows.values():
        row["total_volume_mm3"] = row["quantity"] * row["unit_volume_mm3"]
    return [rows[key] for key in sorted(rows)]


def export_bom(root, stem):
    rows = collect_bom(root)
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    values = [
        [
            safe_text(row[column]) if isinstance(row[column], str) else row[column]
            for column in COLUMNS
        ]
        for row in rows
    ]
    with stem.with_suffix(".csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        writer.writerows(values)
    book = Workbook()
    sheet = book.active
    sheet.title = "BOM"
    sheet.append(COLUMNS)
    for row in values:
        sheet.append(row)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="28536B")
    for column, width in zip("ABCDEF", (22, 12, 24, 12, 24, 24)):
        sheet.column_dimensions[column].width = width
    for row in sheet.iter_rows(min_row=2, min_col=5, max_col=6):
        for cell in row:
            cell.number_format = "0.000"
    book.save(stem.with_suffix(".xlsx"))
    book.close()
    return rows
