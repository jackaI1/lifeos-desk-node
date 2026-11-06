"""Headless plots. Waveforms reconstruct steady-state AC, with no DC offset."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def waveforms(phasors, frequency_hz, cycles=3, samples=1200):
    if not np.isfinite(frequency_hz) or frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")
    if not np.isfinite(cycles) or cycles <= 0 or samples < 2:
        raise ValueError("cycles must be positive and samples at least two")
    values = np.asarray(phasors, dtype=complex)
    if values.shape != (3,) or not np.isfinite(values).all():
        raise ValueError("Expected three finite phasors")
    t = np.linspace(0, cycles / frequency_hz, samples)
    return t, np.sqrt(2) * np.real(values[:, None] * np.exp(2j * np.pi * frequency_hz * t))


def plot_fault(result, frequency_hz, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    colors = ("#0072B2", "#D55E00", "#009E73")
    paths = []
    for mode in ("phasors", "waveforms"):
        fig, ax = plt.subplots(figsize=(8, 5), layout="constrained")
        try:
            currents = result.phase_current_a
            if mode == "phasors":
                for name, value, color in zip("abc", currents, colors):
                    ax.quiver(
                        0,
                        0,
                        value.real,
                        value.imag,
                        angles="xy",
                        scale_units="xy",
                        scale=1,
                        color=color,
                        label=f"Phase {name}: {abs(value):.1f} A",
                    )
                limit = max(1, max(abs(currents))) * 1.2
                ax.set(
                    xlim=(-limit, limit),
                    ylim=(-limit, limit),
                    xlabel="Real current (A RMS)",
                    ylabel="Imaginary current (A RMS)",
                )
                ax.set_aspect("equal")
            else:
                time, values = waveforms(currents, frequency_hz)
                for name, values, color in zip("abc", values, colors):
                    ax.plot(time * 1000, values, color=color, label=f"Phase {name}")
                ax.set(xlabel="Time (ms)", ylabel="Instantaneous current (A)")
            ax.set_title(
                f"{result.fault_type.upper()} fault at {result.bus} | "
                + ("RMS phasors" if mode == "phasors" else "Steady-state AC only")
            )
            ax.grid(alpha=0.25)
            ax.legend(loc="upper right")
            path = directory / f"{result.fault_type}_{mode}.png"
            fig.savefig(path, dpi=150)
            paths.append(path)
        finally:
            plt.close(fig)
    return paths
