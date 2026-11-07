"""Run real core properties and require the seeded flush error to fail."""
import json
from pathlib import Path
import subprocess


def run(output=Path('build/formal')):
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    for task in ['bmc', 'prove', 'cover', 'bug']:
        folder = output / task
        with (output / f'{task}.log').open('w') as log:
            proc = subprocess.run(['sby', '-f', '-d', str(folder), 'formal/core.sby', task],
                                  stdout=log, stderr=subprocess.STDOUT, timeout=300)
        status = (folder / 'status').read_text().strip().split()[0] if (folder / 'status').exists() else 'ERROR'
        # A tool crash/timeout is never accepted as successful fault detection.
        expected = 'FAIL' if task == 'bug' else 'PASS'
        results[task] = status
        if status != expected or (task != 'bug' and proc.returncode != 0):
            raise RuntimeError(f'{task}: expected {expected}, got {status}; see {output}/{task}.log')
        if task == 'bug' and not list(folder.glob('engine_*/trace_tb.v')):
            raise RuntimeError('Seeded bug failed without a replayable counterexample')
    (output / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results))
    return results


if __name__ == '__main__':
    run()
