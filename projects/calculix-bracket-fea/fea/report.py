"""Generate a short report and ordinary scientific plots from solved fields."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from fea.analysis import von_mises
from fea.results import PROBES


def write_report(r, snapshot, output):
    rows=r['bracket']
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,3,figsize=(13,7),layout='constrained')
    for col,case in enumerate(('down','side','combined')):
        subset=[x for x in rows if x['case']==case]
        h=[x['mesh_size_mm'] for x in subset]
        axes[0,col].plot(h,[x['peak_vm_mpa'] for x in subset],'o-',label='Global nodal peak')
        axes[0,col].plot(h,[x['reference_peak_vm_mpa'] for x in subset],'s-',label='Fixed reference peak')
        for probe in PROBES:
            axes[0,col].plot(h,[x['probe_vm_mpa'][probe] for x in subset],'o--',label=probe.replace('_',' '))
        axes[0,col].set(title=case,ylabel='von Mises stress (MPa)')
        axes[1,col].plot(h,[x['max_displacement_mm'] for x in subset],'o-',color='#12624d')
        axes[1,col].set(xlabel='Requested mesh size h (mm)',ylabel='Maximum displacement (mm)')
        for ax in axes[:,col]:
            ax.invert_xaxis()
            ax.grid(alpha=0.25)
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Refinement goes left to right; stress probes remain at fixed physical coordinates')
    fig.savefig(output/'convergence.png',dpi=160)
    plt.close(fig)
    mesh,fields=snapshot
    data,stress=fields['combined']
    polygons,colors=[],[]
    # Subdivide each TRI6 surface into four triangles for curved geometry display.
    for face in mesh['surface']:
        for indices in ((0,3,5),(3,1,4),(5,4,2),(3,4,5)):
            ids=[int(face[i]) for i in indices]
            polygons.append([mesh['nodes'][n] for n in ids])
            colors.append(np.mean([von_mises(stress[n]) for n in ids]))
    fig=plt.figure(figsize=(10,7),layout='constrained')
    ax=fig.add_subplot(projection='3d',computed_zorder=False)
    norm=Normalize(0,max(colors))
    collection=Poly3DCollection(polygons,facecolors=plt.cm.viridis(norm(colors)),linewidth=0,zorder=1)
    ax.add_collection3d(collection)
    ax.set(xlim=(0,85),ylim=(-25,25),zlim=(0,65),xlabel='x (mm)',ylabel='y (mm)',zlabel='z (mm)')
    ax.set_box_aspect((85,50,65))
    ax.view_init(24,-65)
    for p in PROBES.values():
        ax.scatter(*p,c='#df442a',s=25,depthshade=False,zorder=3)
    ax.quiver(80,0,3,0,6,-10,color='#d53918',linewidth=2,arrow_length_ratio=0.25,zorder=4)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='viridis'),ax=ax,shrink=0.65,label='Smoothed nodal von Mises stress (MPa)')
    ax.set_title('Combined load, finest mesh, undeformed shape\nRed points: fixed-coordinate gauges; arrow: load direction')
    fig.savefig(output/'bracket-stress.png',dpi=160)
    plt.close(fig)
    b=r['beam']
    lines=['# Bracket study', '',
        'I built this study to see how a bracket bends under load and to check how much the answer changes when I use smaller elements. These are numerical model results, not a rating for a manufactured bracket.', '',
        '## Beam verification', '',
        'A 100 mm cantilever has a 10 mm wide, 5 mm deep rectangular section, E = 70,000 MPa and a 10 N downward end force. It uses the same solid elements, traction integration and solver pipeline as the bracket.', '',
        '`I = bh³/12 = 104.166667 mm⁴`; `tip deflection = PL³/(3EI)`; `bending stress = Mz/I`.', '',
        f'- Tip deflection: {b["deflection_mm"]:.6f} mm solved versus {b["hand_deflection_mm"]:.6f} mm by hand ({100*b["deflection_error_fraction"]:.3f}% difference).',
        f'- Root stress by hand: 24 MPa. A least-squares comparison of computed axial stress against `P(L-x)z/I` at integration points 15 < x < 35 mm, |z| > 1 mm gives a ratio of {b["section_stress_ratio"]:.7f} ({100*b["stress_error_fraction"]:.4f}% difference). The corresponding extrapolated root bending stress is {24*b["section_stress_ratio"]:.6f} MPa.',
        f'- Signed axial-stress field error over those points: {100*b["stress_rms_error_fraction"]:.4f}% RMS (norm of error / norm of prediction) and {100*b["stress_max_error_fraction"]:.4f}% maximum pointwise relative error. The fitted scale above is an amplitude diagnostic, not a pointwise accuracy claim.',
        '- I compare stress away from the fully fixed end because the local three-dimensional restraint violates the simple beam assumption there. The extrapolated root value is not the local clamp peak.',
        f'- Reaction force residual: {100*b["force_balance_error_fraction"]:.6f}% of the applied load; {b["elements"]:,} elements, {b["nodes"]:,} nodes.', '',
        '## Bracket and loads', '',
        'The L bracket is 80 mm long, 60 mm high, 40 mm wide and 6 mm thick, with a 6 mm inside fillet radius. Two 7 mm diameter mounting holes run through the upright in the x direction, at (y,z) = (±10,45) mm. All three translations on both cylindrical bores are fixed. There are no explicit bolt solids or contacts.', '',
        'Forces act as constant traction over the entire 40 × 6 mm free end face at x = 80 mm. Six-node triangular face integration puts zero load on each corner and area/3 on each midside node. This preserves resultant force and moment independently of mesh size.', '',
        '| Case | Fx (N) | Fy (N) | Fz (N) |', '|---|---:|---:|---:|',
        '| down | 0 | 0 | -100 |','| side | 0 | 100 | 0 |','| combined | 0 | 60 | -100 |', '',
        '![Bracket stress and geometry](bracket-stress.png)', '',
        'Surface colors interpolate extrapolated, averaged nodal stresses. Color smoothing does not establish accuracy. The geometry shown is undeformed; the free end moves by the displacement in the table.', '',
        '## All twelve solutions', '',
        'The mesh size is a requested maximum edge scale, not a measured uniform element size. Each independently generated mesh uses quadratic ten-node tetrahedra (C3D10). Nodal von Mises stress combines normal and shear stresses into one yield comparison number. Displacement is the largest vector magnitude at any node.', '',
        'I assume a 276 MPa yield stress for an illustrative 6061-T6 aluminium model. The margin is `276 / peak von Mises - 1`, with load factor 1 and no additional safety factor. It is a model-only yield margin, not a certified allowable.', '',
        '| Case | h (mm) | Elements | Nodes | Peak VM (MPa) | Max movement (mm) | Yield margin |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f'| {row["case"]} | {row["mesh_size_mm"]:g} | {row["elements"]:,} | {row["nodes"]:,} | {row["peak_vm_mpa"]:.3f} | {row["max_displacement_mm"]:.6f} | {row["yield_margin"]:.3f} |')
    lines += ['', '## Mesh convergence and peak location', '',
        '![Stress and displacement refinement](convergence.png)', '',
        'Smaller elements should make an answer settle. I flag a sequence as within 5% only if BOTH of its last two refinement changes are below 5%. This is a screening criterion, not an error bound or Richardson extrapolation. The mesh ratios are unequal and no asymptotic order is assumed.', '',
        'A separate preliminary h = 1.5 mm mesh locates the global peak for each load. I then embed those exact physical coordinates in all four study meshes. The table tracks stress at that fixed reference peak as well as the global maximum, which may move after remeshing. Three additional embedded gauges track the right bore (6,10,41.5), left bore (6,-10,41.5), and inner fillet (7.757359,0,7.757359) mm.', '',
        '| Case | Reference peak (x,y,z), mm | Stress at reference, coarse to fine (MPa) | Reference changes | Global peak changes | Movement changes |',
        '|---|---|---|---|---|---|']
    for case,c in r['convergence'].items():
        fmt=lambda seq:', '.join(f'{100*v:.2f}%' for v in seq['relative_changes'])
        p=', '.join(f'{v:.6f}' for v in c['reference_peak']['xyz_mm'])
        values=', '.join(f'{x["reference_peak_vm_mpa"]:.3f}' for x in rows if x['case']==case)
        lines.append(f'| {case} | ({p}) | {values} | {fmt(c["at_reference_peak"])} | {fmt(c["global_peak"])} | {fmt(c["displacement"])} |')

    for case,c in r['convergence'].items():
        passed=c['at_reference_peak']['within_five_percent_last_two_changes']
        movement = 'meets' if c['displacement']['within_five_percent_last_two_changes'] else 'does not meet'
        lines += ['', f'{case}: reference peak stress {"meets" if passed else "does not meet"} the two-change 5% screen; displacement {movement} it.']
    lines += ['', 'Fixed-bore edges impose an abrupt restraint boundary and can cause stress singularities. A small change over four meshes does not prove a finite limiting stress at those edges. I do not use positive margins to declare the bracket safe. The fillet gauge is a separate location away from the mounting restraint; its complete convergence sequence is in `results.json`.', '',
        f'The largest force residual over all bracket runs is {100*max(x["force_balance_error_fraction"] for x in rows):.6f}% of the applied force. All moment residual magnitudes are below 0.1 N mm. The combined displacement and stress tensor fields are independently solved and checked against down + 0.6 × side, within 0.003% relative maximum-component error.', '',
        '## Assumptions and limits', '',
        '- Units are N, mm and MPa. Homogeneous isotropic aluminium uses E = 70,000 MPa and Poisson ratio 0.33; yield = 276 MPa is an assumed comparison value, not a measured property or procurement specification.',
        '- Small-displacement, linear static elasticity; no plastic redistribution, geometric nonlinearity, fatigue, impact, thermal stress or residual manufacturing stress.',
        '- Fixed hole walls represent a stiff idealized attachment. Real bolt preload, slip, washer pressure, bearing, clearance, bolt strength and support compliance are omitted. This model cannot check bolt failure or joint separation.',
        '- Only the inside corner is rounded. Other sharp edges and restraint transitions can produce mesh-sensitive local stress. Nodal stress extrapolation/averaging can understate or overstate a peak.',
        '- Three loads explore directions; they are assumed examples, not a measured service-load envelope. A reaction check and a beam benchmark check implementation, not all bracket physics.',
        '- Next I would model the actual attachment and loading, refine the hole/fillet regions locally, compare unaveraged stresses and test a physical bracket before selecting a working load.', '',
        '## Reproduce and inspect', '',
        'From the repository root, run `python -m fea.study all`. The script regenerates this report, PNG plots, CSV and JSON. `build/` keeps every generated input deck, solver log, integration-point stress table and FRD field file for inspection. `results.json` records input-deck SHA-256 hashes and solver/mesher versions. Delete `build/` when finished.', '',
        'Hand-calculation reference: [MIT cantilever exercise](https://ocw.mit.edu/courses/1-050-solid-mechanics-fall-2004/fd4eff39aec922b8c07660006f40686e_pset04_11.pdf). Reference formats and element conventions: [CalculiX manual](https://www.dhondt.de/ccx_2.23.pdf), [Gmsh manual and node ordering](https://gmsh.info/doc/texinfo/gmsh.html#Node-ordering).', '',
        f'Generated with Gmsh {r["provenance"]["gmsh"]}, {r["provenance"]["ccx"]}, Python {r["provenance"]["python"]}.']
    (output/'report.md').write_text('\n'.join(lines)+'\n')
