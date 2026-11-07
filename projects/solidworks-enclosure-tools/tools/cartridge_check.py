"""Conservative shell and tool-envelope screens for a side design exercise."""
import argparse,json,math,pathlib


def check(p):
    erosion=2*p['height_mm']*math.tan(math.radians(abs(p['draft_deg'])))
    wall=min(p['floor_mm'],p['lid_mm'],p['wall_mm']-erosion)
    access=math.hypot(p['screw_x_mm']-p['port_x_mm'],p['screw_y_mm'])-p['port_flange_mm']/2-p['driver_diameter_mm']/2
    flags=[]
    if wall<p['minimum_wall_mm']:flags.append('wall')
    if p['draft_deg']<p['minimum_draft_deg']:flags.append('draft')
    if access<p['access_margin_mm'] or p['release_slot_width_mm']<p['release_blade_width_mm'] or p['release_slot_thickness_mm']<p['release_blade_thickness_mm']:flags.append('assembly_access')
    return dict(wall_mm=p['wall_mm'],conservative_shell_wall_mm=wall,draft_deg=p['draft_deg'],driver_to_port_margin_mm=access,
                release_slot_mm=[p['release_slot_width_mm'],p['release_slot_thickness_mm']],flags=flags,passes=not flags,
                note='Draft erosion assumes both shell contours reduce wall thickness over full height. Tool check is an axial cylinder versus port flange and a rectangular release blade. Snap beams, holes and intentional mating surfaces are excluded from the shell draft rule. No pressure, leak, fatigue or mold-release validation.')


def measure_shell(path,p):
    import numpy as np
    from printcheck import load_mesh,ray_hits
    t=load_mesh(path);cross=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0])
    area=np.linalg.norm(cross,axis=1)/2;normals=cross/(2*area[:,None])
    # Main shell pull faces only: large side triangles spanning half the wall height.
    mask=(area>150)&(np.abs(normals[:,2])<.3)&(np.ptp(t[:,:,2],axis=1)>p['height_mm']/2)
    if not np.any(mask):raise ValueError('No main shell faces found')
    angles=np.rad2deg(np.arcsin(np.abs(normals[mask,2])))
    walls=np.array([ray_hits(c,-n,t).min() for c,n in zip(t[mask].mean(axis=1),normals[mask])])
    finite=walls[np.isfinite(walls)]
    if not len(finite):raise ValueError('No wall ray intersections')
    return dict(shell_face_samples=int(mask.sum()),minimum_draft_deg=float(angles.min()),maximum_draft_deg=float(angles.max()),
                minimum_wall_sample_mm=float(finite.min()),
                passes=bool(angles.min()>=p['minimum_draft_deg']-1e-4 and finite.min()>=p['minimum_wall_mm']),
                note='Samples main planar shell triangles. Bosses, catches, holes and mating faces excluded. Does not prove mold release.')


def sweep(p):return [check(dict(p,wall_mm=w)) for w in p['wall_sweep_mm']]


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('spec');p.add_argument('output');a=p.parse_args();spec=json.loads(pathlib.Path(a.spec).read_text());out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=True)
    (out/'dfm-dfa.json').write_text(json.dumps(dict(nominal=check(spec),wall_sweep=sweep(spec)),indent=2)+'\n')
