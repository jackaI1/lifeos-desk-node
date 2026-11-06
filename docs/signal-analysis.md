# Checking my room logs

I added this analysis because a sudden room-reading jump is hard to interpret
on its own. I want to see the slower room trend, find repeating interference and
check how much smoothing changes a reading before using it to judge room comfort.
Everything runs on saved logs. The firmware and room-control loop keep their
original behavior.

## Run a comparison with known answers

With Python 3.11 or newer, from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r analysis/requirements.txt
.venv/bin/python -m analysis.demo
```

The output directory must be new. To keep another run, choose a new name with
`--output analysis/build/another-run`. `--seed 7` is the default and fixes the
random-number sequence. I keep generated or private logs under `analysis/build/`,
which Git ignores. I do not commit room recordings.

The demo creates 2,048 five-minute samples, about 7.1 days. The true temperature
is 22 C plus a 0.8 C sine wave repeating every two hours. I add a 0.6 C unwanted
wave repeating every fifteen minutes, Gaussian random noise with standard
deviation 0.18 C, and fifteen isolated 3 C spikes. The humidity channel is a
scaled version for checking units, not an independent humidity physics model.
These frequencies are observable at the actual node's nominal sampling cadence.

Files in the output folder:

- `input.csv`: generated adapter-format readings and separate true values.
- `manifest.json`: seed, tones, amplitudes, cadence and exact spike locations.
- `samples.csv`: aligned raw, median, final filtered and optional true values, in C or %RH.
- `spectrum.csv`: every frequency bin and raw/filtered power density, in unit²/Hz.
- `report.json`: parameters, peak candidates, band powers and error metrics.
- `report.md`: readable comparison. The default run reproduces the [saved report](signal-analysis-report.md).

## Read saved desk-node samples

The adapter in `firmware/tools/desk_api.py` already saves `readings` in SQLite.
I can stop collection or analyze a consistent read snapshot while collection
continues. I choose one device ID, one channel and a continuous time interval:

```sh
.venv/bin/python -m analysis --database room.sqlite3 --device desk-1 \
  --channel temperature --cutoff-hz 0.000277777778 \
  --start 1700000000 --end 1700614100 --output analysis/build/room-temperature
```

`--start` and `--end` are optional inclusive Unix timestamps, seconds since
1 January 1970 UTC. Replace the example interval with the dates in the log.
`--channel humidity` selects relative humidity instead. The tool opens SQLite
with `mode=ro`, never creates a missing database and never writes to the original.
Unknown devices and intervals with fewer than 32 samples produce an error.

For CSV, each row needs `timestamp` and the selected adapter column:
`temperature_mc` (thousandths of a degree C) or `humidity_mpermil` (thousandths
of one percentage point). For example `22000` means 22 C, and `45000` means
45% relative humidity. A file can contain both columns. CSV input must contain
one device and be ordered by timestamp already; it is not a mixed-device export.
Optional `true_temperature_mc` and `true_humidity_mpermil` supply reference values
in the same units. Do not supply them for an unknown real temperature.

```sh
.venv/bin/python -m analysis --csv analysis/build/demo/input.csv \
  --channel temperature --cutoff-hz 0.000277777778 \
  --median-window 5 --output analysis/build/csv-comparison
```

All timestamps must be positive and synchronized. At least 32 and at most 200,000
finite samples are accepted; CSV size is limited to 32 MB. Cadence can vary by
up to 1% around its median interval. A duplicate timestamp, unsynchronized sample,
missing reading or larger gap stops analysis. I crop a continuous interval rather
than silently fill gaps or mix readings from different devices. Small accepted
timing jitter is approximated as uniform sampling at that median interval.
Output must be a new directory, protecting source files and previous reports.

## What each stage does

1. A centered moving median replaces each reading with the middle value from
   an odd group of nearby readings. The default five samples span twenty minutes
   between the oldest and newest samples. Endpoints repeat at the edges. I can
   choose an odd `--median-window` from 1 to 101, limited by the record length;
   1 bypasses spike removal. The bound also limits temporary filtering memory.
2. A fourth-order Butterworth low-pass uses small cascaded sections to keep the
   numerical calculation stable. `--cutoff-hz` is cycles per second: 1/3600 Hz
   corresponds to a one-hour period. The filter runs forward and backward so
   slow changes are not shifted in time. Each pass has amplitude gain 1/sqrt(2)
   at cutoff; together they have gain 0.5, or about -6.02 dB. That cutoff describes
   the low-pass stage alone. The nonlinear median changes the combined response.
3. A Hann window softens the record boundaries before a real FFT. I remove the
   mean first so the room's 22 C baseline does not count as useful changing signal.
   The one-sided power spectral density includes the negative-frequency power.
   Frequency resolution is sample rate divided by sample count, without zero
   padding. Local maxima are sorted by power; the five strongest above the
   chosen signal band are noise candidates, not proof of a physical cause.

The cutoff must cover at least one FFT bin and stay below half the sampling
frequency, called the
Nyquist limit. With one sample every 300 seconds, Nyquist is 0.001667 Hz, a
ten-minute period. Shorter-period interference can appear at a false slower
frequency, called aliasing. These logs cannot diagnose 50/60 Hz electrical noise;
that needs faster measurements and appropriate filtering before sampling.

The one-hour cutoff is a demo choice for separating the two-hour room cycle
from fifteen-minute interference. I would choose it based on the timescale of
interest in an actual room. It could erase a real rapid temperature change.
This is offline analysis: it uses future samples and is unsuitable for direct
live thermostat control. Padding reduces boundary artifacts but cannot remove
all edge uncertainty, especially for very low cutoffs or short records.

## Reading signal-to-noise ratio

The FFT estimate splits power at `--signal-max-hz`, which defaults to the cutoff.
It excludes the zero-frequency bin, integrates power in each band and reports
`10 log10(low-band power / high-band power)`. A higher number means more of the
remaining changes are slow. This is a **band SNR proxy**, not an independently
measured sensor SNR: low-frequency noise counts as signal and useful fast changes
count as noise. Filtering itself raises this ratio, so it cannot establish that
the chosen trend is correct. The signal band must contain at least one nonzero
FFT bin; use a longer recording if it does not.

When true values are supplied, I separately calculate root mean square error
(RMSE) and `10 log10(variance(true values) / mean squared error)`. This removes
the true signal's constant baseline from signal power and counts bias as error.
The error uses every aligned sample including the boundaries. A zero numerator
or denominator produces JSON `null` and readable `undefined`, rather than a
misleading finite number or nonstandard Infinity. Real logs without true values
have no ground-truth error claim.

## Design references and checks

I use SciPy's [Butterworth design](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.butter.html),
[forward/backward section filter](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html)
and [periodogram normalization](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.periodogram.html).
The low-pass tests separately measure long sine waves in the passband, exactly at
cutoff and in the stopband, discarding transient edges only for that gain check.
Other tests recover known tones within one FFT bin, check integrated power and
known band SNR, remove spikes, exercise real adapter schema/units/read-only access,
reject broken logs and run the command-line tools. The synthetic error comparison
does not discard edges.

```sh
.venv/bin/python -m pip install -r analysis/requirements-dev.txt
.venv/bin/python -m pytest analysis/tests -q
```

GitHub CI runs the suite on Python 3.11 and 3.12, regenerates the default report
and compares it with the committed report. It saves all generated synthetic
outputs for inspection. No hardware, LifeOS account or network service is needed.
