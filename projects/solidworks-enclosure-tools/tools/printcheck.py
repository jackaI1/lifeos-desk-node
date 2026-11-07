"""Mesh screening in mm. Estimates are not slicer output or print validation."""
import argparse
import html
import json
import pathlib
import struct
import numpy as np


def load_mesh(path):
    data = pathlib.Path(path).read_bytes()
    if len(data) < 84:
        raise ValueError('Expected binary STL')
    count = struct.unpack_from('<I', data, 80)[0]
    if len(data) != 84 + 50 * count:
        raise ValueError('Expected binary STL with exact triangle count')
    return np.array([struct.unpack_from('<12fH', data, 84+50*i)[3:12]
                     for i in range(count)], dtype=float).reshape(-1,3,3)


def ray_hits(origin, direction, triangles):
    """Moller-Trumbore positive ray intersections, two-sided, in mm."""
    e1=triangles[:,1]-triangles[:,0]; e2=triangles[:,2]-triangles[:,0]
    p=np.cross(np.broadcast_to(direction,e2.shape),e2)
    det=np.einsum('ij,ij->i',e1,p)
    valid=np.abs(det)>1e-10
    inv=np.divide(1.,det,out=np.zeros_like(det),where=valid)
    s=origin-triangles[:,0]
    u=np.einsum('ij,ij->i',s,p)*inv
    q=np.cross(s,e1)
    v=q@direction*inv
    t=np.einsum('ij,ij->i',e2,q)*inv
    return np.where(valid & (u>=-1e-7) & (v>=-1e-7) & (u+v<=1+1e-7) & (t>1e-5), t, np.inf)


def analyze(triangles, profile, name):
    t=np.array(triangles,dtype=float,copy=True)
    t-=t.min(axis=(0,1))
    cross=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]); length=np.linalg.norm(cross,axis=1)
    if np.any(length<1e-10):
        raise ValueError('Degenerate mesh face')
    normals=cross/length[:,None]; centers=t.mean(axis=1)
    walls=np.array([ray_hits(c,-n,t).min() for c,n in zip(centers,normals)])
    thin=np.flatnonzero(walls<profile['min_wall_mm']-1e-5)
    bed=t[:,:,2].max(axis=1)<1e-4
    over=np.flatnonzero((normals[:,2]<-np.cos(np.deg2rad(profile['overhang_deg']))) & ~bed)
    # Connected downward patches provide a conservative unsupported span screen.
    patches=[]; remaining=set(int(i) for i in over)
    vertices=[set(map(tuple,np.round(x,5))) for x in t]
    while remaining:
        group={remaining.pop()}; frontier=list(group)
        while frontier:
            i=frontier.pop()
            adjacent=[j for j in remaining if len(vertices[i]&vertices[j])>=2]
            remaining.difference_update(adjacent);group.update(adjacent);frontier.extend(adjacent)
        pts=t[list(group)].reshape(-1,3)
        patches.append(dict(faces=sorted(group),span_mm=float(np.ptp(pts,axis=0)[:2].max())))
    # Vertical support rays on square cells. Union intervals per cell avoids double counting.
    pitch=profile['grid_mm']; support=0.; columns=0
    if len(over):
        low=t[over].min(axis=(0,1));high=t[over].max(axis=(0,1))
        for x in np.arange(low[0]+pitch/2,high[0],pitch):
            for y in np.arange(low[1]+pitch/2,high[1],pitch):
                origin=np.array([x,y,-1.]); hits=ray_hits(origin,np.array([0.,0.,1.]),t)-1
                intervals=[]
                for i in over:
                    z=hits[i]
                    if not np.isfinite(z): continue
                    below=hits[(hits<z-1e-4)&(normals[:,2]>1e-6)]
                    bottom=max(0.,float(below.max())) if len(below) else 0.
                    if z>bottom+1e-4: intervals.append((bottom,float(z)))
                end=0.;height=0.
                for a,b in sorted(intervals):
                    height+=max(0.,b-max(a,end));end=max(end,b)
                support+=height*pitch*pitch
                columns+=bool(height)
    volume=abs(float(np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6))
    bbox=t.max(axis=(0,1))
    # Full solid part is conservative; supports use specified effective fill fraction.
    deposited=volume+support*profile['support_fraction']
    mass=deposited/1000*profile['density_g_cm3']
    flow=profile['layer_mm']*profile['extrusion_width_mm']*profile['speed_mm_s']
    finite=walls[np.isfinite(walls)]
    return dict(orientation=name, triangles=len(t), bounds_mm=bbox.tolist(),
                fits_printer=bool(np.all(bbox<=profile['build_mm'])),
                minimum_wall_mm=float(finite.min()) if len(finite) else None,
                wall_sample_coverage=float(len(finite)/len(t)),
                thin_faces=thin.tolist(),overhang_faces=over.tolist(),
                overhang_angles_from_vertical_deg={str(i):float(np.rad2deg(np.arcsin(np.clip(-normals[i,2],0,1)))) for i in over},
                overhang_area_mm2=float(length[over].sum()/2),regions=patches,
                max_bridge_mm=max((p['span_mm'] for p in patches),default=0.),
                bridge_flags=[p for p in patches if p['span_mm']>profile['max_bridge_mm']],
                support_volume_mm3=support,support_columns=columns,volume_mm3=volume,
                estimated_material_g=mass,material_cost=mass/1000*profile['cost_per_kg'],
                time_hours=deposited/flow/3600*1.3)


