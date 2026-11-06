"""Headless PNG previews drawn from the independently parsed G-code moves."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle  # noqa: E402

from .model import Job  # noqa: E402
from .simulator import Report  # noqa: E402


def render(job: Job, report: Report, output: str | Path) -> None:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 7))
    try:
        ax.add_patch(Rectangle((0, 0), *job.stock[:2], fc="#f3efe4", ec="#6d6658"))
        ax.add_patch(Polygon(job.outline, fc="#d6dfda", ec="#174e48", lw=2))
        x0, y0, x1, y1 = job.pocket
        ax.add_patch(FancyBboxPatch((x0, y0), x1-x0, y1-y0,
                                   boxstyle=f"round,pad=0,rounding_size={job.diameter / 2}",
                                   fc="white", ec="#174e48"))
        for hole in job.holes:
            ax.add_patch(Circle(hole, job.diameter / 2, fc="white", ec="#174e48"))
        for rapid, color, label in ((False, "#167c80", "Feed move"),
                                    (True, "#c76b24", "Rapid at clearance")):
            segments = [[m.start[:2], m.end[:2]] for m in report.moves if m.rapid == rapid]
            ax.add_collection(LineCollection(segments, colors=color, linewidths=0.65,
                                             linestyles="dashed" if rapid else "solid",
                                             alpha=0.65, label=label))
        ax.set(xlim=(-2, job.stock[0]+2), ylim=(-2, job.stock[1]+2), aspect="equal",
               xlabel="X (mm)", ylabel="Y (mm)",
               title="Bracket | cutter-centre paths from emitted G-code")
        ax.legend(loc="upper right")
        fig.tight_layout()
        fig.savefig(output / "toolpath-top.png", dpi=150)
    finally:
        plt.close(fig)
    fig = plt.figure(figsize=(10, 7))
    try:
        ax = fig.add_subplot(projection="3d")
        # One collection per move type avoids thousands of plot objects.
        from mpl_toolkits.mplot3d.art3d import Line3DCollection
        for rapid, color in ((False, "#167c80"), (True, "#c76b24")):
            segments = [[m.start, m.end] for m in report.moves if m.rapid == rapid]
            ax.add_collection3d(Line3DCollection(segments, colors=color, linewidths=0.5,
                                                alpha=0.65))
        ax.set(xlim=(0, job.stock[0]), ylim=(0, job.stock[1]),
               zlim=(-job.stock[2], job.safe_z), xlabel="X (mm)", ylabel="Y (mm)",
               zlabel="Z (mm)", title="Depth passes | stock top at Z0")
        ax.view_init(elev=30, azim=-60)
        fig.tight_layout()
        fig.savefig(output / "toolpath-3d.png", dpi=150)
    finally:
        plt.close(fig)
