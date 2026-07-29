"""Tests for the primary A/B duel equivalence verdict tool.

Two layers are exercised: the pure statistics/rendering core
(`verdict_row`, `render_table`) with synthetic run-level VALUES (no
filesystem), and the aggregation layer (`cell_run_values`,
`build_verdict_table`, the concrete extractors) with synthetic run-*
DIRECTORIES built the same way tests/benchmarks/test_report.py does.
"""

from pathlib import Path

import numpy as np
import pytest
import yaml
from benchmarks.analysis.manifest import RunManifest
from benchmarks.scripts.duel_verdict import (
    CONTROL_TOPIC,
    DEFAULT_CARLA_PROCESS_LABEL,
    LIDAR_TOPIC,
    NDT_TOPIC,
    MetricUnavailableError,
    build_extractors,
    build_verdict_table,
    cell_run_values,
    extract_achieved_rate_ratio,
    extract_carla_process_cpu_pct,
    extract_control_staleness_ms,
    extract_lidar_to_ndt_sim_ms,
    extract_one_hop_wall_ms,
    render_table,
    verdict_row,
)

# ---------------------------------------------------------------------------
# Layer 1: pure statistics/rendering core, synthetic run-level VALUES only.
# Values below are constructed to land the bootstrap CI (pinned seed
# 20260727) FAR from any branch boundary, per the task brief: not a
# borderline case that could flip on a reseed.
# ---------------------------------------------------------------------------


def test_verdict_row_parity():
    a = [10.0, 10.1, 9.9, 10.05, 9.95, 10.02, 9.98, 10.03, 9.97, 10.01]
    b = [10.2, 10.3, 10.1, 10.25, 10.15, 10.22, 10.18, 10.23, 10.17, 10.21]
    row = verdict_row("m", a, b, margin=2.0)
    assert row.verdict == "parity"
    assert row.ci[0] > -2.0 and row.ci[1] < 2.0
    assert row.delta_median == pytest.approx(-0.2, abs=1e-6)
    assert row.n_a == 10 and row.n_b == 10


def test_verdict_row_a_better():
    a = [5.0, 5.1, 4.9, 5.05, 4.95, 5.02, 4.98, 5.03, 4.97, 5.01]
    b = [12.0, 12.1, 11.9, 12.05, 11.95, 12.02, 11.98, 12.03, 11.97, 12.01]
    row = verdict_row("m", a, b, margin=2.0)
    assert row.verdict == "a_better"
    assert row.ci[1] < 0.0


def test_verdict_row_b_better():
    a = [20.0, 20.1, 19.9, 20.05, 19.95, 20.02, 19.98, 20.03, 19.97, 20.01]
    b = [8.0, 8.1, 7.9, 8.05, 7.95, 8.02, 7.98, 8.03, 7.97, 8.01]
    row = verdict_row("m", a, b, margin=2.0)
    assert row.verdict == "b_better"
    assert row.ci[0] > 0.0


def test_verdict_row_inconclusive():
    a = [10.0, 30.0, 5.0, 25.0, 12.0, 28.0, 8.0, 22.0, 15.0, 20.0]
    b = [11.0, 29.0, 6.0, 24.0, 13.0, 27.0, 9.0, 21.0, 16.0, 19.0]
    row = verdict_row("m", a, b, margin=2.0)
    assert row.verdict == "inconclusive"
    # CI straddles both -margin and +margin -- not a narrow near-miss.
    assert row.ci[0] < -2.0 < row.ci[1] and row.ci[0] < 2.0 < row.ci[1]


def test_verdict_row_is_deterministic_across_calls():
    a = [10.0, 30.0, 5.0, 25.0, 12.0, 28.0, 8.0, 22.0, 15.0, 20.0]
    b = [11.0, 29.0, 6.0, 24.0, 13.0, 27.0, 9.0, 21.0, 16.0, 19.0]
    r1 = verdict_row("m", a, b, margin=2.0)
    r2 = verdict_row("m", a, b, margin=2.0)
    assert r1.ci == r2.ci
    assert r1.verdict == r2.verdict


