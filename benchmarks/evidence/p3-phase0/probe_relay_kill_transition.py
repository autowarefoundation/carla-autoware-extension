"""P4/P3 across the relay kill, on a subscriber that is ALREADY discovered.

Written for P3 Phase 0 fix round 2. It exists because two instrument confounds
made the brief's own `ros2 topic hz` post-kill readings unsafe to report on
cell B, and both are properties of that cell rather than of the phenomenon:

1. FRESH-NODE DISCOVERY. `ros2 topic hz` builds a brand-new node and starts
   discovering when it starts. Phase 0 already measured that on cell B
   (`rmw_fastrtps_cpp`, shared memory OFF) a freshly started CLI graph query
   under-reports for a long time -- a `--no-daemon` census returned nothing,
   then one publisher with `_NODE_NAME_UNKNOWN_`, while the relay was
   demonstrably alive. So a post-kill `topic hz` that prints NOTHING is
   ambiguous: it can mean "NDT stopped" or "this node never discovered NDT".
   Those are opposite conclusions and the tool cannot tell them apart.
2. SIGTERM LATENCY ON THE RECORDED PID. `/tmp/tier4-concat-relay.pid` records
   the pid of the `ros2 run topic_tools relay ...` WRAPPER. Measured live on
   `results/B/run-026`: three seconds after `kill`, `kill -0` reported the pid
   still alive. A post-kill measurement started on a fixed sleep can therefore
   be taken while the relay is still publishing.

This probe removes both. It subscribes FIRST and holds the subscription across
the kill, so discovery is established while the relay is still up and the same
subscriber sees both regimes; and it performs the kill itself, confirming the
process is actually gone (escalating SIGTERM -> SIGKILL) before it labels any
sample "post-kill". Rates are reported in fixed buckets so the transition is
visible rather than averaged away.

It also answers P3 without `ros2 topic echo --once --no-daemon`, which failed
twice on cell B with "Could not determine the type for the passed topic" -- the
same discovery problem as (1). The first cloud that arrives on RELAY_OUT after
the relay is confirmed dead is by construction a `concatenate_data` cloud, and
this probe prints its full structural metadata: frame_id, height, width,
point_step, row_step, is_dense and the field layout. That is exactly the
"non-empty clouds, sane width/point_step/frame" P3 asks for.

NOTHING HERE MOVES A THRESHOLD. The pre-declared recovery criterion is
unchanged and is not evaluated in this file: it is >= 9.0 Hz sustained
(0.9 x cell B's registered `ndt_expected_hz: 10.0`), and this probe only
reports measured rates for the adjudication to read.

Run INSIDE the Autoware container:

    docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash &&
      source /opt/autoware/setup.bash &&
      python3 /work/benchmarks/evidence/p3-phase0/probe_relay_kill_transition.py'
"""

from __future__ import annotations

import argparse
import os
import signal
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from geometry_msgs.msg import PoseWithCovarianceStamped
from sensor_msgs.msg import PointCloud2

NDT_TOPIC = "/localization/pose_estimator/pose_with_covariance"
RELAY_OUT = "/sensing/lidar/concatenated/pointcloud"
RELAY_PIDFILE = "/tmp/tier4-concat-relay.pid"


def best_effort(depth: int) -> QoSProfile:
    return QoSProfile(
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=depth,
        durability=QoSDurabilityPolicy.VOLATILE,
    )


def reliable(depth: int) -> QoSProfile:
    return QoSProfile(
        reliability=QoSReliabilityPolicy.RELIABLE,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=depth,
        durability=QoSDurabilityPolicy.VOLATILE,
    )


class Probe(Node):
    def __init__(self) -> None:
        super().__init__("probe_relay_kill_transition")
        self.ndt: list[float] = []
        self.clouds: list[float] = []
        self.first_post_kill_cloud: PointCloud2 | None = None
        self.kill_time: float | None = None
        # NDT's pose output is RELIABLE on this stack; the cloud topics are
        # BEST_EFFORT (measured in P1's `topic info -v`). Subscribing with the
        # wrong reliability matches nothing and silently records zero, which
        # would look exactly like the phenomenon under test.
        self.create_subscription(PoseWithCovarianceStamped, NDT_TOPIC, self._on_ndt, reliable(100))
        self.create_subscription(PointCloud2, RELAY_OUT, self._on_cloud, best_effort(100))

    def _on_ndt(self, _msg: PoseWithCovarianceStamped) -> None:
        self.ndt.append(time.monotonic())

    def _on_cloud(self, msg: PointCloud2) -> None:
        now = time.monotonic()
        self.clouds.append(now)
        if self.kill_time is not None and now > self.kill_time and self.first_post_kill_cloud is None:
            self.first_post_kill_cloud = msg


