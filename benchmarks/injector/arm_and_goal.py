#!/usr/bin/env python3
"""Scripted goal + engage: the ONE arm/engage path shared by every approach
under test (extension, bridge, tier4-native). Runs INSIDE the cell's
Autoware container (docker exec), using only rclpy and the AD API message
packages the container already provides -- no docker, no CARLA PythonAPI, no
host-side dependency of any kind, so it works unchanged wherever it is run.

Sequence:

  1. Wait for /localization/kinematic_state to sustain >= 5 Hz over a
     trailing 5 s window ("localized"). Everything below depends on a live
     localization/planning stack, so this is the one precondition checked
     before touching anything else.
  2. --wait-localized-only stops here (a static arm: confirm localization
     came up, do not route or engage). Otherwise:
  3. SetRoutePoints to the given goal -- header.frame_id=map,
     option.allow_goal_modification=true, waypoints=[] -- preceded by a
     best-effort ClearRoute. These are the exact fields
     scripts/e2e/arm_closed_loop.sh's proven-working `ros2 service call`
     invocation uses (Step 3 of that script); this is the same request
     built with rclpy instead of shelled-out YAML text, so the extension
     path -- the one already gated live (docs/e2e-report.md) -- keeps
     identical semantics. The goal carries no z (Task 7's route YAML schema,
     benchmarks/scripts/pick_route.py, likewise omits it from `goal:`) --
     the AD API projects the given x/y onto the lanelet network regardless.
  4. Engage (R4, replacing the AD-API-only attempt Task 7 shipped):

     a. Attempt AD-API `/api/operation_mode/change_to_autonomous`, bounded
        to ADAPI_ENGAGE_ATTEMPT_TIMEOUT_S regardless of --timeout. This is
        NOT the arming mechanism -- step 11.6
        (benchmarks/evidence/step-11_6-adapi-engage/) measured it refuse
        for a full 60 s, ~30 retries, "target mode is not available", on
        cell A, a cell that demonstrably drives. Root cause localized to
        /vehicle/status/control_mode reporting MANUAL, so the
        operation-mode transition manager never marks autonomous
        available. Kept anyway, deliberately: whether change_to_autonomous
        succeeds is itself a per-approach finding this campaign records
        (benchmarks/README.md's "Known confounds" -- the control_mode gap
        is recorded, not patched, because patching every approach into
        reporting AUTONOMOUS would erase a real interop difference). Its
        outcome is logged and never gates step (b).
     b. ALWAYS publish `/autoware/engage {engage: true}` -- the repo's one
        proven arming path (scripts/e2e/arm_closed_loop.sh,
        gate_g2_closed_loop.sh), unconditionally, whether or not (a)
        succeeded. The two paths are not documented as interchangeable
        (arm_closed_loop.sh --disarm calls BOTH the AD-API change_to_stop
        service AND publishes /autoware/engage false), so this function
        does not assume (a) alone is ever sufficient. The gated control_cmd
        window, and the operation-mode state below, are both reset here
        (see verify_control_flowing): only state and traffic from this
        moment on can prove the engage.
     c. Verify BOTH, per review round 2: AUTHORITY -- /api/operation_mode/
        state reports mode == OperationModeState.AUTONOMOUS (NOT
        is_autoware_control_enabled: that flag reports WHO drives, not
        WHICH mode, and some vehicle interfaces report it true in STOP
        mode too -- it is recorded, logged for R4.3, but does not gate)
        -- AND LIVENESS -- the GATED `/control/command/control_cmd` (not
        /control/trajectory_follower/control_cmd, the raw planner output)
        sustains >= CONTROL_CMD_MIN_HZ. Rate alone is not enough:
        benchmarks/results/E/run-008's real trace clears any threshold
        calibrated near 1.30 Hz while never having engaged (see
        CONTROL_CMD_MIN_HZ's comment for what is and is not retained
        evidence for that run), and cell A measures ~19.93 Hz of
        zero-velocity commands PRE-engage while in STOP mode -- either one
        alone would let verify_control_flowing() return True on a stack
        that never armed. engage() returns this check's result, not (a)'s
        or (b)'s reported success, so a near-silent OR not-actually-engaged
        gate cannot reach ARMED through this function.

  Steps 3 and (4a) each retry every 2 s until their service reports
  status.success, up to their own timeout budget. (4a)'s budget is fixed at
  ADAPI_ENGAGE_ATTEMPT_TIMEOUT_S, taken OUT of --timeout, not in addition to
  it: engage()'s total wall time is still bounded by --timeout, matching
  "retrying each up to --timeout" for the localize / set-route / engage
  three-phase contract below. Every wait on the arming path spins this
  node instead of blind-sleeping (review round 1, C2): a non-spinning
  sleep lets the keep-last-10 control_cmd subscription queue up messages
  that then drain in a burst on the next spin, all stamped "now" -- which
  can manufacture a fake sustained rate out of stale backlog.

Usage (inside the `autoware` container, overlay sourced, ROS_DOMAIN_ID=0).
Direct script path, like scripts/e2e/reseed_localization.py -- this module
has no benchmarks.* / scripts.* imports of its own, so unlike
dummy_perception.py it needs neither `cd /work` nor `PYTHONPATH=/work` for
this invocation to resolve:

    python3 /work/benchmarks/injector/arm_and_goal.py --goal X Y YAW_RAD \\
        [--wait-localized-only] --timeout 60

X, Y are map-frame metres and YAW_RAD is map-frame radians -- exactly a
route YAML's (benchmarks/config/routes/<Map>.yaml) `goal: {x, y, yaw_rad}`
fields, so a caller reads a route file and passes its goal straight through.

Exit 0 armed (or localized, under --wait-localized-only); exit 2 on any
timeout (localization never sustained 5 Hz, set_route_points never
succeeded, or authority + the gated control_cmd never both held) within
--timeout.
"""