def test_verdict_row_under_n_is_flagged_not_silent():
    """A cell with fewer than the pre-registered n >= 10 still gets a
    verdict (the statistics remain valid with >= 3 per side) but the row
    MUST say so -- silently reporting a 4-run verdict indistinguishably
    from a 10-run one would be a misreport."""
    a = [10.0, 10.1, 9.9, 10.05]
    b = [10.2, 10.3, 10.1, 10.25]
    row = verdict_row("m", a, b, margin=2.0, min_n=10)
    assert row.n_a == 4 and row.n_b == 4
    assert row.verdict in ("parity", "a_better", "b_better", "inconclusive")
    assert "UNDER-N" in row.notes


def test_verdict_row_meeting_min_n_has_no_under_n_note():
    a = [10.0, 10.1, 9.9, 10.05, 9.95, 10.02, 9.98, 10.03, 9.97, 10.01]
    b = [10.2, 10.3, 10.1, 10.25, 10.15, 10.22, 10.18, 10.23, 10.17, 10.21]
    row = verdict_row("m", a, b, margin=2.0, min_n=10)
    assert "UNDER-N" not in row.notes


def test_verdict_row_insufficient_data_below_bootstrap_minimum():
    """Fewer than stats.py's own hard minimum (3 per side) cannot even
    run the bootstrap; this must render as a clear non-verdict, not
    crash the whole table."""
    row = verdict_row("m", [10.0, 10.1], [10.2, 10.3], margin=2.0)
    assert row.verdict == "insufficient-data"
    assert row.ci is None and row.delta_median is None
    assert "insufficient" in row.notes.lower()


def test_verdict_row_reports_excluded_counts():
    a = [10.0, 10.1, 9.9, 10.05, 9.95, 10.02, 9.98, 10.03, 9.97, 10.01]
    b = [10.2, 10.3, 10.1, 10.25, 10.15, 10.22, 10.18, 10.23, 10.17, 10.21]
    row = verdict_row("m", a, b, margin=2.0, excluded_a=2, excluded_b=1)
    assert "2 run(s) excluded from A" in row.notes
    assert "1 run(s) excluded from B" in row.notes


def test_render_table_has_required_columns():
    rows = [verdict_row("one_hop_wall_ms", [1, 2, 3], [1, 2, 3], margin=2.0)]
    md = render_table(rows)
    header = md.splitlines()[0]
    for col in ("metric", "delta", "ci", "margin", "verdict"):
        assert col in header.lower()


def test_render_table_renders_all_four_verdicts_together():
    rows = [
        verdict_row(
            "parity_metric",
            [10.0, 10.1, 9.9, 10.05, 9.95, 10.02, 9.98, 10.03, 9.97, 10.01],
            [10.2, 10.3, 10.1, 10.25, 10.15, 10.22, 10.18, 10.23, 10.17, 10.21],
            margin=2.0,
        ),
        verdict_row(
            "a_better_metric",
            [5.0, 5.1, 4.9, 5.05, 4.95, 5.02, 4.98, 5.03, 4.97, 5.01],
            [12.0, 12.1, 11.9, 12.05, 11.95, 12.02, 11.98, 12.03, 11.97, 12.01],
            margin=2.0,
        ),
        verdict_row(
            "b_better_metric",
            [20.0, 20.1, 19.9, 20.05, 19.95, 20.02, 19.98, 20.03, 19.97, 20.01],
            [8.0, 8.1, 7.9, 8.05, 7.95, 8.02, 7.98, 8.03, 7.97, 8.01],
            margin=2.0,
        ),
        verdict_row(
            "inconclusive_metric",
            [10.0, 30.0, 5.0, 25.0, 12.0, 28.0, 8.0, 22.0, 15.0, 20.0],
            [11.0, 29.0, 6.0, 24.0, 13.0, 27.0, 9.0, 21.0, 16.0, 19.0],
            margin=2.0,
        ),
    ]
    md = render_table(rows)
    assert "| parity_metric " in md and "| parity |" in md
    assert "| a_better_metric " in md and "| a_better |" in md
    assert "| b_better_metric " in md and "| b_better |" in md
    assert "| inconclusive_metric " in md and "| inconclusive |" in md


