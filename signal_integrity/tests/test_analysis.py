"""scikit-rf conversion and metrics on a synthetic line with a known answer."""

from pathlib import Path

import numpy as np
import pytest

from signal_integrity import analysis, fdtd
from signal_integrity.kicad_pcb import parse_board

BOARD = Path(__file__).resolve().parents[2] / "hardware" / "desk-node.kicad_pcb"
FREQ = np.arange(1, 121) * 50e6


def test_matched_through_line_has_no_loss_and_no_reflection():
    s21 = np.exp(-1j * 2 * np.pi * FREQ * 0.5e-9)     # a 0.5 ns matched delay line
    s11 = np.zeros_like(s21)
    net = analysis.network_from_s(FREQ, s11, s21)
    result = analysis.metrics(net)
    assert result["at_ghz"][3.0]["il_db"] == pytest.approx(0.0, abs=1e-9)
    assert result["at_ghz"][3.0]["rl_db"] > 200
    assert result["tdr_min_ohm"] == pytest.approx(50.0, abs=1e-6)


def test_lossy_line_reports_insertion_loss():
    s21 = 0.5 * np.exp(-1j * 2 * np.pi * FREQ * 0.5e-9)  # -6.02 dB flat
    net = analysis.network_from_s(FREQ, np.zeros_like(s21), s21)
    il = analysis.metrics(net)["at_ghz"][1.0]["il_db"]
    assert il == pytest.approx(6.0206, rel=1e-3)


def test_touchstone_round_trips_through_scikit_rf(tmp_path):
    import skrf

    s21 = 0.8 * np.exp(-1j * 2 * np.pi * FREQ * 0.2e-9)
    s11 = 0.1 * np.ones_like(s21)
    path = tmp_path / "line.s2p"
    analysis.network_from_s(FREQ, s11, s21, path=path)
    back = skrf.Network(str(path))
    assert np.allclose(back.s[:, 1, 0], s21, atol=1e-6)
    assert np.allclose(back.s[:, 0, 0], s11, atol=1e-6)


def test_representative_trace_is_a_signal_net_at_its_common_width():
    board = parse_board(BOARD)
    net, width = analysis.pick_representative(board)
    assert net not in analysis.POWER_AND_GROUND
    assert width == 0.25


def test_closed_form_table_matches_the_board():
    board = parse_board(BOARD)
    result = analysis.closed_form(board, analysis.default_stackup(board))
    widths = {round(row["width_mm"], 2): row["z0_ohm"] for row in result["tracks"]}
    assert widths[0.25] > widths[0.3] > widths[0.5]
    assert result["via"]["z0_ohm"] == pytest.approx(39.21, abs=0.01)
    assert result["width_for_50_mm"] == pytest.approx(2.97, abs=0.02)


def test_default_model_geometry_is_symmetric():
    model = fdtd.default_model(0.25, 1.6, 4.5, 0.02, 0.3, 0.6, 0.3)
    x1, x2 = model.via.x_mm
    assert model.length_mm == pytest.approx(x2 + 8.0)
    assert x1 - 0.0 == pytest.approx(model.length_mm - x2)     # same run on both ends
    assert model.via.antipad_mm == pytest.approx(1.2)
    assert len(model.freq_hz) == model.n_freq
    assert model.freq_hz[0] == pytest.approx(50e6)


def test_simulation_without_openems_says_so(tmp_path):
    try:
        import CSXCAD  # noqa: F401
        pytest.skip("openEMS is installed; the unavailable path is not reached")
    except ImportError:
        pass
    board = parse_board(BOARD)
    with pytest.raises(fdtd.OpenEMSUnavailable):
        analysis.simulate(board, analysis.default_stackup(board), 0.25, tmp_path)


def test_report_with_simulated_results_writes_tables_and_plots(tmp_path):
    from signal_integrity.report import write_report

    board = parse_board(BOARD)
    stackup = analysis.default_stackup(board)
    closed = analysis.closed_form(board, stackup)
    s21 = 0.9 * np.exp(-1j * 2 * np.pi * FREQ * 0.4e-9)
    s11 = 0.05 * np.ones_like(s21)
    net = analysis.network_from_s(FREQ, s11, s21, path=tmp_path / "synthetic.s2p")
    simulated = analysis.metrics(net)
    simulated["touchstone"] = str(tmp_path / "synthetic.s2p")
    report = write_report(tmp_path, board=board, stackup=stackup, net="/I2C_SCL", width_mm=0.25,
                          closed=closed, simulated=simulated, pcb=str(BOARD))
    text = report.read_text(encoding="utf-8")
    assert "3D FDTD model (openEMS) and scikit-rf" in text
    assert "| 3 GHz | 0.92 dB | 26.02 dB |" in text
    assert (tmp_path / "losses.png").stat().st_size > 1000
    assert (tmp_path / "tdr.png").stat().st_size > 1000
