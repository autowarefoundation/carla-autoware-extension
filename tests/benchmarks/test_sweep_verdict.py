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
from benchmarks.scripts.cell_info import load_cells_doc, metrics_for
from benchmarks.scripts.sweep_verdict import RunVerdict, render_verdicts, verdict_for_run

BASE = 1_700_000_000_000_000_000
TOPIC = "/lidar"
# Matches cell A's real registration in cells.yaml's metrics: block (tick_hz
# and lidar_expected_hz coincide there), so main()-level tests that target
# cell A need no --tick-hz/--lidar-expected-hz override.
TICK_HZ = 20.0
LIDAR_EXPECTED_HZ = 20.0


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

    v = verdict_for_run(run_dir, topic=TOPIC, tick_hz=TICK_HZ, lidar_expected_hz=LIDAR_EXPECTED_HZ)

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

    v = verdict_for_run(run_dir, topic=TOPIC, tick_hz=TICK_HZ, lidar_expected_hz=LIDAR_EXPECTED_HZ)

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

    v = verdict_for_run(run_dir, topic=TOPIC, tick_hz=TICK_HZ, lidar_expected_hz=LIDAR_EXPECTED_HZ)

    assert v.verdict.reached
    assert len(v.verdict.reasons) == 1
    assert "publisher rate" in v.verdict.reasons[0]
    assert v.publisher_rate_ratio == pytest.approx(500 / 1200)


def test_quality_firing(tmp_path):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _healthy_paced_point(run_dir)
    _write_quality(run_dir, gate_pass=False, reasons=["pose_error drift 0.4 >= 0.2"])

    v = verdict_for_run(run_dir, topic=TOPIC, tick_hz=TICK_HZ, lidar_expected_hz=LIDAR_EXPECTED_HZ)

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

    v = verdict_for_run(run_dir, topic=TOPIC, tick_hz=TICK_HZ, lidar_expected_hz=LIDAR_EXPECTED_HZ)

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

    v = verdict_for_run(run_dir, topic=TOPIC, tick_hz=TICK_HZ, lidar_expected_hz=LIDAR_EXPECTED_HZ)

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

    v = verdict_for_run(run_dir, topic=TOPIC, tick_hz=TICK_HZ, lidar_expected_hz=LIDAR_EXPECTED_HZ)

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
        verdict_for_run(run_dir, topic=TOPIC, tick_hz=TICK_HZ, lidar_expected_hz=LIDAR_EXPECTED_HZ)


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

    v = verdict_for_run(run_dir, topic=TOPIC, tick_hz=100.0, lidar_expected_hz=20.0)

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

    v = verdict_for_run(run_dir, topic=TOPIC, tick_hz=100.0, lidar_expected_hz=20.0)

    assert v.verdict.reached
    assert len(v.verdict.reasons) == 1
    assert "tick rate" in v.verdict.reasons[0]


def test_a_hf_real_registered_metrics_diverge_5x_and_score_cleanly(tmp_path):
    """Grounds the S2 fix in the real, committed cells.yaml: A-hf's own
    registered metrics: block, not a synthetic stand-in. A-hf is not a
    sweep_classes cell (applies_to excludes it), so this calls
    verdict_for_run directly with metrics_for's real numbers rather than
    through main()'s --class gate."""
    metrics = metrics_for(load_cells_doc(), "A-hf")
    assert metrics["tick_hz"] == 100.0
    assert metrics["lidar_expected_hz"] == 20.0

    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm="unpaced")
    wall = BASE + np.arange(6001) * 10_000_000  # steady 100 Hz
    _write_clock_csv(run_dir, wall)
    _write_observer_csv(run_dir)
    window_s = (int(wall[-1]) - int(wall[0])) / 1e9
    expected = round(window_s * metrics["lidar_expected_hz"])
    _write_publisher_counts(run_dir, TOPIC, round(expected * 0.99))
    _write_quality(run_dir, gate_pass=True)

    v = verdict_for_run(
        run_dir,
        topic=TOPIC,
        tick_hz=metrics["tick_hz"],
        lidar_expected_hz=metrics["lidar_expected_hz"],
    )

    assert not v.verdict.reached


# --- Minor 15: --tick-hz must not silently override a registered value ----


def test_resolve_tick_hz_no_cli_input_returns_the_registered_value():
    assert sweep_verdict._resolve_tick_hz(20.0, None, None) == 20.0


def test_resolve_tick_hz_plain_flag_agreeing_with_registry_is_fine():
    assert sweep_verdict._resolve_tick_hz(20.0, 20.0, None) == 20.0


def test_resolve_tick_hz_plain_flag_fills_in_an_unregistered_binding():
    """registered=None (e.g. cell B pending Task 13): nothing to disagree
    with, so --tick-hz legitimately supplies the missing value."""
    assert sweep_verdict._resolve_tick_hz(None, 25.0, None) == 25.0


def test_resolve_tick_hz_plain_flag_disagreeing_with_registry_fails_loudly():
    """The Minor 15 fix itself: a hand-typed --tick-hz that disagrees with
    a REAL registered value must not silently win."""
    with pytest.raises(ValueError, match="tick_hz") as exc_info:
        sweep_verdict._resolve_tick_hz(20.0, 25.0, None)
    assert "--override-tick-hz" in str(exc_info.value)


def test_resolve_tick_hz_override_flag_always_wins_with_no_check():
    """--override-tick-hz is the deliberate-what-if escape hatch: it wins
    even against a real, disagreeing registered value, with no error."""
    assert sweep_verdict._resolve_tick_hz(20.0, None, 999.0) == 999.0
    # Wins even when --tick-hz is ALSO given (and would itself disagree).
    assert sweep_verdict._resolve_tick_hz(20.0, 25.0, 999.0) == 999.0


# --- fail-clearly on an unbound metric (never substitute a plausible number)


def test_missing_lidar_expected_hz_fails_clearly(tmp_path):
    """cell B's real registration: lidar_expected_hz is null pending Task
    13. Must raise, never fall back to tick_hz or any other number."""
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _healthy_paced_point(run_dir)

    with pytest.raises(ValueError, match="lidar_expected_hz"):
        verdict_for_run(run_dir, topic=TOPIC, tick_hz=TICK_HZ, lidar_expected_hz=None)


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
        verdict_for_run(run_dir, topic=TOPIC, tick_hz=None, lidar_expected_hz=LIDAR_EXPECTED_HZ)


def test_missing_lidar_topic_fails_clearly(tmp_path):
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _healthy_paced_point(run_dir)

    with pytest.raises(ValueError, match="lidar_topic"):
        verdict_for_run(run_dir, topic=None, tick_hz=TICK_HZ, lidar_expected_hz=LIDAR_EXPECTED_HZ)


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
        ["A", "--class", "vlp16", "--results-root", str(tmp_path), "--topic", TOPIC]
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
