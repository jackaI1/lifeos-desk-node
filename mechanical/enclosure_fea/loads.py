"""Supports and loads for the case, chosen from the boundary triangles of the mesh.

Two load cases are used:
* screw-down: each lid screw pulls the lid onto its post with a preload, which the
  post top carries as a compressive load (a ring-shaped patch on each post top);
* drop: a static stand-in for an impact. The case rests flat on the desk and a point
  load (spread over a short patch) pushes down on the top of the -y wall.
"""
import math

import numpy as np

from .board import CaseParams


def _centroid(mesh, tri):
    pts = np.array([mesh['nodes'][int(n)] for n in tri[:3]])
    return pts.mean(axis=0)


def _triangles_where(mesh, predicate):
    return [tri for tri in mesh['triangles'] if predicate(tri, _centroid(mesh, tri))]


def _all_at_z(mesh, tri, z, tol=1e-6):
    return all(abs(mesh['nodes'][int(n)][2] - z) < tol for n in tri)


def traction_loads(mesh, triangles, force):
    """Distribute a constant traction over TRI6 faces: corner nodes carry none, mid-sides A/3."""
    force = np.asarray(force, dtype=float)
    if force.shape != (3,) or not np.all(np.isfinite(force)):
        raise ValueError('force must have three finite components')
    if not len(triangles):
        raise ValueError('no load faces were selected')
    areas = []
    for tri in triangles:
        a, b, c = [mesh['nodes'][int(n)] for n in tri[:3]]
        areas.append(np.linalg.norm(np.cross(b - a, c - a)) / 2)
    total = sum(areas)
    loads = {}
    for tri, area in zip(triangles, areas):
        for n in tri[3:]:
            key = int(n)
            loads[key] = loads.get(key, np.zeros(3)) + force * area / (3 * total)
    return loads


def _nodes_of(triangles):
    return sorted({int(n) for tri in triangles for n in tri})


def supports(mesh, params: CaseParams, patch=2.0):
    """The case sits flat on a desk: every node on the bottom face is held in z.

    Rigid-body motion is removed by holding x on a small patch at the (0, 0) corner and
    y on a small patch at the (w, 0) corner. With only vertical loads the sideways
    reactions are almost zero, so these patches do not disturb the stress field.
    Rubber feet are ignored.
    """
    w = params.outer_width
    bottom = [t for t in mesh['triangles'] if _all_at_z(mesh, t, 0.0)]
    if not bottom:
        raise ValueError('no mesh faces on the bottom of the case')
    fixed = {}
    for tri in bottom:
        for n in tri:
            fixed.setdefault(int(n), {3})
    for n in list(fixed):
        x, y, _ = mesh['nodes'][n]
        if x < patch and y < patch:
            fixed[n].add(1)
        if x > w - patch and y < patch:
            fixed[n].add(2)
    fixed = {n: tuple(sorted(dofs)) for n, dofs in fixed.items()}
    return dict(fixed=fixed, support_nodes=sorted(fixed))


def _top_faces(mesh, params):
    return [t for t in mesh['triangles'] if _all_at_z(mesh, t, params.outer_height)]


def screw_down_loads(mesh, params: CaseParams, preload_n):
    """Each post top carries one screw preload, pushing down over its ring-shaped face."""
    if not (math.isfinite(preload_n) and preload_n > 0):
        raise ValueError('screw preload must be positive and finite')
    loads = {}
    top = _top_faces(mesh, params)
    for cx, cy in params.post_centres():
        ring = [t for t in top if params.screw_hole_radius - 0.05
                <= math.hypot(_centroid(mesh, t)[0] - cx, _centroid(mesh, t)[1] - cy)
                <= params.post_radius + 0.05]
        for n, v in traction_loads(mesh, ring, (0, 0, -preload_n)).items():
            loads[n] = loads.get(n, np.zeros(3)) + v
    return loads


def drop_loads(mesh, params: CaseParams, force_n, patch_half_length=3.0):
    """Point-style load on the top of the -y wall, spread over a short patch of its rim."""
    if not (math.isfinite(force_n) and force_n > 0):
        raise ValueError('drop force must be positive and finite')
    wall = params.wall
    mid_x = params.outer_width / 2
    patch = [t for t in _top_faces(mesh, params)
             if 0 < _centroid(mesh, t)[1] < wall and abs(_centroid(mesh, t)[0] - mid_x) <= patch_half_length]
    loads = traction_loads(mesh, patch, (0, 0, -force_n))
    return loads, _nodes_of(patch)


def cantilever_loads(mesh, tip_force_n):
    """Fix the x = 0 end; push down on the x = L end (uniform traction)."""
    if not (math.isfinite(tip_force_n) and tip_force_n > 0):
        raise ValueError('tip force must be positive and finite')
    length, _, _ = mesh['box']
    tip = [t for t in mesh['triangles'] if all(abs(mesh['nodes'][int(n)][0] - length) < 1e-6 for n in t)]
    root = [t for t in mesh['triangles'] if all(abs(mesh['nodes'][int(n)][0]) < 1e-6 for n in t)]
    fixed = {n: (1, 2, 3) for n in _nodes_of(root)}
    return fixed, traction_loads(mesh, tip, (0, 0, -tip_force_n)), _nodes_of(tip)
