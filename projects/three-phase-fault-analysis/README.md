# Three-phase fault analysis

I built a short-circuit calculator because I wanted to check my hand calculations when a fault affects only part of a three-phase power supply. Three-phase power uses three alternating currents spaced a third of a cycle apart. A short circuit can disturb one, two or all three of them, so one current value does not tell the whole story.

I give the calculator a small network in a JSON file, choose where the short circuit happens, and get the current in each wire and the remaining voltage at each connection. It also checks whether a simple protection relay would detect the current and how long it would take to trip. The plots show the currents as rotating arrows and as waves over time.

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

## Scope and checks

This is my study tool for small networks. I assume balanced supplies at the same voltage before the fault, ignore load current, and use one voltage base. I support an open ground-return path, but do not model line capacitance, transformer phase shifts, changing machine currents or the DC offset after a fault. The waveform plots reconstruct steady alternating current. The relay timing excludes breaker travel, current-transformer behaviour and coordination with other relays, so this is not a field protection setting tool.

The package separates network assembly, fault equations, component conversion, relay timing and plotting. I check all four fault types against the worked calculations in [J. L. Kirtley's MIT chapter 4, section 7.4](https://ocw.mit.edu/courses/6-061-introduction-to-electric-power-systems-spring-2011/7603169f5d8514b769a46fa900b79a57_MIT6_061S11_ch4.pdf). I document a discrepancy in its final double-line-to-ground phase table rather than copying that answer.

Run the checks with:

```sh
pytest --cov=three_phase_fault --cov-report=term-missing --cov-fail-under=90
ruff check .
ruff format --check .
```

There are 89 tests, including published answers, independent closed-form equations, current conservation, open ground paths, input errors, relay timing and the command-line plots. GitHub Actions runs them on Python 3.11, 3.12 and 3.13 and saves the example report and plots as downloadable artifacts.
