#pragma once

// Six `/vehicle/status/*` publishers, driven by the host's per-frame ego-status
// observer (CARLA_ROS2_SENSOR_VEHICLE_STATUS). One CarlaRos2VehicleStatusView in,
// six Autoware status samples out, every frame, at AWSIM-compatible QoS
// (RELIABLE / VOLATILE / KEEP_LAST depth-1). This header is an implementation
// detail of the extension .so, not part of the frozen C ABI seam.

#include <cstdint>

#include "carla/ros2/extension/CarlaRos2Extension.h"

namespace carla {
namespace autoware {

// Per-frame state the status publishers need BEYOND the ego observer view: the
// control mode from the engage state machine and the latest cached
// command reports from the control subscribers. The init entrypoint
// threads these in alongside each observer callback. Defaults are the
// safe "vehicle idle, not engaged" state so a frame that arrives before any
// command still publishes a coherent status.
struct StatusInputs {
  uint8_t control_mode{4};     // ControlModeReport::mode   (1=AUTONOMOUS, 4=MANUAL)
  uint8_t gear{0};             // GearReport::report        (cached gear_cmd; 0=NONE)
  uint8_t turn_indicators{1};  // TurnIndicatorsReport::report (1=DISABLE)
  uint8_t hazard_lights{1};    // HazardLightsReport::report   (1=DISABLE)
};

class StatusPublishers {
 public:
  // Creates all six status publishers on `host`. Must be called once, from the
  // extension init / game thread, before the first OnVehicleStatus (host-vtable
  // rule: create_publisher is not thread-safe against dispatch).
  void Init(const CarlaRos2Host& host);

  // Serializes and publishes all six status messages for one ego frame. `v`
  // supplies velocity/lateral/heading-rate/steering/stamp; `in` supplies the
  // gear/mode/turn/hazard values the observer view does not carry.
  void OnVehicleStatus(const CarlaRos2VehicleStatusView& v, const StatusInputs& in);

 private:
  CarlaRos2Host host_{};
  CarlaRos2PubHandle velocity_{0}, steering_{0}, gear_{0}, mode_{0}, turn_{0}, hazard_{0};
};

}  // namespace autoware
}  // namespace carla
