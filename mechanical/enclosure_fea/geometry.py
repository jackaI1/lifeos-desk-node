"""Build the desk-node case as a solid (OpenCASCADE via Gmsh), export STEP, and mesh it.

The mesh uses ten-node tetrahedra (CalculiX C3D10). Gmsh numbers the last two edge
nodes in the opposite order to CalculiX, so they are swapped on output.
"""
import contextlib
import math

import gmsh
import numpy as np

from .board import BOARD_THICKNESS, CaseParams, HEADER_CENTRE_X, HEADER_SLOT_WIDTH
from .board import USB_CENTRE_X, USB_OPENING

GMSH_TO_CCX_C3D10 = [0, 1, 2, 3, 4, 5, 6, 7, 9, 8]


@contextlib.contextmanager
def gmsh_model(name):
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.option.setNumber('General.NumThreads', 1)
        gmsh.model.add(name)
        yield gmsh.model.occ
    finally:
        gmsh.finalize()


def _box(occ, x, y, z, dx, dy, dz):
    return (3, occ.addBox(x, y, z, dx, dy, dz))


def _cylinder(occ, x, y, z, height, radius):
    return (3, occ.addCylinder(x, y, z, 0, 0, height, radius))


def build_case(occ, p: CaseParams):
    """Add the case solid to the open Gmsh model. Returns nothing; call synchronize after."""
    p.validate()
    t = p.wall
    outer = [_box(occ, 0, 0, 0, p.outer_width, p.outer_depth, p.outer_height)]
    cavity = [_box(occ, t, t, t, p.cavity_width, p.cavity_depth, p.cavity_height + 1)]
    body, _ = occ.cut(outer, cavity)

    # Solid corner posts (lid screws) and board standoffs, both rising from the floor.
    additions = [_cylinder(occ, x, y, t, p.cavity_height, p.post_radius) for x, y in p.post_centres()]
    additions += [_cylinder(occ, x, y, t, p.standoff_height, p.standoff_radius)
                  for x, y in p.standoff_centres()]
    body, _ = occ.fuse(body, additions)

    # Blind screw pilots in the posts, and M3 through-holes in the standoffs and floor.
    cuts = [_cylinder(occ, x, y, t + 1.5, p.cavity_height, p.screw_hole_radius) for x, y in p.post_centres()]
    cuts += [_cylinder(occ, x, y, -1, t + p.standoff_height + 2, p.screw_hole_radius)
             for x, y in p.standoff_centres()]

    # Connector openings in the +y wall, where the USB-C and header sit on the board edge.
    top_of_board = t + p.standoff_height + BOARD_THICKNESS
    usb_x0 = t + p.side_clearance + USB_CENTRE_X - USB_OPENING[0] / 2
    cuts.append(_box(occ, usb_x0, t + p.cavity_depth - 1, top_of_board,
                     USB_OPENING[0], p.usb_clearance + t + 2, USB_OPENING[1]))
    header_x0 = t + p.side_clearance + HEADER_CENTRE_X - HEADER_SLOT_WIDTH / 2
    cuts.append(_box(occ, header_x0, t + p.cavity_depth - 1, top_of_board,
                     HEADER_SLOT_WIDTH, p.usb_clearance + t + 2, p.outer_height + 1 - top_of_board))
    body, _ = occ.cut(body, cuts)
    occ.synchronize()
    return body


def export_step(p: CaseParams, path):
    with gmsh_model('desk_node_case') as occ:
        build_case(occ, p)
        gmsh.write(str(path))
    return path


def _mesh_size(lc):
    if not (isinstance(lc, (int, float)) and math.isfinite(lc) and lc > 0):
        raise ValueError('mesh size must be a positive finite number')
    gmsh.option.setNumber('Mesh.MeshSizeMin', lc)
    gmsh.option.setNumber('Mesh.MeshSizeMax', lc)
    gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 0)
    gmsh.option.setNumber('Mesh.ElementOrder', 2)


def _extract(lc):
    """Read the generated mesh: nodes, C3D10 tetrahedra and TRI6 boundary triangles."""
    gmsh.model.mesh.generate(3)
    tags, xyz, _ = gmsh.model.mesh.getNodes()
    coords = {int(n): np.asarray(v, dtype=float) for n, v in zip(tags, np.asarray(xyz).reshape(-1, 3))}
    types, element_tags, connectivities = gmsh.model.mesh.getElements(3)
    if list(types) != [11]:
        raise ValueError('only ten-node tetrahedra are supported')
    elements = np.asarray(connectivities[0], dtype=int).reshape(-1, 10)[:, GMSH_TO_CCX_C3D10]
    element_ids = np.asarray(element_tags[0], dtype=int)
    # Boundary faces: quadratic triangles (gmsh type 9) on every surface.
    surface_types, _, surface_conn = gmsh.model.mesh.getElements(2)
    triangles = np.zeros((0, 6), dtype=int)
    for kind, conn in zip(surface_types, surface_conn):
        if kind != 9:
            raise ValueError('expected six-node boundary triangles')
        triangles = np.vstack([triangles, np.asarray(conn, dtype=int).reshape(-1, 6)])
    used = set(elements.ravel().tolist())
    coords = {n: c for n, c in coords.items() if n in used}
    mesh = dict(nodes=coords, elements=elements, element_ids=element_ids, triangles=triangles,
                lc=lc, kind='case')
    check_orientation(mesh)
    return mesh


def check_orientation(mesh):
    """Every tetrahedron must be positively oriented, or CalculiX reports bad elements."""
    corner = np.array([mesh['nodes'][int(n)] for n in mesh['elements'][:, :4].ravel()]).reshape(-1, 4, 3)
    a, b, c, d = corner[:, 0], corner[:, 1], corner[:, 2], corner[:, 3]
    volume = np.einsum('ij,ij->i', np.cross(b - a, c - a), d - a) / 6.0
    if np.any(np.abs(volume) < 1e-9):
        raise ValueError('degenerate tetrahedron in mesh')
    if np.any(volume <= 0):
        raise ValueError('inverted or mixed-sign tetrahedra in mesh')
    mesh['min_volume_mm3'] = float(volume.min())
    mesh['total_volume_mm3'] = float(volume.sum())


def mesh_case(p: CaseParams, lc=1.0):
    with gmsh_model('desk_node_case') as occ:
        build_case(occ, p)
        _mesh_size(lc)
        mesh = _extract(lc)
    mesh['params'] = p
    return mesh


def mesh_box(length, width, height, lc):
    """Rectangular bar for the cantilever benchmark; x runs along the length."""
    with gmsh_model('cantilever_bar') as occ:
        occ.addBox(0, 0, 0, length, width, height)
        occ.synchronize()
        _mesh_size(lc)
        mesh = _extract(lc)
    mesh['kind'] = 'box'
    mesh['box'] = (length, width, height)
    return mesh
