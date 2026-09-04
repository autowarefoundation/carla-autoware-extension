import statistics

from benchmarks.analysis.stats import bootstrap_ci_median_diff, equivalence_decision, load_margins


def test_bootstrap_ci_contains_true_diff_and_is_deterministic():
    a = [10.0, 11.0, 10.5, 10.2, 10.8, 10.4, 10.6, 10.3, 10.7, 10.5]
    b = [12.0, 12.5, 12.2, 11.8, 12.4, 12.1, 12.3, 11.9, 12.6, 12.0]
    true_diff = statistics.median(a) - statistics.median(b)
    lo, hi = bootstrap_ci_median_diff(a, b, iters=2000, seed=1)
    assert lo <= true_diff <= hi
    assert hi < 0  # a is clearly better than b
    assert (lo, hi) == bootstrap_ci_median_diff(a, b, iters=2000, seed=1)


def test_equivalence_parity():
    assert equivalence_decision(0.5, (-1.0, 1.5), margin=2.0) == "parity"


def test_equivalence_a_better():
    assert equivalence_decision(-5.0, (-6.0, -4.0), margin=2.0) == "a_better"


def test_equivalence_b_better():
    assert equivalence_decision(5.0, (4.0, 6.0), margin=2.0) == "b_better"


def test_equivalence_inconclusive_wide_ci():
    assert equivalence_decision(0.1, (-9.0, 9.0), margin=2.0) == "inconclusive"


def test_margins_file_loads():
    m = load_margins("benchmarks/config/margins.yaml")
    assert "one_hop_wall_ms" in m and m["one_hop_wall_ms"]["margin"] > 0
