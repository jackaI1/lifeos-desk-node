"""Nominal and bounded fit checks for the enclosure assembly nest, mm."""
import argparse,csv,html,json,pathlib


def check(p):
    px=p['enclosure_length_mm']+2*p['clearance_per_side_mm']
    py=p['enclosure_width_mm']+2*p['clearance_per_side_mm']
    wall=min(p['floor_mm'],(p['outer_length_mm']-px)/2,(p['outer_width_mm']-py)/2)
    hole_edge=min(p['outer_length_mm']/2-p['hole_x_mm'],p['outer_width_mm']/2-p['hole_y_mm'])-p['hole_diameter_mm']/2
    hole_pocket=min(p['hole_x_mm']-px/2,p['hole_y_mm']-py/2)-p['hole_diameter_mm']/2
    rows=[]
    for s in p['shrinkage_values']:
        if s<0 or s>=1: raise ValueError('Invalid shrinkage')
        rows.append(dict(shrinkage=s,worst_total_gap_x_mm=(px-p['pocket_size_tolerance_mm'])*(1-s)-(p['enclosure_length_mm']+p['enclosure_size_tolerance_mm']),
                         worst_total_gap_y_mm=(py-p['pocket_size_tolerance_mm'])*(1-s)-(p['enclosure_width_mm']+p['enclosure_size_tolerance_mm'])))
    flags=[]
    if wall<p['minimum_wall_mm']: flags.append('wall')
    if min(hole_edge,hole_pocket)<p['minimum_edge_ligament_mm']: flags.append('hole_edge')
    if min(min(r['worst_total_gap_x_mm'],r['worst_total_gap_y_mm']) for r in rows)<=0: flags.append('fit_stack')
    return dict(pocket_mm=[px,py],minimum_wall_mm=wall,hole_to_outer_edge_ligament_mm=hole_edge,
                hole_to_pocket_ligament_mm=hole_pocket,shrinkage=rows,flags=flags,passes=not flags,
                note='Isotropic fixture shrinkage applied to the minimum pocket size. Enclosure remains at maximum unshrunk size. No physical fit test.')


def instructions(bom,out):
    rows=list(csv.DictReader(pathlib.Path(bom).open()));out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    labels=[]
    for i,row in enumerate(rows,1):
        labels.append('<article><strong>BIN B%02d</strong><h2>%s</h2><p>%s</p><p>Qty per assembly: %s<br>Material: %s</p><p>Return surplus here. Keep one part type per bin.</p></article>'%(i,html.escape(row['id']),html.escape(row['description']),html.escape(row['quantity']),html.escape(row['material'])))
    (out/'5S-labels.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Enclosure 5S bin labels</title><style>body{font:18px system-ui;display:grid;grid-template-columns:repeat(2,1fr);gap:15px}article{border:2px solid;padding:20px;break-inside:avoid}h2{margin:8px 0}@media print{article{min-height:55mm}}</style>'+''.join(labels)+'</html>')
    (out/'work-instruction.md').write_text('''# Enclosure assembly nest work instruction

I use this fixture to locate the revision B enclosure while placing the PCB, gasket and lid. This instruction is generated from the parts list. It has not been tried physically.

1. Check the current drawing revision, DFM results and shrinkage sweep. Slice the fixture floor-down with the saved profile. Inspect the G-code in the slicer before any machine use. Print and measure a fit coupon before making the full fixture.
2. Keep the fixture on a flat bench. Check the nest for burrs and debris. Place the housing floor-down; it should sit flat without force. Stop if it rocks or binds.
3. Place the carrier on its four posts. Confirm actual PCB hole spacing against the drawing before fastening. Route wiring so the lid cannot pinch it.
4. Place the sheet gasket into the groove without stretching it. The tolerance report currently flags compression outside the target at worst case. Resolve and measure that stack before treating this as a seal.
5. Place the lid on the four shoulders. Start all four reference M3 screws by hand, then tighten in a cross pattern using a torque established by physical thread and material tests. No torque is specified or validated here.
6. Inspect lid seating, wire clearance and visible gasket location. Record measured gap and parts revision. Do not claim ingress protection or powered safety from this fixture.
7. Return parts to their matching B-number bins. Remove debris and return the fixture to its labeled location. Replace damaged printed tooling.

## Parts per assembly

'''+''.join(f"- {r['quantity']} x {r['id']}: {r['description']} ({r['material']})\n" for r in rows))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('spec');p.add_argument('output');p.add_argument('--bom');a=p.parse_args()
    out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=True)
    (out/'fit-dfm.json').write_text(json.dumps(check(json.loads(pathlib.Path(a.spec).read_text())),indent=2)+'\n')
    if a.bom: instructions(a.bom,out)
