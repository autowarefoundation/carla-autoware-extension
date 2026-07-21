#include "GnssPosePublisher.h"

#include <cstdint>
#include <vector>

#include "GeoGoldens.inc"  // GENERATED: AW_GOLDEN_PoseStamped / _PoseWithCovarianceStamped
#include "carla/autoware/geo/MgrsOffset.h"
#include "carla/autoware/messages/Cdr.h"

namespace carla {
namespace autoware {

// DDS type names (rmw_cyclonedds convention: `pkg::msg::dds_::Type_`), matching
// the AutowareMessages.cpp style. These are hand-authored; the RIHS01 hashes are
// the generated goldens. This .cpp is the ONE TU that includes GeoGoldens.inc.
const char* pose_stamped_type_name() { return "geometry_msgs::msg::dds_::PoseStamped_"; }
const char* pose_stamped_type_hash() { return AW_GOLDEN_PoseStamped; }
const char* pose_with_covariance_stamped_type_name() {
  return "geometry_msgs::msg::dds_::PoseWithCovarianceStamped_";
}
const char* pose_with_covariance_stamped_type_hash() { return AW_GOLDEN_PoseWithCovarianceStamped; }

// AWSIM GNSS QoS: RELIABLE / VOLATILE / KEEP_LAST depth 1 (same encoding as the
// status publishers; CarlaRos2Extension.h documents the field meanings --
// reliability 0 = reliable, durability 0 = volatile, history_depth clamped>=1).
static CarlaRos2Qos GnssQos() { return CarlaRos2Qos{/*reliability=*/0u, /*durability=*/0u,
                                                    /*history_depth=*/1u}; }

// geometry_msgs/Pose in the `map` frame: Header(stamp, frame_id "map") then
// Point(x,y,z) + Quaternion(x,y,z,w), all float64. This is the shared prefix of
// BOTH published messages -- PoseStamped ends here; PoseWithCovarianceStamped
// appends the covariance. frame_id is publisher policy ("map"), written here
// rather than carried on a POD.
static void write_map_pose_prefix(CdrWriter& w, int32_t sec, uint32_t nanosec, double x, double y,
                                  double z, double qx, double qy, double qz, double qw) {
  w.i32(sec);
  w.u32(nanosec);
  w.str("map");
  w.f64(x);
  w.f64(y);
  w.f64(z);
  w.f64(qx);
  w.f64(qy);
  w.f64(qz);
  w.f64(qw);
}

void GnssPosePublisher::Init(const CarlaRos2Host& host) {
  host_ = host;
  // create_publisher takes `const CarlaRos2Qos*`; bind an lvalue whose lifetime
  // spans both synchronous calls (never pass the address of a temporary).
  const CarlaRos2Qos qos = GnssQos();
  pose_ = host_.create_publisher(host_.host_ctx, "/sensing/gnss/pose", pose_stamped_type_name(),
                                 pose_stamped_type_hash(), &qos);
  pose_cov_ = host_.create_publisher(host_.host_ctx, "/sensing/gnss/pose_with_covariance",
                                     pose_with_covariance_stamped_type_name(),
                                     pose_with_covariance_stamped_type_hash(), &qos);
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

  // Split the ROS 2 sim clock into builtin_interfaces/Time (sec, nanosec).
  const int32_t sec = static_cast<int32_t>(t);
  const uint32_t nanosec = static_cast<uint32_t>((t - static_cast<double>(sec)) * 1e9);

  CdrWriter wp;
  write_map_pose_prefix(wp, sec, nanosec, mx, my, mz, qx, qy, qz, qw);
  host_.publish(host_.host_ctx, pose_, wp.bytes().data(), wp.bytes().size());

  CdrWriter wc;
  write_map_pose_prefix(wc, sec, nanosec, mx, my, mz, qx, qy, qz, qw);  // same header+pose prefix
  // PoseWithCovariance appends a float64[36] row-major covariance. It is a
  // FIXED-size array, so there is NO uint32 length prefix -- the 36 f64 are
  // written straight. A small diagonal (x,y,z, roll,pitch,yaw) marks the pose as
  // trustworthy-but-not-perfect; off-diagonal terms are zero.
  const double diag[6] = {0.1, 0.1, 0.1, 0.05, 0.05, 0.05};
  for (int row = 0; row < 6; ++row) {
    for (int col = 0; col < 6; ++col) {
      wc.f64(row == col ? diag[row] : 0.0);
    }
  }
  host_.publish(host_.host_ctx, pose_cov_, wc.bytes().data(), wc.bytes().size());
}

}  // namespace autoware
}  // namespace carla
