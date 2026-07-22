#pragma once

// GNSS/MGRS pose synthesis: turns the host's per-frame ego status
// (CARLA_ROS2_SENSOR_VEHICLE_STATUS) into AWSIM-style GNSS poses on
//   /sensing/gnss/pose                 (geometry_msgs/PoseStamped)
//   /sensing/gnss/pose_with_covariance (geometry_msgs/PoseWithCovarianceStamped)
// in the `map` frame at 1 Hz (decimated). The pose is synthesised from the ego
// world transform + the static MGRS converter offset (MgrsOffset.h), NEVER from
// CARLA's own geolocation (the loaded Nishi-Shinjuku map has a degenerate
// geo-reference; see docs/mgrs-handedness.md). This header is an implementation
// detail of the extension .so, not part of the frozen C ABI seam.

#include <cstdint>

#include "carla/ros2/extension/CarlaRos2Extension.h"

namespace carla {
namespace autoware {

class GnssPosePublisher {
 public:
  // Creates both GNSS pose publishers on `host`. Must be called once, from the
  // extension init / game thread, before the first OnVehicleStatus (host-vtable
  // rule: create_publisher is not thread-safe against dispatch).
  void Init(const CarlaRos2Host& host);

  // Synthesises and publishes both poses for one ego frame, decimated to 1 Hz.
  // The FIRST call always publishes; thereafter it publishes only once the sim
  // clock has advanced >= 1 s -- OR gone BACKWARDS (episode reload restarts the
  // sim clock, which must not deadlock the decimator; see the .cpp).
  void OnVehicleStatus(const CarlaRos2VehicleStatusView& v);

 private:
  CarlaRos2Host host_{};
  CarlaRos2PubHandle pose_{0};       // /sensing/gnss/pose
  CarlaRos2PubHandle pose_cov_{0};   // /sensing/gnss/pose_with_covariance
  double last_pub_s_{-1.0};          // sentinel < 0 so the first frame publishes
};

}  // namespace autoware
}  // namespace carla
