"""sweep_verdict.py: assembles evaluate_ceiling's four inputs from a
synthetic run directory and renders a per-point M4 sweep verdict table.

Each "firing" test is built so its scenario's own numbers isolate exactly
one of the four pre-registered disjuncts -- the other three are kept
comfortably healthy -- so a test passing for the wrong reason (e.g. two
criteria firing at once, with the assertion only checking one) is not
possible. This mirrors analysis/test_ceiling.py's own convention.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from benchmarks.analysis.ceiling import CeilingVerdict
from benchmarks.analysis.manifest import RunManifest
from benchmarks.analysis.publisher_counts import publisher_counts_doc
from benchmarks.scripts import sweep_verdict
from benchmarks.scripts.cell_info import load_cells_doc, metrics_for
from benchmarks.scripts.sweep_verdict import RunVerdict, render_verdicts, verdict_for_run

BASE = 1_700_000_000_000_000_000
TOPIC = "/lidar"
# Matches cell A's real registration in cells.yaml's metrics: block (tick_hz
# and lidar_expected_hz coincide there), so main()-level tests that target
# cell A need no --tick-hz/--lidar-expected-hz override.
TICK_HZ = 20.0
LIDAR_EXPECTED_HZ = 20.0
# S5: every fixture in this file builds a healthy, well-populated clock.csv
# (>= 2 rows), so its actual window branch is always "fittable"; passing the
# same expectation is the "no surprise, no note" baseline every non-S5 test
# wants. The S5-specific tests below set up their own mismatch deliberately.
EXPECTED_FITTABLE = "fittable"


# --- synthetic run directory builders -------------------------------------


def _write_manifest(
    run_dir, *, arm, approach="python-bridge", cell="A", excluded=False, exclusion_reason=""
):
    placement = {
        "run_mode": "container",
        "container_image": "img@sha256:deadbeef",
        "observer_env": "bench-observer:universe-devel",
    }
    if approach in ("extension", "tier4-native"):
        placement["engine_build_id"] = "b4c93e55-fc8f-42fc-b377-358910364e1c"
    RunManifest(
        cell=cell,
        approach=approach,
        map_name="Town10HD_Opt",
        run_index=1,
        arm=arm,
        harness_git_sha="abc",
        patches_git_sha="def",
        transport={
            "rmw": "rmw_cyclonedds_cpp",
            "shm_enabled": False,
            "dds_profile_sha256": "0" * 64,
        },
        carla_version="0.10-fork",
        autoware_image="img",
        started_at_ns=0,
        excluded=excluded,
        exclusion_reason=exclusion_reason,
        placement=placement,
    ).save(run_dir / "manifest.json")


def _write_resources_csv(run_dir, sample_ns, rtf, processes=("carla", "observer")):
    header = "sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf\n"
    lines = [header]
    for process in processes:
        for t, r in zip(sample_ns, rtf):
            lines.append(f"{int(t)},{process},1.0,100,-1,-1,{r}\n")
    (run_dir / "resources.csv").write_text("".join(lines))


def _write_clock_csv(run_dir, wall_ns, rtf=1.0):
    """clock.csv for `wall_ns` arrivals, with sim time advancing at
    `rtf` x wall time.

    `clock_ns` is a real sim series, not a row index: `verdict_for_run`
    takes the expected-count window off the SIM extent (`lidar_expected_
    hz` is a sim-domain rate), so a fixture whose `clock_ns` column is
    arbitrary cannot say anything about that count. The default rtf=1.0
    makes the two spans coincide, which is what every fixture below that
    is not ABOUT the domain wants; the domain test passes rtf != 1.
    """
    wall0 = int(wall_ns[0])
    lines = ["clock_ns,arrival_system_ns\n"]
    for w in wall_ns:
        lines.append(f"{int(round((int(w) - wall0) * rtf))},{int(w)}\n")
    (run_dir / "clock.csv").write_text("".join(lines))


def _write_observer_csv(run_dir, topic=TOPIC, arrivals=()):
    lines = ["topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes\n"]
    for a in arrivals:
        lines.append(f"{topic},{int(a)},{int(a)},{int(a)},0,1048576\n")
    (run_dir / "observer.csv").write_text("".join(lines))


def _write_publisher_counts(run_dir, topic, count):
    """`count` published messages, written through collect_gt.py's own
    writer so these fixtures track the real on-disk contract.

    The stamps themselves are evenly spread over the fixture's run and
    otherwise arbitrary: unlike `duel_verdict.py`, this tool's
    reconciliation is whole-run on every term (see
    `_publisher_rate_ratio`), so it reads the total and never filters on
    a stamp.
    """
    stamps = (BASE + np.arange(count) * 50_000_000).tolist()
    (run_dir / "publisher_counts.json").write_text(
        json.dumps(publisher_counts_doc({topic: stamps}))
    )


def _write_quality(run_dir, gate_pass=True, reasons=None, **extra):
    # Registered schema (benchmarks/README.md "M5 gate result"):
    # dataclasses.asdict(QualityStats) verbatim plus four provenance keys.
    # `gate_pass` is the only field a consumer may treat as the verdict, so
    # these defaults are otherwise arbitrary placeholders -- present so the
    # fixture matches the registered SHAPE, not because sweep_verdict reads
    # them.
    doc = {
        "pose_err_p50_m": 0.05,
        "pose_err_p95_m": 0.12,
        "pose_err_max_m": 0.20,
        "pose_bias_m": 0.03,
        "lateral_dev_p95_m": 0.08,
        "goal_closest_approach_m": 0.5,
        "goal_terminal_distance_m": 0.5,
        "ndt_rate_ratio": 1.0,
        "gate_pass": gate_pass,
        "reasons": reasons or [],
        "arm": "closed-loop",
        "window_sim_ns": [0, 5_000_000_000],
        "ladder_branch": "absolute",
        "expected_ndt_hz": 10.0,
    }
    doc.update(extra)
    (run_dir / "quality.json").write_text(json.dumps(doc))


def _healthy_paced_point(run_dir, *, arm="paced", approach="python-bridge", dip=None):
    """60 x 1 Hz resources samples (rtf 0.99, optionally dipped) plus a
    60 s / 20 Hz clock.csv and a healthy (>90%) publisher count -- the
    common healthy baseline every "fires only its own criterion" test
    starts from, then deviates exactly one input away from healthy."""
    _write_manifest(run_dir, arm=arm, approach=approach)
    sample_ns = BASE + np.arange(60) * 1_000_000_000
    rtf = np.full(60, 0.99)
    if dip is not None:
        lo, hi = dip
        rtf[lo:hi] = 0.5
    _write_resources_csv(run_dir, sample_ns, rtf)
    wall = BASE + np.arange(1201) * 50_000_000  # 1200 gaps * 50ms = 60.0s, 20 Hz
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    _write_publisher_counts(run_dir, TOPIC, 1190)  # 1190/1200 = 0.992, healthy
    _write_quality(run_dir, gate_pass=True)
    return run_dir


# --- the four disjuncts, each firing alone --------------------------------


def test_paced_point_over_ceiling_via_rtf(tmp_path):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _healthy_paced_point(run_dir, dip=(20, 35))  # 15 s sustained rtf dip

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=TICK_HZ,
        lidar_expected_hz=LIDAR_EXPECTED_HZ,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert v.verdict.reached
    assert len(v.verdict.reasons) == 1
    assert v.verdict.reasons[0].startswith("rtf<")
    assert not any("tick rate" in r for r in v.verdict.reasons)
    assert not any("publisher rate" in r for r in v.verdict.reasons)
    assert not any("quality" in r for r in v.verdict.reasons)
    assert v.publisher_rate_ratio == pytest.approx(1190 / 1200)
    assert v.quality_ok is True


def test_unpaced_point_over_ceiling_via_tick_ratio(tmp_path):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="unpaced")
    # No resources.csv at all: the unpaced path must never open it.
    n1, n2, n3 = 300, 150, 300  # gaps; degraded window = 150 * 0.1s = 15s > 10s
    gaps_s = [0.05] * n1 + [0.1] * n2 + [0.05] * n3
    wall = [BASE]
    for g in gaps_s:
        wall.append(wall[-1] + int(g * 1e9))
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    window_s = sum(gaps_s)
    expected = round(window_s * LIDAR_EXPECTED_HZ)
    _write_publisher_counts(run_dir, TOPIC, round(expected * 0.99))
    _write_quality(run_dir, gate_pass=True)

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=TICK_HZ,
        lidar_expected_hz=LIDAR_EXPECTED_HZ,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert v.verdict.reached
    assert len(v.verdict.reasons) == 1
    assert "tick rate" in v.verdict.reasons[0]
    assert not any(r.startswith("rtf<") for r in v.verdict.reasons)
    assert not any("publisher rate" in r for r in v.verdict.reasons)
    assert not any("quality" in r for r in v.verdict.reasons)


def test_publisher_rate_firing(tmp_path):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _healthy_paced_point(run_dir)
    # Override the healthy publisher count with a starved one: 500/1200.
    _write_publisher_counts(run_dir, TOPIC, 500)

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=TICK_HZ,
        lidar_expected_hz=LIDAR_EXPECTED_HZ,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert v.verdict.reached
    assert len(v.verdict.reasons) == 1
    assert "publisher rate" in v.verdict.reasons[0]
    assert v.publisher_rate_ratio == pytest.approx(500 / 1200)


def test_expected_lidar_count_uses_the_sim_span_not_the_wall_span(tmp_path):
    """`lidar_expected_hz` is a SIM-domain rate (`min(1 / sensor_tick,
    tick_hz)`; both periods are simulation time), so the expected count
    is the SIM span times that rate.

    This run's clock advances at 0.92x wall: 60 s of wall time is 55.2 s
    of sim time, in which the sensor is due 1104 scans, not 1200. The
    publisher delivers 1010 -- healthy against the sim-span expectation
    (0.915), starved against the wall-span one (0.842). Taking the wall
    span therefore reports "ceiling reached, publisher rate" for a
    publisher that dropped nothing, and does so precisely on the arms
    the sweep runs below real time, where the ceiling verdict is the
    point. RTF has its own registered disjunct here (and the unpaced
    arm's tick_rate_ratio substitute); it must not leak into this one
    as well.
    """
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="paced")
    sample_ns = BASE + np.arange(60) * 1_000_000_000
    # Above evaluate_ceiling's 0.9 rtf threshold, and equal to the clock
    # slope below: the fixture is one self-consistent 0.92x run.
    _write_resources_csv(run_dir, sample_ns, np.full(60, 0.92))
    wall = BASE + np.arange(1201) * 50_000_000  # 60.0 s of WALL time
    _write_clock_csv(run_dir, wall, rtf=0.92)  # 55.2 s of SIM time
    _write_observer_csv(run_dir)
    _write_publisher_counts(run_dir, TOPIC, 1010)
    _write_quality(run_dir, gate_pass=True)

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=TICK_HZ,
        lidar_expected_hz=LIDAR_EXPECTED_HZ,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    sim_expected = round(55.2 * LIDAR_EXPECTED_HZ)  # 1104
    wall_expected = round(60.0 * LIDAR_EXPECTED_HZ)  # 1200
    assert v.publisher_rate_ratio == pytest.approx(1010 / sim_expected)
    assert v.publisher_rate_ratio != pytest.approx(1010 / wall_expected)
    # The discriminating property: the two domains land on opposite
    # sides of the pre-registered 0.9 disjunct for this run.
    assert 1010 / wall_expected < 0.9 <= 1010 / sim_expected
    assert not v.verdict.reached
    assert not any("publisher rate" in r for r in v.verdict.reasons)


def test_quality_firing(tmp_path):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _healthy_paced_point(run_dir)
    _write_quality(run_dir, gate_pass=False, reasons=["pose_error drift 0.4 >= 0.2"])

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=TICK_HZ,
        lidar_expected_hz=LIDAR_EXPECTED_HZ,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert v.verdict.reached
    assert len(v.verdict.reasons) == 1
    assert "quality" in v.verdict.reasons[0]
    assert v.quality_ok is False


# --- exclusion, NaN, and missing-publisher-count handling -----------------


def test_excluded_run_never_enters_a_verdict(tmp_path):
    run_dir = tmp_path / "run-000"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="paced", excluded=True, exclusion_reason="crash:cell-launch")
    # No clock.csv / resources.csv / observer.csv / quality.json at all: an
    # excluded run legitimately may have none of these (exclusions.md).

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=TICK_HZ,
        lidar_expected_hz=LIDAR_EXPECTED_HZ,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert v.excluded
    assert v.verdict is None
    assert v.exclusion_reason == "crash:cell-launch"
    table = render_verdicts("A", "vlp16", [v])
    assert "EXCLUDED" in table
    assert "crash:cell-launch" in table


def test_missing_publisher_counts_is_not_measurable_not_zero(tmp_path):
    """E-cells have no independent publisher-side count: publisher_counts.json
    is simply absent, and that must read as "not measurable", never as the
    zero-throughput case (test below), which fires for real."""
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="paced", approach="python-bridge")
    sample_ns = BASE + np.arange(60) * 1_000_000_000
    _write_resources_csv(run_dir, sample_ns, np.full(60, 0.99))
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    _write_quality(run_dir, gate_pass=True)
    # Deliberately no publisher_counts.json.

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=TICK_HZ,
        lidar_expected_hz=LIDAR_EXPECTED_HZ,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert not v.verdict.reached
    assert v.verdict.reasons == []
    assert v.publisher_rate_ratio == 1.0
    assert v.publisher_note == sweep_verdict.NOT_MEASURABLE
    assert math.isnan(v.observer_loss_rate)
    table = render_verdicts("E", "vlp16", [v])
    assert "not measurable" in table
    assert "NaN" in table


def test_zero_published_count_fires_and_reports_nan_not_zero(tmp_path):
    """The opposite, file-backed case: publisher_counts.json exists and
    genuinely says 0 (e.g. the ablation arm, publish disabled by design).
    This must FIRE the publisher disjunct (real zero throughput) while still
    surfacing observer_loss_rate as NaN rather than a misleading 0.0 -- the
    two failure modes reconcile_drops warns about are not the same thing."""
    run_dir = tmp_path / "run-002"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="ablation", approach="python-bridge")
    sample_ns = BASE + np.arange(60) * 1_000_000_000
    _write_resources_csv(run_dir, sample_ns, np.full(60, 0.99))  # ablation is still paced-tick
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    _write_publisher_counts(run_dir, TOPIC, 0)
    # No quality.json: the ablation arm defaults quality_ok=True with a note
    # (no closed loop runs, so no M5 measurement is possible).

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=TICK_HZ,
        lidar_expected_hz=LIDAR_EXPECTED_HZ,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert v.verdict.reached
    assert len(v.verdict.reasons) == 1
    assert "publisher rate" in v.verdict.reasons[0]
    assert v.publisher_rate_ratio == 0.0
    assert math.isnan(v.observer_loss_rate)
    assert v.quality_ok is True
    assert v.quality_note == sweep_verdict.NOT_APPLICABLE_ABLATION


def test_non_ablation_arm_requires_quality_json(tmp_path):
    """Missing quality.json must not silently default to a pass on an arm
    that IS supposed to close the loop -- only "ablation" gets that default."""
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="paced")
    sample_ns = BASE + np.arange(60) * 1_000_000_000
    _write_resources_csv(run_dir, sample_ns, np.full(60, 0.99))
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    _write_publisher_counts(run_dir, TOPIC, 1190)
    # No quality.json.

    with pytest.raises(FileNotFoundError, match="quality"):
        verdict_for_run(
            run_dir,
            topic=TOPIC,
            tick_hz=TICK_HZ,
            lidar_expected_hz=LIDAR_EXPECTED_HZ,
            expected_window_branch=EXPECTED_FITTABLE,
        )


# --- table rendering is pure formatting (no filesystem) --------------------


def test_render_verdicts_is_pure_and_needs_no_filesystem():
    v = RunVerdict(
        run="run-003",
        arm="paced",
        excluded=False,
        exclusion_reason="",
        verdict=CeilingVerdict(True, ["rtf<0.9 sustained >= 10.0s"]),
        publisher_rate_ratio=0.95,
        publisher_note=None,
        observer_loss_rate=0.01,
        quality_ok=True,
        quality_note=None,
        window_branch_note=None,
    )
    table = render_verdicts("A", "vlp16", [v])
    assert "run-003" in table
    assert "True" in table
    assert "rtf<0.9" in table


def test_render_verdicts_reports_skipped_out_of_arm_count():
    """Pure, filesystem-free: skipped_out_of_arm must be visible in the
    table text, not just a caller-side print -- a skipped run is exactly
    the class of silent gap this campaign guards against."""
    table = render_verdicts("A", "vlp16", [], skipped_out_of_arm=3)
    assert "3 run(s) skipped" in table
    # A caller that never skips anything sees byte-identical output to
    # before this parameter existed.
    assert render_verdicts("A", "vlp16", []) == render_verdicts(
        "A", "vlp16", [], skipped_out_of_arm=0
    )


# --- _rtf_series_from_resources: dedup, not concatenation ------------------


def test_rtf_series_from_resources_dedups_across_processes_not_concatenates():
    """Pins the dedup: two processes x 5 samples each must yield a 5-sample
    series (one process's column), not 10 (both columns concatenated)."""
    sample_ns = BASE + np.arange(5) * 1_000_000_000
    rtf = np.array([0.91, 0.92, 0.93, 0.94, 0.95])
    resources = {
        "carla": {"sample_system_ns": sample_ns, "rtf": rtf},
        "observer": {"sample_system_ns": sample_ns, "rtf": rtf},
    }

    out_ns, out_rtf = sweep_verdict._rtf_series_from_resources(resources)

    assert out_ns.size == 5
    np.testing.assert_array_equal(out_ns, sample_ns)
    np.testing.assert_allclose(out_rtf, rtf)


# --- S2: tick_hz and lidar_expected_hz are separate, non-conflatable -------


def test_tick_hz_and_lidar_expected_hz_are_independent_bindings(tmp_path):
    """A-hf/B-hf-shaped regression: tick_hz (world tick target) and
    lidar_expected_hz (sensor scan rate) diverge 5x on those cells. A
    shared constant would size expected_count off tick_hz and report
    publisher_rate_ratio ~= 0.2 here (500 Hz world / 100 Hz sensor), firing
    the ceiling spuriously; reading the two bindings separately must not."""
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="unpaced")
    wall = BASE + np.arange(6001) * 10_000_000  # steady 100 Hz, 60.0s
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    # Sized against lidar_expected_hz=20, NOT tick_hz=100: 60s * 20 = 1200.
    _write_publisher_counts(run_dir, TOPIC, 1190)
    _write_quality(run_dir, gate_pass=True)

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=100.0,
        lidar_expected_hz=20.0,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert not v.verdict.reached
    assert v.publisher_rate_ratio == pytest.approx(1190 / 1200)


def test_unpaced_tick_ratio_uses_tick_hz_not_lidar_expected_hz(tmp_path):
    """Swap-detector: ticks running steady at 30 Hz score BELOW the 90%
    threshold against tick_hz=100 (ratio 0.30, must fire) but ABOVE it
    against lidar_expected_hz=20 (ratio 1.50, would NOT fire) -- so this
    test only passes if the tick-rate denominator is genuinely tick_hz."""
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="unpaced")
    gap_ns = round(1e9 / 30)
    wall = BASE + np.arange(2001) * gap_ns  # steady 30 Hz, ~66.7s
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    window_s = (int(wall[-1]) - int(wall[0])) / 1e9
    expected = round(window_s * 20.0)
    _write_publisher_counts(run_dir, TOPIC, round(expected * 0.99))
    _write_quality(run_dir, gate_pass=True)

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=100.0,
        lidar_expected_hz=20.0,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert v.verdict.reached
    assert len(v.verdict.reasons) == 1
    assert "tick rate" in v.verdict.reasons[0]


