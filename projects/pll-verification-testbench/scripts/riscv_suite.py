"""Fetch pinned public instruction tests and run every rv32ui program unmodified.

Only the bare-metal environment is replaced. The upstream test bodies and scalar
macros come directly from the pinned commit, including their LICENSE.
"""
import argparse
import io
import json
from pathlib import Path
import re
import subprocess
import urllib.request
import zipfile

REVISION = '3df703cd52d5f0d8224e3c50bf03c6cb70efff98'
ROOT = Path(__file__).resolve().parents[1]


def fetch(destination):
    url = f'https://codeload.github.com/riscv-software-src/riscv-tests/zip/{REVISION}'
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(8_000_001)
    if len(data) > 8_000_000:
        raise RuntimeError('Unexpected upstream archive size')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        prefix = f'riscv-tests-{REVISION}/'
        for name in archive.namelist():
            rel = Path(name.removeprefix(prefix))
            if name.endswith('/') or '..' in rel.parts or rel.is_absolute():
                continue
            if rel.parts[0] == 'isa' or str(rel) == 'LICENSE':
                target = destination / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))


def build_core(output, fast=1):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    command = ['verilator', '--cc', '--exe', '--build', '-j', '2', '-Wno-fatal',
               '--assert', '--top-module', 'rv32_core', f'-GFAST_ALU={fast}',
               '--Mdir', str(output), str(ROOT/'rtl/rv32_core.sv'), str(ROOT/'tests/core_main.cpp')]
    with (output/'compile.log').open('w') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    return output/'Vrv32_core'


def run_suite(output):
    output.mkdir(parents=True, exist_ok=True)
    vendor = output/'upstream'
    fetch(vendor)
    fragment = (vendor/'isa/rv32ui/Makefrag').read_text()
    body = fragment.split('rv32ui_sc_tests =', 1)[1].split('rv32ui_p_tests', 1)[0]
    names = body.replace('\\', '').split()
    assert len(names) >= 38, 'Upstream manifest is unexpectedly short'
    executable = build_core(output/'sim')
    # The first upstream misalignment test uses TESTNUM=1. Prove that its
    # failure macro cannot be mistaken for the normal gp=1 success signal.
    negative=output/'adapter-failure.S'
    negative.write_text('#include "riscv_test.h"\nRVTEST_CODE_BEGIN\nli gp,1; RVTEST_FAIL\n')
    results = []
    negative_caught=False
    for name in ['adapter-failure']+names:
        elf, binary = output/f'{name}.elf', output/f'{name}.bin'
        cmd = ['riscv64-unknown-elf-gcc', '-march=rv32i_zifencei', '-mabi=ilp32',
               '-nostdlib', '-nostartfiles', '-Wl,--no-relax',
               '-T', str(ROOT/'tests/programs/link.ld'), '-I', str(ROOT/'tests/programs'),
               '-I', str(vendor/'isa/macros/scalar'),
               str(negative if name=='adapter-failure' else vendor/f'isa/rv32ui/{name}.S'), '-o', str(elf)]
        compiled=subprocess.run(cmd, capture_output=True, text=True)
        (output/f'{name}-compile.log').write_text(compiled.stdout+compiled.stderr)
        if compiled.returncode:
            raise RuntimeError(f'{name} assembly failed:\n{compiled.stderr[-3000:]}')
        subprocess.run(['riscv64-unknown-elf-objcopy', '-O', 'binary', str(elf), str(binary)], check=True)
        proc = subprocess.run([str(executable), str(binary), str(output/f'{name}.trace')],
                              capture_output=True, text=True, timeout=30)
        (output/f'{name}.log').write_text(proc.stdout+proc.stderr)
        counts = {k: int(v) for k,v in re.findall(r'(\w+)=(\d+)', proc.stdout)}
        if name=='adapter-failure':
            negative_caught=proc.returncode==1 and counts.get('test_number')==3
            if not negative_caught: raise RuntimeError('The upstream test failure adapter did not reject TESTNUM=1')
            continue
        results.append({'name': name, 'passed': proc.returncode == 0, **counts})
        print(f'{name}: {"PASS" if proc.returncode == 0 else "FAIL"} {proc.stdout.strip()}')
    report = {'revision': REVISION, 'negative_control_caught':negative_caught, 'total': len(results),
              'passed': sum(r['passed'] for r in results), 'tests': results}
    (output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    if report['passed'] != report['total']:
        raise RuntimeError('Upstream instruction regression failed')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=Path('build/riscv-tests'))
    run_suite(p.parse_args().output)
