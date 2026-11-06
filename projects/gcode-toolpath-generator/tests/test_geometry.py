from dataclasses import replace
from math import pi

import pytest
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from gcode_toolpath import generate, simulate
from gcode_toolpath.materials import cutting_data
from gcode_toolpath.planner import depths, outline_path


def test_depths_partial_pass():
    assert depths(1.1, 0.5) == [-0.5, -1.0, -1.1]
    assert depths(1, 0.5) == [-0.5, -1]


def test_rectangle_compensation(job):
    job = replace(job, outline=((10, 10), (90, 10), (90, 70), (10, 70)))
    path = outline_path(job)
    assert Polygon(path).bounds == (8.5, 8.5, 91.5, 71.5)
    assert LineString(path).distance(Polygon(job.outline)) == pytest.approx(1.5)


def test_sample_and_every_material_pass(job):
    for material, stepdown in [("aluminum_6061", .5), ("acetal", 1), ("mild_steel", .4)]:
        revised = replace(job, material=material, stepdown=stepdown)
        report = simulate(generate(revised), job.stock, job.diameter, job.safe_z)
        assert report.ok, report.issues
        assert min(m.end[2] for m in report.moves) == -5.5
        assert report.estimated_minutes > 0


def test_capped_speed_recomputes_chip_feed():
    data = cutting_data("aluminum_6061", 3, 2, 6000)
    assert data == {"rpm": 6000, "feed": 180, "plunge": 45}
    uncapped = cutting_data("aluminum_6061", 3, 2, 50000)
    assert uncapped["rpm"] == round(120000 / (pi * 3))


def test_actual_pocket_sweep_covers_floor_without_gouging(job):
    code = generate(job).split("(HOLES")[0] + "M5\nM30\n"
    report = simulate(code, job.stock, job.diameter, job.safe_z)
    assert report.ok, report.issues
    full_depth = [LineString([m.start[:2], m.end[:2]]) for m in report.moves
                  if m.start[2] == m.end[2] == -job.pocket_depth
                  and m.start[:2] != m.end[:2]]
    swept = unary_union(full_depth).buffer(job.diameter / 2, quad_segs=64)
    # Expected rectangular pocket has the unavoidable tool-radius internal corners.
    expected = box(*job.pocket).buffer(-job.diameter / 2, join_style="mitre").buffer(
        job.diameter / 2, quad_segs=64)
    assert expected.difference(swept).area < 0.002
    assert swept.difference(box(*job.pocket)).area < 0.002


def test_actual_outline_does_not_gouge_and_has_tangent_lead(job):
    code = generate(job)
    start = next(i for i, line in enumerate(code.splitlines(), 1)
                 if line.startswith("(OUTLINE -"))
    report = simulate(code, job.stock, job.diameter, job.safe_z)
    profile = [m for m in report.moves if m.line > start and not m.rapid
               and m.start[2] < 0 and m.end[2] < 0 and m.start[:2] != m.end[:2]]
    part = Polygon(job.outline)
    assert profile
    for move in profile:
        assert LineString([move.start[:2], move.end[:2]]).distance(part) >= 1.5 - 0.001
    # The first move at depth is the specified 2 mm tangent entry.
    assert LineString([profile[0].start[:2], profile[0].end[:2]]).length == pytest.approx(2)
    layers = sorted({m.end[2] for m in profile})
    assert layers == sorted(depths(job.profile_depth, job.stepdown))


def test_all_holes_peck_to_exact_depth(job):
    code = generate(job)
    lines = code.splitlines()
    first = next(i for i, s in enumerate(lines, 1) if s.startswith("(HOLES"))
    last = next(i for i, s in enumerate(lines, 1) if s.startswith("(OUTLINE -"))
    report = simulate(code, job.stock, job.diameter, job.safe_z)
    holes = [m for m in report.moves if first < m.line < last and m.end[2] < 0]
    for xy in job.holes:
        actual = [m.end[2] for m in holes if m.end[:2] == xy]
        assert actual == depths(job.hole_depth, min(job.peck, job.stepdown))
        assert Point(xy).buffer(job.diameter / 2).within(Polygon(job.outline))


def test_narrow_pocket_ramp_respects_three_degree_limit(job):
    job = replace(job, pocket=(30, 25, 34, 35), holes=())
    code = generate(job).split("(HOLES")[0] + "M5\nM30\n"
    report = simulate(code, job.stock, job.diameter, job.safe_z)
    ramps = [m for m in report.moves if m.end[2] < m.start[2]
             and m.end[0] != m.start[0]]
    assert ramps
    assert all(abs((m.end[2] - m.start[2]) / (m.end[0] - m.start[0])) <= .0525
               for m in ramps)


@pytest.mark.parametrize("changes", [
    {"stepover": 2}, {"stepover": 0}, {"stepdown": 1}, {"stepdown": .001},
    {"diameter": 0}, {"diameter": float("nan")}, {"safe_z": -1}, {"max_rpm": 0},
    {"flutes": 1.5}, {"flutes": True}, {"material": "unobtainium"},
    {"profile_depth": 6}, {"pocket_depth": 5.6}, {"hole_depth": 7},
    {"holes": ((50, 40),)}, {"holes": ((1, 1),)}, {"holes": ((20, 20), (21, 20))},
    {"pocket": (30, 25, 31, 55)}, {"pocket": (0, 0, 40, 40)},
    {"outline": ((10, 10), (90, 70), (90, 10), (10, 70))},
    {"stock": (90, 80, 6)}, {"lead_length": 100},
])
def test_invalid_jobs_fail_before_output(job, changes):
    with pytest.raises(ValueError):
        generate(replace(job, **changes))


@pytest.mark.parametrize("changes", [
    {"pocket": (30, 25, 33.0000001, 55)},
    {"pocket_depth": 0.0001}, {"hole_depth": 0.0001},
    {"safe_z": 0.0001}, {"lead_length": 0.0001},
])
def test_reject_dimensions_lost_to_gcode_rounding(job, changes):
    with pytest.raises(ValueError, match="0.01"):
        replace(job, **changes).validate()


def test_move_budget_includes_narrow_pocket_ramp_traverses(job):
    # A 0.01 mm centre travel needs 955 ramp traverses per 0.5 mm layer.
    revised = replace(job, pocket=(30, 25, 33.01, 28.01), holes=(),
                      stock=(100, 80, 61), stepdown=0.5,
                      pocket_depth=60, profile_depth=60, hole_depth=1)
    with pytest.raises(ValueError, match="budget"):
        revised.validate()


def test_feeds_use_emitted_integer_spindle_speed():
    data = cutting_data("aluminum_6061", 3, 2, 6000.8)
    assert data["rpm"] <= 6000.8
    assert data["feed"] == round(data["rpm"] * 2 * 0.015, 3)
    assert data["plunge"] == round(data["feed"] * 0.25, 3)


@pytest.mark.parametrize("notch_right", [47, 55])
def test_concave_notches_are_rejected_instead_of_silently_erased(job, notch_right):
    revised = replace(job, outline=((10, 10), (90, 10), (90, 70),
                                   (notch_right, 70), (notch_right, 40),
                                   (45, 40), (45, 70), (10, 70)),
                      pocket=(20, 20, 35, 35), holes=())
    with pytest.raises(ValueError, match="convex"):
        generate(revised)