def test_a_hf_real_registered_metrics_are_all_null_pending_task_26(tmp_path):
    """Grounds S2 in the real, committed cells.yaml as it now stands. A
    prior registration briefly had A-hf's tick_hz/lidar_expected_hz
    diverge in VALUE (the scenario this file's S2 fix was originally
    grounded in); a later amendment (Task 26, "Optional cells -- E-opt,
    A-hf/B-hf") found that registration itself wrong -- A-hf's LiDAR
    sensor_tick is set explicitly by Task 26, not derived from cell A's
    -- and nulled all three rate bindings on both A-hf and B-hf. A-hf is
    not a sweep_classes cell (applies_to excludes it), so this calls
    verdict_for_run directly with metrics_for's real numbers rather than
    through main()'s --class gate. lidar_expected_hz is checked first
    (verdict_for_run computes expected_count before the arm branch), so
    that is the disjunct that fires, not tick_hz."""
    metrics = metrics_for(load_cells_doc(), "A-hf")
    assert metrics["tick_hz"] is None
    assert metrics["lidar_expected_hz"] is None

    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="unpaced", cell="A-hf")
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    _write_publisher_counts(run_dir, TOPIC, 1190)
    _write_quality(run_dir, gate_pass=True)

    with pytest.raises(ValueError, match="lidar_expected_hz"):
        verdict_for_run(
            run_dir,
            topic=TOPIC,
            tick_hz=metrics["tick_hz"],
            lidar_expected_hz=metrics["lidar_expected_hz"],
            expected_window_branch=EXPECTED_FITTABLE,
        )


