"""Portable CSV/JSON/Markdown reports and headless charts; figures always close."""

import csv
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from .batch import BatchResult
from .control import CONTROL_SOURCE

NOTICE = "SIMULATED DATA. Selected class B checks only. Not a certified test or calibration."


def write_report(batch: BatchResult, output: Path) -> None:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    points = {
        p.id: {
            **asdict(p),
            "limit_pct": p.limit_pct,
            "limit_source": p.limit_source,
            "source_url": p.source_url,
        }
        for p in batch.points
    }
    payload = {
        "schema_version": 1,
        "simulated": True,
        "notice": NOTICE,
        "profile": "Selected OIML R 46:2012 class B positive-flow checks",
        "config": asdict(batch.config),
        "sampling": {
            "sample_rate_hz": 7200,
            "frequency_hz": 60,
            "cycles": 12,
            "duration_s": 0.2,
            "voltage_rms_phase_to_neutral": 120,
        },
        "control_method": {
            "source_url": CONTROL_SOURCE,
            "baseline": "separate undrifted units",
            "formula": "mean +/- 3 * mean(abs(diff(baseline))) / 1.128",
            "rule": "one observation strictly outside frozen limits",
        },
        "summary": batch.summary,
        "points": list(points.values()),
        "meters": [asdict(m) for m in batch.meters],
        "baseline_meters": [asdict(m) for m in batch.baseline_meters],
        "control_limits": {key: asdict(value) for key, value in batch.control_limits.items()},
        "units": [asdict(u) for u in batch.units],
        "baseline_measurements": [asdict(m) for m in batch.baseline_measurements],
        "measurements": [asdict(m) for m in batch.measurements],
    }
    (output / "report.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    measurements = []
    for row in batch.baseline_measurements + batch.measurements:
        point = points[row.point_id]
        measurements.append(
            {
                **asdict(row),
                **{
                    key: point[key]
                    for key in (
                        "phases",
                        "current_a",
                        "power_factor",
                        "leading",
                        "point_source",
                        "limit_source",
                        "source_url",
                    )
                },
            }
        )
    for name, data in (("measurements", measurements), ("units", payload["units"])):
        with (output / f"{name}.csv").open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(data[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(data)
    summary = batch.summary
    lines = [
        "# Simulated batch report",
        "",
        NOTICE,
        "",
        f"{summary['passed_units']}/{summary['total_units']} units passed every selected point.",
        f"First control alarm: {summary['first_control_alarm']}; "
        f"first failed unit: {summary['first_failed_unit']} (None means none observed).",
        "",
        "Control alarms flag unusual variation; they do not change a unit's accuracy verdict.",
        "Limits use a separate undrifted baseline for each load point, never this batch.",
        "",
        "| Unit | Accuracy verdict | Failed points | Control alarms |",
        "| --- | --- | ---: | ---: |",
    ]
    lines.extend(
        f"| {u.id} | {'PASS' if u.passed else 'FAIL'} | {u.failed_points} | {u.control_alarms} |"
        for u in batch.units
    )
    lines += [
        "",
        "Full unrounded point readings and citations: measurements.csv and report.json.",
        "",
        "![Single-phase control charts](control-1ph.png)",
        "",
        "![Three-phase control charts](control-3ph.png)",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    for phases in (1, 3):
        _chart(batch, phases, output / f"control-{phases}ph.png")


def _chart(batch: BatchResult, phases: int, path: Path) -> None:
    fig, axes = plt.subplots(4, 3, figsize=(15, 12), layout="constrained")
    try:
        for ax, point in zip(
            axes.flat, (p for p in batch.points if p.phases == phases), strict=True
        ):
            baseline = [r.error_pct for r in batch.baseline_measurements if r.point_id == point.id]
            rows = [r for r in batch.measurements if r.point_id == point.id]
            limits = batch.control_limits[point.id]
            ax.plot(range(1 - len(baseline), 1), baseline, color=".65", linewidth=0.9)
            ax.plot(
                [r.unit_index for r in rows],
                [r.error_pct for r in rows],
                color="#24648c",
                linewidth=1,
            )
            colors = [
                "#b12c2c" if not r.passed else "#b77000" if r.control_alarm else "#24648c"
                for r in rows
            ]
            ax.scatter(
                [r.unit_index for r in rows], [r.error_pct for r in rows], c=colors, s=12, zorder=3
            )
            ax.axhline(limits.center, color=".5", linewidth=0.7)
            for value in (limits.lower, limits.upper):
                ax.axhline(value, color="#b77000", linestyle="--", linewidth=0.9)
            for value in (-point.limit_pct, point.limit_pct):
                ax.axhline(value, color="#b12c2c", linestyle=":", linewidth=1)
            ax.axvline(0.5, color=".6", linewidth=0.7)
            ax.set_title(point.id, fontsize=10)
            ax.set_xlabel("Baseline (<=0) / production unit (>=1)", fontsize=8)
            ax.set_ylabel("Energy error (%)", fontsize=8)
            ax.grid(alpha=0.15)
        fig.suptitle(
            f"SIMULATED {phases}-phase batch: fixed-baseline individuals charts\n"
            "Amber: 3-sigma control limits / alarms. Red: accuracy limits / failures.",
            fontsize=13,
        )
        fig.legend(
            handles=[
                Line2D([], [], color=".65", label="Undrifted baseline"),
                Line2D([], [], color="#24648c", label="Production error"),
            ],
            loc="outside lower center",
            ncol=2,
        )
        fig.savefig(path, dpi=130)
    finally:
        plt.close(fig)
