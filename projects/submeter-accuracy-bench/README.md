# submeter-accuracy-bench

I built a software bench for checking electricity meters to learn how the underlying idea works. This is a learning project.

## Change the experiment

```sh
# Remove the deliberate drift. All 40 units pass with this seed.
uv run submeter-bench --gain-drift-pct 0 --output reports/stable --fail-on-unit-failure

# Change the batch size and random seed.
uv run submeter-bench --units 80 --seed 7 --output reports/batch-7

# Compare phase error and a residual power offset at light loads.
uv run submeter-bench --gain-drift-pct 0 --phase-drift-deg 0.03 --output reports/phase
uv run submeter-bench --gain-drift-pct 0 --offset-drift-w 0.05 --output reports/offset
```

The seed reproduces the same unit errors. Drift settings are added for each successive unit: `--gain-drift-pct 0.035` adds 0.035 percentage points to current gain per unit after the first. `--baseline-units` sets the size of a separate batch without deliberate drift; its default is 20 and minimum is 10. Running into the same output directory replaces the six report files. Use a different directory to keep an experiment.

The command normally exits successfully even when simulated meters fail. Add `--fail-on-unit-failure` to return exit code 1 for any failed unit. Invalid settings return 2. Warnings alone do not change the exit code.

## Inside the bench

I generate voltage and current samples at 7,200 samples per second, covering 12 complete cycles at 60 Hz. I calculate reference energy by multiplying simultaneous voltage and current samples, summing across time and phases, and converting watt-seconds to watt-hours. The reference does not use the meter's error parameters.

Each simulated meter has its own seeded voltage gain, current gain, phase error, voltage/current offsets and residual power bias. I apply those errors to the measurement channels before calculating its reading. This lets phase error behave differently with leading and lagging loads, and lets a small fixed power bias matter more at light loads.

`src/submeter_bench/` separates waveforms, meter errors, the cited test profile, batch decisions, control limits and reports. [The method notes](docs/method.md) explain the equations, assumptions and limitations, including the ideal reference and omitted hardware tests. A real bench would need calibrated equipment, an uncertainty budget and the full applicable test programme.

## Tests and limits

There are 2 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `submeter-accuracy-bench-ci.yml`.
