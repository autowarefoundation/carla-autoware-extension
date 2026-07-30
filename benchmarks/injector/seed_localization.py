#!/usr/bin/env python3
"""Seed localization through `/localization/initialize` -- the ONE bring-up
step every cell needs before `arm_and_goal.py` can do anything, because on
this Autoware image nothing else can initialize a fresh stack.

Runs INSIDE the cell's Autoware container (docker exec), using only rclpy and
message packages the container already provides -- no docker, no CARLA
PythonAPI, no host-side dependency -- exactly like `arm_and_goal.py`. The
caller supplies the map-frame pose (a cell launcher reads it from CARLA ground
truth, host-side, since only the launcher has a simulator client).

WHY THIS SERVICE AND NOT THE TWO OBVIOUS ALTERNATIVES. Both were tried live on
cell B and both fail on this image (Autoware 0.50.0, universe-devel-cuda;
Task 13, `benchmarks/results/B/run-002` and `run-003`):

1. **Autoware's own `autoware_automatic_pose_initializer`** calls AD-API
   `/api/localization/initialize` every 1-3 s for as long as localization is
   uninitialized. Every call was REFUSED for the whole budget:

       [ERROR] [system.service_log_checker]: /api/localization/initialize:
         status code 1 'The vehicle is not stopped.'

   That is a DEADLOCK, not a statement about the ego. The AD-API's stop check
   is `autoware::motion_utils::VehicleStopChecker`, which reads
   `/localization/kinematic_state` -- the EKF output that only exists once
   localization HAS initialized (an rclpy probe counted 0 messages on it while
   the refusals repeated). MEASURED against the alternative explanation: the
   ego was stationary to 3.7e-12 m/s on `/vehicle/status/velocity_status`
   (n=283 over 15 s) and exactly 0.0 on
   `/sensing/vehicle_velocity_converter/twist_with_covariance` (n=238), so
   `pose_initializer`'s OWN stop check -- which reads that converter twist --
   would pass. The refusal is the AD-API's, on a topic that cannot exist yet.

2. **Publishing `/initialpose`** (what `scripts/e2e/reseed_localization.py`
   does, the extension harness's proven re-seed) does not reach
   `pose_initializer` on this image AT ALL: `ros2 node info
   /localization/util/pose_initializer` lists its subscriptions as
   `/sensing/gnss/pose_with_covariance` and
   `/sensing/vehicle_velocity_converter/twist_with_covariance` -- and nothing
   else. `/initialpose` has exactly one subscriber, and it is not that node;
   on the evidence above it is the AD-API's RViz adapter, i.e. route 1 again.
   Seeding that topic was tried live and produced no `pose_estimator/pose` at
   all (7 attempts, `run-003`).

`/localization/initialize` is `pose_initializer`'s OWN service server
(`autoware_localization_msgs/srv/InitializeLocalization`, seen in that same
`ros2 node info`), it takes the pose directly, and its stop check is the
converter-twist one that the measurement above shows passing. That is why this
script calls it.

**Caution for the extension cells (Task 20):** cell A's image carries the same
package versions (autoware_universe_utils / autoware_vehicle_cmd_gate /
autoware_pointcloud_preprocessor 0.50.0, autoware_internal_msgs 1.12.1), so
the same two failures are very likely there too -- but that has NOT been
measured on cell A, and this note is not a claim that it has.

Usage (inside the `autoware` container, overlay sourced, ROS_DOMAIN_ID=0):

    python3 /work/benchmarks/injector/seed_localization.py \\
        --pose X Y Z YAW_RAD [--timeout 120]

X, Y, Z are map-frame metres and YAW_RAD is map-frame radians. Exit 0 once the
NDT pose converges within CONVERGED_TOLERANCE_M of the seed, exit 2 on timeout
(the service never reported success, or NDT never converged).
"""

from __future__ import annotations

import argparse
import math
import sys
import time

import rclpy
from autoware_localization_msgs.srv import InitializeLocalization
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from rclpy.node import Node

INITIALIZE_SERVICE = "/localization/initialize"
# The NDT pose, not the EKF-fused kinematic_state: this checks that the SCAN
# MATCHER locked, which is what a seed either achieves or does not. The fused
# state comes up afterwards and the launcher waits on it separately.
NDT_POSE_TOPIC = "/localization/pose_estimator/pose"
# Same 1.0 m criterion scripts/e2e/reseed_localization.py uses for a re-seed,
# so "locked" means the same thing on both paths. Engineering judgment
# inherited from that script, not an independently measured constant.
CONVERGED_TOLERANCE_M = 1.0
SERVICE_RETRY_PERIOD_S = 2.0
SPIN_SLICE_S = 0.1

# The covariance scripts/e2e/reseed_localization.py sends, kept identical so a
# seed and a re-seed present NDT with the same search basin: 0.25 m^2 on x/y,
# 0.01 on z/roll/pitch, 0.068 rad^2 on yaw.
SEED_COVARIANCE = {0: 0.25, 7: 0.25, 14: 0.01, 21: 0.01, 28: 0.01, 35: 0.068}

EXIT_OK = 0
EXIT_TIMEOUT = 2


