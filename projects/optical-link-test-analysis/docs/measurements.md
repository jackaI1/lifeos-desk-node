# Measurement definitions and simulation limits

Everything in this repository is simulated. No physical optical equipment was used. The analysis functions consume arrays rather than reading ground-truth spectrum parameters, so the stored traces can be analyzed again independently.

## Link

PRBS7 uses the primitive polynomial x^7 + x^6 + 1 with an all-ones initial state. Its period is 127 bits, with 64 ones. The requested bit count can include a partial final repetition. The nominal received power P is the balanced-bit mean in mW, converted from dBm as 10^(dBm/10). With extinction ratio r = 10^(ER_dB/10), P0 = 2P/(1+r), P1 = r P0. The actual PRBS mean differs slightly because there is one extra one in each complete period.

Supported configuration ranges are 0.001..1000 Gbit/s, 0.001..100 dB extinction, 0..10000 km fiber, -10000..10000 ps²/km beta2, 0.001..1000000 GHz receiver bandwidth, and 0..100 mW noise standard deviation. These broad numerical limits prevent overflow; they do not imply physical validity everywhere in those ranges. Captures are limited to 16 million samples.

The source field is the positive square root of the NRZ intensity (non-return-to-zero means a level is held for the entire bit). Fiber propagation uses H(omega) = exp(-j beta2 L omega^2 / 2), with omega in radians/ps, beta2 in ps²/km and L in km. The default beta2 is -21.7 ps²/km. Square-law detection recovers intensity. The electrical Gaussian receiver response is exp[-ln(2)/2 * (f/B)^2], with a -3 dB amplitude bandwidth B of 7 GHz. The bit rate defaults to 10 Gbit/s, sampled 32 times per bit.

FFT propagation treats the finite record as circular. The boundary of a truncated PRBS record wraps to its beginning; this is part of the synthetic periodic record, not a model of a real packet boundary. There is no adaptive timing or threshold recovery: decisions use the middle sample of each bit and the calibrated nominal midpoint (P0+P1)/2. This intentionally isolates dispersion and noise effects. There is no fiber loss term because received power is the controlled sweep variable.

Noise is independent Gaussian electrical receiver noise in mW, after the bandwidth filter. The default standard deviation is 0.0015 mW per sample. Negative noisy samples are allowed, just as a noisy calibrated electrical reading can cross zero. The additive noise has no shot-noise or intensity-dependent component. Each power point resets the RNG to the configured seed, giving common random numbers. Repeated seeds are reproducible trials, not independent repetitions; use different seeds for independent noise realizations.

## BERT and receiver sensitivity

Measured BER = count(reference != received) / bit_count. The confidence bound is the exact one-sided 95% Clopper-Pearson bound: Beta^-1(0.95; errors+1, bits-errors), or 1 if every bit is wrong. At zero errors it is 1 - 0.05^(1/bits), about 3/bits. This describes uncertainty from this finite synthetic capture under the model, not calibration or field reliability.

For sensitivity I sort by increasing power, take the maximum upper bound over each point and all stronger points, and locate the first point whose envelope is at or below the requested target. This prevents a single lucky dip followed by failures from becoming a sensitivity claim. If adjacent points bracket the target, I interpolate linearly in log10(bound) versus dBm. This is an estimate between tested points, not an extra measurement. `first_passing_dbm` remains the discrete measured result. I never extrapolate outside the sweep. With the default 32,768 bits, even zero errors cannot establish BER below about 9.14e-5.

## Eye

I split the acquired trace into known bit periods and group samples by transmitted reference level. At the bit-center decision phase, eye height is mu1 - mu0 - 3(sigma1 + sigma0), in mW. A negative result is retained to expose a closed eye. Extinction ratio is 10 log10(mu1/mu0), using linear optical-equivalent intensity means; it is undefined if either mean is nonpositive. No correction hides noisy low-level estimates.

The eye analyzer estimates its midpoint from the acquired level means. This differs from the nominal calibrated midpoint used for BERT decisions; eye width describes the measured opening rather than the fixed receiver threshold margin.