def test_missing_tick_hz_message_names_task_26_for_a_hf(tmp_path):
    """A-hf's tick_hz is pending Task 26 ("Optional cells -- E-opt,
    A-hf/B-hf"), not the "Task 12" this file's own development briefly
    (and wrongly) attributed it to before checking cells.yaml's actual
    citation -- see TICK_HZ_PENDING_TASK's comment. Uses a synthetic
    lidar_expected_hz to isolate the tick_hz check from A-hf's OWN
    lidar_expected_hz also being null today."""
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="unpaced", approach="extension", cell="A-hf")
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir, topic="/sensing/lidar/top/pointcloud_raw_ex")
    _write_publisher_counts(run_dir, "/sensing/lidar/top/pointcloud_raw_ex", 1190)
    _write_quality(run_dir, gate_pass=True)

    with pytest.raises(ValueError) as exc_info:
        verdict_for_run(
            run_dir,
            topic="/sensing/lidar/top/pointcloud_raw_ex",
            tick_hz=None,
            lidar_expected_hz=20.0,  # synthetic: isolates the tick_hz check
            expected_window_branch=EXPECTED_FITTABLE,
        )

    message = str(exc_info.value)
    assert "metrics.tick_hz" in message
    assert "'A-hf'" in message
    assert "Task 26" in message


