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
        does not assume (a) alone is ever sufficient.
     c. Verify the GATED `/control/command/control_cmd` -- what
        vehicle_cmd_gate actually sends, not
        /control/trajectory_follower/control_cmd, the raw planner output
        -- sustains >= CONTROL_CMD_MIN_HZ before reporting ARMED. This is
        the guard that matters most: step 11.6 (this same evidence
        directory) measured the gated topic at 20.07 Hz commanding
        +4.170 m/s on 281/281 samples once actually engaged, against
        ~1.30 Hz (n=109, benchmarks/results/E/run-007/observer.csv) for a
        run whose engage() reported success while nothing drove -- the
        defect that produced cell E's false conclusion. engage() returns
        this check's result, not (a)'s or (b)'s reported success, so a
        near-silent gate cannot reach ARMED through this function.

  Steps 3 and (4a) each retry every 2 s until their service reports
  status.success, up to their own timeout budget. (4a)'s budget is fixed at
  ADAPI_ENGAGE_ATTEMPT_TIMEOUT_S, taken OUT of --timeout, not in addition to
  it: engage()'s total wall time is still bounded by --timeout, matching
  "retrying each up to --timeout" for the localize / set-route / engage
  three-phase contract below.

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
succeeded, or the gated control_cmd never reached sustained flow) within
--timeout.
"""

from __future__ import annotations

import argparse
import collections
import math
import sys
import time

import rclpy
from autoware_adapi_v1_msgs.srv import ChangeOperationMode, ClearRoute, SetRoutePoints
from autoware_control_msgs.msg import Control
from autoware_vehicle_msgs.msg import Engage
from nav_msgs.msg import Odometry
from rclpy.node import Node

LOCALIZED_TOPIC = "/localization/kinematic_state"
LOCALIZED_WINDOW_S = 5.0
LOCALIZED_MIN_HZ = 5.0
SERVICE_RETRY_PERIOD_S = 2.0

# R4.2 -- the gated control topic and the threshold that decides whether an
# engage actually took. Measured reference points (both cited in
# benchmarks/evidence/step-11_6-adapi-engage/ and the R4 report):
#   ~1.30 Hz (n=109) -- benchmarks/results/E/run-007/observer.csv, a
#     closed-loop run whose engage() reported success while the vehicle was
#     not under command (cell E's false conclusion).
#   20.07 Hz -- gated_control_cmd.log, the SAME topic once actually engaged
#     via /autoware/engage, 281/281 samples carrying a nonzero velocity
#     command.
# CONTROL_CMD_MIN_HZ=5.0 sits close to the geometric mean of the two
# (sqrt(1.30 * 20.07) ~= 5.11 Hz), giving a roughly symmetric ~4x margin on
# each side in log-space: comfortably clears the near-silent failure mode
# without demanding anywhere near the full engaged rate, which is free to
# vary a little across approaches. This is a LIVENESS precondition only
# (matching gate_g2_closed_loop.sh's own liveness check) -- it does not
# prove command AUTHORITY: the same gated topic is measured elsewhere
# (gate_g2_closed_loop.sh's header) publishing ~19.9 Hz in STOP mode
# carrying zero-velocity commands, which is why a full driving verdict
# stays G2's job, not this script's.
CONTROL_CMD_TOPIC = "/control/command/control_cmd"
CONTROL_CMD_MIN_HZ = 5.0
CONTROL_CMD_WINDOW_S = 3.0

# R4.1 -- the AD-API attempt is bounded far below --timeout's default (60 s)
# because step 11.6 already measured it refuse consistently for the full
# 60 s; a few retries are enough to record the per-approach observation
# without taxing every run in the campaign for the whole budget.
ADAPI_ENGAGE_ATTEMPT_TIMEOUT_S = 10.0

# R4.1 -- the proven engage path (scripts/e2e/arm_closed_loop.sh,
# gate_g2_closed_loop.sh). Published multiple times over
# ENGAGE_DISCOVERY_TIMEOUT_S + (ENGAGE_PUBLISH_COUNT * ENGAGE_PUBLISH_PERIOD_S)
# seconds for delivery margin against a still-joining DDS graph; harmless
# because engage is documented to LATCH (CLAUDE.md's arming gotchas).
ENGAGE_TOPIC = "/autoware/engage"
ENGAGE_DISCOVERY_TIMEOUT_S = 5.0
ENGAGE_PUBLISH_COUNT = 5
ENGAGE_PUBLISH_PERIOD_S = 0.2

EXIT_ARMED = 0
EXIT_TIMEOUT = 2


def recent_count(timestamps, now: float, window_s: float) -> int:
    """Count of `timestamps` within [now - window_s, now].

    Pure so the "sustained >= N Hz over a trailing window" rule is
    unit-testable without rclpy or a live topic (tests/benchmarks/
    test_arm_and_goal.py); wait_localized/verify_control_flowing below are
    this function plus the rclpy spin loop that keeps `timestamps` current,
    not a re-implementation of it.
    """
    return sum(1 for t in timestamps if now - t <= window_s)


def sustained_rate_ok(timestamps, now: float, window_s: float, min_hz: float) -> bool:
    """True if `timestamps` shows >= min_hz sustained over the trailing
    window_s seconds ending at `now`. The one decision point behind BOTH
    wait_localized (kinematic_state) and verify_control_flowing
    (control_cmd, R4.2) -- pure and shared so the regression R4.2 exists to
    pin (an engage that reports success while the gate is near-silent) is
    tested directly against this predicate, without a live rclpy graph.
    """
    return recent_count(timestamps, now, window_s) >= min_hz * window_s


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
        # Subscribed from construction, not just after engage: the trailing
        # window in verify_control_flowing() only needs samples arriving
        # DURING its own wait, but subscribing early costs nothing and means
        # no message published between node start and the engage call is
        # ever missed.
        self._control_cmd_times: collections.deque[float] = collections.deque()
        self.create_subscription(Control, CONTROL_CMD_TOPIC, self._on_control_cmd, 10)

    def _on_kinematic_state(self, _msg: Odometry) -> None:
        self._kinematic_times.append(time.monotonic())

    def _on_control_cmd(self, _msg: Control) -> None:
        self._control_cmd_times.append(time.monotonic())

    def _wait_for_sustained_rate(
        self,
        timestamps: collections.deque[float],
        min_hz: float,
        window_s: float,
        timeout_s: float,
    ) -> bool:
        """Block (spinning this node) until `timestamps` shows >= min_hz
        sustained over the trailing window_s seconds, or timeout_s elapses.
        Shared driver behind wait_localized and verify_control_flowing;
        sustained_rate_ok() above is the pure decision this loop polls."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            now = time.monotonic()
            while timestamps and now - timestamps[0] > window_s:
                timestamps.popleft()
            if sustained_rate_ok(timestamps, now, window_s, min_hz):
                return True
        return False

    def wait_localized(self, timeout_s: float) -> bool:
        """Block until LOCALIZED_TOPIC sustains >= LOCALIZED_MIN_HZ over a
        trailing LOCALIZED_WINDOW_S window, or timeout_s elapses."""
        return self._wait_for_sustained_rate(
            self._kinematic_times, LOCALIZED_MIN_HZ, LOCALIZED_WINDOW_S, timeout_s
        )

    def verify_control_flowing(self, timeout_s: float) -> bool:
        """R4.2: block until the GATED CONTROL_CMD_TOPIC sustains >=
        CONTROL_CMD_MIN_HZ over a trailing CONTROL_CMD_WINDOW_S window, or
        timeout_s elapses. This is the check that pins the regression that
        produced cell E's false conclusion: a near-silent gate (measured
        ~1.30 Hz) must fail here, before main() ever prints ARMED. See the
        module docstring's CONTROL_CMD_MIN_HZ comment for the threshold's
        justification."""
        return self._wait_for_sustained_rate(
            self._control_cmd_times, CONTROL_CMD_MIN_HZ, CONTROL_CMD_WINDOW_S, timeout_s
        )

    def _call_with_retries(self, client, request, service_name: str, timeout_s: float):
        """Call `client` with `request`, retrying every SERVICE_RETRY_PERIOD_S
        until response.status.success, up to timeout_s. Returns the
        successful response, or None on timeout."""
        if not client.wait_for_service(timeout_sec=timeout_s):
            self.get_logger().error(f"{service_name}: service never became available")
            return None
        deadline = time.monotonic() + timeout_s
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
            time.sleep(SERVICE_RETRY_PERIOD_S)
        return None

    def set_route(self, goal_x: float, goal_y: float, yaw_rad: float, timeout_s: float) -> bool:
        # Best-effort: a fresh stack has no route to clear, and a clear
        # failure must not block setting the new one (arm_closed_loop.sh's
        # own clear_route call is likewise not treated as fatal).
        clear_client = self.create_client(ClearRoute, "/api/routing/clear_route")
        if clear_client.wait_for_service(timeout_sec=2.0):
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
            time.sleep(0.1)
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
            time.sleep(ENGAGE_PUBLISH_PERIOD_S)
        self.get_logger().info(f"{ENGAGE_TOPIC}: published engage=true x{ENGAGE_PUBLISH_COUNT}")

    def engage(self, timeout_s: float) -> bool:
        """R4.1 + R4.2 orchestration. Returns verify_control_flowing()'s
        result -- NOT try_adapi_engage()'s or legacy_engage()'s reported
        success -- so a call that reports success while the gate is
        near-silent cannot reach ARMED through this function. That
        substitution (trusting a service response instead of the gated
        topic) is exactly the defect that produced cell E's false
        conclusion.

        timeout_s bounds the WHOLE phase, matching the "fresh timeout
        budget per step" contract documented at module scope: the AD-API
        attempt takes a fixed slice out of it (never in addition to it),
        and whatever remains goes to verify_control_flowing().
        """
        start = time.monotonic()
        adapi_budget = min(ADAPI_ENGAGE_ATTEMPT_TIMEOUT_S, timeout_s)
        self.try_adapi_engage(adapi_budget)
        self.legacy_engage()
        remaining = max(0.0, timeout_s - (time.monotonic() - start))
        return self.verify_control_flowing(remaining)


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
                f"ARM FAIL: {CONTROL_CMD_TOPIC} never sustained {CONTROL_CMD_MIN_HZ:.0f} Hz "
                f"within {args.timeout:.0f} s after engage (see step-11_6-adapi-engage and "
                "R4.2 -- a service reporting success is not enough)"
            )
            return EXIT_TIMEOUT

        print(f"ARMED: localized, route set to ({goal_x:.3f}, {goal_y:.3f}), autonomous engaged")
        return EXIT_ARMED
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
