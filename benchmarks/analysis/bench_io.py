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


def read_clock_csv(path):
    clock, wall = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            clock.append(int(row["clock_ns"]))
            wall.append(int(row["arrival_system_ns"]))
    return np.asarray(clock, dtype=np.int64), np.asarray(wall, dtype=np.int64)
