"""Native Gmsh OCC solids and consistent quadratic triangular face loading."""
import gmsh
import numpy as np


def mesh_model(kind, size, extra_probes=()):
    if kind not in ('beam', 'bracket') or not np.isfinite(size) or size <= 0:
        raise ValueError('expected beam/bracket and positive finite mesh size')
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.option.setNumber('General.NumThreads', 1)
        gmsh.model.add(kind)
        occ = gmsh.model.occ
        if kind == 'beam':
            occ.addBox(0, -5, -2.5, 100, 10, 5)
        else:
            # x-z L profile, 6 mm thick with a 6 mm inside radius; 40 mm wide.
            coords = [(0,0),(80,0),(80,6),(12,6),(6,12),(6,60),(0,60)]
            p = [occ.addPoint(x,-20,z) for x,z in coords]
            center = occ.addPoint(12,-20,12)
            edges = [occ.addLine(p[i], p[i+1]) for i in range(3)]
            edges += [occ.addCircleArc(p[3], center, p[4])]
            edges += [occ.addLine(p[i],p[(i+1)%7]) for i in range(4,7)]
            face = occ.addPlaneSurface([occ.addWire(edges)])
            extruded = occ.extrude([(2,face)], 0,40,0)
            volumes = [e for e in extruded if e[0] == 3]
            holes = [(3,occ.addCylinder(-1,y,45,8,0,0,3.5)) for y in (-10,10)]
            solid, _ = occ.cut(volumes, holes)
            # Embedded physical gauges survive every refinement unchanged.
            gauges = [(6,10,41.5),(6,-10,41.5),(12-6/np.sqrt(2),0,12-6/np.sqrt(2))]
            # Deduplicate points already coincident with a standard gauge.
            for p in extra_probes:
                if not any(np.linalg.norm(np.array(p)-q)<1e-7 for q in gauges):
                    gauges.append(p)
            occ.fragment(solid, [(0,occ.addPoint(*p)) for p in gauges])
        occ.synchronize()
        surfaces = gmsh.model.getEntities(2)
        load_faces = [tag for _,tag in surfaces
                      if abs(occ.getCenterOfMass(2,tag)[0] - (100 if kind=='beam' else 80)) < 1e-6]
        if kind == 'beam':
            fixed_faces = [tag for _,tag in surfaces if abs(occ.getCenterOfMass(2,tag)[0]) < 1e-6]
        else:
            fixed_faces = [tag for _,tag in surfaces if gmsh.model.getType(2,tag) == 'Cylinder'
                           and abs(occ.getCenterOfMass(2,tag)[2]-45) < 1e-6]
        if len(load_faces) != 1 or len(fixed_faces) != (1 if kind=='beam' else 2):
            raise ValueError('geometry surface selection failed')
        gmsh.option.setNumber('Mesh.MeshSizeMin', size)
        gmsh.option.setNumber('Mesh.MeshSizeMax', size)
        gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 0)
        gmsh.option.setNumber('Mesh.ElementOrder', 2)
        gmsh.model.mesh.generate(3)
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        nodes = {int(n): v for n,v in zip(tags, np.asarray(xyz).reshape(-1,3))}
        types, element_tags, connectivities = gmsh.model.mesh.getElements(3)
        if list(types) != [11]:
            raise ValueError('only ten-node tetrahedra are supported')
        # Gmsh's last two edge nodes have the opposite order to CalculiX C3D10.
        elements = np.asarray(connectivities[0], dtype=int).reshape(-1,10)[:,[0,1,2,3,4,5,6,7,9,8]]
        used = set(elements.ravel())
        nodes = {n:p for n,p in nodes.items() if n in used}
        fixed = sorted({int(n) for f in fixed_faces for n in gmsh.model.mesh.getNodes(2,f,True)[0]})
        types, _, conn = gmsh.model.mesh.getElements(2,load_faces[0])
        if list(types) != [9]:
            raise ValueError('expected six-node load triangles')
        loaded = np.asarray(conn[0], dtype=int).reshape(-1,6)
        _, _, surface_conn = gmsh.model.mesh.getElements(2)
        surface = np.asarray(surface_conn[0],dtype=int).reshape(-1,6)
        return dict(surface=surface,nodes=nodes, elements=elements, element_ids=np.asarray(element_tags[0],dtype=int),
                    fixed=fixed, loaded=loaded, kind=kind, size=size)
    finally:
        gmsh.finalize()


def traction_loads(mesh, force):
    """Integrate constant traction: TRI6 corners carry 0, midsides A/3."""
    force = np.asarray(force, dtype=float)
    if force.shape != (3,) or not np.all(np.isfinite(force)):
        raise ValueError('force must contain three finite components')
    areas = []
    for triangle in mesh['loaded']:
        a,b,c = [mesh['nodes'][int(n)] for n in triangle[:3]]
        areas.append(np.linalg.norm(np.cross(b-a,c-a))/2)
    area = sum(areas)
    if area <= 0:
        raise ValueError('empty load surface')
    loads = {}
    for triangle, a in zip(mesh['loaded'],areas):
        for node in triangle[3:]:
            n = int(node)
            loads[n] = loads.get(n,np.zeros(3)) + force*a/(3*area)
    return loads
