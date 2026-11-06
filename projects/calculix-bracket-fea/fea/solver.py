"""Write an auditable one-step C3D10 deck and run the native solver."""
import os
from pathlib import Path
import shutil
import subprocess
from fea.model import traction_loads
from fea.analysis import parse_dat


def write_deck(mesh, force, path):
    path = Path(path)
    with path.open('w') as f:
        f.write('*HEADING\nLinear elastic aluminium, N mm MPa\n*NODE,NSET=ALL\n')
        for n,xyz in mesh['nodes'].items():
            f.write(f'{n},'+','.join(f'{v:.12g}' for v in xyz)+'\n')
        f.write('*ELEMENT,TYPE=C3D10,ELSET=SOLID\n')
        for eid,conn in zip(mesh['element_ids'],mesh['elements']):
            f.write(f'{eid},'+','.join(str(int(n)) for n in conn)+'\n')
        f.write('*NSET,NSET=FIXED\n')
        fixed = mesh['fixed']
        for i in range(0,len(fixed),16):
            f.write(','.join(map(str,fixed[i:i+16]))+'\n')
        f.write('*MATERIAL,NAME=ALUMINIUM\n*ELASTIC\n70000.,0.33\n')
        f.write('*SOLID SECTION,ELSET=SOLID,MATERIAL=ALUMINIUM\n')
        f.write('*BOUNDARY\nFIXED,1,3,0\n*STEP\n*STATIC\n*CLOAD\n')
        for n,load in traction_loads(mesh,force).items():
            for d,v in enumerate(load,1):
                if v != 0:
                    f.write(f'{n},{d},{v:.12g}\n')
        f.write('*NODE PRINT,NSET=ALL\nU\n*NODE PRINT,NSET=FIXED\nRF\n')
        f.write('*EL PRINT,ELSET=SOLID\nS\n*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n')
    return path


def solver_executable():
    override = os.environ.get('CCX')
    executable = shutil.which(override) if override else (shutil.which('ccx') or shutil.which('ccx_2.23'))
    if executable is None:
        raise RuntimeError('CCX executable not found; install CalculiX or set CCX, see README')
    return executable


def run_solver(mesh, force, directory, name='case'):
    executable = solver_executable()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    write_deck(mesh,force,directory/f'{name}.inp')
    # This synchronous child is always reaped. Timeout kills and waits for it.
    env = dict(os.environ, OMP_NUM_THREADS='1', CCX_NPROC_RESULTS='1', NUMBER_OF_CPUS='1')
    log = directory/f'{name}.log'
    with log.open('w') as output:
        completed = subprocess.run([executable,'-i',name],cwd=directory,env=env,
                                   stdout=output,stderr=subprocess.STDOUT,timeout=600)
    log_text = log.read_text()
    if completed.returncode or '*ERROR' in log_text or 'Job finished' not in log_text:
        raise RuntimeError(f'CalculiX failed: inspect {log}')
    data = parse_dat(directory/f'{name}.dat')
    if set(data['displacements']) != set(mesh['nodes']):
        raise ValueError('incomplete displacement output')
    expected = {(int(e),ip) for e in mesh['element_ids'] for ip in range(1,5)}
    if set(data['stresses']) != expected or set(data['forces']) != set(mesh['fixed']):
        raise ValueError('incomplete stress or support-reaction output')
    return data
