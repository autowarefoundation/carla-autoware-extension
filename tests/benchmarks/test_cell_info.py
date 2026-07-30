"""cell_info: the top-of-pipeline typo guard for cell and class ids."""

from __future__ import annotations

import json

import pytest
import yaml

from benchmarks.scripts import cell_info

CONFIG_DIR = cell_info.CELLS_YAML.parent
ALL_CELL_IDS = [str(c["id"]) for c in yaml.safe_load(cell_info.CELLS_YAML.read_text())["cells"]]


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
    a configuration error -- the exact failure mode observer_topics/
    CAL-seam.yaml's deliberately-empty list exists to avoid. `null` bindings
    are skipped: they are the registered "not chosen yet" state."""
    metrics = cell_info.metrics_for(doc, cell)
    registered = _observer_topics(cell)
    for key in ("lidar_topic", "ndt_topic", "control_topic"):
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
