"""Write a compact report plus aligned readings and one-sided spectral densities."""
import csv
import json
from pathlib import Path
import shutil


def _number(value):
    return 'undefined' if value is None else f'{value:.6g}'


def markdown(result, synthetic=False):
    raw, filtered = result['raw_spectrum'], result['filtered_spectrum']
    lines = ['# ' + ('Synthetic room-reading comparison' if synthetic else 'Room-log analysis'), '',
             'I compare the recorded readings with a moving median followed by a low-pass filter.',
             'The median removes isolated spikes; the low-pass keeps slower changes.', '',
             f"Samples: {result['sample_count']}; interval: {_number(1/result['sample_rate_hz'])} s; "
             f"FFT resolution: {_number(result['resolution_hz'])} Hz.",
             f"Median window: {result['median_window']}; low-pass cutoff: {_number(result['cutoff_hz'])} Hz.",
             'The fourth-order Butterworth runs forward and backward: zero phase, amplitude gain 0.5 at cutoff.',
             'This is offline processing. The centered median is nonlinear and also changes the overall response.', '',
             '## Error against supplied true values', '']
    if result['truth'] is None:
        lines.append('Ground-truth comparison unavailable: this log supplies no true values.')
    else:
        lines += ['RMSE is root mean square error, the typical distance from the true reading.',
                  'SNR uses true AC signal power divided by mean squared error; larger is better.',
                  'Every sample, including both ends, is included. Units are ' + result['unit'] + '.', '',
                  '| Reading | RMSE | True-value SNR (dB) |', '| --- | ---: | ---: |']
        for name in ('raw', 'median', 'filtered'):
            lines.append(f"| {name} | {_number(result['truth'][name+'_rmse'])} | "
                         f"{_number(result['truth'][name+'_snr_db'])} |")
    lines += ['', '## Frequency comparison', '',
              'The FFT (fast Fourier transform) separates repeating changes by frequency.',
              'A Hann window softens record boundaries before the FFT. Power density is in unit squared per Hz.',
              f"Band SNR proxy: AC power from >0 to {_number(result['signal_max_hz'])} Hz divided by power above it.",
              'This assumes slow changes are useful and fast changes are noise. It is not a sensor accuracy measurement.', '',
              '| Reading | Band SNR proxy (dB) |', '| --- | ---: |',
              f"| raw | {_number(raw['band_snr_db'])} |",
              f"| filtered | {_number(filtered['band_snr_db'])} |", '',
              'Strongest raw peaks above the chosen signal band (noise candidates):', '',
              '| Frequency (Hz) | Period (s) | Power density |', '| ---: | ---: | ---: |']
    for peak in raw['noise_peaks']:
        lines.append(f"| {_number(peak['frequency_hz'])} | {_number(peak['period_seconds'])} | {_number(peak['psd'])} |")
    if not raw['noise_peaks']:
        lines.append('| none | | |')
    lines += ['', '## Limits', '',
              'Synthetic results test the software, not an assembled sensor. Real fast room changes may be useful.',
              'Frequencies above half the sample rate cannot be identified; five-minute logs cannot reveal mains hum.',
              'Filtering cannot recover aliased noise. Gaps and duplicate timestamps must be cropped before analysis.',
              'Boundary estimates use padding and may be less reliable. Undefined power ratios are null in JSON.',
              'See samples.csv for aligned raw, median and filtered values, and spectrum.csv for every FFT bin.', '']
    return '\n'.join(lines)


def write_report(output, data, result, synthetic=False, manifest=None):
    """Require a new directory so input files and earlier reports cannot be overwritten."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        summary = {key: value for key, value in result.items() if key not in ('median', 'filtered')}
        for name in ('raw_spectrum', 'filtered_spectrum'):
            summary[name] = {k: v for k, v in result[name].items() if k not in ('frequency_hz', 'psd')}
        summary['synthetic'] = synthetic
        (output / 'report.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
        (output / 'report.md').write_text(markdown(result, synthetic))
        with (output / 'samples.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['timestamp', 'raw', 'median', 'filtered', 'true_value'])
            truth = data.truth if data.truth is not None else ['']*len(data.values)
            writer.writerows(zip(data.times, data.values, result['median'], result['filtered'], truth))
        with (output / 'spectrum.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['frequency_hz', 'raw_psd', 'filtered_psd'])
            writer.writerows(zip(result['raw_spectrum']['frequency_hz'],
                                 result['raw_spectrum']['psd'], result['filtered_spectrum']['psd']))
        if manifest is not None:
            (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')
    except Exception:
        shutil.rmtree(output)
        raise
