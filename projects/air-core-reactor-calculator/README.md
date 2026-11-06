# air-core-reactor-calculator

I built a coil calculator to learn how the underlying idea works. This is a learning project.

## Run a saved example

I can also use the command line without opening the page:

```sh
python -m reactor examples/nbs-single-layer.json
python -m reactor examples/nbs-multilayer.json
python -m reactor examples/series-reactor.json
```

The output is JSON. Saved geometry uses **metres**, inductance is in **henries**, and fault current is in **amperes**. I can copy an example and change its dimensions. The installed `air-reactor` command takes the same file argument.

For the 400-turn reference coil, my filament calculation gives **12.90949 mH**, compared with the published **12.909 mH**, a difference of about **0.004%**. That checks this example; it is not an accuracy claim for arbitrary coils. [The reference notes](docs/references.md) identify the book, printed pages, dimensions and test tolerances.

## A coil in a power circuit

The series-reactor example puts one identical coil in each of the three phases of a simplified circuit. Its 100-turn, four-layer geometry gives **2.05275 mH**. On an 11 kV, 10 MVA, 60 Hz circuit with the supplied source impedance, the estimated fault current falls from **5.223 kA to 3.195 kA**, a **38.8% reduction**.

I use per-unit values, which express voltage and impedance relative to a chosen circuit base, so the source and coil can be combined consistently. In the page, **Circuit assumptions** lets me change the voltage, power base, frequency and source impedance.

I calculate symmetrical RMS current, an averaged AC magnitude. I do not calculate the initial current peak, temperature rise, insulation requirements or forces that could tear a coil apart. The example leaves out loads, motor contributions, nearby metal and protection coordination. No physical winding has been measured or rated.

## How I calculate it

I keep the geometry and electromagnetics in `reactor/coils.py`, the physical checks in `reactor/analysis.py`, and the simple power-circuit calculation in `reactor/circuit.py`. The command line and Flask page use those same functions.

Wheeler's original formulas use inches, so I convert internally and return SI units. For Nagaoka I use the finite-length current-sheet formula for each layer, then integrate the magnetic coupling between layers. The filament method adds circular-turn mutual inductances and finite round-wire self terms. Repeated turn separations are grouped to avoid allocating a large turn-by-turn matrix.

The geometry is limited to 2,000 total turns and 20 layers. The models assume coaxial windings, equal turns per layer, the same winding direction and thin round wire. Leads, helical advance, skin and proximity effects, stray capacitance and nearby magnetic materials need a more detailed model. I explain the formulas, numerical choices and bounds in [the model notes](docs/models.md).

## Tests and limits

There are 3 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `air-core-reactor-calculator-ci.yml`.
