import rclpy, time
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import TwistWithCovarianceStamped
T = "/sensing/vehicle_velocity_converter/twist_with_covariance"
rclpy.init(); n = Node("comp_probe")
rows = []
n.create_subscription(TwistWithCovarianceStamped, T,
    lambda m: rows.append((m.twist.twist.linear.x, m.twist.twist.linear.y, m.twist.twist.linear.z,
                           m.twist.twist.angular.z)),
    QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE,
               history=HistoryPolicy.KEEP_LAST, depth=20))
end = time.time() + 10.0
while time.time() < end:
    rclpy.spin_once(n, timeout_sec=0.2)
print(f"n={len(rows)}")
if rows:
    import math
    sq = [x*x + y*y + z*z for x, y, z, _ in rows]
    print(f"linear (x,y,z) first: {rows[0][:3]}")
    print(f"|v| min={math.sqrt(min(sq)):.6g} max={math.sqrt(max(sq)):.6g}  threshold=1e-3")
    print(f"over_threshold={sum(1 for s in sq if s > 1e-6)}/{len(sq)}")
    print(f"angular.z first={rows[0][3]:.6g}")
rclpy.shutdown()
