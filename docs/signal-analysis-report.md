# Synthetic room-reading comparison

I compare the recorded readings with a moving median followed by a low-pass filter.
The median removes isolated spikes; the low-pass keeps slower changes.

Samples: 2048; interval: 300 s; FFT resolution: 1.6276e-06 Hz.
Median window: 5; low-pass cutoff: 0.000277778 Hz.
The fourth-order Butterworth runs forward and backward: zero phase, amplitude gain 0.5 at cutoff.
This is offline processing. The centered median is nonlinear and also changes the overall response.

## Error against supplied true values

RMSE is root mean square error, the typical distance from the true reading.
SNR uses true AC signal power divided by mean squared error; larger is better.
Every sample, including both ends, is included. Units are C.

| Reading | RMSE | True-value SNR (dB) |
| --- | ---: | ---: |
| raw | 0.523244 | 0.679201 |
| median | 0.196934 | 9.16686 |
| filtered | 0.110919 | 14.1531 |

## Frequency comparison

The FFT (fast Fourier transform) separates repeating changes by frequency.
A Hann window softens record boundaries before the FFT. Power density is in unit squared per Hz.
Band SNR proxy: AC power from >0 to 0.000277778 Hz divided by power above it.
This assumes slow changes are useful and fast changes are noise. It is not a sensor accuracy measurement.

| Reading | Band SNR proxy (dB) |
| --- | ---: |
| raw | 0.881098 |
| filtered | 32.9735 |

Strongest raw peaks above the chosen signal band (noise candidates):

| Frequency (Hz) | Period (s) | Power density |
| ---: | ---: | ---: |
| 0.00111165 | 899.561 | 60781.3 |
| 0.000410156 | 2438.1 | 338.426 |
| 0.000449219 | 2226.09 | 326.383 |
| 0.000426432 | 2345.04 | 279.353 |
| 0.00101888 | 981.47 | 278.941 |

## Limits

Synthetic results test the software, not an assembled sensor. Real fast room changes may be useful.
Frequencies above half the sample rate cannot be identified; five-minute logs cannot reveal mains hum.
Filtering cannot recover aliased noise. Gaps and duplicate timestamps must be cropped before analysis.
Boundary estimates use padding and may be less reliable. Undefined power ratios are null in JSON.
See samples.csv for aligned raw, median and filtered values, and spectrum.csv for every FFT bin.
