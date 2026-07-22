#pragma once

// Single `/autoware/engage` subscriber (autoware_vehicle_msgs/Engage) driving
// the ControlModeReport mode that StatusPublishers::OnVehicleStatus publishes
// (the init entrypoint threads Mode() into StatusInputs::control_mode each
// frame -- this class does NOT publish anything itself).
//
// TOPIC PINNED AGAINST THE CONTAINER (Step 1, ghcr.io/autowarefoundation/
// autoware:universe-devel, ROS_DISTRO=humble):
//   $ grep -rniE "engage" /opt/autoware/share/autoware_vehicle_cmd_gate/ | grep -i topic
//   (no hits -- this exact filter matches nothing; the launch XML remap
//    lines below don't contain the literal word "topic")
//   $ grep -rn "autoware/engage" /opt/autoware/share/autoware_vehicle_cmd_gate/
//   launch/vehicle_cmd_gate.launch.xml:  <!-- TODO(Takagi, Isamu): deprecated -->
//   launch/vehicle_cmd_gate.launch.xml:  <remap from="input/engage" to="/autoware/engage"/>
// vehicle_cmd_gate.launch.xml (also duplicated verbatim in
// tier4_control_launch/launch/control.launch.xml) remaps its `input/engage`
// subscription to `/autoware/engage`, confirming the expected topic
// over the 2026-07-09 spec's `/vehicle/engage`. The remap is annotated
// "deprecated" upstream (the modern path is the `/api/autoware/set/engage`
// SERVICE via default_ad_api) but is still wired up and functional -- this is
// exactly the topic the G2 harness drives with `ros2 topic pub`.
//
// Type pinned the same way:
//   $ ros2 interface show autoware_vehicle_msgs/msg/Engage
//   builtin_interfaces/Time stamp
//   bool engage
// matches the expected field order exactly, as used directly via the
// rosidl-generated autoware_vehicle_msgs::msg::Engage type (no hand-copied
// .msg extraction needed now that the rosidl codec is the message layer).
//
// PUBLISHER-SIDE DURABILITY: no node in the image PUBLISHES `/autoware/engage`
// (it is fed externally -- by design, since it is the deprecated topic path);
// so the real publisher's QoS could not be observed directly from the
// container, and it remains unobserved. The load-bearing justification for
// this extension's VOLATILE subscriber is the G2 harness itself: it engages
// via `ros2 topic pub`, whose default publisher profile is RELIABLE /
// VOLATILE / KEEP_LAST -- a transient_local subscriber would never match it.
// For reference (merely CONSISTENT WITH, not proof of, a volatile publisher:
// a volatile-requesting subscriber matches either durability), the upstream
// vehicle_cmd_gate subscriber uses the same default profile
// (github.com/autowarefoundation/autoware_universe,
// control/autoware_vehicle_cmd_gate/src/vehicle_cmd_gate.cpp):
//   engage_sub_ = create_subscription<EngageMsg>(
//       "input/engage", 1, std::bind(&VehicleCmdGate::onEngage, this, _1));
// See the QoS comment below for the compatibility rule.

#include <atomic>
#include <cstdint>

#include "carla/ros2/extension/CarlaRos2Extension.h"

namespace carla {
namespace autoware {

// Pure engage-bool -> ControlModeReport mode mapping (the
// ControlModeReport.msg constants: AUTONOMOUS = 1, MANUAL = 4). Declared for
// the unit test; defined in the .cpp.
uint8_t engage_to_mode(bool engaged);

class EngageStateMachine {
 public:
  // Creates the `/autoware/engage` subscriber on `host`. Must be called once,
  // from the extension init / game thread, before any sample can arrive
  // (host-vtable rule: create_subscriber is not thread-safe against dispatch).
  void Init(const CarlaRos2Host& host);

  // Latest mode, read from the GAME thread (via StatusPublishers::
  // OnVehicleStatus) while the DDS listener thread writes it -- hence
  // std::atomic. relaxed is sufficient: this is a lone independent byte with
  // no ordering relationship to any other state the reader synchronizes on
  // (mirrors ControlSubscribers' cached command bytes).
  uint8_t Mode() const { return mode_.load(std::memory_order_relaxed); }

 private:
  CarlaRos2Host host_{};
  // Default MANUAL (4) until the first engage message arrives -- matches
  // StatusInputs::control_mode's documented safe-idle default.
  std::atomic<uint8_t> mode_{4};
};

}  // namespace autoware
}  // namespace carla
