import numpy as np
import pytest

from benchmarks.analysis import quality
from benchmarks.analysis.quality import QualityStats, evaluate_quality

ROUTE = np.array([[0.0, 0.0], [200.0, 0.0]])


def _mk(n=100, bias=0.0):
    t = np.arange(n, dtype=np.int64) * 50_000_000  # 20 Hz sim stamps
    gt = np.column_stack([np.linspace(0, 150, n), np.zeros(n)])
    ndt = gt + [0.0, bias]
    return t, ndt, t.copy(), gt


def test_gate_passes_clean_run():
    t, ndt, gt_t, gt = _mk()
    q = evaluate_quality(
        ndt_stamp_ns=t,
        ndt_xy=ndt,
        gt_sim_ns=gt_t,
        gt_xy=gt,
        odom_stamp_ns=t,
        odom_xy=gt,
        route_xy=ROUTE,
        goal_xy=np.array([150.0, 0.0]),
        window=(0, int(t[-1])),
        goal_window=(0, int(t[-1])),
        expected_ndt_hz=20.0,
        abs_pose_gate_m=0.5,
    )
    assert isinstance(q, QualityStats)
    assert q.gate_pass and q.goal_closest_approach_m < 1.0
    assert q.goal_terminal_distance_m == pytest.approx(0.0, abs=1e-9)


def test_absolute_gate_fails_on_half_meter_bias():
    t, ndt, gt_t, gt = _mk(bias=0.6)
    q = evaluate_quality(
        ndt_stamp_ns=t,
        ndt_xy=ndt,
        gt_sim_ns=gt_t,
        gt_xy=gt,
        odom_stamp_ns=t,
        odom_xy=gt,
        route_xy=ROUTE,
        goal_xy=np.array([150.0, 0.0]),
        window=(0, int(t[-1])),
        goal_window=(0, int(t[-1])),
        expected_ndt_hz=20.0,
        abs_pose_gate_m=0.5,
    )
    assert not q.gate_pass and any("pose_error" in r for r in q.reasons)


def test_relative_gate_reports_bias_but_passes():
    t, ndt, gt_t, gt = _mk(bias=0.6)
    q = evaluate_quality(
        ndt_stamp_ns=t,
        ndt_xy=ndt,
        gt_sim_ns=gt_t,
        gt_xy=gt,
        odom_stamp_ns=t,
        odom_xy=gt,
        route_xy=ROUTE,
        goal_xy=np.array([150.0, 0.0]),
        window=(0, int(t[-1])),
        goal_window=(0, int(t[-1])),
        expected_ndt_hz=20.0,
        abs_pose_gate_m=None,
    )  # relative ladder branch
    assert q.gate_pass and q.pose_err_p50_m == pytest.approx(0.6, abs=1e-6)


def _drifting(n=100, drift_m=0.0, spread_m=0.0):
    """A track whose NDT error ramps by `drift_m` over the run and takes a
    `spread_m` excursion in the MIDDLE of it.

    The two knobs drive the relative branch's two criteria independently, which
    is what makes each bracket test attributable. The excursion sits mid-run
    (samples 40-49 of 100) rather than in the second half on purpose: a step at
    the midpoint moves the last-20% mean too, so it would fire the DRIFT
    criterion instead and the spread test would pass for the wrong reason --
    measured while writing this.
    """
    t = np.arange(n, dtype=np.int64) * 50_000_000
    gt = np.column_stack([np.linspace(0, 150, n), np.zeros(n)])
    err = np.linspace(0.0, drift_m, n)
    err[int(0.4 * n) : int(0.5 * n)] += spread_m
    return t, gt + np.column_stack([np.zeros(n), err]), t.copy(), gt


def _relative(t, ndt, gt_t, gt):
    return evaluate_quality(
        ndt_stamp_ns=t,
        ndt_xy=ndt,
        gt_sim_ns=gt_t,
        gt_xy=gt,
        odom_stamp_ns=t,
        odom_xy=gt,
        route_xy=ROUTE,
        goal_xy=np.array([150.0, 0.0]),
        window=(0, int(t[-1])),
        goal_window=(0, int(t[-1])),
        expected_ndt_hz=20.0,
        abs_pose_gate_m=None,
    )


@pytest.mark.parametrize(("drift_m", "fires"), [(0.15, False), (0.35, True)])
def test_relative_gate_brackets_the_drift_threshold(drift_m, fires):
    """The relative branch's registered no-drift criterion is
    |mean(last 20%) − mean(first 20%)| < 0.2 m, and NOTHING covered it failing:
    `test_relative_gate_reports_bias_but_passes` uses a constant offset, so
    both of this branch's criteria are trivially satisfied there and any
    relaxation of either survives. A ramp of `drift_m` yields 0.808 x that much
    drift, i.e. 0.121 m (passes) and 0.283 m (fails), and only 0.45 x it in
    spread, so the spread criterion stays quiet in both.
    """
    q = _relative(*_drifting(drift_m=drift_m))
    assert any("drift" in r for r in q.reasons) is fires, (drift_m, q.reasons)
    assert not any("p95-p50" in r for r in q.reasons), q.reasons
    assert q.gate_pass is not fires


