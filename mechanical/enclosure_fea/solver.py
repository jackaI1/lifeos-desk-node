"""Write a CalculiX static deck (C3D10, linear elastic, N-mm-MPa), run ccx, read results.

The reader is strict: a missing table, a duplicate row or a non-finite value raises an
error instead of returning a partial answer.
"""
import math
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np


def solver_executable():
    override = os.environ.get('CCX')
    if override:
        found = shutil.which(override)
        if found is None:
            raise RuntimeError('CCX is set but not an executable; see mechanical/README.md')
        return found
    found = shutil.which('ccx') or shutil.which('ccx_2.23')
    if found is None:
        raise RuntimeError('CalculiX (ccx) not found; install it or set CCX, see mechanical/README.md')
    return found


def write_deck(path, mesh, material, supports, loads, name='SOLID'):
    """supports: node -> tuple of fixed DOFs; loads: node -> 3-vector in N."""
    path = Path(path)
    with path.open('w') as f:
        f.write('*HEADING\nDesk-node case, linear static, N mm MPa\n*NODE,NSET=ALL\n')
        for n in sorted(mesh['nodes']):
            f.write(f'{n},' + ','.join(f'{v:.12g}' for v in mesh['nodes'][n]) + '\n')
        f.write(f'*ELEMENT,TYPE=C3D10,ELSET={name}\n')
        for eid, conn in zip(mesh['element_ids'], mesh['elements']):
            f.write(f'{int(eid)},' + ','.join(str(int(n)) for n in conn) + '\n')
        f.write('*MATERIAL,NAME=MAT\n*ELASTIC\n')
        f.write(f"{material['youngs_mpa']:.12g},{material['poisson']:.12g}\n")
        f.write(f'*SOLID SECTION,ELSET={name},MATERIAL=MAT\n')
        f.write('*NSET,NSET=SUPPORTS\n')
        nodes = sorted(supports)
        for i in range(0, len(nodes), 16):
            f.write(','.join(str(n) for n in nodes[i:i + 16]) + '\n')
        f.write('*BOUNDARY\n')
        for n in nodes:
            for dof in supports[n]:
                f.write(f'{n},{dof},{dof},0\n')
        f.write('*STEP\n*STATIC\n*CLOAD\n')
        for n in sorted(loads):
            for dof, v in enumerate(loads[n], 1):
                if v != 0:
                    f.write(f'{n},{dof},{v:.12g}\n')
        f.write('*NODE PRINT,NSET=ALL\nU\n*NODE PRINT,NSET=SUPPORTS\nRF\n')
        f.write(f'*EL PRINT,ELSET={name}\nS\n*END STEP\n')
    return path


def run_ccx(directory, job):
    """Run ccx once in directory; raise unless the log reports a clean finish."""
    executable = solver_executable()
    directory = Path(directory).resolve()
    env = dict(os.environ, OMP_NUM_THREADS='1', NUMBER_OF_CPUS='1')
    log = directory / f'{job}.log'
    with log.open('w') as output:
        completed = subprocess.run([executable, '-i', job], cwd=directory, env=env,
                                   stdout=output, stderr=subprocess.STDOUT, timeout=900)
    text = log.read_text(errors='replace')
    if completed.returncode or '*ERROR' in text or 'Job finished' not in text:
        raise RuntimeError(f'CalculiX failed; see {log}')
    return directory / f'{job}.dat'


def parse_dat(path):
    """Read the displacement, stress and reaction tables of one static step."""
    result = {'displacements': {}, 'stresses': {}, 'forces': {}}
    kinds = {'displacements': 1, 'stresses': 2, 'forces': 1}
    width = {'displacements': 3, 'stresses': 6, 'forces': 3}
    active = None
    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        header = next((k for k in result if stripped.startswith(k + ' ') or stripped.startswith(k + '(')), None)
        if header:
            if result[header]:
                raise ValueError('multiple result frames are not supported')
            active = header
            continue
        if not stripped or active is None:
            continue
        if not (stripped[0].isdigit() or stripped[0] == '-'):
            active = None
            continue
        fields = stripped.replace('D', 'E').split()
        ids = kinds[active]
        if len(fields) != ids + width[active]:
            raise ValueError(f'malformed {active} row')
        key = tuple(int(v) for v in fields[:ids])
        key = key if ids == 2 else key[0]
        values = tuple(float(v) for v in fields[ids:])
        if not all(math.isfinite(v) for v in values) or key in result[active]:
            raise ValueError('nonfinite or duplicate solver result')
        result[active][key] = values
    if not all(result.values()):
        raise ValueError('missing displacement, stress or reaction table')
    return result


def von_mises(s):
    """CalculiX order: xx, yy, zz, xy, xz, yz (tensor shear components)."""
    xx, yy, zz, xy, xz, yz = s
    return math.sqrt(((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) / 2
                     + 3 * (xy * xy + xz * xz + yz * yz))


def summarize(mesh, data, loads, load_nodes=None):
    """Peak stress, percentile stress, deflection and reaction checks for one solve."""
    vm = {key: von_mises(s) for key, s in data['stresses'].items()}
    if not vm:
        raise ValueError('no stress results')
    values = np.array(list(vm.values()))
    peak_key = max(vm, key=vm.get)
    element_nodes = {int(e): conn for e, conn in zip(mesh['element_ids'], mesh['elements'])}
    centroid = np.mean([mesh['nodes'][int(n)] for n in element_nodes[peak_key[0]][:4]], axis=0)
    disp = {n: np.linalg.norm(u) for n, u in data['displacements'].items()}
    applied = np.sum(list(loads.values()), axis=0)
    reaction = np.sum(list(data['forces'].values()), axis=0)
    summary = dict(
        peak_von_mises_mpa=float(vm[peak_key]),
        peak_element=int(peak_key[0]),
        peak_xyz_mm=[round(float(c), 3) for c in centroid],
        p95_von_mises_mpa=float(np.percentile(values, 95)),
        max_displacement_mm=float(max(disp.values())),
        applied_force_n=[float(v) for v in applied],
        reaction_force_n=[float(v) for v in reaction],
        force_balance_error=float(np.linalg.norm(applied + reaction) / max(np.linalg.norm(applied), 1e-12)),
        elements=len(mesh['elements']),
        nodes=len(mesh['nodes']),
    )
    if load_nodes is not None:
        nodes_on_load = [n for n in load_nodes if n in data['displacements']]
        if nodes_on_load:
            summary['load_point_deflection_mm'] = float(np.mean(
                [data['displacements'][n][2] for n in nodes_on_load]))
    return summary
