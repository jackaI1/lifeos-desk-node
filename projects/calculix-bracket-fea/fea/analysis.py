"""Small, unit-consistent checks and strict CalculiX text-result readers."""
import math
from pathlib import Path


def cantilever(length, width, height, force, young):
    """Euler-Bernoulli end deflection and root bending stress (N, mm, MPa)."""
    if not all(math.isfinite(v) for v in (length, width, height, force, young)):
        raise ValueError('inputs must be finite')
    if min(length, width, height, young) <= 0:
        raise ValueError('geometry and modulus must be positive')
    inertia = width * height**3 / 12
    return abs(force)*length**3/(3*young*inertia), abs(force)*length*height/(2*inertia)


def von_mises(s):
    """CalculiX tensor order: xx, yy, zz, xy, xz, yz; true shear stress."""
    xx, yy, zz, xy, xz, yz = s
    return math.sqrt(((xx-yy)**2+(yy-zz)**2+(zz-xx)**2)/2 + 3*(xy*xy+xz*xz+yz*yz))


def parse_dat(path):
    """Read one static step's U, S and RF tables; fail closed on incomplete data."""
    result = {'displacements': {}, 'stresses': {}, 'forces': {}}
    active = None
    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        header = next((key for key in result if stripped.startswith(key+' ')), None)
        if header:
            if result[header]:
                raise ValueError('multiple result frames are not supported')
            active = header
            continue
        if not stripped:
            continue
        if active is None:
            continue
        if not (stripped[0].isdigit() or stripped[0] == '-'):
            active = None
            continue
        fields = stripped.replace('D', 'E').split()
        indices = 2 if active == 'stresses' else 1
        if len(fields) != indices + (6 if active == 'stresses' else 3):
            raise ValueError(f'malformed {active} row')
        ids = tuple(int(s) for s in fields[:indices])
        key = ids if indices == 2 else ids[0]
        values = tuple(float(s) for s in fields[indices:])
        if not all(math.isfinite(v) for v in values) or key in result[active]:
            raise ValueError('nonfinite or duplicate solver result')
        result[active][key] = values
    if not all(result.values()):
        raise ValueError('missing displacement, stress or reaction results')
    return result


def parse_frd(path):
    """Read one ASCII FRD nodal stress frame, normalized to DAT tensor order."""
    stress, active, complete = {}, False, False
    for line in Path(path).read_text().splitlines():
        if line.startswith(' -4'):
            if 'STRESS' in line:
                if active or complete:
                    raise ValueError('multiple stress frames are not supported')
                active = True
            elif active:
                raise ValueError('unterminated stress frame')
        elif active and line.startswith(' -1'):
            if len(line.rstrip()) != 85:
                raise ValueError('malformed FRD stress row')
            node = int(line[3:13])
            v = tuple(float(line[i:i+12].replace('D','E')) for i in range(13,85,12))
            if len(v) != 6 or not all(math.isfinite(s) for s in v) or node in stress:
                raise ValueError('nonfinite or duplicate FRD result')
            stress[node] = (v[0],v[1],v[2],v[3],v[5],v[4])
        elif active and line.startswith(' -3'):
            active, complete = False, True
    if not complete or not stress:
        raise ValueError('missing or incomplete FRD stress output')
    return stress