from __future__ import annotations

import argparse
import collections
import math
import sys
import time
from typing import Callable

import rclpy
from autoware_adapi_v1_msgs.msg import OperationModeState
from autoware_adapi_v1_msgs.srv import ChangeOperationMode, ClearRoute, SetRoutePoints
from autoware_control_msgs.msg import Control
from autoware_vehicle_msgs.msg import Engage
from nav_msgs.msg import Odometry
from rclpy.node import Node

LOCALIZED_TOPIC = "/localization/kinematic_state"
LOCALIZED_WINDOW_S = 5.0
LOCALIZED_MIN_HZ = 5.0
SERVICE_RETRY_PERIOD_S = 2.0
# Slice size for every spin-based wait on the arming path (review round 1,
# C2) -- small enough that a blocked spin never meaningfully overshoots the
# deadlines computed against it.
SPIN_SLICE_S = 0.1

# R4.2 -- the gated control topic. Measured reference points, one
# inference, and one run with no retained arm evidence at all:
#   ~1.30 Hz (n=109, max 11 samples in any trailing 3 s window) --
#     benchmarks/results/E/run-007/observer.csv. This is the ONLY thing
#     retained about run-007's arm attempt: its launch.log contains zero
#     mentions of change_to_autonomous, /autoware/engage or
#     operation_mode (case-insensitive grep), and it has no
#     bridge-stage*.log at all. Its original gate:arm-failed exclusion
#     (superseded by harness:092dc9a) is the only other surviving fact --
#     HOW it failed to arm is not retained, and is not asserted here.
#   8.52 Hz (n=588, max 70 samples in any trailing 3 s window) --
#     benchmarks/results/E/run-008/observer.csv. Ground truth for both
#     runs recomputes to 0.0000 m net displacement and 0.0000 m path
#     length from their own gt.csv, so RATE ALONE CANNOT DISTINGUISH AN
#     ENGAGED STACK FROM EITHER RUN'S STATE. run-008's own
#     bridge-stage2.log retains 78 occurrences of change_to_autonomous's
#     "target mode is not available" refusal (24 tagged "status code 1"
#     by service_log_checker) and ZERO /autoware/engage publications,
#     over a harness_git_sha (4557e5c) that predates 092dc9a -- so
#     run-008 never engaged is an INFERENCE from that log, not a direct
#     capture of /api/operation_mode/state (neither run's
#     observer_topics.yaml lists that topic).
#   ~19.9 Hz -- gate_g2_closed_loop.sh's header claims the same gated topic
#     publishes this fast PRE-engage, in STOP mode, carrying zero-velocity
#     commands. NOT RETAINED as tracked evidence (benchmarks/evidence/
#     README.md's step-11_6 row) -- cited here as the stated reason a
#     script header already treats rate as insufficient on its own, not as
#     a number this threshold is computed from.
#   20.07 Hz -- gated_control_cmd.log, the SAME topic once actually engaged
#     via /autoware/engage, 281/281 samples carrying a nonzero velocity
#     command.
# CONTROL_CMD_MIN_HZ=5.0 is chosen against the 1.30 Hz / 20.07 Hz pair (near
# their geometric mean, sqrt(1.30 * 20.07) ~= 5.11 Hz) but the run-008 and
# pre-engage figures show a threshold on rate ALONE cannot be calibrated to
# separate "engaged" from "not engaged" -- 8.52 Hz sits above it and ~19.9 Hz
# sits far above it, both while genuinely not commanding. That is why
# verify_control_flowing() below requires mode ==
# OperationModeState.AUTONOMOUS (AUTHORITY) in addition to this rate
# (LIVENESS), and resets BOTH at the engage call so pre-engage state and
# traffic cannot satisfy them. Kept as a real, if now secondary,
# requirement: an approach that reports itself autonomous but is not
# actually commanding would still be a false ARMED without it, which is
# the ORIGINAL cell-E defect this task started from. recent_count's
# closed-interval convention (`now - t <= window_s`) means a perfectly
# steady stream needs ~4.67 Hz, not exactly 5.0 Hz, to reach the
# 15-sample count this threshold checks for over a 3 s window
# (14/3 = 4.667; the same approximation pre-exists for LOCALIZED_MIN_HZ).
# CONTROL_CMD_MIN_HZ/CONTROL_CMD_WINDOW_S are engineering judgment, not
# independently measured constants.
CONTROL_CMD_TOPIC = "/control/command/control_cmd"
CONTROL_CMD_MIN_HZ = 5.0
CONTROL_CMD_WINDOW_S = 3.0

