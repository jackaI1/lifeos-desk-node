# three-phase-fault-analysis

I built a short-circuit calculator to learn how the underlying idea works. This is a learning project.

## Try a study

With Python 3.11 or newer, run these commands from the downloaded repository:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
three-phase-fault examples/feeder.json --bus workshop \
  --pickup-a 500 --time-dial 0.1 --max-time-s 1 \
  --plots output --output output/report.json
```

Open `output/report.json` for the numbers and the eight PNG files in `output/` for the plots. The sample is a supply feeding a plant and a workshop. Change the impedances, which describe how much each connection limits current, in [examples/feeder.json](examples/feeder.json) and run it again.

The report covers four faults. Currents below are amperes RMS, a measure of the effective alternating current, rounded to the nearest ampere:

| Short circuit at the workshop | Wire a | Wire b | Wire c |
| --- | ---: | ---: | ---: |
| All three wires (`3ph`) | 2527 | 2527 | 2527 |
| Wire a to ground (`lg`) | 1661 | 0 | 0 |
| Wires b to c (`ll`) | 0 | 2189 | 2189 |
| Wires b and c together to ground (`llg`) | 0 | 2288 | 2261 |

For just one fault, add `--fault lg`. Add `--zf 0.02 0.01` to include resistance and reactance at the fault, in that order. Use `python -m three_phase_fault --help` for all options.

## Study an industrial feeder

I also wanted to see how a plant's normal demand and a short circuit affect its cables and switchgear. This example models a utility supply, transformer, motor loads, cables and an isolated standby generator. It uses pandapower, an open-source analogue to ETAP, to calculate normal voltages and three-phase short-circuit currents. A load flow estimates the voltage and current while the equipment is running; a short-circuit study estimates the current when wires are accidentally connected together.

```sh
python -m three_phase_fault.industrial --output output/industrial
```

Open `output/industrial/one-line.png` for the simplified connection diagram and `report.json` for voltages, cable and transformer loading, fault currents and warnings. The deliberately undersized example flags two low-voltage buses, an overloaded cable and a breaker whose interrupting rating is too low. [Industrial study notes](docs/industrial-study.md) explain the assumptions and two hand checks. The generator is isolated and motor fault contributions are excluded, so this is a learning example, not a design for installation.

## What I calculate

I use **per-unit values**, meaning quantities divided by a shared reference rating, to keep the network calculations consistent. The program converts the answer back to amperes using the power and voltage ratings in the input.

For unbalanced faults I use **symmetrical components**: three simpler patterns whose sum recreates the original currents. Positive sequence follows the normal phase order, negative sequence runs in reverse, and zero sequence moves all three together. I solve a separate network for each pattern, connect their equations at the fault, then convert back to the three wires.

The relay has a **pickup**, the current threshold it must exceed, and a **time dial**, a multiplier for its trip delay. I use the IEC standard-inverse curve, which trips faster as current rises. The report gives each phase's pickup status, trip time, and largest dial that meets the requested deadline. `--relay-source breaker_B` checks the current through that supply path rather than the combined current from every source:

```sh
three-phase-fault examples/kirtley.json --bus fault --fault llg \
  --pickup-a 1000 --relay-source breaker_B --output output/breaker.json
```

## Use the Python package

```python
from three_phase_fault import load_network, solve_fault, phase_to_sequence

network = load_network("examples/feeder.json")
fault = solve_fault(network, "workshop", "lg")
print(abs(fault.phase_current_a))
print(phase_to_sequence(fault.phase_current_pu))  # zero, positive, negative
```

[Model and input guide](docs/model.md) explains the JSON fields, units, assumptions and equations. [Validation notes](docs/validation.md) records the published reference, hand calculations and tolerances.

## Tests and limits

There are 4 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `three-phase-fault-analysis-ci.yml`.
