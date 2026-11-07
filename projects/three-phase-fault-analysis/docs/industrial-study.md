# Industrial feeder study

This synthetic example is a utility-fed 11 kV supply, a 1 MVA 11/0.4 kV transformer, two radial cables and two constant-power motor groups. A 0.5 MVA standby generator is shown isolated: this study does not simulate transfer, islanded operation, or its fault contribution. The motor loads represent running demand, not motor starting or motor fault-current contributions. All ratings and lengths are illustrative, not equipment selections.

The report uses a balanced AC load flow and maximum initial symmetrical three-phase fault current, with zero fault impedance, using the IEC 60909 equivalent voltage-source method. It checks bus voltages against 0.95 to 1.05 pu, cable and transformer continuous loading against 100%, and each assumed breaker interrupting rating against the calculated fault current. Breaker ratings are 16, 20, 10 and 10 kA in bus order. A violation is a study result, not an automatic equipment design. It does not assess minimum fault current, single-phase faults, protection coordination, cable thermal withstand or actual manufacturer ratings.

## Independent hand checks

Refer impedances to the 0.4 kV side. For the utility, the 250 MVA short-circuit level and R/X = 0.1 give |Z| = 1.1 × 0.4² / 250 = 0.000704 ohm. Split this into R and X using R/X. The transformer has Z base = 0.4² / 1 = 0.16 ohm, r = 0.01 pu and x = sqrt(0.06² - 0.01²) = 0.05916 pu. For the IEC maximum case, multiply its impedance by K = 0.95 × 1.1 / (1 + 0.6 × 0.05916) = 1.009. Then use I = 1.1 × 0.4 / (sqrt(3) × |Z total|) kA.

| Fault location | Additional impedance | Hand result | pandapower |
| --- | --- | ---: | ---: |
| Main switchboard | none | 24.448457 kA | 24.448457 kA |
| Motor control centre | 0.12 × (0.124 + j0.08) ohm cable | 9.824932 kA | 9.824932 kA |

The main-switchboard comparison checks the utility impedance referred to 400 V and the IEC transformer correction. The motor-control-centre comparison also checks the added cable resistance and reactance. Both results agree to the six decimal places shown; the automated tests evaluate these expressions independently and require agreement within 0.2%. These checks validate the maximum three-phase fault currents for this utility-fed example, not the load-flow results, motor contributions or generator operation. The [pandapower short-circuit documentation](https://pandapower.readthedocs.io/en/stable/shortcircuit/run.html) describes the method and [transformer correction](https://github.com/e2nIEE/pandapower/blob/develop/doc/shortcircuit/branch_elements.rst). Actual studies need verified equipment data, motor contributions and an engineer's review.
