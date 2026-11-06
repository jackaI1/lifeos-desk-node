"""Generate printable documents from a validated pin map."""
import argparse
import csv
import html
from pathlib import Path
from .check import load, validate

def write_csv(path, header, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

def endpoint(w, side):
    return ':'.join(w[side])

def generate(data, out):
    errors = validate(data)
    if errors:
        raise ValueError('\n'.join(errors))
    out.mkdir(parents=True, exist_ok=True)
    wires = data['wires']
    write_csv(out / 'cut-list.csv', ['Wire', 'Net', 'From', 'To', 'Cut length (mm)', 'AWG', 'Color', 'Design current (A)'],
              ([w['id'], w['net'], endpoint(w, 'from'), endpoint(w, 'to'), w['length_mm'], w['awg'], w['color'], w['current_a']] for w in wires))
    write_csv(out / 'labels.csv', ['Wire', 'End', 'Connect to', 'Net', 'Color'],
              ([w['id'], side, endpoint(w, side), w['net'], w['color']] for w in wires for side in ('from', 'to')))
    rows = [[w['id'], 'Continuity', endpoint(w, 'from'), endpoint(w, 'to'), 'Connected', '', ''] for w in wires]
    rows += [['POWER', 'Polarity / isolation', '3V3', 'GND', 'No short with power disconnected', '', ''],
             ['POWER', 'Polarity', '3V3', 'GND', 'After inspection, verify +3.3 V with one supply', '', '']]
    write_csv(out / 'test-sheet.csv', ['Wire', 'Test', 'Probe + / end A', 'Probe - / end B', 'Expected', 'Result', 'Initials / date'], rows)
    esc = lambda x: html.escape(str(x), quote=True)
    height = 110 + len(wires) * 48
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="{height}" viewBox="0 0 1000 {height}">',
           '<rect width="100%" height="100%" fill="white"/>', f'<text x="20" y="30" font-family="sans-serif" font-size="20">{esc(data.get("title", "Harness"))}</text>',
           '<text x="20" y="60" font-family="sans-serif" font-size="13">Point-to-point schematic, not physical routing. Check connector orientation before assembly.</text>']
    for i, w in enumerate(wires):
        y = 100 + i * 48
        svg.extend([f'<text x="20" y="{y}" font-family="sans-serif" font-size="14">{esc(endpoint(w, "from"))}</text>',
                    f'<line x1="230" y1="{y-5}" x2="690" y2="{y-5}" stroke="#333" stroke-width="2"/>',
                    f'<text x="250" y="{y-12}" font-family="sans-serif" font-size="12">{esc(w["id"])} | {esc(w["net"])} | {esc(w["color"])} | {esc(w["awg"])} AWG | {esc(w["length_mm"])} mm</text>',
                    f'<text x="710" y="{y}" font-family="sans-serif" font-size="14">{esc(endpoint(w, "to"))}</text>'])
    svg.append('</svg>')
    (out / 'harness.svg').write_text('\n'.join(svg), encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('map')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        generate(load(args.map), Path(args.output))
    except (OSError, ValueError) as exc:
        parser.exit(1, f'{exc}\n')
    print(f'Documents written to {args.output}')

if __name__ == '__main__':
    main()
