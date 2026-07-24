from scripts.e2e.measure_rates import rate_in_band


def test_lidar_20hz_in_band():
    assert rate_in_band(19.6, target=20.0, tol=1.0) is True


def test_lidar_free_running_too_fast_fails():
    # 80 Hz (headless sync master free-running) is NOT a valid 20 Hz cadence.
    assert rate_in_band(80.0, target=20.0, tol=1.0) is False
