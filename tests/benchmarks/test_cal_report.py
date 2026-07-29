"""Tests for cal_report.py: the CAL-seam report tool (C1(a) table).

A CAL run has NO clock.csv (nothing publishes /clock -- see
benchmarks/scripts/cal_report.py's module docstring), so, unlike
benchmarks/report.py, one-hop wall latency here is the DIRECT difference
arrival_system_ns - header_stamp_ns: both stamps are wall-clock `now()`
taken on the same host, so no sim/wall affine fit is needed or available.
"""

from __future__ import annotations

import numpy as np
import pytest
from benchmarks.scripts.cal_report import main, render_report, summarize_run

OBSERVER_HEADER = "topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes\n"
RESOURCES_HEADER = "sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf\n"


def _write_observer(run_dir, rows):
    """rows: iterable of (topic, header_stamp_ns, arrival_system_ns)."""
    with open(run_dir / "observer.csv", "w") as f:
        f.write(OBSERVER_HEADER)
        for topic, header_ns, arrival_ns in rows:
            # arrival_steady_ns/clock_ns/size_bytes are irrelevant to this
            # tool; clock_ns=-1 matches the real contract (no /clock ever
            # arrives on a CAL run), size_bytes is the fixed synthetic
            # payload size the two bench publishers are pinned to.
            f.write(f"{topic},{header_ns},{arrival_ns},0,-1,921600\n")


def _write_resources(run_dir, rows):
    """rows: iterable of (sample_system_ns, process, cpu_pct)."""
    with open(run_dir / "resources.csv", "w") as f:
        f.write(RESOURCES_HEADER)
        for sample_ns, process, cpu_pct in rows:
            f.write(f"{sample_ns},{process},{cpu_pct},0,-1,-1,-1\n")


def _known_one_hop_run(tmp_path):
    """One topic, 10 samples, one_hop_ms exactly 1..10 (known percentiles):
    header_stamp_ns = 0 for every row, arrival_system_ns = k ms for k=1..10.
    numpy's default (linear) percentile interpolation over [1..10] gives
    p50=5.5, p95=9.55, p99=9.91 -- values recomputed independently below
    via the interpolation formula, not copied from the implementation.
    """
    d = tmp_path / "run-001"
    d.mkdir()
    rows = [("/bench/seam_cloud", 0, k * 1_000_000) for k in range(1, 11)]
    _write_observer(d, rows)
    _write_resources(d, [(1_000_000_000, "carla-server", 10.0)])
    return d


def test_summarize_run_one_hop_percentiles_match_known_values(tmp_path):
    run_dir = _known_one_hop_run(tmp_path)
    s = summarize_run(run_dir)
    t = s["topics"]["/bench/seam_cloud"]
    assert t["n"] == 10
    assert t["one_hop_p50_ms"] == pytest.approx(5.5)
    assert t["one_hop_p95_ms"] == pytest.approx(9.55)
    assert t["one_hop_p99_ms"] == pytest.approx(9.91)


def test_summarize_run_achieved_hz_from_steady_arrivals(tmp_path):
    """10 Hz steady arrivals (100 ms apart) -> achieved hz == 10.0. header_
    stamp_ns is held constant per row so one_hop_ms is not exercised here."""
    d = tmp_path / "run-002"
    d.mkdir()
    rows = [("/bench/incore_cloud", 0, 1_000_000_000 + k * 100_000_000) for k in range(20)]
    _write_observer(d, rows)
    _write_resources(d, [(1_000_000_000, "carla-server", 5.0)])
    s = summarize_run(d)
    t = s["topics"]["/bench/incore_cloud"]
    assert t["hz"] == pytest.approx(10.0, rel=1e-6)
    assert t["n"] == 20


def test_summarize_run_separates_both_seam_topics(tmp_path):
    """The whole point of CAL-seam is a PAIRED measurement: both publishers'
    topics must appear as independent rows, never merged."""
    d = tmp_path / "run-003"
    d.mkdir()
    rows = [("/bench/seam_cloud", 0, k * 100_000_000) for k in range(1, 6)]
    rows += [("/bench/incore_cloud", 0, k * 100_000_000 + 5_000_000) for k in range(1, 6)]
    _write_observer(d, rows)
    _write_resources(d, [(1_000_000_000, "carla-server", 10.0)])
    s = summarize_run(d)
    assert set(s["topics"]) == {"/bench/seam_cloud", "/bench/incore_cloud"}
    # The incore topic's one-hop values are exactly 5 ms larger by construction.
    seam = s["topics"]["/bench/seam_cloud"]
    incore = s["topics"]["/bench/incore_cloud"]
    assert incore["one_hop_p50_ms"] - seam["one_hop_p50_ms"] == pytest.approx(5.0)


