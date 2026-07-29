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
from benchmarks.scripts import sweep_verdict
from benchmarks.scripts.sweep_verdict import RunVerdict, render_verdicts, verdict_for_run

BASE = 1_700_000_000_000_000_000
TOPIC = "/lidar"


# --- synthetic run directory builders -------------------------------------


def _write_manifest(run_dir, *, arm, approach="python-bridge", excluded=False, exclusion_reason=""):
    placement = {
        "run_mode": "container",
        "container_image": "img@sha256:deadbeef",
        "observer_env": "bench-observer:universe-devel",
    }
    if approach in ("extension", "tier4-native"):
        placement["engine_build_id"] = "b4c93e55-fc8f-42fc-b377-358910364e1c"
    RunManifest(
        cell="A",
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


def _write_clock_csv(run_dir, wall_ns):
    lines = ["clock_ns,arrival_system_ns\n"]
    for i, w in enumerate(wall_ns):
        lines.append(f"{i},{int(w)}\n")
    (run_dir / "clock.csv").write_text("".join(lines))


def _write_observer_csv(run_dir, topic=TOPIC, arrivals=()):
    lines = ["topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes\n"]
    for a in arrivals:
        lines.append(f"{topic},{int(a)},{int(a)},{int(a)},0,1048576\n")
    (run_dir / "observer.csv").write_text("".join(lines))


def _write_publisher_counts(run_dir, topic, count):
    (run_dir / "publisher_counts.json").write_text(json.dumps({topic: count}))


def _write_quality(run_dir, gate_pass=True, reasons=None):
    (run_dir / "quality.json").write_text(
        json.dumps({"gate_pass": gate_pass, "reasons": reasons or []})
    )


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

    v = verdict_for_run(run_dir, topic=TOPIC)

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
    expected = round(window_s * sweep_verdict.PACED_TICK_HZ)
    _write_publisher_counts(run_dir, TOPIC, round(expected * 0.99))
    _write_quality(run_dir, gate_pass=True)

    v = verdict_for_run(run_dir, topic=TOPIC)

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

    v = verdict_for_run(run_dir, topic=TOPIC)

    assert v.verdict.reached
    assert len(v.verdict.reasons) == 1
    assert "publisher rate" in v.verdict.reasons[0]
    assert v.publisher_rate_ratio == pytest.approx(500 / 1200)


def test_quality_firing(tmp_path):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _healthy_paced_point(run_dir)
    _write_quality(run_dir, gate_pass=False, reasons=["pose_error drift 0.4 >= 0.2"])

    v = verdict_for_run(run_dir, topic=TOPIC)

    assert v.verdict.reached
    assert len(v.verdict.reasons) == 1
    assert "quality" in v.verdict.reasons[0]
    assert v.quality_ok is False


# --- exclusion, NaN, and missing-publisher-count handling -----------------


def test_excluded_run_never_enters_a_verdict(tmp_path):
    run_dir = tmp_path / "run-000"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="paced", excluded=True, exclusion_reason="crash:carla")
    # No clock.csv / resources.csv / observer.csv / quality.json at all: an
    # excluded run legitimately may have none of these (exclusions.md).

    v = verdict_for_run(run_dir, topic=TOPIC)

    assert v.excluded
    assert v.verdict is None
    assert v.exclusion_reason == "crash:carla"
    table = render_verdicts("A", "vlp16", [v])
    assert "EXCLUDED" in table
    assert "crash:carla" in table


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

    v = verdict_for_run(run_dir, topic=TOPIC)

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

    v = verdict_for_run(run_dir, topic=TOPIC)

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
        verdict_for_run(run_dir, topic=TOPIC)


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


# --- LiDAR topic resolution (observer_topics/<cell>.yaml) -----------------


def test_lidar_topic_for_cell_reads_observer_topics_yaml_for_a():
    """Regression: cell A's own committed observer_topics/A.yaml, not a
    guessed literal. This is the real repo file, not a synthetic fixture."""
    assert sweep_verdict._lidar_topic_for_cell("A") == "/sensing/lidar/top/pointcloud_raw_ex"


def test_lidar_topic_for_cell_reads_the_bridges_own_topic_for_e():
    """E-cells' bridge emits on a different, patched-around topic name --
    the whole reason observer_topics/E.yaml exists as ITS OWN file rather
    than sharing A's."""
    assert sweep_verdict._lidar_topic_for_cell("E") == "/sensing/lidar/top/pointcloud_before_sync"


def test_lidar_topic_for_cell_falls_back_when_no_pointcloud_entry(tmp_path):
    """CAL-seam's real file has an empty topics list (Task 14 not yet
    landed); any cell whose file is absent or PointCloud2-less must fall
    back to collect_gt.DEFAULT_LIDAR_TOPIC, never silently return None or
    raise."""
    (tmp_path / "Q.yaml").write_text("/**:\n  ros__parameters:\n    topics: []\n")
    assert sweep_verdict._lidar_topic_for_cell("Q", tmp_path) == sweep_verdict.DEFAULT_LIDAR_TOPIC
    # A cell with no file at all (not even empty) takes the same fallback.
    assert (
        sweep_verdict._lidar_topic_for_cell("Nonexistent", tmp_path)
        == sweep_verdict.DEFAULT_LIDAR_TOPIC
    )


# --- PACED_TICK_HZ / camera_classes[*].fps consistency ---------------------


def test_check_paced_hz_consistency_passes_against_the_real_cells_yaml():
    from benchmarks.scripts.cell_info import load_cells_doc

    sweep_verdict._check_paced_hz_consistency(load_cells_doc(), sweep_verdict.PACED_TICK_HZ)


def test_check_paced_hz_consistency_raises_on_drift():
    doc = {"camera_classes": [{"id": "cam1", "fps": 30}]}
    with pytest.raises(ValueError, match="cam1"):
        sweep_verdict._check_paced_hz_consistency(doc, sweep_verdict.PACED_TICK_HZ)


def test_check_paced_hz_consistency_skips_when_paced_hz_is_overridden():
    """An explicit --paced-hz is a deliberate what-if; it must not be
    penalized for disagreeing with camera_classes."""
    doc = {"camera_classes": [{"id": "cam1", "fps": 20}]}
    sweep_verdict._check_paced_hz_consistency(doc, 25.0)  # would not raise


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


# --- CLI ---------------------------------------------------------------


def test_main_unknown_cell_exits_2(tmp_path, capsys):
    rc = sweep_verdict.main(["Q", "--class", "vlp16", "--results-root", str(tmp_path)])
    assert rc == 2
    assert "unknown cell" in capsys.readouterr().err


def test_main_walks_results_root_and_prints_table(tmp_path, capsys):
    cell_dir = tmp_path / "A" / "run-001"
    cell_dir.mkdir(parents=True)
    _healthy_paced_point(cell_dir, approach="extension")

    rc = sweep_verdict.main(
        ["A", "--class", "vlp16", "--results-root", str(tmp_path), "--topic", TOPIC]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "run-001" in out
    assert "cell A, class vlp16" in out


def test_main_resolves_lidar_topic_from_the_real_observer_topics_yaml(tmp_path, capsys):
    """No --topic given: main() must resolve cell A's real, committed
    observer_topics/A.yaml topic on its own and score the point normally
    (not "not measurable") -- this is the exact gap Finding 1 reported:
    without this resolution, the tool KeyErrors on every mandatory sweep
    cell (A/B/E) it exists to score."""
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
        ["A", "--class", "vlp16", "--results-root", str(tmp_path), "--topic", TOPIC]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "run-002" in out
    assert "run-001" not in out
    assert "1 run(s) skipped" in out
