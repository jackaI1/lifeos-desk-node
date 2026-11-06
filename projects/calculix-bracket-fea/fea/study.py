"""Reproducible study entry points (N, mm, MPa throughout)."""
from pathlib import Path
import numpy as np
from fea.model import mesh_model
from fea.solver import run_solver
from fea.analysis import cantilever


def solve_beam(directory):
    mesh = mesh_model('beam',2.5)
    data = run_solver(mesh,(0,0,-10),directory,'beam')
    end = [n for n,p in mesh['nodes'].items() if abs(p[0]-100)<1e-6]
    delta = -float(np.mean([data['displacements'][n][2] for n in end]))
    # Compare stress away from the clamp: fit sigma_xx vs z over x=15..35.
    # Linear beam theory predicts gradient -P(L-x)/I. Use actual Gauss points.
    a,b = 0.5854101966249685,0.1381966011250105
    barycentric = np.full((4,4),b)
    np.fill_diagonal(barycentric,a)
    observed, predicted = [],[]
    inertia = 10*5**3/12
    for eid,conn in zip(mesh['element_ids'],mesh['elements']):
        coords = np.array([mesh['nodes'][int(n)] for n in conn[:4]])
        for ip,p in enumerate(barycentric@coords,1):
            if 15 < p[0] < 35 and abs(p[2]) > 1:
                observed.append(data['stresses'][(int(eid),ip)][0])
                predicted.append(10*(100-p[0])*p[2]/inertia)
    observed, predicted = np.asarray(observed),np.asarray(predicted)
    rms_error = float(np.linalg.norm(observed-predicted)/np.linalg.norm(predicted))
    max_error = float(np.max(np.abs((observed-predicted)/predicted)))
    stress_ratio = float(np.dot(observed,predicted)/np.dot(predicted,predicted))
    theory_delta, theory_root_stress = cantilever(100,10,5,10,70000)
    reaction = np.sum(list(data['forces'].values()),axis=0)
    return dict(deflection_mm=delta,hand_deflection_mm=theory_delta,
                deflection_error_fraction=abs(delta/theory_delta-1),
                stress_rms_error_fraction=rms_error,stress_max_error_fraction=max_error,
                hand_root_bending_stress_mpa=theory_root_stress,
                section_stress_ratio=stress_ratio,stress_error_fraction=abs(stress_ratio-1),
                force_balance_error_fraction=float(np.linalg.norm(reaction+(0,0,-10))/10),
                nodes=len(mesh['nodes']),elements=len(mesh['elements']))