def orientations(mesh):
    yield 'base-down',mesh.copy()
    flipped=mesh.copy(); flipped[:,:,1:]*=-1
    yield 'top-down',flipped


def report(paths,profile,out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    results={}; pictures=[]
    for path in paths:
        mesh=load_mesh(path); rows=[]
        for name,tri in orientations(mesh):
            r=analyze(tri,profile,name);rows.append(r)
            # Orthographic isometric SVG, every triangle colored by its flagged ID.
            tri-=tri.min(axis=(0,1)); projected=np.stack((tri[:,:,0]-.55*tri[:,:,1],-.4*tri[:,:,0]-.4*tri[:,:,1]-tri[:,:,2]),axis=-1)
            lo=projected.min(axis=(0,1)); projected=(projected-lo)*4+10
            size=projected.max(axis=(0,1))+10; polygons=[]
            thin=set(r['thin_faces']);over=set(r['overhang_faces'])
            for i in np.argsort(tri.mean(axis=1)@np.array([1.,1.,1.])):
                color='#d73027' if i in thin else '#fdae61' if i in over else '#a6bddb'
                pts=' '.join(f'{x:.2f},{y:.2f}' for x,y in projected[i])
                polygons.append(f'<polygon points="{pts}" fill="{color}" stroke="#444" stroke-width=".2"><title>Face {i}</title></polygon>')
            svg=f'<svg viewBox="0 0 {size[0]} {size[1]}" width="460" role="img" aria-label="Flagged mesh faces">'+''.join(polygons)+'</svg>'
            pictures.append(f'<h2>{html.escape(pathlib.Path(path).name)}: {name}</h2>'+svg+'<pre>'+html.escape(json.dumps(r,indent=2))+'</pre>')
        results[pathlib.Path(path).name]=dict(recommended=min(rows,key=lambda r:(not r['fits_printer'],r['support_volume_mm3'],len(r['overhang_faces'])))['orientation'],orientations=rows)
    (out/'results.json').write_text(json.dumps(dict(profile=profile,parts=results),indent=2)+'\n')
    (out/'report.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Print screening</title><style>body{font:16px system-ui;max-width:1000px;margin:40px auto}pre{white-space:pre-wrap}svg{max-width:100%}</style><h1>SolidWorks mesh print screening</h1><p>Red: thin-wall samples. Orange: downward faces above bed. Hover for triangle ID. Both flags may apply. SolidWorks Student Edition exports. No physical printing or validation.</p><p>Wall rays sample face centroids, so small local defects can be missed. Bridge length is a downward-patch bounding span, not a verified bridge with anchored ends. Support is a vertical-column estimate sampled on a grid, not slicer output. Cost uses full-solid parts and effective support fill; time adds an assumed 30% travel allowance. Orientation ranking uses fit, support volume, then flagged face count. Use a slicer and print coupons before relying on this.</p>'+''.join(pictures)+'</html>')
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('meshes',nargs='+');p.add_argument('--profile',required=True);p.add_argument('--output',required=True)
    a=p.parse_args(); report(a.meshes,json.loads(pathlib.Path(a.profile).read_text()),a.output)
