"""Measurements on acquired arrays, independent of simulator configuration."""
import numpy as np
from scipy.signal import find_peaks
from scipy.stats import beta


def _bits(values):
    array = np.asarray(values)
    if array.ndim != 1 or not array.size or not np.isin(array, [0, 1]).all():
        raise ValueError('expected a nonempty one-dimensional bit sequence')
    return array


def count_errors(reference, received) -> dict:
    reference, received = _bits(reference), _bits(received)
    if reference.shape != received.shape:
        raise ValueError('bit sequences must have the same length')
    n = reference.size
    errors = int(np.count_nonzero(reference != received))
    # One-sided exact Clopper-Pearson 95% bound, including zero errors.
    upper = 1.0 if errors == n else float(beta.ppf(0.95, errors + 1, n - errors))
    return dict(bits=int(n), errors=errors, ber=errors / n, ber_upper_95=upper)


def analyze_eye(samples_mw, bits, samples_per_bit: int) -> dict:
    bits = _bits(bits)
    samples = np.asarray(samples_mw, dtype=float)
    if (not isinstance(samples_per_bit, int) or samples_per_bit < 2
            or samples.ndim != 1 or samples.size != bits.size * samples_per_bit
            or not np.isfinite(samples).all() or np.unique(bits).size != 2):
        raise ValueError('eye needs finite complete bit periods and both levels')
    periods = samples.reshape(-1, samples_per_bit)
    ones, zeros = periods[bits == 1], periods[bits == 0]
    mean1, mean0 = ones.mean(axis=0), zeros.mean(axis=0)
    std1, std0 = ones.std(axis=0), zeros.std(axis=0)
    center = samples_per_bit // 2
    high, low = float(mean1[center]), float(mean0[center])
    threshold = (high + low) / 2
    lower_ones, upper_zeros = mean1 - 3 * std1, mean0 + 3 * std0
    # The opening must contain the decision threshold, not merely separate levels.
    margin = np.minimum(lower_ones - threshold, threshold - upper_zeros)
    if margin[center] <= 0:
        width = 0.0
    else:
        left = right = center
        while left > 0 and margin[left - 1] > 0:
            left -= 1
        while right < samples_per_bit - 1 and margin[right + 1] > 0:
            right += 1
        left_ui = (left - margin[left] / (margin[left] - margin[left - 1])
                   if left else -0.5)
        right_ui = (right + margin[right] / (margin[right] - margin[right + 1])
                    if right < samples_per_bit - 1 else samples_per_bit - 0.5)
        width = (right_ui - left_ui) / samples_per_bit
    return dict(eye_height_mw=float(lower_ones[center] - upper_zeros[center]),
                eye_width_ui=float(width),
                extinction_ratio_db=float(10 * np.log10(high / low))
                if high > 0 and low > 0 else None,
                one_level_mw=high, zero_level_mw=low)


def analyze_spectrum(wavelength_nm, power_dbm) -> dict:
    x, y = np.asarray(wavelength_nm, float), np.asarray(power_dbm, float)
    if (x.ndim != 1 or x.size < 3 or x.shape != y.shape or not np.isfinite(x).all()
            or not np.isfinite(y).all() or not (np.diff(x) > 0).all()):
        raise ValueError('spectrum needs matching finite arrays and increasing wavelengths')
    peak = int(np.argmax(y))
    linear = 10 ** ((y - y[peak]) / 10)
    below_left = np.flatnonzero(linear[:peak] < 0.5)
    below_right = np.flatnonzero(linear[peak + 1:] < 0.5) + peak + 1
    if not below_left.size or not below_right.size:
        raise ValueError('spectrum must bracket both half-power crossings')
    left, right = below_left[-1], below_right[0]
    x_left = np.interp(0.5, linear[left:left+2], x[left:left+2])
    x_right = np.interp(0.5, linear[right-1:right+1][::-1], x[right-1:right+1][::-1])
    # Only resolved local peaks outside the main mode's FWHM count as side modes.
    peaks, _ = find_peaks(y, prominence=3)
    side = [i for i in peaks if x[i] < x_left or x[i] > x_right]
    strongest = max(side, key=lambda i: y[i]) if side else None
    return dict(peak_wavelength_nm=float(x[peak]), peak_power_dbm=float(y[peak]),
                smsr_db=float(y[peak] - y[strongest]) if strongest is not None else None,
                side_mode_wavelength_nm=float(x[strongest]) if strongest is not None else None,
                linewidth_fwhm_nm=float(x_right - x_left))


def sensitivity(rows: list[dict], target_ber: float) -> dict:
    if not np.isfinite(target_ber) or not 0 < target_ber < 1 or not rows:
        raise ValueError('target BER must be between zero and one; sweep cannot be empty')
    ordered = sorted(rows, key=lambda r: r['power_dbm'])
    powers = np.array([r['power_dbm'] for r in ordered], dtype=float)
    bounds = np.array([r['ber_upper_95'] for r in ordered], dtype=float)
    if (not np.isfinite(powers).all() or not (np.diff(powers) > 0).all()
            or not np.isfinite(bounds).all() or not ((bounds > 0) & (bounds <= 1)).all()):
        raise ValueError('sensitivity needs unique finite powers and positive BER bounds')
    # A pass requires this and every stronger measured point to meet the bound.
    envelope = np.maximum.accumulate(bounds[::-1])[::-1]
    passing = np.flatnonzero(envelope <= target_ber)
    result = dict(target_ber=target_ber, status='not_reached', interpolated_dbm=None,
                  first_passing_dbm=None)
    if not passing.size:
        return result
    i = passing[0]
    result['first_passing_dbm'] = float(powers[i])
    result['status'] = 'below_sweep' if i == 0 else 'bracketed'
    if i:
        fraction = ((np.log10(target_ber) - np.log10(envelope[i-1]))
                    / (np.log10(envelope[i]) - np.log10(envelope[i-1])))
        result['interpolated_dbm'] = float(powers[i-1] + fraction * (powers[i] - powers[i-1]))
    return result
