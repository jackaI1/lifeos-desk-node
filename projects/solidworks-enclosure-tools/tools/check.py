"""Read real exported STL geometry and calculate explicitly assumed engineering cases."""
import collections, hashlib, json, math, pathlib, re, struct
ROOT = pathlib.Path(__file__).resolve().parents[1]
CAD = ROOT / 'cad' / 'A'
def mesh(path):
    data = path.read_bytes()
    count = struct.unpack_from('<I', data, 80)[0]
    assert len(data) == 84 + 50 * count, path
    faces, edges, vertices = [], collections.Counter(), []
    volume = 0
    center = [0.,0.,0.]
    for i in range(count):
        values = struct.unpack_from('<12fH', data, 84 + 50*i)
        points = [tuple(round(x, 5) for x in values[j:j+3]) for j in (3,6,9)]
        vertices += points
        a,b,c = points
        cross = (b[1]*c[2]-b[2]*c[1], b[2]*c[0]-b[0]*c[2], b[0]*c[1]-b[1]*c[0])
        dv = sum(a[j]*cross[j] for j in range(3))/6
        volume += dv
        for j in range(3): center[j] += dv*(a[j]+b[j]+c[j])/4
        for j in range(3): edges[tuple(sorted((points[j],points[(j+1)%3])))] += 1
        faces.append(values[:3])
    bounds = [[min(p[j] for p in vertices) for j in range(3)], [max(p[j] for p in vertices) for j in range(3)]]
    # SolidWorks exported these files in mm, confirmed against native bounding boxes.
    inverted = 'lid' in path.name
    overhangs = sum(1 for n in faces if n[2] * (-1 if inverted else 1) < -math.cos(math.pi/4))
    return dict(triangles=count, bounds_mm=bounds, volume_mm3=abs(volume), centroid_mm=[v/volume for v in center],
                closed_edges=all(v==2 for v in edges.values()),
                downward_triangles_including_bed_faces=overhangs,
                print_orientation='top face on bed' if inverted else 'minimum Z on bed')
meshes = {p.name:mesh(p) for p in CAD.glob('*.STL')}
assert len(meshes)==7
assert all(m['closed_edges'] for m in meshes.values())
assert meshes['ED-001_case_A.STL']['bounds_mm'][1] == [80.,60.,36.]
assert abs(meshes['ED-002_lid_A.STL']['bounds_mm'][1][2]-20.4)<.001
native_text = '\n'.join(p.read_text() for p in [CAD/'build-results.txt', CAD/'moving-feature.txt', CAD/'carrier-update.txt', CAD/'mount-update.txt'] if p.exists())
# Later exports supersede earlier ones after the drive features are added.
latest = dict(re.findall(r'PART (\S+) bodies=1 volume_mm3=([\d.]+)',native_text))
for name, vol in latest.items():
    assert math.isclose(meshes[name+'.STL']['volume_mm3'], float(vol), rel_tol=.01), name
# Conservative uniform PETG assumption, not measured properties of a printed coupon.
E, b, t, L, delta = 2000, 8, 1.2, 16.25, .5
I = b*t**3/12
F = 3*E*I*delta/L**3
stress = 6*F*L/(b*t*t)
hatch_mass = meshes['ED-003_hatch_A.STL']['volume_mm3']*1.27e-6
# SolidWorks STL exporter translates each part's bounding minimum to zero.
# Recover hatch model Y using the native bounding minimum, -11.7 mm.
lever = abs(.0205-(meshes['ED-003_hatch_A.STL']['centroid_mm'][1]-11.7)/1000)
gravity_torque = hatch_mass*9.80665*lever
friction_allowance = .005
required = 3*(gravity_torque+friction_allowance)
stall = 1.8*9.80665*.01
result = dict(meshes=meshes, snap=dict(E_MPa=E, width_mm=b, thickness_mm=t,
    effective_length_to_hook_mm=L, interference_mm=delta, force_N=F,
    root_stress_MPa=stress, root_strain=stress/E, assumed_allowable_MPa=15,
    worst_interference_mm=.9, worst_root_stress_MPa=stress*.9/delta,
    passes=stress<=15, note='Load at hook center, 16.25 mm below root. Linear beam approximation, no notch or print anisotropy model.'),
    tolerance=dict(aperture_mm=40, hatch_mm=39.4, each_size_tolerance_mm=.2,
    nominal_total_gap_mm=.6, worst_min_total_gap_mm=39.8-39.6,
    worst_max_total_gap_mm=40.2-39.2,
    note='Total gap, not minimum local gap. Eccentricity can close one side.'),
    actuator=dict(part='TowerPro SG90 Digital', source='https://towerpro.com.tw/product/sg90-7/',
    hatch_mass_kg=hatch_mass, density_kg_m3=1270, axis_to_centroid_m=lever,
    gravity_torque_Nm=gravity_torque, assumed_friction_Nm=friction_allowance,
    design_factor=3, required_Nm=required, stall_Nm=stall,
    assumed_continuous_fraction_of_stall=.25, available_screening_Nm=.25*stall,
    passes_screening=.25*stall>required,
    note='Worst gravity orientation plus assumed friction. Horizontal rotation has zero gravity torque about Z. Stall torque is not a continuous rating. Output shape is a reference. Vendor horn fit and motion are not bench tested.'),
    print_review=dict(wall_mm=2.4, snap_beam_mm=1.2, nozzle_assumed_mm=.4,
    wall_lines=6, beam_lines=3, nozzle_validation='NOT PRINTED',
    support_notes='Case ledges and square snap hooks need local support or a chamfer revision. Mesh orientation flags include bed faces. No slicer run.',
    release='PROTOTYPE: beam calculation passes assumed limit; requires support planning, slicer and physical testing'))
(CAD/'engineering-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='meshes'},indent=2))
