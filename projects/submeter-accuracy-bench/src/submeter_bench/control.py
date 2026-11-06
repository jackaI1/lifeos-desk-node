"""Individuals chart limits fitted only to a separate baseline, never the monitored batch."""

import math
from dataclasses import dataclass

import numpy as np

CONTROL_SOURCE = "https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm"


@dataclass(frozen=True)
class ControlLimits:
    center: float
    sigma: float
    lower: float
    upper: float

    @classmethod
    def fit(cls, errors: list[float]) -> "ControlLimits":
        values = np.asarray(errors, dtype=float)
        if values.ndim != 1 or len(values) < 10 or not np.isfinite(values).all():
            raise ValueError("control baseline needs at least 10 finite observations")
        center = float(np.mean(values))
        sigma = float(np.mean(np.abs(np.diff(values))) / 1.128)
        if not math.isfinite(sigma) or sigma <= 1e-12:
            raise ValueError("zero-spread baseline cannot estimate process variation")
        return cls(center, sigma, center - 3 * sigma, center + 3 * sigma)

    def alarm(self, error_pct: float) -> bool:
        if not math.isfinite(error_pct):
            raise ValueError("control observation must be finite")
        return error_pct < self.lower or error_pct > self.upper
