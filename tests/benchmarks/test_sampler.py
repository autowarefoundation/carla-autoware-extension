"""TDD tests for the M3 resource sampler's /proc CPU+RSS math, cgroup
reads, GPU aggregation, and the resources.csv row formatter.

None of this exercises pgrep/docker/nvidia-smi directly -- those are
thin subprocess wrappers covered live by the Step-4 smoke run (see the
task report), not by this suite. Every test here drives real files (a
fake --proc-root, fake cgroup files) or real dict math, never a mock.
"""

from __future__ import annotations

import csv

import pytest

from benchmarks.sampler.sample_resources import (
    RESOURCE_COLUMNS,
    compute_cgroup_cpu_pct,
    compute_cpu_pct,
    elapsed_since,
    format_row,
    gpu_totals_for_pids,
    read_cgroup_cpu_usec,
    read_cgroup_memory_current,
    read_cgroup_pids,
    read_loadavg_1m,
    read_pid_cpu_ticks,
    read_pid_rss_bytes,
    sample_pids_cpu_rss,
)


def _write_stat(pid_dir, utime, stime):
    """A minimal but format-correct /proc/<pid>/stat line.

    Fields after the comm's closing ')': state ppid pgrp session tty_nr
    tpgid flags minflt cminflt majflt cmajflt utime stime ... -- utime
    and stime are the 12th/13th fields in that tail, which is what
    read_pid_cpu_ticks parses.
    """
    pid_dir.mkdir(parents=True, exist_ok=True)
    line = f"1 (proc) S 1 1 1 0 -1 0 0 0 0 0 {utime} {stime} 0 0 0 0 0 0 0 0\n"
    (pid_dir / "stat").write_text(line)


def _write_statm(pid_dir, resident_pages):
    pid_dir.mkdir(parents=True, exist_ok=True)
    (pid_dir / "statm").write_text(f"1000 {resident_pages} 100 5 0 100 0\n")


# ---------------------------------------------------------------------------
# /proc CPU math (Step 1: two synthetic stat snapshots -> expected cpu_pct)
# ---------------------------------------------------------------------------


def test_read_pid_cpu_ticks_parses_utime_plus_stime(tmp_path):
    _write_stat(tmp_path / "111", utime=1000, stime=500)
    assert read_pid_cpu_ticks(111, str(tmp_path)) == 1500


def test_cpu_pct_from_two_snapshots_one_second_apart(tmp_path):
    pid_dir = tmp_path / "111"
    _write_stat(pid_dir, utime=1000, stime=500)  # snapshot 0: 1500 ticks
    ticks0 = read_pid_cpu_ticks(111, str(tmp_path))

    _write_stat(pid_dir, utime=1100, stime=550)  # snapshot 1: 1650 ticks
    ticks1 = read_pid_cpu_ticks(111, str(tmp_path))

    # delta 150 ticks / 100 CLK_TCK / 1.0 s interval * 100 = 150% (1.5 cores)
    pct = compute_cpu_pct({111: ticks0}, {111: ticks1}, interval_s=1.0, clk_tck=100)
    assert pct == pytest.approx(150.0)


def test_cpu_pct_sums_across_multiple_pids():
    prev = {1: 100, 2: 200}
    curr = {1: 150, 2: 260}  # deltas 50 + 60 = 110 ticks
    pct = compute_cpu_pct(prev, curr, interval_s=1.0, clk_tck=100)
    assert pct == pytest.approx(110.0)


def test_cpu_pct_new_pid_with_no_baseline_contributes_zero():
    # pid 2 is freshly resolved this sample (e.g. a restarted process);
    # it has no earlier baseline, so it must not blow up the delta.
    prev = {1: 100}
    curr = {1: 150, 2: 999}
    pct = compute_cpu_pct(prev, curr, interval_s=1.0, clk_tck=100)
    assert pct == pytest.approx(50.0)


def test_cpu_pct_rejects_non_positive_interval():
    with pytest.raises(ValueError):
        compute_cpu_pct({1: 0}, {1: 10}, interval_s=0.0, clk_tck=100)


# ---------------------------------------------------------------------------
# elapsed_since: cpu_pct must divide by the MEASURED wall-clock gap
# between successive samples for a label, not the nominal --interval --
# a sampling cycle (N pgrep/docker calls + two nvidia-smi calls, each
# with its own timeout) can overrun the nominal interval, and dividing
# by the unchanged nominal value would then overstate cpu_pct, worst
# exactly under the load the sampler exists to characterise.
# ---------------------------------------------------------------------------


