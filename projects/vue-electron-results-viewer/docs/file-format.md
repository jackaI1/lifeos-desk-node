# Test-run JSON format

A run is one JSON object. Each channel has its own unit and inclusive limits. Times are elapsed seconds from the start of the run, rather than clock times. The plot spaces points by elapsed time and connects consecutive readings; those connecting lines do not imply extra measured values.

```json
{
  "runId": "Bench 042",
  "startedAt": "2026-01-10T12:00:00Z",
  "channels": [
    {
      "name": "Voltage",
      "unit": "V",
      "lowerLimit": 3.2,
      "upperLimit": 3.4,
      "measurements": [
        { "timeSeconds": 0, "value": 3.1 },
        { "timeSeconds": 10, "value": 3.3 },
        { "timeSeconds": 20, "value": 3.4 }
      ]
    }
  ]
}
```

In this example, 3.1 V is below range. Both 3.3 V and 3.4 V are in range. Values strictly above 3.4 V are above range. Limits apply to every reading in that channel. If limits change during an experiment, split the data into separate runs.

Rules checked before a run reaches the screen:

- Files are UTF-8 JSON, with an optional byte-order mark, and at most 2 MiB (2,097,152 bytes).
- `runId`, channel `name` and `unit` are nonempty strings, at most 120 characters before trimming. Names must be unique after trimming.
- `startedAt` is a real UTC date in `YYYY-MM-DDTHH:mm:ssZ` or `YYYY-MM-DDTHH:mm:ss.sssZ` form. The UI displays it in the computer's local timezone.
- There are 1 to 16 channels, 1 to 2,000 readings per channel, and at most 20,000 readings across the run.
- Limits, times and values are JSON numbers, finite and within ±1,000,000,000,000. Numeric strings are rejected.
- Times are nonnegative and strictly increasing within each channel. Unsorted or duplicate times are rejected rather than silently changed.
- The lower limit must be less than or equal to the upper limit. A constant channel, a single reading, and equal limits are supported.
- Unknown fields are ignored. Only validated fields are sent to the screen.

The synthetic [example](../samples/bench-run.json) contains voltage and temperature channels. Its five flags were deliberately inserted: three voltage readings and two temperature readings. It is not a real experiment or a calibration standard.
