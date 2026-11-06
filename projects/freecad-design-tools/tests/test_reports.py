import csv
import math

import FreeCAD as App
import Part
import pytest
from openpyxl import load_workbook

from freecad_tools.bom import collect_bom, export_bom
from freecad_tools.parts import make_part
from freecad_tools.reuse import compare, scan_library, signature


def plate(doc, part_id="PL", **updates):
    dims = dict(length=80, width=40, thickness=4, hole_diameter=5, pitch=60)
    dims.update(updates)
    return make_part(doc, part_id, "plate", dims)


def test_nested_repeated_subassembly_counts_occurrences_not_definitions(doc, tmp_path):
    part = plate(doc)
    sub = doc.addObject("App::Part", "Sub")
    for _ in range(2):
        link = doc.addObject("App::Link", "PlateLink")
        link.setLink(part)
        sub.addObject(link)
    root = doc.addObject("App::Part", "Assembly")
    for _ in range(3):
        link = doc.addObject("App::Link", "SubLink")
        link.setLink(sub)
        root.addObject(link)
    doc.recompute()
    rows = collect_bom(root)
    assert len(rows) == 1 and rows[0]["quantity"] == 6
    assert rows[0]["unit_volume_mm3"] == pytest.approx(12800 - 50 * math.pi)
    export_bom(root, tmp_path / "bom")
    with (tmp_path / "bom.csv").open() as stream:
        assert list(csv.DictReader(stream))[0]["quantity"] == "6"
    book = load_workbook(tmp_path / "bom.xlsx", data_only=False)
    assert book.active["D2"].value == 6
    assert book.active["F2"].value == pytest.approx(6 * (12800 - 50 * math.pi))
    assert book.active.freeze_panes == "A2"
    book.close()


def test_bom_rejects_unidentified_geometry_and_conflicting_same_revision(doc):
    root = doc.addObject("App::Part", "Assembly")
    a = plate(doc)
    b = plate(doc, "OTHER", pitch=50)
    b.PartId = a.PartId
    root.addObject(a)
    root.addObject(b)
    doc.recompute()
    with pytest.raises(ValueError, match="Conflicting"):
        collect_bom(root)
    root.removeObject(b)
    anonymous = doc.addObject("Part::Feature", "Anonymous")
    anonymous.Shape = Part.makeBox(1, 1, 1)
    root.addObject(anonymous)
    with pytest.raises(ValueError, match="metadata"):
        collect_bom(root)


def test_bom_preserves_distinct_revisions_and_formula_like_material_as_text(doc, tmp_path):
    root = doc.addObject("App::Part", "Assembly")
    a = plate(doc)
    b = plate(doc, "OTHER")
    b.PartId, b.Revision = a.PartId, 2
    a.Material = "=1+1"
    root.addObject(a)
    root.addObject(b)
    doc.recompute()
    export_bom(root, tmp_path / "bom")
    book = load_workbook(tmp_path / "bom.xlsx")
    assert book.active["C2"].data_type == "s"
    assert book.active["C2"].value == "'=1+1"
    assert len(collect_bom(root)) == 2
    book.close()


def test_reuse_detects_small_variant_but_rejects_different_hole_pitch(doc):
    a = plate(doc)
    near = plate(doc, "NEAR", length=80.1)
    other = plate(doc, "OTHER", pitch=50)
    assert compare(signature(a), signature(near)) is not None
    # Equal bounding boxes and volume alone cannot distinguish these two plates.
    assert a.Shape.Volume == pytest.approx(other.Shape.Volume)
    assert compare(signature(a), signature(other)) is None
    assert len(signature(a)["holes"]) == 2


def test_signature_uses_solid_geometry_and_ignores_translation(doc):
    a = plate(doc)
    shape = a.Shape.copy()
    shape.translate(App.Vector(100, 200, 300))
    imported = doc.addObject("Part::Feature", "Imported")
    imported.Shape = shape
    doc.recompute()
    assert compare(signature(a), signature(imported)) is not None
    assert len(signature(imported)["holes"]) == 2


