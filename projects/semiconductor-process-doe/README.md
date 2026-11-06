# semiconductor-process-doe

I built a tool for exploring how thin layers grow on silicon to learn how the underlying idea works. This is a learning project.

## How the oxide grows

Heating silicon in oxygen or steam forms silicon dioxide. As the layer gets thicker, the oxidant must travel farther through it, slowing growth. The Deal-Grove model represents both the surface reaction and this transport. It predicts thickness from time, the initial oxide, and two rate constants. The fit adjusts those constants to reduce squared differences between predicted and measured thickness.

The included six measurements are wet oxidation at 1050 °C, from the source and door positions in the [Oregon State University experimental dataset](https://github.com/IsaiahB14/Wet-Silicon-Oxidation--Thin-Films/blob/main/data/osu_oxidation_clean_dataset.csv). The source describes its furnace and data in its [README](https://github.com/IsaiahB14/Wet-Silicon-Oxidation--Thin-Films). I retained the reported times, native oxide and final thickness, excluding broken or invalid wafers. Position and loading/unloading effects are not modelled, so these observations are not independent replicates of identical conditions. They span roughly 13 to 44 minutes; avoid extrapolation.

## How I compare recipes

A designed experiment varies power, pressure and gas flow in a planned way. I start with a four-run half fraction, where some effects are tied together, and add its foldover to separate main effects from two-factor interactions. I replicate both halves, add six axial and four center runs for curvature, and randomize the 26 runs. The simulated responses include a linear run-to-run drift and independent Gaussian measurement noise: rate standard deviation 2 nm/min and uniformity standard deviation 0.25 percentage points. Uniformity is represented as 100 minus the within-wafer relative spread, in percent. Both process models and their coefficients are illustrative, not calibrated equipment recipes.

Least squares fits a quadratic response surface, including interactions and a run-order term. The printed analysis of variance (ANOVA) uses partial F tests: each term is compared with a model that omits it, with residual error from the full model. A main or interaction effect is twice its coded coefficient. The optimiser searches within the studied ranges for a target rate while requiring predicted uniformity of at least 93%; its prediction uses the middle of the run-order range. Surface plots hold flow at the chosen value. Confirm any suggested settings with real wafers and a new experiment.

## Model details and limitations

For thickness x and time t, the model is `x² + A x = B t + x0² + A x0`, with `A = B / (B/A)`. The parabolic constant B has units µm²/hour and the linear constant B/A has units µm/hour. The fit uses nonlinear least squares in thickness, and reports approximate 95% Student-t intervals from the local covariance matrix. These intervals assume independent, constant-variance errors and a well-identified model. With only six measurements at three times and pooled wafer positions, the included data do not identify B reliably: the fit approaches the linear-growth limit and its symmetric interval can extend below zero despite positive fitting bounds. Treat that interval as a warning, not a physical range; more times, especially thicker oxides, and independent runs are needed. Deal-Grove is also less accurate for very thin dry oxides.

The implementation is in `semiconductor_doe/oxidation.py` and `semiconductor_doe/experiment.py`; the command and plots are in `semiconductor_doe/__main__.py`. The three tests recover known oxidation and experiment parameters and check recipe constraints. GitHub Actions installs the package, runs the tests and executes the example on Linux.

## Tests and limits

There are 1 test source files in this copy. That source count does not establish an execution result. This is a source snapshot, and running it on a new machine may need environment-specific setup.



The relocated workflow did not complete successfully within the migration batch. Local test sources remain available.

No project-specific GitHub Actions workflow was retained. The local test sources remain in this folder.