# --- Minor 15: no plain flag may silently override a registered value ----
# Generalized to all three CLI-overridable bindings (tick_hz,
# lidar_expected_hz, topic): the reasoning does not distinguish them, so
# the same parametrized suite exercises all three flag families through
# the one shared `_resolve_override`.

_OVERRIDE_FAMILIES = [
    ("tick-hz", "tick_hz"),
    ("lidar-expected-hz", "lidar_expected_hz"),
    ("topic", "lidar_topic"),
]


@pytest.mark.parametrize("flag,key", _OVERRIDE_FAMILIES)
def test_resolve_override_no_cli_input_returns_the_registered_value(flag, key):
    assert sweep_verdict._resolve_override(flag, key, "REG", None, None) == "REG"


@pytest.mark.parametrize("flag,key", _OVERRIDE_FAMILIES)
def test_resolve_override_plain_flag_agreeing_with_registry_is_fine(flag, key):
    assert sweep_verdict._resolve_override(flag, key, "REG", "REG", None) == "REG"


@pytest.mark.parametrize("flag,key", _OVERRIDE_FAMILIES)
def test_resolve_override_plain_flag_fills_in_an_unregistered_binding(flag, key):
    """registered=None (e.g. cell B's lidar_expected_hz pending Task 13, or
    cell B's tick_hz likewise): nothing to disagree with, so the plain
    flag legitimately supplies the missing value."""
    assert sweep_verdict._resolve_override(flag, key, None, "NEW", None) == "NEW"