def rate(stamps: list[float], lo: float, hi: float) -> tuple[int, float]:
    n = [t for t in stamps if lo <= t < hi]
    span = hi - lo
    return len(n), (len(n) / span if span > 0 else float("nan"))


def kill_relay() -> None:
    pid = int(open(RELAY_PIDFILE).read().strip())
    print(f"relay pidfile records pid {pid}; sending SIGTERM")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("  already gone")
        return
    for _ in range(20):
        time.sleep(0.25)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            print("  relay pid is gone after SIGTERM")
            return
    # See confound (2) in the module docstring: measured surviving SIGTERM for
    # >3 s on run-026. Escalate rather than mislabel live samples "post-kill".
    print("  STILL ALIVE after 5 s of SIGTERM; escalating to SIGKILL")
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    for _ in range(20):
        time.sleep(0.25)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            print("  relay pid is gone after SIGKILL")
            return
    print("  WARNING: relay pid STILL alive; post-kill labels below are NOT trustworthy")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pre-s", type=float, default=12.0, help="seconds observed before the kill")
    ap.add_argument("--post-s", type=float, default=35.0, help="seconds observed after the kill")
    ap.add_argument("--bucket-s", type=float, default=5.0)
    args = ap.parse_args()

    rclpy.init()
    node = Probe()
    t0 = time.monotonic()
    print(f"subscribed; observing {args.pre_s:.0f} s PRE-kill (discovery settles here)")
    while time.monotonic() - t0 < args.pre_s:
        rclpy.spin_once(node, timeout_sec=0.05)

    print(f"\n=== KILLING THE RELAY at t+{time.monotonic() - t0:.1f}s ===")
    kill_relay()
    node.kill_time = time.monotonic()
    kill_rel = node.kill_time - t0

    while time.monotonic() - t0 < args.pre_s + args.post_s:
        rclpy.spin_once(node, timeout_sec=0.05)
    end = time.monotonic()

    print("\n=== NDT OUTPUT RATE, bucketed (topic: %s) ===" % NDT_TOPIC)
    print(f"{'window (s rel. start)':<26}{'regime':<12}{'msgs':>6}{'Hz':>10}")
    edges = []
    t = 0.0
    while t < args.pre_s + args.post_s:
        edges.append((t, min(t + args.bucket_s, args.pre_s + args.post_s)))
        t += args.bucket_s
    for lo, hi in edges:
        regime = "PRE-kill" if hi <= kill_rel else ("POST-kill" if lo >= kill_rel else "spans kill")
        n, hz = rate(node.ndt, t0 + lo, t0 + hi)
        print(f"{f'[{lo:5.1f}, {hi:5.1f})':<26}{regime:<12}{n:>6}{hz:>10.3f}")

    n_pre, hz_pre = rate(node.ndt, t0, t0 + kill_rel)
    n_post, hz_post = rate(node.ndt, node.kill_time, end)
    c_pre, chz_pre = rate(node.clouds, t0, t0 + kill_rel)
    c_post, chz_post = rate(node.clouds, node.kill_time, end)
    print("\n=== SUMMARY ===")
    print(f"NDT   PRE-kill  : {n_pre:4d} msgs over {kill_rel:5.1f} s = {hz_pre:6.3f} Hz")
    print(f"NDT   POST-kill : {n_post:4d} msgs over {end - node.kill_time:5.1f} s = {hz_post:6.3f} Hz")
    print(f"CLOUD PRE-kill  : {c_pre:4d} msgs over {kill_rel:5.1f} s = {chz_pre:6.3f} Hz")
    print(f"CLOUD POST-kill : {c_post:4d} msgs over {end - node.kill_time:5.1f} s = {chz_post:6.3f} Hz")

    print("\n=== P3: FIRST CLOUD ON RELAY_OUT AFTER THE RELAY IS CONFIRMED DEAD ===")
    print("(by construction a concatenate_data cloud: it is the only publisher left)")
    msg = node.first_post_kill_cloud
    if msg is None:
        print("NONE RECEIVED: no cloud arrived on RELAY_OUT after the kill.")
    else:
        print(f"header.frame_id : {msg.header.frame_id!r}")
        print(f"header.stamp    : {msg.header.stamp.sec}.{msg.header.stamp.nanosec:09d}")
        print(f"height          : {msg.height}")
        print(f"width           : {msg.width}")
        print(f"point_step      : {msg.point_step}")
        print(f"row_step        : {msg.row_step}")
        print(f"is_dense        : {msg.is_dense}")
        print(f"is_bigendian    : {msg.is_bigendian}")
        print(f"data length     : {len(msg.data)} bytes")
        print(f"fields          : {[(f.name, f.offset, f.datatype, f.count) for f in msg.fields]}")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
