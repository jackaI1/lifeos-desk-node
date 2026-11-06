"""These checks run the installed ngspice executable, never a simulator mock."""

from dataclasses import replace

import numpy as np
import pytest

from pdn.model import Study, impedance
from pdn.spice import make_deck, netlist, run_netlist


@pytest.mark.parametrize(
    "resistance,inductance,capacitance", [(0.02, 1e-9, 100e-6), (0.1, 1e-6, 1e-6), (1, 1e-3, 1e-9)]
)
def test_series_rlc_ac_matches_complex_hand_calculation(resistance, inductance, capacitance):
    deck = make_deck(
        f"Itest 0 out DC 0 AC 1\nR1 out a {resistance}\nL1 a b {inductance}\nC1 b 0 {capacitance}",
        "ac dec 100 1000 1e7\nlet zr=real(v(out))\nlet zi=imag(v(out))\nwrdata data.dat zr zi",
    )
    data = run_netlist(deck)
    w = 2 * np.pi * data[:, 0]
    expected = resistance + 1j * (w * inductance - 1 / (w * capacitance))
    np.testing.assert_allclose(data[:, 1] + 1j * data[:, 2], expected, rtol=1e-7)


def test_rc_step_matches_exponential_and_sign():
    # 1 A through a 1 ohm / 1 uF shunt: v(t) = 1-exp(-t/1us), after 1ns rise.
    deck = make_deck(
        "Itest 0 out PULSE(0 1 1e-6 1e-9 1e-9 10e-6 30e-6)\nR1 out 0 1\nC1 out 0 1e-6",
        "tran 2e-9 6e-6 0 2e-9\nwrdata data.dat v(out)",
    )
    data = run_netlist(deck)
    mask = data[:, 0] > 1.01e-6
    expected = 1 - np.exp(-(data[mask, 0] - 1.0005e-6) / 1e-6)
    np.testing.assert_allclose(data[mask, 1], expected, atol=2e-6)


@pytest.mark.parametrize("no_package", [False, True])
def test_full_network_ac_matches_independent_equations(no_package):
    model = Study()
    if no_package:
        model = replace(model, banks=tuple(b for b in model.banks if b.node != "die"))
    data = run_netlist(netlist(model, "ac"))
    np.testing.assert_allclose(
        data[:, 1] + 1j * data[:, 2],
        impedance(model, data[:, 0]),
        rtol=2e-7,
        atol=1e-12,
    )


def test_load_step_dc_levels_and_current_direction():
    model = Study()
    data = run_netlist(netlist(model, "tran"))
    t, voltage, board, current = data.T
    assert voltage[0] == pytest.approx(0.893, abs=1e-8)
    assert current[0] == pytest.approx(20)
    assert current[(t > 25e-6) & (t < 55e-6)] == pytest.approx(60)
    assert np.min(voltage) < 0.879
    assert np.mean(voltage[(t > 55e-6) & (t < 59e-6)]) == pytest.approx(0.879, abs=1e-4)
    assert np.mean(voltage[t > 95e-6]) == pytest.approx(0.893, abs=1e-4)
    assert board[0] == pytest.approx(0.895, abs=1e-8)


def test_missing_executable_is_actionable():
    with pytest.raises(RuntimeError, match="install ngspice"):
        run_netlist("unused", executable="not-a-real-spice-executable")


def test_simulator_error_is_not_silently_accepted():
    with pytest.raises(RuntimeError, match="ngspice"):
        run_netlist(make_deck("R1 out 0 nonsense", "ac dec 10 1 10\nwrdata data.dat v(out)"))


def test_aborted_run_with_zero_exit_and_partial_data_is_rejected(tmp_path):
    # A process-boundary fixture reproduces ngspice's zero exit on a solver abort.
    binary = tmp_path / "aborted-spice"
    binary.write_text(
        "#!/bin/sh\nprintf '0 0.9\\n0.00002 0.8\\n' > data.dat\n"
        "echo 'tran simulation(s) aborted'\nexit 0\n"
    )
    binary.chmod(0o755)
    with pytest.raises(RuntimeError, match="aborted"):
        run_netlist("unused", executable=str(binary))


def test_droop_converges_when_maximum_step_is_halved():
    model = Study()
    coarse = run_netlist(netlist(model, "tran"))
    fine = run_netlist(netlist(replace(model, max_step_s=5e-9), "tran"))
    assert fine[-1, 0] == pytest.approx(model.stop_s)
    assert coarse[-1, 0] == pytest.approx(model.stop_s)
    assert model.baseline_v - min(coarse[:, 1]) == pytest.approx(
        model.baseline_v - min(fine[:, 1]),
        rel=0.002,
    )


def test_bank_named_path_does_not_short_shared_package_path():
    model = Study()
    model = replace(
        model, banks=tuple(replace(b, name="path") if b.node == "die" else b for b in model.banks)
    )
    data = run_netlist(netlist(model, "ac"))
    np.testing.assert_allclose(
        data[:, 1] + 1j * data[:, 2],
        impedance(model, data[:, 0]),
        rtol=1e-7,
    )
