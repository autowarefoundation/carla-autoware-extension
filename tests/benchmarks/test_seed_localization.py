"""Unit tests for seed_localization.py's pure pieces: the convergence
criterion, the CLI surface, and the documented exit codes.

``benchmarks.injector.seed_localization`` imports rclpy and Autoware message
packages at module scope and CI has neither, so they are stubbed exactly as
tests/benchmarks/test_arm_and_goal.py stubs them (``setdefault``, so a real ROS
environment still uses the real modules). The service-calling / spinning method
(``SeedLocalization.seed``) is not covered here for the same reason
``ArmAndGoal``'s is not: it needs a live executor and a live
``/localization/initialize`` server, which is what running only inside the
Autoware container buys. What IS covered is the part that decides the outcome
without rclpy -- whether a given NDT pose counts as locked onto the seed.

The ``ndt_xy is None`` case is the one that matters most and is why
``converged`` exists as a named predicate rather than an inline ``hypot``: on
the run this script was written from (benchmarks/results/B/run-003) the scan
matcher published NOTHING for 420 s, so a criterion that treated "no pose yet"
as anything other than "not converged" would have reported a seeded stack.
"""

from __future__ import annotations

import sys
import types

import pytest


class _StubModule(types.ModuleType):
    """Yields a fresh empty class for any attribute, so `from x import Y`
    works without the real package (matches test_arm_and_goal.py)."""

    def __getattr__(self, name: str):
        return type(name, (), {})


for _name in (
    "rclpy",
    "rclpy.node",
    "autoware_localization_msgs",
    "autoware_localization_msgs.srv",
    "geometry_msgs",
    "geometry_msgs.msg",
):
    sys.modules.setdefault(_name, _StubModule(_name))

from benchmarks.injector.seed_localization import (  # noqa: E402
    CONVERGED_TOLERANCE_M,
    EXIT_OK,
    EXIT_TIMEOUT,
    build_arg_parser,
    converged,
)


def test_no_ndt_pose_at_all_is_not_converged():
    """The measured failure mode of results/B/run-003: 420 s with no
    /localization/pose_estimator/pose message at all. "Nothing yet" must never
    read as "locked", or the launcher would proceed to arm an unlocalized
    stack and the failure would resurface as an arm timeout instead."""
    assert converged(None, (55.322, -141.155)) is False


def test_pose_inside_the_tolerance_is_converged():
    target = (55.322, -141.155)
    assert converged(target, target) is True
    assert converged((target[0] + 0.9, target[1]), target) is True


def test_pose_outside_the_tolerance_is_not_converged():
    target = (55.322, -141.155)
    assert converged((target[0] + 1.5, target[1]), target) is False
    # Diagonal: 0.8 m on each axis is 1.13 m away, outside 1.0 m.
    assert converged((target[0] + 0.8, target[1] + 0.8), target) is False


def test_the_tolerance_boundary_is_inclusive():
    """<= rather than <, so a pose exactly at the tolerance counts. Stated as a
    test because the two conventions differ by a measure-zero case that would
    otherwise be decided by accident."""
    target = (0.0, 0.0)
    assert converged((CONVERGED_TOLERANCE_M, 0.0), target) is True


def test_tolerance_is_the_same_one_the_reseed_path_uses():
    """scripts/e2e/reseed_localization.py's re-seed calls a lock at < 1.0 m; a
    fresh seed must not be scored on a looser criterion than a re-seed."""
    assert CONVERGED_TOLERANCE_M == pytest.approx(1.0)


def test_cli_requires_a_four_number_pose():
    parser = build_arg_parser()
    args = parser.parse_args(["--pose", "55.322", "-141.155", "-0.001", "-0.0053"])
    assert args.pose == [55.322, -141.155, -0.001, -0.0053]
    assert args.timeout == pytest.approx(120.0)
    with pytest.raises(SystemExit):
        parser.parse_args(["--pose", "1", "2", "3"])
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_exit_codes_match_the_documented_contract():
    assert (EXIT_OK, EXIT_TIMEOUT) == (0, 2)
