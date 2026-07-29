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
  4. ChangeOperationMode -> /api/operation_mode/change_to_autonomous (the
     AD-API-documented engage call). NOTE: this differs from
     gate_g2_closed_loop.sh's current engage path, which publishes
     `/autoware/engage {engage: true}` on the legacy vehicle-level topic
     instead; that script was not changed by this task, and this path has
     not been live-verified end to end (see task-7-report.md's Concerns).
     The codebase does NOT treat the two engage paths as interchangeable
     already -- arm_closed_loop.sh's --disarm calls BOTH the AD-API
     change_to_stop service AND publishes /autoware/engage false -- so do
     not assume this call alone is sufficient on the first live run.

     HANDOVER for whoever runs the first live gate (Tasks 10/11/13): after
     engage() reports status.success, do not stop there -- verify
     /control/command/control_cmd (the GATED output vehicle_cmd_gate
     actually sends, not /control/trajectory_follower/control_cmd, the raw
     planner output) is flowing and nonzero, reusing arm_closed_loop.sh's
     own step-6 raw-vs-gated comparison. If /control/command/control_cmd
     stays suppressed after a successful change_to_autonomous response,
     this AD-API path is not enough on its own and needs a fallback:
     publish /autoware/engage {engage: true} the way gate_g2_closed_loop.sh
     does, in addition to (not instead of) the service call above.

  Steps 3 and 4 each retry every 2 s until their service reports
  status.success, up to --timeout seconds (a fresh timeout budget per step,
  matching "retrying each up to --timeout").

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
timeout (localization never sustained 5 Hz, or a service never reported
success) within --timeout.
"""

from __future__ import annotations

import argparse
import collections
import math
import sys
import time

import rclpy
from autoware_adapi_v1_msgs.srv import ChangeOperationMode, ClearRoute, SetRoutePoints
from nav_msgs.msg import Odometry
from rclpy.node import Node

LOCALIZED_TOPIC = "/localization/kinematic_state"
LOCALIZED_WINDOW_S = 5.0
LOCALIZED_MIN_HZ = 5.0
SERVICE_RETRY_PERIOD_S = 2.0

EXIT_ARMED = 0
EXIT_TIMEOUT = 2


def recent_count(timestamps, now: float, window_s: float) -> int:
    """Count of `timestamps` within [now - window_s, now].

    Pure so the "sustained >= 5 Hz over a trailing window" rule is
    unit-testable without rclpy or a live topic (tests/benchmarks/
    test_arm_and_goal.py); wait_localized() below is this function plus the
    rclpy spin loop that keeps `timestamps` current, not a re-implementation
    of it.
    """
    return sum(1 for t in timestamps if now - t <= window_s)


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

    def _on_kinematic_state(self, _msg: Odometry) -> None:
        self._kinematic_times.append(time.monotonic())

    def wait_localized(self, timeout_s: float) -> bool:
        """Block (spinning this node) until LOCALIZED_TOPIC has delivered
        >= LOCALIZED_MIN_HZ * LOCALIZED_WINDOW_S messages within the
        trailing LOCALIZED_WINDOW_S seconds, or timeout_s elapses."""
        deadline = time.monotonic() + timeout_s
        min_count = LOCALIZED_MIN_HZ * LOCALIZED_WINDOW_S
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            now = time.monotonic()
            while self._kinematic_times and now - self._kinematic_times[0] > LOCALIZED_WINDOW_S:
                self._kinematic_times.popleft()
            if recent_count(self._kinematic_times, now, LOCALIZED_WINDOW_S) >= min_count:
                return True
        return False

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

    def engage(self, timeout_s: float) -> bool:
        client = self.create_client(ChangeOperationMode, "/api/operation_mode/change_to_autonomous")
        return (
            self._call_with_retries(
                client, ChangeOperationMode.Request(), "change_to_autonomous", timeout_s
            )
            is not None
        )


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
            print(f"ARM FAIL: change_to_autonomous did not succeed within {args.timeout:.0f} s")
            return EXIT_TIMEOUT

        print(f"ARMED: localized, route set to ({goal_x:.3f}, {goal_y:.3f}), autonomous engaged")
        return EXIT_ARMED
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