def test_elapsed_since_first_sample_falls_back_to_nominal():
    # No prior timestamp for this label yet -- any positive divisor is
    # fine since compute_cpu_pct reports 0% with no tick baseline
    # either; the nominal interval is used only to satisfy
    # compute_cpu_pct's interval_s > 0 requirement.
    assert elapsed_since(None, now_mono=1000.0, fallback_s=1.0) == 1.0


def test_elapsed_since_returns_measured_delta_not_the_fallback():
    assert elapsed_since(prev_mono=1000.0, now_mono=1002.5, fallback_s=1.0) == pytest.approx(2.5)


def test_cpu_pct_follows_measured_elapsed_when_a_cycle_overruns_the_nominal_interval():
    """End-to-end simulation of run()'s per-label wiring (prev_sample_mono
    -> elapsed_since -> compute_cpu_pct), reproducing the exact scenario
    the finding describes: a slow cycle makes the real gap since the
    previous sample exceed the nominal --interval, and cpu_pct must
    follow the measured gap, not the unchanged nominal one.
    """
    nominal_interval_s = 1.0
    prev_sample_mono = {}
    label = "carla-server"

    # First sample: no baseline (timestamp or ticks) yet -> 0%.
    t0 = 1000.0
    elapsed0 = elapsed_since(prev_sample_mono.get(label), t0, nominal_interval_s)
    first_ticks = {1: 1000}
    cpu0 = compute_cpu_pct({}, first_ticks, elapsed0, clk_tck=100)
    assert cpu0 == 0.0
    prev_sample_mono[label] = t0

    # Second sample: the cycle overran to 2.5 s of REAL elapsed time,
    # not the nominal 1.0 s.
    t1 = t0 + 2.5
    elapsed1 = elapsed_since(prev_sample_mono.get(label), t1, nominal_interval_s)
    assert elapsed1 == pytest.approx(2.5)
    next_ticks = {1: 1250}  # +250 ticks over the measured 2.5 s
    cpu1 = compute_cpu_pct(first_ticks, next_ticks, elapsed1, clk_tck=100)
    # 250 ticks / 100 CLK_TCK / 2.5 s * 100 = 100%. Dividing by the
    # nominal 1.0 s instead (the bug) would report 250%.
    assert cpu1 == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# RSS from /proc/<pid>/statm
# ---------------------------------------------------------------------------


def test_read_pid_rss_bytes_from_statm(tmp_path):
    _write_statm(tmp_path / "222", resident_pages=250)
    assert read_pid_rss_bytes(222, str(tmp_path), page_size=4096) == 250 * 4096


def test_sample_pids_cpu_rss_skips_pid_that_exited(tmp_path):
    _write_stat(tmp_path / "1", utime=10, stime=5)
    _write_statm(tmp_path / "1", resident_pages=100)
    # pid 2 has no directory at all -- simulates a PID pgrep resolved a
    # moment ago that has since exited.
    ticks, rss = sample_pids_cpu_rss([1, 2], str(tmp_path), page_size=4096)
    assert ticks == {1: 15}
    assert rss == 100 * 4096


def test_sample_pids_cpu_rss_skips_pid_with_truncated_stat_file(tmp_path):
    # A short/truncated /proc/<pid>/stat (fewer fields than a real one
    # has, e.g. read mid-fork or mid-exit) must not crash the whole
    # sampling run via an uncaught IndexError -- it is the same kind of
    # transient race as a pid that has already exited (the case above),
    # not a fatal error.
    pid_dir = tmp_path / "3"
    pid_dir.mkdir(parents=True)
    (pid_dir / "stat").write_text("3 (proc) S 1 1 1\n")  # far too few fields
    (pid_dir / "statm").write_text("100 10 5 0 0 5 0\n")
    ticks, rss = sample_pids_cpu_rss([3], str(tmp_path), page_size=4096)
    assert ticks == {}
    assert rss == 0


# ---------------------------------------------------------------------------
# cgroup v2 reads (containers)
# ---------------------------------------------------------------------------


def test_read_cgroup_cpu_usec_and_memory_and_procs(tmp_path):
    cg = tmp_path / "docker-abc123.scope"
    cg.mkdir()
    (cg / "cpu.stat").write_text("usage_usec 123456\nuser_usec 100000\nsystem_usec 23456\n")
    (cg / "memory.current").write_text("104857600\n")
    (cg / "cgroup.procs").write_text("111\n222\n")

    cg_dir = str(cg) + "/"
    assert read_cgroup_cpu_usec(cg_dir) == 123456
    assert read_cgroup_memory_current(cg_dir) == 104857600
    assert read_cgroup_pids(cg_dir) == [111, 222]


