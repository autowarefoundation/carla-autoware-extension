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


def read_clock_csv(path):
    clock, wall = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            clock.append(int(row["clock_ns"]))
            wall.append(int(row["arrival_system_ns"]))
    return np.asarray(clock, dtype=np.int64), np.asarray(wall, dtype=np.int64)
