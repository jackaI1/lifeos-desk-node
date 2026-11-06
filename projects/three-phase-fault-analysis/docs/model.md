# Model and input guide

## Input

The input is a JSON object; see `examples/feeder.json` for a complete three-bus network. A bus is a named connection point. A branch connects two buses. A source is a balanced supply behind its internal impedance.

| Field | Meaning |
| --- | --- |
| `base_mva` | Positive three-phase apparent-power reference in MVA |
| `base_kv_ll` | Positive line-to-line voltage reference in kV, shared by all buses |
| `frequency_hz` | Positive frequency; defaults to 60 Hz |
| `prefault_voltage` | Positive-sequence phase voltage in per unit as `[real, imaginary]`; defaults to `[1, 0]` |
| `buses` | Array of unique, nonempty names |
| `sources` | Nonempty array of `{name, bus, z0, z1, z2}` |
| `branches` | Array of `{name, from_bus, to_bus, z0, z1, z2}`; defaults to empty |

Each impedance is `[R, X]`, representing `R + jX` per unit. All impedances must be finite, nonzero and passive, with R and X at least zero. Only `z0` may be `null`, which means the path blocks zero-sequence current. Include any source neutral grounding impedance as `3 Zn` in `z0`. Element names must be unique across both sources and branches. Unknown fields and missing element fields are rejected. Each bus must have a path to a source in the positive and negative networks.

The current base in amperes is `1000 * base_mva / (sqrt(3) * base_kv_ll)`. The impedance base in ohms is `base_kv_ll**2 / base_mva`. Divide a physical impedance by that base to enter it. Phase voltage uses the line-to-neutral base, `base_kv_ll / sqrt(3)`; current and voltage phasors are RMS throughout.

All sources have the same prefault positive-sequence internal voltage. Loads and shunts are omitted, so the prefault voltage is identical at every bus. Meshed networks, multiple equal-voltage sources, and separately supplied islands are supported. There are no ideal zero-impedance branches, voltage-ratio changes, transformer phase shifts, or mutual sequence coupling. A transformer may be represented only by an already reduced same-base equivalent consistent with these restrictions.

## Sequence networks and fault equations

With `a = exp(j 2 pi / 3)`, the conversion is:

```text
[Ia]   [1  1    1 ] [I0]
[Ib] = [1  a^2  a ] [I1]
[Ic]   [1  a    a^2] [I2]
```

The inverse is the conjugate transpose of this matrix divided by three. All public arrays use phase order `[a,b,c]` or sequence order `[0,1,2]`.

For each sequence the program assembles a nodal admittance matrix, using branch admittances `1/Z` and source admittances to the reference. Solving `Y z = e_fault` gives the fault column of the bus impedance matrix without inverting the whole matrix. The driving-point value is its entry at the fault bus. For a grounded sequence, `Vk = Ek - Zk Ik`; only `E1` is nonzero. The solver combines those relations with three physical boundary conditions in a six-unknown complex linear system:

| CLI name | Fault definition | Conditions at the fault |
| --- | --- | --- |
| `3ph` | Three equal phase fault impedances | `Va=Zf Ia`, `Vb=Zf Ib`, `Vc=Zf Ic` |
| `lg` | Phase a to ground | `Ib=Ic=0`, `Va=Zf Ia` |
| `ll` | b to c through one total impedance | `Ia=0`, `Ib=-Ic`, `Vb-Vc=Zf Ib` |
| `llg` | b and c shorted together, then one shared impedance to ground | `Ia=0`, `Vb=Vc=Zf (Ib+Ic)` |

`--zf R X` is per unit and defaults to zero, called a bolted fault. For LLG it is the common ground impedance, not two independent impedances in the two wires.

An ungrounded zero-sequence component imposes `I0=0` rather than using an arbitrary large impedance. The fault equations determine its neutral displacement. For an ungrounded LL fault the neutral reference is arbitrary, so I choose its prefault reference. With no capacitance, an isolated single ground fault carries zero current; this does not model real capacitive ground current.

Bus voltages follow from the fault column. Source currents flow toward the network; branch currents flow from `from_bus` to `to_bus`. Branch and source currents in the report are per unit; multiply by `base_current_a_rms` for amperes. Fault currents flow from the network into the fault. Residual current is `Ia+Ib+Ic = 3 I0` in amperes.

## Relay and output

Without `--relay-source`, pickup is checked against each phase of total fault current. With that option, it uses a named source's individual contribution, important when multiple supplies feed a fault. It models phase overcurrent only. Source names come from the input JSON; residual current is reported separately, not used as a ground-relay measurement.

I use the standard-inverse equation in [SEL's PowerSystemProtection manual, Table 1, C1](https://selinc.com/api/download/120078/id/128502/0/):

```text
M = abs(I_primary_rms) / pickup_a
t = time_dial * 0.14 / (M**0.02 - 1)    for M > 1
maximum_time_dial = max_time_s * (M**0.02 - 1) / 0.14
```

At or below pickup, trip time and maximum dial are JSON `null`, and the deadline is not met. For 1000 A, pickup 100 A and dial 0.1, the delay is 0.2970598624 s. Doubling the dial doubles the delay. This ideal curve does not model device limits, reset history, saturation or breaker operation.

Every phasor has real, imaginary, magnitude and angle-in-degrees fields. `sequence_current_pu_012` is the fault-point current, while `source_current_pu` is each source's contribution. A CLI error writes a message to stderr and exits with code 2. A successful report exits 0 even when a relay misses its deadline, since that is a study result.

`--plots output` writes two PNGs per fault, closing each figure after writing it. Waveforms are `sqrt(2) Re(I exp(j 2 pi f t))`, showing three steady-state cycles. They do not predict transient peaks. Reusing the same output directory overwrites plots with the same fault name.
