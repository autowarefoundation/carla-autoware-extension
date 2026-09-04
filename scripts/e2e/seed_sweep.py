#!/usr/bin/env python3
"""Re-seed NDT from a ring of initial poses and report the converged error.

The G1 root-cause discriminator: does NDT's map-frame bias depend on WHERE it
was seeded? This is the load-bearing evidence behind the Town10HD_Opt G1
verdict in docs/running-e2e.md, and Plan 2's fallback choice (re-register the
Town10 pcd, or move the primary duel to Nishi-Shinjuku) turns on its answer --
which is why it is a tracked script and not a scratch file.

Runs IN the `autoware` container, on a live stack. The ego stays PARKED at a
known CARLA ground-truth pose for the whole sweep, so the truth is a constant
and every seed is an independent convergence of the same scan against the same
map.

Why this is the decisive test. The G1 window measured dy>0 in 400/400 samples,
which looks overwhelming but is ONE convergence sampled 400 times -- n=1 in
independent draws. Both hypotheses predict it:

  H1 weak geometry -- a near-featureless local pcd leaves x/y in a shallow
     basin, so NDT stops wherever the seed put it and then stays there.
     PREDICTS: converged error varies with the seed.
  H2 pcd frame offset -- the pcd is translated relative to the map frame, so
     every scan matches at true+offset no matter where the search started.
     PREDICTS: the same bias from every seed, with small spread.

So the spread of converged dy ACROSS seeds is the discriminating statistic,
and its comparison against the within-lock jitter (std 0.188 m, measured in G1)
is what says whether any variation is real.

Usage (inside the container, overlay sourced, ROS_DOMAIN_ID=0; TRUE_* is the
parked ego's ground-truth pose in the MAP frame, as arm_closed_loop.sh prints
it):

    docker compose -f docker/compose.yaml exec -T autoware bash -lc \\
      'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash &&
       export ROS_DOMAIN_ID=0 &&
       python3 /work/scripts/e2e/seed_sweep.py TRUE_X TRUE_Y QZ QW'

Takes about 2 minutes (8 seeds x 14 s). Reads only /localization, publishes
only /initialpose, and leaves NDT seeded at the last entry in SEEDS.
"""

import sys
import time

import rclpy
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from rclpy.node import Node

TRUE_X, TRUE_Y, QZ, QW = (float(a) for a in sys.argv[1:5])

# Seeds spread well beyond the observed bias so a basin, if shallow, is entered
# from genuinely different places; (0,0) repeated last is the repeatability
# control -- it must reproduce the first (0,0) result.
SEEDS = [
    (0.0, 0.0),
    (2.0, 0.0),
    (-2.0, 0.0),
    (0.0, 2.0),
    (0.0, -2.0),
    (1.5, 1.5),
    (-1.5, -1.5),
    (0.0, 0.0),
]

SETTLE_S = 10.0  # let NDT converge after the seed
SAMPLE_S = 4.0  # then average the lock


def main() -> int:
    rclpy.init()
    n = Node("seed_sweep")
    pub = n.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
    latest = {}
    n.create_subscription(
        PoseStamped,
        "/localization/pose_estimator/pose",
        lambda m: latest.update(p=(m.pose.position.x, m.pose.position.y)),
        10,
    )

    def spin(seconds):
        end = time.time() + seconds
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(n, timeout_sec=0.05)

    print(f"truth ({TRUE_X:.3f}, {TRUE_Y:.3f}); {len(SEEDS)} seeds")
    print(f"{'seed_dx':>8} {'seed_dy':>8} {'n':>4} {'err_dx':>8} {'err_dy':>8}")
    rows = []
    for sdx, sdy in SEEDS:
        m = PoseWithCovarianceStamped()
        m.header.frame_id = "map"
        m.header.stamp = n.get_clock().now().to_msg()
        m.pose.pose.position.x = TRUE_X + sdx
        m.pose.pose.position.y = TRUE_Y + sdy
        m.pose.pose.orientation.z = QZ
        m.pose.pose.orientation.w = QW
        cov = [0.0] * 36
        cov[0] = cov[7] = 0.25
        cov[35] = 0.06
        m.pose.covariance = cov
        pub.publish(m)

        spin(SETTLE_S)
        xs, ys = [], []
        end = time.time() + SAMPLE_S
        while time.time() < end and rclpy.ok():
            rclpy.spin_once(n, timeout_sec=0.05)
            if "p" in latest:
                xs.append(latest["p"][0])
                ys.append(latest["p"][1])
        if not xs:
            print(f"{sdx:8.2f} {sdy:8.2f} {0:4d} {'NO NDT':>8} {'NO NDT':>8}")
            continue
        ex = sum(xs) / len(xs) - TRUE_X
        ey = sum(ys) / len(ys) - TRUE_Y
        rows.append((sdx, sdy, ex, ey))
        print(f"{sdx:8.2f} {sdy:8.2f} {len(xs):4d} {ex:+8.3f} {ey:+8.3f}")

    if len(rows) >= 2:
        exs = [r[2] for r in rows]
        eys = [r[3] for r in rows]

        def stats(v):
            mu = sum(v) / len(v)
            sd = (sum((x - mu) ** 2 for x in v) / len(v)) ** 0.5
            return mu, sd, min(v), max(v)

        mx, sx, lox, hix = stats(exs)
        my, sy, loy, hiy = stats(eys)
        print(f"\nACROSS {len(rows)} SEEDS")
        print(f"  err_dx mean {mx:+.3f}  std {sx:.3f}  range [{lox:+.3f}, {hix:+.3f}]")
        print(f"  err_dy mean {my:+.3f}  std {sy:.3f}  range [{loy:+.3f}, {hiy:+.3f}]")
        print("  within-lock jitter measured in G1: std 0.188 m (the comparison baseline)")
        print(
            "  H2 (pcd offset) if across-seed std << seed spread and dy stays ~+0.48;\n"
            "  H1 (shallow basin) if converged dy tracks the seed."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
