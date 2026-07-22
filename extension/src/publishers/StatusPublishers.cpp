#include "StatusPublishers.h"

#include <cstdint>
#include <vector>

#include <autoware_vehicle_msgs/msg/control_mode_report.hpp>
#include <autoware_vehicle_msgs/msg/gear_report.hpp>
#include <autoware_vehicle_msgs/msg/hazard_lights_report.hpp>
#include <autoware_vehicle_msgs/msg/steering_report.hpp>
#include <autoware_vehicle_msgs/msg/turn_indicators_report.hpp>
#include <autoware_vehicle_msgs/msg/velocity_report.hpp>
#include <builtin_interfaces/msg/time.hpp>

#include "carla/autoware/messages/RosIdl.h"

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
  using autoware_vehicle_msgs::msg::ControlModeReport;
  using autoware_vehicle_msgs::msg::GearReport;
  using autoware_vehicle_msgs::msg::HazardLightsReport;
  using autoware_vehicle_msgs::msg::SteeringReport;
  using autoware_vehicle_msgs::msg::TurnIndicatorsReport;
  using autoware_vehicle_msgs::msg::VelocityReport;
  velocity_ = mk("/vehicle/status/velocity_status",
                 dds_type_name<VelocityReport>(), rihs01_hash<VelocityReport>().c_str());
  steering_ = mk("/vehicle/status/steering_status",
                 dds_type_name<SteeringReport>(), rihs01_hash<SteeringReport>().c_str());
  gear_ = mk("/vehicle/status/gear_status",
             dds_type_name<GearReport>(), rihs01_hash<GearReport>().c_str());
  mode_ = mk("/vehicle/status/control_mode",
             dds_type_name<ControlModeReport>(), rihs01_hash<ControlModeReport>().c_str());
  turn_ = mk("/vehicle/status/turn_indicators_status",
             dds_type_name<TurnIndicatorsReport>(), rihs01_hash<TurnIndicatorsReport>().c_str());
  hazard_ = mk("/vehicle/status/hazard_lights_status",
               dds_type_name<HazardLightsReport>(), rihs01_hash<HazardLightsReport>().c_str());
}

void StatusPublishers::OnVehicleStatus(const CarlaRos2VehicleStatusView& v, const StatusInputs& in) {
  // Split the ROS 2 sim clock into builtin_interfaces/Time (sec, nanosec). Every
  // status message shares this one stamp. E.g. 12.5 -> sec 12, nanosec 5e8.
  builtin_interfaces::msg::Time stamp;
  stamp.sec = static_cast<int32_t>(v.sim_time_s);
  stamp.nanosec =
      static_cast<uint32_t>((v.sim_time_s - static_cast<double>(stamp.sec)) * 1e9);

  std::vector<uint8_t> buf;
  auto emit = [&](CarlaRos2PubHandle h) {
    host_.publish(host_.host_ctx, h, buf.data(), buf.size());
  };

  // VelocityReport is the only status message with a std_msgs/Header; its
  // frame_id is publisher policy ("base_link"), set here explicitly now that
  // the field lives on the generated message rather than in a hand serializer.
  autoware_vehicle_msgs::msg::VelocityReport vr;
  vr.header.stamp = stamp;
  vr.header.frame_id = "base_link";
  vr.longitudinal_velocity = velocity_report_longitudinal(v.velocity_mps);
  vr.lateral_velocity = static_cast<float>(v.lateral_velocity_mps);
  vr.heading_rate = static_cast<float>(v.yaw_rate_rps);
  cdr_serialize(vr, buf);
  emit(velocity_);

  autoware_vehicle_msgs::msg::SteeringReport sr;
  sr.stamp = stamp;
  sr.steering_tire_angle = steering_report_tire_angle(v.steering_tire_angle_rad);
  cdr_serialize(sr, buf);
  emit(steering_);

  autoware_vehicle_msgs::msg::GearReport gr;
  gr.stamp = stamp;
  gr.report = in.gear;
  cdr_serialize(gr, buf);
  emit(gear_);

  autoware_vehicle_msgs::msg::ControlModeReport cm;
  cm.stamp = stamp;
  cm.mode = in.control_mode;  // from the engage state machine
  cdr_serialize(cm, buf);
  emit(mode_);

  autoware_vehicle_msgs::msg::TurnIndicatorsReport ti;
  ti.stamp = stamp;
  ti.report = in.turn_indicators;  // cached from the control subscribers
  cdr_serialize(ti, buf);
  emit(turn_);

  autoware_vehicle_msgs::msg::HazardLightsReport hl;
  hl.stamp = stamp;
  hl.report = in.hazard_lights;  // cached from the control subscribers
  cdr_serialize(hl, buf);
  emit(hazard_);
}

}  // namespace autoware
}  // namespace carla
