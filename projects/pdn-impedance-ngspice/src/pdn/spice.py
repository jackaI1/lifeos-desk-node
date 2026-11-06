"""Generate inspectable netlists and run ngspice synchronously in isolated scratch space."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from pdn.model import Study


def make_deck(circuit: str, commands: str) -> str:
    return (
        "Core rail PDN study\n" + circuit + "\n.options reltol=1e-5 abstol=1e-7\n"
        ".control\nset noaskquit\nset wr_singlescale\nset numdgt=15\n"
        + commands
        + "\nquit\n.endc\n.end\n"
    )


def netlist(model: Study, analysis: str) -> str:
    lines = [
        f"Vvrm source 0 DC {model.nominal_v:.15g} AC 0",
        f"Rvrm source vrm_l {model.vrm_r_ohm:.15g}",
        f"Lvrm vrm_l board {model.vrm_l_h:.15g}",
        f"Rpath board path_l {model.path_r_ohm:.15g}",
        f"Lpath path_l die {model.path_l_h:.15g}",
        "Iprobe 0 die DC 0 AC 1",
        "Vsense die load 0",
        f"Iload load 0 DC {model.base_a:.15g} AC 0 PULSE("
        f"{model.base_a:.15g} {model.base_a + model.step_a:.15g} "
        f"{model.delay_s:.15g} {model.rise_s:.15g} {model.rise_s:.15g} "
        f"{model.hold_s:.15g} {2 * model.stop_s:.15g})",
    ]
    for b in model.banks:
        if b.count:
            lines += [
                f"R_{b.name} {b.node} cap_{b.name}_r {b.esr_ohm / b.count:.15g}",
                f"L_{b.name} cap_{b.name}_r cap_{b.name}_l {b.esl_h / b.count:.15g}",
                f"C_{b.name} cap_{b.name}_l 0 {b.capacitance_f * b.count:.15g}",
            ]
    if analysis == "ac":
        commands = (
            f"ac dec {model.points_per_decade} {model.f_start_hz:.15g} {model.f_stop_hz:.15g}\n"
            "let zr=real(v(die))\nlet zi=imag(v(die))\nwrdata data.dat zr zi"
        )
    elif analysis == "tran":
        commands = (
            f"tran {model.max_step_s:.15g} {model.stop_s:.15g} 0 {model.max_step_s:.15g}\n"
            "wrdata data.dat v(die) v(board) i(Vsense)"
        )
    else:
        raise ValueError("analysis must be ac or tran")
    return make_deck("\n".join(lines), commands)


def run_netlist(deck: str, *, executable="ngspice", timeout_s=60) -> np.ndarray:
    binary = shutil.which(executable)
    if not binary:
        raise RuntimeError("Cannot find simulator; install ngspice and put it on PATH")
    # No daemon or shared process. subprocess.run reaps its child even after a timeout.
    with tempfile.TemporaryDirectory(prefix="pdn-ngspice-") as folder:
        root = Path(folder)
        (root / "study.cir").write_text(deck)
        log_path = root / "ngspice.log"
        try:
            with log_path.open("w") as log:
                proc = subprocess.run(
                    [binary, "-n", "-b", "study.cir"],
                    cwd=root,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_s,
                    check=False,
                )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ngspice exceeded {timeout_s} seconds") from exc
        # ngspice can return zero after a failed control command. Require real finite output too.
        with log_path.open("rb") as log:
            log.seek(max(0, log_path.stat().st_size - 4000))
            tail = log.read().decode(errors="replace")
        if (
            proc.returncode
            or not (root / "data.dat").exists()
            or "error:" in tail.lower()
            or "aborted" in tail.lower()
        ):
            raise RuntimeError(f"ngspice failed (exit {proc.returncode}):\n{tail}")
        try:
            data = np.loadtxt(root / "data.dat", ndmin=2)
        except ValueError as exc:
            raise RuntimeError("ngspice produced malformed data") from exc
        if data.shape[0] < 2 or not np.isfinite(data).all():
            raise RuntimeError("ngspice produced empty or nonfinite data")
        return data
