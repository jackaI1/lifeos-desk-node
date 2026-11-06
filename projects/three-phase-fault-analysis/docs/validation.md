# Validation notes

## Published reference

I use J. L. Kirtley Jr., *Introduction to Symmetrical Components*, MIT 6.061 class notes, chapter 4, section 7.4, printed pages 12-17: [original MIT PDF](https://ocw.mit.edu/courses/6-061-introduction-to-electric-power-systems-spring-2011/7603169f5d8514b769a46fa900b79a57_MIT6_061S11_ch4.pdf). This is one published network with four worked fault cases. I compare breaker B's contribution, not the combined fault current.

`examples/kirtley.json` reduces the two supply paths to their terminal equivalents. The left path has `Z1=Z2=j(0.1+0.05)=j0.15`, `Z0=j(0.1+0.1)=j0.2`. The right path has `Z1=Z2=j(0.1+0.02)=j0.12` and an open zero path. Both internal positive-sequence voltages are 1 pu; the base is 100 MVA, 138 kV line-to-line. This preserves the fault and breaker currents, but does not expose internal transformer or line buses.

The published breaker sequence answers, reordered here as zero, positive, negative, are:

| Fault | I0 at B (pu) | I1 at B (pu) | I2 at B (pu) |
| --- | --- | --- | --- |
| Three-phase | 0 | -j6.67 | 0 |
| a-ground | -j3.00 | -j1.33 | -j1.33 |
| b-c | 0 | -j3.33 | +j3.33 |
| b-c-ground | +j2.14 | -j3.81 | +j2.86 |

`test_textbook_breaker_sequence_answers` checks these independently entered, rounded answers with absolute tolerance 0.005 pu and zero relative tolerance.

## Independent reconstruction and a reference discrepancy

Using exact arithmetic on those network impedances, I obtain these phase currents at B:

| Fault | Ia (pu) | Ib (pu) | Ic (pu) |
| --- | --- | --- | --- |
| Three-phase | -j6.6666666667 | -5.7735026919+j3.3333333333 | +5.7735026919+j3.3333333333 |
| a-ground | -j5.6666666667 | -j1.6666666667 | -j1.6666666667 |
| b-c | 0 | -5.7735026919 | +5.7735026919 |
| b-c-ground | +j1.1904761905 | -5.7735026919+j2.6190476190 | +5.7735026919+j2.6190476190 |

For example, the parallel positive impedance is `j/15`. For LLG the total positive current is `-j60/7`. The breaker carries 4/9 of that, so `I1B=-j80/21`. The negative breaker current is `I2B=+j20/7`, and `I0B=+j15/7`. Inserting these into `Ib=I0+a^2 I1+a I2` gives `Ib=-10/sqrt(3)+j55/21` and magnitude about 6.3398 pu. The source's later LLG phase table instead gives 6.43 pu; its earlier sequence values agree with my calculation. I keep the sequence checks and test the reconstructed phase answer at 1e-9 pu rather than forcing agreement with that inconsistent final table.

## Checks independent of the matrix solver

Let `E` be the prefault positive voltage and `Z0,Z1,Z2` be the driving-point sequence impedances. The tests also evaluate scalar formulas, over 20 deterministic random passive impedance cases for each fault:

```text
3ph: I0=I2=0; I1=E/(Z1+Zf)
LG:  I0=I1=I2=E/(Z0+Z1+Z2+3Zf)
LL:  I0=0; I1=E/(Z1+Z2+Zf); I2=-I1
LLG: D=Z2+Z0+3Zf
     I1=E/(Z1+Z2*(Z0+3Zf)/D)
     I0=-I1*Z2/D; I2=-I1*(Z0+3Zf)/D
```

These are a separate implementation from the six-unknown boundary solver. Additional tests enforce the actual phase fault conditions, with zero and finite complex fault impedance, and check current conservation at every bus in a grounded mesh with two sources. They also check reversed branch orientation, isolated networks and completely open ground-return paths.

Other tests cover known positive/negative/zero transforms, 100 seeded transform round trips and the associated norm identity, ampere conversion, relay pickup boundaries and numeric timing, malformed inputs, steady-state waveform RMS and frequency, command-line subprocess use, eight valid PNG outputs and figure cleanup.

## Reproduce

```sh
python -m pip install -e '.[test]'
pytest --cov=three_phase_fault --cov-report=term-missing --cov-fail-under=90
ruff check .
ruff format --check .
three-phase-fault examples/kirtley.json --bus fault --pickup-a 1000 \
  --relay-source breaker_B --output output/kirtley.json
```

The suite has 84 test cases. CI runs the same suite and a complete example study on Python 3.11, 3.12 and 3.13. Published rounding tolerance is intentionally looser than the 1e-12 pu circuit-law and scalar-formula checks. Tests establish this model's internal and reference agreement, not suitability for designing live protection systems.