# R4.2 (review round 2, NEW-1) -- the AUTHORITY half of the compound check.
# mode == OperationModeState.AUTONOMOUS is the exact flag
# benchmarks/evidence/step-11_6-adapi-engage/legacy_autoware_engage.log's
# single post-engage snapshot states a value for (mode: 2). Deliberately
# NOT is_autoware_control_enabled, true in that same snapshot: that flag
# reports WHO drives, not WHICH mode, and some vehicle interfaces report
# it true in STOP mode too -- gating on it could pass a stationary,
# un-engaged ego on a stack whose engage never took (rebuilding C1/C3
# through a different door). Kept as a recorded, non-gating observation
# instead (self._control_enabled, logged in engage() for R4.3).
# Approach-agnostic: every cell runs the same AD-API operation-mode layer
# regardless of which vehicle interface backs it.
OPERATION_MODE_STATE_TOPIC = "/api/operation_mode/state"

# R4.1 -- the AD-API attempt is bounded far below --timeout's default (60 s)
# because step 11.6 already measured it refuse consistently for the full
# 60 s; a few retries are enough to record the per-approach observation
# without taxing every run in the campaign for the whole budget. Engineering
# judgment, not an independently measured constant.
ADAPI_ENGAGE_ATTEMPT_TIMEOUT_S = 10.0

