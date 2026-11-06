"""Export the actual fitted KiCad BOM and build the manufacturing review package."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from .core import parse_bom, prepare, validate_placements
from .reports import write_reports

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent


def export(output, boards=1, bom=None, placements=None):
    if boards < 1:
        raise ValueError('Build quantity must be a positive integer')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    exported = output / 'bom-kicad.csv'
    if bom:
        exported.write_bytes(Path(bom).read_bytes())
    else:
        subprocess.run(['kicad-cli','sch','export','bom','-o',str(exported),
                        '--fields','Reference,Value,Footprint,LCSC,MPN,${QUANTITY}',
                        '--labels','Designator,Value,Footprint,LCSC,MPN,Qty',
                        '--group-by','MPN,Footprint','--ref-range-delimiter','','--exclude-dnp',
                        str(ROOT/'hardware/desk-node.kicad_sch')], check=True)
    digest = hashlib.sha256(exported.read_bytes()).hexdigest()
    with exported.open() as stream:
        rows = parse_bom(stream)
    catalog = json.loads((DATA/'catalog.json').read_text())
    templates = json.loads((DATA/'templates.json').read_text())
    parts = prepare(rows, catalog, templates)
    (output/'parts.json').write_text(json.dumps(parts, indent=2) + '\n')
    report = write_reports(parts, templates, output, boards, digest)
    # Assembly review package includes actual board placements, not generated mock coordinates.
    if placements:
        (output/'placements.csv').write_bytes(Path(placements).read_bytes())
    else:
        subprocess.run(['kicad-cli','pcb','export','pos','-o',str(output/'placements.csv'),
                    '--format','csv','--units','mm','--side','both','--exclude-dnp',
                    str(ROOT/'hardware/desk-node.kicad_pcb')], check=True)
    with (output/'placements.csv').open() as stream:
        validate_placements(stream, parts)
    (output/'manifest.json').write_text(json.dumps({
        'bom_sha256':digest,
        'placements_sha256':hashlib.sha256((output/'placements.csv').read_bytes()).hexdigest(),
        'schematic_sha256':hashlib.sha256((ROOT/'hardware/desk-node.kicad_sch').read_bytes()).hexdigest(),
        'board_sha256':hashlib.sha256((ROOT/'hardware/desk-node.kicad_pcb').read_bytes()).hexdigest(),
        'catalog_sha256':hashlib.sha256((DATA/'catalog.json').read_bytes()).hexdigest(),
        'templates_sha256':hashlib.sha256((DATA/'templates.json').read_bytes()).hexdigest(),
        'boards':boards, 'distinct_parts':len(parts),'fitted_components':sum(p['quantity'] for p in parts),
        'release':'Engineering review only; unverified declarations and candidate alternates require approval.'
    }, indent=2) + '\n')
    return parts, templates, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'hardware/build/components')
    parser.add_argument('--boards', type=int, default=10)
    parser.add_argument('--bom', type=Path, help='Existing KiCad CLI CSV export (still checked against catalogue)')
    parser.add_argument('--placements', type=Path, help='Existing KiCad board position export')
    args = parser.parse_args()
    parts, _, _ = export(args.output, args.boards, args.bom, args.placements)
    print(f'Exported {len(parts)} purchasing parts / {sum(p["quantity"] for p in parts)} components to {args.output}')


if __name__ == '__main__':
    main()
