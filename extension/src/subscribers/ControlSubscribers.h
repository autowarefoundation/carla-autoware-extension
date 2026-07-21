#pragma once

// Four `/control/command/*` subscribers driven by the host's DDS reader:
//   /control/command/control_cmd          (autoware_control_msgs/Control) ->
//       Control->Ackermann conversion -> host.apply_ackermann_control(ego)
//   /control/command/gear_cmd             (uint8 command, cached)
//   /control/command/turn_indicators_cmd  (uint8 command, cached)
//   /control/command/hazard_lights_cmd    (uint8 command, cached)
// The three cached command bytes are read back by the status publishers
// (Task 18/22) via the accessors below. This header is an implementation detail
// of the extension .so, not part of the frozen C ABI seam.

#include <atomic>
#include <cstdint>

#include "carla/autoware/messages/AutowareMessages.h"
#include "carla/ros2/extension/CarlaRos2Extension.h"

namespace carla {
namespace autoware {

// Pure Control -> CarlaRos2AckermannPod conversion (sign ownership + steering
// compensation live here). Declared for the unit test; defined in the .cpp.
CarlaRos2AckermannPod control_to_ackermann(const Control& c);

class ControlSubscribers {
 public:
  // Creates all four control-command subscribers on `host`. Must be called once,
  // from the extension init / game thread, before any sample can arrive
  // (host-vtable rule: create_subscriber is not thread-safe against dispatch).
  void Init(const CarlaRos2Host& host);

  // Latest cached command bytes, read from the GAME thread by the status
  // publishers while the DDS listener thread writes them -- hence std::atomic.
  // relaxed is sufficient: each cache is a lone independent byte with no
  // ordering relationship to the others or to any surrounding state, so there is
  // nothing for an acquire/release fence to publish or observe.
  uint8_t CachedGear() const { return gear_.load(std::memory_order_relaxed); }
  uint8_t CachedTurnIndicators() const { return turn_.load(std::memory_order_relaxed); }
  uint8_t CachedHazardLights() const { return hazard_.load(std::memory_order_relaxed); }

 private:
  CarlaRos2Host host_{};
  // Safe idle defaults so a status frame before any command still publishes a
  // coherent state (mirrors StatusInputs): gear NONE, indicators DISABLE.
  std::atomic<uint8_t> gear_{0};    // GearReport::NONE
  std::atomic<uint8_t> turn_{1};    // TurnIndicatorsReport::DISABLE
  std::atomic<uint8_t> hazard_{1};  // HazardLightsReport::DISABLE
};

}  // namespace autoware
}  // namespace carla
