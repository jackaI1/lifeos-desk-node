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
