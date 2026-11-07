"""Hash the generated prototype deliverables. Default mode checks, --write releases."""
import argparse,csv,hashlib,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
FOLDERS=['print-check','bracket','B','fixture','cartridge','clamp']

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def files(folder):
    return sorted(p for p in folder.rglob('*') if p.is_file() and p.name!='manifest.csv' and not p.name.startswith('~$'))

def run(write=False):
    for name in FOLDERS:
        folder=ROOT/'cad'/name;manifest=folder/'manifest.csv'
        paths=files(folder)
        if not paths:raise ValueError(f'No deliverables in {folder}')
        if any(p.stat().st_size>50_000_000 for p in paths):raise ValueError('Deliverable exceeds 50 MB')
        if write:
            with manifest.open('w',newline='') as f:
                w=csv.writer(f,lineterminator="\n");w.writerow(['path','bytes','sha256','status'])
                for p in paths:w.writerow([p.relative_to(folder).as_posix(),p.stat().st_size,digest(p),'Educational prototype; no physical testing'])
        else:
            rows=list(csv.DictReader(manifest.open()))
            if {r['path'] for r in rows}!={p.relative_to(folder).as_posix() for p in paths}:raise ValueError(f'Unlisted or missing deliverable in {folder}')
            for row in rows:
                p=folder/row['path']
                if p.stat().st_size!=int(row['bytes']) or digest(p)!=row['sha256']:raise ValueError(f'Manifest mismatch: {p}')
        print(f'{name}: {len(paths)} files verified' if not write else f'{name}: manifest written')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--write',action='store_true');run(a.parse_args().write)
