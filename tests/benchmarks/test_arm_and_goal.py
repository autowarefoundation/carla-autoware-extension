"""Unit tests for arm_and_goal.py's pure pieces: the localization-rate rule,
the R4.2 compound authority-AND-liveness arming decision, the yaw-only
quaternion convention, the CLI surface, and the documented exit codes
(Task 7's Produces line: "exit 0 armed / 2 timeout").

``benchmarks.injector.arm_and_goal`` imports rclpy and the AD API message
packages at module scope, and CI has none of them -- same situation as
tests/e2e/test_dummy_perception.py, and stubbed the same way with
``setdefault`` so a real ROS environment still uses the real modules. The
service-calling / rclpy-spinning methods on ArmAndGoal (wait_localized,
set_route, try_adapi_engage, legacy_engage, verify_control_flowing, engage)
are not covered here: they need a live rclpy executor and AD API services,
which is exactly what running only inside the Autoware container buys -- the
same reason scripts/e2e/reseed_localization.py, the closest existing
precedent, has no dedicated test file either. What IS covered is everything
that does not need rclpy to be real: the arithmetic, including the R4.2
decision predicates those methods poll, and the argument parser.

Review round 1 found that a rate-only guard, calibrated only from a
1.30 Hz / 20.07 Hz pair using synthetic steady arrivals, passed
benchmarks/results/E/run-008 (8.52 Hz, real trace, ego never engaged). The
"real trace" tests below load that same retained observer.csv (and
run-007's) through benchmarks.analysis.bench_io.read_observer_csv --
tracked, recomputable evidence, not a synthetic generator that can only
emit steady arrivals -- specifically because a steady generator cannot
reproduce the burstiness or the over-threshold rate that hid the original
gap.
"""

from __future__ import annotations

import math
import sys
import types
from pathlib import Path

import pytest

from benchmarks.analysis.bench_io import read_observer_csv


class _StubModule(types.ModuleType):
    """Yields a fresh empty class for any attribute, so `from x import Y`
    works without the real package (matches test_dummy_perception.py)."""

    def __getattr__(self, name: str):
        return type(name, (), {})


for _name in (
    "rclpy",
    "rclpy.node",
    "autoware_adapi_v1_msgs",
    "autoware_adapi_v1_msgs.msg",
    "autoware_adapi_v1_msgs.srv",
    "autoware_control_msgs",
    "autoware_control_msgs.msg",
    "autoware_vehicle_msgs",
    "autoware_vehicle_msgs.msg",
    "nav_msgs",
    "nav_msgs.msg",
):
    sys.modules.setdefault(_name, _StubModule(_name))

