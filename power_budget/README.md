# Desk-node power estimates

I use `python3 -m power_budget.compare` to compare Rev A and Rev B using the
firmware sleep setting, datasheet currents and explicit assumptions. The
[power guide](../docs/power-and-battery.md) explains each input, the runtime
calculation and the empty bench sheet. These are calculations, not measurements.

The original preliminary command remains available:

```sh
python3 -m power_budget --active-seconds 10 --display-ma 3 --led-forward-v 2
```

That command keeps its original simplified Rev A calculation for compatibility;
it omits conversion, pull-resistor and leakage allowances included in the new
comparison. Run both old and new checks with `python3 -m pytest power_budget/tests -q`.

## Checking a charging cycle and a saved current trace

I also model a duty-cycled cell load and a constant-current/constant-voltage
charging cycle. These are calculations, with a linear cell voltage model and
series resistance; they are not measured charging curves or a charger design.

```sh
python3 -m power_budget.charging --profile power_budget/examples/duty.json --capacity-mah 500 --temperature-c 5
python3 -m power_budget.charging --output /tmp/desk-charge.csv
python3 -m power_budget.charging --trace my-current.csv --budget-ma 10
```

A profile is an array of named phases with `seconds` and cell-side `ma`. The
example includes the OLED's continuous draw in every phase. The model weights
current by duration, applies an explicit cold-capacity assumption and reports
zero usable runtime at or below the loaded brown-out cutoff. A zero-current
profile has no finite battery-life estimate rather than a divide-by-zero result.

The charge model integrates delivered current into state of charge, switches
from current limiting to voltage limiting and stops at the termination current.
It inhibits charging outside 0..45 C and halves the current near the cold/hot
limits. Those thresholds are example assumptions, not a verified cell datasheet.
`my-current.csv` has `seconds,ma,voltage,temperature_c`; the checker integrates
current by the trapezoidal rule and flags budget, voltage and temperature
violations. It rejects nonfinite values and backwards time. Charging CSVs have
`seconds,soc,ma,voltage,stage`; a measured-budget trace is a different schema.
Tests check charge conservation, integration step convergence, termination,
cold/hot cases and brown-outs. I still need physical cell and regulator data.
