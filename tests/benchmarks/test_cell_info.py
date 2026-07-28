"""cell_info: the top-of-pipeline typo guard for cell and class ids."""

from __future__ import annotations

import json

import pytest

from benchmarks.scripts import cell_info


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
