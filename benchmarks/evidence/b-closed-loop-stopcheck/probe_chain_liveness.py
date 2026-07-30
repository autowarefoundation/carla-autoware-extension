import rclpy, time
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import PointCloud2
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from nav_msgs.msg import Odometry

TOPICS = [
    ("/sensing/lidar/top/pointcloud_raw_ex", PointCloud2),
    ("/sensing/lidar/top/self_cropped/pointcloud_ex", PointCloud2),
    ("/sensing/lidar/top/mirror_cropped/pointcloud_ex", PointCloud2),
    ("/sensing/lidar/top/pointcloud_before_sync", PointCloud2),
    ("/sensing/lidar/concatenated/pointcloud", PointCloud2),
    ("/localization/util/measurement_range/pointcloud", PointCloud2),
    ("/localization/util/voxel_grid_downsample/pointcloud", PointCloud2),
    ("/localization/util/downsample/pointcloud", PointCloud2),
    ("/localization/pose_estimator/pose", PoseStamped),
    ("/localization/pose_estimator/pose_with_covariance", PoseWithCovarianceStamped),
    ("/localization/kinematic_state", Odometry),
    ("/sensing/gnss/pose_with_covariance", PoseWithCovarianceStamped),
]
qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                 durability=DurabilityPolicy.VOLATILE,
                 history=HistoryPolicy.KEEP_LAST, depth=5)
rclpy.init()
n = Node("bench_probe")
counts = {t: 0 for t, _ in TOPICS}
frames = {}
def mk(t):
    def cb(m):
        counts[t] += 1
        h = getattr(m, "header", None)
        if h is not None and t not in frames:
            frames[t] = h.frame_id
    return cb
for t, ty in TOPICS:
    n.create_subscription(ty, t, mk(t), qos)
end = time.time() + 15.0
while time.time() < end:
    rclpy.spin_once(n, timeout_sec=0.2)
for t, _ in TOPICS:
    print(f"{counts[t]:5d}  {t}  frame={frames.get(t, '-')}")
rclpy.shutdown()
