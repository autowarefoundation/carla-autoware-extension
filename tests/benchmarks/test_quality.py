import numpy as np
import pytest

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
        expected_ndt_hz=20.0,
        abs_pose_gate_m=None,
    )  # relative ladder branch
    assert q.gate_pass and q.pose_err_p50_m == pytest.approx(0.6, abs=1e-6)


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
        expected_ndt_hz=20.0,
        abs_pose_gate_m=0.5,
    )
    assert not q.gate_pass and any("ndt rate" in r for r in q.reasons)