@pytest.mark.parametrize("flag,key", _OVERRIDE_FAMILIES)
def test_resolve_override_plain_flag_disagreeing_with_registry_fails_loudly(flag, key):
    """The Minor 15 fix itself, for every flag family: a hand-typed plain
    flag that disagrees with a REAL registered value must not silently
    win. The error names the disagreement and the matching --override-*
    escape hatch."""
    with pytest.raises(ValueError, match=key) as exc_info:
        sweep_verdict._resolve_override(flag, key, "REG", "OTHER", None)
    assert f"--override-{flag}" in str(exc_info.value)


@pytest.mark.parametrize("flag,key", _OVERRIDE_FAMILIES)
def test_resolve_override_flag_always_wins_with_no_check(flag, key):
    """--override-<flag> is the deliberate-what-if escape hatch: it wins
    even against a real, disagreeing registered value, with no error."""
    assert sweep_verdict._resolve_override(flag, key, "REG", None, "OVERRIDE") == "OVERRIDE"
    # Wins even when the plain flag is ALSO given (and would itself
    # disagree with the registry on its own).
    assert sweep_verdict._resolve_override(flag, key, "REG", "OTHER", "OVERRIDE") == "OVERRIDE"


# --- S5: mirror the expected-window-branch check (D10, Task 23's half) ----


def test_expected_window_branch_calibration_approach_is_unfittable():
    assert sweep_verdict._expected_window_branch("calibration") == "unfittable"


def test_expected_window_branch_every_other_approach_is_fittable():
    """Every registered non-calibration approach, not just "extension" --
    the rule is about having (or not having) a simulation loop, and only
    `approach: calibration` cells lack one."""
    for approach in ("extension", "tier4-native", "python-bridge"):
        assert sweep_verdict._expected_window_branch(approach) == "fittable"


def test_actual_window_branch_needs_at_least_two_clock_rows():
    """Verbatim analysis/clockfit.py's fit_sim_wall_affine precondition
    ("need >= 2 paired (sim, wall) samples"): fittable at exactly 2 rows,
    unfittable at 1 or 0. Must never crash on the empty case -- it is
    deliberately just a size check (see the function's own docstring)."""
    assert sweep_verdict._actual_window_branch(np.array([], dtype=np.int64)) == "unfittable"
    assert sweep_verdict._actual_window_branch(np.array([1], dtype=np.int64)) == "unfittable"
    assert sweep_verdict._actual_window_branch(np.array([1, 2], dtype=np.int64)) == "fittable"