# ---------------------------------------------------------------------------
# Layer 2: aggregation over synthetic run-* directories.
# ---------------------------------------------------------------------------


def _write_manifest(
    run_dir, *, cell="A", approach="extension", excluded=False, exclusion_reason="", run_index=1
):
    RunManifest(
        cell=cell,
        approach=approach,
        map_name="Town10HD_Opt",
        run_index=run_index,
        arm="closed-loop",
        harness_git_sha="abc",
        patches_git_sha="def",
        transport={
            "rmw": "rmw_cyclonedds_cpp",
            "shm_enabled": False,
            "dds_profile_sha256": "0" * 64,
        },
        carla_version="0.10-fork" if approach == "extension" else "0.10-tier4",
        autoware_image="img",
        started_at_ns=0,
        excluded=excluded,
        exclusion_reason=exclusion_reason,
        placement={
            "run_mode": "editor-game",
            "container_image": "img@sha256:x",
            "observer_env": "bench-observer:universe-devel",
            "engine_build_id": "b4c93e55-fc8f-42fc-b377-358910364e1c",
        },
    ).save(run_dir / "manifest.json")


def _make_run(
    tmp_path,
    cell="A",
    name="run-001",
    approach="extension",
    excluded=False,
    exclusion_reason="",
    one_hop_extra_ms=7.0,
    lidar_to_ndt_gap_ms=15.0,
    control_staleness_val_ms=5.0,
    cpu_pct=50.0,
    lidar_hz=10.0,
    n=30,
    include_published_time=True,
    include_ndt_topic=True,
    process_label=DEFAULT_CARLA_PROCESS_LABEL,
):
    """Build one minimal, self-consistent run-<NNN>/ directory.

    The clock fit is the identity affine (slope 1, intercept 1e12), so
    sim-domain and wall-domain offsets in nanoseconds convert 1:1 and the
    expected extractor outputs below can be reasoned about directly:

    - LIDAR_TOPIC arrives `one_hop_extra_ms` after its header stamp (wall
      domain) -> extract_one_hop_wall_ms ~= one_hop_extra_ms.
    - NDT_TOPIC's header stamp EQUALS the triggering LIDAR_TOPIC header
      stamp (the propagating hop latency.py documents), and its observer
      arrival lags the matched LIDAR_TOPIC arrival by
      `lidar_to_ndt_gap_ms` -> extract_lidar_to_ndt_sim_ms ~= that gap.
    - CONTROL_TOPIC's published_time.csv staleness is a fixed constant
      -> extract_control_staleness_ms ~= control_staleness_val_ms.
    - resources.csv carries one process (`process_label`) at a fixed
      cpu_pct -> extract_carla_process_cpu_pct ~= cpu_pct.
    """
    run_index = int(name.split("-")[1])
    d = tmp_path / cell / name
    d.mkdir(parents=True)
    _write_manifest(
        d,
        cell=cell,
        approach=approach,
        excluded=excluded,
        exclusion_reason=exclusion_reason,
        run_index=run_index,
    )

    period_ns = int(1e9 / lidar_hz)
    sim = np.arange(0, period_ns * n, period_ns, dtype=np.int64)
    wall = 1_000_000_000_000 + sim  # identity affine

    with open(d / "clock.csv", "w") as f:
        f.write("clock_ns,arrival_system_ns\n")
        for s, w in zip(sim.tolist(), wall.tolist()):
            f.write(f"{s},{w}\n")

    extra_ns = int(one_hop_extra_ms * 1e6)
    gap_ns = int(lidar_to_ndt_gap_ms * 1e6)

    with open(d / "observer.csv", "w") as f:
        f.write("topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes\n")
        for s in sim.tolist():
            lidar_arrival = 1_000_000_000_000 + s + extra_ns
            f.write(f"{LIDAR_TOPIC},{s},{lidar_arrival},{lidar_arrival},{s + extra_ns},1048576\n")
        if include_ndt_topic:
            for s in sim.tolist():
                ndt_arrival = 1_000_000_000_000 + s + extra_ns + gap_ns
                f.write(
                    f"{NDT_TOPIC},{s},{ndt_arrival},{ndt_arrival},{s + extra_ns + gap_ns},512\n"
                )

    with open(d / "published_time.csv", "w") as f:
        f.write("topic,source_header_ns,published_ns\n")
        if include_published_time:
            stale_ns = int(control_staleness_val_ms * 1e6)
            for s in sim.tolist():
                f.write(f"{CONTROL_TOPIC},{s},{s + stale_ns}\n")

    with open(d / "resources.csv", "w") as f:
        f.write("sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf\n")
        for w in wall.tolist()[:10]:
            f.write(f"{w},{process_label},{cpu_pct},1000,-1,-1,1.0\n")

    return tmp_path / cell


