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
benchmarks/results/E/run-008 (8.52 Hz, real trace, 0.0000 m net
displacement AND path length -- see the section comment below for exactly
what is measured vs inferred vs not retained per run). The "real trace"
tests below load that same retained observer.csv (and run-007's) through
benchmarks.analysis.bench_io.read_observer_csv -- tracked, recomputable
evidence, not a synthetic generator that can only emit steady arrivals --
specifically because a steady generator cannot reproduce the burstiness or
the over-threshold rate that hid the original gap. Review round 2 then
found the authority term itself gated on the wrong field
(is_autoware_control_enabled instead of mode == AUTONOMOUS) and that the
liveness term was unpinned; both are fixed and pinned below.
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
    # rcl_interfaces is the MRM suppression's parameter-service dependency
    # (SetParameters on vehicle_cmd_gate). Stubbed for the same reason as the
    # rest: CI has no ROS.
    "rcl_interfaces",
    "rcl_interfaces.msg",
    "rcl_interfaces.srv",
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
# over-threshold rate, nor run-007's real burstiness). Evidence status
# differs per run -- stated precisely, not blurred into one claim:
#   run-008: 0.0000 m net displacement AND 0.0000 m path length, recomputed
#     from its own gt.csv. That change_to_autonomous was refused (so
#     mode never reached AUTONOMOUS) is an INFERENCE from
#     run-008/bridge-stage2.log (78 "target mode is not available"
#     refusals, zero /autoware/engage publications) -- neither run's
#     observer_topics.yaml captured /api/operation_mode/state directly.
#   run-007: NO arm-attempt evidence is retained at all (its launch.log
#     has zero mentions of change_to_autonomous, /autoware/engage or
#     operation_mode; it has no bridge-stage*.log). Only its 1.30 Hz rate
#     is retained. `False`/non-autonomous below is the REGRESSION-RELEVANT
#     assumption a compound check must correctly reject under, not a
#     claim about what this run's real state was.
# armed_ok's authority term is the fix for run-008's rate-only escape;
# these tests pin that it is load-bearing, not vestigial.
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


def _armed_ever(autonomous_mode: bool, timestamps, window_s: float, min_hz: float) -> bool:
    """Same scan as _rate_ever_sustained, through the compound armed_ok
    predicate instead of sustained_rate_ok alone."""
    return any(armed_ok(autonomous_mode, timestamps, t, window_s, min_hz) for t in timestamps)


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
    # the rate threshold easily despite the ego never having moved
    # (0.0000 m net displacement AND path length, run-008/gt.csv). This
    # documents C1 directly and must stay green: "fixing" it by
    # recalibrating the rate threshold higher would just chase one number
    # (cell A's own pre-engage traffic runs at ~19.9 Hz, above any such
    # threshold too). It also plays two mechanical roles, not just
    # documentation: it bounds CONTROL_CMD_MIN_HZ from ABOVE on real data
    # (mutating it to 25.0 makes THIS test fail, since 8.52 Hz no longer
    # clears it), and it is the non-vacuity guard for the round-2 pin
    # below -- without a real trace that passes on rate alone, that pin
    # could stay green for the wrong reason (nothing to distinguish).
    ts = _control_cmd_arrival_times_s(RUN_008_OBSERVER)
    assert _rate_ever_sustained(ts, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ) is True


def test_armed_ok_rejects_run_007_with_no_retained_authority_evidence():
    # See the section comment above: run-007 retains no arm-attempt
    # evidence at all. `False` (mode never AUTONOMOUS) is the
    # regression-relevant assumption, not a measured fact about this run.
    ts = _control_cmd_arrival_times_s(RUN_007_OBSERVER)
    assert _armed_ever(False, ts, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ) is False


def test_armed_ok_rejects_run_008_despite_its_rate_clearing_the_threshold():
    # THE round-2 regression pin: run-008's rate alone passes (previous
    # test), so this fails unless armed_ok's authority term is genuinely
    # load-bearing in the AND, not vestigial. `False` here is an inference
    # from run-008/bridge-stage2.log (78 refusals, zero /autoware/engage
    # publications) -- see the section comment above, not a direct
    # capture of /api/operation_mode/state.
    ts = _control_cmd_arrival_times_s(RUN_008_OBSERVER)
    assert _armed_ever(False, ts, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ) is False


def test_armed_ok_would_accept_run_008_if_authority_had_been_true():
    # Confirms the authority term is doing real work rather than always
    # returning False: autonomous_mode=True is NOT run-008's inferred
    # state (a hypothetical), but with it forced true the same real trace
    # passes, because its rate was always sufficient. Guards against
    # `and` silently becoming `or` or similar.
    ts = _control_cmd_arrival_times_s(RUN_008_OBSERVER)
    assert _armed_ever(True, ts, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ) is True


def test_armed_ok_requires_liveness_even_with_authority_true():
    # NEW-2 (review round 2): the liveness term itself was unpinned --
    # `return autonomous_mode` (dropping the rate check entirely) or
    # weakening it to "any sample at all" both left every previous test
    # green, since they only ever forced authority FALSE to prove
    # rejection. Force authority TRUE here (not run-007's real/assumed
    # state -- a hypothetical, like the run-008 test above) against
    # run-007's real trace, which never reaches the rate threshold: if
    # armed_ok ever ignored or weakened liveness, this would flip to True.
    ts = _control_cmd_arrival_times_s(RUN_007_OBSERVER)
    assert _armed_ever(True, ts, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ) is False


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


# --- MRM suppression constants (Task 13, results/B/run-008) -----------------
# The behaviour needs a live vehicle_cmd_gate, so what is pinned here is the
# CONTRACT: which node and parameter, and that the value is false. run-008
# measured what happens without it -- MRM_OPERATING, "EMERGENCY_STOP is
# operated.", 231 x "no mrm operation available", /autoware/modes/autonomous
# ERROR x35, and change_to_autonomous refused.


def test_mrm_suppression_targets_the_same_node_and_param_as_the_proven_sequence():
    """scripts/e2e/arm_closed_loop.sh step 5 sets exactly this pair."""
    from benchmarks.injector.arm_and_goal import (
        EMERGENCY_HANDLING_PARAM,
        VEHICLE_CMD_GATE_NODE,
    )

    assert VEHICLE_CMD_GATE_NODE == "/control/vehicle_cmd_gate"
    assert EMERGENCY_HANDLING_PARAM == "use_emergency_handling"


def test_the_proven_extension_sequence_still_sets_that_exact_pair():
    """If arm_closed_loop.sh ever changes node or parameter, this must fail.

    The whole justification for suppressing MRM here is that it reproduces the
    configuration every promoted gate number already came from. If the proven
    script diverges, that justification no longer holds.
    """
    from benchmarks.injector.arm_and_goal import (
        EMERGENCY_HANDLING_PARAM,
        VEHICLE_CMD_GATE_NODE,
    )

    text = (Path(__file__).resolve().parents[2] / "scripts/e2e/arm_closed_loop.sh").read_text()
    assert f"ros2 param set {VEHICLE_CMD_GATE_NODE} {EMERGENCY_HANDLING_PARAM} false" in text


def test_mrm_param_budget_is_bounded_so_it_cannot_eat_the_whole_arm_timeout():
    from benchmarks.injector.arm_and_goal import ADAPI_ENGAGE_ATTEMPT_TIMEOUT_S, MRM_PARAM_TIMEOUT_S

    assert 0.0 < MRM_PARAM_TIMEOUT_S <= 15.0
    # Both pre-engage attempts together must leave room inside a 60 s arm.
    assert MRM_PARAM_TIMEOUT_S + ADAPI_ENGAGE_ATTEMPT_TIMEOUT_S < 60.0


# --- arm observability (Task 13, coordinator ruling 2c) ----------------------
# OBSERVABILITY ONLY: armed_ok is unchanged and none of this feeds a decision.
# The point is that a filed arm failure records every candidate authority
# signal on both sides of engage, so the authority term can be ruled on from
# data instead of from a guess.


def test_nonzero_longitudinal_counts_and_fractions():
    from benchmarks.injector.arm_and_goal import nonzero_longitudinal

    n, frac, peak = nonzero_longitudinal([0.0, 0.0, 4.17, -2.0])
    assert n == 2
    assert frac == pytest.approx(0.5)
    assert peak == pytest.approx(4.17)


def test_all_zero_commands_are_distinguished_from_no_commands():
    """The pre-engage STOP-mode case: commands flowing, all zero."""
    from benchmarks.injector.arm_and_goal import nonzero_longitudinal

    n, frac, peak = nonzero_longitudinal([0.0] * 400)
    assert n == 0
    assert frac == pytest.approx(0.0)
    assert peak == 0.0


def test_empty_series_reports_nan_fraction_not_zero():
    """ "No commands seen" must not read as "commands seen, all zero".

    Same reasoning cadence.reconcile_drops uses for its NaN observer_loss_rate.
    """
    from benchmarks.injector.arm_and_goal import nonzero_longitudinal

    n, frac, peak = nonzero_longitudinal([])
    assert n == 0
    assert math.isnan(frac)
    assert peak == 0.0


def test_step_11_6_engaged_trace_reads_as_fully_nonzero():
    """Cell A engaged: 281/281 nonzero at +4.170 m/s."""
    from benchmarks.injector.arm_and_goal import nonzero_longitudinal

    n, frac, _ = nonzero_longitudinal([4.170] * 281)
    assert n == 281
    assert frac == pytest.approx(1.0)


def test_zero_epsilon_is_tight_enough_to_not_swallow_a_real_creep():
    from benchmarks.injector.arm_and_goal import ZERO_COMMAND_EPS_MPS, nonzero_longitudinal

    assert ZERO_COMMAND_EPS_MPS <= 1e-6
    n, _, _ = nonzero_longitudinal([0.001])
    assert n == 1


def test_armed_ok_is_unchanged_by_the_observability_work():
    """Regression guard: the authority term must still be mode-gated only."""
    from benchmarks.injector.arm_and_goal import armed_ok

    now = 1000.0
    live = [now - 0.1 * i for i in range(40)]
    # Liveness satisfied but authority absent -> still NOT armed.
    assert not armed_ok(False, live, now, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ)
    # Both satisfied -> armed.
    assert armed_ok(True, live, now, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ)


# --- I-1 regression guard (fix round 1) --------------------------------------
# R4 fix round 2 verified "all three state variables reset in one block at
# engage". Task 13 added three OBSERVABILITY variables without extending that
# reset, so post-engage observations pooled pre-engage commands. This pins the
# whole reset block by SOURCE, because the behaviour needs a live executor:
# a unit test cannot call engage() without rclpy, but it can assert that every
# piece of per-engage state is cleared in the same block.


def _engage_reset_block() -> str:
    """The text of engage()'s reset block, from `legacy_engage()` to `remaining`."""
    src = (Path(__file__).resolve().parents[2] / "benchmarks/injector/arm_and_goal.py").read_text()
    start = src.index("self.legacy_engage()")
    end = src.index("remaining = max(", start)
    return src[start:end]


def test_every_per_engage_variable_is_reset_at_engage():
    """Fails if ANY of the six survives an engage -- the I-1 regression."""
    block = _engage_reset_block()
    for expected in (
        "self._control_cmd_times.clear()",
        "self._autonomous_mode = False",
        "self._control_enabled = False",
        "self._cmd_longitudinal.clear()",
        "self._speeds.clear()",
        "self._first_xy = None",
    ):
        assert expected in block, f"engage() no longer resets: {expected}"


def test_the_reset_covers_every_observability_field_arm_observations_reads():
    """A new per-engage field must be added to the reset block, not just to
    __init__ -- which is precisely how I-1 happened."""
    src = (Path(__file__).resolve().parents[2] / "benchmarks/injector/arm_and_goal.py").read_text()
    block = _engage_reset_block()
    # Fields arm_observations() derives its numbers from, excluding the raw
    # mode/available flags which are refreshed by every incoming message.
    for field in ("_cmd_longitudinal", "_speeds", "_first_xy", "_control_cmd_times"):
        assert f"self.{field}" in src, f"{field} disappeared from the module"
        assert field in block, f"{field} is read by arm_observations but not reset at engage"


# --- I-1 BEHAVIOURAL pin (fix round 2) ---------------------------------------
# The source-text scans below/above are a second signal only. They pass whenever
# the text is PRESENT, so they survive the reset being commented out, moved off
# the engage path, made unreachable, or shadowed -- they pin the source, not the
# behaviour. That is the same "asserts less than its name claims" defect the
# guard was added to close, so the real pin is here: drive the ACTUAL engage()
# with sentinel state and assert every per-engage variable came back reset.
#
# engage() needs no rclpy -- it touches only time.monotonic() and its own
# methods -- so it can be driven with a duck-typed object via the unbound
# function. That is what makes a behavioural assertion possible at unit level.


class _FakeLogger:
    def info(self, *_a, **_k):
        pass

    def warning(self, *_a, **_k):
        pass


class _FakeArm:
    """Duck-typed stand-in carrying only what engage() touches."""

    def __init__(self):
        import collections as _c

        # Sentinels: every one must be gone after engage().
        self._control_cmd_times = _c.deque([1.0, 2.0, 3.0])
        self._autonomous_mode = True
        self._control_enabled = True
        self._cmd_longitudinal = _c.deque([4.17, 4.17, 4.17])
        self._speeds = _c.deque([9.9, 9.9])
        self._first_xy = (111.0, 222.0)
        self._last_xy = (333.0, 444.0)
        self.verify_called_with = None

    def get_logger(self):
        return _FakeLogger()

    def arm_observations(self, label):
        return f"obs[{label}]"

    def suppress_false_mrm(self, _timeout):
        return True

    def try_adapi_engage(self, _timeout):
        return False

    def legacy_engage(self):
        return None

    def verify_control_flowing(self, timeout_s):
        # Captured so the test can prove the reset happened BEFORE the
        # verification window opened, not merely by the time engage() returned.
        self.verify_called_with = {
            "control_cmd_times": list(self._control_cmd_times),
            "autonomous_mode": self._autonomous_mode,
            "control_enabled": self._control_enabled,
            "cmd_longitudinal": list(self._cmd_longitudinal),
            "speeds": list(self._speeds),
            "first_xy": self._first_xy,
            "last_xy": self._last_xy,
            "timeout_s": timeout_s,
        }
        return False


def _drive_engage():
    from benchmarks.injector.arm_and_goal import ArmAndGoal

    fake = _FakeArm()
    ArmAndGoal.engage(fake, 30.0)
    return fake


def test_engage_actually_resets_every_per_engage_variable():
    """BEHAVIOURAL: fails if the reset is neutralised, not only if deleted."""
    fake = _drive_engage()
    assert list(fake._control_cmd_times) == []
    assert fake._autonomous_mode is False
    assert fake._control_enabled is False
    assert list(fake._cmd_longitudinal) == []
    assert list(fake._speeds) == []
    assert fake._first_xy is None
    assert fake._last_xy is None


def test_the_reset_happens_BEFORE_the_verification_window_opens():
    """Ordering matters: a reset after verify_control_flowing would let
    pre-engage traffic satisfy the very check it is meant to gate."""
    fake = _drive_engage()
    seen = fake.verify_called_with
    assert seen is not None, "engage() never called verify_control_flowing"
    assert seen["control_cmd_times"] == []
    assert seen["autonomous_mode"] is False
    assert seen["control_enabled"] is False
    assert seen["cmd_longitudinal"] == []
    assert seen["speeds"] == []
    assert seen["first_xy"] is None
    assert seen["last_xy"] is None


def test_engage_still_reports_the_verification_result():
    """Guard against a reset refactor that swallows engage()'s return value."""
    from benchmarks.injector.arm_and_goal import ArmAndGoal

    fake = _FakeArm()
    fake.verify_control_flowing = lambda _t: True
    assert ArmAndGoal.engage(fake, 30.0) is True
