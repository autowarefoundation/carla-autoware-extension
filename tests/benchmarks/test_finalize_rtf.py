"""TDD tests for finalize_rtf.py: fills resources.csv's rtf column from
clock.csv, per the registered rule (benchmarks/README.md): for each
distinct sample_system_ns, find clock rows in [t-1s, t]; with >= 2 rows,
rtf = Δclock_ns/Δarrival_ns (clamped >= 0); else -1. The rewrite must be
atomic (tmp + rename) and leave every other column byte-identical.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest

from benchmarks.analysis.bench_io import read_resources_csv
from benchmarks.sampler.finalize_rtf import compute_rtf_series, finalize_rtf

RESOURCE_HEADER = (
    "sample_system_ns",
    "process",
    "cpu_pct",
    "rss_bytes",
    "gpu_util_pct",
    "vram_bytes",
    "rtf",
)

BASE = 1_700_000_000_000_000_000


def _write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _write_clock_csv(path, base_ns, n, step_ns, *, freeze_after=None):
    """n clock rows, arrival_system_ns advancing by step_ns each row.

    clock_ns advances the same amount every row unless freeze_after (a
    row index) is given, after which clock_ns holds at its last real
    value while arrival_system_ns keeps advancing -- simulating a
    publisher that keeps sending but whose sim clock has stalled.
    """
    rows = []
    clock = base_ns
    for i in range(n):
        arrival = base_ns + i * step_ns
        if freeze_after is None or i <= freeze_after:
            clock = base_ns + i * step_ns
        rows.append((clock, arrival))
    _write_csv(path, ("clock_ns", "arrival_system_ns"), rows)


def _write_resources_csv(path, sample_times, process="carla-server"):
    rows = [(t, process, 1.0, 100, -1, -1, -1) for t in sample_times]
    _write_csv(path, RESOURCE_HEADER, rows)


def test_samples_before_first_clock_stay_negative_one(tmp_path):
    clock_csv = tmp_path / "clock.csv"
    resources_csv = tmp_path / "resources.csv"
    _write_clock_csv(clock_csv, BASE, n=20, step_ns=100_000_000)  # 10 Hz, starts at BASE
    _write_resources_csv(resources_csv, [BASE - 2_000_000_000, BASE - 1_500_000_000])

    finalize_rtf(resources_csv, clock_csv)

    d = read_resources_csv(resources_csv)
    for v in d["carla-server"]["rtf"]:
        assert v == pytest.approx(-1.0)


def test_paced_clock_advancing_one_sim_second_per_wall_second_gives_rtf_near_one(tmp_path):
    clock_csv = tmp_path / "clock.csv"
    resources_csv = tmp_path / "resources.csv"
    # 10 Hz /clock, sim advances in lockstep with wall time -> RTF 1.0.
    _write_clock_csv(clock_csv, BASE, n=50, step_ns=100_000_000)
    sample_times = [BASE + s * 1_000_000_000 for s in (1, 2, 3)]
    _write_resources_csv(resources_csv, sample_times)

    finalize_rtf(resources_csv, clock_csv)

    d = read_resources_csv(resources_csv)
    for v in d["carla-server"]["rtf"]:
        assert v == pytest.approx(1.0, abs=1e-6)


def test_clock_that_stops_advancing_gives_rtf_zero_afterward(tmp_path):
    clock_csv = tmp_path / "clock.csv"
    resources_csv = tmp_path / "resources.csv"
    # Publisher keeps sending (arrival keeps advancing) but the sim
    # clock value freezes after row 20 (2.0 s of real advance).
    _write_clock_csv(clock_csv, BASE, n=50, step_ns=100_000_000, freeze_after=20)
    sample_times = [BASE + 4_000_000_000]  # well after the freeze point
    _write_resources_csv(resources_csv, sample_times)

    finalize_rtf(resources_csv, clock_csv)

    d = read_resources_csv(resources_csv)
    assert d["carla-server"]["rtf"][0] == pytest.approx(0.0, abs=1e-6)


def test_exactly_two_rows_with_zero_wall_time_separation_stays_negative_one():
    """Degenerate window: exactly 2 clock rows fall in [t-1s, t], so the
    hi-lo >= 2 gate passes, but both rows share the SAME
    arrival_system_ns (d_wall == 0 -- e.g. two /clock messages recorded
    with identical arrival timestamps). The `if d_wall > 0` guard must
    block this case rather than divide by zero or fabricate a rate: rtf
    stays at the -1 sentinel. This is the safer of the two possible
    behaviours (no invented number on a degenerate window) and is
    exercised directly here at the compute_rtf_series level, since
    bench_observer's own clock.csv is receipt-ordered and would never
    itself produce two identical arrival timestamps.
    """
    sample_ns = np.array([BASE + 1_000_000_000], dtype=np.int64)
    clock_ns = np.array([500_000_000, 600_000_000], dtype=np.int64)
    arrival_ns = np.array([BASE, BASE], dtype=np.int64)  # identical -> d_wall == 0

    out = compute_rtf_series(sample_ns, clock_ns, arrival_ns)

    assert out[0] == -1.0


def test_finalize_preserves_other_columns_and_row_order_and_is_atomic(tmp_path):
    clock_csv = tmp_path / "clock.csv"
    resources_csv = tmp_path / "resources.csv"
    _write_clock_csv(clock_csv, BASE, n=50, step_ns=100_000_000)
    t1 = BASE + 1_000_000_000
    t2 = BASE + 2_000_000_000
    rows = [
        (t1, "carla-server", 12.5, 1000, -1, -1, -1),
        (t1, "autoware", 8.25, 2000, 30.0, 512, -1),
        (t2, "carla-server", 13.0, 1050, -1, -1, -1),
    ]
    _write_csv(resources_csv, RESOURCE_HEADER, rows)

    finalize_rtf(resources_csv, clock_csv)

    with open(resources_csv, newline="") as f:
        out_rows = list(csv.reader(f))
    assert out_rows[0] == list(RESOURCE_HEADER)
    assert len(out_rows) - 1 == len(rows)  # row count / order preserved
    for orig, out in zip(rows, out_rows[1:]):
        # every column except rtf (last) must be byte-identical to the source
        assert [str(v) for v in orig[:-1]] == out[:-1]
        assert out[-1] != "-1"  # clock data covers this window: rtf got filled in

    # atomic rewrite: no leftover temp file next to the target
    assert not (tmp_path / "resources.csv.tmp").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clock.csv", "resources.csv"]


def test_finalize_on_header_only_file_is_a_no_op(tmp_path):
    clock_csv = tmp_path / "clock.csv"
    resources_csv = tmp_path / "resources.csv"
    _write_clock_csv(clock_csv, BASE, n=5, step_ns=100_000_000)
    _write_csv(resources_csv, RESOURCE_HEADER, [])

    finalize_rtf(resources_csv, clock_csv)

    with open(resources_csv, newline="") as f:
        out_rows = list(csv.reader(f))
    assert out_rows == [list(RESOURCE_HEADER)]
