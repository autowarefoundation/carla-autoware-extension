"""Unit tests for arm_and_goal.py's pure pieces: the localization-rate rule,
the yaw-only quaternion convention, the CLI surface, and the documented exit
codes (Task 7's Produces line: "exit 0 armed / 2 timeout").

``benchmarks.injector.arm_and_goal`` imports rclpy and the AD API message
packages at module scope, and CI has none of them -- same situation as
tests/e2e/test_dummy_perception.py, and stubbed the same way with
``setdefault`` so a real ROS environment still uses the real modules. The
service-calling methods on ArmAndGoal (wait_localized/set_route/engage) are
not covered here: they need a live rclpy executor and AD API services, which
is exactly what running only inside the Autoware container buys -- the same
reason scripts/e2e/reseed_localization.py, the closest existing precedent,
has no dedicated test file either. What IS covered is everything that does
not need rclpy to be real: the arithmetic and the argument parser.
"""

from __future__ import annotations

import math
import sys
import types

import pytest


class _StubModule(types.ModuleType):
    """Yields a fresh empty class for any attribute, so `from x import Y`
    works without the real package (matches test_dummy_perception.py)."""

    def __getattr__(self, name: str):
        return type(name, (), {})


for _name in (
    "rclpy",
    "rclpy.node",
    "autoware_adapi_v1_msgs",
    "autoware_adapi_v1_msgs.srv",
    "nav_msgs",
    "nav_msgs.msg",
):
    sys.modules.setdefault(_name, _StubModule(_name))

from benchmarks.injector.arm_and_goal import (  # noqa: E402
    EXIT_ARMED,
    EXIT_TIMEOUT,
    build_arg_parser,
    recent_count,
    yaw_to_quaternion_zw,
)

# ---------------------------------------------------------------------------
# recent_count: the "sustained >= 5 Hz over a trailing window" rule.
# ---------------------------------------------------------------------------


def test_recent_count_counts_only_timestamps_within_the_window():
    # now=10, window=5 -> [5, 10] inclusive; 3.0 falls outside, the rest inside.
    assert recent_count([3.0, 5.0, 7.5, 10.0], now=10.0, window_s=5.0) == 3


def test_recent_count_is_zero_when_nothing_is_recent():
    assert recent_count([0.0, 1.0], now=10.0, window_s=5.0) == 0


def test_recent_count_is_zero_for_empty_timestamps():
    assert recent_count([], now=10.0, window_s=5.0) == 0


def test_recent_count_includes_the_boundary_sample():
    # exactly window_s old must still count (<=, not <).
    assert recent_count([5.0], now=10.0, window_s=5.0) == 1


# ---------------------------------------------------------------------------
# yaw_to_quaternion_zw: yaw-only quaternion, same convention as
# arm_closed_loop.sh's SEED computation / reseed_localization.py.
# ---------------------------------------------------------------------------


def test_yaw_zero_is_identity_quaternion():
    qz, qw = yaw_to_quaternion_zw(0.0)
    assert (qz, qw) == pytest.approx((0.0, 1.0))


def test_yaw_pi_over_2_matches_sin_cos_half_angle():
    qz, qw = yaw_to_quaternion_zw(math.pi / 2)
    assert (qz, qw) == pytest.approx((math.sin(math.pi / 4), math.cos(math.pi / 4)))


def test_yaw_pi_gives_pure_z_rotation():
    qz, qw = yaw_to_quaternion_zw(math.pi)
    assert (qz, qw) == pytest.approx((1.0, 0.0), abs=1e-9)


def test_yaw_negative_negates_z_only():
    qz, qw = yaw_to_quaternion_zw(-math.pi / 2)
    assert qz == pytest.approx(-math.sin(math.pi / 4))
    assert qw == pytest.approx(math.cos(math.pi / 4))


# ---------------------------------------------------------------------------
# CLI surface.
# ---------------------------------------------------------------------------


def test_goal_is_required_and_parses_three_floats():
    args = build_arg_parser().parse_args(["--goal", "55.330", "141.161", "0.320"])
    assert args.goal == pytest.approx([55.330, 141.161, 0.320])
    assert args.wait_localized_only is False
    assert args.timeout == 60.0


def test_goal_is_required():
    with pytest.raises(SystemExit) as exc_info:
        build_arg_parser().parse_args([])
    assert exc_info.value.code == 2


def test_wait_localized_only_and_timeout_are_parsed():
    args = build_arg_parser().parse_args(
        ["--goal", "1", "2", "3", "--wait-localized-only", "--timeout", "30"]
    )
    assert args.wait_localized_only is True
    assert args.timeout == 30.0


# ---------------------------------------------------------------------------
# Documented exit codes.
# ---------------------------------------------------------------------------


def test_exit_codes_match_the_documented_contract():
    assert EXIT_ARMED == 0
    assert EXIT_TIMEOUT == 2
