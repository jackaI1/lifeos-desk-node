import math
from pathlib import Path

import FreeCAD as App
import pytest

from freecad_tools.parts import build_project, load_dimensions, make_part

ROOT = Path(__file__).resolve().parents[1]


def test_plate_bracket_spacer_are_valid_solids_with_independent_volumes(doc):
    plate = make_part(
        doc, "PL", "plate", dict(length=80, width=40, thickness=4, hole_diameter=5, pitch=60)
    )
    bracket = make_part(
        doc,
        "BR",
        "bracket",
        dict(length=80, width=20, thickness=4, height=30, hole_diameter=5, pitch=60),
    )
    spacer = make_part(doc, "SP", "spacer", dict(outer_diameter=10, hole_diameter=5, height=12))
    for part in (plate, bracket, spacer):
        assert part.Shape.isValid() and len(part.Shape.Solids) == 1
    assert plate.Shape.Volume == pytest.approx(80 * 40 * 4 - 2 * math.pi * 2.5**2 * 4)
    assert bracket.Shape.Volume == pytest.approx(
        (80 * 20 * 4 + 80 * 4 * 26) - 2 * math.pi * 2.5**2 * 4
    )
    assert spacer.Shape.Volume == pytest.approx(math.pi * (5**2 - 2.5**2) * 12)


def test_spreadsheet_edit_recomputes_and_survives_reopen(doc, tmp_path):
    part = make_part(
        doc, "PL", "plate", dict(length=80, width=40, thickness=4, hole_diameter=5, pitch=60)
    )
    sheet = doc.getObject(part.DimensionSheet)
    sheet.set("B1", "100")
    doc.recompute()
    assert part.Shape.BoundBox.XLength == pytest.approx(100)
    path = tmp_path / "editable.FCStd"
    doc.saveAs(str(path))
    part_name = part.Name
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(path))
    try:
        restored = reopened.getObject(part_name)
        reopened.getObject(restored.DimensionSheet).set("B1", "120")
        reopened.recompute()
        assert restored.Shape.BoundBox.XLength == pytest.approx(120)
    finally:
        App.closeDocument(reopened.Name)


@pytest.mark.parametrize(
    "updates",
    [
        dict(length=0),
        dict(pitch=79),
        dict(thickness=float("nan")),
        dict(hole_diameter=-1),
        dict(width=4),
    ],
)
def test_impossible_dimensions_rejected_before_creating_objects(doc, updates):
    dims = dict(length=80, width=40, thickness=4, hole_diameter=5, pitch=60)
    dims.update(updates)
    with pytest.raises(ValueError):
        make_part(doc, "PL", "plate", dims)
    assert not doc.Objects


def test_csv_library_creates_six_variants_and_eight_assembly_occurrences(tmp_path):
    rows = load_dimensions(ROOT / "examples/dimensions.csv")
    assert len(rows) == 6
    result = build_project(ROOT / "examples/dimensions.csv", tmp_path)
    assembly = App.openDocument(str(result / "assembly.FCStd"))
    try:
        from freecad_tools.bom import collect_bom

        assert sum(row["quantity"] for row in collect_bom(assembly.getObject("Assembly"))) == 8
        assert all(not part.Visibility for part in assembly.getObject("Library").Group)
        assert all(link.Visibility for link in assembly.getObject("Assembly").Group)
    finally:
        App.closeDocument(assembly.Name)
    assert len(list((result / "library").glob("*.FCStd"))) == 6


def test_duplicate_ids_and_non_numeric_cells_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(
        "part_id,kind,length,width,thickness,hole_diameter,pitch\nA,plate,80,40,4,5,60\nA,plate,80,40,4,5,60\n"
    )
    with pytest.raises(ValueError, match="Duplicate"):
        load_dimensions(path)
    path.write_text(
        "part_id,kind,length,width,thickness,hole_diameter,pitch\nA,plate,=2+2,40,4,5,60\n"
    )
    with pytest.raises(ValueError):
        load_dimensions(path)


def test_invalid_spreadsheet_edit_clears_stale_shape_and_blocks_bom(doc):
    from freecad_tools.bom import collect_bom

    part = make_part(
        doc, "PL", "plate", dict(length=80, width=40, thickness=4, hole_diameter=5, pitch=60)
    )
    root = doc.addObject("App::Part", "Assembly")
    root.addObject(part)
    doc.getObject(part.DimensionSheet).set("B1", "10")
    doc.recompute()
    assert part.Shape.isNull()
    assert part.GenerationError
    with pytest.raises(ValueError):
        collect_bom(root)


@pytest.mark.parametrize(
    "kind,dims",
    [
        ("spacer", dict(outer_diameter=5, hole_diameter=5, height=12)),
        ("bracket", dict(length=80, width=20, thickness=4, height=3, hole_diameter=5, pitch=60)),
        ("bracket", dict(length=80, width=10, thickness=4, height=30, hole_diameter=5, pitch=60)),
    ],
)
def test_spacer_wall_and_bracket_leg_clearance_are_required(doc, kind, dims):
    with pytest.raises(ValueError):
        make_part(doc, "BAD", kind, dims)
    assert not doc.Objects


def test_csv_rejects_case_collisions_before_output(tmp_path):
    path = tmp_path / "case.csv"
    path.write_text(
        "part_id,kind,length,width,thickness,hole_diameter,pitch\nA,plate,80,40,4,5,60\na,plate,80,40,4,5,60\n"
    )
    with pytest.raises(ValueError, match="Duplicate"):
        load_dimensions(path)
