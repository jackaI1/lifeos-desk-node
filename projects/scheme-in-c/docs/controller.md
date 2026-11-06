# Thermostat fixture

I use this small C state machine to practice testing time-dependent control logic alongside the interpreter. It is independent of Scheme and does not control physical hardware.

The caller initializes a `Thermostat` with a lower threshold, an upper threshold (both in integer milli-degrees Celsius), and a nonzero timeout in samples. Initialization rejects a null pointer, reversed or equal thresholds, and a zero timeout. The caller owns the state and calls `thermostat_step` once per fixed sampling interval. There is no allocation in either function. The caller must provide a valid initialized state and a trustworthy validity flag; sensor range checking and scheduling belong to the caller.

At or below the lower threshold, heat turns on; at or above the upper threshold, it turns off. In between, the output holds its previous value. Missing samples preserve the output until the configured number of consecutive misses, when a fault turns heat off. The miss counter saturates at the timeout. The next valid sample clears the fault and counter; if it falls inside the deadband, heat remains off after a fault. The fault duration in seconds is the sampling interval multiplied by the timeout. This policy is an example, not a safety-certified controller.

`tests/thermostat_trace.csv` records a short deterministic sequence with expected outputs. `tests/test_controller.py` also compares 20,000 reproducible randomized samples to a Python reference model. The line-oriented driver runs the real C code as a subprocess, including in the sanitizer build. `make test` and `make sanitize` run both interpreter and controller checks.