def test_extract_one_hop_wall_ms(tmp_path):
    cell = _make_run(tmp_path, one_hop_extra_ms=7.0)
    assert extract_one_hop_wall_ms(cell / "run-001") == pytest.approx(7.0, abs=0.05)


def test_extract_lidar_to_ndt_sim_ms(tmp_path):
    cell = _make_run(tmp_path, one_hop_extra_ms=7.0, lidar_to_ndt_gap_ms=15.0)
    assert extract_lidar_to_ndt_sim_ms(cell / "run-001") == pytest.approx(15.0, abs=0.05)


def test_extract_lidar_to_ndt_sim_ms_raises_when_ndt_topic_missing(tmp_path):
    cell = _make_run(tmp_path, include_ndt_topic=False)
    with pytest.raises(MetricUnavailableError):
        extract_lidar_to_ndt_sim_ms(cell / "run-001")


def test_extract_control_staleness_ms(tmp_path):
    cell = _make_run(tmp_path, control_staleness_val_ms=5.0)
    assert extract_control_staleness_ms(cell / "run-001") == pytest.approx(5.0, abs=0.01)


def test_extract_control_staleness_ms_raises_when_topic_unwired(tmp_path):
    """Matches today's real data contract: published_time.csv topics for
    the A/B duel are not registered yet (observer_topics/A.yaml), so this
    metric is currently unmeasurable -- and must say so, not misreport."""
    cell = _make_run(tmp_path, include_published_time=False)
    with pytest.raises(MetricUnavailableError):
        extract_control_staleness_ms(cell / "run-001")


def test_extract_carla_process_cpu_pct(tmp_path):
    cell = _make_run(tmp_path, cpu_pct=42.5)
    assert extract_carla_process_cpu_pct(cell / "run-001") == pytest.approx(42.5)


def test_extract_carla_process_cpu_pct_raises_for_unknown_label(tmp_path):
    cell = _make_run(tmp_path, process_label="carla")
    with pytest.raises(MetricUnavailableError):
        extract_carla_process_cpu_pct(cell / "run-001", process_label="autoware")


def test_default_carla_process_label_matches_committed_process_maps():
    """Cross-check DEFAULT_CARLA_PROCESS_LABEL against the ACTUAL
    committed benchmarks/config/processes/{A,B}.yaml, not a
    self-contained synthetic fixture -- a fixture built with whatever
    label this module already assumes can never catch that assumption
    drifting from the real config (Task 22 Step 1 review, Finding 1: the
    default silently stopped matching real resources.csv data because
    the committed process maps label the CARLA process "carla-server",
    not "carla"). Both of the primary duel's process maps must agree
    with the default so achieved_rate_ratio's sibling metric,
    carla_process_cpu_pct, is reachable by default on real P3 data."""
    processes_dir = Path(__file__).resolve().parents[2] / "benchmarks" / "config" / "processes"
    for cell in ("A", "B"):
        doc = yaml.safe_load((processes_dir / f"{cell}.yaml").read_text())
        carla_entries = [
            e for e in doc["processes"] if "CarlaUnreal.uproject" in e.get("pattern", "")
        ]
        assert len(carla_entries) == 1, f"{cell}.yaml: expected exactly one CARLA-server entry"
        assert carla_entries[0]["label"] == DEFAULT_CARLA_PROCESS_LABEL


def test_extract_achieved_rate_ratio(tmp_path):
    cell = _make_run(tmp_path, lidar_hz=10.0)
    ratio = extract_achieved_rate_ratio(cell / "run-001", expected_hz=10.0)
    assert ratio == pytest.approx(1.0, abs=0.02)
    ratio_half = extract_achieved_rate_ratio(cell / "run-001", expected_hz=20.0)
    assert ratio_half == pytest.approx(0.5, abs=0.02)


