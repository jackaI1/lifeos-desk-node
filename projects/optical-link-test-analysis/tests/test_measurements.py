import numpy as np
import pytest

from optical_link.analysis import analyze_eye, analyze_spectrum, count_errors, sensitivity
from optical_link.model import LinkConfig, acquire, prbs7, simulate_spectrum


def test_prbs7_is_maximal_and_repeats():
    bits = prbs7(254)
    assert set(bits) == {0, 1}
    assert bits[:127].sum() == 64
    np.testing.assert_array_equal(bits[:127], bits[127:])
    assert len({tuple(np.roll(bits[:127], i)) for i in range(127)}) == 127


def test_error_count_and_zero_error_confidence():
    result = count_errors([0, 1, 0, 1], [0, 0, 0, 1])
    assert result['errors'] == 1
    assert result['ber'] == 0.25
    zero = count_errors(np.zeros(1000), np.zeros(1000))
    assert zero['ber'] == 0
    assert zero['ber_upper_95'] == pytest.approx(0.00299125, rel=1e-5)
    assert count_errors([0], [1])['ber_upper_95'] == 1


@pytest.mark.parametrize('a,b', [([], []), ([0], [0, 1]), ([2], [0])])
def test_invalid_bits_rejected(a, b):
    with pytest.raises(ValueError):
        count_errors(a, b)


def test_ideal_eye_has_calibrated_height_width_and_extinction():
    bits = prbs7(1270)
    samples = np.repeat(np.where(bits, 2.0, 0.2), 32)
    eye = analyze_eye(samples, bits, 32)
    assert eye['eye_height_mw'] == pytest.approx(1.8)
    assert eye['eye_width_ui'] == pytest.approx(1.0)
    assert eye['extinction_ratio_db'] == pytest.approx(10)


def test_closed_eye_and_nonpositive_low_level_are_explicit():
    bits = prbs7(1270)
    eye = analyze_eye(np.zeros(bits.size * 16), bits, 16)
    assert eye['eye_width_ui'] == 0
    assert eye['extinction_ratio_db'] is None


def test_clean_link_and_fiber_dispersion_penalty():
    clean = acquire(LinkConfig(n_bits=4096, noise_std_mw=0, fiber_km=0), -15)
    spread = acquire(LinkConfig(n_bits=4096, noise_std_mw=0, fiber_km=100), -15)
    assert count_errors(clean.bits, clean.decisions)['errors'] == 0
    clean_eye = analyze_eye(clean.samples_mw, clean.bits, 32)
    spread_eye = analyze_eye(spread.samples_mw, spread.bits, 32)
    assert clean_eye['eye_height_mw'] > spread_eye['eye_height_mw']


def test_received_power_changes_real_decisions_and_seed_reproduces():
    config = LinkConfig(n_bits=16384, fiber_km=0)
    weak, strong = acquire(config, -30), acquire(config, -15)
    assert count_errors(weak.bits, weak.decisions)['ber'] > 0.1
    assert count_errors(strong.bits, strong.decisions)['ber'] < 0.001
    np.testing.assert_array_equal(weak.samples_mw, acquire(config, -30).samples_mw)


def test_known_spectrum_peak_smsr_and_half_power_linewidth():
    wavelength, power = simulate_spectrum()
    result = analyze_spectrum(wavelength, power)
    assert result['peak_wavelength_nm'] == pytest.approx(1550, abs=0.001)
    assert result['smsr_db'] == pytest.approx(30, abs=0.02)
    assert result['linewidth_fwhm_nm'] == pytest.approx(0.08, abs=0.001)


def test_spectrum_missing_side_mode_and_unbracketed_peak():
    x = np.linspace(-1, 1, 1001)
    one_mode = analyze_spectrum(x, 10 * np.log10(np.exp(-x*x / 0.01) + 1e-12))
    assert one_mode['smsr_db'] is None
    with pytest.raises(ValueError, match='bracket'):
        analyze_spectrum(np.arange(5), np.arange(5))
    with pytest.raises(ValueError):
        analyze_spectrum([1, 0, 2], [0, 0, 0])


def test_sensitivity_is_conservative_and_does_not_extrapolate():
    rows = [dict(power_dbm=-30, ber_upper_95=0.1),
            dict(power_dbm=-20, ber_upper_95=0.001),
            dict(power_dbm=-10, ber_upper_95=0.0001)]
    result = sensitivity(rows, 0.01)
    assert result['interpolated_dbm'] == pytest.approx(-25)
    assert result['first_passing_dbm'] == -20
    assert sensitivity(rows, 1e-6)['status'] == 'not_reached'
    assert sensitivity(rows, 0.2)['status'] == 'below_sweep'


@pytest.mark.parametrize('kwargs', [dict(n_bits=0), dict(samples_per_bit=3),
    dict(noise_std_mw=-1), dict(fiber_km=float('nan')), dict(bit_rate_gbps=0),
    dict(extinction_ratio_db=-1), dict(seed=-1)])
def test_bad_configuration_rejected(kwargs):
    with pytest.raises(ValueError):
        LinkConfig(**kwargs)


def test_noise_only_ber_matches_independent_gaussian_prediction():
    from math import erfc, sqrt
    # At -25 dBm, nominal P1-P0 = 2P*(10-1)/(10+1).
    # An effectively unlimited receiver bandwidth removes filtering ISI.
    config = LinkConfig(n_bits=100_000, samples_per_bit=8, fiber_km=0,
                        receiver_bandwidth_ghz=1e6)
    capture = acquire(config, -25)
    measured = count_errors(capture.bits, capture.decisions)['ber']
    expected = .5 * erfc((2 * 10**(-2.5) * 9/11) / (2 * .0015 * sqrt(2)))
    assert measured == pytest.approx(expected, abs=.003)


@pytest.mark.parametrize('samples,bits,sps', [([0, 1], [0, 1], 2),
    ([float('nan')]*4, [0, 1], 2), ([0]*4, [0, 0], 2)])
def test_incomplete_or_invalid_eye_rejected(samples, bits, sps):
    with pytest.raises(ValueError):
        analyze_eye(samples, bits, sps)


def test_sensitivity_requires_all_stronger_points_to_pass():
    rows = [dict(power_dbm=-30, ber_upper_95=.1),
            dict(power_dbm=-20, ber_upper_95=.001),
            dict(power_dbm=-10, ber_upper_95=.1)]
    assert sensitivity(rows, .01)['status'] == 'not_reached'


@pytest.mark.parametrize('kwargs', [dict(extinction_ratio_db=4000), dict(fiber_km=1e308),
    dict(noise_std_mw=1e308), dict(beta2_ps2_per_km=1e308),
    dict(bit_rate_gbps=1e-300), dict(receiver_bandwidth_ghz=1e-300)])
def test_unsupported_magnitudes_rejected_before_capture(kwargs):
    with pytest.raises(ValueError):
        LinkConfig(**kwargs)
