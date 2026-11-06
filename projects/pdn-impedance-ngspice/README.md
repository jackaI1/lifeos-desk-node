# pdn-impedance-ngspice

I built a power-supply simulation to learn how the underlying idea works. This is a learning project.

## What I found

My example allows a 45 mV dip for an extra 40 A. That gives a **1.125 mΩ target impedance**, a guide to how little the supply should resist changes in current. I sweep from 1 kHz to 100 MHz and separately simulate the load pulse.

| Example design | Largest impedance | Load-step droop |
|---|---:|---:|
| Original capacitor banks | 26.60 mΩ | 113.27 mV |
| Package capacitors removed | 109.03 mΩ | 82.76 mV |
| Package capacitor resistance increased | 6.55 mΩ | 89.69 mV |

All three miss the example budget. The original design has a strong peak around **3.02 MHz**. Adding resistance to the package capacitors damps that peak and reduces droop by about **21%**, but it still needs work. Removing those capacitors happens to help this particular pulse while making high-frequency impedance much worse. That is why I check both plots.

![Supply impedance and capacitor comparison](results/reference/impedance.png)

The [saved report](results/reference/report.md) includes the voltage waveform, peak frequencies, failing frequency bands and hand checks. These are synthetic component values, not measurements of a commercial GPU.

## Changing the study

I keep the assumptions in [examples/gpu-core.json](examples/gpu-core.json). Values use volts, amperes, seconds, ohms, henries and farads. For example, `100e-9` seconds means 100 ns. Capacitor values and their losses are **per part**; `count` puts that many identical parts in parallel. A count of zero disables a bank.

```sh
cp examples/gpu-core.json my-rail.json
# Edit step_a, rise_s, bank counts or component values.
uv run pdn-study --config my-rail.json --output results/local
```

Every run compares the original design with two controlled changes: remove the die-side package capacitors, or multiply only their resistance by 20. The output contains the input file, six runnable circuit files, six CSV data files, two plots, `summary.json` and `report.md`. A failed simulation leaves the previous completed output intact. The report labels budget failures without treating an intentionally failing design as a software error.

To inspect a generated circuit directly:

```sh
cd results/local
ngspice -n -b full-ac.cir
# data.dat now contains the simulated frequency, real impedance and imaginary impedance.
```

## What is in the circuit

The voltage regulator module, or VRM, is an ideal supply followed by resistance and inductance. Bulk and ceramic capacitors sit on the board. A shared resistance and inductance connect the board to the processor die, where the package capacitors sit.

Each capacitor includes ESR, its small internal resistance, and ESL, the inductance of its connections. These explain why a capacitor stops behaving like ideal stored charge at high frequencies. I use an effective ceramic capacitance of 12 µF per part to represent assumed loss under DC bias.

For the frequency sweep I inject a 1 A test current at the die, so the measured voltage gives impedance directly. I find local maxima, including anti-resonance peaks caused by interacting capacitor banks and inductances. For the pulse I measure the minimum voltage relative to the already loaded starting voltage, then report the dip and overshoot separately.

My independent Python calculation reduces the same circuit with complex impedances. I compare every sweep point with ngspice and also check the DC voltage drop, individual capacitor resonances, charge storage and inductive voltage scales. The [model notes](docs/model.md) show the equations, component assumptions and numerical settings.

This is a passive, lumped circuit study. It does not include regulator control, switching ripple, extracted PCB geometry or hardware measurements. I would need those before making a claim about an actual board. I used ngspice here; I have not validated this model in SIMetrix or Sigrity.

## Tests and limits

There are 4 test source files in this copy. That source count does not establish an execution result. This is a source snapshot, and running it on a new machine may need environment-specific setup.



Generated output omitted from this copy: results/ (generated output). Regenerate it with the project scripts.

The relocated workflow did not complete successfully within the migration batch. Local test sources remain available.

No project-specific GitHub Actions workflow was retained. The local test sources remain in this folder.
