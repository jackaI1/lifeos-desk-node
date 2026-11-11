"""Run the benchmark, the two load cases and the wall-thickness sweep; write the report."""
import json
import math
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from .board import CaseParams
from .geometry import mesh_box, mesh_case
from .loads import cantilever_loads, drop_loads, screw_down_loads, supports
from .solver import parse_dat, run_ccx, summarize, write_deck

HERE = Path(__file__).resolve().parent.parent
MATERIALS = json.loads((HERE / 'specs' / 'materials.json').read_text())
PRINTED = 'PETG printed'
MACHINED = '6061-T6 machined'

SCREW_PRELOAD_N = 300.0      # per lid screw; about 0.18 N·m on an M3 screw (0.2 x F x d)
DROP_STATIC_N = 50.0         # 0.5 kg device, static stand-in for a 10 g impact
DROP_HARSH_N = 500.0         # about 100 g on the same device, a harsher drop for the design wall
WALL_SWEEP_MM = (2.0, 2.5, 3.0, 3.5, 4.0)
MESH_MM = 1.0                       # production mesh for the sweep and machined case
MESH_CHECK_MM = (2.0, 1.4, 1.0)     # coarse to fine; 0.7 mm ran out of memory on a 24 GB Mac


def cantilever_check(work, lc=1.0, length=100.0, width=10.0, height=5.0, force=10.0, young=70000.0,
                     poisson=0.33):
    """Compare CalculiX with Euler-Bernoulli tip deflection and root bending stress."""
    inertia = width * height ** 3 / 12
    closed_deflection = force * length ** 3 / (3 * young * inertia)
    closed_stress = force * length * (height / 2) / inertia
    mesh = mesh_box(length, width, height, lc)
    fixed, loads, tip = cantilever_loads(mesh, force)
    directory = Path(work) / 'cantilever'
    directory.mkdir(parents=True, exist_ok=True)
    write_deck(directory / 'cantilever.inp', mesh, dict(youngs_mpa=young, poisson=poisson), fixed, loads)
    data = parse_dat(run_ccx(directory, 'cantilever'))
    summary = summarize(mesh, data, loads, tip)
    fem_deflection = abs(summary['load_point_deflection_mm'])
    bending = _bending_stress_error(mesh, data, length, height, force, inertia)
    return dict(
        closed_form_deflection_mm=closed_deflection,
        fem_deflection_mm=fem_deflection,
        deflection_error=abs(fem_deflection - closed_deflection) / closed_deflection,
        closed_form_root_stress_mpa=closed_stress,
        bending_stress_rms_error=bending['rms'],
        bending_stress_max_error=bending['max'],
        bending_stress_elements=bending['elements'],
        elements=summary['elements'],
    )


def _bending_stress_error(mesh, data, length, height, force, inertia):
    """Axial stress along the span, compared with sigma = F (L - x) (z - h/2) / I.

    Each element's Gauss-point stresses are averaged first, which gives the value at the
    element centre. Only the middle half of the span is used: the clamped end and the tip
    load disturb the field close to either end. Errors are relative to the closed-form peak.
    """
    element_nodes = dict(zip((int(e) for e in mesh['element_ids']), mesh['elements']))
    per_element = {}
    for (eid, _), s in data['stresses'].items():
        per_element.setdefault(eid, []).append(s[0])
    errors, peak = [], 0.0
    for eid, values in per_element.items():
        centre = np.mean([mesh['nodes'][int(n)] for n in element_nodes[eid][:4]], axis=0)
        x, z = centre[0], centre[2]
        if not (0.25 * length <= x <= 0.75 * length):
            continue
        closed = force * (length - x) * (z - height / 2) / inertia
        peak = max(peak, abs(closed))
        errors.append(np.mean(values) - closed)
    if not errors or peak == 0:
        raise ValueError('no elements in the bending check band')
    errors = np.array(errors)
    return dict(rms=float(np.sqrt(np.mean(errors ** 2)) / peak),
                max=float(np.max(np.abs(errors)) / peak), elements=len(errors))