def run_study(work, output):
    import hashlib
    import json
    import platform
    import gmsh
    from fea.analysis import parse_frd
    from fea.results import summarize, assess_convergence, peak_node
    from fea.report import write_report
    work, output = Path(work),Path(output)
    output.mkdir(parents=True,exist_ok=True)
    beam = solve_beam(work/'beam')
    if (beam['deflection_error_fraction']>0.03 or beam['stress_rms_error_fraction']>0.01 or beam['stress_max_error_fraction']>0.05
            or beam['force_balance_error_fraction']>1e-5):
        raise ValueError('beam verification failed')
    cases = {'down':(0,0,-100),'side':(0,100,0),'combined':(0,60,-100)}
    # A separate fine-mesh discovery run defines peak coordinates before refinement.
    # Re-embed those physical points, rather than sampling nearby nodes on each mesh.
    reference_peaks = {}
    discovery_mesh = mesh_model('bracket',1.5)
    for name,force in cases.items():
        directory = work/'discovery'/name
        run_solver(discovery_mesh,force,directory)
        stress = parse_frd(directory/'case.frd')
        from fea.analysis import von_mises
        peak = peak_node(stress,discovery_mesh['nodes'])
        reference_peaks[name] = {'xyz_mm':list(map(float,discovery_mesh['nodes'][peak])),
                                 'discovery_vm_mpa':von_mises(stress[peak]),
                                 'input_sha256':hashlib.sha256((directory/'case.inp').read_bytes()).hexdigest()}
        print(f'Discovery {name}: peak at {reference_peaks[name]["xyz_mm"]}',flush=True)
    del discovery_mesh, stress
    rows = []
    snapshot = None
    for size in (4.,3.,2.,1.5):
        mesh = mesh_model('bracket',size,extra_probes=[p['xyz_mm'] for p in reference_peaks.values()])
        fields = {}
        for name,force in cases.items():
            directory = work/f'h{size:g}'/name
            data = run_solver(mesh,force,directory)
            stress = parse_frd(directory/'case.frd')
            row = summarize(mesh,data,stress,force)
            target = reference_peaks[name]['xyz_mm']
            gauge = min(mesh['nodes'],key=lambda n:np.linalg.norm(mesh['nodes'][n]-target))
            if np.linalg.norm(mesh['nodes'][gauge]-target)>1e-7:
                raise ValueError('reference peak location is missing')
            row['reference_peak_vm_mpa'] = von_mises(stress[gauge])
            row.update(case=name,mesh_size_mm=size,force_n=force,
                       input_sha256=hashlib.sha256((directory/'case.inp').read_bytes()).hexdigest())
            if row['force_balance_error_fraction']>1e-5 or np.linalg.norm(row['moment_residual_nmm'])>0.1:
                raise ValueError('bracket equilibrium check failed')
            rows.append(row)
            fields[name] = (data,stress)
            print(f'{name:8s} h={size:g}: {row["elements"]} elements, '
                  f'{row["peak_vm_mpa"]:.3f} MPa, {row["max_displacement_mm"]:.5f} mm',flush=True)
        # Compare whole vector/tensor fields, not VM (which is nonlinear).
        for field,index in (('displacements',0),('stress',1)):
            values = []
            for name in cases:
                d,s=fields[name]
                source = d[field] if index==0 else s
                values.append(np.array([source[n] for n in sorted(mesh['nodes'])]))
            down,side,combined = values
            error = float(np.max(np.abs(combined-down-0.6*side))/np.max(np.abs(combined)))
            if error>3e-5:
                raise ValueError(f'linear superposition check failed: {field}, {error}')
            rows[-1][f'{field}_superposition_error_fraction'] = error
        snapshot = (mesh,fields)
    peak_convergence = {}
    from fea.results import PROBES
    for case in cases:
        subset = [r for r in rows if r['case']==case]
        peak_convergence[case] = {
            'reference_peak':reference_peaks[case],
            'at_reference_peak':assess_convergence([r['reference_peak_vm_mpa'] for r in subset]),
            'global_peak':assess_convergence([r['peak_vm_mpa'] for r in subset]),
            'fixed_gauges':{p:assess_convergence([r['probe_vm_mpa'][p] for r in subset]) for p in PROBES},
            'displacement':assess_convergence([r['max_displacement_mm'] for r in subset])}
    version = (work/'beam'/'beam.log').read_text().splitlines()
    result = dict(units={'length':'mm','force':'N','stress':'MPa'},
                  material={'young_mpa':70000,'poisson':0.33,'assumed_yield_mpa':276},
                  provenance={'gmsh':gmsh.__version__,'python':platform.python_version(),
                              'platform':platform.platform(),'ccx':next(x.strip() for x in version if 'Version' in x)},
                  beam=beam,bracket=rows,convergence=peak_convergence)
    (output/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    import csv
    with (output/'results.csv').open('w') as f:
        keys=['case','mesh_size_mm','nodes','elements','peak_vm_mpa','reference_peak_vm_mpa','max_displacement_mm','yield_margin','force_balance_error_fraction']
        writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore',lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    write_report(result,snapshot,output)
    return result


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case',choices=['beam','all'])
    parser.add_argument('--work',type=Path,default=Path('build'))
    parser.add_argument('--output',type=Path,default=Path('docs/study'))
    args=parser.parse_args()
    if args.case=='beam':
        print(json.dumps(solve_beam(args.work/'beam'),indent=2))
    else:
        run_study(args.work,args.output)


if __name__=='__main__':
    main()
