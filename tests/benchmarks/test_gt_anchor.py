"""Tests for the per-approach base_link anchor (Task 13).

The property that matters most here is the EXACT no-op for the extension cells:
G1's 0.089 m and G2's 0.244 m were measured with gt.csv anchored at the CARLA
actor origin, and they stay valid only if this transform cannot move a cell-A
sample by even a float epsilon.
"""

from __future__ import annotations

import math

import pytest

from benchmarks.analysis.gt_anchor import (
    GT_ANCHOR_OFFSET_M,
    base_link_from_actor_origin,
    offset_for_approach,
    offset_from_bridge_source,
    offset_from_demo_source,
    verify_registered_offset,
)


def test_extension_anchor_is_exactly_zero_because_base_link_is_the_actor_origin():
    """runner/ applies no vehicle-frame shift, so there is nothing to correct."""
    assert offset_for_approach("extension") == 0.0


def test_extension_transform_is_bit_identical_not_merely_close():
    """The promoted G1/G2 numbers depend on this being an EXACT identity.

    A `+ 0.0 * cos(yaw)` would be value-equal but still a float round-trip; the
    implementation short-circuits instead, so the returned objects are the very
    inputs. Asserted at an awkward yaw and awkward coordinates on purpose.
    """
    x, y, yaw = 81571.61600000001, 50019.827499999995, 2.9261740000000003
    out_x, out_y = base_link_from_actor_origin(x, y, yaw, 0.0)
    assert out_x == x
    assert out_y == y


def test_tier4_offset_is_the_demos_literal_not_the_vehicle_wheelbase():
    """R5's correction: 2.79/2 = 1.395 is NOT what the demo uses."""
    assert offset_for_approach("tier4-native") == -1.39706787
    assert offset_for_approach("tier4-native") != -2.79 / 2


def test_bridge_offset_is_where_the_bridge_puts_base_link_not_the_sample_vehicle_value():
    """C2: -1.425 stays; the 0.03 m gap against 2.79 is a registered confound."""
    assert offset_for_approach("python-bridge") == -1.425
    assert offset_for_approach("python-bridge") == -2.850 / 2


def test_offset_is_applied_along_the_heading_so_it_rotates_with_yaw():
    """R3: the term is body-frame longitudinal, so it is NOT a map constant."""
    # Facing +X: the whole offset lands on x.
    x, y = base_link_from_actor_origin(100.0, 200.0, 0.0, -1.4)
    assert x == pytest.approx(98.6)
    assert y == pytest.approx(200.0)
    # Facing +Y (90 deg): the whole offset lands on y instead.
    x, y = base_link_from_actor_origin(100.0, 200.0, math.pi / 2, -1.4)
    assert x == pytest.approx(100.0)
    assert y == pytest.approx(198.6)


def test_a_169_degree_turn_moves_the_correction_by_nearly_twice_the_offset():
    """Why "state the offset beside every number" was rejected on the merits.

    The committed Town10 route turns 169.4 degrees, so a map-frame constant
    chosen at the start heading is wrong by ~2x the offset by the goal.
    """
    offset = -1.39706787
    start_x, _ = base_link_from_actor_origin(0.0, 0.0, 0.0, offset)
    end_x, _ = base_link_from_actor_origin(0.0, 0.0, math.radians(169.4), offset)
    # -1.397 at the start heading, +1.373 at the goal heading: the correction
    # very nearly reverses sign, so a constant chosen at either end is ~2.77 m
    # wrong at the other -- against a 1.0 m goal gate.
    assert abs(end_x - start_x) == pytest.approx(2.770, abs=1e-3)


def test_magnitude_is_preserved_at_every_heading():
    for deg in range(0, 360, 17):
        x, y = base_link_from_actor_origin(0.0, 0.0, math.radians(deg), -1.39706787)
        assert math.hypot(x, y) == pytest.approx(1.39706787)


def test_unknown_approach_raises_rather_than_defaulting_to_zero():
    """A silent 0.0 for an unregistered approach IS the bug this prevents."""
    with pytest.raises(KeyError, match="no registered base_link anchor offset"):
        offset_for_approach("some-new-approach")


def _repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[2]


def test_every_registered_cells_yaml_approach_has_an_anchor():
    """cells.yaml must not be able to name an approach this registry lacks.

    This is the guard that makes offset_for_approach's KeyError unreachable in
    practice: a new cell family gets an anchor at registration time, not a
    silent 0.0 the first time it runs.
    """
    import yaml

    cells = yaml.safe_load((_repo_root() / "benchmarks/config/cells.yaml").read_text())
    approaches = {c["approach"] for c in cells["cells"] if "approach" in c}
    assert approaches
    missing = sorted(approaches - set(GT_ANCHOR_OFFSET_M))
    assert not missing, f"cells.yaml approaches with no registered anchor: {missing}"


def test_demo_source_parser_reads_the_assignment_not_a_stray_number():
    text = "x = -9.9\npivot_to_base_link_transform = ROS2.Transform(x=-1.39706787)\n"
    assert offset_from_demo_source(text) == -1.39706787


def test_demo_source_parser_refuses_when_the_assignment_is_gone():
    with pytest.raises(ValueError, match="no `pivot_to_base_link_transform`|has no"):
        offset_from_demo_source("nothing relevant here\n")


def test_bridge_source_parser_halves_and_negates_the_wheelbase():
    assert offset_from_bridge_source("DEFAULT_WHEELBASE = 2.850\n") == -1.425


def test_verify_accepts_the_matching_source():
    verify_registered_offset(
        "tier4-native", "pivot_to_base_link_transform = ROS2.Transform(x=-1.39706787)"
    )
    verify_registered_offset("python-bridge", "DEFAULT_WHEELBASE = 2.850")


def test_verify_aborts_when_the_demo_literal_drifts():
    """A fork edit or a patch that parameterizes the spawn offset must fail."""
    with pytest.raises(ValueError, match="registers a base_link anchor offset"):
        verify_registered_offset(
            "tier4-native", "pivot_to_base_link_transform = ROS2.Transform(x=-1.5)"
        )


def test_verify_aborts_if_the_extensions_removed_shift_comes_back():
    """docs/e2e-report.md issue #6 must not be able to return silently."""
    with pytest.raises(ValueError, match="issue #6"):
        verify_registered_offset("extension", "def base_link_to_vehicle_center(x):\n    pass\n")


def test_verify_passes_for_a_clean_extension_source():
    verify_registered_offset("extension", "def sensor_in_base_link(kit, frame):\n    pass\n")


def test_registered_tier4_offset_matches_the_real_demo_if_present():
    """Against the actual fork tree, when this workstation has it."""
    import os
    from pathlib import Path

    import yaml

    pins = yaml.safe_load((_repo_root() / "benchmarks/pins.yaml").read_text())
    demo = (
        Path(os.path.expanduser(pins["tier4_carla_fork"]["path"]))
        / "PythonAPI/examples/autoware_demo.py"
    )
    if not demo.is_file():
        pytest.skip(f"tier4 fork demo not present at {demo}")
    verify_registered_offset("tier4-native", demo.read_text())


def test_registered_extension_anchor_matches_the_real_runner():
    """The forbidden symbols really are absent from the committed runner."""
    root = _repo_root()
    text = (root / "runner/kit.py").read_text() + (root / "runner/spawn.py").read_text()
    verify_registered_offset("extension", text)