from benchmarks.injector.arm_and_goal import (  # noqa: E402
    CONTROL_CMD_MIN_HZ,
    CONTROL_CMD_WINDOW_S,
    EXIT_ARMED,
    EXIT_TIMEOUT,
    armed_ok,
    build_arg_parser,
    recent_count,
    sustained_rate_ok,
    yaw_to_quaternion_zw,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_007_OBSERVER = REPO_ROOT / "benchmarks/results/E/run-007/observer.csv"
RUN_008_OBSERVER = REPO_ROOT / "benchmarks/results/E/run-008/observer.csv"

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


def test_recent_count_excludes_timestamps_after_now():
    # A timestamp in the future relative to `now` must never count, even
    # though `now - t` alone (without the `>= 0` bound) would read as a
    # very negative, trivially-"within-window" number. Exercised by the
    # real-trace regression pins, which evaluate this function at a `now`
    # drawn from partway through an already-known series.
    assert recent_count([15.0], now=10.0, window_s=5.0) == 0


# ---------------------------------------------------------------------------
# sustained_rate_ok: the shared "sustained >= min_hz over a trailing window"
# decision behind BOTH wait_localized and verify_control_flowing (R4.2).
# ---------------------------------------------------------------------------


def _periodic_timestamps(hz: float, span_s: float, now: float) -> list[float]:
    """Synthetic arrival times at a steady `hz`, ending at `now`, covering
    the trailing `span_s` seconds -- models what a real rclpy subscription's
    timestamp deque holds, without needing a live one."""
    period = 1.0 / hz
    times = []
    t = now
    while t >= now - span_s:
        times.append(t)
        t -= period
    return times


def test_sustained_rate_ok_true_when_the_window_is_full():
    ts = _periodic_timestamps(hz=10.0, span_s=5.0, now=100.0)
    assert sustained_rate_ok(ts, now=100.0, window_s=5.0, min_hz=5.0) is True


def test_sustained_rate_ok_false_when_nothing_has_arrived():
    # Models a timeout: the deque a real wait loop polls never fills.
    assert sustained_rate_ok([], now=100.0, window_s=5.0, min_hz=5.0) is False


def test_sustained_rate_ok_false_just_under_the_count():
    # 5 Hz * 5 s = 25 required; 24 samples in the window must not pass.
    ts = [100.0 - i * (5.0 / 24) for i in range(24)]
    assert sustained_rate_ok(ts, now=100.0, window_s=5.0, min_hz=5.0) is False


def test_sustained_rate_ok_true_at_exactly_the_count():
    ts = [100.0 - i * (5.0 / 25) for i in range(25)]
    assert sustained_rate_ok(ts, now=100.0, window_s=5.0, min_hz=5.0) is True


# ---------------------------------------------------------------------------
# sustained_rate_ok (LIVENESS half only) against two synthetic reference
# rates. No retained per-message trace exists for an actual successful
# engage (gated_control_cmd.log records a summary rate/count, not raw
# arrival timestamps), so the 20.07 Hz case stays synthetic; the 1.30 Hz
# case is superseded below by the real run-007 trace but kept as a simple,
# exact-figure sanity check on the boundary.
# ---------------------------------------------------------------------------


def test_near_silent_control_cmd_must_fail_the_arm_1_30_hz():
    # ~1.30 Hz, matching run-007's measured rate (see the real-trace test
    # below for the actual arrival series).
    ts = _periodic_timestamps(hz=1.30, span_s=CONTROL_CMD_WINDOW_S, now=100.0)
    assert (
        sustained_rate_ok(ts, now=100.0, window_s=CONTROL_CMD_WINDOW_S, min_hz=CONTROL_CMD_MIN_HZ)
        is False
    )


def test_actually_engaged_control_cmd_passes_the_arm_20_07_hz():
    # step 11.6's legacy /autoware/engage capture: 20.07 Hz, 281/281 samples
    # nonzero. No raw per-message trace is retained for this run (only the
    # summary in gated_control_cmd.log), so this stays a synthetic steady
    # stream at the measured rate rather than a real-trace test.
    ts = _periodic_timestamps(hz=20.07, span_s=CONTROL_CMD_WINDOW_S, now=100.0)
    assert (
        sustained_rate_ok(ts, now=100.0, window_s=CONTROL_CMD_WINDOW_S, min_hz=CONTROL_CMD_MIN_HZ)
        is True
    )


# ---------------------------------------------------------------------------
# R4.2 regression pin, driven from the RETAINED real traces (review round 1,
# I4: a synthetic steady-arrival generator cannot reproduce run-008's real,
# over-threshold rate, nor run-007's real burstiness). Cell E's original
# false conclusion came from an engage() that trusted a service response;
# review round 1 found the REPLACEMENT rate-only guard then passed
# run-008 -- 8.52 Hz on the gated topic, but the ego never engaged
# (0.0000 m net displacement, task-10-review.md). armed_ok's authority term
# is the fix; these tests pin that it is load-bearing, not vestigial, using
# both runs' own recorded arrival timestamps.
# ---------------------------------------------------------------------------


def _control_cmd_arrival_times_s(observer_csv_path: Path) -> list[float]:
    """Real /control/command/control_cmd arrival timestamps, in seconds,
    from a retained run's observer.csv -- arrival_steady_ns is the same
    clock domain (a monotonic counter) _on_control_cmd stamps with
    time.monotonic()."""
    cols = read_observer_csv(observer_csv_path)["/control/command/control_cmd"]
    return sorted(ns / 1e9 for ns in cols["arrival_steady_ns"])


def _rate_ever_sustained(timestamps, window_s: float, min_hz: float) -> bool:
    """Whether sustained_rate_ok would ever have been True for some `now`
    in this real trace. recent_count only changes value at an arrival
    instant, so scanning `now = each timestamp` covers every local maximum
    a live polling loop could actually observe."""
    return any(sustained_rate_ok(timestamps, t, window_s, min_hz) for t in timestamps)


def _armed_ever(control_enabled: bool, timestamps, window_s: float, min_hz: float) -> bool:
    """Same scan as _rate_ever_sustained, through the compound armed_ok
    predicate instead of sustained_rate_ok alone."""
    return any(armed_ok(control_enabled, timestamps, t, window_s, min_hz) for t in timestamps)


def test_run_007_real_trace_never_reaches_the_rate_threshold():
    # ~1.30 Hz, n=109, max 11 samples in any trailing 3 s window (need 15)
    # -- rate alone correctly fails this run. Also pins CONTROL_CMD_WINDOW_S
    # itself: mutating it to 1.0 or 2.0 lets this real trace pass on rate
    # alone (10 and 11 samples respectively clear the smaller requirement),
    # which is exactly the gap review round 1 found unpinned.
    ts = _control_cmd_arrival_times_s(RUN_007_OBSERVER)
    assert _rate_ever_sustained(ts, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ) is False


def test_run_008_real_trace_passes_on_rate_alone():
    # 8.52 Hz, n=588, max 70 samples in any trailing 3 s window -- clears
    # the rate threshold easily despite the ego never having engaged. This
    # documents C1 directly: it must stay green, because "fixing" it by
    # recalibrating the rate threshold higher would just chase one number
    # (cell A's own pre-engage traffic runs at ~19.9 Hz, above any such
    # threshold too) instead of adding the authority term that actually
    # discriminates -- tested next.
    ts = _control_cmd_arrival_times_s(RUN_008_OBSERVER)
    assert _rate_ever_sustained(ts, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ) is True


def test_armed_ok_rejects_run_007_with_its_real_measured_authority_state():
    # change_to_autonomous was refused for 60 s on this run
    # (task-10-report.md); is_autoware_control_enabled was never true.
    ts = _control_cmd_arrival_times_s(RUN_007_OBSERVER)
    assert _armed_ever(False, ts, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ) is False


def test_armed_ok_rejects_run_008_despite_its_rate_clearing_the_threshold():
    # THE round-2 regression pin: run-008's rate alone passes (previous
    # test), so this fails unless armed_ok's authority term is genuinely
    # load-bearing in the AND, not vestigial. Ground truth for this run is
    # the same as run-007's -- refused engage, control never enabled.
    ts = _control_cmd_arrival_times_s(RUN_008_OBSERVER)
    assert _armed_ever(False, ts, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ) is False


def test_armed_ok_would_accept_run_008_if_authority_had_been_true():
    # Confirms the authority term is doing real work rather than always
    # returning False: control_enabled=True is NOT run-008's actual
    # measured state (a hypothetical), but with it forced true the same
    # real trace passes, because its rate was always sufficient. Guards
    # against `and` silently becoming `or not` or similar.
    ts = _control_cmd_arrival_times_s(RUN_008_OBSERVER)
    assert _armed_ever(True, ts, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ) is True


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
