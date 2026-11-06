"""IEC standard-inverse phase-overcurrent timing on primary RMS amperes."""

import math
from dataclasses import dataclass

from .model import positive


@dataclass(frozen=True)
class Relay:
    pickup_a: float
    time_dial: float = 0.1

    def __post_init__(self):
        positive(self.pickup_a, "pickup_a")
        positive(self.time_dial, "time_dial")

    def check(self, current_a, max_time_s=1.0):
        """None trip time at/below pickup; deadline includes relay time only."""
        positive(max_time_s, "max_time_s")
        current = abs(complex(current_a))
        if not math.isfinite(current):
            raise ValueError("current_a must be finite")
        multiple = current / self.pickup_a
        picked_up = multiple > 1
        denominator = math.expm1(0.02 * math.log(multiple)) if picked_up else None
        time = self.time_dial * 0.14 / denominator if picked_up else None
        return {
            "current_a_rms": current,
            "pickup_multiple": multiple,
            "picked_up": picked_up,
            "trip_time_s": time,
            "max_time_s": max_time_s,
            "meets_deadline": time is not None and time <= max_time_s,
            "maximum_time_dial": max_time_s * denominator / 0.14 if picked_up else None,
        }