def _solve(work, name, mesh, params, material, kind, force=None):
    """Solve one load case on one mesh. Each solve gets its own folder.

    force is the lid preload per screw (screw) or the drop force (drop); it defaults to the
    study value for that load case.
    """
    directory = Path(work) / name
    directory.mkdir(parents=True, exist_ok=True)
    sup = supports(mesh, params)
    if kind == 'screw':
        preload = SCREW_PRELOAD_N if force is None else force
        loads = screw_down_loads(mesh, params, preload)
        load_nodes = None
        applied = 4 * preload
    else:
        drop = DROP_STATIC_N if force is None else force
        loads, load_nodes = drop_loads(mesh, params, drop)
        applied = drop
    write_deck(directory / f'{name}.inp', mesh, material, sup['fixed'], loads)
    started = time.time()
    data = parse_dat(run_ccx(directory, name))
    summary = summarize(mesh, data, loads, load_nodes)
    summary.update(load_case=kind, applied_n=applied, wall_mm=params.wall, mesh_mm=mesh['lc'],
                   material=material, seconds=round(time.time() - started, 1))
    summary['safety_factor'] = material['yield_mpa'] / summary['peak_von_mises_mpa']
    summary['margin_of_safety'] = summary['safety_factor'] - 1
    return summary


def _mesh_convergence(work, design, sweep):
    """Screw load on the 2.0 mm wall at three mesh sizes. The 1.0 mm point reuses the sweep."""
    reference = next(r for r in sweep if r['wall_mm'] == design.wall and r['load_case'] == 'screw')
    rows = []
    for lc in MESH_CHECK_MM:
        if lc == MESH_MM:
            result = reference
        else:
            mesh = mesh_case(design, lc)
            result = _solve(work, f'screw-mesh{lc:.1f}'.replace('.', 'p'), mesh, design, MATERIALS[PRINTED], 'screw')
        rows.append(dict(mesh_mm=lc, elements=result['elements'], peak_mpa=result['peak_von_mises_mpa'],
                         p95_mpa=result['p95_von_mises_mpa'], deflection_mm=result['max_displacement_mm']))
    return rows


def run_study(work, report=None, mesh_check=True):
    """Full study: cantilever check, wall sweep with both loads, machined comparison, mesh check.

    The 2.0 mm wall is the design point. Its mesh is built once and shared by the sweep and
    the machined comparison.
    """
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    results = dict(cantilever=cantilever_check(work), sweep=[], machined=[], harsh_drop=None, mesh_check=[])
    design = CaseParams().validate()
    design_mesh = None
    for wall in WALL_SWEEP_MM:
        params = replace(design, wall=wall).validate()
        mesh = mesh_case(params, MESH_MM)
        if wall == design.wall:
            design_mesh = mesh
        for kind in ('screw', 'drop'):
            name = f'{kind}-wall{wall:.1f}'.replace('.', 'p')
            results['sweep'].append(_solve(work, name, mesh, params, MATERIALS[PRINTED], kind))
    for kind in ('screw', 'drop'):
        results['machined'].append(_solve(work, f'{kind}-machined', design_mesh, design,
                                          MATERIALS[MACHINED], kind))
    results['harsh_drop'] = _solve(work, 'drop-harsh-wall2p0', design_mesh, design, MATERIALS[PRINTED],
                                   'drop', force=DROP_HARSH_N)
    if mesh_check:
        results['mesh_check'] = _mesh_convergence(work, design, results['sweep'])
    report = Path(report) if report else None
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.with_suffix('.json').write_text(json.dumps(results, indent=2) + '\n')
        report.write_text(render_markdown(results))
    return results


def _change(before, after):
    return f"{(after - before) / before:+.1%}"


