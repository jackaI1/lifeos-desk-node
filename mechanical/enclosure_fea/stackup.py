"""Tolerance stack-up for the board, its standoffs and the case.

Two chains are checked:
* vertical: cavity height minus the standoff, board and tallest part must leave a gap for the lid;
* radial: the M3 screw must still pass through the board hole when the hole and the boss
  are both off their nominal positions.

Each chain is reported two ways. Worst case adds every tolerance at its limit, which holds
for any combination of parts. Root-sum-square (RSS) adds them in quadrature, which is a
statistical estimate for a batch of parts and is less conservative.
"""
import json
import math
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parent.parent / 'specs' / 'stackup.json'


def load_spec(path=SPEC_PATH):
    spec = json.loads(Path(path).read_text())
    if spec.get('units') != 'mm':
        raise ValueError('stack-up spec must be in mm')
    return spec


def _check_tol(value, name):
    if not (isinstance(value, (int, float)) and math.isfinite(value) and value >= 0):
        raise ValueError(f'{name} must be a non-negative finite tolerance')
    return float(value)


def vertical_clearance(spec):
    """Nominal clearance and worst-case / RSS clearance above the board."""
    v = spec['vertical']
    nominal = 0.0
    tols = []
    for item in v['items']:
        if item['sign'] not in (1, -1):
            raise ValueError('sign must be +1 or -1')
        nominal += item['sign'] * item['nominal']
        tols.append(_check_tol(item['tol'], item['name']))
    worst = nominal - sum(tols)
    rss = nominal - math.sqrt(sum(t * t for t in tols))
    required = v['required_min_clearance_mm']
    return dict(nominal_mm=nominal, worst_case_mm=worst, rss_mm=rss, required_mm=required,
                worst_case_pass=worst >= required, rss_pass=rss >= required)


def radial_clearance(spec, hole_diameter=None):
    """Radial room for the screw: half the hole-minus-screw gap, less the position error."""
    r = spec['radial']
    hole = r['hole_nominal_mm'] if hole_diameter is None else hole_diameter
    hole_min = hole - _check_tol(r['hole_tol_mm'], 'hole tolerance')
    slack = (hole_min - r['screw_major_max_mm']) / 2
    tols = [_check_tol(item['tol'], item['name']) for item in r['position_items']]
    worst_position = sum(tols)
    rss_position = math.sqrt(sum(t * t for t in tols))
    required = r['required_min_clearance_mm']
    worst = slack - worst_position
    rss = slack - rss_position
    # Smallest nominal hole that keeps the worst-case clearance at zero, given the same screw.
    needed = r['screw_major_max_mm'] + 2 * worst_position + _check_tol(r['hole_tol_mm'], 'hole tolerance')
    return dict(hole_min_mm=hole_min, slack_mm=slack, worst_position_mm=worst_position,
                rss_position_mm=rss_position, worst_case_mm=worst, rss_mm=rss,
                required_mm=required, worst_case_pass=worst >= required, rss_pass=rss >= required,
                hole_needed_worst_mm=needed)


def report(spec=None):
    spec = spec or load_spec()
    return dict(vertical=vertical_clearance(spec), radial=radial_clearance(spec),
                radial_with_3_5_mm_hole=radial_clearance(spec, hole_diameter=3.5))
