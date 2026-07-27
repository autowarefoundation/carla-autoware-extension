import numpy as np
import pytest
from benchmarks.analysis.clockfit import fit_sim_wall_affine
from benchmarks.analysis.latency import match_stamps, one_hop_wall_ms, segment_sim_ms, staleness_ms


def test_one_hop_wall():
    sim = np.array([0, 50_000_000, 100_000_000])
    wall = np.array([1_000_000_000, 1_050_000_000, 1_100_000_000])
    fit = fit_sim_wall_affine(sim, wall)  # RTF 1.0
    # message stamped sim=50ms arrives at wall 1.058s -> 8 ms transport
    lat = one_hop_wall_ms(np.array([50_000_000]), np.array([1_058_000_000]), fit)
    assert lat[0] == pytest.approx(8.0, abs=0.01)


def test_match_stamps_pairs_common_only():
    src = np.array([100, 200, 300, 400])
    dst = np.array([200, 400, 500])
    i, j = match_stamps(src, dst)
    np.testing.assert_array_equal(src[i], [200, 400])
    np.testing.assert_array_equal(dst[j], [200, 400])


def test_segment_and_staleness():
    np.testing.assert_allclose(
        segment_sim_ms(np.array([100_000_000]), np.array([130_000_000])), [30.0]
    )
    np.testing.assert_allclose(staleness_ms(np.array([0]), np.array([45_000_000])), [45.0])