def converged(ndt_xy, target_xy, tolerance_m: float = CONVERGED_TOLERANCE_M) -> bool:
    """True when the NDT pose is within `tolerance_m` of the seed target.

    `ndt_xy` is None until the scan matcher publishes at all, which is the
    normal state of an un-initialized stack -- so "no pose yet" is NOT
    convergence. Pure, so the criterion is testable without rclpy.
    """
    if ndt_xy is None:
        return False
    return math.hypot(ndt_xy[0] - target_xy[0], ndt_xy[1] - target_xy[1]) <= tolerance_m


def seed_pose_msg(x: float, y: float, z: float, yaw_rad: float) -> PoseWithCovarianceStamped:
    """The seed pose, frame_id `map`, yaw-only quaternion -- the same
    (sin(yaw/2), cos(yaw/2)) convention as arm_and_goal.py and
    scripts/e2e/reseed_localization.py."""
    msg = PoseWithCovarianceStamped()
    msg.header.frame_id = "map"
    msg.pose.pose.position.x = x
    msg.pose.pose.position.y = y
    msg.pose.pose.position.z = z
    msg.pose.pose.orientation.z = math.sin(yaw_rad / 2.0)
    msg.pose.pose.orientation.w = math.cos(yaw_rad / 2.0)
    covariance = [0.0] * 36
    for index, value in SEED_COVARIANCE.items():
        covariance[index] = value
    msg.pose.covariance = covariance
    return msg


class SeedLocalization(Node):
    def __init__(self):
        super().__init__("seed_localization")
        self._ndt_xy: tuple[float, float] | None = None
        self.create_subscription(PoseStamped, NDT_POSE_TOPIC, self._on_ndt, 10)
        self._client = self.create_client(InitializeLocalization, INITIALIZE_SERVICE)

    def _on_ndt(self, msg: PoseStamped) -> None:
        self._ndt_xy = (msg.pose.position.x, msg.pose.position.y)

    def _spin_for(self, duration_s: float) -> None:
        """Spin rather than sleep, for arm_and_goal.py's reason: a blind sleep
        lets the NDT subscription queue and then drain in a burst, and here it
        would also stall the service future."""
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            rclpy.spin_once(
                self, timeout_sec=max(0.0, min(SPIN_SLICE_S, deadline - time.monotonic()))
            )

    def _service_ready(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._client.service_is_ready():
                return True
            rclpy.spin_once(self, timeout_sec=SPIN_SLICE_S)
        return self._client.service_is_ready()

    def seed(self, x: float, y: float, z: float, yaw_rad: float, timeout_s: float) -> bool:
        """Call INITIALIZE_SERVICE with the pose, retrying until it reports
        success, then wait for NDT to converge -- all inside ONE timeout_s
        budget, so the caller's bound is the whole phase (arm_and_goal.py's
        `_call_with_retries` contract)."""
        deadline = time.monotonic() + timeout_s
        request = InitializeLocalization.Request()
        request.pose_with_covariance = [seed_pose_msg(x, y, z, yaw_rad)]
        if not self._service_ready(max(0.0, deadline - time.monotonic())):
            self.get_logger().error(f"{INITIALIZE_SERVICE}: service never became available")
            return False

        accepted = False
        while time.monotonic() < deadline:
            future = self._client.call_async(request)
            rclpy.spin_until_future_complete(
                self, future, timeout_sec=max(0.1, deadline - time.monotonic())
            )
            response = future.result()
            if response is not None and response.status.success:
                accepted = True
                break
            reason = (
                response.status.message if response is not None else "no response (spin timed out)"
            )
            self.get_logger().warning(f"{INITIALIZE_SERVICE}: not yet ok ({reason}); retrying")
            self._spin_for(min(SERVICE_RETRY_PERIOD_S, max(0.0, deadline - time.monotonic())))
        if not accepted:
            return False

        target = (x, y)
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=SPIN_SLICE_S)
            if converged(self._ndt_xy, target):
                return True
        self.get_logger().error(
            f"{INITIALIZE_SERVICE} succeeded but {NDT_POSE_TOPIC} "
            f"{'never published' if self._ndt_xy is None else f'stayed at {self._ndt_xy}'}"
        )
        return False


def build_arg_parser() -> argparse.ArgumentParser:
    """Split out from main() so the CLI surface is unit-testable without rclpy."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--pose",
        nargs=4,
        type=float,
        required=True,
        metavar=("X", "Y", "Z", "YAW_RAD"),
        help="map-frame seed pose: x, y, z (metres) and yaw (radians)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        metavar="S",
        help="whole-phase timeout in seconds (service + NDT convergence), default 120",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    x, y, z, yaw = args.pose

    rclpy.init()
    node = SeedLocalization()
    try:
        node.get_logger().info(
            f"seeding {INITIALIZE_SERVICE} at ({x:.3f}, {y:.3f}, {z:.3f}) "
            f"yaw={math.degrees(yaw):.2f} deg (timeout {args.timeout:.0f} s)"
        )
        if not node.seed(x, y, z, yaw, args.timeout):
            print(
                f"SEED FAIL: localization did not initialize within {args.timeout:.0f} s "
                f"({INITIALIZE_SERVICE} never succeeded, or {NDT_POSE_TOPIC} never came "
                f"within {CONVERGED_TOLERANCE_M:.1f} m of the seed)"
            )
            return EXIT_TIMEOUT
        print(f"SEEDED: NDT locked within {CONVERGED_TOLERANCE_M:.1f} m of ({x:.3f}, {y:.3f})")
        return EXIT_OK
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
