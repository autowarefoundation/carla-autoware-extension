import numpy as np
import pytest

from benchmarks.analysis.cadence import inter_arrival_stats, reconcile_drops


def test_steady_20hz():
    arrivals = np.arange(0, 10_000_000_000, 50_000_000)
    s = inter_arrival_stats(arrivals)
    assert s.hz == pytest.approx(20.0, rel=1e-3)
    assert s.p50_ms == pytest.approx(50.0)
    assert s.p99_ms == pytest.approx(50.0)
    assert s.n == arrivals.size


def test_jitter_percentiles_ordered():
    rng = np.random.default_rng(1)
    arrivals = np.cumsum(rng.uniform(40e6, 60e6, 500)).astype(np.int64)
    s = inter_arrival_stats(arrivals)
    assert s.p50_ms <= s.p95_ms <= s.p99_ms


def test_reconcile_drops():
    d = reconcile_drops(expected_count=200, published_count=180, observed_count=171)
    assert d.publisher_drop_rate == pytest.approx(0.10)
    assert d.observer_loss_rate == pytest.approx(0.05)


def test_reconcile_never_negative():
    d = reconcile_drops(100, 100, 103)  # duplicate delivery edge case
    assert d.observer_loss_rate == 0.0