def test_window_branch_note_is_none_when_branches_match():
    """The normal case, no note needed: a run behaving exactly as its
    cell is registered to is not a finding."""
    assert sweep_verdict._window_branch_note("fittable", "fittable") is None
    assert sweep_verdict._window_branch_note("unfittable", "unfittable") is None


def test_window_branch_note_names_both_branches_on_mismatch():
    note = sweep_verdict._window_branch_note("fittable", "unfittable")
    assert note is not None
    assert "fittable" in note
    assert "unfittable" in note


def test_verdict_for_run_no_note_when_branch_matches_expectation(tmp_path):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _healthy_paced_point(run_dir)

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=TICK_HZ,
        lidar_expected_hz=LIDAR_EXPECTED_HZ,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert v.window_branch_note is None


def test_verdict_for_run_surfaces_an_unexpected_unfittable_branch(tmp_path):
    """A normally-fittable cell (extension approach, expected 'fittable')
    whose clock.csv has only 1 row (actual 'unfittable') must NOT raise --
    the run is still scored -- but the mismatch must be visible in the
    RunVerdict and in render_verdicts's notes column: benchmarks/README.md,
    "a loud finding to be reported, not a silent fallback", "visible in
    the artifact a reader sees, not only in a log"."""
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="paced", approach="extension")
    sample_ns = BASE + np.arange(60) * 1_000_000_000
    _write_resources_csv(run_dir, sample_ns, np.full(60, 0.99))
    _write_clock_csv(run_dir, [BASE])  # exactly 1 row: unfittable
    _write_observer_csv(run_dir)
    _write_publisher_counts(run_dir, TOPIC, 1)
    _write_quality(run_dir, gate_pass=True)

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=TICK_HZ,
        lidar_expected_hz=LIDAR_EXPECTED_HZ,
        expected_window_branch=EXPECTED_FITTABLE,
    )

    assert v.verdict is not None  # still scored, not aborted
    assert v.window_branch_note is not None
    assert "fittable" in v.window_branch_note
    assert "unfittable" in v.window_branch_note
    table = render_verdicts("A", "vlp16", [v])
    assert "window branch" in table


def test_main_surfaces_window_branch_mismatch_in_the_printed_table(tmp_path, capsys):
    """End-to-end: main() resolves cell A's expected branch from the real
    cells.yaml (extension -> fittable) and surfaces a real run's mismatch
    in the printed table -- not a log line, the artifact itself."""
    cell_dir = tmp_path / "A" / "run-001"
    cell_dir.mkdir(parents=True)
    _write_manifest(cell_dir, arm="paced", approach="extension")
    sample_ns = BASE + np.arange(60) * 1_000_000_000
    _write_resources_csv(cell_dir, sample_ns, np.full(60, 0.99))
    _write_clock_csv(cell_dir, [BASE])  # 1 row: unfittable, unexpected for A
    _write_observer_csv(cell_dir)
    _write_publisher_counts(cell_dir, TOPIC, 1)
    _write_quality(cell_dir, gate_pass=True)

    rc = sweep_verdict.main(
        ["A", "--class", "vlp16", "--results-root", str(tmp_path), "--override-topic", TOPIC]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "window branch" in out
    assert "fittable" in out
    assert "unfittable" in out


def test_tick_hz_pending_task_entries_are_all_still_actually_null():
    """TICK_HZ_PENDING_TASK is hand-maintained -- no cells.yaml field
    carries "which task owns this null". This pins the other half of its
    correctness: every cell it lists must currently read tick_hz == None
    in the real, committed cells.yaml. The moment a cell's tick_hz is
    registered, this test fails, forcing the mapping to be updated in the
    SAME change rather than silently drifting stale (the coordinator's
    flagged risk, after A-hf's tick_hz was found listed while unpaced was
    unreachable for it -- this is the general form of that check)."""
    doc = load_cells_doc()
    for cell in sweep_verdict.TICK_HZ_PENDING_TASK:
        assert metrics_for(doc, cell)["tick_hz"] is None, (
            f"{cell}'s tick_hz is no longer null in cells.yaml; update or "
            "remove its TICK_HZ_PENDING_TASK entry to match"
        )


# --- fail-clearly on an unbound metric (never substitute a plausible number)


def test_missing_lidar_expected_hz_fails_clearly(tmp_path):
    """cell B's real registration: lidar_expected_hz is null pending Task
    13. Must raise, never fall back to tick_hz or any other number."""
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _healthy_paced_point(run_dir)

    with pytest.raises(ValueError, match="lidar_expected_hz"):
        verdict_for_run(
            run_dir,
            topic=TOPIC,
            tick_hz=TICK_HZ,
            lidar_expected_hz=None,
            expected_window_branch=EXPECTED_FITTABLE,
        )


def test_missing_tick_hz_on_unpaced_arm_fails_clearly(tmp_path):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="unpaced")
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    _write_publisher_counts(run_dir, TOPIC, 1190)
    _write_quality(run_dir, gate_pass=True)

    with pytest.raises(ValueError, match="tick_hz"):
        verdict_for_run(
            run_dir,
            topic=TOPIC,
            tick_hz=None,
            lidar_expected_hz=LIDAR_EXPECTED_HZ,
            expected_window_branch=EXPECTED_FITTABLE,
        )