# R4.1 -- the proven engage path (scripts/e2e/arm_closed_loop.sh,
# gate_g2_closed_loop.sh). Published ENGAGE_PUBLISH_COUNT times over
# ENGAGE_PUBLISH_COUNT * ENGAGE_PUBLISH_PERIOD_S seconds, AFTER up to
# ENGAGE_DISCOVERY_TIMEOUT_S spent waiting for a subscriber to appear --
# the two spans are sequential, not summed into one publish window. The
# repeat is delivery margin against a still-joining DDS graph; harmless
# because engage is documented to LATCH (CLAUDE.md's arming gotchas). All
# four constants are engineering judgment, not independently measured.
ENGAGE_TOPIC = "/autoware/engage"
ENGAGE_DISCOVERY_TIMEOUT_S = 5.0
ENGAGE_PUBLISH_COUNT = 5
ENGAGE_PUBLISH_PERIOD_S = 0.2

EXIT_ARMED = 0
EXIT_TIMEOUT = 2


def recent_count(timestamps, now: float, window_s: float) -> int:
    """Count of `timestamps` within the closed interval [now - window_s,
    now] -- BOTH bounds enforced (`0 <= now - t`, not just `now - t <=
    window_s`), so a timestamp that is actually in the future relative to
    `now` is never counted. In the live wait loop this bound is redundant
    (a deque fed only by callbacks that fire before the loop reads `now`
    can never hold a future value), but it matters for a caller -- namely
    tests/benchmarks/test_arm_and_goal.py's real-trace regression pins --
    that evaluates this function at a `now` drawn from the MIDDLE of an
    already-known series rather than at the moving present.

    Pure so the "sustained >= N Hz over a trailing window" rule is
    unit-testable without rclpy or a live topic; wait_localized/
    verify_control_flowing below are this function plus the rclpy spin
    loop that keeps `timestamps` current, not a re-implementation of it.
    """
    return sum(1 for t in timestamps if 0.0 <= now - t <= window_s)


def sustained_rate_ok(timestamps, now: float, window_s: float, min_hz: float) -> bool:
    """True if `timestamps` shows >= min_hz sustained over the trailing
    window_s seconds ending at `now`. The LIVENESS half of the compound
    arming decision (armed_ok below); also used standalone by
    wait_localized. Pure so it is testable without a live rclpy graph.

    Rate alone is NOT sufficient to decide an arm (review round 1, C1):
    benchmarks/results/E/run-008 clears any threshold set near the 1.30 Hz
    figure this was originally calibrated against -- 8.52 Hz, 0.0000 m net
    displacement (recomputed from its own gt.csv); that it never engaged is
    an INFERENCE from its bridge-stage2.log (78 refusals, 0
    /autoware/engage publications), not a direct measurement -- see
    CONTROL_CMD_MIN_HZ's comment. Kept as the liveness half of armed_ok,
    not the whole decision.
    """
    return recent_count(timestamps, now, window_s) >= min_hz * window_s


def armed_ok(autonomous_mode: bool, timestamps, now: float, window_s: float, min_hz: float) -> bool:
    """The compound R4.2 decision verify_control_flowing() polls each
    iteration: AUTHORITY (autonomous_mode, from /api/operation_mode/state's
    mode == OperationModeState.AUTONOMOUS -- NOT is_autoware_control_enabled,
    which reports WHO drives rather than WHICH mode and could read true in
    STOP mode; see OPERATION_MODE_STATE_TOPIC's comment) AND LIVENESS
    (sustained_rate_ok on the gated control_cmd). Pure and separate from
    sustained_rate_ok so both halves -- and specifically that authority is
    load-bearing, not vestigial -- are unit-testable without rclpy.

    This is the fix for a rate-only guard passing benchmarks/results/E/
    run-008 (8.52 Hz on its real trace, inferred never engaged -- see
    sustained_rate_ok's docstring): tests/benchmarks/test_arm_and_goal.py
    replays run-008's own retained observer.csv arrivals with
    autonomous_mode=False and asserts this returns False throughout, even
    though sustained_rate_ok alone would not.
    """
    return autonomous_mode and sustained_rate_ok(timestamps, now, window_s, min_hz)


