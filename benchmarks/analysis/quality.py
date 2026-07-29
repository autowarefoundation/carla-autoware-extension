"""M5 closed-loop quality metrics + per-cell validation gate.

Definitions are pre-registered in benchmarks/README.md (M5 definitions).
`abs_pose_gate_m` selects the G1 ladder branch: a float applies the
absolute gate (pcd fix landed); None applies the relative gate (no
drift, bounded spread) and reports the constant bias instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .window import _project

JOIN_TOL_NS = 25_000_000  # nearest-stamp join tolerance (half a 20 Hz tick)


@dataclass(frozen=True)
class QualityStats:
    pose_err_p50_m: float
    pose_err_p95_m: float
    pose_err_max_m: float
    pose_bias_m: float
    lateral_dev_p95_m: float
    goal_closest_approach_m: float
    goal_terminal_distance_m: float
    ndt_rate_ratio: float
    gate_pass: bool
    reasons: list = field(default_factory=list)


def _nearest_join(a_ns: np.ndarray, b_ns: np.ndarray, tol_ns: int):
    """Indices (i, j) pairing each a to its nearest b within tol."""
    j = np.searchsorted(b_ns, a_ns)
    j = np.clip(j, 1, len(b_ns) - 1)
    left = np.abs(a_ns - b_ns[j - 1])
    right = np.abs(a_ns - b_ns[j])
    j = np.where(left <= right, j - 1, j)
    ok = np.abs(a_ns - b_ns[j]) <= tol_ns
    return np.nonzero(ok)[0], j[ok]


def evaluate_quality(
    *,
    ndt_stamp_ns,
    ndt_xy,
    gt_sim_ns,
    gt_xy,
    odom_stamp_ns,
    odom_xy,
    route_xy,
    goal_xy,
    window: tuple[int, int],
    expected_ndt_hz: float,
    abs_pose_gate_m: float | None,
) -> QualityStats:
    lo, hi = window
    reasons: list[str] = []

    ndt_t = np.asarray(ndt_stamp_ns, dtype=np.int64)
    in_w = (ndt_t >= lo) & (ndt_t <= hi)
    ndt_t, ndt_p = ndt_t[in_w], np.asarray(ndt_xy, dtype=np.float64)[in_w]
    gt_t = np.asarray(gt_sim_ns, dtype=np.int64)
    gt_p = np.asarray(gt_xy, dtype=np.float64)

    i, j = _nearest_join(ndt_t, gt_t, JOIN_TOL_NS)
    if i.size < 10:
        raise ValueError("fewer than 10 NDT<->GT stamp pairs in the window")
    err = np.linalg.norm(ndt_p[i] - gt_p[j], axis=1)
    k = max(1, err.size // 5)
    drift = abs(float(err[-k:].mean() - err[:k].mean()))
    spread = float(np.percentile(err, 95) - np.percentile(err, 50))

    ndt_rate = (ndt_t.size - 1) / ((ndt_t[-1] - ndt_t[0]) / 1e9)
    rate_ratio = float(ndt_rate / expected_ndt_hz)
    if rate_ratio < 0.9:
        reasons.append(f"ndt rate ratio {rate_ratio:.2f} < 0.9")

    if abs_pose_gate_m is not None:
        if float(err.max()) >= abs_pose_gate_m:
            reasons.append(f"pose_error max {err.max():.3f} >= {abs_pose_gate_m}")
    else:
        if drift >= 0.2:
            reasons.append(f"pose_error drift {drift:.3f} >= 0.2")
        if spread >= 0.3:
            reasons.append(f"pose_error p95-p50 {spread:.3f} >= 0.3")

    ot = np.asarray(odom_stamp_ns, dtype=np.int64)
    ow = (ot >= lo) & (ot <= hi)
    op = np.asarray(odom_xy, dtype=np.float64)[ow]
    goal_d = np.linalg.norm(op - np.asarray(goal_xy, dtype=np.float64), axis=1)
    closest, terminal = float(goal_d.min()), float(goal_d[-1])
    if closest >= 1.0:
        reasons.append(f"goal closest approach {closest:.3f} >= 1.0")

    # lateral deviation = distance to the route polyline itself; shares
    # the projection pass with window.project_station_m (same argmin
    # segment) instead of re-deriving the clip/project/argmin math.
    _, lat = _project(route_xy, op)

    return QualityStats(
        pose_err_p50_m=float(np.percentile(err, 50)),
        pose_err_p95_m=float(np.percentile(err, 95)),
        pose_err_max_m=float(err.max()),
        pose_bias_m=float(err.mean()),
        lateral_dev_p95_m=float(np.percentile(lat, 95)),
        goal_closest_approach_m=closest,
        goal_terminal_distance_m=terminal,
        ndt_rate_ratio=rate_ratio,
        gate_pass=not reasons,
        reasons=reasons,
    )