def test_read_cgroup_helpers_return_none_or_empty_when_missing(tmp_path):
    missing = str(tmp_path / "does-not-exist") + "/"
    assert read_cgroup_cpu_usec(missing) is None
    assert read_cgroup_memory_current(missing) is None
    assert read_cgroup_pids(missing) == []


def test_compute_cgroup_cpu_pct():
    # 500_000 usec delta over a 1.0 s interval = 0.5 core-second = 50%
    assert compute_cgroup_cpu_pct(1_000_000, 1_500_000, 1.0) == pytest.approx(50.0)


def test_compute_cgroup_cpu_pct_with_no_baseline_is_zero():
    assert compute_cgroup_cpu_pct(None, 1_500_000, 1.0) == 0.0


# ---------------------------------------------------------------------------
# GPU aggregation over a PID list
# ---------------------------------------------------------------------------


def test_gpu_totals_for_pids_sums_hits():
    vram_map = {10: 100 * 1024 * 1024, 20: 50 * 1024 * 1024}
    sm_map = {10: 25.0}
    sm, vram = gpu_totals_for_pids([10, 20], vram_map, sm_map)
    assert vram == 150 * 1024 * 1024
    assert sm == pytest.approx(25.0)  # only pid 10 reported an sm sample


def test_gpu_totals_for_pids_reports_sentinel_when_no_pid_has_gpu_context():
    sm, vram = gpu_totals_for_pids([99], {10: 1}, {10: 1.0})
    assert sm == -1.0
    assert vram == -1


def test_gpu_totals_for_pids_empty_pid_list_is_sentinel():
    sm, vram = gpu_totals_for_pids([], {10: 1}, {10: 1.0})
    assert sm == -1.0
    assert vram == -1


# ---------------------------------------------------------------------------
# /proc/loadavg: the host-wide in-run load series (added to the resources.csv
# contract 2026-07-30). Read through --proc-root, like the CPU math above, so
# these drive real files rather than a mock.
# ---------------------------------------------------------------------------


def test_read_loadavg_1m_reads_the_first_field(tmp_path):
    (tmp_path / "loadavg").write_text("25.80 18.42 12.03 3/1892 40771\n")
    assert read_loadavg_1m(str(tmp_path)) == pytest.approx(25.80)


def test_read_loadavg_1m_takes_the_one_minute_figure_not_a_smoother_one(tmp_path):
    """Field 1, deliberately. `preflight.sh` gates on exactly this field
    (`awk '{print $1}' /proc/loadavg`), so the in-run series is on the same
    basis as the pre-run gate; and Task 13's ad hoc 2 s sampling recorded the
    same field (mean 25.80, peak 50.05 on results/B/run-009), so the new series
    is comparable with the figures already in the record. Fields 2 and 3 are
    the 5- and 15-minute averages: over a run of this length they are dominated
    by load from BEFORE the run started, which is the opposite of the question.
    """
    (tmp_path / "loadavg").write_text("64.00 1.00 1.00 3/1892 40771\n")
    assert read_loadavg_1m(str(tmp_path)) == pytest.approx(64.00)


def test_read_loadavg_1m_missing_file_is_the_not_applicable_sentinel(tmp_path):
    """-1, NOT 0.0. A real 0.0 would state that the host was idle at that
    instant, and the finding this series exists to record is that it never is
    during a run -- so an unreadable sample must not be able to drag a mean
    downward while looking like data."""
    assert read_loadavg_1m(str(tmp_path)) == -1.0


def test_read_loadavg_1m_unparsable_content_is_the_sentinel(tmp_path):
    """An empty or malformed /proc/loadavg must not end the sampling run: the
    sampler is a background recorder, and killing it loses the whole M3 series
    for a live run over one bad read."""
    (tmp_path / "loadavg").write_text("\n")
    assert read_loadavg_1m(str(tmp_path)) == -1.0
    (tmp_path / "loadavg").write_text("not-a-number 1.0 1.0\n")
    assert read_loadavg_1m(str(tmp_path)) == -1.0


# ---------------------------------------------------------------------------
# Row formatter: column order must match the resources.csv contract exactly
# (benchmarks/README.md: sample_system_ns,process,cpu_pct,rss_bytes,
#  gpu_util_pct,vram_bytes,rtf,loadavg_1m)
# ---------------------------------------------------------------------------


