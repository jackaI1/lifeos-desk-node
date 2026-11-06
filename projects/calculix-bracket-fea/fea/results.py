"""Physical summaries; distinguish sampled convergence from design validation."""
import numpy as np
from fea.analysis import von_mises

PROBES = {'right_bore':(6,10,41.5), 'left_bore':(6,-10,41.5),
          'fillet':(12-6/np.sqrt(2),0,12-6/np.sqrt(2))}


def peak_node(stress, expected_nodes):
    if not stress or set(stress) != set(expected_nodes):
        raise ValueError('incomplete or unexpected nodal stress field')
    return max(stress,key=lambda n:von_mises(stress[n]))


def summarize(mesh, data, stress, force, yield_mpa=276):
    peak = peak_node(stress, mesh['nodes'])
    vm = {n:von_mises(s) for n,s in stress.items()}
    reaction = np.sum(list(data['forces'].values()),axis=0)
    residual = reaction+force
    moments = sum(np.cross(mesh['nodes'][n],f) for n,f in data['forces'].items())
    centroid = (100,0,0) if mesh.get('kind')=='beam' else (80,0,3)
    moment_residual = moments+np.cross(centroid,force)
    probes = {}
    for name,p in PROBES.items():
        n = min(mesh['nodes'],key=lambda n:np.linalg.norm(np.array(mesh['nodes'][n])-p))
        distance = float(np.linalg.norm(np.array(mesh['nodes'][n])-p))
        if mesh.get('kind') == 'bracket' and distance > 1e-7:
            raise ValueError('physical stress gauge is missing')
        if distance < 1e-7:
            probes[name] = vm[n]
    return dict(nodes=len(mesh['nodes']),elements=len(mesh['elements']),
                peak_vm_mpa=vm[peak],peak_node=int(peak),peak_xyz_mm=list(map(float,mesh['nodes'][peak])),
                max_displacement_mm=max(float(np.linalg.norm(u)) for u in data['displacements'].values()),
                yield_margin=yield_mpa/vm[peak]-1,
                reaction_n=reaction.tolist(),force_balance_error_fraction=float(np.linalg.norm(residual)/np.linalg.norm(force)),
                moment_residual_nmm=moment_residual.tolist(),probe_vm_mpa=probes)


def assess_convergence(values):
    if len(values) < 3 or not all(np.isfinite(v) and v>0 for v in values):
        raise ValueError('need at least three positive finite results')
    changes = [abs(b-a)/abs(b) for a,b in zip(values,values[1:])]
    return dict(relative_changes=changes,
                within_five_percent_last_two_changes=bool(max(changes[-2:])<0.05))
