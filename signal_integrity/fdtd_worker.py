"""Run one openEMS simulation in its own process and save its S-parameters.

openEMS keeps solver state in the Python process, and a second run in the same
process has failed in the Debian build. Each run therefore gets a fresh process,
started by fdtd.run_isolated. The worker exits with os._exit after saving: the
solver's C++ objects can crash the interpreter during normal shutdown.

    python -m signal_integrity.fdtd_worker SPEC.json RESULT.npz
"""

import json
import os
import sys
from pathlib import Path

import numpy as np

from signal_integrity import fdtd


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    spec_path, out_path = Path(argv[0]), Path(argv[1])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    model = fdtd.model_from_dict(spec["model"])
    freq, s11, s21 = fdtd.build_and_run(model)
    np.savez(out_path, freq=freq, s11=s11, s21=s21)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
