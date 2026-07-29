"""M2: achieved rate, inter-arrival percentiles, drop reconciliation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CadenceStats:
    hz: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    n: int


@dataclass(frozen=True)
class DropStats:
    publisher_drop_rate: float  # approach property
    observer_loss_rate: float  # instrument property


def inter_arrival_stats(arrival_ns) -> CadenceStats:
    a = np.sort(np.asarray(arrival_ns, dtype=np.int64))
    if a.size < 2:
        raise ValueError("need >= 2 arrivals")
    d_ms = np.diff(a) / 1e6
    span_s = (a[-1] - a[0]) / 1e9
    return CadenceStats(
        hz=float((a.size - 1) / span_s),
        p50_ms=float(np.percentile(d_ms, 50)),
        p95_ms=float(np.percentile(d_ms, 95)),
        p99_ms=float(np.percentile(d_ms, 99)),
        n=int(a.size),
    )


def reconcile_drops(expected_count: int, published_count: int, observed_count: int) -> DropStats:
    if expected_count <= 0 or published_count < 0:
        raise ValueError("expected_count must be > 0 and published_count >= 0")
    pub_drop = max(0.0, 1.0 - published_count / expected_count)
    # A zero-throughput run has no denominator to measure observer loss
    # against; reporting 0.0 would silently read as "no observer loss"
    # instead of "undefined", so this degenerate case reports NaN.
    obs_loss = (
        float("nan") if published_count == 0 else max(0.0, 1.0 - observed_count / published_count)
    )
    return DropStats(pub_drop, obs_loss)
