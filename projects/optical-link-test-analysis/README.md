# optical-link-test-analysis

I built a light-link test simulator to learn how the underlying idea works. This is a learning project.

## What I measure

- **Bit error rate (BER):** wrong bits divided by tested bits. A BERT, or bit error rate tester, compares a known transmitted pattern with received decisions. I do the same comparison for every power point.
- **Receiver sensitivity:** the received power needed to meet a chosen error-rate target. I plot the whole curve and report both the first tested passing power and an estimate between adjacent points when the target is bracketed.
- **Eye diagram:** many short pieces of the signal drawn on top of one another, like a digital communications analyzer (DCA) display. I measure its vertical opening, horizontal opening, and the ratio of light in a one to light in a zero, called extinction ratio.
- **Optical spectrum:** light power versus wavelength, like an optical spectrum analyzer (OSA) trace. I locate the strongest peak, compare it with the strongest separate side peak, and measure the main peak's width at half its maximum power.

A run with zero wrong bits still has uncertainty. I save a one-sided 95% upper bound on BER and use that bound for sensitivity. For example, zero errors in 4,096 bits gives an upper bound of about 0.000731. It cannot establish a target of one error in a trillion bits. The default target is 0.001.

## Change the experiment

```sh
# Increase fiber dispersion by using a longer link.
optical-link --fiber-km 100 --output runs/long-fiber

# Repeat a noise setting with an explicit random seed.
optical-link --noise-std-mw 0.002 --seed 42 --output runs/more-noise

# Ask whether the tested points establish a stricter target.
optical-link --target-ber 0.0001 --output runs/strict-target
```

I use the same random noise sequence across the power points in a sweep to make comparisons less noisy. Repeating the configuration and seed reproduces the numeric results. Changing `--seed` produces another noise realization. Run `optical-link --help` for all command options.

## Reading the saved files

| File | What I use it for |
| --- | --- |
| `ber.csv` | Received power, tested bits, actual errors, measured BER, and its 95% upper bound |
| `eye.csv` | Eye height in milliwatts, width in bit periods and picoseconds, level means and extinction ratio in decibels |
| `spectrum_metrics.csv` | Peak wavelength, main-peak power, side-mode suppression ratio and half-power linewidth |
| `sensitivity.csv` | Target, bracket status, first passing tested power and interpolated estimate |
| `point_NNN_waveform.csv.gz` | Every received sample, transmitted reference bit, and receiver decision; compressed CSV |
| `point_NNN_spectrum.csv` | The full wavelength and spectral-power arrays for each point |
| `commands.csv` | Instrument addresses and commands used during the run |
| `metadata.json` | Simulation label, settings, seed, package versions and completion status |
| `summary.png` | Error curve, eye diagram at the strongest tested power, and spectrum |

To load a saved waveform in Python:

```python
import numpy as np
from optical_link.analysis import analyze_eye, count_errors

# NumPy reads gzip CSV directly. First two columns are reference and decisions.
trace = np.loadtxt("runs/quick/point_000_waveform.csv.gz", delimiter=",", skiprows=1)
print(count_errors(trace[:, 0], trace[:, 1]))
print(analyze_eye(trace[:, 2:].ravel(), trace[:, 0], samples_per_bit=32))
```

## How I model the bench

The source produces PRBS7, a repeating 127-bit pseudo-random binary sequence, and maps it to two optical power levels. I propagate the complex optical field through a frequency-domain fiber-dispersion response, detect its intensity, apply a receiver bandwidth limit, and add Gaussian electrical noise. The receiver samples once per bit against a fixed calibrated midpoint threshold.

The sweep talks to four shared simulated resources through `write`, `query`, and `close`, the same basic interface used by PyVISA. The attenuator changes received power, the BERT acquires and counts errors, the DCA reads that same acquisition, and the OSA returns a separate simulated laser spectrum. My small SCPI command dialect is documented in [the measurement notes](docs/measurements.md). SCPI is a text-command approach to controlling instruments. These commands are specific to this project; connecting real hardware would require vendor command mappings and calibration.

I deliberately keep the laser spectrum separate from the modulated waveform. Its apparent linewidth is the width of a sampled Gaussian peak, not an intrinsic laser linewidth measurement. The model also leaves out clock recovery, laser chirp, polarization, nonlinear fiber effects and instrument resolution broadening. The notes explain the definitions and assumptions behind the measurements.

## Tests and limits

There are 2 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `optical-link-test-analysis-ci.yml`.
