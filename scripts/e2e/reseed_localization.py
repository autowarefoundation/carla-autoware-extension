#!/usr/bin/env python3
"""Re-seed /initialpose programmatically and wait for NDT to re-lock (runs IN the container).

Why a script and not `ros2 topic pub`: publishing a PoseWithCovarianceStamped with an
inline-YAML 36-entry covariance silently mangles the array (the CLI parser fails at a caret
without surfacing an error through the pipeline), so the seed never takes. An rclpy publisher
is reliable, and the convergence watch below turns "did NDT actually re-lock?" into an exit
code instead of eyeballing.

Operationally: NDT drifts while PARKED (an idle stack slides off by metres and can capture a
mirrored basin), so re-seed immediately before arming a drive and do not trust a lock that
has been idling. See docs/e2e-report.md "Operational findings from the reroute campaign".

Usage (inside the `autoware` container, overlay sourced, ROS_DOMAIN_ID=0):

    python3 /work/scripts/e2e/reseed_localization.py X Y Z QZ QW [TIMEOUT_S]

Exit 0 once the NDT pose converges within 1.0 m of the target, 1 on timeout.
"""

import math
import sys
import time

import rclpy
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from rclpy.node import Node

X, Y, Z, QZ, QW = (float(a) for a in sys.argv[1:6])
TIMEOUT = float(sys.argv[6]) if len(sys.argv) > 6 else 40.0

rclpy.init()
n = Node("reseed")
pub = n.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
state = {}


def yaw_of(q):
    return math.degrees(math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))


def on_ndt(m):
    state["ndt"] = (m.pose.position.x, m.pose.position.y, yaw_of(m.pose.orientation))


n.create_subscription(PoseStamped, "/localization/pose_estimator/pose", on_ndt, 10)

msg = PoseWithCovarianceStamped()
msg.header.frame_id = "map"
msg.pose.pose.position.x = X
msg.pose.pose.position.y = Y
msg.pose.pose.position.z = Z
msg.pose.pose.orientation.z = QZ
msg.pose.pose.orientation.w = QW
cov = [0.0] * 36
cov[0] = cov[7] = 0.25
cov[14] = cov[21] = cov[28] = 0.01
cov[35] = 0.068
msg.pose.covariance = cov

# Let discovery settle, then publish twice for safety.
end_warm = time.time() + 2.0
while time.time() < end_warm:
    rclpy.spin_once(n, timeout_sec=0.2)
pub.publish(msg)
time.sleep(0.5)
pub.publish(msg)
print(
    f"published /initialpose target=({X:.3f},{Y:.3f}) yaw={math.degrees(2 * math.atan2(QZ, QW)):.2f}"
)

end = time.time() + TIMEOUT
last_print = 0.0
locked = False
while time.time() < end:
    rclpy.spin_once(n, timeout_sec=0.3)
    if "ndt" in state and time.time() - last_print > 2.0:
        x, y, yaw = state["ndt"]
        d = math.hypot(x - X, y - Y)
        print(f"ndt: ({x:.2f},{y:.2f}) yaw={yaw:.1f} dist_to_target={d:.2f}")
        last_print = time.time()
        if d < 1.0:
            locked = True
            break
print("LOCKED" if locked else "NOT LOCKED")
sys.exit(0 if locked else 1)
