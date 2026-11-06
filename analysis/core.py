"""Offline, zero-phase filtering and explicitly band-defined spectral estimates."""
from dataclasses import dataclass

import numpy as np
from scipy import ndimage, signal

MAX_SAMPLES = 200_000


@dataclass
class Samples:
    times: np.ndarray
    values: np.ndarray
    truth: np.ndarray | None = None
    unit: str = 'C'


def validate(times, values, truth=None):
    """Return Hz; reject missing time, gaps and >1% cadence jitter, never resample."""
    times, values = np.asarray(times), np.asarray(values)
    if (times.ndim != 1 or values.ndim != 1 or len(times) != len(values)
            or not 32 <= len(times) <= MAX_SAMPLES):
        raise ValueError('expected 32 to 200000 matched, one-dimensional samples')
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(values)):
        raise ValueError('timestamps and readings must be finite')
    if np.any(times <= 0):
        raise ValueError('timestamps must be positive synchronized epoch seconds')
    dt = np.diff(times)
    step = np.median(dt)
    if step <= 0 or np.any(dt <= 0) or not np.allclose(dt, step, rtol=.01, atol=1e-6):
        raise ValueError('timestamps must increase at uniform cadence (1% tolerance); crop gaps')
    if truth is not None:
        truth = np.asarray(truth)
        if truth.shape != values.shape or not np.all(np.isfinite(truth)):
            raise ValueError('true values must be finite and match readings')
    return float(1 / step)


def _values(values):
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) < 32 or len(values) > MAX_SAMPLES or not np.all(np.isfinite(values)):
        raise ValueError('expected 32 to 200000 finite one-dimensional readings')
    return values


def _cutoff(fs, cutoff):
    if not np.isfinite(fs) or fs <= 0 or not np.isfinite(cutoff) or not 0 < cutoff < fs / 2:
        raise ValueError('cutoff must be positive and below Nyquist (half the sample rate)')


def median_filter(values, window=5):
    """Centered odd window, repeat endpoint values at edges; 1 disables this stage."""
    values = _values(values)
    if type(window) is not int or window < 1 or window % 2 == 0 or window > min(101, len(values)):
        raise ValueError('median window must be an odd positive integer <= 101 and <= sample count')
    return ndimage.median_filter(values, size=window, mode='nearest')


def lowpass(values, fs, cutoff_hz):
    """Fourth-order Butterworth per pass, forward/backward; gain=0.5 at cutoff."""
    values = _values(values)
    _cutoff(fs, cutoff_hz)
    if cutoff_hz < fs / len(values):
        raise ValueError('cutoff needs at least one FFT bin; use a longer log')
    sos = signal.butter(4, cutoff_hz, fs=fs, output='sos')
    # Filter deviations, then restore the baseline, preserving constants exactly.
    return signal.sosfiltfilt(sos, values-values[0]) + values[0]


def ratio_db(numerator, denominator):
    # Undefined ratios are JSON null rather than nonstandard +/-Infinity or NaN.
    if numerator <= 0 or denominator <= 0:
        return None
    return float(10 * np.log10(numerator / denominator))


def spectrum(values, fs, signal_max_hz):
    """Hann FFT PSD; SNR proxy = AC power <= band edge / power above it."""
    values = _values(values)
    _cutoff(fs, signal_max_hz)
    # Subtract a nearby reference before the mean to keep a constant decimal
    # record exactly zero, instead of turning mean-roundoff into fake AC power.
    centered = values - values[0]
    frequencies, psd = signal.periodogram(centered, fs=fs, window='hann',
                                          detrend='constant', scaling='density')
    df = fs / len(values)
    if signal_max_hz < df:
        raise ValueError('signal band needs at least one non-DC FFT bin; use a longer log')
    low = (frequencies > 0) & (frequencies <= signal_max_hz)
    high = frequencies > signal_max_hz
    candidates, _ = signal.find_peaks(psd)
    # Include a genuine endpoint maximum at Nyquist (find_peaks skips endpoints).
    if psd[-1] > psd[-2]:
        candidates = np.append(candidates, len(psd)-1)
    candidates = sorted((int(i) for i in candidates if i > 0 and psd[i] > 0),
                        key=lambda i: psd[i], reverse=True)

    def peaks(indices):
        return [{'frequency_hz': float(frequencies[i]), 'period_seconds': float(1/frequencies[i]),
                 'psd': float(psd[i])} for i in indices[:5]]

    low_power, high_power = float(np.sum(psd[low])*df), float(np.sum(psd[high])*df)
    return {'frequency_hz': frequencies, 'psd': psd,
            'peaks': peaks(candidates),
            'noise_peaks': peaks([i for i in candidates if high[i]]),
            'signal_band_power': low_power, 'noise_band_power': high_power,
            'band_snr_db': ratio_db(low_power, high_power)}


def analyze(samples, cutoff_hz, median_window=5, signal_max_hz=None):
    fs = validate(samples.times, samples.values, samples.truth)
    band = cutoff_hz if signal_max_hz is None else signal_max_hz
    median = median_filter(samples.values, median_window)
    filtered = lowpass(median, fs, cutoff_hz)
    result = {'sample_count': len(samples.values), 'sample_rate_hz': fs,
              'resolution_hz': fs/len(samples.values), 'unit': samples.unit,
              'cutoff_hz': cutoff_hz, 'median_window': median_window, 'signal_max_hz': band,
              'median': median, 'filtered': filtered,
              'raw_spectrum': spectrum(samples.values, fs, band),
              'filtered_spectrum': spectrum(filtered, fs, band), 'truth': None}
    if samples.truth is not None:
        centered_truth = samples.truth - samples.truth[0]
        signal_power = float(np.var(centered_truth))
        metrics = {}
        for name, values in [('raw', samples.values), ('median', median), ('filtered', filtered)]:
            error_power = float(np.mean((values-samples.truth)**2))
            metrics[f'{name}_rmse'] = float(np.sqrt(error_power))
            metrics[f'{name}_snr_db'] = ratio_db(signal_power, error_power)
        result['truth'] = metrics
    return result
