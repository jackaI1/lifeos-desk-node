"""Run the PLL regression and write a machine-readable summary."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def summarize(log: str, returncode: int) -> dict:
    matches = re.findall(r'Coverage: (\d+)/(\d+) required bins', log)
    hit, total = map(int, matches[-1]) if matches else (0, 0)
    records = re.findall(r'FIFO_COVERAGE depth=(\d+) seed=(\d+) hit=(\d+) total=(\d+)', log)
    expected = {(d,s) for d in [1,3,8] for s in [17,409,20261106]}
    observed = {(int(d),int(s)) for d,s,_,_ in records}
    fifo_ok = observed == expected and len(records)==len(expected) and all(
        int(h)==7 and int(t)==7 for _,_,h,t in records)
    pll_ok = len(matches)==1 and (hit,total)==(11,11)
    return {'status': 'pass' if returncode == 0 and pll_ok and fifo_ok else 'fail',
            'simulation_exit_code': returncode, 'coverage_hit': hit, 'coverage_total': total,
            'fifo_runs': [{'depth': int(d), 'seed': int(s), 'hit': int(h), 'total': int(t)}
                          for d,s,h,t in records]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('build/report.json'))
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    log_path = args.output.with_suffix('.log')
    with log_path.open('w') as log:
        result = subprocess.run([sys.executable, '-m', 'pytest', '-s', '-q',
                                 '--basetemp', str(args.output.parent / (args.output.stem+'-simulation')),
                                 str(ROOT / 'tests/test_regression.py'), str(ROOT / 'tests/test_fifo.py')],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
    content = log_path.read_text()
    report = summarize(content, result.returncode)
    print(json.dumps(report, indent=2))
    if report['status'] != 'pass':
        print('\n'.join(content.splitlines()[-40:]))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
