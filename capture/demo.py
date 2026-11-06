"""Build clean and deliberately damaged captures and verify their reports."""
import json
from pathlib import Path
import subprocess
import sys

from .decode import decode
from .generate import main as generate

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'replay/build/captures'
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(['make', '-C', str(ROOT / 'replay')], check=True)
    for name in ('clean', 'corrupt'):
        (output / f'{name}.scm').write_text((ROOT / f'capture/examples/{name}.scm').read_text())
        with (ROOT / f'capture/examples/{name}.scm').open() as source:
            compiled = subprocess.run(['guile', '--no-auto-compile', '-L', str(ROOT / 'replay/scheme'),
                                       str(ROOT / 'replay/compile.scm')], stdin=source,
                                      capture_output=True, text=True, check=True).stdout
        wire, uart = output / f'{name}.wire', output / f'{name}.uart.txt'
        wire.write_text(compiled)
        subprocess.run([str(ROOT / 'replay/build/desk-replay'), '--uart-log', str(uart)],
                       input=compiled, text=True, check=True, capture_output=True)
        faults = ['--fault', 'nack', '--fault', 'missing-ack', '--fault', 'uart-framing'] if name == 'corrupt' else []
        for suffix in ('.sr', '.csv'):
            path = output / (name + suffix)
            status = generate([str(wire), '--uart-log', str(uart), '--output', str(path), *faults])
            if status:
                return status
            report = decode(path, samplerate=2_000_000)
            report_path = path.with_suffix(suffix + '.report.json')
            report_path.write_text(json.dumps(report, indent=2) + '\n')
            expected = {'unexpected_nack', 'missing_ack', 'bad_crc', 'uart_framing', 'incomplete_transaction'} if name == 'corrupt' else set()
            actual = {item['code'] for item in report['findings']}
            if actual != expected or len(report['findings']) != len(expected):
                raise ValueError(f'{name}{suffix}: expected {sorted(expected)}, got {sorted(actual)}')
            print(f'{name}{suffix}: {len(report["sensor_readings"])} sensor reading, '
                  f'{report["uart"]["byte_count"]} UART bytes, {len(report["findings"])} findings')
    print(f'Captures and JSON reports: {output}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'capture demo: {exc}', file=sys.stderr)
        sys.exit(2)
