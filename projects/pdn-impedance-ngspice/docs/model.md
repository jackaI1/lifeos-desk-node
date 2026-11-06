# Circuit assumptions and checks

I chose a synthetic core rail so I could change one cause at a time. These numbers are an example study, not a GPU specification, extracted layout or recommended bill of materials.

## Topology

```text
0.9 V source -- Rvrm -- Lvrm -- board -- Rpath -- Lpath -- die -- load current --> ground
                                |                        |
                         bulk and ceramic             package
                         series R-L-C banks         series R-L-C bank
                                |                        |
                              ground                   ground
```

The capacitors at a node are shunt branches. Each branch is a series resistance, inductance and capacitance. The shared package path stays in the circuit when I remove the package capacitors.

| Quantity | Assumed value | Reason for including it |
|---|---:|---|
| Supply voltage | 0.9 V | Example low-voltage core rail |
| VRM output resistance | 0.25 mΩ | Low-frequency source loss |
| VRM output inductance | 2 nH | Passive source impedance above DC |
| Shared board-to-die resistance | 0.10 mΩ | Distribution loss |
| Shared board-to-die inductance | 0.15 nH | Finite connection inductance |
| Bulk bank | 4 × 330 µF; 12 mΩ ESR; 2 nH ESL each | Large stored charge |
| Ceramic bank | 24 × 12 µF effective; 2 mΩ ESR; 0.6 nH ESL each | Board decoupling closer to the load |
| Package bank | 16 × 1 µF; 3 mΩ ESR; 0.15 nH ESL each | Local stored charge behind the shared path |
| Load pulse | 20 A to 60 A, 100 ns rise and fall | A repeatable rapid change |
| Timing | Starts at 20 µs, holds high for 40 µs after rising, stops at 100 µs | Includes both edges and recovery |
| Allowed incremental dip | 45 mV | A deliberately demanding example budget |

Ceramic capacitance represents a nominal 22 µF part reduced to an assumed effective 12 µF under bias. No manufacturer curve is implied. The capacitor counts assume identical independent connections, so shared mounting inductance must be represented separately in the path. The damped comparison changes the package part ESR from 3 mΩ to 60 mΩ without changing anything else; it is a sensitivity experiment, not a selected physical part.

## Frequency calculation

Let ω = 2πf. For a bank of n identical parallel parts:

```text
Zbank = (ESR + jω ESL + 1/(jω C)) / n
Cbank = nC; Rbank = ESR/n; Lbank = ESL/n
Zvrm = Rvrm + jω Lvrm
Zboard = 1 / (1/Zvrm + 1/Zbulk + 1/Zceramic)
Zpath = Rpath + jω Lpath
Zdie = 1 / (1/(Zboard + Zpath) + 1/Zpackage)
```

The implementation permits additional board or die banks by summing their admittances, the reciprocals of impedance. Disabled banks contribute zero admittance. The Python equations use no ngspice result to construct their expected values.

The ideal voltage source is AC ground. A 1 A current source injects into the die, so Vdie / 1 A is Zdie in ohms with the correct sign. The operating load has no incremental conductance because I model it as an independent current sink. It is not a constant-power load.

I use 200 logarithmically spaced points per decade from 1 kHz to 100 MHz. `summary.json` records the worst sampled magnitude, its frequency, all sampled local maxima, and contiguous regions above the target. The actual sampled frequency limits are recorded separately from the requested limits; a logarithmic grid can end up to one interval below the requested stop. Threshold boundaries interpolate magnitude against log10(frequency). A local maximum can be an anti-resonance; a high sweep endpoint is not labeled as one. A finite sweep can miss a narrow peak, so this is a sampled diagnostic, not a continuous-band proof.

The target is ΔVallowed / ΔI = 0.045 / 40 = 0.001125 Ω. It is a conservative flat design guide for this chosen disturbance, not a conversion of one AC peak into an exact time-domain droop.

## Transient and hand estimates

The simulation starts from a DC operating point, not a power-on ramp. Before the pulse, capacitors are open circuits and inductors are shorts:

```text
Vbaseline = 0.9 - 20 × (0.00025 + 0.00010) = 0.893 V
Vhigh-load equilibrium = 0.9 - 60 × 0.00035 = 0.879 V
Incremental resistive loss = 40 × 0.00035 = 14 mV
Package-path L di/dt scale = 0.15 nH × 40 A / 100 ns = 60 mV
```

For the rising edge alone, a linear extra current ramp draws Q = ΔI × trise / 2. If I unrealistically give it access to all 1,624 µF instantly, ΔV = Q/C = 1.23 mV. Using only the 16 µF package bank gives 125 mV. Neither is a bound: real source current, ESR, ESL and phase-dependent energy exchange matter. Their disagreement is the reason to simulate the complete ladder. Each bank's series resonance is 1/(2π√LC); the count does not change that value for identical parallel parts.

Python measures the baseline from samples before 90% of the pulse delay. Droop is that baseline minus the minimum die voltage from the rising edge through recovery, including the falling edge. Nominal drop is the 0.9 V source minus the minimum; it also includes the initial 7 mV DC loss. Overshoot is the maximum voltage above the loaded baseline over that same interval. These quantities and the time of the minimum are separate JSON fields.

## Numerical checks and reproducibility

I set `reltol=1e-5`, `abstol=1e-7 A` and a maximum transient step of 10 ns, ten points across each 100 ns edge. The absolute tolerance is small compared with the 20 to 60 A load. Extremely small absolute tolerance caused the SPARSE solver in ngspice 47 to abort at the pulse edge in this low-impedance network. A zero exit code alone did not reveal that failure, so the runner also rejects abort/error messages, missing or nonfinite data and incomplete analysis coverage.

The tests compare the 10 ns result with a 5 ns result and require incremental droop to agree within 0.2%. Three series RLC cases compare complex values across a sweep. A separate RC circuit checks an exponential step response. The full rail and removed-package variant agree with the independent ladder equation to a relative tolerance of 2e-7. Every generated study checks all three variants against the equation, refusing to publish a report when relative disagreement exceeds 1e-6. DC and recovery tests use absolute voltage tolerances rather than exact waveform snapshots.

The runner uses `ngspice -n -b` so a user's `.spiceinit` cannot change its settings. Each invocation owns a temporary directory, has a 60-second timeout and is reaped synchronously. It launches no server or browser. Plots use a noninteractive renderer and are closed after saving. Error output is limited to the final 4,000 bytes of the simulator log. Simulations and report generation finish in a temporary sibling directory before completed outputs replace previous files, so a failed simulation preserves the last complete study. The saved netlists can also be run independently of Python.

I use the ngspice [manual](https://ngspice.sourceforge.io/docs.html) for AC and transient syntax and the official [control-language tutorial](https://ngspice.sourceforge.io/ngspice-control-language-tutorial.html) for exporting numeric vectors with `wrdata`.

## Limits

The passive source gives a finite DC resistance and inductive high-frequency response. It does not model regulator feedback or switching, output current limits, a real GPU's load spectrum, capacitor tolerances, temperature, mutual inductance, PCB planes or package geometry. A lumped model at 100 MHz is exploratory. The mathematical cross-check verifies the circuit and simulator interface; it does not validate the physical assumptions. I would need measured or extracted component/path data and a regulator model before using these results for a board decision.
