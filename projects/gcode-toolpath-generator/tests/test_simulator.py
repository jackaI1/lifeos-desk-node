import pytest

from gcode_toolpath import generate, simulate

PREAMBLE = "G21 G17 G90 G94 G40 G49 G80 G54\nS12000 M3\n"


def check(body):
    return simulate(PREAMBLE + body + "\nG1 Z5 F100\nM5\nM30\n", (100, 80, 6), 3, 5)


def test_modal_moves_comments_and_feeds():
    report = check("G0X10Y10 (compact; comment)\nG1Z-1F100\nX20 ; modal feed")
    assert report.ok, report.issues
    assert report.moves[2].end == (20, 10, -1)
    assert report.moves[2].feed == 100


@pytest.mark.parametrize("body, issue", [
    ("G0 X10 Y10\nG1 Z-1 F100\nG0 X20", "Rapid through"),
    ("G0 X10 Y10 Z-1", "Rapid through"),
    ("G0 X0 Y10", "Cutter envelope"),
    ("G0 X99 Y10", "Cutter envelope"),
    ("G0 X10 Y79", "Cutter envelope"),
    ("G0 X10 Y10\nG1 Z-6.1 F100", "Cutter envelope"),
    ("G0 Z6", "Cutter envelope"),
    ("G91\nG0 X10", "Unsupported"),
    ("G20\nG0 X10", "Unsupported"),
    ("G2 X10 Y10 I2", "Unsupported"),
    ("G81 X10 Z-3", "Unsupported"),
    ("G0 G1 X10", "conflicting"),
    ("G0 X10 X20", "conflicting"),
    ("G0 XNaN", "malformed"),
    ("G0 X10 (unclosed", "malformed"),
    ("G0 X10 (nested (bad))", "malformed"),
    ("G1 X10 F0", "Feed must"),
    ("M5\nG1 X10 F100", "spindle on"),
    ("S0\nG1 X10 F100", "Spindle speed"),
    ("M3 M5", "conflicting"),
    ("M30 X10", "Motion on M30"),
    ("M30\nG0 X10", "after M30"),
])
def test_reject_unsafe_or_unknown_programs(body, issue):
    report = check(body)
    assert not report.ok
    assert any(issue in message for message in report.issues), report.issues


def test_conservative_checker_flags_rapid_in_previously_cut_area():
    report = check("G0 X10 Y10\nG1 Z-1 F100\nX20\nG0 X10")
    assert any("Rapid through" in s for s in report.issues)


def test_no_preamble_or_end_cannot_pass():
    report = simulate("G0 X10 Y10", (100, 80, 6), 3, 5)
    assert not report.ok
    assert any("requires explicit" in s for s in report.issues)
    assert "Missing M30 program end" in report.issues


def test_finish_requires_retraction_and_spindle_stop():
    report = simulate(PREAMBLE + "G1 Z-1 F100\nM30", (100, 80, 6), 3, 5)
    assert not report.ok
    assert any("finish at clearance" in s for s in report.issues)


def test_machine_time_and_travel_known_geometry():
    report = check("G0 X10 Y10\nG1 Z-1 F100\nX20 F200")
    # 6 mm plunge + 10 mm cut + 6 mm retract at explicitly programmed feeds.
    assert report.cutting_mm == pytest.approx(22)
    assert report.estimated_minutes == pytest.approx(
        report.rapid_mm / 2000 + 6 / 100 + 10 / 200 + 6 / 100)


def test_mutation_of_real_program_is_detected(job):
    code = generate(job)
    bad = code.replace("G1 Z-0.500", "G0 Z-0.500", 1)
    assert bad != code
    report = simulate(bad, job.stock, job.diameter, job.safe_z)
    assert not report.ok
    assert any("Rapid through" in s for s in report.issues)


def test_g80_cancels_modal_motion_until_reselected():
    report = check("G1 X10 F100\nG80\nX20")
    assert not report.ok
    assert any("requires explicit" in s for s in report.issues)


@pytest.mark.parametrize("motion", ["G0", "G1"])
def test_g80_cannot_share_motion_group(motion):
    report = check(f"G80 {motion} X10 F100")
    assert not report.ok
    assert any("conflicting" in s for s in report.issues)
