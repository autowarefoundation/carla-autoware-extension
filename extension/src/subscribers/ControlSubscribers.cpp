#include "ControlSubscribers.h"

#include <cmath>
#include <cstdint>

#include <autoware_control_msgs/msg/control.hpp>
#include <autoware_vehicle_msgs/msg/gear_command.hpp>
#include <autoware_vehicle_msgs/msg/hazard_lights_command.hpp>
#include <autoware_vehicle_msgs/msg/turn_indicators_command.hpp>

#include "carla/autoware/control/AutowareSteeringCompensation.h"
#include "carla/autoware/messages/RosIdl.h"

namespace carla {
namespace autoware {

// ===========================================================================
// Control -> CarlaRos2AckermannPod.
//
// SIGN OWNERSHIP (this file owns the steering flip on the INBOUND path):
//   Autoware treats positive steering_tire_angle as LEFT; CARLA treats positive
//   as RIGHT (when moving forward). So we negate first, then feed the negated,
//   still-signed value through the compensation lookup. The resulting
//   CarlaRos2AckermannPod::steer is already in CARLA sign -- the ABI header
//   documents that field as "rad (CARLA sign, after the extension's
//   compensation/flip)", i.e. the host does NOT flip again downstream.
//   (Contrast the OUTBOUND status path, where CarlaRos2VehicleStatusView already
//   arrives Autoware-signed and StatusPublishers passes it through unchanged.)
//
// STEERING COMPENSATION: GetSteeringInput is the INVERSE lookup -- given the
// target tire angle it returns the CARLA input that makes the vehicle reach it
// (reduces understeer / outward drift on the Lincoln MKZ the table was measured
// on). It takes the SIGNED angle and restores the sign internally.
//
// LONGITUDINAL -- DELIBERATE DEVIATION FROM tier4: tier4's AutowareController
// used ACCELERATION ONLY ("pure acceleration control"; velocity and jerk were
// intentionally ignored). This port instead maps all three
// (speed=velocity, acceleration, jerk) because CARLA's ApplyVehicleAckermann-
// Control is a TARGET-BASED controller that consumes a target speed together
// with the accel/jerk limits. The difference is a tuning watch-point for
// closed-loop path tracking (the live G2 drive passed with it in place).
CarlaRos2AckermannPod control_to_ackermann(const autoware_control_msgs::msg::Control& c) {
  CarlaRos2AckermannPod p{};

  // Longitudinal: all three forwarded (see the deviation note above).
  p.speed = c.longitudinal.velocity;
  p.acceleration = c.longitudinal.acceleration;
  p.jerk = c.longitudinal.jerk;

  // Lateral: negate into CARLA sign, then apply the inverse-lookup compensation.
  const float raw_steering = -c.lateral.steering_tire_angle;
  p.steer = GetSteeringInput(raw_steering);

  // steer_speed defaults to 0 and is only set when the rate is defined; when set
  // it is negated onto the same axis convention as the steering angle.
  p.steer_speed = 0.0f;
  if (c.lateral.is_defined_steering_tire_rotation_rate) {
    p.steer_speed = -c.lateral.steering_tire_rotation_rate;
  }
  return p;
}

// Deserialize a { builtin_interfaces/Time stamp; uint8 command } message and
// return the command byte, or the fallback if the sample is short/malformed.
// The typed deserializer reads by position and ignores any trailing DDS
// padding, mirroring the old bounds-checked positional parser.
template <typename CmdT>
static uint8_t parse_command(const uint8_t* cdr, size_t len, uint8_t fallback) {
  CmdT m;
  return cdr_deserialize(cdr, len, m) ? m.command : fallback;
}

void ControlSubscribers::Init(const CarlaRos2Host& host) {
  host_ = host;

  // Control commands are streamed at ~60 Hz; best_effort/volatile/keep-last-1
  // matches the native Autoware control subscriber (reliability 1 = BEST_EFFORT,
  // durability 0 = VOLATILE, history_depth 1 -- CarlaRos2Extension.h comments).
  CarlaRos2Qos qos{1u, 0u, 1u};

  // /control/command/control_cmd -> Control -> Ackermann -> ego actuation.
  // The type_hash is the REAL Control RIHS01 golden, so this reader's
  // topic type registration matches the real Autoware publisher at the live E2E gates.
  //
  // The callback runs on the DDS listener thread. Applying inline is the
  // intended host design: the host stages the pod last-wins and drains it at
  // SetFrame, so there is no cross-thread hazard in calling
  // apply_ackermann_control directly here. Malformed CDR or "no ego yet" both
  // drop silently (fire-and-forget, per the ABI's apply_ackermann_control
  // contract and the status/GNSS publisher precedent) -- return values are not surfaced.
  host_.create_subscriber(
      host_.host_ctx, "/control/command/control_cmd",
      dds_type_name<autoware_control_msgs::msg::Control>(),
      rihs01_hash<autoware_control_msgs::msg::Control>().c_str(), &qos,
      [](void* user, const uint8_t* cdr, size_t len) {
        auto* self = static_cast<ControlSubscribers*>(user);
        autoware_control_msgs::msg::Control c;
        if (!cdr_deserialize(cdr, len, c)) return;  // truncated/garbage -> drop
        const uint32_t ego = self->host_.get_ego_actor_id(self->host_.host_ctx);
        if (ego == 0u) return;  // no ego registered -> drop
        const CarlaRos2AckermannPod pod = control_to_ackermann(c);
        self->host_.apply_ackermann_control(self->host_.host_ctx, ego, &pod);
      },
      this);

  // The three command subscribers cache their uint8 for the status publishers.
  // The CycloneDDS blob subscriber ignores type_hash, so "" is correct here --
  // Humble puts no type hash on the wire for these. The runtime RIHS01 hash is
  // now available via rihs01_hash<T>() but is deliberately NOT sent, to stay
  // bit-compatible with the G0-verified registration. The caches are atomic:
  // written here on the DDS listener thread, read on the game thread.
  host_.create_subscriber(
      host_.host_ctx, "/control/command/gear_cmd",
      "autoware_vehicle_msgs::msg::dds_::GearCommand_", "", &qos,
      [](void* user, const uint8_t* cdr, size_t len) {
        auto* self = static_cast<ControlSubscribers*>(user);
        self->gear_.store(
            parse_command<autoware_vehicle_msgs::msg::GearCommand>(cdr, len, self->CachedGear()),
            std::memory_order_relaxed);
      },
      this);
  host_.create_subscriber(
      host_.host_ctx, "/control/command/turn_indicators_cmd",
      "autoware_vehicle_msgs::msg::dds_::TurnIndicatorsCommand_", "", &qos,
      [](void* user, const uint8_t* cdr, size_t len) {
        auto* self = static_cast<ControlSubscribers*>(user);
        self->turn_.store(
            parse_command<autoware_vehicle_msgs::msg::TurnIndicatorsCommand>(
                cdr, len, self->CachedTurnIndicators()),
            std::memory_order_relaxed);
      },
      this);
  host_.create_subscriber(
      host_.host_ctx, "/control/command/hazard_lights_cmd",
      "autoware_vehicle_msgs::msg::dds_::HazardLightsCommand_", "", &qos,
      [](void* user, const uint8_t* cdr, size_t len) {
        auto* self = static_cast<ControlSubscribers*>(user);
        self->hazard_.store(
            parse_command<autoware_vehicle_msgs::msg::HazardLightsCommand>(
                cdr, len, self->CachedHazardLights()),
            std::memory_order_relaxed);
      },
      this);
}

}  // namespace autoware
}  // namespace carla