def yaw_to_quaternion_zw(yaw_rad: float) -> tuple[float, float]:
    """Yaw-only quaternion (z, w); x = y = 0. Same convention
    scripts/e2e/arm_closed_loop.sh's SEED computation and
    scripts/e2e/reseed_localization.py use (sin(yaw/2), cos(yaw/2))."""
    return math.sin(yaw_rad / 2.0), math.cos(yaw_rad / 2.0)


class ArmAndGoal(Node):
    def __init__(self):
        super().__init__("arm_and_goal")
        self._kinematic_times: collections.deque[float] = collections.deque()
        self.create_subscription(Odometry, LOCALIZED_TOPIC, self._on_kinematic_state, 10)
        # Subscribed from construction so no message is ever missed, but
        # verify_control_flowing() clears this deque at the engage call
        # (review round 1, C3) -- pre-engage traffic must not be able to
        # satisfy the post-engage liveness check. See engage()'s reset.
        self._control_cmd_times: collections.deque[float] = collections.deque()
        self.create_subscription(Control, CONTROL_CMD_TOPIC, self._on_control_cmd, 10)
        # AUTHORITY half of armed_ok (mode == AUTONOMOUS). Starts False
        # like a fresh stack's actual state; reset again at the engage
        # call (engage()), same reasoning as _control_cmd_times.
        self._autonomous_mode: bool = False
        # RECORDED, NOT GATING (review round 2, NEW-1): logged for R4.3's
        # per-approach finding, never used in an arming decision.
        self._control_enabled: bool = False
        self.create_subscription(
            OperationModeState,
            OPERATION_MODE_STATE_TOPIC,
            self._on_operation_mode_state,
            10,
        )

    def _on_kinematic_state(self, _msg: Odometry) -> None:
        self._kinematic_times.append(time.monotonic())

    def _on_control_cmd(self, _msg: Control) -> None:
        self._control_cmd_times.append(time.monotonic())

    def _on_operation_mode_state(self, msg: OperationModeState) -> None:
        self._autonomous_mode = msg.mode == OperationModeState.AUTONOMOUS
        self._control_enabled = bool(msg.is_autoware_control_enabled)

    def _spin_for(self, duration_s: float) -> None:
        """Spin this node for duration_s, in SPIN_SLICE_S slices, instead
        of a blind time.sleep (review round 1, C2). A non-spinning sleep on
        the arming path lets subscriptions -- control_cmd chief among them
        -- queue up (keep-last depth 10) and then drain in a burst on the
        next spin, every buffered message stamped whatever `now()` is at
        drain time. That can manufacture up to 10 samples inside a single
        trailing window out of stale backlog, which is exactly how a
        near-silent gate could otherwise look sustained."""
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            slice_s = max(0.0, min(SPIN_SLICE_S, deadline - time.monotonic()))
            rclpy.spin_once(self, timeout_sec=slice_s)

    def _service_ready(self, client, timeout_s: float) -> bool:
        """client.wait_for_service() replacement: rclpy's own version polls
        the graph with a blind sleep and never spins this node (review
        round 1, C2b) -- another route into the same burst-on-drain
        failure as a bare time.sleep. Poll readiness while spinning."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if client.service_is_ready():
                return True
            rclpy.spin_once(self, timeout_sec=SPIN_SLICE_S)
        return client.service_is_ready()

    def _wait_for_condition(
        self,
        timestamps: collections.deque[float],
        window_s: float,
        timeout_s: float,
        is_ready: Callable[[collections.deque[float], float], bool],
    ) -> bool:
        """Block (spinning this node), trimming `timestamps` to the
        trailing window_s seconds each iteration, until
        is_ready(timestamps, now) is True or timeout_s elapses. Shared
        driver behind wait_localized (is_ready checks sustained_rate_ok
        alone) and verify_control_flowing (is_ready checks armed_ok, the
        compound authority-AND-liveness decision)."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=SPIN_SLICE_S)
            now = time.monotonic()
            while timestamps and now - timestamps[0] > window_s:
                timestamps.popleft()
            if is_ready(timestamps, now):
                return True
        return False

    def wait_localized(self, timeout_s: float) -> bool:
        """Block until LOCALIZED_TOPIC sustains >= LOCALIZED_MIN_HZ over a
        trailing LOCALIZED_WINDOW_S window, or timeout_s elapses."""
        return self._wait_for_condition(
            self._kinematic_times,
            LOCALIZED_WINDOW_S,
            timeout_s,
            lambda ts, now: sustained_rate_ok(ts, now, LOCALIZED_WINDOW_S, LOCALIZED_MIN_HZ),
        )

    def verify_control_flowing(self, timeout_s: float) -> bool:
        """R4.2 (revised, review round 2): block until BOTH hold -- AUTHORITY
        (self._autonomous_mode, mode == OperationModeState.AUTONOMOUS from
        /api/operation_mode/state -- NOT is_autoware_control_enabled, see
        OPERATION_MODE_STATE_TOPIC's comment) AND LIVENESS (the GATED
        CONTROL_CMD_TOPIC sustains >= CONTROL_CMD_MIN_HZ over a trailing
        CONTROL_CMD_WINDOW_S window) -- or timeout_s elapses. Neither alone
        was sufficient: rate alone passes benchmarks/results/E/run-008's
        real trace (8.52 Hz; inferred never engaged, see
        sustained_rate_ok's docstring) and passes vacuously pre-engage on
        cell A (~19.9 Hz zero-velocity in STOP mode); authority alone would
        not catch a stack that reports itself autonomous but is not
        actually commanding -- the original cell-E defect. See
        CONTROL_CMD_MIN_HZ's and armed_ok's comments.

        engage() clears self._control_cmd_times AND self._autonomous_mode
        immediately before calling this, so this can only be satisfied by
        mode/traffic that postdates the engage call (review round 1 C3,
        round 2 NEW-1)."""
        return self._wait_for_condition(
            self._control_cmd_times,
            CONTROL_CMD_WINDOW_S,
            timeout_s,
            lambda ts, now: armed_ok(
                self._autonomous_mode, ts, now, CONTROL_CMD_WINDOW_S, CONTROL_CMD_MIN_HZ
            ),
        )

    def _call_with_retries(self, client, request, service_name: str, timeout_s: float):
        """Call `client` with `request`, retrying every SERVICE_RETRY_PERIOD_S
        until response.status.success, up to ONE overall timeout_s deadline
        shared by the service-readiness wait and every retry (review round
        1, M1 -- the previous version gave each its own fresh timeout_s,
        so a caller could block up to ~2x timeout_s). Returns the
        successful response, or None on timeout."""
        deadline = time.monotonic() + timeout_s
        if not self._service_ready(client, max(0.0, deadline - time.monotonic())):
            self.get_logger().error(f"{service_name}: service never became available")
            return None
        while time.monotonic() < deadline:
            future = client.call_async(request)
            rclpy.spin_until_future_complete(
                self, future, timeout_sec=max(0.1, deadline - time.monotonic())
            )
            resp = future.result()
            if resp is not None and resp.status.success:
                return resp
            reason = resp.status.message if resp is not None else "no response (spin timed out)"
            self.get_logger().warning(f"{service_name}: not yet ok ({reason}); retrying")
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                break
            self._spin_for(min(SERVICE_RETRY_PERIOD_S, remaining))
        return None

    def set_route(self, goal_x: float, goal_y: float, yaw_rad: float, timeout_s: float) -> bool:
        # Best-effort: a fresh stack has no route to clear, and a clear
        # failure must not block setting the new one (arm_closed_loop.sh's
        # own clear_route call is likewise not treated as fatal).
        clear_client = self.create_client(ClearRoute, "/api/routing/clear_route")
        if self._service_ready(clear_client, 2.0):
            future = clear_client.call_async(ClearRoute.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)

        req = SetRoutePoints.Request()
        req.header.frame_id = "map"
        req.option.allow_goal_modification = True
        req.goal.position.x = goal_x
        req.goal.position.y = goal_y
        req.goal.position.z = 0.0  # Task 7's route schema carries no goal z
        qz, qw = yaw_to_quaternion_zw(yaw_rad)
        req.goal.orientation.z = qz
        req.goal.orientation.w = qw
        client = self.create_client(SetRoutePoints, "/api/routing/set_route_points")
        return self._call_with_retries(client, req, "set_route_points", timeout_s) is not None

    def try_adapi_engage(self, timeout_s: float) -> bool:
        """R4.1 step (4a): bounded, non-fatal AD-API attempt. Logged, never
        gates whether legacy_engage() below runs -- see the module
        docstring for why this is kept rather than deleted (it is itself a
        per-approach finding the campaign records, benchmarks/README.md's
        "Known confounds")."""
        client = self.create_client(ChangeOperationMode, "/api/operation_mode/change_to_autonomous")
        resp = self._call_with_retries(
            client, ChangeOperationMode.Request(), "change_to_autonomous", timeout_s
        )
        if resp is not None:
            self.get_logger().info(
                "change_to_autonomous: SUCCEEDED -- per-approach observation, "
                "record it (R4.3); the proven /autoware/engage publish still runs next"
            )
            return True
        self.get_logger().warning(
            f"change_to_autonomous: did not succeed within {timeout_s:.0f} s -- "
            "FALLING BACK to the proven /autoware/engage publish (documented "
            "fallback, not silent; see step-11_6-adapi-engage and R4.3)"
        )
        return False

    def legacy_engage(self) -> None:
        """R4.1 step (4b): publish /autoware/engage {engage: true} -- the
        repo's ONE proven arming path. Always runs, regardless of
        try_adapi_engage()'s outcome (see module docstring)."""
        pub = self.create_publisher(Engage, ENGAGE_TOPIC, 10)
        deadline = time.monotonic() + ENGAGE_DISCOVERY_TIMEOUT_S
        while pub.get_subscription_count() == 0 and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=SPIN_SLICE_S)
        if pub.get_subscription_count() == 0:
            self.get_logger().warning(
                f"{ENGAGE_TOPIC}: no subscriber found after "
                f"{ENGAGE_DISCOVERY_TIMEOUT_S:.0f} s; publishing anyway "
                "(verify_control_flowing() is the real arbiter, not this count)"
            )
        # stamp left at its default (zero): the proven
        # legacy_autoware_engage.log capture used the same unstamped
        # construction and engaged successfully.
        msg = Engage()
        msg.engage = True
        for _ in range(ENGAGE_PUBLISH_COUNT):
            pub.publish(msg)
            self._spin_for(ENGAGE_PUBLISH_PERIOD_S)
        self.get_logger().info(f"{ENGAGE_TOPIC}: published engage=true x{ENGAGE_PUBLISH_COUNT}")

    def engage(self, timeout_s: float) -> bool:
        """R4.1 + R4.2 orchestration. Returns verify_control_flowing()'s
        result -- NOT try_adapi_engage()'s or legacy_engage()'s reported
        success -- so a call that reports success while the gate is
        not actually under command cannot reach ARMED through this
        function. That substitution (trusting a service response instead
        of the gated topic's authority + liveness) is exactly the defect
        this task exists to close.

        timeout_s bounds the WHOLE phase, matching the "fresh timeout
        budget per step" contract documented at module scope: the AD-API
        attempt takes a fixed slice out of it (never in addition to it),
        and whatever remains goes to verify_control_flowing().
        """
        start = time.monotonic()
        adapi_budget = min(ADAPI_ENGAGE_ATTEMPT_TIMEOUT_S, timeout_s)
        self.try_adapi_engage(adapi_budget)
        self.legacy_engage()
        # Reset BOTH terms AT the engage moment (review round 1 C3, round 2
        # NEW-1): without this, a control_cmd stream or an operation-mode
        # state that predates the engage (e.g. cell A's own ~19.9 Hz
        # zero-velocity STOP-mode traffic) could satisfy
        # verify_control_flowing() on its very first iteration, regardless
        # of whether the engage took.
        self._control_cmd_times.clear()
        self._autonomous_mode = False
        self._control_enabled = False
        remaining = max(0.0, timeout_s - (time.monotonic() - start))
        armed = self.verify_control_flowing(remaining)
        # is_autoware_control_enabled is RECORDED here, not gating (NEW-1):
        # log its final observed value alongside the gating mode flag so
        # Task 13/15 can capture it for R4.3's per-approach finding.
        self.get_logger().info(
            f"post-engage state: mode_autonomous={self._autonomous_mode} "
            f"is_autoware_control_enabled={self._control_enabled} "
            "(R4.3 observation; only mode_autonomous gates ARMED)"
        )
        return armed