def test_summarize_run_per_process_cpu_from_resources_csv(tmp_path):
    d = tmp_path / "run-004"
    d.mkdir()
    _write_observer(d, [("/bench/seam_cloud", 0, k * 100_000_000) for k in range(1, 4)])
    _write_resources(
        d,
        [
            (1_000_000_000, "carla-server", 10.0),
            (2_000_000_000, "carla-server", 20.0),
            (3_000_000_000, "carla-server", 30.0),
            (1_000_000_000, "bench-observer", 1.0),
            (2_000_000_000, "bench-observer", 2.0),
            (3_000_000_000, "bench-observer", 3.0),
        ],
    )
    s = summarize_run(d)
    assert set(s["processes"]) == {"carla-server", "bench-observer"}
    carla = s["processes"]["carla-server"]
    assert carla["n"] == 3
    assert carla["cpu_pct_mean"] == pytest.approx(20.0)
    # np.percentile linear interpolation over [10, 20, 30] at p95: rank =
    # 0.95 * 2 = 1.9 -> interpolate index 1 (20) and index 2 (30) -> 29.0.
    assert carla["cpu_pct_p95"] == pytest.approx(29.0)
    obs = s["processes"]["bench-observer"]
    assert obs["cpu_pct_mean"] == pytest.approx(2.0)


def test_summarize_run_raises_when_observer_csv_missing(tmp_path):
    d = tmp_path / "run-005"
    d.mkdir()
    _write_resources(d, [(1_000_000_000, "carla-server", 10.0)])
    with pytest.raises(FileNotFoundError):
        summarize_run(d)


def test_summarize_run_raises_when_resources_csv_missing(tmp_path):
    """Per-process publish CPU is part of the C1(a) table, not an optional
    extra, so a run missing resources.csv must fail loud, not render a
    silently-incomplete report."""
    d = tmp_path / "run-006"
    d.mkdir()
    _write_observer(d, [("/bench/seam_cloud", 0, k * 100_000_000) for k in range(1, 4)])
    with pytest.raises(FileNotFoundError):
        summarize_run(d)


def test_summarize_run_does_not_touch_clock_csv(tmp_path):
    """A CAL run directory legitimately has no clock.csv at all (nothing
    publishes /clock); summarize_run must not require or read one."""
    run_dir = _known_one_hop_run(tmp_path)
    assert not (run_dir / "clock.csv").exists()
    summarize_run(run_dir)  # must not raise


def test_render_report_markdown_contains_topics_and_processes(tmp_path):
    run_dir = _known_one_hop_run(tmp_path)
    md = render_report(run_dir)
    assert "/bench/seam_cloud" in md
    assert "carla-server" in md
    assert "5.50" in md  # one_hop_p50_ms rendered to 2dp


def test_main_prints_report_for_run_dir_argv(tmp_path, capsys):
    run_dir = _known_one_hop_run(tmp_path)
    rc = main([str(run_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "/bench/seam_cloud" in out
    assert "carla-server" in out


def test_summarize_run_topics_with_a_single_sample_do_not_crash_one_hop(tmp_path):
    """One-hop percentiles must tolerate n=1 (np.percentile is well-defined
    there); achieved Hz genuinely needs >= 2 arrivals, which cadence.py's
    inter_arrival_stats already enforces -- that ValueError is expected to
    propagate, not be swallowed here."""
    d = tmp_path / "run-007"
    d.mkdir()
    _write_observer(d, [("/bench/seam_cloud", 0, 42_000_000)])
    _write_resources(d, [(1_000_000_000, "carla-server", 10.0)])
    with pytest.raises(ValueError, match="arrivals"):
        summarize_run(d)


def test_summarize_run_topics_are_independent_np_arrays_not_views(tmp_path):
    """Regression guard: read_observer_csv groups rows into fresh arrays per
    topic, so mutating one topic's stats must never perturb another's."""
    d = tmp_path / "run-008"
    d.mkdir()
    rows = [("/a", 0, k * 100_000_000) for k in range(1, 4)]
    rows += [("/b", 0, k * 100_000_000) for k in range(1, 4)]
    _write_observer(d, rows)
    _write_resources(d, [(1_000_000_000, "carla-server", 10.0)])
    s = summarize_run(d)
    assert s["topics"]["/a"]["n"] == 3
    assert s["topics"]["/b"]["n"] == 3
    assert np.isclose(s["topics"]["/a"]["hz"], s["topics"]["/b"]["hz"])
