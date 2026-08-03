"""cell_info: the top-of-pipeline typo guard for cell and class ids."""

from __future__ import annotations

import json
import math
import re

import pytest
import yaml

from benchmarks.scripts import cell_info

CONFIG_DIR = cell_info.CELLS_YAML.parent
ALL_CELL_IDS = [str(c["id"]) for c in yaml.safe_load(cell_info.CELLS_YAML.read_text())["cells"]]

# The bridge's sensor-config patch, which carries BOTH python-bridge rigs: the
# as-shipped `frequency_hz` on its `-` side (cell E0's) and the harmonized one
# on its `+` side (cells E / E-opt's). Read here so the rate DERIVATION cell E's
# comment records is falsifiable rather than merely asserted.
BRIDGE_SENSOR_PATCH = (
    cell_info.CELLS_YAML.parents[1]
    / "patches"
    / "python-bridge"
    / "0002-sensor-config-harmonized.patch"
)
_FREQ_RE = re.compile(r"^([-+])\s*frequency_hz:\s*([0-9.]+)\s*$", re.MULTILINE)


def _observer_topics(cell: str) -> list[str]:
    """The topic names registered in config/observer_topics/<cell>.yaml.

    Each entry is "<topic>|<type>|<kind>" (benchmarks/observer/src/
    bench_observer.cpp); only the topic half is compared here.
    """
    doc = yaml.safe_load((CONFIG_DIR / "observer_topics" / f"{cell}.yaml").read_text())
    specs = doc["/**"]["ros__parameters"]["topics"] or []
    return [str(spec).split("|", 1)[0] for spec in specs]


def _process_labels(cell: str) -> list[str]:
    doc = yaml.safe_load((CONFIG_DIR / "processes" / f"{cell}.yaml").read_text())
    return [str(entry["label"]) for entry in doc["processes"]]


@pytest.fixture
def doc() -> dict:
    return cell_info.load_cells_doc()


