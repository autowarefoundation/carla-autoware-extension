#include "StatusPublishers.h"

#include <cstdint>
#include <vector>

#include "carla/autoware/messages/AutowareMessages.h"  // PODs + AwTopicInfo + cdr_serialize

namespace carla {
namespace autoware {

// Steering sign is OWNED BY THE HOST, not by this extension. The CARLA-side
// observer converts the FL wheel angle into the Autoware convention (deg->rad,
// negated, positive = left) before it populates the view. The ABI header is
// explicit -- CarlaRos2Extension.h, steering_tire_angle_rad:
//   "positive = left (Autoware convention, already applied by the host --
//    do NOT negate again)".
// So SteeringReport.steering_tire_angle is the view value passed straight
// through. This helper is the single documented seam where a sign transform
// would live if the host did NOT already own it; keeping it named (rather than
// inlining `(float)v...`) is what makes that contract testable.
float steering_report_tire_angle(double view_steering_tire_angle_rad) {
  return static_cast<float>(view_steering_tire_angle_rad);
}

// VelocityReport.longitudinal_velocity is the body-frame longitudinal speed the
// view already reports in m/s (CarlaRos2VehicleStatusView::velocity_mps is
// documented "longitudinal, body frame"); just narrow double -> float32.
float velocity_report_longitudinal(double body_velocity_mps) {
  return static_cast<float>(body_velocity_mps);
}

// AWSIM status QoS: RELIABLE / VOLATILE / KEEP_LAST depth 1. The ABI header
// documents the field encoding (CarlaRos2Extension.h, CarlaRos2Qos):
//   reliability   0 = reliable
//   durability    0 = volatile
//   history_depth = keep-last depth (0 clamped to 1 by the host)
// The header defines no named enum constants for these, so the literals are
// annotated here rather than symbolically.
static CarlaRos2Qos StatusQos() {
  return CarlaRos2Qos{/*reliability=*/0u, /*durability=*/0u, /*history_depth=*/1u};
}

void StatusPublishers::Init(const CarlaRos2Host& host) {
  host_ = host;
  // create_publisher takes `const CarlaRos2Qos*`; bind an lvalue whose lifetime
  // spans all six synchronous calls (never pass the address of a temporary).
  const CarlaRos2Qos qos = StatusQos();
  auto mk = [&](const char* topic, const char* type_name, const char* type_hash) {
    return host_.create_publisher(host_.host_ctx, topic, type_name, type_hash, &qos);
  };
  velocity_ = mk("/vehicle/status/velocity_status",
                 AwTopicInfo<VelocityReport>::type_name(), AwTopicInfo<VelocityReport>::type_hash());
  steering_ = mk("/vehicle/status/steering_status",
                 AwTopicInfo<SteeringReport>::type_name(), AwTopicInfo<SteeringReport>::type_hash());
  gear_ = mk("/vehicle/status/gear_status",
             AwTopicInfo<GearReport>::type_name(), AwTopicInfo<GearReport>::type_hash());
  mode_ = mk("/vehicle/status/control_mode",
             AwTopicInfo<ControlModeReport>::type_name(), AwTopicInfo<ControlModeReport>::type_hash());
  turn_ = mk("/vehicle/status/turn_indicators_status",
             AwTopicInfo<TurnIndicatorsReport>::type_name(), AwTopicInfo<TurnIndicatorsReport>::type_hash());
  hazard_ = mk("/vehicle/status/hazard_lights_status",
               AwTopicInfo<HazardLightsReport>::type_name(), AwTopicInfo<HazardLightsReport>::type_hash());
}

void StatusPublishers::OnVehicleStatus(const CarlaRos2VehicleStatusView& v, const StatusInputs& in) {
  // Split the ROS 2 sim clock into builtin_interfaces/Time (sec, nanosec). Every
  // status message shares this one stamp. E.g. 12.5 -> sec 12, nanosec 5e8.
  const int32_t sec = static_cast<int32_t>(v.sim_time_s);
  const uint32_t nanosec = static_cast<uint32_t>((v.sim_time_s - static_cast<double>(sec)) * 1e9);
  const Time stamp{sec, nanosec};

  std::vector<uint8_t> buf;
  auto emit = [&](CarlaRos2PubHandle h) {
    host_.publish(host_.host_ctx, h, buf.data(), buf.size());
  };

  // VelocityReport is the only status message with a std_msgs/Header (frame_id
  // "base_link" is written by the serializer); the rest carry a bare Time stamp.
  VelocityReport vr{};
  vr.header.stamp = stamp;
  vr.longitudinal_velocity = velocity_report_longitudinal(v.velocity_mps);
  vr.lateral_velocity = static_cast<float>(v.lateral_velocity_mps);
  vr.heading_rate = static_cast<float>(v.yaw_rate_rps);
  cdr_serialize(vr, buf);
  emit(velocity_);

  SteeringReport sr{};
  sr.stamp = stamp;
  sr.steering_tire_angle = steering_report_tire_angle(v.steering_tire_angle_rad);
  cdr_serialize(sr, buf);
  emit(steering_);

  GearReport gr{};
  gr.stamp = stamp;
  gr.report = in.gear;
  cdr_serialize(gr, buf);
  emit(gear_);

  ControlModeReport cm{};
  cm.stamp = stamp;
  cm.mode = in.control_mode;  // from the engage state machine (Task 21)
  cdr_serialize(cm, buf);
  emit(mode_);

  TurnIndicatorsReport ti{};
  ti.stamp = stamp;
  ti.report = in.turn_indicators;  // cached from the control subscribers (Task 20)
  cdr_serialize(ti, buf);
  emit(turn_);

  HazardLightsReport hl{};
  hl.stamp = stamp;
  hl.report = in.hazard_lights;  // cached from the control subscribers (Task 20)
  cdr_serialize(hl, buf);
  emit(hazard_);
}

}  // namespace autoware
}  // namespace carla
