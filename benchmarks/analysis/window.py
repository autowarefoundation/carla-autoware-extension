"""Scoring windows (spec: Scenario): spatial gating + warm-up discard.

Closed-loop metrics are computed over a SPATIAL window (ego odometry
between fixed route stations), so every run scores the same stretch of
road regardless of small speed differences. Static-arm metrics use a
wall window with the same warm-up discard.
"""

from __future__ import annotations

import numpy as np


def _cum_arclen(route_xy: np.ndarray) -> np.ndarray:
    seg = np.linalg.norm(np.diff(route_xy, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(seg)])


def _project(route_xy, xy) -> tuple[np.ndarray, np.ndarray]:
    """Per point: (arc-length station on the route, perpendicular
    distance to it).

    Projects onto every segment, clamps to segment ends, and takes the
    globally nearest projection -- O(n_points * n_segments), fine at the
    row counts this harness produces. Station and lateral distance both
    come from the same nearest-segment argmin, so the two outputs are
    consistent by construction.
    """
    route_xy = np.asarray(route_xy, dtype=np.float64)
    xy = np.asarray(xy, dtype=np.float64)
    a, b = route_xy[:-1], route_xy[1:]
    ab = b - a
    seg_len2 = np.einsum("ij,ij->i", ab, ab)
    base = _cum_arclen(route_xy)[:-1]
    stations = np.empty(len(xy))
    lateral = np.empty(len(xy))
    for k, p in enumerate(xy):
        t = np.clip(np.einsum("ij,ij->i", p - a, ab) / seg_len2, 0.0, 1.0)
        proj = a + t[:, None] * ab
        d2 = np.einsum("ij,ij->i", p - proj, p - proj)
        i = int(np.argmin(d2))
        stations[k] = base[i] + t[i] * np.sqrt(seg_len2[i])
        lateral[k] = np.sqrt(d2[i])
    return stations, lateral


def project_station_m(route_xy, xy) -> np.ndarray:
    """Arc-length station (m) of each point's nearest spot on the route."""
    return _project(route_xy, xy)[0]


def spatial_window(
    odom_stamp_ns, odom_xy, route_xy, start_station_m: float, end_station_m: float, warmup_ns: int
) -> tuple[int, int]:
    """[start, end] stamps of the scoring window, or ValueError if empty."""
    stamps = np.asarray(odom_stamp_ns, dtype=np.int64)
    st = project_station_m(route_xy, odom_xy)
    ok = (st >= start_station_m) & (st <= end_station_m) & (stamps >= stamps[0] + warmup_ns)
    idx = np.nonzero(ok)[0]
    if idx.size == 0:
        raise ValueError("no odometry sample inside the spatial window")
    return int(stamps[idx[0]]), int(stamps[idx[-1]])


def static_window(t0_ns: int, end_ns: int, warmup_ns: int) -> tuple[int, int]:
    if t0_ns + warmup_ns >= end_ns:
        raise ValueError("warm-up discard consumes the whole run")
    return t0_ns + warmup_ns, end_ns