def test_known_cell_round_trip(doc, capsys):
    assert cell_info.main(["A"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["id"] == "A"
    assert printed["approach"] == "extension"
    assert printed["map"] == "Town10HD_Opt"
    assert printed["arms"] == ["static", "closed-loop"]
    # sweep_arms rides along so run.sh can validate --unpaced without a
    # second read of cells.yaml.
    assert "unpaced" in printed["sweep_arms"]
    assert printed == cell_info.merge(doc, "A")


def test_unknown_cell_exits_2(capsys):
    assert cell_info.main(["Q"]) == cell_info.EXIT_UNKNOWN_ID
    err = capsys.readouterr().err
    assert "unknown cell 'Q'" in err
    # The message must name the legitimate ids, or the operator's next move
    # is to go read cells.yaml by hand.
    assert "CAL-rmw" in err


def test_class_merge_injects_points_per_second(doc):
    merged = cell_info.merge(doc, "A", "32ch")
    assert merged["class_id"] == "32ch"
    assert merged["points_per_second"] == 1200000
    assert merged["channels"] == 32
    # Lookup metadata is consumed, not leaked into the workload description.
    assert "applies_to" not in merged
    # The cell's own fields survive the merge.
    assert merged["approach"] == "extension"


def test_camera_class_merges_too(doc):
    merged = cell_info.merge(doc, "B", "cam6")
    assert merged["class_id"] == "cam6"
    assert merged["cameras"] == 6
    assert merged["fps"] == 20


def test_unknown_class_exits_2(capsys):
    assert cell_info.main(["A", "--class", "1024ch"]) == cell_info.EXIT_UNKNOWN_ID
    assert "unknown class '1024ch'" in capsys.readouterr().err


def test_class_not_registered_for_cell_is_an_error(doc):
    # 32ch applies_to [A, B, E]; C is a registered cell but not a sweep cell.
    with pytest.raises(cell_info.UnknownIdError, match="not registered for cell 'C'"):
        cell_info.merge(doc, "C", "32ch")


def test_no_class_leaves_workload_keys_absent(doc):
    merged = cell_info.merge(doc, "A")
    assert "class_id" not in merged
    assert "points_per_second" not in merged


def test_calibration_cell_has_no_sim_clock(doc):
    """Regression: CAL-rmw runs no simulator, so nothing publishes /clock and
    clock.csv stays header-only. run.sh reads this one derived field in three
    places (start the watchdog / act on a stall marker / use the sim-wall clock
    fit). While it was inferred per call site instead, step 7 started the
    watchdog anyway, the watchdog reported "no /clock rows at all" after its
    grace period, and EVERY CAL-rmw run was excluded as `stall:clock` --
    quietly, under a legitimate-looking pre-registered reason."""
    assert cell_info.merge(doc, "CAL-rmw")["has_sim_clock"] is False


@pytest.mark.parametrize("cell", ["A", "B", "C", "E0", "CAL-seam"])
def test_every_simulator_cell_has_a_sim_clock(doc, cell):
    """The converse, so the guard cannot be widened into "skip the watchdog for
    calibration cells". CAL-seam is the discriminating case: a calibration cell
    that DOES run a simulator (`carla: 0.10-fork`), so the flag follows the
    simulator, not the approach."""
    assert cell_info.merge(doc, cell)["has_sim_clock"] is True


# ---------------------------------------------------------------------------
# metrics_for: the per-cell metric bindings (benchmarks/README.md, "Primary-
# duel metric definitions"). A cell missing a binding is a registration gap
# that would otherwise surface as a KeyError mid-campaign, or -- worse -- as a
# tool's own hardcoded default matching zero rows and reading as real data.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cell", ALL_CELL_IDS)
def test_every_registered_cell_has_every_metric_binding(doc, cell):
    metrics = cell_info.metrics_for(doc, cell)
    assert set(metrics) == set(cell_info.METRIC_KEYS)


@pytest.mark.parametrize("cell", ALL_CELL_IDS)
def test_metric_topics_are_topics_the_observer_actually_records(doc, cell):
    """A bound topic that bench_observer never subscribes to yields zero rows,
    which reads downstream as "this transport delivered nothing" rather than as
    a configuration error -- the exact failure mode an unregistered topic
    binding would produce. `null` bindings are skipped: they are the
    registered "not chosen yet" state.

    `control_published_time_topic` joined this tuple 2026-08-03 (Task 5's fix
    round 1): `_observer_topics()` parses every `<topic>|<type>|<kind>` line
    generically regardless of `kind`, so a `published_time` row is exactly as
    checkable here as a `generic`/`pose`/`odometry` one, and the same
    almost-right-line failure this test guards against for the other three
    keys applies to this one -- a drift between cells.yaml's binding and the
    topic actually subscribed in observer_topics/<cell>.yaml would otherwise
    surface only as a silently empty published_time.csv, not a failing test."""
    metrics = cell_info.metrics_for(doc, cell)
    registered = _observer_topics(cell)
    for key in ("lidar_topic", "ndt_topic", "control_topic", "control_published_time_topic"):
        if metrics[key] is not None:
            assert metrics[key] in registered, f"{cell}: {key} not in observer_topics"


@pytest.mark.parametrize("cell", ALL_CELL_IDS)
def test_cpu_process_label_is_a_label_the_sampler_writes(doc, cell):
    """resources.csv's `process` column is the process-map entry's `label`
    verbatim (sampler/sample_resources.py), so carla_process_cpu_pct's binding
    must be one of them. A label that matches nothing does not raise -- it
    silently reads as "the simulator used no CPU"."""
    label = cell_info.metrics_for(doc, cell)["cpu_process_label"]
    if label is not None:
        assert label in _process_labels(cell)


@pytest.mark.parametrize("cell", ALL_CELL_IDS)
def test_registered_rates_are_positive_or_explicitly_unregistered(doc, cell):
    """Rates are either a positive number or `null` (not pre-registered yet).
    A zero or negative rate would divide achieved_rate_ratio (or the M5 gate's
    NDT rate ratio) by zero or flip its sign rather than failing."""
    metrics = cell_info.metrics_for(doc, cell)
    for key in ("tick_hz", "lidar_expected_hz", "ndt_expected_hz"):
        assert metrics[key] is None or metrics[key] > 0


@pytest.mark.parametrize("cell", ["A-hf", "B-hf"])
@pytest.mark.parametrize("key", ["tick_hz", "lidar_expected_hz", "ndt_expected_hz"])
def test_high_frequency_cells_register_no_rate_task_26_has_not_applied(doc, cell, key):
    """Task 26 Step 2 configures both high-frequency cells end to end -- the
    world tick AND the sensor ticks, set explicitly and separately -- and it has
    not run (it is also owner-strikable, so it may never). No committed launcher
    applies any of it: cells/extension.sh passes no fixed-delta, and Task 13's
    cells/tier4_autoware.sh -- which DOES exist, since 2026-07-30 -- applies cell
    B's harmonized 20 Hz tick, not B-hf's intended 100 Hz.

    The sensor rates are the subtle half. An earlier revision registered 20.0
    for A-hf's, reasoning that --fixed-delta moves only the world tick so the
    cell inherits cell A's sensor_tick. Task 26 sets A-hf's LiDAR sensor_tick
    explicitly, to neither cell A's value nor the tick period, so the rate is
    neither inherited nor derivable -- and a wrong lidar_expected_hz feeds
    achieved_rate_ratio (M2) and, through ndt_expected_hz, the M5 gate."""
    assert cell_info.metrics_for(doc, cell)[key] is None


def test_a_partly_unregistered_cell_is_not_an_all_or_nothing_cell(doc):
    """The three rate bindings are independent keys, so "one is null" must not
    read as "this cell has no rates". CAL-rmw is the discriminating case: no
    world tick and no NDT, but a registered publisher rate -- so a tool that
    gated on all-rates-present would skip a cell whose achieved_rate_ratio is
    perfectly computable."""
    metrics = cell_info.metrics_for(doc, "CAL-rmw")
    assert metrics["tick_hz"] is None
    assert metrics["ndt_expected_hz"] is None
    assert metrics["lidar_expected_hz"] == 10.0


@pytest.mark.parametrize("cell", ALL_CELL_IDS)
def test_ndt_rate_is_registered_only_where_the_ndt_topic_is(doc, cell):
    """ndt_expected_hz is the divisor of the M5 gate's "NDT rate >= 90% of
    expected" criterion, so it is meaningful exactly on the cells that have an
    NDT topic at all. A rate registered for a cell with no localization stack
    (the calibration cells) would invite gating a run that cannot be gated."""
    metrics = cell_info.metrics_for(doc, cell)
    if metrics["ndt_topic"] is None:
        assert metrics["ndt_expected_hz"] is None


def _bridge_frequency_hz() -> dict[str, float]:
    """`{"E0": <as-shipped frequency_hz>, "E": <harmonized frequency_hz>}`.

    Both come from the ONE committed patch file, which is what makes them
    checkable: its `-` side is the image cell E0 runs and its `+` side is the
    image cells E / E-opt run, and `cells/python-bridge.sh` refuses to run either
    cell against the other's image. Exactly one of each is required -- a second
    `frequency_hz` hunk (a camera rate, say) would make "the LiDAR's" ambiguous,
    and silently picking the first would then bind a rate off the wrong sensor.
    """
    found = _FREQ_RE.findall(BRIDGE_SENSOR_PATCH.read_text())
    shipped = [v for sign, v in found if sign == "-"]
    patched = [v for sign, v in found if sign == "+"]
    assert len(shipped) == 1 and len(patched) == 1, (
        f"expected exactly one -/+ frequency_hz pair in {BRIDGE_SENSOR_PATCH.name}, "
        f"got {found}: the E-family rate derivation cannot tell which sensor is meant"
    )
    return {"E0": float(shipped[0]), "E": float(patched[0])}


@pytest.mark.parametrize("cell", ["E", "E0"])
def test_bridge_cells_register_the_rate_their_own_config_can_actually_emit(doc, cell):
    """The E-family derivation, made falsifiable (Task 8, 2026-08-01).

    The bridge sets no `sensor_tick`, so its LiDAR fires every world tick, and it
    throttles PUBLICATION on a sim-time threshold (`should_publish`:
    `time_diff >= 1.0 / frequency_hz`) that can only be evaluated on tick
    boundaries. The as-emitted rate is therefore
    `tick_hz / ceil(tick_hz / frequency_hz)` -- NOT `frequency_hz`, which for
    cell E0's shipped 11 is a rate a 20 Hz tick cannot produce.

    Pinned rather than restated in prose because getting it wrong is silent: a
    denominator no configuration can satisfy caps `achieved_rate_ratio` by
    arithmetic alone, and through `ndt_expected_hz` it moves the M5 gate.
    """
    metrics = cell_info.metrics_for(doc, cell)
    tick_hz = metrics["tick_hz"]
    freq_hz = _bridge_frequency_hz()[cell]
    assert metrics["lidar_expected_hz"] == tick_hz / math.ceil(tick_hz / freq_hz)


def test_bcyc_metrics_mirror_cell_b(doc):
    """Cell B-cyc (Task 4, P4 transport-sweep plan) is the SAME tier4-native
    stack as cell B -- same fork, same launcher (cells/tier4_autoware.sh),
    same map/bundle -- registered under a DIFFERENT DDS transport (row-11
    cyclone rather than B's fastrtps/udp_only). Transport is resolved by
    run.sh's per-cell correction and enforced by cells/tier4_autoware.sh's
    registered-transport refusal, neither of which lives in this metrics
    block, so every metric BINDING here (topics, rates, process label,
    ladder branch) must be identical to cell B's, field for field."""
    assert cell_info.metrics_for(doc, "B-cyc") == cell_info.metrics_for(doc, "B")


def test_cell_a_registers_the_control_published_time_topic(doc):
    """REGISTERED 2026-08-03 (Task 5, P4 transport-sweep plan), closing the
    gap Tasks 13/20 left open. observer_topics/A.yaml has carried this row
    since 2026-07-30 (Task 15b's live discovery on cell A's own stack, commit
    2453984); only cells.yaml's binding was missing, which left
    control_staleness_ms UNAVAILABLE for the whole P3 duel
    (docs/evaluation/p3-baseline.md Sec.1). Same value as cell B's -- the
    same Autoware graph family (vehicle_cmd_gate's PublishedTimePublisher on
    the gated /control/command/control_cmd) -- not because the two cells
    were merged.

    NOT redundant with test_metric_topics_are_topics_the_observer_actually_
    records's ALL_CELL_IDS parametrization (this file, above): that test
    checks MEMBERSHIP only -- that whatever cells.yaml binds is also a
    topic observer_topics/<cell>.yaml subscribes to -- so a binding pointed
    at the WRONG (but still observed) PublishedTime topic would pass it
    silently. This test pins the exact expected VALUE, which membership
    alone cannot catch."""
    assert (
        cell_info.metrics_for(doc, "A")["control_published_time_topic"]
        == "/control/command/control_cmd/debug/published_time"
    )


def test_the_two_bridge_cells_do_not_share_a_rate(doc):
    """E is PATCHED to 20 Hz on /pointcloud_raw_ex; E0 is the AS-SHIPPED image on
    /pointcloud_before_sync. Copying either cell's rate onto the other is the
    mistake this asserts against -- it would read as a measurement of the rig the
    cell does not run, and cells.yaml's own E0 comment names it."""
    e = cell_info.metrics_for(doc, "E")
    e0 = cell_info.metrics_for(doc, "E0")
    assert e["lidar_expected_hz"] != e0["lidar_expected_hz"]
    assert e["lidar_topic"] != e0["lidar_topic"]


@pytest.mark.parametrize("cell", ["E", "E0"])
def test_bridge_cells_take_the_relative_ladder_branch(doc, cell):
    """Both mount the UNSHIFTED `~/autoware_map/town10`
    (`cells/python-bridge.sh`'s `MAP_BUNDLE_HOST`), which carries the +0.475 m
    cross-track offset `pins.yaml`'s rigid variants exist to correct -- so
    README's branch (b) applies. Gating them at 0.5 m against that bundle would
    fail them for map registration under a reason a reader would attribute to the
    bridge, which is the outcome cells.yaml's header block predicted by name."""
    metrics = cell_info.metrics_for(doc, cell)
    assert metrics["ladder_branch"] == "relative"
    assert metrics["abs_pose_gate_m"] is None


@pytest.mark.parametrize("cell", ALL_CELL_IDS)
def test_every_ladder_registration_is_one_of_the_three_valid_states(doc, cell):
    """`ladder_branch` and `abs_pose_gate_m` are ONE binding in two fields, and
    cells.yaml's header registers exactly three legal combinations. Anything else
    -- `absolute` with no threshold, `relative` carrying one, an unrecognised
    branch name -- is an inconsistent registration that `write_quality` refuses
    at run time, i.e. only after a cell has been booted and a window recorded.
    Asserting it over the REGISTRY catches it before that costs a live run."""
    metrics = cell_info.metrics_for(doc, cell)
    branch, gate = metrics["ladder_branch"], metrics["abs_pose_gate_m"]
    if branch is None:
        assert gate is None, f"{cell}: no branch selected, so no threshold may be registered"
    elif branch == "absolute":
        assert gate is not None and gate > 0, f"{cell}: absolute branch needs its threshold"
    elif branch == "relative":
        assert gate is None, f"{cell}: the relative branch applies no absolute threshold"
    else:
        pytest.fail(f"{cell}: unregistered ladder branch {branch!r}")


def test_metrics_for_rejects_a_cell_with_no_metrics_block():
    doc = {"cells": [{"id": "X"}]}
    with pytest.raises(cell_info.UnknownIdError, match="no `metrics:` block"):
        cell_info.metrics_for(doc, "X")


def test_metrics_for_rejects_a_partial_metrics_block():
    doc = {"cells": [{"id": "X", "metrics": {"lidar_topic": "/t"}}]}
    with pytest.raises(cell_info.UnknownIdError, match="missing ndt_topic"):
        cell_info.metrics_for(doc, "X")


def test_metrics_for_rejects_an_unknown_cell(doc):
    with pytest.raises(cell_info.UnknownIdError, match="unknown cell 'Q'"):
        cell_info.metrics_for(doc, "Q")


# ---------------------------------------------------------------------------
# The 2026-07-30 core-duel scope cut, pinned as a record-integrity guard.
#
# `dropped:` says a cell is out of MEASUREMENT scope; `mandatory:` still says
# whether a campaign result rested on it. That PAIRING is the record, so it is
# pinned here rather than left to prose: quietly flipping CAL-seam or B45 to
# `mandatory: false` would make cells.yaml read as if they had always been
# optional (they were not), and silently striking a third mandatory cell
# without an amendment entry would be invisible. Both now fail a test instead
# of passing review.
#
# Nothing in the harness reads either key to decide completeness -- these
# tests are the only consumers, deliberately, and they check the RECORD, not a
# measurement.
# ---------------------------------------------------------------------------

# Struck by the owner's 2026-07-30 core-duel scope cut, on an owner
# time-budget decision (benchmarks/README.md, `## Amendments made so far`).
# NOT dropped for being infeasible, blocked or unmeasurable.
#
# CAL-seam left this set 2026-08-03 (Task 8, P4 transport-sweep plan): the
# owner reinstated it (P4 spec decision 6) on the D8 lift that makes the
# fork-side twin publisher buildable (Task 9). Its `dropped:` key is gone
# from cells.yaml; `mandatory: true` was never touched by either the strike
# or the reinstatement.
DROPPED_CELL_IDS = frozenset({"B45", "E-opt", "A-hf", "B-hf", "D"})
# The one that still carries `mandatory: true` while struck -- the reason
# that scope cut is a pre-registration AMENDMENT and not merely a note. Until
# 2026-08-03 this set also held CAL-seam; see the reinstatement note above.
DROPPED_MANDATORY_CELL_IDS = frozenset({"B45"})
DROPPED_MARKER = "owner-time-budget-2026-07-30"


def test_the_scope_cut_struck_exactly_the_recorded_cells(doc):
    struck = {str(c["id"]) for c in doc["cells"] if c.get("dropped")}
    assert struck == set(DROPPED_CELL_IDS)


@pytest.mark.parametrize("cell", sorted(DROPPED_CELL_IDS))
def test_every_struck_cell_names_the_owner_time_budget_decision(doc, cell):
    """One marker value, so "why was this dropped?" has one answer for every
    struck cell and cannot drift into a per-cell story that reads as a
    technical failure on some of them."""
    assert cell_info.cell_entry(doc, cell)["dropped"] == DROPPED_MARKER


@pytest.mark.parametrize("cell", sorted(DROPPED_MANDATORY_CELL_IDS))
def test_the_mandatory_strike_keeps_mandatory_true(doc, cell):
    """The strike must not erase what was given up. `mandatory: true` is the
    only thing in the tree that still records that a MANDATORY cell was cut --
    the hard-fork-maintenance finding for B45, the sole remaining member of
    this set since CAL-seam's 2026-08-03 reinstatement -- as opposed to an
    owner-strikable one (D / E-opt / A-hf / B-hf, which were `mandatory:
    false` before the cut and still are)."""
    assert cell_info.cell_entry(doc, cell)["mandatory"] is True


@pytest.mark.parametrize("cell", sorted(DROPPED_CELL_IDS - DROPPED_MANDATORY_CELL_IDS))
def test_the_note_only_strikes_were_already_non_mandatory(doc, cell):
    """The converse, so the two classes cannot be merged from the other side:
    these four needed no matrix change because they were pre-registered as
    owner-strikable. A cell appearing here with `mandatory: true` would mean
    an amendment item is missing."""
    assert cell_info.cell_entry(doc, cell)["mandatory"] is False


@pytest.mark.parametrize("cell", sorted(set(ALL_CELL_IDS) - DROPPED_CELL_IDS))
def test_every_kept_cell_carries_no_dropped_key(doc, cell):
    """Absence of the key is what "in scope" means, so it must be absent and
    not `dropped: false` -- the A-vs-B duel plus C / E0 / E / CAL-rmw /
    CAL-seam (reinstated 2026-08-03, Task 8)."""
    assert "dropped" not in cell_info.cell_entry(doc, cell)


def test_a_struck_cell_still_resolves_through_cell_info(doc):
    """Struck is NOT deleted. The entries stay registered so the record of
    what was given up survives, so `analysis/manifest.py` still accepts the id
    on the already-filed runs, and so a reader can see the full matrix. The
    key rides along in the merged JSON (`cell_info.merge` copies it), where
    run.sh ignores it -- run.sh reads only approach / map / carla /
    has_sim_clock / arms / sweep_arms.

    B45, not CAL-seam: CAL-seam was this exemplar until its 2026-08-03
    reinstatement (see test_cal_seam_reinstated_registers_its_launch_path
    below) un-struck it, leaving B45 as the sole struck-and-mandatory cell."""
    merged = cell_info.merge(doc, "B45")
    assert merged["dropped"] == DROPPED_MARKER
    assert merged["mandatory"] is True
    assert merged["has_sim_clock"] is True  # unchanged by the strike
    assert "dropped" not in cell_info.merge(doc, "A")


# ---------------------------------------------------------------------------
# CAL-seam reinstated 2026-08-03 (Task 8, P4 transport-sweep plan): the
# bindings a live run now depends on, pinned directly rather than inferred
# from `dropped`'s absence above.
# ---------------------------------------------------------------------------


def test_cal_seam_reinstated_registers_its_launch_path(doc):
    """The two publishers under test (extension's `/bench/seam_cloud`, the
    fork's `/bench/incore_cloud` -- benchmarks/patches/extension/README.md)
    must both be in observer_topics/CAL-seam.yaml, or bench_observer records
    nothing and a comparison finds two empty CSVs instead of a delta.
    `tick_hz` is the e2e sync loop's rate (what drives `ext_on_tick`,
    extension/src/ExtensionInit.cpp); `lidar_expected_hz` is both
    publishers' wall-clock-decimated rate (extension/src/publishers/
    BenchCloudPublisher.h and the fork's ROS2.cpp twin). Neither is
    inferable from the cell being a calibration cell -- CAL-rmw registers a
    rate but no tick at all."""
    assert set(_observer_topics("CAL-seam")) == {"/bench/seam_cloud", "/bench/incore_cloud"}
    metrics = cell_info.metrics_for(doc, "CAL-seam")
    assert metrics["tick_hz"] == 20.0
    assert metrics["lidar_expected_hz"] == 10.0
    assert metrics["ndt_expected_hz"] is None  # no localization stack in this cell
    entry = cell_info.cell_entry(doc, "CAL-seam")
    assert "dropped" not in entry
    assert entry["mandatory"] is True


CALIBRATION_SH = CONFIG_DIR.parent / "cells" / "calibration.sh"


def test_cal_seam_branch_exports_both_bench_env_vars_into_the_run_e2e_invocation():
    """A LITERAL PIN, explicitly narrow and explicitly disclosed as such --
    NOT a subprocess check. Everything this suite CAN verify behaviourally
    now lives in tests/benchmarks/test_calibration_launch.py, which runs the
    real `calibration.sh plan` as a subprocess (no CARLA needed: `plan` mode
    writes launch.env and exits before ever touching run_e2e.sh) and asserts
    on the real generated file -- that is where APPROACH, ARM_ENABLED,
    GT_ENABLED, INJECTOR_ENABLED, RUN_MODE and SPAWN_ARGS are pinned as real
    behaviour.

    What is NOT reachable that way: the two `$CARLA_BENCH_*_CLOUD=1` exports
    and `WITH_AUTOWARE=0` live in the `up`-mode subshell that execs
    `run_e2e.sh`, which `plan` mode exits before reaching -- and actually
    running it needs a live CARLA this environment does not have (Task 8's
    brief is explicit: no CARLA, no live-launch attempt). So this one
    assertion stays a text scan, and is deliberately SLICED NARROWLY to just
    the exec-subshell's own body (`cd "$BENCH_REPO"` .. `echo $! >` its pid
    file) rather than the whole CAL-seam branch: that body contains no
    comments, so unlike a scan over the full branch (which a comment could
    satisfy -- e.g. `WITH_AUTOWARE=0` appears in an explanatory comment a few
    lines above this same subshell), every match here is a real assignment
    on the command line `nohup bash scripts/e2e/run_e2e.sh` actually runs
    with."""
    text = CALIBRATION_SH.read_text()
    seam_branch_start = text.index('"$BENCH_CELL" = "CAL-seam"')
    rmw_guard_start = text.index('"$BENCH_CELL" = "CAL-rmw"')
    assert seam_branch_start < rmw_guard_start, (
        "the CAL-seam branch must be handled before the CAL-rmw-only guard"
    )
    seam_branch = text[seam_branch_start:rmw_guard_start]
    # The old refusal text this branch replaces -- a negative assertion, so
    # it is not weakened by scanning the whole branch: nothing in the intact
    # branch needs to contain this phrase, comment or code.
    assert "has not been written" not in seam_branch

    exec_start = seam_branch.index('cd "$BENCH_REPO"')
    exec_end = seam_branch.index('echo $! >"$CARLA_PID_FILE"', exec_start)
    exec_body = seam_branch[exec_start:exec_end]
    assert "CARLA_BENCH_SEAM_CLOUD=1" in exec_body
    assert "CARLA_BENCH_INCORE_CLOUD=1" in exec_body
    assert "WITH_AUTOWARE=0" in exec_body
    assert "run_e2e.sh" in exec_body
