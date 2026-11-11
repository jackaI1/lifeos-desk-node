"""Summarize the Yosys reports for the sensor path and fail if anything is unmapped.

Reads build/synth_stat.txt and build/synth_ltp.txt written by synth/synth_ice40.ys.
Exits 1 when the netlist still has generic cells (for example $_DFF_ or $mem),
which would mean the design did not map onto the iCE40 primitives.
"""
import re
import sys
from pathlib import Path

ALLOWED_GENERIC = {'$scopeinfo'}   # debug scope markers, not logic


def main(build):
    build = Path(build)
    stat = (build / 'synth_stat.txt').read_text()
    ltp = (build / 'synth_ltp.txt').read_text()
    cells = {}
    for match in re.finditer(r'^\s+(\d+)\s+(\S+)\s*$', stat, re.MULTILINE):
        cells[match.group(2)] = int(match.group(1))
    unmapped = {name: count for name, count in cells.items()
                if name.startswith('$') and name not in ALLOWED_GENERIC}
    length = re.search(r'Longest topological path in \S+ \(length=(\d+)\)', ltp)
    lut4 = cells.get('SB_LUT4', 0)
    flops = sum(cells.get(name, 0) for name in cells if name.startswith('SB_DFF'))
    print('Yosys synthesis, sensor_path for iCE40 (FPGA-style), counts from build/synth_stat.txt')
    print(f'  LUT4 cells:          {lut4}')
    print(f'  flip-flops:          {flops}')
    print(f'  carry cells:         {cells.get("SB_CARRY", 0)}')
    print(f'  total mapped cells:  {sum(v for k, v in cells.items() if k.startswith("SB_"))}')
    print(f'  logic depth (ltp):   {length.group(1) if length else "missing"} cells')
    if unmapped:
        print(f'  UNMAPPED cells: {unmapped}')
        return 1
    if not length:
        print('  missing logic-depth report')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'build'))
