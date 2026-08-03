"""write_quality.py: the M5 gate step, from a run directory to quality.json.

Every fixture here is built so exactly one thing is wrong at a time -- the
other gate criteria are kept comfortably healthy -- so a test cannot pass
because a second criterion happened to fire. Several tests are written
specifically to DIE under a plausible wrong implementation and say so in their
docstring (the NDT source, the window branch, the wall->sim conversion, the
join tolerance, the ladder-branch provenance): a suite that stays green when
the implementation is replaced by a rejected interpretation is not pinning
anything.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

from benchmarks.analysis.manifest import RunManifest
from benchmarks.analysis.quality import MIN_JOIN_PAIRS, QualityStats
from benchmarks.scripts import sweep_verdict, write_quality
from benchmarks.scripts.cell_info import METRIC_KEYS, load_cells_doc, metrics_for
from benchmarks.scripts.write_quality import GateRefused, build_quality, main, write_quality as _wq

BASE_WALL = 1_700_000_000_000_000_000
DT_NS = 50_000_000  # 20 Hz
NDT_TOPIC = "/localization/pose_estimator/pose_with_covariance"
ODOM_TOPIC = "/localization/kinematic_state"
MAP = "SyntheticStraight"
ROUTE_LEN_M = 200.0
N_SAMPLES = 3000  # 150 s at 20 Hz, so the 20 s warm-up leaves plenty

# The repo root, for the subprocess-level CLI test and for reading run.sh.
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_ROUTES_DIR = REPO_ROOT / "benchmarks" / "config" / "routes"


# --- fixtures -------------------------------------------------------------


def _cells_yaml(
    tmp_path,
    *,
    cell="A",
    ndt_topic=NDT_TOPIC,
    ndt_expected_hz=20.0,
    ladder_branch=None,
    abs_pose_gate_m=None,
) -> str:
    metrics = {
        "lidar_topic": "/sensing/lidar/top/pointcloud_raw_ex",
        "ndt_topic": ndt_topic,
        "control_topic": "/control/command/control_cmd",
        "control_published_time_topic": None,
        "cpu_process_label": "carla-server",
        "tick_hz": 20.0,
        "lidar_expected_hz": 20.0,
        "ndt_expected_hz": ndt_expected_hz,
        "ladder_branch": ladder_branch,
        "abs_pose_gate_m": abs_pose_gate_m,
    }
    assert set(metrics) == set(METRIC_KEYS), "fixture drifted from the registry's keys"
    path = tmp_path / "cells.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "cells": [
                    {
                        "id": cell,
                        "approach": "extension",
                        "carla": "0.10-fork",
                        "map": MAP,
                        "mandatory": True,
                        "arms": ["static", "closed-loop"],
                        "metrics": metrics,
                    }
                ],
                "sweep_arms": ["paced", "unpaced", "ablation"],
            }
        )
    )
    return str(path)


def _write_route(routes_dir, *, map_name=MAP, start_m=20.0, end_m=ROUTE_LEN_M, goal=None):
    """A straight 200 m route whose goal is its own end point, so a track that
    drives to the end is BOTH inside the station window and at the goal. The
    committed routes are not like that -- see
    test_committed_route_window_cannot_reach_the_goal_criterion."""
    routes_dir.mkdir(exist_ok=True)
    n = 101
    poly = [[round(i * ROUTE_LEN_M / (n - 1), 6), 0.0] for i in range(n)]
    goal_xy = poly[-1] if goal is None else list(goal)
    (routes_dir / f"{map_name}.yaml").write_text(
        yaml.safe_dump(
            {
                "map": map_name,
                "spawn_pose": {"x": 0.0, "y": 0.0, "z": 0.0, "yaw_deg": 0.0},
                "goal": {"x": goal_xy[0], "y": goal_xy[1], "yaw_rad": 0.0},
                "stations": {"start_m": start_m, "end_m": end_m},
                "polyline": poly,
            }
        )
    )


def _track(n=N_SAMPLES, length_m=ROUTE_LEN_M, hold_n=0):
    """(sim stamps, xy) for an ego crawling from station 0 to `length_m`.

    `hold_n` leading samples are parked at station 0, which is what makes the
    spatial window and the static window disagree.
    """
    t = np.arange(n, dtype=np.int64) * DT_NS
    x = np.concatenate([np.zeros(hold_n), np.linspace(0.0, length_m, n - hold_n)])
    return t, np.column_stack([x, np.zeros(n)])


def _write_xy_csv(path, topic, stamps, xy):
    lines = ["topic,header_stamp_ns,x_m,y_m\n"]
    for t, (x, y) in zip(stamps, xy):
        lines.append(f"{topic},{int(t)},{x:.4f},{y:.4f}\n")
    path.write_text("".join(lines))


def _write_gt_csv(path, sim_ns, xy):
    lines = ["arrival_system_ns,sim_ns,x_m,y_m,z_m,yaw_rad\n"]
    for t, (x, y) in zip(sim_ns, xy):
        lines.append(f"{BASE_WALL + int(t)},{int(t)},{x:.4f},{y:.4f},0.0000,0.000000\n")
    path.write_text("".join(lines))


def _write_clock_csv(path, sim_ns, rtf=1.0):
    """clock.csv pairing each sim stamp with a wall arrival at `1 / rtf` x sim.

    rtf != 1 is what makes the static branch's wall->sim conversion observable.
    """
    lines = ["clock_ns,arrival_system_ns\n"]
    for t in sim_ns:
        lines.append(f"{int(t)},{BASE_WALL + int(round(int(t) / rtf))}\n")
    path.write_text("".join(lines))


def _write_manifest(
    run_dir, *, arm="closed-loop", cell="A", excluded=False, reason="", map_name=MAP
):
    """Write the manifest through `dataclasses.asdict`, not `save()`.

    `save()` validates `cell` and `map_name` against the REAL cells.yaml,
    which these per-test synthetic registries deliberately do not stand in
    for. The gate step reads the file back with `load_manifest`, which does
    not validate, so the JSON shape is what matters here and it is produced by
    the same dataclass.
    """
    manifest = RunManifest(
        cell=cell,
        approach="extension",
        map_name=map_name,
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
        exclusion_reason=reason,
        placement={
            "run_mode": "editor-game",
            "container_image": "img@sha256:dead",
            "observer_env": "bench-observer:universe-devel",
            "engine_build_id": "b4c93e55-fc8f-42fc-b377-358910364e1c",
        },
    )
    (run_dir / "manifest.json").write_text(json.dumps(dataclasses.asdict(manifest), indent=2))


def _run(
    tmp_path,
    monkeypatch,
    *,
    arm="closed-loop",
    ndt_bias=0.0,
    ndt_stride=1,
    ndt_stamp_offset_ns=0,
    hold_n=0,
    rtf=1.0,
    gt_stride=1,
    track_len_m=ROUTE_LEN_M,
    ndt_bias_before=None,
    ndt_stride_before=None,
    ndt_pairs_in_window=None,
    odom_lat=0.0,
    odom_lat_top=None,
    odom_lat_before=None,
    route_kwargs=None,
    **cells_kwargs,
):
    """A synthetic run directory plus the cells.yaml path that describes it.

    The `*_before` knobs and `odom_lat*` exist to make a value VARY along the
    axis a window trims, so that dropping the window changes the number. A
    fixture that is uniform along that axis pins the criterion's existence and
    nothing else -- which is how the NDT series' window binding and
    `lateral_dev_p95_m`'s value both stayed unpinned through two rounds. The
    boundary they split on is the 20 s warm-up, which is where the default
    fixture's scoring window opens (see
    test_the_spatial_window_applies_the_warm_up_discard).
    """
    monkeypatch.setattr(write_quality, "ROUTES_DIR", tmp_path / "routes")
    _write_route(tmp_path / "routes", **(route_kwargs or {}))
    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, arm=arm)
    t, xy = _track(hold_n=hold_n, length_m=track_len_m)
    cut = write_quality.WARMUP_NS
    _write_gt_csv(run_dir / "gt.csv", t[::gt_stride], xy[::gt_stride])

    # Ego odometry: a lateral profile, not a constant. `odom_lat_top` is
    # applied to the last 10% of the in-window samples so p95 and p50 differ,
    # and `odom_lat_before` only to the pre-window samples so scoring the
    # whole series differs from scoring the window.
    lat = np.full(len(t), float(odom_lat))
    before = t < cut
    if odom_lat_before is not None:
        lat[before] = odom_lat_before
    if odom_lat_top is not None:
        inside = np.nonzero(~before)[0]
        lat[inside[-max(1, inside.size // 10) :]] = odom_lat_top
    _write_xy_csv(
        run_dir / "odometry.csv", ODOM_TOPIC, t, xy + np.column_stack([np.zeros(len(t)), lat])
    )

    pose_t = t[::ndt_stride] + ndt_stamp_offset_ns
    pose_xy = xy[::ndt_stride] + [0.0, ndt_bias]
    if ndt_bias_before is not None or ndt_stride_before is not None or ndt_pairs_in_window:
        pre = pose_t < cut
        pre_t, pre_xy = pose_t[pre], pose_xy[pre]
        in_t, in_xy = pose_t[~pre], pose_xy[~pre]
        if ndt_stride_before is not None:
            pre_t, pre_xy = pre_t[::ndt_stride_before], pre_xy[::ndt_stride_before]
        if ndt_bias_before is not None:
            pre_xy = pre_xy - [0.0, ndt_bias] + [0.0, ndt_bias_before]
        if ndt_pairs_in_window:
            in_t, in_xy = in_t[:ndt_pairs_in_window], in_xy[:ndt_pairs_in_window]
        pose_t = np.concatenate([pre_t, in_t])
        pose_xy = np.concatenate([pre_xy, in_xy])
    _write_xy_csv(run_dir / "pose.csv", NDT_TOPIC, pose_t, pose_xy)

    _write_clock_csv(run_dir / "clock.csv", t, rtf=rtf)
    return run_dir, _cells_yaml(tmp_path, **cells_kwargs)


# --- the ladder's two branches --------------------------------------------


def test_absolute_branch_passes_a_clean_run(tmp_path, monkeypatch):
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["gate_pass"] is True
    assert doc["reasons"] == []
    assert doc["ladder_branch"] == "absolute"
    assert doc["pose_err_max_m"] == pytest.approx(0.05, abs=1e-6)
    assert doc["goal_closest_approach_m"] == pytest.approx(0.0, abs=1e-6)
    assert doc["ndt_rate_ratio"] == pytest.approx(1.0, abs=1e-6)


def test_absolute_branch_fails_over_the_registered_threshold(tmp_path, monkeypatch):
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.6
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["gate_pass"] is False
    assert any("pose_error max" in r for r in doc["reasons"])
    # Only the localization criterion fired: the rate and goal criteria are
    # healthy in this fixture, so the failure cannot be a coincidence.
    assert len(doc["reasons"]) == 1


def test_relative_branch_reports_the_bias_and_passes(tmp_path, monkeypatch):
    """The same 0.6 m constant offset that fails the absolute branch passes the
    relative one -- no drift, bounded spread -- with the bias recorded."""
    run_dir, cells = _run(tmp_path, monkeypatch, ladder_branch="relative", ndt_bias=0.6)
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["gate_pass"] is True
    assert doc["ladder_branch"] == "relative"
    assert doc["pose_bias_m"] == pytest.approx(0.6, abs=1e-6)
    assert doc["pose_err_p95_m"] - doc["pose_err_p50_m"] == pytest.approx(0.0, abs=1e-6)


def test_unselected_ladder_branch_refuses_and_writes_nothing(tmp_path, monkeypatch):
    """The registered R3.3 behaviour, and the single most important test here:
    an unset slot must REFUSE, not fall through to the relative branch.
    `evaluate_quality(abs_pose_gate_m=None)` IS the relative branch, so a
    silent default would record an UNGATED cell as gated."""
    run_dir, cells = _run(tmp_path, monkeypatch, ndt_bias=0.6)  # both keys null
    with pytest.raises(GateRefused, match="ladder_branch is null"):
        build_quality(run_dir, cells_yaml=cells)
    with pytest.raises(GateRefused, match="Task 11"):
        build_quality(run_dir, cells_yaml=cells)
    assert main(["--run-dir", str(run_dir), "--cells-yaml", cells]) == write_quality.EXIT_REFUSED
    assert not (run_dir / "quality.json").exists()


def test_absolute_branch_with_no_threshold_is_refused(tmp_path, monkeypatch):
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=None, ndt_bias=0.05
    )
    with pytest.raises(GateRefused, match="null abs_pose_gate_m"):
        build_quality(run_dir, cells_yaml=cells)


def test_relative_branch_with_a_threshold_is_refused(tmp_path, monkeypatch):
    """A registered threshold the relative branch would silently ignore is an
    inconsistent registration, not a harmless extra."""
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="relative", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    with pytest.raises(GateRefused, match="relative branch applies no"):
        build_quality(run_dir, cells_yaml=cells)


def test_unrecognised_ladder_branch_is_refused(tmp_path, monkeypatch):
    run_dir, cells = _run(tmp_path, monkeypatch, ladder_branch="strict", ndt_bias=0.05)
    with pytest.raises(GateRefused, match="registered branches"):
        build_quality(run_dir, cells_yaml=cells)


def test_the_ladder_cross_check_keeps_branch_and_threshold_equivalent():
    """What is falsifiable about `ladder_branch`'s provenance, in place of a
    test that was not.

    An earlier revision of this file asserted that `quality.json`'s
    `ladder_branch` "comes from the registry, not from `abs_pose_gate_m is
    None`". That assertion CANNOT FAIL: `resolve_ladder` refuses both
    inconsistent combinations, so `gate is not None` and `branch ==
    "absolute"` agree on every reachable input and the rejected inference
    yields the identical value. Mutating the writer to infer leaves the whole
    suite green -- verified by applying the mutant.

    So the honest pin is the INVARIANT that makes the inference harmless: for
    every state `resolve_ladder` accepts, the biconditional holds. If either
    half of the cross-check is ever relaxed -- which is what would let an
    unselected cell read as a deliberate relative-branch scoring -- this test
    fails, and `test_absolute_branch_with_no_threshold_is_refused` /
    `test_relative_branch_with_a_threshold_is_refused` pin the two halves
    themselves.
    """
    accepted = []
    for branch in (None, "absolute", "relative", "strict"):
        for gate in (None, 0.5):
            metrics = {"ladder_branch": branch, "abs_pose_gate_m": gate}
            try:
                accepted.append(write_quality.resolve_ladder(metrics, "A"))
            except GateRefused:
                continue
    assert accepted == [("absolute", 0.5), ("relative", None)], accepted
    for resolved_branch, resolved_gate in accepted:
        assert (resolved_gate is not None) == (resolved_branch == "absolute")


# --- the other two gate criteria ------------------------------------------


def test_ndt_rate_gate_fires(tmp_path, monkeypatch):
    """One NDT pose in four -> 5 Hz against a registered 20 Hz."""
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        ndt_stride=4,
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["gate_pass"] is False
    assert doc["ndt_rate_ratio"] == pytest.approx(0.25, abs=0.01)
    assert len(doc["reasons"]) == 1
    assert "ndt rate" in doc["reasons"][0]


def test_expected_ndt_hz_comes_from_the_registry_not_the_tick(tmp_path, monkeypatch):
    """The divisor is `metrics.ndt_expected_hz` and nothing else. This fixture
    registers 10.0 beside a `tick_hz` of 20.0 and publishes at 20 Hz, so a
    tool that reached for the tick would record 1.0 instead of 2.0."""
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        ndt_expected_hz=10.0,
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["expected_ndt_hz"] == 10.0
    assert doc["ndt_rate_ratio"] == pytest.approx(2.0, abs=1e-3)


# --- the scoring window's binding on the NDT series ----------------------
#
# N1/N2/N3: every fixture above is UNIFORM along the axis the window trims --
# a constant pose bias, a constant 20 Hz rate, a zero lateral offset, an ego
# that stops exactly at the goal -- so windowing cannot change the answer and
# dropping it entirely leaves the suite green. The fixtures below vary the
# quantity across the window boundary, and each failing case sits just past
# the threshold rather than orders of magnitude beyond it.


def test_pose_error_is_scored_only_inside_the_scoring_window(tmp_path, monkeypatch):
    """Ruling item 1, pinned: `pose_error` is the SPATIAL window's.

    The NDT pose is 0.6 m off before the window opens and 0.4 m off inside it,
    against a 0.5 m absolute gate -- so the window decides the verdict, in both
    directions and from within 0.1 m of the threshold on each side. Dropping
    the window (or widening it to the whole series) reports 0.6 m and FAILS;
    the same fixture with a uniform bias cannot tell the two apart, which is
    exactly how this binding survived two rounds unpinned.
    """
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.4,
        ndt_bias_before=0.6,
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["window_sim_ns"][0] == write_quality.WARMUP_NS
    assert doc["pose_err_max_m"] == pytest.approx(0.4, abs=1e-3)
    assert doc["pose_err_p50_m"] == pytest.approx(0.4, abs=1e-3)
    assert doc["gate_pass"] is True, doc["reasons"]


def test_the_ndt_rate_is_computed_only_inside_the_scoring_window(tmp_path, monkeypatch):
    """The other half of ruling item 1: `ndt_rate_ratio` is the window's too.

    The NDT series runs at 20 Hz inside the window and at 1 Hz before it. In
    window that is a healthy 1.00 ratio; over the whole series it is 0.874 --
    just past the registered 0.9 -- so a missing window flips the rate
    criterion. The 1 Hz prefix is also what makes the un-windowed number land
    NEAR the threshold instead of far below it.
    """
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        ndt_stride_before=20,  # 20 Hz -> 1 Hz before the window opens
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["ndt_rate_ratio"] == pytest.approx(1.0, abs=1e-3)
    assert doc["gate_pass"] is True, doc["reasons"]
    # The un-windowed ratio this fixture would produce, computed here so the
    # assertion above is known to be discriminating rather than assumed to be.
    n_before = int(write_quality.WARMUP_NS / DT_NS / 20)
    n_total = n_before + (N_SAMPLES - int(write_quality.WARMUP_NS / DT_NS))
    unwindowed = (n_total - 1) / ((N_SAMPLES - 1) * DT_NS / 1e9) / 20.0
    assert unwindowed < 0.9, unwindowed


def test_lateral_deviation_is_the_p95_of_the_in_window_series(tmp_path, monkeypatch):
    """`lateral_dev_p95_m` by VALUE, which nothing asserted before.

    The lateral profile is 0.1 m for most of the window, 0.5 m over its last
    10%, and 3.0 m before the window opens. So p95 in window is 0.5, and the
    three plausible wrong answers are all different numbers: 0.1 (p50 instead
    of p95), 3.0 (the whole series instead of the window) and 0.0 (not
    computed). A constant offset -- what `odom_bias` was, unused -- makes all
    four coincide.
    """
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        odom_lat=0.1,
        odom_lat_top=0.5,
        odom_lat_before=3.0,
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["lateral_dev_p95_m"] == pytest.approx(0.5, abs=1e-3)


def test_goal_terminal_distance_is_the_last_sample_not_the_closest(tmp_path, monkeypatch):
    """The overshoot case `goal_terminal_distance_m` exists for.

    Every other fixture stops AT the goal, so last == min and replacing one
    with the other is invisible. Here the goal sits at station 195 m of a 200 m
    track the ego drives to the end of: it passes within a sample of the goal
    (closest ~0, so the 1.0 m criterion still passes) and ends 5.0 m beyond it.
    That is precisely the "distinguishes precise arrival from overshoot"
    property the field is registered for.
    """
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        route_kwargs={"goal": (ROUTE_LEN_M - 5.0, 0.0)},
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["goal_closest_approach_m"] < 1.0
    assert doc["goal_terminal_distance_m"] == pytest.approx(5.0, abs=0.1)
    assert doc["goal_terminal_distance_m"] > doc["goal_closest_approach_m"]
    assert doc["gate_pass"] is True, doc["reasons"]


@pytest.mark.parametrize(("pairs", "refuses"), [(9, True), (10, False)])
def test_the_minimum_join_pair_count_is_bracketed(tmp_path, monkeypatch, pairs, refuses):
    """The registered minimum of 10 NDT<->GT pairs, from both sides.

    The counts are LITERALS and the constant is asserted separately, not used
    to build the parametrization. A parametrization written as
    `[MIN_JOIN_PAIRS - 1, MIN_JOIN_PAIRS]` moves WITH the constant, so it
    passes at any threshold and pins nothing -- measured: tightening 10 to 11
    survived that form. The only other test reaching this check produces ZERO
    pairs, so a threshold relaxed to 1 survived that too.

    The pre-window NDT samples are kept on purpose: they would pair with the
    ground truth if the window were dropped, so this fixture ALSO fails under
    an unwindowed NDT series.
    """
    assert MIN_JOIN_PAIRS == 10, "the registered minimum; update these literals with it"
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        ndt_pairs_in_window=pairs,
    )
    if not refuses:
        assert build_quality(run_dir, cells_yaml=cells)["gate_pass"] is True
        return
    with pytest.raises(GateRefused, match="fewer than 10 NDT") as exc:
        build_quality(run_dir, cells_yaml=cells)
    assert f"found {pairs}" in str(exc.value)


# --- the NDT source ------------------------------------------------------


def test_pose_error_reads_pose_csv_not_odometry_csv(tmp_path, monkeypatch):
    """pose.csv carries a 0.6 m NDT bias while odometry.csv is clean, so an
    implementation that scored `pose_error` on `/localization/kinematic_state`
    -- the EKF-fused pose -- would PASS this run instead of failing it. That
    substitution is exactly what README's M5 definitions forbid, because
    fusion masks NDT error."""
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.6
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["gate_pass"] is False
    assert doc["pose_err_max_m"] == pytest.approx(0.6, abs=1e-6)


def test_missing_pose_csv_is_refused(tmp_path, monkeypatch):
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    (run_dir / "pose.csv").unlink()
    with pytest.raises(GateRefused, match="NDT pose series"):
        build_quality(run_dir, cells_yaml=cells)


def test_a_header_only_pose_csv_is_refused_by_topic(tmp_path, monkeypatch):
    """The observer opens pose.csv on every run, so "the NDT pose was never
    recorded" arrives as a header-only file, not a missing one -- and it must
    name the topic and the `pose` kind rather than scoring zero rows."""
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    (run_dir / "pose.csv").write_text("topic,header_stamp_ns,x_m,y_m\n")
    with pytest.raises(GateRefused, match="has no rows in"):
        build_quality(run_dir, cells_yaml=cells)


def test_null_ndt_topic_is_refused(tmp_path, monkeypatch):
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        ndt_topic=None,
    )
    with pytest.raises(GateRefused, match="ndt_topic is null"):
        build_quality(run_dir, cells_yaml=cells)


def test_null_ndt_expected_hz_is_refused(tmp_path, monkeypatch):
    """README: a cell whose ndt_expected_hz is null cannot be gated. Cell B is
    that cell today (pending Task 13)."""
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        ndt_expected_hz=None,
    )
    with pytest.raises(GateRefused, match="ndt_expected_hz is null"):
        build_quality(run_dir, cells_yaml=cells)


# --- the ground truth and the join ---------------------------------------


def test_missing_gt_csv_is_refused(tmp_path, monkeypatch):
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    (run_dir / "gt.csv").unlink()
    with pytest.raises(GateRefused, match="ground truth"):
        build_quality(run_dir, cells_yaml=cells)


def test_out_of_order_gt_is_refused(tmp_path, monkeypatch):
    """The nearest-stamp join searchsorts gt.csv, so an unsorted series would
    pair NDT poses with the wrong ground truth instead of failing."""
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    rows = (run_dir / "gt.csv").read_text().splitlines()
    rows[1], rows[500] = rows[500], rows[1]
    (run_dir / "gt.csv").write_text("\n".join(rows) + "\n")
    with pytest.raises(GateRefused, match="non-decreasing"):
        build_quality(run_dir, cells_yaml=cells)


@pytest.mark.parametrize(
    ("offset_ns", "pairs"),
    [(10_000_000, True), (40_000_000, False)],
)
def test_the_join_tolerance_is_enforced(tmp_path, monkeypatch, offset_ns, pairs):
    """Both sides sit on a 100 ms grid (`gt_stride=2`, `ndt_stride=2`), so the
    NDT-to-nearest-GT distance IS the offset -- on the default 50 ms grid the
    nearest neighbour is never more than 25 ms away, so no offset could ever
    exceed the tolerance and such a fixture would pin nothing.

    10 ms pairs and scores; 40 ms is past `quality.JOIN_TOL_NS` (25 ms), so no
    pair survives and the gate refuses. A tolerance dropped or widened flips
    exactly one of these two, which is the point of running both.
    """
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        ndt_expected_hz=10.0,  # both series are decimated to 10 Hz here
        gt_stride=2,
        ndt_stride=2,
        ndt_stamp_offset_ns=offset_ns,
    )
    if pairs:
        assert build_quality(run_dir, cells_yaml=cells)["gate_pass"] is True
    else:
        with pytest.raises(GateRefused, match="stamp pairs"):
            build_quality(run_dir, cells_yaml=cells)


# --- window resolution ---------------------------------------------------


def test_closed_loop_uses_the_spatial_window_not_the_static_one(tmp_path, monkeypatch):
    """The ego is PARKED at station 0 for the first 60 s, so the two candidate
    windows disagree by 49 s: the registered spatial window opens only once the
    ego passes station 20 m (69.0 s here), while a static window would open at
    t0 + 20 s. A test whose fixture starts moving immediately cannot tell the
    two apart, which is exactly how a "uses the spatial window" test passes
    under a static one."""
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        hold_n=1200,  # 60 s parked
    )
    lo, hi = build_quality(run_dir, cells_yaml=cells)["window_sim_ns"]
    # Parked for 1200 samples, then 1800 samples covering 200 m: station 20 m
    # is reached 180 samples later, i.e. at sample 1380 = 69.0 s.
    assert lo == pytest.approx(69_000_000_000, abs=DT_NS)
    assert lo > 20_000_000_000 + 40_000_000_000, "a static window would open at t0 + 20 s"
    assert hi == (N_SAMPLES - 1) * DT_NS


def test_the_spatial_window_applies_the_warm_up_discard(tmp_path, monkeypatch):
    """The 20 s discard on the SPATIAL branch, pinned on its own.

    The default fixture crawls 200 m in 150 s, so it clears station 20 m at
    15.0 s -- BEFORE the warm-up boundary at 20.0 s, which is what then sets
    the window's lower bound. Drop `warmup_ns` on that branch and the window
    opens at 15.0 s instead: 5 s earlier here, and in a real run (where the ego
    clears 20 m in ~4 s) inside the engage transient, silently shifting every
    M5 number. The parked-ego fixture above cannot see this, because there the
    station bound dominates the warm-up bound.
    """
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    lo, hi = build_quality(run_dir, cells_yaml=cells)["window_sim_ns"]
    assert lo == 20_000_000_000, "the warm-up discard sets this bound, not station 20 m"
    assert hi == (N_SAMPLES - 1) * DT_NS


@pytest.mark.parametrize("arm", ["paced", "unpaced", "ablation"])
def test_sweep_arms_take_the_static_window_branch(tmp_path, monkeypatch, arm):
    """README registers the spatial window for the `closed-loop` arm and the
    clock-based one for EVERY other arm -- `static`, `paced`, `unpaced`,
    `ablation`. The sweep arms are the only ones that mechanically consume
    quality.json (`sweep_verdict`), and no test used them, so widening the
    branch test to `arm != "static"` left the suite green.

    The parked-ego fixture separates the two branches by 49 s, so this asserts
    the clock-derived bound (20.0 s) and would fail on the spatial one (69.0 s).
    Failure scenario the widening produces: at a heavy sweep class the ego never
    clears station 20 m, the gate refuses, and `sweep_verdict` dies
    FileNotFoundError -- blaming a missing gate instead of the load under test.
    """
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        arm=arm,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        hold_n=1200,
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["arm"] == arm
    assert doc["window_sim_ns"][0] == pytest.approx(20_000_000_000, abs=1_000_000)
    # The goal criteria DO apply on the sweep arms: only the manifest's own
    # `static` says the ego was parked. run.sh drives a sweep arm under either
    # window_arm, so exempting them would silently drop the criterion.
    assert doc["goal_window_sim_ns"] is not None
    assert doc["goal_closest_approach_m"] is not None


def test_static_arm_window_is_the_clock_window_converted_into_sim(tmp_path, monkeypatch):
    """The static branch takes its bounds from clock.csv's WALL arrivals and
    converts them through the run's own affine fit. This run advances sim at
    half wall time (rtf 0.5), so the registered inverse
    `(wall - intercept) / slope` is observable in the lower bound: the 20 s
    WALL warm-up is 10 s of SIM. An implementation that skipped the conversion
    would put `lo` at a wall epoch (~1.7e18); one that subtracted the origin
    but forgot the slope would put it at exactly 20 s."""
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        arm="static",
        ladder_branch="relative",
        ndt_bias=0.05,
        rtf=0.5,
    )
    lo, hi = build_quality(run_dir, cells_yaml=cells)["window_sim_ns"]
    assert lo == pytest.approx(10_000_000_000, abs=1_000_000)
    assert lo < 20_000_000_000
    assert hi == pytest.approx((N_SAMPLES - 1) * DT_NS, abs=1_000_000)


def test_static_arm_on_an_unfittable_clock_is_refused(tmp_path, monkeypatch):
    """Fewer than 2 clock.csv rows is README's UNFITTABLE branch: no sim
    domain exists, so there is no sim window to convert to and none is
    invented."""
    run_dir, cells = _run(tmp_path, monkeypatch, arm="static", ladder_branch="relative")
    (run_dir / "clock.csv").write_text("clock_ns,arrival_system_ns\n0,%d\n" % BASE_WALL)
    with pytest.raises(GateRefused, match="UNFITTABLE"):
        build_quality(run_dir, cells_yaml=cells)


def test_a_missing_route_file_is_refused(tmp_path, monkeypatch):
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    (tmp_path / "routes" / f"{MAP}.yaml").unlink()
    with pytest.raises(GateRefused, match="no route file"):
        build_quality(run_dir, cells_yaml=cells)


def test_a_route_file_missing_its_stations_is_refused(tmp_path, monkeypatch):
    """A route file that parses but lacks a field the window needs must name
    the file and the field, not raise a bare KeyError out of an unattended
    step."""
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    route = tmp_path / "routes" / f"{MAP}.yaml"
    doc = yaml.safe_load(route.read_text())
    del doc["stations"]
    route.write_text(yaml.safe_dump(doc))
    with pytest.raises(GateRefused, match="missing a required field"):
        build_quality(run_dir, cells_yaml=cells)


def test_odometry_without_the_registered_topic_is_refused(tmp_path, monkeypatch):
    """odometry.csv carries whatever the observer's `odometry`-kind lines
    registered; without `/localization/kinematic_state` there is no ego track,
    so neither window nor the goal/lateral metrics exist."""
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    rows = (run_dir / "odometry.csv").read_text().replace(ODOM_TOPIC, "/some/other/odom")
    (run_dir / "odometry.csv").write_text(rows)
    with pytest.raises(GateRefused, match="odometry.csv"):
        build_quality(run_dir, cells_yaml=cells)


def test_an_empty_spatial_window_is_refused(tmp_path, monkeypatch):
    """Station bounds the ego never reaches must abort by name, not score
    whatever rows happened to be in the file."""
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        route_kwargs={"start_m": 900.0, "end_m": 1000.0},
    )
    with pytest.raises(GateRefused, match="spatial window"):
        build_quality(run_dir, cells_yaml=cells)


# --- provenance, schema, and the consumer contract -----------------------


def test_excluded_runs_are_not_scored(tmp_path, monkeypatch):
    """run.sh runs this step before the exclusion step, so this refusal is
    what stops the ordering ever being inverted silently -- excluded data must
    not carry an M5 verdict."""
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    _write_manifest(run_dir, excluded=True, reason="stall:clock")
    with pytest.raises(GateRefused, match="marked excluded"):
        build_quality(run_dir, cells_yaml=cells)


def test_an_unreadable_manifest_is_refused_by_name(tmp_path, monkeypatch):
    """`load_manifest` splats the document into the dataclass, so a manifest
    whose shape has drifted raises a TypeError from inside it -- which must
    arrive as a named refusal, not as a traceback out of an unattended step."""
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    (run_dir / "manifest.json").write_text(json.dumps({"cell": "A", "unexpected": 1}))
    with pytest.raises(GateRefused, match="run manifest"):
        build_quality(run_dir, cells_yaml=cells)


def test_schema_is_exactly_the_registered_keys(tmp_path, monkeypatch):
    run_dir, cells = _run(
        tmp_path, monkeypatch, arm="static", ladder_branch="relative", ndt_bias=0.05
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    stat_keys = [f.name for f in dataclasses.fields(QualityStats)]
    assert list(doc) == stat_keys + [
        "arm",
        "window_sim_ns",
        "goal_window_sim_ns",
        "ladder_branch",
        "expected_ndt_hz",
    ]
    assert doc["arm"] == "static"
    assert isinstance(doc["window_sim_ns"], list) and len(doc["window_sim_ns"]) == 2


def test_static_arm_records_no_goal_metrics(tmp_path, monkeypatch):
    """2026-07-29 owner ruling: the two goal criteria do not apply to the
    static arm at all. Both fields are null, `goal_window_sim_ns` is null, no
    goal reason is recorded, and the gate can still PASS on the NDT-rate and
    ladder criteria alone. Before the ruling this arm's gate was structurally
    unpassable -- a parked ego can never be within 1.0 m of the goal."""
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        arm="static",
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["goal_window_sim_ns"] is None
    assert doc["goal_closest_approach_m"] is None
    assert doc["goal_terminal_distance_m"] is None
    assert doc["gate_pass"] is True, doc["reasons"]
    assert not any("goal" in r for r in doc["reasons"])


def test_the_goal_window_is_not_station_trimmed(tmp_path, monkeypatch):
    """The two windows are resolved separately, and this fixture forces them
    apart: `end_m` stops the SCORING window at station 100 m of a 200 m track,
    while the goal sits at the route's end.

    Scored on the station window (the pre-ruling behaviour) closest approach is
    ~100 m and the gate FAILS; scored on the warm-up-trimmed armed span it is
    ~0 m and the gate passes. The recorded windows differ, and the goal window
    runs to the last odometry sample.
    """
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        route_kwargs={"end_m": 100.0},
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["window_sim_ns"][1] < doc["goal_window_sim_ns"][1]
    assert doc["goal_window_sim_ns"] == [20_000_000_000, (N_SAMPLES - 1) * DT_NS]
    assert doc["goal_closest_approach_m"] == pytest.approx(0.0, abs=1e-6)
    assert doc["goal_terminal_distance_m"] == pytest.approx(0.0, abs=1e-6)
    assert doc["gate_pass"] is True, doc["reasons"]


def test_the_goal_window_applies_the_warm_up_discard(tmp_path, monkeypatch):
    """Warm-up-trimmed, not raw: the goal window opens 20 s after the ego
    odometry's first stamp, so the engage transient is out of both windows."""
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["goal_window_sim_ns"][0] == 20_000_000_000


def test_a_goal_never_approached_still_fails_the_gate(tmp_path, monkeypatch):
    """The ruling widens the goal window; it does not weaken the criterion. A
    goal 500 m off the track is still a failure, over the wider window."""
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        route_kwargs={"goal": (0.0, 500.0)},
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["gate_pass"] is False
    assert len(doc["reasons"]) == 1
    assert "goal closest approach" in doc["reasons"][0]


@pytest.mark.parametrize(("offset_m", "passes"), [(0.8, True), (1.2, False)])
def test_the_goal_threshold_is_pinned_at_one_metre(tmp_path, monkeypatch, offset_m, passes):
    """The registered 1.0 m goal threshold, bracketed.

    The 500 m fixture above pins only that the criterion exists at all: it
    still fails under a threshold relaxed to 100 m. Straddling 1.0 m from both
    sides is what pins the NUMBER, so neither a relaxation nor a tightening
    passes unnoticed. The goal sits `offset_m` beside the track's end point, so
    the closest approach IS that offset.
    """
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        route_kwargs={"goal": (ROUTE_LEN_M, offset_m)},
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["goal_closest_approach_m"] == pytest.approx(offset_m, abs=1e-3)
    assert doc["gate_pass"] is passes, doc["reasons"]


@pytest.mark.parametrize(("expected_hz", "passes"), [(21.0, True), (23.0, False)])
def test_the_ndt_rate_threshold_is_pinned_at_ninety_percent(
    tmp_path, monkeypatch, expected_hz, passes
):
    """The registered "NDT rate >= 90% of expected" threshold, bracketed.

    The 20 Hz series is held fixed and the registered expectation moved
    instead, so the ratio lands at 0.952 (pass) and 0.870 (fail) -- either side
    of 0.9, with no other criterion changed. `test_ndt_rate_gate_fires`'s 0.25
    ratio pins only that the criterion exists; it survives a threshold relaxed
    to 0.1.
    """
    run_dir, cells = _run(
        tmp_path,
        monkeypatch,
        ladder_branch="absolute",
        abs_pose_gate_m=0.5,
        ndt_bias=0.05,
        ndt_expected_hz=expected_hz,
    )
    doc = build_quality(run_dir, cells_yaml=cells)
    assert doc["gate_pass"] is passes, (doc["ndt_rate_ratio"], doc["reasons"])


def test_written_file_round_trips_through_sweep_verdicts_reader(tmp_path, monkeypatch):
    """The consumer contract is fixed: sweep_verdict._quality_ok reads
    `gate_pass` out of this file, and a missing file is a hard error on any arm
    that closes the loop."""
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    assert not (run_dir / "quality.json").exists()
    with pytest.raises(FileNotFoundError, match="quality"):
        sweep_verdict._quality_ok(run_dir, "paced")

    path = _wq(run_dir, cells_yaml=cells)
    assert path == run_dir / "quality.json"
    assert sweep_verdict._quality_ok(run_dir, "paced") == (True, None)
    # ... and a failing verdict round-trips as a failure, not as a pass.
    doc = json.loads(path.read_text())
    doc["gate_pass"] = False
    path.write_text(json.dumps(doc))
    assert sweep_verdict._quality_ok(run_dir, "paced") == (False, None)


def test_main_writes_the_file_and_exits_zero(tmp_path, monkeypatch, capsys):
    run_dir, cells = _run(
        tmp_path, monkeypatch, ladder_branch="absolute", abs_pose_gate_m=0.5, ndt_bias=0.05
    )
    assert main(["--run-dir", str(run_dir), "--cells-yaml", cells]) == 0
    assert (run_dir / "quality.json").is_file()
    assert "gate_pass=True" in capsys.readouterr().out


def test_main_names_the_refusal_on_stderr(tmp_path, monkeypatch, capsys):
    """The status is asserted as the LITERAL 2, not as
    `write_quality.EXIT_REFUSED`. Comparing against the constant is
    tautological: setting `EXIT_REFUSED = 0` satisfies it, and `run.sh`'s
    `if ! (...)` guard then never fires, so a refusal becomes invisible in the
    live log -- the one thing that step's own comment calls load-bearing."""
    run_dir, cells = _run(tmp_path, monkeypatch, ndt_bias=0.05)  # ladder unset
    assert main(["--run-dir", str(run_dir), "--cells-yaml", cells]) == 2
    assert write_quality.EXIT_REFUSED == 2
    err = capsys.readouterr().err
    assert "QUALITY GATE FAIL" in err
    assert "ladder_branch is null" in err


def test_the_cli_exits_non_zero_so_run_sh_can_see_a_refusal(tmp_path, monkeypatch):
    """The PROCESS-level contract `run.sh` step 13 depends on, exercised as a
    real subprocess rather than through `main`'s return value: a refusal must
    leave a non-zero exit status, a named reason on stderr and no file."""
    run_dir, cells = _run(tmp_path, monkeypatch, ndt_bias=0.05)  # ladder unset
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.scripts.write_quality",
            "--run-dir",
            str(run_dir),
            "--cells-yaml",
            cells,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2, proc.stderr
    assert "QUALITY GATE FAIL" in proc.stderr
    assert not (run_dir / "quality.json").exists()


def test_run_sh_warns_when_the_gate_refuses():
    """The other half of the same contract, on the `run.sh` side.

    Asserted against the script's text because executing step 13 in isolation
    needs a whole run directory produced by steps 1-12; what matters is the
    structure, and the structure is what a well-meaning edit breaks. Pinned
    here: the gate is step 13, it sits between finalize_rtf (12) and the
    exclusion step (14) -- the ordering the ruling and the excluded-run refusal
    both depend on -- its invocation is guarded by `if !` so a non-zero exit is
    seen at all, and a WARN naming the run directory follows inside the guard.
    """
    text = (REPO_ROOT / "benchmarks" / "run.sh").read_text()
    step12 = text.index('step 12 "finalize_rtf')
    step13 = text.index('step 13 "M5 gate')
    step14 = text.index('step 14 "exclusions')
    assert step12 < step13 < step14
    block = text[step13:step14]
    assert 'if ! (cd "$REPO" && python3 -m benchmarks.scripts.write_quality' in block
    assert 'echo "WARN: the M5 gate did not score $run_dir' in block


# --- the committed registry ----------------------------------------------


def test_committed_cells_yaml_ladder_slots_match_the_selected_branches():
    """R3.3's registration, now partly FILLED -- pinned either way.

    Task 11's live G1 re-gate (2026-07-29) walked the ladder to rung 2 and
    selected the ABSOLUTE branch for the two extension Town10 cells, which
    localize against the regenerated bundle (pins.yaml town10_pcd_regen):
    max NDT error 0.089 m against the 0.5 m gate. The rigid rungs missed it
    (0.824 m on `dy = -0.475`, 0.570 m on the `dy = -0.607` refit). See
    benchmarks/README.md's 2026-07-29 ladder amendment for the full record.

    The B family's three TOWN10 cells joined that set on 2026-07-30, when Task
    13 wired their bundle: benchmarks/cells/tier4_autoware.sh resolves the map
    through scripts/e2e/map_defaults.sh -- the same table cells A/A-hf read --
    so they localize against the SAME rung-2 bundle, and the branch is a
    property of the bundle (README, "M5 definitions"), not of the approach.
    Task 11 could not register them because the branch differs per Town10
    bundle (regen -> absolute, rigid/unshifted -> relative) and nothing had yet
    chosen one.

    Cell C joined on 2026-07-30 from ITS OWN live G1 re-gate on the
    Nishi-Shinjuku bundle: max NDT error 0.062 m against the same 0.5 m gate,
    bias 21 mm, so branch (a) applies on the first rung and no ladder had to be
    walked (benchmarks/evidence/g1-nishi-bundle/, README's 2026-07-30
    amendment).

    Cell D runs the tier4 launcher against that SAME bundle and still stays
    UNSET -- deliberately, and this assertion is the pinned half of that
    decision. D was STRUCK by the 2026-07-30 core-duel scope cut, so it will
    never produce a run to gate, and whether the tier4 tree can cook this map at
    all was never tested; mirroring cell C's values across (what Task 13
    legitimately did for cell B, which runs) would make a never-run, never-shown
    cell read as a gated one. `null` keeps the M5 gate refusing it. So D is NOT
    a stale slot to be "fixed" later by filling it: a change that fills it has
    to argue against that reasoning, which is what this assertion forces.

    Cells E and E0 joined on 2026-08-01 (Task 8) on the OTHER branch, and they
    are what makes this test's two-set shape necessary rather than a
    selected-or-not flag. Their launcher (`cells/python-bridge.sh`) pins the
    UNSHIFTED `~/autoware_map/town10` -- content-verified as
    `autoware_contents.town10_pcd_sha256`, the digest `pins.yaml`'s rigid
    variants describe themselves as correcting "+0.475 m cross-track" away from
    -- so README's branch (b) applies and `abs_pose_gate_m` must stay null. That
    is a SELECTION, not an absent one: gating them at 0.5 m against that bundle
    would fail them for map registration under a reason a reader would attribute
    to the bridge, which cells.yaml's header block predicted by name. Their
    branch was settled from the bundle's identity, not from a scored run -- no
    E-family run had been scored when it was registered.

    E-opt stays UNSET even though it runs cell E's image and would inherit E's
    values: it was STRUCK by the scope cut, and its only arm is `closed-loop`,
    which Task 4 showed this family cannot reach (cell E armed to AUTONOMOUS and
    the gated control command never flowed). Same argument as cell D.

    The CAL cells have no localization stack. Every cell in neither set must stay
    UNSET so the M5 gate keeps refusing it rather than gating on a guessed
    branch -- the property R3.3 added this test for.

    Cell B-cyc joined `selected_absolute` on 2026-08-03 (Task 4, P4
    transport-sweep plan) alongside B, B-hf and B45: it runs the identical
    tier4-native launcher (cells/tier4_autoware.sh) against the identical
    rung-2 bundle as cell B, differing only in DDS transport (row-11
    cyclonedds rather than B's fastrtps/udp_only), and the docstring above is
    explicit that the ladder branch is a property of the BUNDLE, not the
    approach or the transport -- so B-cyc inherits B's `absolute` branch and
    0.5 m gate for the same reason B itself is in this set, not by mirroring
    a value nothing measured. config/cells.yaml's B-cyc entry mirrors B's
    metrics block field for field, this assertion included.
    """
    selected_absolute = {"A", "A-hf", "B", "B-hf", "B45", "C", "B-cyc"}
    selected_relative = {"E", "E0"}
    doc = load_cells_doc()
    for cell in (c["id"] for c in doc["cells"]):
        metrics = metrics_for(doc, cell)
        if cell in selected_absolute:
            assert metrics["ladder_branch"] == "absolute", cell
            # Non-null iff absolute, and it is the README's registered
            # threshold -- not any float, which would let a relaxed gate in.
            assert metrics["abs_pose_gate_m"] == pytest.approx(0.5), cell
        elif cell in selected_relative:
            assert metrics["ladder_branch"] == "relative", cell
            # Null iff relative, and `write_quality.resolve_ladder` REFUSES a
            # relative branch carrying a threshold rather than ignoring it.
            assert metrics["abs_pose_gate_m"] is None, cell
        else:
            assert metrics["ladder_branch"] is None, cell
            assert metrics["abs_pose_gate_m"] is None, cell


def test_committed_route_stations_stop_short_of_the_goal():
    """The arithmetic the 2026-07-29 owner ruling rests on, pinned on the
    COMMITTED route files.

    Both routes set `stations.end_m` 20 m short of their own length while their
    goal sits at the route's END, so the station-trimmed window's last possible
    sample is ~20 m from the goal -- against the gate's registered
    `goal_closest_approach < 1.0 m`. That is why the ruling scores the two goal
    metrics over the warm-up-trimmed armed span instead, and why it did NOT
    move `end_m`: README registers the SAME window for all five
    margin-carrying duel metrics, so extending it would move the headline
    equivalence measurement itself.

    If a future change alters either route's stations or its goal, this test
    fails and the ruling has to be revisited rather than silently invalidated.
    """
    from benchmarks.analysis.window import _cum_arclen, project_station_m

    # Town10's 19.850 m replaced 19.772 m when Task 11 RE-PICKED that route
    # (2026-07-29): the original 438.9 m route proved infeasible BEFORE any
    # measurement, so its goal moved to station 258.9 m. This test firing is
    # precisely the "revisit the ruling rather than silently invalidate it"
    # behaviour its docstring asks for -- and the ruling SURVIVES unchanged:
    # the gap is still ~20 m, so a station-trimmed goal metric still could not
    # clear the 1.0 m criterion, which is the ruling's whole basis. Only the
    # constant moved.
    for map_name, expected_gap_m in (("Town10HD_Opt", 19.850), ("NishishinjukuMap", 20.039)):
        doc = yaml.safe_load((write_quality.ROUTES_DIR / f"{map_name}.yaml").read_text())
        poly = np.asarray(doc["polyline"], dtype=np.float64)
        goal = np.asarray([doc["goal"]["x"], doc["goal"]["y"]], dtype=np.float64)
        cum = _cum_arclen(poly)
        end_m = float(doc["stations"]["end_m"])
        # The goal is the route's own end point, so its station is the length.
        assert project_station_m(poly, goal[None, :])[0] == pytest.approx(cum[-1], abs=1e-6)
        at_end = np.array([np.interp(end_m, cum, poly[:, 0]), np.interp(end_m, cum, poly[:, 1])])
        gap = float(np.linalg.norm(at_end - goal))
        assert gap == pytest.approx(expected_gap_m, abs=0.01), f"{map_name}: {gap:.3f} m"
        assert gap > 1.0, f"{map_name}: a station-trimmed goal metric cannot clear 1.0 m"


def test_the_ruling_makes_the_committed_town10_route_gateable(tmp_path, monkeypatch):
    """End to end on the REAL `config/routes/Town10HD_Opt.yaml`: an ego that
    drives the committed route to its goal now PASSES the gate.

    This is the ruling's whole point, on the real file rather than a synthetic
    straight line. The recorded windows differ exactly as the arithmetic above
    says they must -- the scoring window closes ~19.8 m short of the goal while
    the goal window runs to the last odometry sample -- so scoring the goal
    metrics on the scoring window would report ~19.8 m and fail.
    """
    monkeypatch.setattr(write_quality, "ROUTES_DIR", REAL_ROUTES_DIR)
    doc = yaml.safe_load((REAL_ROUTES_DIR / "Town10HD_Opt.yaml").read_text())
    poly = np.asarray(doc["polyline"], dtype=np.float64)
    goal = np.asarray([doc["goal"]["x"], doc["goal"]["y"]], dtype=np.float64)

    from benchmarks.analysis.window import _cum_arclen

    cum = _cum_arclen(poly)
    t = np.arange(N_SAMPLES, dtype=np.int64) * DT_NS
    station = np.linspace(0.0, float(cum[-1]), N_SAMPLES)
    xy = np.column_stack([np.interp(station, cum, poly[:, 0]), np.interp(station, cum, poly[:, 1])])

    run_dir = tmp_path / "run-001"
    run_dir.mkdir()
    _write_manifest(run_dir, map_name="Town10HD_Opt")
    _write_gt_csv(run_dir / "gt.csv", t, xy)
    _write_xy_csv(run_dir / "odometry.csv", ODOM_TOPIC, t, xy)
    _write_xy_csv(run_dir / "pose.csv", NDT_TOPIC, t, xy + [0.0, 0.05])
    _write_clock_csv(run_dir / "clock.csv", t)
    cells = _cells_yaml(tmp_path, ladder_branch="absolute", abs_pose_gate_m=0.5)

    q = build_quality(run_dir, cells_yaml=cells)
    assert q["gate_pass"] is True, q["reasons"]
    assert q["goal_closest_approach_m"] < 1.0
    assert q["window_sim_ns"][1] < q["goal_window_sim_ns"][1]
    # The ego at the scoring window's end is ~19.8 m from the goal: the number
    # the pre-ruling definition would have recorded and failed on.
    at_window_end = xy[np.searchsorted(t, q["window_sim_ns"][1])]
    assert float(np.linalg.norm(at_window_end - goal)) == pytest.approx(19.8, abs=0.5)