def test_library_reads_saved_geometry_and_reports_bad_file(doc, tmp_path):
    plate(doc)
    doc.saveAs(str(tmp_path / "a.FCStd"))
    plate(doc, "NEAR", length=80.1)
    doc.saveAs(str(tmp_path / "b.FCStd"))
    assert len(scan_library(tmp_path)) >= 1
    (tmp_path / "bad.FCStd").write_bytes(b"not a FreeCAD file")
    with pytest.raises(ValueError, match="bad.FCStd"):
        scan_library(tmp_path)


def test_library_scan_preserves_open_document_and_reads_saved_bytes(doc, tmp_path):
    part = plate(doc)
    saved = tmp_path / "a.FCStd"
    doc.saveAs(str(saved))
    sheet = doc.getObject(part.DimensionSheet)
    sheet.set("B1", "150")
    doc.recompute()
    # The scan owns a separate copy and cannot close or inspect this unsaved edit.
    from freecad_tools.reuse import scan_library

    assert scan_library(tmp_path) == []
    assert App.getDocument(doc.Name) is doc
    assert part.Shape.BoundBox.XLength == pytest.approx(150)


def test_scaled_assembly_links_are_rejected(doc):
    part = plate(doc)
    root = doc.addObject("App::Part", "Assembly")
    link = doc.addObject("App::Link", "Scaled")
    link.setLink(part)
    link.Scale = 2
    root.addObject(link)
    doc.recompute()
    with pytest.raises(ValueError, match="[Ss]cal"):
        collect_bom(root)


@pytest.mark.parametrize("bad_cell", ["=1/0", "invalid text"])
def test_bom_rejects_spreadsheet_dependency_errors(doc, bad_cell):
    part = plate(doc)
    root = doc.addObject("App::Part", "Assembly")
    root.addObject(part)
    doc.getObject(part.DimensionSheet).set("B1", bad_cell)
    doc.recompute()
    with pytest.raises(ValueError):
        collect_bom(root)


def test_library_scans_terminal_partdesign_body_not_sketch_or_history(doc, tmp_path):
    body = doc.addObject("PartDesign::Body", "Body")
    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(sketch)
    # A closed rectangular wire and two internal circles produce a perforated plate pad.
    corners = [
        App.Vector(0, 0, 0),
        App.Vector(80, 0, 0),
        App.Vector(80, 40, 0),
        App.Vector(0, 40, 0),
    ]
    for i in range(4):
        sketch.addGeometry(Part.LineSegment(corners[i], corners[(i + 1) % 4]), False)
    for x in (10, 70):
        sketch.addGeometry(Part.Circle(App.Vector(x, 20, 0), App.Vector(0, 0, 1), 2.5), False)
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = sketch
    pad.Length = 4
    doc.recompute()
    assert pad.Shape.isValid() and len(pad.Shape.Solids) == 1
    first = tmp_path / "body-a.FCStd"
    doc.saveAs(str(first))
    doc.saveAs(str(tmp_path / "body-b.FCStd"))
    rows = scan_library(tmp_path)
    assert len(rows) == 1
    assert rows[0]["part_a"].endswith(":Body") and rows[0]["hole_count"] == 2


def test_spacer_outer_cylinder_is_not_counted_as_a_bore(doc):
    spacer = make_part(doc, "SP", "spacer", dict(outer_diameter=10, hole_diameter=5, height=12))
    result = signature(spacer)
    assert len(result["holes"]) == 1
    assert result["holes"][0][0] == pytest.approx(2.5)


def test_removing_alias_keeps_cell_binding_editable(doc):
    part = plate(doc)
    root = doc.addObject("App::Part", "Assembly")
    root.addObject(part)
    sheet = doc.getObject(part.DimensionSheet)
    # FreeCAD rewrites removed aliases to cell addresses; that valid binding should still work.
    sheet.setAlias("B1", "")
    sheet.set("B1", "100")
    doc.recompute()
    assert collect_bom(root)[0]["unit_volume_mm3"] == pytest.approx(16000 - 50 * math.pi)


def test_bom_requires_recompute_after_dimension_edit(doc):
    part = plate(doc)
    root = doc.addObject("App::Part", "Assembly")
    root.addObject(part)
    doc.recompute()
    doc.getObject(part.DimensionSheet).set("B1", "100")
    with pytest.raises(ValueError, match="Recompute"):
        collect_bom(root)
    doc.recompute()
    assert collect_bom(root)[0]["unit_volume_mm3"] == pytest.approx(16000 - 50 * math.pi)
