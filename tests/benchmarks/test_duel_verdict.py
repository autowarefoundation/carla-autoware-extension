"""Tests for the primary A/B duel equivalence verdict tool.

Three layers are exercised:

* the pure statistics/rendering core (`verdict_row`, `render_table`)
  with synthetic run-level VALUES (no filesystem);
* the scoring-window + extraction layer (`extract_*`,
  `cell_run_values`) with synthetic run-* DIRECTORIES, built the same
  way tests/benchmarks/test_report.py does, extended with a real
  registered route (config/routes/Town10HD_Opt.yaml) for the
  closed-loop arm;
* the per-cell binding + orchestration layer (`METRIC_BINDERS`,
  `build_verdict_table`) with a synthetic in-memory cells.yaml document
  matching `cell_info.metrics_for`'s schema.

Mutation-testing review note: several fixtures below are deliberately
NOT the simplest ones that would make the happy-path assertion pass --
a fixture whose windowed/quantized/domain-dependent quantity happens to
equal its whole-run or naively-computed counterpart cannot tell a
correct implementation from a rejected one. Each such fixture's
docstring states the specific property that makes the rejected
implementation diverge, and a mutation to the rejected form is described
inline where it matters (D1, D7).
"""

from pathlib import Path

import numpy as np
import pytest
import yaml
from benchmarks.analysis.clockfit import fit_sim_wall_affine, sim_to_wall
from benchmarks.analysis.manifest import RunManifest, load_manifest
from benchmarks.scripts.duel_verdict import (
    METRIC_BINDERS,
    ODOM_TOPIC,
    SIM_STAMP_CEIL_NS,
    WALL_STAMP_FLOOR_NS,
    WARMUP_NS,
    MetricUnavailableError,
    _bind_achieved_rate_ratio,
    _bind_carla_process_cpu_pct,
    _bind_control_staleness_ms,
    _bind_lidar_to_ndt_sim_ms,
    _bind_one_hop_wall_ms,
    _registered_arms,
    _resolve_window,
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

LIDAR_TOPIC = "/sensing/lidar/top/pointcloud_raw_ex"
NDT_TOPIC = "/localization/pose_estimator/pose_with_covariance"
ROUTES_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "config" / "routes"

# observer.csv's clock_ns is "the latest /clock value seen at arrival"
# (README) -- it advances once per WORLD TICK (50 ms at the registered
# tick_hz: 20.0), not continuously. Fixtures below quantize to this
# grid deliberately: a continuous clock_ns cannot distinguish the
# registered lidar_to_ndt_sim_ms implementation (arrival gap / clock-fit
# slope) from the REJECTED one (a raw clock_ns diff), since both would
# see an indistinguishable smooth signal. See test_extract_lidar_to_ndt_
# sim_ms's docstring for the exact discriminating computation.
CLOCK_TICK_NS = 50_000_000


def _quantized_clock_ns(raw_ns: int) -> int:
    return (raw_ns // CLOCK_TICK_NS) * CLOCK_TICK_NS


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


def test_verdict_row_carries_arm_through():
    row = verdict_row("m", [1.0, 2.0, 3.0], [1.0, 2.0, 3.0], margin=2.0, arm="closed-loop")
    assert row.arm == "closed-loop"


def test_render_table_has_required_columns():
    rows = [verdict_row("one_hop_wall_ms", [1, 2, 3], [1, 2, 3], margin=2.0, arm="static")]
    md = render_table(rows)
    header = md.splitlines()[0]
    for col in ("metric", "arm", "delta", "ci", "margin", "verdict"):
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
# Fixture builders: synthetic run-* directories.
# ---------------------------------------------------------------------------


def _write_manifest(
    run_dir,
    *,
    cell="A",
    approach="extension",
    arm="static",
    map_name="Town10HD_Opt",
    excluded=False,
    exclusion_reason="",
    run_index=1,
):
    RunManifest(
        cell=cell,
        approach=approach,
        map_name=map_name,
        run_index=run_index,
        arm=arm,
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


def _route_odometry(
    run_duration_s: float, map_name: str, n: int = 80, stationary_until_s: float = 0.0
):
    """(header_stamp_ns[], x_m[], y_m[]) tracing the REAL registered
    route polyline for `map_name`, so `window.spatial_window` resolves a
    real, registered scoring window in these tests, not an invented
    one.

    `stationary_until_s`, when > 0, holds the ego at the route's very
    start (station ~0) until that time, only then beginning to move
    through the route -- this is what lets a closed-loop test separate
    the SPATIAL window's start (gated by reaching stations.start_m) from
    the naive WALL warm-up bound (gated only by elapsed time): with
    stationary_until_s=0, a roughly-linear traverse reaches station 20 m
    within the first few percent of the route almost immediately, so the
    two windows' starts collapse onto each other and a mutation to
    static_window is invisible.
    """
    doc = yaml.safe_load((ROUTES_DIR / f"{map_name}.yaml").read_text())
    poly = np.asarray(doc["polyline"], dtype=np.float64)
    t = np.linspace(0.0, run_duration_s, n)
    move_duration = max(run_duration_s - stationary_until_s, 1e-9)
    frac = np.clip((t - stationary_until_s) / move_duration, 0.0, 1.0)
    idx = np.clip((frac * (len(poly) - 1)).astype(int), 0, len(poly) - 1)
    xy = poly[idx]
    stamp_ns = (t * 1e9).astype(np.int64)
    return stamp_ns, xy[:, 0], xy[:, 1]


def _make_run(
    tmp_path,
    cell="A",
    name="run-001",
    approach="extension",
    arm="static",
    map_name="Town10HD_Opt",
    excluded=False,
    exclusion_reason="",
    one_hop_extra_ms=7.0,
    warmup_outlier_one_hop_ms=None,
    outlier_until_ns=WARMUP_NS,
    lidar_arrival_scale=1.0,
    lidar_to_ndt_gap_ms=15.0,
    gap_outlier_ms=None,
    cpu_pct=50.0,
    cpu_pct_before_window=None,
    lidar_hz=10.0,
    run_duration_s=40.0,
    include_ndt_topic=True,
    process_label="carla-server",
    lidar_topic=LIDAR_TOPIC,
    ndt_topic=NDT_TOPIC,
    pre_window_decimate=None,
    stationary_until_s=0.0,
):
    """Build one minimal, self-consistent run-<NNN>/ directory.

    The clock fit is (close to) the identity affine (slope 1, intercept
    1e12), so sim-domain and wall-domain nanosecond offsets convert ~1:1
    and the expected extractor outputs can be reasoned about directly:

    - LIDAR_TOPIC arrives `one_hop_extra_ms` after its header stamp
      (wall domain) -> extract_one_hop_wall_ms ~= one_hop_extra_ms, for
      rows AT OR AFTER the scoring window's start; `warmup_outlier_
      one_hop_ms`, when given, replaces this value for rows with
      `header_stamp_ns < outlier_until_ns`, so a test can prove a
      window's start actually filters rather than merely not crashing.
    - NDT_TOPIC's header stamp EQUALS the triggering LIDAR_TOPIC header
      stamp (the propagating hop latency.py documents), and its observer
      arrival lags the matched LIDAR_TOPIC arrival by
      `lidar_to_ndt_gap_ms` (or `gap_outlier_ms` before `outlier_
      until_ns`) -> extract_lidar_to_ndt_sim_ms ~= that gap.
    - `clock_ns` is QUANTIZED to CLOCK_TICK_NS (50 ms), matching the
      real data contract -- see the module-level comment.
    - resources.csv carries one process (`process_label`) at `cpu_pct`
      (or `cpu_pct_before_window` before the window starts, wall
      domain).
    - `lidar_arrival_scale` != 1.0 decouples LIDAR_TOPIC's wall arrival
      spacing from its (always evenly spaced) sim header-stamp spacing,
      so a test can prove achieved_rate_ratio uses SIM stamps.
    - `pre_window_decimate`, when given, keeps only every Nth LIDAR_TOPIC
      row with `header_stamp_ns < outlier_until_ns` (thinning out the
      pre-window portion to a visibly lower rate), so a test can prove
      achieved_rate_ratio's rate comes from the WINDOWED series, not the
      whole run.
    - arm="closed-loop" additionally writes odometry.csv tracing the
      real `config/routes/<map_name>.yaml` polyline, optionally held
      stationary until `stationary_until_s` (see `_route_odometry`).
    """
    run_index = int(name.split("-")[1])
    d = tmp_path / cell / name
    d.mkdir(parents=True)
    _write_manifest(
        d,
        cell=cell,
        approach=approach,
        arm=arm,
        map_name=map_name,
        excluded=excluded,
        exclusion_reason=exclusion_reason,
        run_index=run_index,
    )

    duration_ns = int(run_duration_s * 1e9)
    wall_t0 = 1_000_000_000_000  # toy wall baseline; fine here (relative only)

    clock_sim = np.arange(0, duration_ns, 1_000_000_000, dtype=np.int64)
    clock_wall = wall_t0 + clock_sim
    with open(d / "clock.csv", "w") as f:
        f.write("clock_ns,arrival_system_ns\n")
        for s, w in zip(clock_sim.tolist(), clock_wall.tolist()):
            f.write(f"{s},{w}\n")

    period_ns = int(1e9 / lidar_hz)
    lidar_sim = np.arange(0, duration_ns, period_ns, dtype=np.int64)
    extra_ns_normal = int(one_hop_extra_ms * 1e6)
    gap_ns_normal = int(lidar_to_ndt_gap_ms * 1e6)
    gap_ns_outlier = None if gap_outlier_ms is None else int(gap_outlier_ms * 1e6)
    with open(d / "observer.csv", "w") as f:
        f.write("topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes\n")
        for k, s in enumerate(lidar_sim.tolist()):
            if (
                pre_window_decimate is not None
                and s < outlier_until_ns
                and k % pre_window_decimate != 0
            ):
                continue  # thin the pre-window portion to a lower rate
            extra_ns = extra_ns_normal
            if warmup_outlier_one_hop_ms is not None and s < outlier_until_ns:
                extra_ns = int(warmup_outlier_one_hop_ms * 1e6)
            lidar_arrival = wall_t0 + int(round(s * lidar_arrival_scale)) + extra_ns
            lidar_clock = _quantized_clock_ns(s + extra_ns)
            f.write(f"{lidar_topic},{s},{lidar_arrival},{lidar_arrival},{lidar_clock},1048576\n")
        if include_ndt_topic:
            for s in lidar_sim.tolist():
                extra_ns = extra_ns_normal
                if warmup_outlier_one_hop_ms is not None and s < outlier_until_ns:
                    extra_ns = int(warmup_outlier_one_hop_ms * 1e6)
                gap_ns = gap_ns_normal
                if gap_ns_outlier is not None and s < outlier_until_ns:
                    gap_ns = gap_ns_outlier
                ndt_arrival = wall_t0 + s + extra_ns + gap_ns
                ndt_clock = _quantized_clock_ns(s + extra_ns + gap_ns)
                f.write(f"{ndt_topic},{s},{ndt_arrival},{ndt_arrival},{ndt_clock},512\n")

    (d / "published_time.csv").write_text("topic,source_header_ns,published_ns\n")

    with open(d / "resources.csv", "w") as f:
        f.write("sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf\n")
        for s in clock_sim.tolist():
            wall = wall_t0 + s
            pct = cpu_pct
            if cpu_pct_before_window is not None and s < WARMUP_NS:
                pct = cpu_pct_before_window
            f.write(f"{wall},{process_label},{pct},1000,-1,-1,1.0\n")

    if arm == "closed-loop":
        stamp_ns, xs, ys = _route_odometry(
            run_duration_s, map_name, stationary_until_s=stationary_until_s
        )
        with open(d / "odometry.csv", "w") as f:
            f.write("topic,header_stamp_ns,x_m,y_m\n")
            for s, x, y in zip(stamp_ns.tolist(), xs.tolist(), ys.tolist()):
                f.write(f"{ODOM_TOPIC},{s},{x},{y}\n")
    else:
        (d / "odometry.csv").write_text("topic,header_stamp_ns,x_m,y_m\n")

    return tmp_path / cell


def _manifest_of(run_dir: Path) -> RunManifest:
    return load_manifest(run_dir / "manifest.json")


def _window_of(run_dir: Path):
    return _resolve_window(run_dir, _manifest_of(run_dir))


def _one_hop_extractor(run_dir, manifest, window):
    return extract_one_hop_wall_ms(run_dir, manifest, window, LIDAR_TOPIC)


def _lidar_to_ndt_extractor(run_dir, manifest, window):
    return extract_lidar_to_ndt_sim_ms(run_dir, manifest, window, LIDAR_TOPIC, NDT_TOPIC)


# ---------------------------------------------------------------------------
# Layer 2: extractors over synthetic run-* directories (windowed).
# ---------------------------------------------------------------------------


def test_extract_one_hop_wall_ms(tmp_path):
    cell = _make_run(tmp_path, one_hop_extra_ms=7.0)
    run_dir = cell / "run-001"
    val = extract_one_hop_wall_ms(run_dir, _manifest_of(run_dir), _window_of(run_dir), LIDAR_TOPIC)
    assert val == pytest.approx(7.0, abs=0.05)


def test_extract_one_hop_wall_ms_raises_when_topic_missing(tmp_path):
    cell = _make_run(tmp_path)
    run_dir = cell / "run-001"
    with pytest.raises(MetricUnavailableError):
        extract_one_hop_wall_ms(
            run_dir, _manifest_of(run_dir), _window_of(run_dir), "/no/such/topic"
        )


def test_extract_one_hop_wall_ms_excludes_warmup(tmp_path):
    """D7: the 20 s warm-up discard must actually filter, not merely not
    crash. An extreme value before WARMUP_NS would dominate a whole-run
    median if windowing were a no-op; the windowed result must instead
    match the POST-warmup value."""
    cell = _make_run(
        tmp_path, one_hop_extra_ms=7.0, warmup_outlier_one_hop_ms=5000.0, run_duration_s=40.0
    )
    run_dir = cell / "run-001"
    val = extract_one_hop_wall_ms(run_dir, _manifest_of(run_dir), _window_of(run_dir), LIDAR_TOPIC)
    assert val == pytest.approx(7.0, abs=0.5)


def test_extract_one_hop_wall_ms_closed_loop_uses_route_spatial_window(tmp_path):
    """D7, closed-loop branch: the scoring window must come from
    window.spatial_window over the REAL Town10HD_Opt route, NOT
    window.static_window.

    Discriminating property: the ego is held stationary at the route's
    start (station ~0, well under stations.start_m=20) for the first
    55 s of a 70 s run, only then moving through the route. This
    separates the two candidate windows enough to matter:

    - static_window(t0, end, 20 s warm-up) = [20 s, 70 s] (50 s span).
    - the REAL spatial window only starts once station >= 20 m is
      reached, which happens at ~55.8 s here (~13.3 s span, ending
      ~69.1 s) -- computed directly from window.spatial_window in this
      fixture's own design, not asserted blindly.

    An outlier is planted for every LIDAR row with header_stamp_ns
    < 55 s (the whole stationary period): that spans 35 of the buggy
    static window's 50 s (70% of its samples) but NONE of the true
    spatial window's ~13.3 s. A build that substituted static_window for
    the closed-loop arm (the exact rejected D7 mutation) would see a
    median dominated by the outlier; the correct implementation must
    not.
    """
    cell = _make_run(
        tmp_path,
        arm="closed-loop",
        one_hop_extra_ms=7.0,
        warmup_outlier_one_hop_ms=5000.0,
        outlier_until_ns=55_000_000_000,
        stationary_until_s=55.0,
        run_duration_s=70.0,
    )
    run_dir = cell / "run-001"
    window = _window_of(run_dir)
    # Sanity-check the fixture's own premise before trusting the below.
    assert window.sim_lo > 55_000_000_000
    val = extract_one_hop_wall_ms(run_dir, _manifest_of(run_dir), window, LIDAR_TOPIC)
    assert val == pytest.approx(7.0, abs=0.5)


def test_extract_lidar_to_ndt_sim_ms(tmp_path):
    """Discriminating fixture for D1: clock_ns is quantized to
    CLOCK_TICK_NS (50 ms). A true gap of 15 ms is smaller than one
    tick, so the REJECTED clock_ns-diff implementation collapses every
    matched pair onto the SAME 50 ms bucket (lidar and ndt clock_ns both
    floor to identical values here, since the 15 ms gap plus a 7 ms
    one-hop offset never crosses a 50 ms boundary at these header
    stamps) and reports a median of 0.0 ms -- 15 ms away from the
    asserted value, which the registered arrival-gap/slope
    implementation still reports exactly."""
    cell = _make_run(tmp_path, one_hop_extra_ms=7.0, lidar_to_ndt_gap_ms=15.0)
    run_dir = cell / "run-001"
    val = extract_lidar_to_ndt_sim_ms(
        run_dir, _manifest_of(run_dir), _window_of(run_dir), LIDAR_TOPIC, NDT_TOPIC
    )
    assert val == pytest.approx(15.0, abs=0.5)


def test_extract_lidar_to_ndt_sim_ms_raises_when_ndt_topic_missing(tmp_path):
    cell = _make_run(tmp_path, include_ndt_topic=False)
    run_dir = cell / "run-001"
    with pytest.raises(MetricUnavailableError):
        extract_lidar_to_ndt_sim_ms(
            run_dir, _manifest_of(run_dir), _window_of(run_dir), LIDAR_TOPIC, NDT_TOPIC
        )


def test_extract_lidar_to_ndt_sim_ms_raises_when_stamps_never_propagate(tmp_path):
    """The registered join is EXACT header_stamp_ns equality; a nearest-
    stamp fallback is explicitly forbidden. Both topics are PRESENT here
    (unlike the "topic missing" test above) but their header stamps
    never coincide -- stamp propagation broken -- so the join must find
    zero pairs and report UNAVAILABLE rather than silently pairing the
    nearest scan to the wrong pose."""
    d = tmp_path / "A" / "run-001"
    d.mkdir(parents=True)
    _write_manifest(d, arm="static")
    sim = np.arange(0, 40_000_000_000, 1_000_000_000, dtype=np.int64)
    wall_t0 = 1_000_000_000_000
    with open(d / "clock.csv", "w") as f:
        f.write("clock_ns,arrival_system_ns\n")
        for s in sim.tolist():
            f.write(f"{s},{wall_t0 + s}\n")
    with open(d / "observer.csv", "w") as f:
        f.write("topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes\n")
        for s in sim.tolist():
            f.write(f"{LIDAR_TOPIC},{s},{wall_t0 + s},{wall_t0 + s},{s},1048576\n")
        for s in sim.tolist():  # NDT stamps offset by 1 ns: never exactly equal
            ndt_stamp = s + 1
            f.write(
                f"{NDT_TOPIC},{ndt_stamp},{wall_t0 + ndt_stamp},{wall_t0 + ndt_stamp},"
                f"{ndt_stamp},512\n"
            )
    (d / "published_time.csv").write_text("topic,source_header_ns,published_ns\n")
    (d / "resources.csv").write_text(
        "sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf\n"
    )
    (d / "odometry.csv").write_text("topic,header_stamp_ns,x_m,y_m\n")
    with pytest.raises(MetricUnavailableError):
        extract_lidar_to_ndt_sim_ms(d, _manifest_of(d), _window_of(d), LIDAR_TOPIC, NDT_TOPIC)


def test_extract_lidar_to_ndt_sim_ms_excludes_pre_window_outlier(tmp_path):
    """D7 coverage for lidar_to_ndt_sim_ms specifically (not just
    one_hop_wall_ms): a wildly different gap planted before the window
    start must not move the windowed median."""
    cell = _make_run(
        tmp_path,
        lidar_to_ndt_gap_ms=15.0,
        gap_outlier_ms=9000.0,
        outlier_until_ns=WARMUP_NS,
        run_duration_s=40.0,
    )
    run_dir = cell / "run-001"
    val = extract_lidar_to_ndt_sim_ms(
        run_dir, _manifest_of(run_dir), _window_of(run_dir), LIDAR_TOPIC, NDT_TOPIC
    )
    assert val == pytest.approx(15.0, abs=0.5)


def test_extract_control_staleness_ms_raises_when_topic_none(tmp_path):
    cell = _make_run(tmp_path)
    run_dir = cell / "run-001"
    with pytest.raises(MetricUnavailableError):
        extract_control_staleness_ms(run_dir, _manifest_of(run_dir), _window_of(run_dir), None)


def test_extract_control_staleness_ms_raises_when_topic_not_in_csv(tmp_path):
    cell = _make_run(tmp_path)
    run_dir = cell / "run-001"
    with pytest.raises(MetricUnavailableError):
        extract_control_staleness_ms(
            run_dir,
            _manifest_of(run_dir),
            _window_of(run_dir),
            "/control/command/control_cmd/_published_time",
        )


def test_extract_control_staleness_ms_branch_a_sim_domain(tmp_path):
    """published_stamp in the SIM domain (< 1e13 ns): the discriminator
    must pick branch (a), the direct staleness_ms diff."""
    cell = _make_run(tmp_path, run_duration_s=40.0)
    run_dir = cell / "run-001"
    topic = "/control/command/control_cmd/_published_time"
    stale_ns = 5_000_000  # 5 ms, sim domain
    sim = np.arange(0, 40_000_000_000, 1_000_000_000, dtype=np.int64)
    with open(run_dir / "published_time.csv", "w") as f:
        f.write("topic,source_header_ns,published_ns\n")
        for s in sim.tolist():
            f.write(f"{topic},{s},{s + stale_ns}\n")
    val = extract_control_staleness_ms(run_dir, _manifest_of(run_dir), _window_of(run_dir), topic)
    assert val == pytest.approx(5.0, abs=0.01)


def test_extract_control_staleness_ms_branch_a_excludes_pre_window_outlier(tmp_path):
    """D7 coverage for control_staleness_ms: a wildly different
    staleness planted before the window start must not move the
    windowed median. (Also fixes the mutation-testing finding that
    control_staleness_ms had no window-sensitivity coverage.)"""
    cell = _make_run(tmp_path, run_duration_s=40.0)
    run_dir = cell / "run-001"
    topic = "/control/command/control_cmd/_published_time"
    stale_ns_normal = 5_000_000  # 5 ms
    stale_ns_outlier = 900_000_000  # 900 ms, absurd for a 10 ms margin
    sim = np.arange(0, 40_000_000_000, 1_000_000_000, dtype=np.int64)
    with open(run_dir / "published_time.csv", "w") as f:
        f.write("topic,source_header_ns,published_ns\n")
        for s in sim.tolist():
            stale = stale_ns_outlier if s < WARMUP_NS else stale_ns_normal
            f.write(f"{topic},{s},{s + stale}\n")
    val = extract_control_staleness_ms(run_dir, _manifest_of(run_dir), _window_of(run_dir), topic)
    assert val == pytest.approx(5.0, abs=0.5)


def test_extract_control_staleness_ms_branch_b_wall_domain(tmp_path):
    """published_stamp in the WALL domain (> 1e18 ns): the discriminator
    must pick branch (b), one_hop_wall_ms's formula (publisher-side
    transport analogue), NOT branch (a)'s raw sim-domain diff -- which
    would misread a huge wall timestamp as an astronomical staleness."""
    d = tmp_path / "A" / "run-001"
    d.mkdir(parents=True)
    _write_manifest(d, arm="static")
    wall_t0 = 1_700_000_000_000_000_000  # realistic epoch-scale wall time
    sim = np.arange(0, 40_000_000_000, 1_000_000_000, dtype=np.int64)
    wall = wall_t0 + sim
    with open(d / "clock.csv", "w") as f:
        f.write("clock_ns,arrival_system_ns\n")
        for s, w in zip(sim.tolist(), wall.tolist()):
            f.write(f"{s},{w}\n")
    fit = fit_sim_wall_affine(sim, wall)  # identity: slope 1, intercept wall_t0
    (d / "observer.csv").write_text(
        "topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes\n"
    )
    (d / "resources.csv").write_text(
        "sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf\n"
    )
    (d / "odometry.csv").write_text("topic,header_stamp_ns,x_m,y_m\n")
    topic = "/control/command/control_cmd/_published_time"
    stale_wall_ns = 7_000_000  # 7 ms, WALL domain
    with open(d / "published_time.csv", "w") as f:
        f.write("topic,source_header_ns,published_ns\n")
        for s in sim.tolist():
            expected_wall = float(sim_to_wall(fit, s))
            published_ns = int(round(expected_wall)) + stale_wall_ns
            f.write(f"{topic},{s},{published_ns}\n")
    val = extract_control_staleness_ms(d, _manifest_of(d), _window_of(d), topic)
    assert val == pytest.approx(7.0, abs=0.1)


def test_extract_control_staleness_ms_raises_when_domain_unclassifiable(tmp_path):
    """D4: the two registered bands are DISJOINT (sim < 1e13, wall
    > 1e18), not a single cut. A monotonic/uptime-style published_stamp
    landing in the unclassified gap between them (e.g. ~1e15 ns, a
    plausible ~11.6-day uptime counter) must be reported UNAVAILABLE,
    never silently read as sim-domain (which would produce a nonsense
    ~1e8 ms "staleness")."""
    cell = _make_run(tmp_path, run_duration_s=40.0)
    run_dir = cell / "run-001"
    topic = "/control/command/control_cmd/_published_time"
    assert SIM_STAMP_CEIL_NS < 5e15 < WALL_STAMP_FLOOR_NS  # the gap is real
    unclassifiable_ns = 5_000_000_000_000_000  # 5e15 ns: in neither band
    sim = np.arange(0, 40_000_000_000, 1_000_000_000, dtype=np.int64)
    with open(run_dir / "published_time.csv", "w") as f:
        f.write("topic,source_header_ns,published_ns\n")
        for s in sim.tolist():
            f.write(f"{topic},{s},{unclassifiable_ns}\n")
    with pytest.raises(MetricUnavailableError, match="neither"):
        extract_control_staleness_ms(run_dir, _manifest_of(run_dir), _window_of(run_dir), topic)


def test_extract_carla_process_cpu_pct(tmp_path):
    cell = _make_run(tmp_path, cpu_pct=42.5)
    run_dir = cell / "run-001"
    val = extract_carla_process_cpu_pct(
        run_dir, _manifest_of(run_dir), _window_of(run_dir), "carla-server"
    )
    assert val == pytest.approx(42.5)


def test_extract_carla_process_cpu_pct_raises_when_label_none(tmp_path):
    cell = _make_run(tmp_path)
    run_dir = cell / "run-001"
    with pytest.raises(MetricUnavailableError):
        extract_carla_process_cpu_pct(run_dir, _manifest_of(run_dir), _window_of(run_dir), None)


def test_extract_carla_process_cpu_pct_raises_for_unknown_label(tmp_path):
    cell = _make_run(tmp_path, process_label="carla-server")
    run_dir = cell / "run-001"
    with pytest.raises(MetricUnavailableError):
        extract_carla_process_cpu_pct(
            run_dir, _manifest_of(run_dir), _window_of(run_dir), "autoware"
        )


def test_extract_carla_process_cpu_pct_excludes_pre_window_samples(tmp_path):
    """D7, WALL-domain branch: resources.csv is filtered on
    sample_system_ns (wall), independently of the sim-domain filtering
    the other four extractors use. An outlier before the window must be
    excluded here too."""
    cell = _make_run(tmp_path, cpu_pct=50.0, cpu_pct_before_window=999.0, run_duration_s=40.0)
    run_dir = cell / "run-001"
    val = extract_carla_process_cpu_pct(
        run_dir, _manifest_of(run_dir), _window_of(run_dir), "carla-server"
    )
    assert val == pytest.approx(50.0, abs=0.5)


def test_extract_achieved_rate_ratio(tmp_path):
    cell = _make_run(tmp_path, lidar_hz=10.0, run_duration_s=40.0)
    run_dir = cell / "run-001"
    manifest, window = _manifest_of(run_dir), _window_of(run_dir)
    ratio = extract_achieved_rate_ratio(run_dir, manifest, window, LIDAR_TOPIC, 10.0)
    assert ratio == pytest.approx(1.0, abs=0.05)
    ratio_half = extract_achieved_rate_ratio(run_dir, manifest, window, LIDAR_TOPIC, 20.0)
    assert ratio_half == pytest.approx(0.5, abs=0.05)


def test_extract_achieved_rate_ratio_uses_sim_stamps_not_wall_arrivals(tmp_path):
    """D5: the rate must come from SIM header_stamp_ns, not wall
    arrival_system_ns. lidar_arrival_scale=2.0 makes wall arrivals
    spread out twice as fast in wall time as the (always evenly spaced)
    sim header stamps; a bug reading wall arrivals would compute a
    visibly different (roughly half) ratio."""
    cell = _make_run(tmp_path, lidar_hz=10.0, run_duration_s=40.0, lidar_arrival_scale=2.0)
    run_dir = cell / "run-001"
    ratio = extract_achieved_rate_ratio(
        run_dir, _manifest_of(run_dir), _window_of(run_dir), LIDAR_TOPIC, 10.0
    )
    assert ratio == pytest.approx(1.0, abs=0.05)


def test_extract_achieved_rate_ratio_excludes_pre_window_rate(tmp_path):
    """D7 coverage for achieved_rate_ratio: the pre-window portion is
    thinned to 1/5th density (a visibly LOWER rate). If the extractor
    computed hz over the whole run instead of the windowed series, the
    measured rate -- and therefore the ratio -- would be pulled well
    below 1.0; windowed correctly, only the full-density post-window
    rows count and the ratio stays near 1.0."""
    cell = _make_run(
        tmp_path,
        lidar_hz=10.0,
        run_duration_s=40.0,
        pre_window_decimate=5,
        outlier_until_ns=WARMUP_NS,
    )
    run_dir = cell / "run-001"
    ratio = extract_achieved_rate_ratio(
        run_dir, _manifest_of(run_dir), _window_of(run_dir), LIDAR_TOPIC, 10.0
    )
    assert ratio == pytest.approx(1.0, abs=0.1)


def test_extract_achieved_rate_ratio_raises_when_expected_hz_none(tmp_path):
    cell = _make_run(tmp_path)
    run_dir = cell / "run-001"
    with pytest.raises(MetricUnavailableError):
        extract_achieved_rate_ratio(
            run_dir, _manifest_of(run_dir), _window_of(run_dir), LIDAR_TOPIC, None
        )


def test_extract_achieved_rate_ratio_rejects_bad_expected_hz(tmp_path):
    cell = _make_run(tmp_path)
    run_dir = cell / "run-001"
    with pytest.raises(ValueError):
        extract_achieved_rate_ratio(
            run_dir, _manifest_of(run_dir), _window_of(run_dir), LIDAR_TOPIC, 0.0
        )


# ---------------------------------------------------------------------------
# cell_run_values: exclusion, per-run error reporting, arm filtering.
# ---------------------------------------------------------------------------


def test_cell_run_values_skips_excluded_and_counts_them(tmp_path):
    cell = None
    for i in range(1, 4):
        cell = _make_run(tmp_path, name=f"run-{i:03d}", one_hop_extra_ms=7.0)
    _make_run(
        tmp_path,
        name="run-004",
        one_hop_extra_ms=999.0,
        excluded=True,
        exclusion_reason="gate:arm-failed",
    )
    values, n_excluded, errors = cell_run_values(cell, _one_hop_extractor)
    assert n_excluded == 1
    assert len(values) == 3
    assert all(v == pytest.approx(7.0, abs=0.05) for v in values)
    assert errors == []


def test_cell_run_values_reports_a_run_whose_extractor_fails_without_aborting(tmp_path):
    cell = _make_run(tmp_path, name="run-001", include_ndt_topic=True)
    _make_run(tmp_path, name="run-002", include_ndt_topic=False)
    values, n_excluded, errors = cell_run_values(cell, _lidar_to_ndt_extractor)
    assert len(values) == 1
    assert len(errors) == 1
    assert "run-002" in errors[0]


def test_cell_run_values_reports_missing_manifest(tmp_path):
    cell = _make_run(tmp_path, name="run-001")
    (cell / "run-002").mkdir(parents=True)
    values, n_excluded, errors = cell_run_values(cell, _one_hop_extractor)
    assert len(values) == 1
    assert any("run-002" in e for e in errors)


def test_cell_run_values_filters_by_arm(tmp_path):
    """The duel is computed per arm, never pooled: a run of a DIFFERENT
    arm must be silently out of scope for this call -- not counted as
    excluded, not reported as an error, and not contributing a value."""
    cell = None
    for i in range(1, 4):
        cell = _make_run(tmp_path, name=f"run-{i:03d}", arm="static", one_hop_extra_ms=7.0)
    _make_run(tmp_path, name="run-004", arm="closed-loop", one_hop_extra_ms=999.0)
    values, n_excluded, errors = cell_run_values(cell, _one_hop_extractor, arm="static")
    assert len(values) == 3
    assert n_excluded == 0
    assert errors == []
    assert all(v == pytest.approx(7.0, abs=0.5) for v in values)


# ---------------------------------------------------------------------------
# Layer 3: per-cell binding (cell_info.metrics_for) + orchestration.
# ---------------------------------------------------------------------------


def _metrics(**overrides) -> dict:
    m = {
        "lidar_topic": LIDAR_TOPIC,
        "ndt_topic": NDT_TOPIC,
        "control_topic": "/control/command/control_cmd",
        "control_published_time_topic": None,
        "cpu_process_label": "carla-server",
        "tick_hz": 20.0,
        "lidar_expected_hz": 20.0,
    }
    m.update(overrides)
    return m


def _cells_doc(a_overrides=None, b_overrides=None, arms=("static", "closed-loop")):
    """A minimal synthetic cells.yaml document matching
    cell_info.metrics_for's schema -- real registered topic/label
    values by default, so the binders exercise the actual registered
    bindings rather than an invented shape."""
    return {
        "cells": [
            {
                "id": "A",
                "approach": "extension",
                "arms": list(arms),
                "metrics": _metrics(**(a_overrides or {})),
            },
            {
                "id": "B",
                "approach": "tier4-native",
                "arms": list(arms),
                "metrics": _metrics(**(b_overrides or {})),
            },
        ]
    }


def test_bind_one_hop_wall_ms_none_when_topic_unregistered():
    extractor, reason = _bind_one_hop_wall_ms(_metrics(lidar_topic=None))
    assert extractor is None
    assert "lidar_topic" in reason


def test_bind_lidar_to_ndt_sim_ms_none_when_either_topic_unregistered():
    extractor, reason = _bind_lidar_to_ndt_sim_ms(_metrics(ndt_topic=None))
    assert extractor is None
    assert "ndt_topic" in reason


def test_bind_control_staleness_ms_none_when_topic_unregistered():
    extractor, reason = _bind_control_staleness_ms(_metrics())  # topic is None
    assert extractor is None
    assert "control_published_time_topic" in reason


def test_bind_carla_process_cpu_pct_none_when_label_unregistered():
    extractor, reason = _bind_carla_process_cpu_pct(_metrics(cpu_process_label=None))
    assert extractor is None
    assert "cpu_process_label" in reason


def test_bind_achieved_rate_ratio_none_when_expected_hz_unregistered():
    extractor, reason = _bind_achieved_rate_ratio(_metrics(lidar_expected_hz=None))
    assert extractor is None
    assert "lidar_expected_hz" in reason


def test_bound_extractors_accept_the_three_arg_cell_run_values_contract(tmp_path):
    """Every binder's returned extractor must match cell_run_values's
    uniform (run_dir, manifest, window) contract -- a binder that still
    returned a 2-arg closure would raise a TypeError the first time
    cell_run_values called it, not at binder-construction time."""
    cell = _make_run(tmp_path, one_hop_extra_ms=7.0, cpu_pct=50.0, lidar_hz=10.0)
    run_dir = cell / "run-001"
    manifest, window = _manifest_of(run_dir), _window_of(run_dir)
    metrics = _metrics(lidar_expected_hz=10.0)
    for binder in (
        _bind_one_hop_wall_ms,
        _bind_lidar_to_ndt_sim_ms,
        _bind_carla_process_cpu_pct,
        _bind_achieved_rate_ratio,
    ):
        extractor, reason = binder(metrics)
        assert extractor is not None, reason
        extractor(run_dir, manifest, window)  # must not raise TypeError


def test_metric_binders_cover_every_margin_metric():
    margins_keys = {
        "one_hop_wall_ms",
        "lidar_to_ndt_sim_ms",
        "control_staleness_ms",
        "carla_process_cpu_pct",
        "achieved_rate_ratio",
    }
    assert set(METRIC_BINDERS) == margins_keys


def test_registered_arms_is_the_intersection():
    doc = _cells_doc(arms=("static", "closed-loop"))
    assert _registered_arms(doc, "A", "B") == ["static", "closed-loop"]


def test_registered_arms_excludes_arms_only_one_side_has():
    doc = _cells_doc()
    doc["cells"][1]["arms"] = ["static"]  # cell B never runs closed-loop
    assert _registered_arms(doc, "A", "B") == ["static"]


# ---------------------------------------------------------------------------
# build_verdict_table: end-to-end over synthetic run-* trees.
# ---------------------------------------------------------------------------


def test_build_verdict_table_reports_one_row_per_arm_not_pooled(tmp_path):
    """The duel must never pool arms into one row.

    Discriminating property: the two arms carry DIFFERENT A-minus-B
    deltas of different SIGN (static: 5.0 vs 6.0, delta -1.0;
    closed-loop: 50.0 vs 20.0, delta +30.0). Pooling cell A's six runs
    ([5,5,5,50,50,50], median 27.5) against cell B's six
    ([6,6,6,20,20,20], median 13.0) would report a pooled delta around
    +14.5 -- neither arm's own delta, and a value the delta assertions
    below directly rule out."""
    for i in range(1, 4):
        _make_run(tmp_path, cell="A", name=f"run-{i:03d}", arm="static", one_hop_extra_ms=5.0)
        _make_run(
            tmp_path, cell="A", name=f"run-{i + 3:03d}", arm="closed-loop", one_hop_extra_ms=50.0
        )
        _make_run(tmp_path, cell="B", name=f"run-{i:03d}", arm="static", one_hop_extra_ms=6.0)
        _make_run(
            tmp_path, cell="B", name=f"run-{i + 3:03d}", arm="closed-loop", one_hop_extra_ms=20.0
        )
    doc = _cells_doc()
    margins = {"one_hop_wall_ms": {"margin": 2.0}}
    table = build_verdict_table(tmp_path / "A", tmp_path / "B", "A", "B", margins, doc, min_n=3)
    static_line = next(line for line in table.splitlines() if "| static |" in line)
    closed_line = next(line for line in table.splitlines() if "| closed-loop |" in line)
    # Columns: metric | arm | n (a/b) | delta_median | 95% ci | margin |
    # verdict | notes
    static_delta = float(static_line.split("|")[4].strip())
    closed_delta = float(closed_line.split("|")[4].strip())
    assert static_delta == pytest.approx(-1.0, abs=0.2)
    assert closed_delta == pytest.approx(30.0, abs=0.5)
    static_n = static_line.split("|")[3].strip()
    closed_n = closed_line.split("|")[3].strip()
    assert static_n == "3/3"
    assert closed_n == "3/3"


def test_build_verdict_table_excluded_and_under_n_are_surfaced(tmp_path):
    for i in range(1, 11):
        _make_run(
            tmp_path,
            cell="A",
            name=f"run-{i:03d}",
            arm="static",
            one_hop_extra_ms=7.0 + 0.01 * i,
            cpu_pct=40.0 + i,
        )
    _make_run(
        tmp_path,
        cell="A",
        name="run-011",
        arm="static",
        one_hop_extra_ms=999.0,
        excluded=True,
        exclusion_reason="gate:arm-failed",
    )
    for i in range(1, 5):  # deliberately under n >= 10 for B
        _make_run(
            tmp_path,
            cell="B",
            name=f"run-{i:03d}",
            arm="static",
            one_hop_extra_ms=9.0 + 0.01 * i,
            cpu_pct=55.0 + i,
        )
    doc = _cells_doc(arms=("static",))
    margins = {
        "one_hop_wall_ms": {"margin": 2.0},
        "carla_process_cpu_pct": {"margin": 10.0},
    }
    table = build_verdict_table(tmp_path / "A", tmp_path / "B", "A", "B", margins, doc, min_n=10)
    assert "one_hop_wall_ms" in table
    assert "carla_process_cpu_pct" in table
    assert "1 run(s) excluded from A" in table
    assert "UNDER-N" in table  # B only has 4 runs


def test_build_verdict_table_unbound_cell_is_unavailable_without_touching_runs(tmp_path):
    """achieved_rate_ratio is unbound for a cell whose lidar_expected_hz
    is registered null: the table must say so clearly WITHOUT ever
    walking a run directory for that metric (no run-* trees exist here
    at all, yet the row still renders correctly)."""
    doc = _cells_doc(b_overrides={"lidar_expected_hz": None})
    margins = {"achieved_rate_ratio": {"margin": 0.02}}
    table = build_verdict_table(tmp_path / "A", tmp_path / "B", "A", "B", margins, doc, min_n=10)
    assert "insufficient-data" in table
    assert "UNAVAILABLE" in table
    assert "lidar_expected_hz" in table
    assert "cell B" in table


def test_build_verdict_table_unknown_margin_metric_has_no_binder(tmp_path):
    doc = _cells_doc()
    margins = {"some_future_metric": {"margin": 1.0}}
    table = build_verdict_table(tmp_path / "A", tmp_path / "B", "A", "B", margins, doc, min_n=10)
    assert "no registered extractor" in table.lower()
    assert "some_future_metric" in table


def test_build_verdict_table_references_readme_provenance(tmp_path):
    doc = _cells_doc()
    margins = {"one_hop_wall_ms": {"margin": 2.0}}
    table = build_verdict_table(tmp_path / "A", tmp_path / "B", "A", "B", margins, doc, min_n=10)
    assert "README.md" in table
    assert "Primary-duel metric definitions" in table


def test_build_verdict_table_attaches_fit_residual_note(tmp_path):
    for i in range(1, 4):
        _make_run(tmp_path, cell="A", name=f"run-{i:03d}", arm="static", one_hop_extra_ms=7.0)
        _make_run(tmp_path, cell="B", name=f"run-{i:03d}", arm="static", one_hop_extra_ms=8.0)
    doc = _cells_doc(arms=("static",))
    margins = {"one_hop_wall_ms": {"margin": 2.0}}
    table = build_verdict_table(tmp_path / "A", tmp_path / "B", "A", "B", margins, doc, min_n=3)
    assert "fit_residual_ns median" in table


def test_build_verdict_table_raises_when_cells_share_no_arm(tmp_path):
    doc = _cells_doc()
    doc["cells"][0]["arms"] = ["static"]
    doc["cells"][1]["arms"] = ["closed-loop"]
    margins = {"one_hop_wall_ms": {"margin": 2.0}}
    with pytest.raises(ValueError):
        build_verdict_table(tmp_path / "A", tmp_path / "B", "A", "B", margins, doc, min_n=10)


def test_main_reports_unknown_cell_id_cleanly(tmp_path, capsys):
    """duel_verdict.main must match cell_info.main's own handling of an
    unregistered cell id: a printed CELL FAIL and a non-zero exit code,
    not an uncaught UnknownIdError traceback."""
    from benchmarks.scripts.duel_verdict import EXIT_UNKNOWN_ID, main

    (tmp_path / "results" / "Q").mkdir(parents=True)
    (tmp_path / "results" / "B").mkdir(parents=True)
    rc = main(["Q", "B", "--results", str(tmp_path / "results")])
    assert rc == EXIT_UNKNOWN_ID
    assert "CELL FAIL" in capsys.readouterr().err
