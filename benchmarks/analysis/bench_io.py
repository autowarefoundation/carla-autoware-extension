"""Readers for the bench_observer CSV contract (see benchmarks/README.md)."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np

OBSERVER_COLS = (
    "header_stamp_ns",
    "arrival_system_ns",
    "arrival_steady_ns",
    "clock_ns",
    "size_bytes",
)
PUBLISHED_COLS = ("source_header_ns", "published_ns")
# resources.csv mixes counters with ratios and is keyed by `process`, not by
# `topic`, so unlike the two readers above it cannot go through _read_grouped's
# int64 path. `-1` is the contract's not-applicable marker (a process with no
# GPU context; an rtf sample taken before the first /clock) and is preserved
# verbatim, so a caller masks it deliberately instead of averaging it in.
RESOURCE_INT_COLS = ("sample_system_ns", "rss_bytes", "vram_bytes")
RESOURCE_FLOAT_COLS = ("cpu_pct", "gpu_util_pct", "rtf")
# odometry.csv and pose.csv share one schema (`topic,header_stamp_ns,x_m,y_m`)
# and one reader below. They stay SEPARATE FILES because they carry different
# quantities -- the EKF-fused kinematic state versus the NDT pose estimate --
# and benchmarks/README.md's M5 definitions score `pose_error` on the latter
# only; see read_pose_csv.
ODOM_INT_COLS = ("header_stamp_ns",)
ODOM_FLOAT_COLS = ("x_m", "y_m")
GT_INT_COLS = ("arrival_system_ns", "sim_ns")
GT_FLOAT_COLS = ("x_m", "y_m", "z_m", "yaw_rad")


def _read_grouped(path: Path, cols: tuple[str, ...]) -> dict:
    grouped: dict[str, dict[str, list[int]]] = defaultdict(lambda: {c: [] for c in cols})
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            g = grouped[row["topic"]]
            for c in cols:
                g[c].append(int(row[c]))
    return {t: {c: np.asarray(v, dtype=np.int64) for c, v in g.items()} for t, g in grouped.items()}


def read_observer_csv(path) -> dict:
    return _read_grouped(Path(path), OBSERVER_COLS)


def read_published_time_csv(path) -> dict:
    return _read_grouped(Path(path), PUBLISHED_COLS)


def read_resources_csv(path) -> dict:
    """M3 resource samples, grouped by process (see benchmarks/README.md).

    Returns ``{process: {column: np.ndarray}}``; counters stay int64,
    percentages and rtf are float64. `rtf` is a property of the sample instant
    and so repeats across the processes sharing a `sample_system_ns` -- any one
    process's column is the series `evaluate_ceiling` consumes.
    """
    grouped: dict[str, dict[str, list]] = defaultdict(
        lambda: {c: [] for c in RESOURCE_INT_COLS + RESOURCE_FLOAT_COLS}
    )
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            g = grouped[row["process"]]
            for c in RESOURCE_INT_COLS:
                g[c].append(int(row[c]))
            for c in RESOURCE_FLOAT_COLS:
                g[c].append(float(row[c]))
    return {
        process: {
            **{c: np.asarray(g[c], dtype=np.int64) for c in RESOURCE_INT_COLS},
            **{c: np.asarray(g[c], dtype=np.float64) for c in RESOURCE_FLOAT_COLS},
        }
        for process, g in grouped.items()
    }


def _read_xy_csv(path) -> dict:
    """`topic,header_stamp_ns,x_m,y_m` grouped by topic; stamps int64,
    positions float64. Shared by odometry.csv and pose.csv, whose schemas
    are identical (see ODOM_INT_COLS)."""
    grouped = defaultdict(lambda: {c: [] for c in ODOM_INT_COLS + ODOM_FLOAT_COLS})
    with open(Path(path), newline="") as f:
        for row in csv.DictReader(f):
            g = grouped[row["topic"]]
            for c in ODOM_INT_COLS:
                g[c].append(int(row[c]))
            for c in ODOM_FLOAT_COLS:
                g[c].append(float(row[c]))
    return {
        t: {
            **{c: np.asarray(g[c], dtype=np.int64) for c in ODOM_INT_COLS},
            **{c: np.asarray(g[c], dtype=np.float64) for c in ODOM_FLOAT_COLS},
        }
        for t, g in grouped.items()
    }


def read_odometry_csv(path) -> dict:
    """odometry.csv grouped by topic; stamps int64, positions float64."""
    return _read_xy_csv(path)


def read_pose_csv(path) -> dict:
    """pose.csv grouped by topic; stamps int64, positions float64.

    Written by bench_observer's typed `pose` subscription
    (geometry_msgs/PoseWithCovarianceStamped) -- the NDT pose output. This is
    the source M5's `pose_error_m` is defined on (benchmarks/README.md, "M5
    definitions"): NDT pose minus CARLA ground truth (`gt.csv`), joined at
    nearest sim-time stamp within 25 ms. It is NOT interchangeable with
    odometry.csv's `/localization/kinematic_state`, which is the EKF-fused
    pose -- scoring pose_error on that would mask NDT error behind
    IMU/odometry fusion, which is why the two are separate files even though
    their schemas match.
    """
    return _read_xy_csv(path)


def read_tf_csv(path) -> dict:
    """tf.csv grouped by (topic, child_frame_id); stamps int64.

    Written by bench_observer's typed `tf` subscription
    (tf2_msgs/TFMessage), one row per transform matching the child_frame_id
    that cell's topic list registered. Returns
    ``{(topic, child_frame_id): {"header_stamp_ns": ndarray,
    "frame_ids": tuple}}``, where `frame_ids` is the sorted distinct set of
    PARENT frames seen for that pair -- the filter is on the child only, so
    the parent is recorded rather than assumed, and a consumer checking
    map->base_link asserts `frame_ids == ("map",)` instead of trusting it.
    A second parent appearing is then visible rather than folded into one
    rate.
    """
    stamps: dict[tuple[str, str], list[int]] = defaultdict(list)
    parents: dict[tuple[str, str], set[str]] = defaultdict(set)
    with open(Path(path), newline="") as f:
        for row in csv.DictReader(f):
            key = (row["topic"], row["child_frame_id"])
            stamps[key].append(int(row["header_stamp_ns"]))
            parents[key].add(row["frame_id"])
    return {
        key: {
            "header_stamp_ns": np.asarray(v, dtype=np.int64),
            "frame_ids": tuple(sorted(parents[key])),
        }
        for key, v in stamps.items()
    }


def read_gt_csv(path) -> dict:
    """gt.csv (ungrouped): {column: np.ndarray}."""
    cols = {c: [] for c in GT_INT_COLS + GT_FLOAT_COLS}
    with open(Path(path), newline="") as f:
        for row in csv.DictReader(f):
            for c in cols:
                cols[c].append(row[c])
    return {
        **{c: np.asarray(cols[c], dtype=np.int64) for c in GT_INT_COLS},
        **{c: np.asarray(cols[c], dtype=np.float64) for c in GT_FLOAT_COLS},
    }


def read_clock_csv(path):
    clock, wall = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            clock.append(int(row["clock_ns"]))
            wall.append(int(row["arrival_system_ns"]))
    return np.asarray(clock, dtype=np.int64), np.asarray(wall, dtype=np.int64)
