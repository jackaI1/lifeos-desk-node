# How I calculate and judge the readings

This bench uses simulated, balanced sinusoidal signals and an ideal numerical reference. Its verdict means only that the simulated unit passes the selected profile. It is not a certification, calibration, complete OIML test programme, or evidence of hands-on hardware testing.

## Test points and limits

My direct-connected simulated rating is Imin = 0.4 A, Itr = 1 A and Imax = 50 A. These are my choices, consistent with the class B current ratios in [OIML R 46:2012, Table 1, printed p.15](https://www.oiml.org/en/files/pdf_r/r046-1-2-e12.pdf#page=15). Imin is the lowest current in this comparison; Itr is where the error band changes; Imax is the top current.

Every row below runs once with one phase and once with three phases, giving 24 checks. PF means power factor. Lagging is inductive; leading is capacitive. Limits are symmetric percentages of reference energy.

| Current (A) | PF | Limit (%) | Point basis | Limit basis |
| ---: | --- | ---: | --- | --- |
| 0.4 | 1 | ±1.5 | [Table 10, Imin](#sources) | [Table 2, low current, unity](#sources) |
| 0.4 | 0.5 lagging | ±1.8 | Additional point in rated range | [Table 2, low current, non-unity](#sources) |
| 0.4 | 0.8 leading | ±1.8 | Additional point in rated range | [Table 2, low current, non-unity](#sources) |
| 1 | 1 | ±1.0 | [Table 10, Itr](#sources) | [Table 2, upper current, unity](#sources) |
| 1 | 0.5 lagging | ±1.5 | [Table 10, Itr](#sources) | [Table 2, upper current, non-unity](#sources) |
| 1 | 0.8 leading | ±1.5 | [Table 10, Itr](#sources) | [Table 2, upper current, non-unity](#sources) |
| 10 | 1 | ±1.0 | [Table 10, my interior choice](#sources) | [Table 2, upper current, unity](#sources) |
| 10 | 0.5 lagging | ±1.5 | [Table 10, my interior choice](#sources) | [Table 2, upper current, non-unity](#sources) |
| 10 | 0.8 leading | ±1.5 | [Table 10, my interior choice](#sources) | [Table 2, upper current, non-unity](#sources) |
| 50 | 1 | ±1.0 | [Table 10, Imax](#sources) | [Table 2, upper current, unity](#sources) |
| 50 | 0.5 lagging | ±1.5 | [Table 10, Imax](#sources) | [Table 2, upper current, non-unity](#sources) |
| 50 | 0.8 leading | ±1.5 | [Table 10, Imax](#sources) | [Table 2, upper current, non-unity](#sources) |

### Sources

- [OIML R 46-1/-2:2012, §3.3.3, Table 2, printed p.17](https://www.oiml.org/en/files/pdf_r/r046-1-2-e12.pdf#page=17) supplies the class B base error bands.
- [The same recommendation, §6.2.1, Table 10, printed p.34](https://www.oiml.org/en/files/pdf_r/r046-1-2-e12.pdf#page=34) supplies the positive-flow point structure. I select 10 A for the interior checks; this is not a national authority selection. I add two low-current PF checks per wiring mode.

The source URL, point basis, exact band and tolerance travel with every CSV measurement and JSON profile row. The code refuses to invent a class B limit outside 0.4 to 50 A or outside the chosen PF range. I cover positive flow only in the acceptance table. Reverse energy is tested as an integrator check, not as a meter approval test.

## Sample-based reference

For phase k, angle θ = 2πft − k·2π/3. I generate:

```text
v[k,n] = sqrt(2) × V_rms × sin(θ)
i[k,n] = sqrt(2) × I_rms × sin(θ − φ)
φ = acos(PF) for lagging; −acos(PF) for leading
E_ref_Wh = sum over k,n of v[k,n] × i[k,n] / sample_rate / 3600
```

I use 120 V RMS from phase to neutral, including three-phase four-wire mode. Each sample represents a whole time cell; there is no repeated endpoint. At 7,200 Hz, 12 cycles at 60 Hz gives 1,440 samples per phase and 0.2 seconds. Integer samples per cycle prevent endpoint leakage. Inputs at or below the Nyquist rate, non-integer cycles, non-finite values and mismatched sample arrays are rejected.

An independent hand check is 120 V × 10 A × 0.2 s / 3600 = 1/15 Wh at PF 1. Three phases give 0.2 Wh. At PF 0.5 these become 1/30 Wh and 0.1 Wh. Another test integrates explicit constant samples, so the reference is not checked only against another sinusoid generator.

## Meter under test

I store a quadrature current, a cosine wave a quarter cycle from the sine, alongside the true current. That lets me apply an exact phase rotation without wrapping or interpolating samples:

```text
i_shifted = i × cos(δ) − i_quadrature × sin(δ)
v_measured = v × (1 + voltage_gain_pct/100) + voltage_offset_v
i_measured = i_shifted × (1 + current_gain_pct/100) + current_offset_a
E_meter = integrate(v_measured × i_measured) + sum(power_offset_w) × duration_s/3600
error_pct = 100 × (E_meter − E_ref) / E_ref
```

A positive phase error adds current lag. Voltage and current gains multiply; a 1% voltage gain and 2% current gain give a 3.02% energy error at PF 1. DC voltage/current offsets produce their product as a power bias over whole cycles; a single DC offset alone cancels. I also model residual active-power bias explicitly, in watts per element. This gives a meaningful low-load error without pretending a lone current offset always changes active energy.

Each unit has three independently sampled channels. Normal distributions are centered at zero, with standard deviations of 0.012% voltage gain, 0.025% current gain, 0.015° phase, 0.002 V voltage offset, 0.00002 A current offset and 0.003 W power bias. These are illustrative process assumptions, not manufacturer data or standard requirements. A single-phase run uses the unit's first channel; a three-phase run uses all three.

The unit index and seed determine each unit independently, so extending a batch preserves its earlier units. The baseline uses a separate seed stream. Production drift adds index × requested drift to each channel, starting at index zero. The report stores every baseline and production meter parameter for inspection.

I compare the full error against its inclusive limit, with only 1e-10 percentage points allowed for floating-point boundary noise. Display rounding never decides a verdict. A zero-energy percentage error is undefined and excluded from this profile.

## Detecting process drift

I fit a separate individuals chart at each of the 24 conditions using a separate undrifted baseline. Following the [NIST/SEMATECH individuals-chart method](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm), I use:

```text
center = mean(baseline errors)
MR_mean = mean(abs(error[j] − error[j−1]))
sigma_estimate = MR_mean / 1.128
lower, upper = center ± 3 × sigma_estimate
```

I freeze these limits before monitoring production. A single reading strictly outside them raises a control alarm, whether or not it fails the published accuracy limit. I do not pool points, fit limits to the drifting production batch, or use the accuracy limits as statistical control limits. At least 10 finite baseline units and nonzero spread are required; the default is 20.

The default example has 960 production comparisons plus 480 baseline comparisons. Unit 2 first raises a control alarm and unit 30 first fails accuracy. The early alarm shows sensitivity in this constructed experiment; it does not establish a false-alarm rate or guarantee warning before failure in other batches. Checking many correlated points increases the chance of an alarm, and real baseline stability must be established before adopting these limits.

## Boundaries of the demonstration

I do not model reference uncertainty, ADC quantization, clock error, harmonics, environmental effects, transformer errors, wiring faults, starting current, no-load creep, pulse/register resolution or the full approval programme. The simulated readings are continuous energy totals over short intervals, not pulses from a physical meter. The numerical integrator supports unbalanced sample arrays and signed energy, but the acceptance sweep uses balanced positive-flow sinusoids. No physical equipment is required or controlled.

For a physical test I would need traceable reference equipment, safe isolated connections, a defined uncertainty budget, sufficient measurement time and the applicable full test procedures. These software results cannot replace that work.
