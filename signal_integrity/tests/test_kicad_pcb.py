"""Parsing of the real desk-node board file and of KiCad's S-expression syntax."""

from pathlib import Path

import pytest

from signal_integrity.kicad_pcb import parse_board, parse_sexpr

BOARD = Path(__file__).resolve().parents[2] / "hardware" / "desk-node.kicad_pcb"


def test_sexpr_reads_nested_lists_and_quoted_atoms():
    tree = parse_sexpr('(a (b "F.Cu" 1.5) (c "x y"))')[0]
    assert tree[0] == "a"
    assert tree[1] == ["b", '"F.Cu', "1.5"]
    assert tree[2] == ["c", '"x y']


def test_sexpr_reports_unbalanced_brackets():
    with pytest.raises(ValueError):
        parse_sexpr("(a (b)")
    with pytest.raises(ValueError):
        parse_sexpr("(a))")


def test_board_stackup_and_clearance():
    board = parse_board(BOARD)
    assert board.thickness_mm == pytest.approx(1.6)
    assert board.ground_clearance_mm == pytest.approx(0.3)


def test_board_nets_and_tracks():
    board = parse_board(BOARD)
    assert board.net_name(1) == "+3V3"
    assert "GND" in board.nets_with_tracks()
    widths = board.track_widths()
    assert set(round(w, 2) for w in widths) >= {0.25, 0.3, 0.5}
    assert board.track_widths("+3V3").keys() == {0.3}
    assert len(board.tracks) > 400


def test_vias_are_the_board_standard():
    board = parse_board(BOARD)
    assert len(board.vias) >= 30
    assert {(v.pad_mm, v.drill_mm) for v in board.vias} == {(0.6, 0.3)}


def test_a_non_board_file_is_refused(tmp_path):
    path = tmp_path / "other.kicad_pcb"
    path.write_text("(kicad_sch (version 1))", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_board(path)
