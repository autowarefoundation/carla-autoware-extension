import rclpy, time
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import TwistWithCovarianceStamped
from autoware_vehicle_msgs.msg import VelocityReport
qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                 durability=DurabilityPolicy.VOLATILE,
                 history=HistoryPolicy.KEEP_LAST, depth=10)
rclpy.init(); n = Node("vel_probe")
vs, tw = [], []
n.create_subscription(VelocityReport, "/vehicle/status/velocity_status",
                      lambda m: vs.append((m.longitudinal_velocity, m.lateral_velocity, m.heading_rate)), qos)
n.create_subscription(TwistWithCovarianceStamped,
                      "/sensing/vehicle_velocity_converter/twist_with_covariance",
                      lambda m: tw.append(m.twist.twist.linear.x), qos)
end = time.time() + 15.0
while time.time() < end:
    rclpy.spin_once(n, timeout_sec=0.2)
print(f"velocity_status n={len(vs)}")
if vs:
    lo = [abs(a) for a, _, _ in vs]
    print(f"  |longitudinal| min={min(lo):.6g} max={max(lo):.6g} mean={sum(lo)/len(lo):.6g}")
    print(f"  first 5: {vs[:5]}")
print(f"converter twist n={len(tw)}")
if tw:
    print(f"  |x| min={min(abs(v) for v in tw):.6g} max={max(abs(v) for v in tw):.6g}")
    print(f"  first 5: {[round(v,6) for v in tw[:5]]}")
rclpy.shutdown()
