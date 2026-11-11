# Desk node anomaly check

I built a small anomaly check for the desk node's temperature and humidity because I want the board to notice a bad reading itself, instead of filling my room log with a sensor spike or a stuck value. The check runs on the device with no network, so it still works when the upload is down.

It learns what a normal five-minute reading looks like from a log, then flags a window of four readings when it does not look like the others. A window that looks wrong gets a high score. The score is how far the model's guess is from what the sensor actually reported.

## What it found

These numbers come from [docs/results.md](docs/results.md), made by `python -m anomaly_int8 run`. The test set is the last 15 % of the log, which I never used for training or for picking the threshold.

| | Float model (PyTorch) | Int8 model (C integer code) |
|---|---|---|
| Accuracy on the test windows | 0.968 | 0.968 |
| Decisions that agree | | 99.56 % |
| Memory for the weights | 592 bytes | 223 bytes |

The int8 model gives the same accuracy as the float model on this test, and it uses about a third of the memory. Caught faults: spikes, humidity jumps and dropouts, all 100 %. Stuck readings, where the sensor repeats its last value for four samples, are missed (0 %), because four identical readings look like a calm room. The report says so too.

The log is simulated. The committed file is made by `python -m anomaly_int8 make-log` with known faults in it, so I can measure the detector. It is not a real recording. Once I have a real export from the adapter database, I can train on it with `--log`.

## How to run it

From this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.9.1   # CPU build, smaller download
python -m pip install -r requirements.txt

python -m pytest                       # all checks, including the C routine (needs a C compiler)
python -m anomaly_int8 run             # train, quantize, write the C headers and the report
python -m anomaly_int8 make-log        # rewrite the simulated log
python -m anomaly_int8 run --log my_export.csv   # train on your own CSV
```

The CSV has the same columns the room analysis tool reads: `timestamp`, `temperature_mc` (milli-degrees C) and `humidity_mpermil` (thousandths of a percent). The `anomaly` column is only for my simulated log.

## How it works

Each window has four temperatures and four humidities, all from the last 20 minutes. The model is a small autoencoder, which means a network that tries to copy its input through a narrow middle layer. It is trained only on normal windows. Normal windows copy well and odd ones do not, so the copy error is the anomaly score.

For the ESP32, the model is turned into integers, called int8 quantization. Each number is stored as one byte with a scale and a zero point, so a stored value `q` means `scale × (q − zero point)`. The C code in [c/anomaly_int8.c](c/anomaly_int8.c) only uses integer multiply, add and shift. Readings in 0.1 °C and 0.5 %RH steps go in, a score comes out, and the device compares it with a threshold.

The scale and zero point for each layer are in [docs/results.md](docs/results.md). The integer rules are written out in [anomaly_int8/quant.py](anomaly_int8/quant.py), and the Python version is the reference that the C test checks against 135 vectors, including rounding edge cases and sensor limits.

## What is in this folder

- `anomaly_int8/`: the Python package. `data.py` reads and makes logs, `model.py` is the PyTorch autoencoder, `quant.py` does the int8 quantization and the integer reference, `export.py` writes the C headers and the report, and `pipeline.py` runs everything.
- `c/`: the C routine, the generated model and test vectors, and a `Makefile`.
- `data/desk_room_log.csv`: the simulated log.
- `docs/results.md` and `build/results.json`: the comparison.
- `tests/`: 23 checks for the data, the quantization and the full pipeline.

## Tests and CI

The GitHub Actions workflow `.github/workflows/anomaly-int8.yml` installs the CPU build of PyTorch, runs all the tests on Ubuntu, and compiles the C routine with warnings as errors. The C test uses `-std=c11 -Wall -Wextra -Werror -pedantic`.

## Limits

- Four readings is a short window. A slow drift, or a stuck sensor, does not show up.
- The model learned a simulated room. Real rooms, the real sensor noise and the screen's effect on the board's temperature may differ.
- The int8 model saturates at ±12.7 °C from 22 °C and ±63.5 %RH from 45 %RH. A value beyond that is still flagged, but its size is capped.
- I have not run the C code on the ESP32 yet. The C test runs on my computer and in CI.
