#!/usr/bin/env python3
"""Fill resources.csv's rtf column from clock.csv (M3 finalize step).

sample_resources.py is deliberately ROS-free and writes rtf as -1 for
every row; this script computes the real per-sample RTF from the
observer's clock.csv and rewrites resources.csv in place, atomically
(tmp file in the same directory + os.replace).

Rule (benchmarks/README.md): for each distinct sample_system_ns, find
the clock.csv rows with arrival_system_ns in [t-1s, t]. With >= 2 such
rows, rtf = Δclock_ns/Δarrival_ns over the window, clamped to >= 0.
Otherwise rtf stays -1 (before the first /clock, or too sparse a
window to form a delta). rtf is a property of the sample instant, not
of the process, so every row sharing a sample_system_ns gets the same
value -- exactly the per-sample series analysis/ceiling.py's
evaluate_ceiling consumes.
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import numpy as np

from benchmarks.analysis.bench_io import read_clock_csv

RTF_WINDOW_NS = 1_000_000_000  # 1 s trailing window, per the registered rule
NOT_APPLICABLE = -1.0


def compute_rtf_series(
    sample_ns: np.ndarray, clock_ns: np.ndarray, arrival_ns: np.ndarray
) -> np.ndarray:
    """Per-sample rtf: Δclock_ns/Δarrival_ns over clock rows in [t-1s, t].

    Needs >= 2 clock rows inside the window to form a delta; otherwise
    the sample keeps the -1 sentinel. The ratio is clamped to >= 0 so a
    momentarily out-of-order clock receipt or a stalled clock cannot
    report a negative rate.
    """
    order = np.argsort(arrival_ns)
    a = np.asarray(arrival_ns, dtype=np.int64)[order]
    c = np.asarray(clock_ns, dtype=np.int64)[order]
    sample_ns = np.asarray(sample_ns, dtype=np.int64)

    out = np.full(sample_ns.shape, NOT_APPLICABLE, dtype=np.float64)
    for i, t in enumerate(sample_ns):
        lo = np.searchsorted(a, t - RTF_WINDOW_NS, side="left")
        hi = np.searchsorted(a, t, side="right")
        if hi - lo >= 2:
            d_wall = a[hi - 1] - a[lo]
            if d_wall > 0:
                d_clock = c[hi - 1] - c[lo]
                out[i] = max(0.0, d_clock / d_wall)
    return out


def _format_rtf(value: float) -> str:
    return "-1" if value < 0 else f"{value:.6f}"


def finalize_rtf(resources_path, clock_path) -> None:
    resources_path = Path(resources_path)
    with open(resources_path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError(f"{resources_path} has no header row")
    header, data = rows[0], rows[1:]
    if not data:
        return  # header-only file: nothing to finalize

    sample_idx = header.index("sample_system_ns")
    rtf_idx = header.index("rtf")

    clock_ns, arrival_ns = read_clock_csv(clock_path)
    row_sample_ns = np.array([int(r[sample_idx]) for r in data], dtype=np.int64)
    unique_samples, inverse = np.unique(row_sample_ns, return_inverse=True)
    rtf_by_unique = compute_rtf_series(unique_samples, clock_ns, arrival_ns)

    for row, u_idx in zip(data, inverse):
        row[rtf_idx] = _format_rtf(float(rtf_by_unique[u_idx]))

    # Atomic rewrite: write to a tmp file in the SAME directory (so the
    # rename below is on one filesystem, never a cross-device copy),
    # then os.replace -- POSIX guarantees that rename is atomic, so a
    # reader never observes a half-written resources.csv.
    tmp_path = resources_path.parent / (resources_path.name + ".tmp")
    with open(tmp_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data)
    os.replace(tmp_path, resources_path)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Fill resources.csv's rtf column from clock.csv.")
    p.add_argument("--resources", required=True, type=Path)
    p.add_argument("--clock", required=True, type=Path)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    finalize_rtf(args.resources, args.clock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