def build_arg_parser() -> argparse.ArgumentParser:
    """Split out from main() so the CLI surface is unit-testable without
    rclpy/AD-API message stubs."""
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--goal",
        nargs=3,
        type=float,
        required=True,
        metavar=("X", "Y", "YAW_RAD"),
        help="map-frame goal x, y (metres) and yaw (radians) -- a route YAML's "
        "goal.x/goal.y/goal.yaw_rad, fed straight through",
    )
    p.add_argument(
        "--wait-localized-only",
        action="store_true",
        help="stop once localization is confirmed (static arm); do not set a "
        "route or engage autonomous mode",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        metavar="S",
        help="per-phase timeout in seconds (localize / set route / engage), default 60",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    goal_x, goal_y, yaw_rad = args.goal

    rclpy.init()
    node = ArmAndGoal()
    try:
        node.get_logger().info(
            f"waiting for {LOCALIZED_TOPIC} >= {LOCALIZED_MIN_HZ:.0f} Hz over "
            f"{LOCALIZED_WINDOW_S:.0f} s (timeout {args.timeout:.0f} s)"
        )
        if not node.wait_localized(args.timeout):
            print(
                f"ARM FAIL: not localized within {args.timeout:.0f} s "
                f"({LOCALIZED_TOPIC} never sustained {LOCALIZED_MIN_HZ:.0f} Hz)"
            )
            return EXIT_TIMEOUT

        if args.wait_localized_only:
            print(
                f"LOCALIZED: {LOCALIZED_TOPIC} sustained {LOCALIZED_MIN_HZ:.0f} Hz over "
                f"{LOCALIZED_WINDOW_S:.0f} s (static arm; no route set, not engaged)"
            )
            return EXIT_ARMED

        if not node.set_route(goal_x, goal_y, yaw_rad, args.timeout):
            print(
                f"ARM FAIL: set_route_points did not succeed within {args.timeout:.0f} s "
                f"(goal {goal_x:.3f}, {goal_y:.3f})"
            )
            return EXIT_TIMEOUT

        if not node.engage(args.timeout):
            print(
                f"ARM FAIL: {OPERATION_MODE_STATE_TOPIC} never reported mode == "
                f"AUTONOMOUS together with {CONTROL_CMD_TOPIC} sustaining "
                f"~{CONTROL_CMD_MIN_HZ:.2f} Hz nominal (~4.67 Hz effective over "
                f"a closed {CONTROL_CMD_WINDOW_S:.0f} s window), within "
                f"{args.timeout:.0f} s after engage (see step-11_6-adapi-engage "
                "and R4.2 -- neither a service reporting success nor rate alone "
                "is enough)"
            )
            return EXIT_TIMEOUT

        print(f"ARMED: localized, route set to ({goal_x:.3f}, {goal_y:.3f}), autonomous engaged")
        return EXIT_ARMED
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