def test_extract_achieved_rate_ratio_rejects_bad_expected_hz(tmp_path):
    cell = _make_run(tmp_path)
    with pytest.raises(ValueError):
        extract_achieved_rate_ratio(cell / "run-001", expected_hz=0.0)


def test_cell_run_values_skips_excluded_and_counts_them(tmp_path):
    cell = None
    for i in range(1, 4):
        cell = _make_run(tmp_path, name=f"run-{i:03d}", one_hop_extra_ms=7.0)
    _make_run(
        tmp_path,
        name="run-004",
        one_hop_extra_ms=999.0,
        excluded=True,
        exclusion_reason="gate:aborted-before-window",
    )
    values, n_excluded, errors = cell_run_values(cell, extract_one_hop_wall_ms)
    assert n_excluded == 1
    assert len(values) == 3
    assert all(v == pytest.approx(7.0, abs=0.05) for v in values)
    assert errors == []


def test_cell_run_values_reports_a_run_whose_extractor_fails_without_aborting(tmp_path):
    cell = _make_run(tmp_path, name="run-001", include_ndt_topic=True)
    _make_run(tmp_path, name="run-002", include_ndt_topic=False)
    values, n_excluded, errors = cell_run_values(cell, extract_lidar_to_ndt_sim_ms)
    assert len(values) == 1
    assert len(errors) == 1
    assert "run-002" in errors[0]


def test_cell_run_values_reports_missing_manifest(tmp_path):
    cell = _make_run(tmp_path, name="run-001")
    (cell / "run-002").mkdir(parents=True)
    values, n_excluded, errors = cell_run_values(cell, extract_one_hop_wall_ms)
    assert len(values) == 1
    assert any("run-002" in e for e in errors)


def test_build_extractors_includes_achieved_rate_ratio_only_when_expected_hz_given():
    without = build_extractors()
    with_hz = build_extractors(expected_lidar_hz=10.0)
    assert "achieved_rate_ratio" not in without
    assert "achieved_rate_ratio" in with_hz
    for m in (
        "one_hop_wall_ms",
        "lidar_to_ndt_sim_ms",
        "control_staleness_ms",
        "carla_process_cpu_pct",
    ):
        assert m in without


def test_build_verdict_table_end_to_end(tmp_path):
    """Full pipeline over two cells' worth of synthetic run directories,
    covering: exclusion dropping, an under-n metric that IS still
    computed and flagged, and a metric with no wired extractor being
    named rather than silently dropped."""
    for i in range(1, 11):
        _make_run(
            tmp_path,
            cell="A",
            name=f"run-{i:03d}",
            approach="extension",
            one_hop_extra_ms=7.0 + 0.01 * i,
            cpu_pct=40.0 + i,
        )
    _make_run(
        tmp_path,
        cell="A",
        name="run-011",
        approach="extension",
        one_hop_extra_ms=999.0,
        excluded=True,
        exclusion_reason="gate:bad",
    )
    for i in range(1, 5):  # deliberately under n >= 10 for B
        _make_run(
            tmp_path,
            cell="B",
            name=f"run-{i:03d}",
            approach="tier4-native",
            one_hop_extra_ms=9.0 + 0.01 * i,
            cpu_pct=55.0 + i,
        )

    margins = {
        "one_hop_wall_ms": {"margin": 2.0},
        "carla_process_cpu_pct": {"margin": 10.0},
        "achieved_rate_ratio": {"margin": 0.02},  # no extractor wired below
    }
    extractors = build_extractors()  # no expected_lidar_hz -> ratio unavailable
    table = build_verdict_table(tmp_path / "A", tmp_path / "B", margins, extractors, min_n=10)

    assert "one_hop_wall_ms" in table
    assert "carla_process_cpu_pct" in table
    assert "1 run(s) excluded from A" in table
    assert "UNDER-N" in table  # B only has 4 runs
    assert "achieved_rate_ratio" in table  # named, not silently dropped
    assert "no wired extractor" in table.lower()