def test_missing_tick_hz_message_names_cell_and_pending_task(tmp_path):
    """The message must read as "known pending dependency", not "the tool
    is broken": it names the missing binding (metrics.tick_hz), the cell,
    and cell B's real owning task (13, per benchmarks/README.md's
    2026-07-28 tick_hz amendment log) -- an operator hitting this mid-sweep
    must be able to tell this apart from a bug in the tool at a glance."""
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="unpaced", approach="tier4-native", cell="B")
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir, topic="/sensing/lidar/top/pointcloud_raw_ex")
    _write_publisher_counts(run_dir, "/sensing/lidar/top/pointcloud_raw_ex", 1190)
    _write_quality(run_dir, gate_pass=True)

    with pytest.raises(ValueError) as exc_info:
        verdict_for_run(
            run_dir,
            topic="/sensing/lidar/top/pointcloud_raw_ex",
            tick_hz=None,
            lidar_expected_hz=LIDAR_EXPECTED_HZ,
            expected_window_branch=EXPECTED_FITTABLE,
        )

    message = str(exc_info.value)
    assert "metrics.tick_hz" in message
    assert "'B'" in message
    assert "Task 13" in message
    assert "not a defect in this tool" in message


def test_missing_tick_hz_message_has_no_task_number_for_an_unmapped_cell(tmp_path):
    """A cell not in the pending-task mapping (including any future one)
    must not have a task number invented for it -- an unverified "Task N"
    claim would be exactly the checkably-wrong-claim failure mode this
    campaign has been burned by before."""
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(
        run_dir, arm="unpaced", cell="A"
    )  # A's tick_hz IS registered; None here is synthetic
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    _write_publisher_counts(run_dir, TOPIC, 1190)
    _write_quality(run_dir, gate_pass=True)

    with pytest.raises(ValueError) as exc_info:
        verdict_for_run(
            run_dir,
            topic=TOPIC,
            tick_hz=None,
            lidar_expected_hz=LIDAR_EXPECTED_HZ,
            expected_window_branch=EXPECTED_FITTABLE,
        )

    message = str(exc_info.value)
    assert "not yet registered" in message
    assert "Task" not in message


def test_missing_lidar_topic_fails_clearly(tmp_path):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _healthy_paced_point(run_dir)

    with pytest.raises(ValueError, match="lidar_topic"):
        verdict_for_run(
            run_dir,
            topic=None,
            tick_hz=TICK_HZ,
            lidar_expected_hz=LIDAR_EXPECTED_HZ,
            expected_window_branch=EXPECTED_FITTABLE,
        )


# --- CLI ---------------------------------------------------------------


def test_main_unknown_cell_exits_2(tmp_path, capsys):
    rc = sweep_verdict.main(["Q", "--class", "vlp16", "--results-root", str(tmp_path)])
    assert rc == 2
    assert "unknown cell" in capsys.readouterr().err


