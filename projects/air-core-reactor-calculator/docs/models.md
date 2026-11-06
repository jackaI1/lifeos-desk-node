# What the calculator assumes

I use three ways of estimating the same winding so a unit mistake or a bad approximation is easier to notice. Agreement between them is evidence of consistency, not proof of accuracy against a real coil.

## Geometry and units

The Python API and JSON files use metres and return henries. The web form uses millimetres and displays millihenries. Wheeler's original formulas use inches and microhenries; conversion happens inside that function only.

A `Coil` has a mean **wire-centre radius**, an axial current-sheet length, an integer turn count in each layer, an integer layer count, a bare conductor diameter, and a radial layer pitch. The mean radius is halfway between the first and last layer centres. Every layer has the same number of turns and axial alignment; all currents circulate in the same direction.

For layer index `i` starting at zero:

```
r[i] = mean_radius + (i - (layers-1)/2) * radial_pitch
axial_pitch = length / turns_per_layer
z[j] = (j + 1/2) * axial_pitch
winding_depth = (layers-1)*radial_pitch + wire_diameter
```

The length is `turns_per_layer × pitch`, following Circular 74. If measuring the distance from the first turn centre to the last, add one pitch. Layer pitch includes insulation. The conductor diameter excludes insulation. Gaps between turns/layers are allowed, but overlapping conductors, negative dimensions, fractional turns and nonfinite values are rejected. The circular thin-wire model requires wire radius no more than 10% of the innermost turn radius and warns above 5%.

Individual dimensions and derived layer radii are limited to 1 micrometre through 1 kilometre to bound numerical scale, with at most 2,000 total turns and 20 layers to bound computation. These are software limits, not design ratings.

## Wheeler: quick estimate

For radius `r`, length `l`, radial winding depth `d`, and **total** turn count `N`, dimensions in inches:

```
single layer: L_uH = r² N² / (9r + 10l)
multiple layers: L_uH = 0.8 r² N² / (6r + 9l + 10d)
```

I use the bare wire envelope for winding depth. These are empirical formulas: convenient fitted approximations, not exact field solutions. Wheeler's stated single-layer 1% region is `l > 0.8r`; for multilayer windings the denominator terms should be about equal. The warning uses a factor-of-two difference between those terms as a review heuristic. It is not a validated accuracy boundary. Few turns and wide spacing further reduce confidence.

## Nagaoka: continuous winding with end effects

An ideal infinitely long solenoid has `L0 = μ0 N² πr²/l`. A real finite winding leaks field at its ends. Nagaoka's coefficient `Kn`, between zero and one, corrects for that:

```
m = 4r² / (l² + 4r²)
Kn = 4 / (3π√(1-m)) * [ (1-m)/m K(m) + (2m-1)/m E(m) - √m ]
Lsheet = Kn * L0
```

`K` and `E` are complete elliptic integrals, functions that describe the field of circular currents. Here their argument is the **parameter** `m = k²`, not the modulus `k`. I evaluate the coefficient at 60 decimal digits in a local mpmath context to avoid subtraction errors at extreme aspect ratios. Other calculations use ordinary double precision. `μ0 = 4π × 10⁻⁷ H/m` is the usual engineering approximation for air/vacuum permeability.

For multiple layers I add each layer's exact Nagaoka self-sheet inductance and the continuous mutual inductance of every layer pair. For two different radii:

```
Msheet(a,b) = 2 ∫[0,1] (1-t) Mloop(a,b,l*t) dt
Ltotal = Σ Lsheet_i + 2 n² Σ[i<j] Msheet(r_i,r_j)
```

Here `n` is turns per layer. I substitute `z = |a-b| sinh(u)` and scale the kernel by `μ0√(ab)` before SciPy's adaptive quadrature, with relative tolerance `2e-9` and dimensionless absolute tolerance `1e-20`. This logarithmic spacing resolves coupling concentrated near zero separation even for very long coils. This preserves real radial separation rather than collapsing all turns onto the mean radius. It still smooths out individual wires; it is not a finite-wire correction.

## Filaments: add the circular turns

A filament is an ideal thin current loop. For coaxial loop radii `a,b` and axial separation `z`, Maxwell's expression is:

```
m = 4ab / ((a+b)²+z²)
M = μ0 √(ab) * [ (2-m)K(m) - 2E(m) ] / √m
L = Σ Lself_i + 2 Σ[i<j] Mij
```

The factor of two counts the two directions of each mutual pair. Calling the mutual formula on a turn paired with itself would be singular, so I use the thin round-wire loop expression instead:

```
Lself = μ0 r [ ln(8r / wire_radius) - 2 + 1/4 ]
```

The `1/4` includes internal inductance for uniform low-frequency current. At high frequency, skin effect changes this term and eventually stray capacitance invalidates the simple inductance model. Leads, helical advance, current crowding and proximity effects are omitted.

Near coincident turns, I compute the complementary elliptic parameter from the squared separation directly. For `m < 0.001`, I use the far-field series `π m^(3/2)/16 × (1 + 3m/4 + 75m²/128 + 245m³/512)` for the bracket divided by `√m`, avoiding cancellation. Repeated axial separations are grouped with exact pair counts, reducing work from quadratic in total turns to `O(layers² × turns_per_layer)` and temporary storage to `O(turns_per_layer)`.

## What the checker can tell me

A negative, zero or nonfinite inductance is an error. Positive mutual coupling gives a lower bound for the filament winding of `Σ Lself`. Magnetic energy gives `Mij ≤ √(Lself_i Lself_j)`, so `(Σ √Lself)²` is an upper bound. I allow 2% around these bounds because the wire self model is approximate. The Nagaoka sheet model cannot exceed the infinitely long-solenoid value using the outermost layer radius and total turns.

These are bounds for these models, not universal bounds for every coil construction. More than 10% spread between methods triggers a separate warning. The spread is `(max-min)/max`, not a measured error. A warning calls for reviewing the model, not silently choosing an average.

## Series-reactor circuit

A series reactor is a coil placed in the current path to add inductive reactance, the opposition to alternating current. The example assumes a balanced three-phase bolted fault, an ideal 1 pu prefault voltage and the same coil in every phase. **Per-unit** means a quantity divided by its chosen circuit base.

```
Zbase = V_line-line² / S_three-phase
Ibase = S_three-phase / (√3 V_line-line)
Xreactor_ohm = 2π f Lfilament
Xreactor_pu = Xreactor_ohm / Zbase
Ibefore_pu = 1 / |Rsource_pu + j Xsource_pu|
Iafter_pu = 1 / |Rsource_pu + j (Xsource_pu + Xreactor_pu)|
Iamp = Ipu * Ibase
```

Voltage input is kV, power is MVA and frequency is Hz. I use the three-phase apparent power and line-to-line voltage consistently; kV²/MVA already gives ohms. Source resistance and reactance must be nonnegative, with combined magnitude at least `1e-12 pu`. To bound numerical scale, each circuit input is at most `1e9`; positive voltage, power base and frequency are at least `1e-9` in their input units. These are software limits, not practical design ranges. The circuit rejects negative reactance because capacitive cancellation is outside this example's model.

The result is prospective **symmetrical RMS** fault current, excluding DC offset and transient peaks. There is no breaker selection, load-flow calculation, relay coordination, insulation design, magnetic-force check or thermal rating. A coil that reduces a calculated fault current could still fail mechanically or thermally. This project has no physical validation and is not construction guidance.
