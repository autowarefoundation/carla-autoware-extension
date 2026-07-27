import numpy as np
import pytest
from benchmarks.analysis.clockfit import fit_sim_wall_affine, sim_to_wall


def test_recovers_exact_affine():
    sim = np.arange(0, 10_000_000_000, 50_000_000)  # 20 Hz sim clock
    wall = 1_700_000_000_000_000_000 + 2.0 * sim  # RTF 0.5, offset epoch
    fit = fit_sim_wall_affine(sim, wall)
    assert fit.slope == pytest.approx(2.0)
    assert fit.max_abs_residual_ns < 1.0
    assert sim_to_wall(fit, 100_000_000) == pytest.approx(1_700_000_000_000_000_000 + 200_000_000)


def test_reports_residual_under_jitter():
    rng = np.random.default_rng(0)
    sim = np.arange(0, 5_000_000_000, 50_000_000)
    wall = 1e18 + sim + rng.normal(0, 1e6, sim.size)  # 1 ms jitter
    fit = fit_sim_wall_affine(sim, wall)
    assert 1e5 < fit.max_abs_residual_ns < 1e7


def test_rejects_short_input():
    with pytest.raises(ValueError):
        fit_sim_wall_affine([0], [0])