Eye width here is the contiguous interval around the bit center where both three-sigma level envelopes clear the center decision threshold: mu0(t)+3sigma0(t) < threshold < mu1(t)-3sigma1(t). I interpolate the margin's zero crossings between phase bins. For an entirely open, ideal rectangular eye, bin edges give exactly one unit interval (UI), meaning one bit period. Width is zero when the center is closed; width_ps = width_UI * 1000 / bit_rate_Gbps. This threshold-envelope width is a documented proxy, not the crossing-jitter algorithm used by every commercial DCA. The plot shows two-UI windows; the eye measurements use all complete bits rather than the 400-window plotting subset.

These definitions are informed by the [Ansys optical eye measurement definitions](https://optics.ansys.com/hc/en-us/articles/360036107074-Eye-Diagram-EYE-INTERCONNECT-Element) and [Keysight's explanation of eye measurements](https://helpfiles.keysight.com/csg/N1930xB/Analyzing/Analyzing_Data_using_Eye_Diagrams.html). They are educational measurements, not standards conformance tests.

## OSA

The separate laser spectrum has a Gaussian main peak at 1550 nm, 0.08 nm full width at half maximum (FWHM), two weaker Gaussian modes at +/-0.8 nm, and a constant floor. Its nominal side-mode suppression is 30 dB. The OSA applies the received-power offset to each trace, preserving its shape. Powers represent spectral sample readings; there is no integration over a calibrated resolution bandwidth.

The analyzer finds the strongest sampled peak, converts relative dBm samples back to linear power, and interpolates the two half-power crossings around that peak. It reports their separation in nm. It rejects a trace that does not bracket both crossings. Side modes are resolved local peaks with at least 3 dB prominence outside the main FWHM; SMSR is main-peak dBm minus the strongest such peak's dBm. A missing resolved side mode produces an undefined result. The floor is not subtracted. This is an apparent sampled width, with no instrument line-shape deconvolution or intrinsic linewidth claim. [Yokogawa describes these OSA spectral measurements and their role](https://tmi.yokogawa.com/bx/library/resources/fundamentals/optical-spectrum-analyzer-or-optical-wavelength-meter-which-is-best-for-your-application/).

## SCPI-style interface

| Resource | Write | Query |
| --- | --- | --- |
| `SIM::ATT` | `:POW <received dBm>` | `:POW?` |
| `SIM::BERT` | `:INIT` | `:FETC:BER?` (JSON counts and bound) |
| `SIM::DCA` | none | `:WAV:DATA?` (JSON reference, waveform, decisions and threshold) |
| `SIM::OSA` | none | `:TRAC:DATA?` (JSON wavelength and dBm arrays) |
| all | none | `*IDN?` |

The resource manager owns the shared bench. Changing power invalidates the existing capture, and BERT initialization creates a new one; DCA refuses stale or absent data. Each resource checks its command set. A context manager closes all owned resources on success or failure. No VISA driver, network connection or background server is required.

The clients accept a `Resource` protocol matching PyVISA's write/query/close shape; a VISA backend would need vendor-specific SCPI translation and response parsing, plus timeouts and instrument configuration. Installing the optional `visa` extra alone does not connect or validate real equipment. The built-in CLI intentionally supports simulation only.

## Output and recovery

A new output directory is mandatory. Each point saves a gzip CSV waveform (reference bit, decision bit, then all samples for that bit), a spectrum CSV, and updated measurement tables. Full-trace CSV values use ten significant digits; metadata records how to recover sample times and the configuration needed to reproduce the unrounded arrays. The gzip container timestamp may differ between runs; decoded numerical CSV tables are reproducible. Public examples contain no private input data.

`metadata.json` starts with status `running` and is updated to `complete` or `failed`. After an exception, completed point files stay available for inspection; the partial run is marked failed and the command log is saved when the output device remains writable. A hard process kill or unavailable disk may leave status `running`. An incomplete run is never a completed result. Plot figures are closed in a finally block. No server or browser process is created.
