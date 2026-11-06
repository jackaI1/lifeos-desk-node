"""Run design comparisons and write portable data, plots and a readable report."""

import argparse
import json
import os
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from pdn.analysis import ac_metrics, transient_metrics
from pdn.model import Study, impedance, load_study
from pdn.spice import netlist, run_netlist


def run_study(model: Study, output: Path):
    """Finish simulations in scratch space before replacing any previous study files."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pdn-study-", dir=output.parent) as folder:
        staging = Path(folder)
        summary = build_study(model, staging)
        output.mkdir(parents=True, exist_ok=True)
        for path in staging.iterdir():
            os.replace(path, output / path.name)
    return summary


def build_study(model: Study, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    (output / "input.json").write_text(json.dumps(asdict(model), indent=2) + "\n")
    # Change only the die-side capacitor bank, retaining the same source and package path.
    variants = {
        "full": model,
        "no_package": replace(
            model, banks=tuple(replace(b, count=0) if b.node == "die" else b for b in model.banks)
        ),
        "damped_package": replace(
            model,
            banks=tuple(
                replace(b, esr_ohm=b.esr_ohm * 20) if b.node == "die" else b for b in model.banks
            ),
        ),
    }
    summary = {"target_ohm": model.target_ohm, "variants": {}}
    traces = {}
    for name, variant in variants.items():
        arrays = {}
        for analysis in ("ac", "tran"):
            deck = netlist(variant, analysis)
            (output / f"{name}-{analysis}.cir").write_text(deck)
            data = run_netlist(deck)
            if analysis == "ac":
                # DEC sampling need not include f_stop, especially for sub-decade sweeps.
                step_ratio = 10 ** (1 / variant.points_per_decade)
                complete = (
                    np.isclose(data[0, 0], variant.f_start_hz, rtol=1e-7, atol=0)
                    and data[-1, 0] >= variant.f_stop_hz / step_ratio * (1 - 1e-7)
                    and data[-1, 0] <= variant.f_stop_hz * (1 + 1e-7)
                    and np.all(np.diff(data[:, 0]) > 0)
                )
            else:
                complete = np.isclose(data[-1, 0], variant.stop_s, rtol=1e-6, atol=0)
            if not complete:
                raise RuntimeError(f"ngspice {analysis} did not reach the requested endpoint")
            arrays[analysis] = data
        ac, tran = arrays["ac"], arrays["tran"]
        z = ac[:, 1] + 1j * ac[:, 2]
        hand = impedance(variant, ac[:, 0])
        error = float(np.max(np.abs(z - hand) / np.abs(hand)))
        if error > 1e-6:
            raise RuntimeError(f"{name}: AC disagrees with circuit equations by {error:.3g}")
        summary["variants"][name] = {
            "max_ac_relative_error": error,
            "ac": ac_metrics(ac[:, 0], z, model.target_ohm),
            "transient": transient_metrics(variant, tran[:, 0], tran[:, 1]),
        }
        np.savetxt(
            output / f"{name}-impedance.csv",
            np.column_stack(
                (
                    ac[:, 0],
                    ac[:, 1],
                    ac[:, 2],
                    np.abs(z),
                    hand.real,
                    hand.imag,
                )
            ),
            delimiter=",",
            header=("frequency_hz,real_ohm,imag_ohm,magnitude_ohm,hand_real_ohm,hand_imag_ohm"),
            comments="",
            fmt="%.10e",
        )
        np.savetxt(
            output / f"{name}-transient.csv",
            tran,
            delimiter=",",
            header="time_s,die_v,board_v,load_a",
            comments="",
            fmt="%.10e",
        )
        traces[name] = (ac, tran, hand)
    summary["hand_calculations"] = hand_calculations(model)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    write_plots(model, traces, output)
    (output / "report.md").write_text(report(model, summary))
    return summary


def hand_calculations(model):
    total_c = sum(b.count * b.capacitance_f for b in model.banks)
    die_c = sum(b.count * b.capacitance_f for b in model.banks if b.node == "die")
    return {
        "dc_baseline_v": model.baseline_v,
        "dc_high_load_v": model.high_load_v,
        "dc_incremental_drop_v": model.step_a * (model.vrm_r_ohm + model.path_r_ohm),
        "path_l_di_dt_v": model.path_l_h * model.step_a / model.rise_s,
        "all_capacitors_charge_only_rise_drop_v": model.step_a * model.rise_s / (2 * total_c)
        if total_c
        else None,
        "die_capacitors_charge_only_rise_drop_v": model.step_a * model.rise_s / (2 * die_c)
        if die_c
        else None,
        "bank_series_resonances_hz": {
            b.name: float(1 / (2 * np.pi * np.sqrt(b.capacitance_f * b.esl_h)))
            for b in model.banks
            if b.count
        },
    }


def write_plots(model, traces, output):
    labels = {
        "full": "Original banks",
        "no_package": "No package capacitors",
        "damped_package": "Package ESR ×20",
    }
    with plt.rc_context({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}):
        fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
        try:
            for name, (ac, _, hand) in traces.items():
                ax.loglog(ac[:, 0], np.hypot(ac[:, 1], ac[:, 2]) * 1e3, label=labels[name])
                if name == "full":
                    ax.loglog(
                        ac[::40, 0], np.abs(hand[::40]) * 1e3, "k.", ms=3, label="Circuit equations"
                    )
            ax.axhline(model.target_ohm * 1e3, color="#b43838", ls="--", label="Target")
            ax.set(
                xlabel="Frequency (Hz)",
                ylabel="Die impedance (mΩ)",
                title="Where the core rail resists a change in load",
            )
            ax.grid(which="both", alpha=0.2)
            ax.legend(fontsize=9)
            fig.savefig(output / "impedance.png", dpi=160)
        finally:
            plt.close(fig)

        fig, axes = plt.subplots(3, 1, figsize=(9, 8), layout="constrained")
        try:
            for name, (_, tran, _) in traces.items():
                for ax in axes[:2]:
                    ax.plot(tran[:, 0] * 1e6, tran[:, 1], label=labels[name], lw=1.2)
            axes[0].set(title="Voltage at the die during a load pulse", ylabel="Rail (V)")
            axes[1].set(
                xlim=(
                    model.delay_s * 1e6 - 0.1,
                    (model.delay_s + max(2e-6, 4 * model.rise_s)) * 1e6,
                ),
                ylabel="Rail (V)",
                title="First load edge, enlarged",
            )
            for ax in axes[:2]:
                ax.axhline(
                    model.baseline_v - model.droop_budget_v,
                    color="#b43838",
                    ls="--",
                    label="Droop limit from loaded baseline",
                )
                ax.legend(fontsize=8, loc="lower right")
            tran = traces["full"][1]
            axes[2].plot(tran[:, 0] * 1e6, tran[:, 3], color="#383838")
            axes[2].set(ylabel="Load (A)")
            for ax in axes:
                ax.set_xlabel("Time (µs)")
                ax.grid(alpha=0.2)
            fig.savefig(output / "load-step.png", dpi=160)
        finally:
            plt.close(fig)


def report(model, summary):
    h = summary["hand_calculations"]
    rows = []
    peak_rows = []
    for name, result in summary["variants"].items():
        ac, tr = result["ac"], result["transient"]
        rows.append(
            f"| {name} | {ac['max_ohm'] * 1e3:.3f} | {tr['droop_v'] * 1e3:.3f} | "
            f"{tr['minimum_v']:.6f} | {'PASS' if ac['meets_target'] else 'FAIL'} | "
            f"{'PASS' if tr['meets_droop_budget'] else 'FAIL'} |"
        )
        for peak in ac["peaks"]:
            peak_rows.append(
                f"| {name} | {peak['frequency_hz']:.6g} | {peak['impedance_ohm'] * 1e3:.3f} |"
            )
    lines = [
        "# Core rail study\n",
        f"I tested a synthetic {model.nominal_v:g} V rail with a {model.base_a:g} A starting load "
        f"and an extra {model.step_a:g} A rising in {model.rise_s * 1e9:g} ns. "
        "These are example assumptions, not measurements of a GPU.\n",
        "## What the results mean\n",
        "Impedance is how much the supply voltage changes for a small change in current at "
        "each frequency. The load pulse separately checks the voltage dip in time. "
        "A flat target is a design guide; passing a particular pulse does not prove the whole "
        "frequency band passes.\n",
        f"Target = allowed incremental droop / current step = {model.droop_budget_v:g} V / "
        f"{model.step_a:g} A = **{model.target_ohm * 1e3:.3f} mΩ**. "
        f"The sweep covers {model.f_start_hz:g} to {model.f_stop_hz:g} Hz at "
        f"{model.points_per_decade} points per decade. These are requested limits; actual "
        "sampled limits are listed below because a logarithmic grid can end short of the stop.\n",
        "| Design | Worst impedance (mΩ) | Droop (mV) | Minimum rail (V) | "
        "AC target | Pulse budget |",
        "|---|---:|---:|---:|---|---|",
        *rows,
        "\nDroop is measured from the simulated, already loaded baseline. Nominal drop includes "
        "the starting DC loss. The JSON also records overshoot and the time of minimum voltage. "
        "Both pulse edges and the recovery interval are included.\n",
        "![Impedance comparison](impedance.png)\n",
        "![Load-step comparison](load-step.png)\n",
        "## Peaks and failing frequency bands\n",
        "Local impedance maxima are candidate anti-resonances, where energy exchanges between "
        "capacitor banks and their inductances. Values are sampled peaks, not fitted extrema; "
        "increase sweep density to resolve narrow peaks. Endpoints are included in the worst "
        "impedance but are not called anti-resonance peaks.\n",
        "| Design | Peak frequency (Hz) | Peak impedance (mΩ) |",
        "|---|---:|---:|",
        *peak_rows,
    ]
    for name, result in summary["variants"].items():
        start, stop = result["ac"]["sampled_range_hz"]
        lines.append(f"\n{name}: sampled {start:.9g} to {stop:.9g} Hz.")
        bands = result["ac"]["above_target_bands_hz"]
        lines.append(
            f"\n{name}: above target in "
            + (
                ", ".join(f"{a:.6g} to {b:.6g} Hz" for a, b in bands)
                if bands
                else "no sampled band"
            )
            + ". Boundaries interpolate magnitude against log frequency."
        )
    lines += [
        "\n## Hand checks\n",
        f"- DC: Vbase = Vsource - Ibase(Rvrm + Rpath) = {h['dc_baseline_v']:.6f} V; "
        f"high-load equilibrium = {h['dc_high_load_v']:.6f} V.",
        f"- Additional steady resistive loss = ΔI(Rvrm + Rpath) = "
        f"{h['dc_incremental_drop_v'] * 1e3:.3f} mV.",
        f"- Package-path inductive scale: L ΔI / rise time = "
        f"{h['path_l_di_dt_v'] * 1e3:.3f} mV. Capacitors share the current, so this is "
        "a scale estimate, not an additive prediction.",
        "- Charge-only estimate for the linear rising edge: ΔV = ΔI × rise time / (2C). "
        f"All banks lumped together: {h['all_capacitors_charge_only_rise_drop_v']} V; "
        f"die-side banks only: {h['die_capacitors_charge_only_rise_drop_v']} V. "
        "These idealized estimates ignore ESR/ESL and source current and are not bounds.",
    ]
    for bank, f in h["bank_series_resonances_hz"].items():
        lines.append(f"- {bank} series resonance: 1/(2π√LC) = {f:.6g} Hz.")
    for name, result in summary["variants"].items():
        lines.append(
            f"- {name}: maximum complex AC relative error versus the independent "
            f"ladder calculation = {result['max_ac_relative_error']:.3g}."
        )
    lines += [
        "\n## Design comparison and limits\n",
        "I kept the same VRM and shared path in each run. `no_package` removes only the "
        "die-side capacitors. `damped_package` multiplies only their ESR by 20 to show the "
        "trade between damping a resonance and increasing resistive loss. A capacitor can "
        "make a peak worse; more capacitance alone does not guarantee less droop.\n",
        "The VRM is a passive output R/L approximation, with no controller, switching ripple "
        "or current limit. Capacitors are identical parts in parallel; board ceramics use "
        "effective capacitance after assumed DC bias. There is no layout extraction, "
        "mutual inductance, tolerance sweep, temperature model or hardware validation. "
        "The sweep endpoint is an exploratory lumped-model limit, not a validated bandwidth.\n",
        "## Reproducing and inspecting\n",
        "`input.json` preserves the exact SI-unit inputs. Each design has an `*-ac.cir` "
        "and `*-tran.cir` netlist, `*-impedance.csv` and `*-transient.csv` data. "
        "Run a saved circuit with `ngspice -n -b full-ac.cir` from this folder; it writes "
        "`data.dat`. `summary.json` preserves numeric measurements without rounded display values. "
        "See `docs/model.md` in the repository for the equations and numerical checks.\n",
    ]
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sweep a core rail and measure load-step droop")
    parser.add_argument(
        "--config", type=Path, help="JSON inputs in SI units; defaults to example rail"
    )
    parser.add_argument("--output", type=Path, default=Path("results/local"))
    args = parser.parse_args(argv)
    try:
        model = load_study(args.config) if args.config else Study()
        result = run_study(model, args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"pdn-study: {exc}\n")
    full = result["variants"]["full"]
    print(
        f"Wrote {args.output / 'report.md'}; target {model.target_ohm * 1e3:.3f} mΩ, "
        f"original droop {full['transient']['droop_v'] * 1e3:.3f} mV"
    )
    return 0