def test_resource_columns_matches_the_registered_contract():
    assert RESOURCE_COLUMNS == (
        "sample_system_ns",
        "process",
        "cpu_pct",
        "rss_bytes",
        "gpu_util_pct",
        "vram_bytes",
        "rtf",
        "loadavg_1m",
    )


def test_loadavg_is_appended_last_so_the_old_header_stays_a_prefix():
    """A LEGIBILITY convention, deliberately NOT a correctness mechanism.

    Appending keeps the pre-2026-07-30 header a strict PREFIX of the contract,
    so a diff of an already-filed run against a new one shows one ADDED column
    rather than a shifted table -- and those runs are retained evidence that
    has to stay comparable by eye.

    What it is NOT: the reason the readers survive both formats. That is
    name-based access on both sides -- `csv.DictReader` in
    `bench_io.read_resources_csv`, and `header.index(...)` in
    `finalize_rtf.py`, which is position-INDEPENDENT and is pinned directly by
    test_finalize_rtf.py's shuffled-header test. An earlier revision of this
    docstring claimed position was load-bearing; that would have licensed a
    reader to believe reordering is unsafe, or that appending anywhere else
    would break a consumer. Neither is true."""
    assert RESOURCE_COLUMNS[-1] == "loadavg_1m"
    assert RESOURCE_COLUMNS[:-1] == (
        "sample_system_ns",
        "process",
        "cpu_pct",
        "rss_bytes",
        "gpu_util_pct",
        "vram_bytes",
        "rtf",
    )


def test_format_row_matches_contract_column_order():
    row = format_row(
        sample_system_ns=123,
        process="carla-server",
        cpu_pct=45.6,
        rss_bytes=789,
        gpu_util_pct=12.3,
        vram_bytes=456,
        rtf=-1,
        loadavg_1m=25.8,
    )
    assert row == [123, "carla-server", 45.6, 789, 12.3, 456, -1, 25.8]


def test_format_row_written_by_csv_writer_round_trips_in_order(tmp_path):
    """End-to-end: format_row's output through a real csv.writer produces
    a header-matching row, read back via csv.DictReader in the exact
    registered column names."""
    out = tmp_path / "resources.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(RESOURCE_COLUMNS)
        w.writerow(format_row(1_000, "carla-server", 10.0, 2000, -1, -1, -1, 25.8))

    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows == [
        {
            "sample_system_ns": "1000",
            "process": "carla-server",
            "cpu_pct": "10.0",
            "rss_bytes": "2000",
            "gpu_util_pct": "-1",
            "vram_bytes": "-1",
            "rtf": "-1",
            "loadavg_1m": "25.8",
        }
    ]


def test_one_loadavg_read_per_cycle_repeats_across_every_process_row(tmp_path, monkeypatch):
    """loadavg is host-wide, so it is sampled ONCE per cycle and stamped onto
    every process row of that cycle -- the same shape as rtf. Sampling it
    per-process would put N reads of a shared quantity in one sample instant
    and invite a reader to attribute it to a process.
    """
    from benchmarks.sampler import sample_resources as sr

    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    (proc_root / "loadavg").write_text("31.50 20.0 10.0 3/1892 1\n")
    processes = tmp_path / "processes.yaml"
    processes.write_text(
        "processes:\n  - {label: carla-server, pattern: nothing-matches-this}\n"
        "  - {label: observer, pattern: nothing-matches-this-either}\n"
    )
    out = tmp_path / "resources.csv"

    reads = {"n": 0}
    real = sr.read_loadavg_1m

    def counting(root):
        reads["n"] += 1
        return real(root)

    monkeypatch.setattr(sr, "read_loadavg_1m", counting)
    # Exactly one cycle, then stop. run() loops on the SIGTERM flag, which
    # _sleep_until is the only place a test can reach -- so set it there.
    #
    # `interval_s` must be LONG enough that the cycle finishes inside it: when
    # a cycle overruns its interval run() takes the resync branch and never
    # calls _sleep_until at all, which is an infinite loop here. 60 s never
    # elapses, because the patched _sleep_until returns immediately.
    monkeypatch.setattr(
        sr, "_sleep_until", lambda target, stop_flag, chunk_s=0.1: stop_flag.update(stop=True)
    )
    sr.run(processes, out, interval_s=60.0, proc_root=str(proc_root))

    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert reads["n"] == 1, "one host-wide read per cycle, not one per process"
    assert len(rows) == 2
    assert {r["loadavg_1m"] for r in rows} == {"31.5"}
    assert len({r["sample_system_ns"] for r in rows}) == 1
