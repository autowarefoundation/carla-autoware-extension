"""Pre-registered statistics: bootstrap CI on run-level medians and the
C1 equivalence decision rule (spec: Statistical treatment)."""

from __future__ import annotations

import numpy as np
import yaml


def bootstrap_ci_median_diff(a, b, iters: int = 10000, seed: int = 20260727, alpha: float = 0.05):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.size < 3 or b.size < 3:
        raise ValueError("need >= 3 run-level values per side")
    rng = np.random.default_rng(seed)
    diffs = np.empty(iters)
    for k in range(iters):
        diffs[k] = np.median(rng.choice(a, a.size, replace=True)) - np.median(
            rng.choice(b, b.size, replace=True)
        )
    return (float(np.quantile(diffs, alpha / 2)), float(np.quantile(diffs, 1 - alpha / 2)))


def equivalence_decision(delta_median: float, ci, margin: float) -> str:
    lo, hi = ci
    if abs(delta_median) < margin and lo > -2 * margin and hi < 2 * margin:
        return "parity"
    if hi < 0:
        return "a_better"
    if lo > 0:
        return "b_better"
    return "inconclusive"


def load_margins(path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)