@pytest.mark.parametrize(("spread_m", "fires"), [(0.25, False), (0.35, True)])
def test_relative_gate_brackets_the_spread_threshold(spread_m, fires):
    """The relative branch's other registered criterion, p95 − p50 < 0.3 m,
    bracketed the same way. A 10%-of-the-run mid-course excursion puts p50 at
    the baseline and p95 at the excursion, so the spread IS `spread_m`, while
    the first and last 20% are both baseline so drift stays at 0."""
    q = _relative(*_drifting(spread_m=spread_m))
    assert any("p95-p50" in r for r in q.reasons) is fires, (spread_m, q.reasons)
    assert not any("drift" in r for r in q.reasons), q.reasons


def test_goal_metrics_use_the_goal_window_not_the_scoring_window():
    """2026-07-29 owner ruling: the two goal metrics are scored over the
    warm-up-trimmed full armed span, not the station-trimmed scoring window.

    Here the scoring window stops half way along the track while the goal
    window covers all of it, so an implementation that reached for `window`
    would report ~75 m of closest approach and FAIL the gate instead of the
    ~0 m arrival the goal window sees.
    """
    t, ndt, gt_t, gt = _mk()
    q = evaluate_quality(
        ndt_stamp_ns=t,
        ndt_xy=ndt,
        gt_sim_ns=gt_t,
        gt_xy=gt,
        odom_stamp_ns=t,
        odom_xy=gt,
        route_xy=ROUTE,
        goal_xy=np.array([150.0, 0.0]),
        window=(0, int(t[49])),
        goal_window=(0, int(t[-1])),
        expected_ndt_hz=20.0,
        abs_pose_gate_m=0.5,
    )
    assert q.gate_pass, q.reasons
    assert q.goal_closest_approach_m == pytest.approx(0.0, abs=1e-9)
    assert q.goal_terminal_distance_m == pytest.approx(0.0, abs=1e-9)


def test_goal_criteria_do_not_apply_without_a_goal_window():
    """The static arm: a parked ego has no goal approach, so both goal fields
    are null and neither contributes a gate reason. A distance computed anyway
    would be misleading evidence, and gating on it would fail every static run
    structurally."""
    t, ndt, gt_t, gt = _mk()
    parked = np.zeros_like(gt)
    q = evaluate_quality(
        ndt_stamp_ns=t,
        ndt_xy=parked,
        gt_sim_ns=gt_t,
        gt_xy=parked,
        odom_stamp_ns=t,
        odom_xy=parked,
        route_xy=ROUTE,
        goal_xy=np.array([150.0, 0.0]),
        window=(0, int(t[-1])),
        goal_window=None,
        expected_ndt_hz=20.0,
        abs_pose_gate_m=0.5,
    )
    assert q.goal_closest_approach_m is None
    assert q.goal_terminal_distance_m is None
    assert q.gate_pass, q.reasons
    assert not any("goal" in r for r in q.reasons)


@pytest.mark.parametrize(("threshold", "refuses"), [(10, True), (5, True), (3, False)])
def test_the_join_pair_refusal_reports_the_threshold_it_used(monkeypatch, threshold, refuses):
    """The refusal message is FORMATTED FROM `MIN_JOIN_PAIRS`, not repeated.

    Four pairs are offered while the threshold is moved around them. At the
    registered 10 and at 5 the run is refused and the message must name the
    threshold IN FORCE -- a hardcoded "fewer than 10" claims 10 while
    refusing at 5, which is a gate misreporting itself in the one string an
    operator reads. At 3 the same four pairs are scored, which is what shows
    the constant drives the behaviour and not just the wording.

    A test that only ever runs at the default value cannot see either
    property: the hardcoded and the formatted string are then identical.
    """
    monkeypatch.setattr(quality, "MIN_JOIN_PAIRS", threshold)
    t, ndt, gt_t, gt = _mk()
    kwargs = dict(
        ndt_stamp_ns=t,
        ndt_xy=ndt,
        gt_sim_ns=gt_t,
        gt_xy=gt,
        odom_stamp_ns=t,
        odom_xy=gt,
        route_xy=ROUTE,
        goal_xy=np.array([150.0, 0.0]),
        window=(0, int(t[3])),  # four in-window NDT samples
        goal_window=(0, int(t[-1])),
        expected_ndt_hz=20.0,
        abs_pose_gate_m=0.5,
    )
    if not refuses:
        assert evaluate_quality(**kwargs).gate_pass
        return
    with pytest.raises(ValueError) as exc:
        evaluate_quality(**kwargs)
    assert f"fewer than {threshold} NDT" in str(exc.value)
    assert "found 4" in str(exc.value)


def test_ndt_rate_gate():
    t, ndt, gt_t, gt = _mk()
    q = evaluate_quality(
        ndt_stamp_ns=t[::4],
        ndt_xy=ndt[::4],
        gt_sim_ns=gt_t,
        gt_xy=gt,
        odom_stamp_ns=t,
        odom_xy=gt,
        route_xy=ROUTE,
        goal_xy=np.array([150.0, 0.0]),
        window=(0, int(t[-1])),
        goal_window=(0, int(t[-1])),
        expected_ndt_hz=20.0,
        abs_pose_gate_m=0.5,
    )
    assert not q.gate_pass and any("ndt rate" in r for r in q.reasons)
