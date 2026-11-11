from pathlib import Path

import pytest

from bench.limits import (
    Check,
    ConfigError,
    Limits,
    crossing_time,
    evaluate,
    load_limits,
    mean_and_ripple_pp,
    steady_slice,
)

LIMITS_FILE = Path(__file__).resolve().parents[1] / "limits.toml"


def make_limits(**overrides) -> Limits:
    base = dict(vbus_setpoint_v=5.0, setpoint_tolerance_v=0.05, max_input_current_ma=150.0,
                vbus_tolerance_fraction=0.05, v3v3_nominal_v=3.3, v3v3_tolerance_fraction=0.05,
                max_ripple_mvpp=30.0, ready_fraction=0.9, min_delay_ms=0.2, max_delay_ms=10.0,
                window_ms=30.0, points=6000, steady_window_ms=5.0)
    base.update(overrides)
    return Limits(**base)


def ramp_record(points=6000, window_ms=30.0, final=5.0, start_ms=0.0, ramp_ms=1.0, ripple_pp=0.0):
    """A rail that starts at start_ms and ramps to `final` over ramp_ms, with optional flat ripple."""
    dt = window_ms / points / 1000.0
    times = [i * dt for i in range(points)]
    volts = []
    for i, t in enumerate(times):
        frac = min(max((t * 1000 - start_ms) / ramp_ms, 0.0), 1.0)
        # Alternating +/- half the ripple once the rail is up, so peak-to-peak equals ripple_pp.
        ripple = (ripple_pp / 2) * (1 if i % 2 else -1) if frac >= 1 else 0.0
        volts.append(frac * final + ripple)
    return times, volts


def run_checks(limits=None, vbus=None, v3=None, current_a=0.060):
    limits = limits or make_limits()
    vt, vv = vbus or ramp_record(final=5.0)
    v3t, v3v = v3 or ramp_record(final=3.3, start_ms=1.5)
    return {c.name: c for c in evaluate(limits, vbus_times=vt, vbus_volts=vv,
                                        v3_times=v3t, v3_volts=v3v, input_current_a=current_a)}


def test_bundled_limits_file_loads_with_expected_values():
    limits = load_limits(LIMITS_FILE)
    assert limits.vbus_setpoint_v == 5.0
    assert limits.max_ripple_mvpp == 30.0
    assert (limits.min_delay_ms, limits.max_delay_ms) == (0.2, 10.0)
    assert limits.points == 6000 and limits.window_ms == 30.0


@pytest.mark.parametrize("section, key", [("supply", "vbus_setpoint_v"), ("rail_3v3", "max_ripple_mvpp"),
                                          ("sequence", "max_delay_ms"), ("capture", "points")])
def test_missing_key_is_a_config_error(tmp_path, section, key):
    text = LIMITS_FILE.read_text(encoding="utf-8")
    broken = "\n".join(line for line in text.splitlines() if not line.startswith(f"{key} ="))
    path = tmp_path / "limits.toml"
    path.write_text(broken, encoding="utf-8")
    with pytest.raises(ConfigError, match=key):
        load_limits(path)


def test_missing_section_is_a_config_error(tmp_path):
    path = tmp_path / "limits.toml"
    path.write_text("[supply]\nvbus_setpoint_v = 5.0\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="missing"):
        load_limits(path)


@pytest.mark.parametrize("overrides", [
    dict(steady_window_ms=30.0),
    dict(min_delay_ms=11.0),
    dict(ready_fraction=1.0),
    dict(points=8),
])
def test_inconsistent_limits_are_rejected(overrides):
    with pytest.raises(ConfigError):
        make_limits(**overrides)


def test_steady_slice_covers_the_last_window():
    times = [i * 0.001 for i in range(31)]  # 0 .. 30 ms in 1 ms steps
    part = steady_slice(times, 5.0)
    assert times[part.start] == pytest.approx(0.025)
    assert part.stop == len(times)


def test_mean_and_ripple_pp():
    assert mean_and_ripple_pp([3.3, 3.3, 3.3]) == (pytest.approx(3.3), 0.0)
    mean, pp = mean_and_ripple_pp([3.29, 3.31, 3.30, 3.32])
    assert mean == pytest.approx(3.305) and pp == pytest.approx(0.03)
    with pytest.raises(ValueError):
        mean_and_ripple_pp([])


def test_crossing_time_interpolates_between_samples():
    assert crossing_time([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], 1.5) == pytest.approx(1.5)


def test_crossing_time_none_when_never_reached_and_first_sample_when_already_high():
    assert crossing_time([0.0, 1.0], [0.0, 0.5], 1.0) is None
    assert crossing_time([0.0, 1.0], [2.0, 2.5], 1.0) == 0.0


def test_nominal_rails_pass_every_check():
    checks = run_checks()
    assert all(c.passed for c in checks.values()), {k: c.measured for k, c in checks.items()}
    # VBUS reaches 90 % at 0.9 ms and 3V3 starts at 1.5 ms, so 3V3 reaches 90 % at 2.4 ms.
    assert checks["sequence_3v3_after_vbus_ms"].measured == pytest.approx(1.5, abs=0.05)


def test_ripple_above_limit_fails_only_the_ripple_check():
    vt, vv = ramp_record(final=5.0)
    v3t, v3v = ramp_record(final=3.3, start_ms=1.5, ripple_pp=0.060)
    checks = run_checks(vbus=(vt, vv), v3=(v3t, v3v))
    assert not checks["rail_3v3_ripple_mvpp"].passed
    assert checks["rail_3v3_ripple_mvpp"].measured == pytest.approx(60.0, abs=0.5)
    assert checks["sequence_3v3_after_vbus_ms"].passed


def test_late_rail_fails_the_sequence_check():
    v3t, v3v = ramp_record(final=3.3, start_ms=14.0)
    checks = run_checks(v3=(v3t, v3v))
    assert not checks["sequence_3v3_after_vbus_ms"].passed
    assert checks["rail_3v3_ripple_mvpp"].passed


def test_rail_that_comes_up_before_vbus_fails_the_lower_delay_bound():
    v3t, v3v = ramp_record(final=3.3, start_ms=0.0)
    vt, vv = ramp_record(final=5.0, start_ms=2.0)
    checks = run_checks(vbus=(vt, vv), v3=(v3t, v3v))
    assert checks["sequence_3v3_after_vbus_ms"].measured < 0
    assert not checks["sequence_3v3_after_vbus_ms"].passed


def test_3v3_that_never_settles_fails_without_a_number():
    v3t, v3v = ramp_record(final=1.0, start_ms=1.5)  # only reaches 1 V
    checks = run_checks(v3=(v3t, v3v))
    assert checks["sequence_3v3_after_vbus_ms"].measured is None
    assert not checks["sequence_3v3_after_vbus_ms"].passed


def test_low_3v3_mean_fails_steady_state():
    v3t, v3v = ramp_record(final=3.0, start_ms=1.5)
    assert not run_checks(v3=(v3t, v3v))["rail_3v3_mean_v"].passed


def test_current_over_the_limit_fails():
    assert run_checks(current_a=0.151)["input_current_ma"].passed is False
    assert run_checks(current_a=0.150)["input_current_ma"].passed is True


def test_check_passed_rejects_nan_and_missing_values():
    assert not Check("x", float("nan"), 0, 1, "V", "").passed
    assert not Check("x", None, 0, 1, "V", "").passed
    assert Check("x", 0.0, 0, 1, "V", "").passed  # limits are inclusive