def render_markdown(results):
    c = results['cantilever']
    lines = ['# Desk-node case study results', '',
             'Generated by `python -m enclosure_fea study`. Units: N, mm, MPa.', '',
             '## Solver check: cantilever bar', '',
             '| Quantity | Closed form | CalculiX | Error |', '|---|---:|---:|---:|',
             f"| Tip deflection (mm) | {c['closed_form_deflection_mm']:.5f} | {c['fem_deflection_mm']:.5f} | {c['deflection_error']:.2%} |",
             f"| Bending stress, middle half of span (max error vs peak {c['closed_form_root_stress_mpa']:.1f} MPa) | | | RMS {c['bending_stress_rms_error']:.3%}, max {c['bending_stress_max_error']:.3%} |",
             '', '## Load cases at the default 2.0 mm wall (PETG printed)', '']
    lines += ['| Load | Peak von Mises (MPa) | 95th percentile (MPa) | Max deflection (mm) | Safety factor vs yield |',
              '|---|---:|---:|---:|---:|']
    for r in results['sweep']:
        if r['wall_mm'] == 2.0:
            lines.append(f"| {r['load_case']} | {r['peak_von_mises_mpa']:.1f} | {r['p95_von_mises_mpa']:.1f} | "
                         f"{r['max_displacement_mm']:.4f} | {r['safety_factor']:.2f} |")
    lines += ['', '## Wall-thickness sweep (PETG printed)', '',
              '| Wall (mm) | Load | Peak von Mises (MPa) | 95th percentile (MPa) | Max deflection (mm) | Safety factor |',
              '|---:|---|---:|---:|---:|---:|']
    for r in results['sweep']:
        lines.append(f"| {r['wall_mm']:.1f} | {r['load_case']} | {r['peak_von_mises_mpa']:.1f} | "
                     f"{r['p95_von_mises_mpa']:.1f} | {r['max_displacement_mm']:.4f} | {r['safety_factor']:.2f} |")
    lines += ['', '## Machined 6061-T6 alternative (2.0 mm wall)', '',
              '| Load | Peak von Mises (MPa) | Max deflection (mm) | Safety factor |', '|---|---:|---:|---:|']
    for r in results['machined']:
        lines.append(f"| {r['load_case']} | {r['peak_von_mises_mpa']:.1f} | {r['max_displacement_mm']:.4f} | "
                     f"{r['safety_factor']:.2f} |")
    h = results['harsh_drop']
    lines += ['', '## Harsher drop (about 100 g on the 0.5 kg device, 2.0 mm wall, PETG printed)', '',
              '| Load | Peak von Mises (MPa) | 95th percentile (MPa) | Max deflection (mm) | Safety factor |',
              '|---|---:|---:|---:|---:|',
              f"| {h['applied_n']:.0f} N drop | {h['peak_von_mises_mpa']:.1f} | {h['p95_von_mises_mpa']:.1f} | "
              f"{h['max_displacement_mm']:.4f} | {h['safety_factor']:.2f} |"]
    if results['mesh_check']:
        lines += ['', '## Mesh convergence (screw load, 2.0 mm wall)', '',
                  '| Mesh (mm) | Elements | Peak von Mises (MPa) | 95th percentile (MPa) | Max deflection (mm) |',
                  '|---:|---:|---:|---:|---:|']
        for m in results['mesh_check']:
            lines.append(f"| {m['mesh_mm']:.1f} | {m['elements']} | {m['peak_mpa']:.1f} | {m['p95_mpa']:.1f} | "
                         f"{m['deflection_mm']:.4f} |")
        last, before = results['mesh_check'][-1], results['mesh_check'][-2]
        lines += ['', f"Between the last two meshes the peak moved {_change(before['peak_mpa'], last['peak_mpa'])} "
                  f"and the deflection moved {_change(before['deflection_mm'], last['deflection_mm'])}. "
                  'If the peak has not settled, read it as a screening value rather than a final stress.']
    return '\n'.join(lines) + '\n'
