"""Run a complete selected load table for every simulated unit."""

import math
from dataclasses import dataclass, replace

from .control import ControlLimits
from .meter import Meter, make_meter
from .profile import TestPoint, default_points
from .waveforms import energy_wh, synthesize


@dataclass(frozen=True)
class BatchConfig:
    seed: int = 42
    units: int = 40
    baseline_units: int = 20
    gain_drift_pct: float = 0.035  # Percentage points per successive production unit.
    phase_drift_deg: float = 0
    offset_drift_w: float = 0

    def __post_init__(self):
        for name, minimum in (("seed", 0), ("units", 1), ("baseline_units", 10)):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if not all(
            math.isfinite(x)
            for x in (self.gain_drift_pct, self.phase_drift_deg, self.offset_drift_w)
        ):
            raise ValueError("drift parameters must be finite")


def within_limit(error_pct: float, limit_pct: float) -> bool:
    if not math.isfinite(error_pct) or not math.isfinite(limit_pct) or limit_pct <= 0:
        raise ValueError("finite error and positive finite limit required")
    # Only absorb floating-point roundoff at an exact boundary; never round for decisions.
    return bool(abs(error_pct) <= limit_pct + 1e-10)


@dataclass(frozen=True)
class Measurement:
    role: str
    unit_id: str
    unit_index: int
    point_id: str
    reference_wh: float
    meter_wh: float
    error_pct: float
    limit_pct: float
    passed: bool
    control_alarm: bool = False


@dataclass(frozen=True)
class UnitResult:
    id: str
    index: int
    passed: bool
    failed_points: int
    control_alarms: int


@dataclass
class BatchResult:
    config: BatchConfig
    points: tuple[TestPoint, ...]
    meters: list[Meter]
    baseline_meters: list[Meter]
    baseline_measurements: list[Measurement]
    measurements: list[Measurement]
    control_limits: dict[str, ControlLimits]
    units: list[UnitResult]

    @property
    def summary(self) -> dict:
        return {
            "total_units": len(self.units),
            "passed_units": sum(u.passed for u in self.units),
            "failed_units": sum(not u.passed for u in self.units),
            "units_with_control_alarms": sum(u.control_alarms > 0 for u in self.units),
            "first_control_alarm": next((u.index for u in self.units if u.control_alarms), None),
            "first_failed_unit": next((u.index for u in self.units if not u.passed), None),
            "production_measurements": len(self.measurements),
            "baseline_measurements": len(self.baseline_measurements),
        }


def run_batch(config: BatchConfig) -> BatchResult:
    points = default_points()
    # Baseline uses a distinct, reproducible random stream, with no injected drift.
    baseline = [
        make_meter(config.seed ^ 0xBACE, i, prefix="BASE") for i in range(config.baseline_units)
    ]
    meters = [
        make_meter(
            config.seed,
            i,
            gain_shift_pct=i * config.gain_drift_pct,
            phase_shift_deg=i * config.phase_drift_deg,
            offset_shift_w=i * config.offset_drift_w,
        )
        for i in range(config.units)
    ]
    baseline_rows, rows, limits = [], [], {}
    for point in points:
        samples = synthesize(point)
        reference = energy_wh(samples.voltage, samples.current, samples.sample_rate)
        if reference <= 0:
            raise ValueError("percentage comparison requires positive reference energy")

        def measure(meter, index, role, samples=samples, reference=reference, point=point):
            reading = meter.read_wh(samples)
            error = 100 * (reading - reference) / reference
            return Measurement(
                role,
                meter.id,
                index + 1,
                point.id,
                reference,
                reading,
                error,
                point.limit_pct,
                within_limit(error, point.limit_pct),
            )

        point_baseline = [measure(meter, i, "baseline") for i, meter in enumerate(baseline)]
        baseline_rows.extend(point_baseline)
        limit = ControlLimits.fit([r.error_pct for r in point_baseline])
        limits[point.id] = limit
        for i, meter in enumerate(meters):
            row = measure(meter, i, "production")
            rows.append(replace(row, control_alarm=limit.alarm(row.error_pct)))
    units = []
    for i, meter in enumerate(meters):
        unit_rows = [r for r in rows if r.unit_id == meter.id]
        units.append(
            UnitResult(
                meter.id,
                i + 1,
                all(r.passed for r in unit_rows),
                sum(not r.passed for r in unit_rows),
                sum(r.control_alarm for r in unit_rows),
            )
        )
    return BatchResult(config, points, meters, baseline, baseline_rows, rows, limits, units)
