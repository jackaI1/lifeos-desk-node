"""Bounded, file-only sigrok subprocesses shared by capture tools."""
from pathlib import Path
import subprocess
import tempfile

MAX_SAMPLES = 8_000_000


def sigrok(args):
    # Spool annotations to disk, not an unbounded in-memory capture_output buffer.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            result = subprocess.run(['sigrok-cli', *map(str, args)], stdout=out,
                                    stderr=err, timeout=90, check=False)
        except FileNotFoundError as exc:
            raise ValueError('install sigrok-cli (see docs/capture-decoding.md)') from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError('sigrok-cli exceeded 90 seconds') from exc
        err.seek(0)
        diagnostic = err.read(4096).decode(errors='replace').strip()
        # Some libsigrok input errors return zero. Never accept their diagnostics
        # as evidence of a successful decode.
        if result.returncode or diagnostic:
            raise ValueError(f'sigrok-cli failed: {diagnostic or result.returncode}')
        if out.tell() > 32_000_000:
            raise ValueError('decoder output exceeds 32 MB; crop the capture')
        out.seek(0)
        return out.read().decode('utf-8')


def save_sr(samples, path, rate):
    with tempfile.TemporaryDirectory(prefix='desk-capture-') as tmp:
        raw = Path(tmp) / 'logic.bin'
        raw.write_bytes(samples)
        sigrok(['-i', raw, '-I', f'binary:numchannels=3:samplerate={rate}',
                '-C', '0=SCL,1=SDA,2=TX', '-o', path, '-O', 'srzip'])
