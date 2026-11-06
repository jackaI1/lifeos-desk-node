# Reference values and independent checks

I use published worked values rather than treating agreement between my own functions as a reference measurement.

## Primary sources

1. National Bureau of Standards, *Radio Instruments and Measurements*, Circular 74, issued March 23, 1918. [Full public-domain scan](https://nvlpubs.nist.gov/nistpubs/Legacy/circ/nbscircular74.pdf). Page numbers below are the printed book pages, not PDF indices.
   - pp. 252-254, formulas (153), (155) and the first worked round-wire coil: 400 turns, mean radius 10 cm, pitch 0.1 cm, bare diameter 0.05 cm. The book gives **12,919 µH** for the current sheet and **12,909 µH** after the round-wire correction. Tests use relative tolerances of 0.01% and 0.02% respectively, allowing rounding in the printed coefficient.
   - pp. 259-260, worked multilayer coil: 10 layers of 100 turns, mean radius 10 cm, length 10 cm, winding depth 1 cm, pitch 0.1 cm. The corrected published value is **195.2 mH**. Bare diameter is not specified: I assume 0.9 mm conductor inside a 1 mm pitch. The layer centres span 9 mm and the wire envelope is 9.9 mm, so this is a comparison within **0.5%**, not an exact reproduction of an unspecified wire construction. The continuous-sheet result is 195.412 mH and the filament result is 195.321 mH.
   - p. 283, Table 10: Nagaoka coefficients for diameter/length ratios 0.05, 0.1, 0.5, 1, 2, 4, 10 and 50. Each is checked within 0.000051, reflecting the table's four-decimal rounding.
   - pp. 251-252: the low-frequency circular-loop and single-layer coil formulas underlying the loop self term and continuous-sheet model.
2. Harold A. Wheeler, “Simple Inductance Formulas for Radio Coils,” *Proceedings of the IRE*, vol. 16, no. 10, October 1928, pp. 1398-1400. [Original issue scan](https://www.worldradiohistory.com/Archive-IRE/20s/IRE-1928-10.pdf), formulas (1) and (2). Tests independently substitute inch dimensions, then check the SI conversion. The stated accuracy regions are reported as assumptions, not guaranteed for all geometry.
3. E. B. Rosa and F. W. Grover, *Formulas and Tables for the Calculation of Mutual and Self-Inductance*, *Bulletin of the Bureau of Standards* 8, 1912, pp. 1-237. [Original paper](https://nvlpubs.nist.gov/nistpubs/bulletin/08/nbsbulletinv8n1p1_A2b.pdf), circular-filament mutual inductance and current-sheet solenoid formulas. Circular 74 points to p. 224 for Nagaoka's coefficient and pp. 197-199 for round-wire correction tables. The code uses the elliptic-integral parameter `m`, equal to the square of the modulus used in older notation.

## Checks that do not reuse the same formula

- A direct angular Neumann integral checks one loop-pair result without calling elliptic integrals. It catches parameter/modulus and factor-of-two errors.
- The magnetic-dipole far-field limit checks very distant loops, where subtracting the elliptic terms directly loses precision.
- A nine-turn, three-layer explicit all-pairs sum checks the optimized separation grouping.
- Scaling every length by two must scale inductance by two.
- A dense winding approaches the continuous sheet, while a sparse winding produces an explicit model warning.
- A hand-calculated 10 kV, 100 MVA, 50 Hz circuit with source `j0.1 pu` and added `j0.1 pu` halves fault current from 57.735 kA to 28.868 kA. A resistive-source case catches treating complex impedance as a simple scalar sum.

These are analytical and historical reference checks. I have not measured a physical winding.