def test_main_walks_results_root_and_prints_table(tmp_path, capsys):
    cell_dir = tmp_path / "A" / "run-001"
    cell_dir.mkdir(parents=True)
    _healthy_paced_point(cell_dir, approach="extension")

    # TOPIC ("/lidar") deliberately does not match cell A's real registered
    # lidar_topic, so this must go through --override-topic (Minor 15,
    # generalized): a plain --topic here would now be refused.
    rc = sweep_verdict.main(
        ["A", "--class", "vlp16", "--results-root", str(tmp_path), "--override-topic", TOPIC]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "run-001" in out
    assert "cell A, class vlp16" in out


def test_main_resolves_lidar_topic_from_cells_yaml_metrics(tmp_path, capsys):
    """S1: no --topic given. main() must resolve cell A's real, registered
    metrics_for(...)["lidar_topic"] on its own and score the point
    normally (not "not measurable") -- this is the exact gap Finding 1
    reported: without this resolution, the tool KeyErrors on every
    mandatory sweep cell (A/B/E) it exists to score."""
    cell_dir = tmp_path / "A" / "run-001"
    cell_dir.mkdir(parents=True)
    _write_manifest(cell_dir, arm="paced", approach="extension")
    sample_ns = BASE + np.arange(60) * 1_000_000_000
    _write_resources_csv(cell_dir, sample_ns, np.full(60, 0.99))
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(cell_dir, wall)
    _write_observer_csv(cell_dir, topic="/sensing/lidar/top/pointcloud_raw_ex")
    _write_publisher_counts(cell_dir, "/sensing/lidar/top/pointcloud_raw_ex", 1190)
    _write_quality(cell_dir, gate_pass=True)

    rc = sweep_verdict.main(["A", "--class", "vlp16", "--results-root", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "not measurable" not in out


def test_main_resolves_the_bridges_own_topic_for_cell_e(tmp_path, capsys):
    """E's registered lidar_topic differs from A/B's (the bridge's own
    as-emitted name). E's lidar_expected_hz is registered null pending
    Task 10/20, so --lidar-expected-hz overrides just that one binding to
    isolate the topic-resolution check from the (separately tested)
    unbound-metric failure."""
    cell_dir = tmp_path / "E" / "run-001"
    cell_dir.mkdir(parents=True)
    _write_manifest(cell_dir, arm="paced", approach="python-bridge", cell="E")
    sample_ns = BASE + np.arange(60) * 1_000_000_000
    _write_resources_csv(cell_dir, sample_ns, np.full(60, 0.99))
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(cell_dir, wall)
    _write_observer_csv(cell_dir, topic="/sensing/lidar/top/pointcloud_before_sync")
    # No publisher_counts.json: E genuinely has none (bridge is the sole
    # listener) -- resolves as "not measurable", which is fine here since
    # this test is only checking WHICH topic name was looked up.
    _write_quality(cell_dir, gate_pass=True)

    rc = sweep_verdict.main(
        ["E", "--class", "vlp16", "--results-root", str(tmp_path), "--lidar-expected-hz", "20.0"]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "not measurable" in out  # publisher count genuinely absent for E
    assert "reasons" in out  # table rendered, i.e. no crash resolving the topic


def test_main_on_cell_b_fails_clearly_when_lidar_expected_hz_is_unbound(tmp_path):
    """The one thing the registration deliberately left open: cell B's
    lidar_expected_hz is null pending Task 13 (metric-definitions-report.md
    open question 1). main() must fail clearly end-to-end, not substitute
    a plausible number (e.g. tick_hz, or A's value)."""
    cell_dir = tmp_path / "B" / "run-001"
    cell_dir.mkdir(parents=True)
    _write_manifest(cell_dir, arm="paced", approach="tier4-native", cell="B")
    sample_ns = BASE + np.arange(60) * 1_000_000_000
    _write_resources_csv(cell_dir, sample_ns, np.full(60, 0.99))
    wall = BASE + np.arange(1201) * 50_000_000
    _write_clock_csv(cell_dir, wall)
    _write_observer_csv(cell_dir, topic="/sensing/lidar/top/pointcloud_raw_ex")
    _write_publisher_counts(cell_dir, "/sensing/lidar/top/pointcloud_raw_ex", 1190)
    _write_quality(cell_dir, gate_pass=True)

    with pytest.raises(ValueError, match="lidar_expected_hz"):
        sweep_verdict.main(["B", "--class", "vlp16", "--results-root", str(tmp_path)])


def test_main_skips_non_sweep_arm_runs_and_reports_the_count(tmp_path, capsys):
    """A cell shared by the P3 duel (static/closed-loop) and the M4 sweep
    (paced/unpaced/ablation) files every run under one flat run-NNN/
    sequence (run.sh). A duel run must not be scored as a sweep point, and
    its exclusion must be visible, not silent."""
    duel_run = tmp_path / "A" / "run-001"
    duel_run.mkdir(parents=True)
    _write_manifest(duel_run, arm="static", approach="extension")  # no CSVs needed: skipped first

    sweep_run = tmp_path / "A" / "run-002"
    sweep_run.mkdir(parents=True)
    _healthy_paced_point(sweep_run, approach="extension")

    rc = sweep_verdict.main(
        ["A", "--class", "vlp16", "--results-root", str(tmp_path), "--override-topic", TOPIC]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "run-002" in out
    assert "run-001" not in out
    assert "1 run(s) skipped" in out


def test_main_tick_hz_flag_disagreeing_with_registry_fails_loudly(tmp_path):
    """Minor 15, end-to-end: cell A's real registered tick_hz is 20.0; an
    explicit --tick-hz 999 must fail loudly rather than silently win. This
    is refused before any run directory is even read (results-root here
    has no A/ subdirectory at all)."""
    with pytest.raises(ValueError, match="tick_hz"):
        sweep_verdict.main(
            ["A", "--class", "vlp16", "--results-root", str(tmp_path), "--tick-hz", "999"]
        )


def test_main_override_tick_hz_flag_bypasses_the_registry_check(tmp_path):
    """--override-tick-hz's whole point: it must NOT raise even though 999
    disagrees with cell A's registered tick_hz=20.0."""
    rc = sweep_verdict.main(
        [
            "A",
            "--class",
            "vlp16",
            "--results-root",
            str(tmp_path),
            "--override-tick-hz",
            "999",
        ]
    )
    assert rc == 0


def test_main_lidar_expected_hz_flag_disagreeing_with_registry_fails_loudly(tmp_path):
    """The same Minor 15 guard, generalized: cell A's real registered
    lidar_expected_hz is 20.0."""
    with pytest.raises(ValueError, match="lidar_expected_hz"):
        sweep_verdict.main(
            ["A", "--class", "vlp16", "--results-root", str(tmp_path), "--lidar-expected-hz", "999"]
        )


def test_main_override_lidar_expected_hz_flag_bypasses_the_registry_check(tmp_path):
    rc = sweep_verdict.main(
        [
            "A",
            "--class",
            "vlp16",
            "--results-root",
            str(tmp_path),
            "--override-lidar-expected-hz",
            "999",
        ]
    )
    assert rc == 0


def test_main_topic_flag_disagreeing_with_registry_fails_loudly(tmp_path):
    """The same Minor 15 guard, generalized: cell A's real registered
    lidar_topic is /sensing/lidar/top/pointcloud_raw_ex, not TOPIC."""
    with pytest.raises(ValueError, match="lidar_topic"):
        sweep_verdict.main(
            ["A", "--class", "vlp16", "--results-root", str(tmp_path), "--topic", TOPIC]
        )


def test_main_override_topic_flag_bypasses_the_registry_check(tmp_path):
    rc = sweep_verdict.main(
        ["A", "--class", "vlp16", "--results-root", str(tmp_path), "--override-topic", TOPIC]
    )
    assert rc == 0
