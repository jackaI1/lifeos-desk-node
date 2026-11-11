"""Summarize the iCEBreaker build and fail if the clock target is not met.

Reads the nextpnr log in build/board and prints the maximum clock frequency,
the resource use and the bitstream size. Exits 1 when place and route did not
reach the 12 MHz board clock or when the bitstream is missing.

Usage: python3 scripts/board_report.py build/board
"""
import re
import sys
from pathlib import Path

FMAX = re.compile(r"Max frequency for clock '([^']+)': ([\d.]+) MHz \((PASS|FAIL) at ([\d.]+) MHz\)")
USE = re.compile(r"^\s*(ICESTORM_\w+|SB_\w+)\s*:\s*(\d+)\s*/\s*(\d+)", re.MULTILINE)


def main(build_dir):
    build = Path(build_dir)
    log = (build / 'nextpnr.log').read_text(errors='replace')
    bitstream = build / 'desk_board.bin'
    problems = []

    fmax = FMAX.findall(log)
    if not fmax:
        problems.append('nextpnr printed no maximum frequency')
    for clock, achieved, verdict, target in fmax:
        print(f'clock {clock}: {achieved} MHz achieved, target {target} MHz, {verdict}')
        if verdict != 'PASS':
            problems.append(f'clock {clock} misses {target} MHz')

    for resource, used, available in USE.findall(log):
        print(f'{resource}: {used} of {available}')

    if not bitstream.exists() or bitstream.stat().st_size == 0:
        problems.append('no bitstream was written')
    else:
        print(f'bitstream: {bitstream.stat().st_size} bytes')

    for problem in problems:
        print(f'FAIL: {problem}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'build/board'))
