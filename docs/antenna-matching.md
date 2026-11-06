# Planning an antenna match

I built an offline matching calculator because a smaller carrier board or nearby
screen can change how an antenna behaves. It suggests small inductors and
capacitors between a radio and an antenna. This is a tool for future external
antenna experiments, not a modification of the WROOM-32E module's factory match.
Both desk boards retain that module and its built-in antenna. There is no exposed
RF feed on these carrier boards where these parts can simply be fitted.

## Try it with known synthetic data

With Python 3.11 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r antenna_matching/requirements.txt
.venv/bin/python -m antenna_matching.match antenna_matching/examples/synthetic-antenna.s1p \
  --source-kind synthetic --output antenna_matching/build/example
```

`report.json` lists both networks in order from radio to antenna, values in
henries or farads, and return loss before and after. Return loss describes how
much radio energy comes back toward the radio; a larger positive dB number means
less reflection. `sweep.csv` compares the whole frequency range. The two predicted
`.s1p` files can be opened in other RF software.

The committed example is **synthetic**, a 25 Ω resistor, 5 nH inductor and
0.7 pF capacitor in series, sampled from 2.3 to 2.6 GHz. It is deliberately
mismatched. Recreate it with
`.venv/bin/python antenna_matching/examples/generate.py`. With assumed Q = 50,
meaning finite component loss, the calculated L network changes worst-band
return loss across 2.4–2.5 GHz from **7.79 to 22.77 dB**. Its ±5% component
corners remain above **21.03 dB** in this model. These are software predictions
against a known circuit, not antenna measurements or proof of radio range.

## Use an actual measurement

A VNA, or vector network analyzer, measures reflection versus frequency. Calibrate
it at the antenna feed plane using open, short and load standards. Disconnect the
radio before attaching the VNA; document the antenna, enclosure, cable routing,
calibration, reference plane and instrument settings. Save a calibrated one-port
Touchstone `.s1p` sweep covering the full chosen band with enough points to see
narrow resonances. Then run:

```sh
.venv/bin/python -m antenna_matching.match my-antenna.s1p \
  --source-kind measured --low-ghz 2.4 --high-ghz 2.5 --q 50 \
  --output antenna_matching/build/my-antenna
```

The source-kind flag records the caller's description; it cannot authenticate a
measurement. I have not supplied or claimed a measured antenna dataset here.
The tool records the file hash so results can be tied to an exact input. It
accepts RI (real/imaginary), MA (magnitude/angle) and DB Touchstone representations,
uses the file's reference impedance and renormalizes to 50 Ω. It rejects
multiport files, active loads, invalid frequencies and requests outside the sweep.
It never extrapolates missing measurements.

## What the search means

I use [scikit-rf](https://scikit-rf.readthedocs.io/en/latest/examples/matching/Impedance%20Matching.html)
to load the measured network, represent each two-port component and cascade it
with the antenna. An L network has two parts, one in series with the feed and
one from the feed to ground; both orders are searched. A pi network adds another
part to ground, giving the drawing a pi shape. The search considers inductors
and capacitors at each position, with 0.1–30 nH or 0.1–30 pF bounds. SciPy searches
for low mean reflected power throughout the requested band, with a fixed seed.
Values are rounded to E24 preferred values and scored again. Each part has a
series resistance `abs(reactance) / Q`; the reported tolerance result sweeps all
±5% value corners. The search is numerical and can settle on a local solution.
It reports the outcome even if an already-good antenna cannot be improved.

A good match can dissipate energy in lossy components. Lower reflection does not
prove high radiation efficiency. Choose actual RF parts with suitable Q and
self-resonant frequency, add pad/trace parasitics or measured component networks,
then remeasure the assembled match and radiated performance in the enclosure.
Never cut into a certified module's antenna feed on the strength of this model.
