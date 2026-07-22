#include "GnssPosePublisher.h"

#include <cstdint>
#include <vector>

#include <builtin_interfaces/msg/time.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>

#include "carla/autoware/geo/MgrsOffset.h"
#include "carla/autoware/messages/RosIdl.h"

namespace carla {
namespace autoware {

// AWSIM GNSS QoS: RELIABLE / VOLATILE / KEEP_LAST depth 1 (same encoding as the
// status publishers; CarlaRos2Extension.h documents the field meanings --
// reliability 0 = reliable, durability 0 = volatile, history_depth clamped>=1).
static CarlaRos2Qos GnssQos() { return CarlaRos2Qos{/*reliability=*/0u, /*durability=*/0u,
                                                    /*history_depth=*/1u}; }

void GnssPosePublisher::Init(const CarlaRos2Host& host) {
  host_ = host;
  using geometry_msgs::msg::PoseStamped;
  using geometry_msgs::msg::PoseWithCovarianceStamped;
  // create_publisher takes `const CarlaRos2Qos*`; bind an lvalue whose lifetime
  // spans both synchronous calls (never pass the address of a temporary).
  const CarlaRos2Qos qos = GnssQos();
  pose_ = host_.create_publisher(host_.host_ctx, "/sensing/gnss/pose",
                                 dds_type_name<PoseStamped>(),
                                 rihs01_hash<PoseStamped>().c_str(), &qos);
  pose_cov_ = host_.create_publisher(host_.host_ctx, "/sensing/gnss/pose_with_covariance",
                                     dds_type_name<PoseWithCovarianceStamped>(),
                                     rihs01_hash<PoseWithCovarianceStamped>().c_str(), &qos);
}

void GnssPosePublisher::OnVehicleStatus(const CarlaRos2VehicleStatusView& v) {
  // 1 Hz decimation, RELOAD-SAFE. Publish when >= 1 s has elapsed since the last
  // publish, OR when the clock ran BACKWARDS (t < last_pub_s_). An episode reload
  // restarts the ROS 2 sim clock from ~0 while last_pub_s_ still holds a large
  // pre-reload value; a plain `t - last < 1.0` guard would then suppress every
  // frame until the clock re-climbed past the stale value (a multi-second stall,
  // or forever if the episode is shorter). Treating a backwards jump as a fresh
  // start avoids that. The -1.0 sentinel makes the very first frame publish.
  const double t = v.sim_time_s;
  const bool should_publish = (t < last_pub_s_) || (t - last_pub_s_ >= 1.0);
  if (!should_publish) {
    return;
  }
  last_pub_s_ = t;

  const auto [mx, my, mz] = world_to_mgrs_local(v.transform.x_cm, v.transform.y_cm,
                                                v.transform.z_cm);
  // Orientation: conjugate the ego quaternion by the SAME Y-flip the position
  // uses (MgrsOffset.h owns the sign rule and its derivation).
  const auto [qx, qy, qz, qw] = carla_quat_to_mgrs(v.transform.qx, v.transform.qy, v.transform.qz,
                                                   v.transform.qw);

  // geometry_msgs/PoseStamped in the `map` frame; the frame is publisher
  // policy, set explicitly on the message header.
  geometry_msgs::msg::PoseStamped ps;
  ps.header.stamp.sec = static_cast<int32_t>(t);
  ps.header.stamp.nanosec =
      static_cast<uint32_t>((t - static_cast<double>(ps.header.stamp.sec)) * 1e9);
  ps.header.frame_id = "map";
  ps.pose.position.x = mx;
  ps.pose.position.y = my;
  ps.pose.position.z = mz;
  ps.pose.orientation.x = qx;
  ps.pose.orientation.y = qy;
  ps.pose.orientation.z = qz;
  ps.pose.orientation.w = qw;

  std::vector<uint8_t> buf;
  cdr_serialize(ps, buf);
  host_.publish(host_.host_ctx, pose_, buf.data(), buf.size());

  // PoseWithCovarianceStamped shares header + pose; the float64[36] row-major
  // covariance gets a small diagonal (x,y,z, roll,pitch,yaw) marking the pose
  // trustworthy-but-not-perfect; off-diagonal terms are zero.
  geometry_msgs::msg::PoseWithCovarianceStamped pc;
  pc.header = ps.header;
  pc.pose.pose = ps.pose;
  const double diag[6] = {0.1, 0.1, 0.1, 0.05, 0.05, 0.05};
  for (int row = 0; row < 6; ++row) {
    for (int col = 0; col < 6; ++col) {
      pc.pose.covariance[row * 6 + col] = (row == col) ? diag[row] : 0.0;
    }
  }
  cdr_serialize(pc, buf);
  host_.publish(host_.host_ctx, pose_cov_, buf.data(), buf.size());
}

}  // namespace autoware
}  // namespace carla
