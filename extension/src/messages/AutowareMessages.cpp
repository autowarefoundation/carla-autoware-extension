// Out-of-line AwTopicInfo definitions + CDR serializers/deserializer for the
// Autoware messages this extension bridges. This .cpp is the ONE place the
// generated RIHS01 goldens (AwGoldens.inc) are pulled in, so the type_hash()
// bodies are the single source of the pinned hashes.
//
// Every field order/type below matches the extracted .msg files under
// extension/msg/** byte-for-byte. Where that differs from the Task-17 brief's
// draft, the deviation is called out inline; each was proven load-bearing by a
// test in test_messages.cpp (the draft layout fails those tests).
#include "carla/autoware/messages/AutowareMessages.h"

#include "AwGoldens.inc"
#include "carla/autoware/messages/Cdr.h"

namespace carla {
namespace autoware {

// --- Type info: declared in the header, defined here (goldens live in one place).
const char* AwTopicInfo<VelocityReport>::type_name() { return "autoware_vehicle_msgs::msg::dds_::VelocityReport_"; }
const char* AwTopicInfo<VelocityReport>::type_hash() { return AW_GOLDEN_VelocityReport; }
const char* AwTopicInfo<SteeringReport>::type_name() { return "autoware_vehicle_msgs::msg::dds_::SteeringReport_"; }
const char* AwTopicInfo<SteeringReport>::type_hash() { return AW_GOLDEN_SteeringReport; }
const char* AwTopicInfo<GearReport>::type_name() { return "autoware_vehicle_msgs::msg::dds_::GearReport_"; }
const char* AwTopicInfo<GearReport>::type_hash() { return AW_GOLDEN_GearReport; }
const char* AwTopicInfo<ControlModeReport>::type_name() { return "autoware_vehicle_msgs::msg::dds_::ControlModeReport_"; }
const char* AwTopicInfo<ControlModeReport>::type_hash() { return AW_GOLDEN_ControlModeReport; }
const char* AwTopicInfo<TurnIndicatorsReport>::type_name() { return "autoware_vehicle_msgs::msg::dds_::TurnIndicatorsReport_"; }
const char* AwTopicInfo<TurnIndicatorsReport>::type_hash() { return AW_GOLDEN_TurnIndicatorsReport; }
const char* AwTopicInfo<HazardLightsReport>::type_name() { return "autoware_vehicle_msgs::msg::dds_::HazardLightsReport_"; }
const char* AwTopicInfo<HazardLightsReport>::type_hash() { return AW_GOLDEN_HazardLightsReport; }
const char* AwTopicInfo<Control>::type_name() { return "autoware_control_msgs::msg::dds_::Control_"; }
const char* AwTopicInfo<Control>::type_hash() { return AW_GOLDEN_Control; }

// --- Serializers (publisher side).

// VelocityReport carries a std_msgs/Header, so the frame_id string IS on the
// wire. The status publishers always report in "base_link"; that frame is a
// publisher policy, not per-sample data, so it is written here rather than
// stored on the POD (Task 18 owns frame semantics).
size_t cdr_serialize(const VelocityReport& m, std::vector<uint8_t>& out) {
  CdrWriter w;
  w.i32(m.header.stamp.sec);
  w.u32(m.header.stamp.nanosec);
  w.str("base_link");  // std_msgs/Header.frame_id
  w.f32(m.longitudinal_velocity);
  w.f32(m.lateral_velocity);
  w.f32(m.heading_rate);
  out = w.bytes();
  return out.size();
}

// SteeringReport.msg has a BARE builtin_interfaces/Time stamp and NO frame_id
// -- so no string is written (contrast VelocityReport above). The brief draft
// wrongly appended one; test steering_report_serializes_without_frame_id pins
// the exact 16-byte layout that forbids it.
size_t cdr_serialize(const SteeringReport& m, std::vector<uint8_t>& out) {
  CdrWriter w;
  w.i32(m.stamp.sec);
  w.u32(m.stamp.nanosec);
  w.f32(m.steering_tire_angle);
  out = w.bytes();
  return out.size();
}

size_t cdr_serialize(const GearReport& m, std::vector<uint8_t>& out) {
  CdrWriter w;
  w.i32(m.stamp.sec);
  w.u32(m.stamp.nanosec);
  w.u8(m.report);
  out = w.bytes();
  return out.size();
}

size_t cdr_serialize(const ControlModeReport& m, std::vector<uint8_t>& out) {
  CdrWriter w;
  w.i32(m.stamp.sec);
  w.u32(m.stamp.nanosec);
  w.u8(m.mode);
  out = w.bytes();
  return out.size();
}

size_t cdr_serialize(const TurnIndicatorsReport& m, std::vector<uint8_t>& out) {
  CdrWriter w;
  w.i32(m.stamp.sec);
  w.u32(m.stamp.nanosec);
  w.u8(m.report);
  out = w.bytes();
  return out.size();
}

size_t cdr_serialize(const HazardLightsReport& m, std::vector<uint8_t>& out) {
  CdrWriter w;
  w.i32(m.stamp.sec);
  w.u32(m.stamp.nanosec);
  w.u8(m.report);
  out = w.bytes();
  return out.size();
}

// --- Deserializer (subscriber side).
//
// Reads the FULL Control/Lateral/Longitudinal layout: both control_time fields
// and every trailing bool, in .msg order. Omitting any of them (as the brief
// draft did) shifts every following field off its wire offset. The reader is
// bounds-checked, so a truncated network sample fails here rather than reading
// out of bounds; r.ok() is the verdict.
bool cdr_deserialize(const uint8_t* p, size_t n, Control& m) {
  CdrReader r(p, n);
  m.stamp.sec = r.i32();
  m.stamp.nanosec = r.u32();
  m.control_time.sec = r.i32();
  m.control_time.nanosec = r.u32();

  m.lateral.stamp.sec = r.i32();
  m.lateral.stamp.nanosec = r.u32();
  m.lateral.control_time.sec = r.i32();
  m.lateral.control_time.nanosec = r.u32();
  m.lateral.steering_tire_angle = r.f32();
  m.lateral.steering_tire_rotation_rate = r.f32();
  m.lateral.is_defined_steering_tire_rotation_rate = r.boolean();

  m.longitudinal.stamp.sec = r.i32();
  m.longitudinal.stamp.nanosec = r.u32();
  m.longitudinal.control_time.sec = r.i32();
  m.longitudinal.control_time.nanosec = r.u32();
  m.longitudinal.velocity = r.f32();
  m.longitudinal.acceleration = r.f32();
  m.longitudinal.jerk = r.f32();
  m.longitudinal.is_defined_acceleration = r.boolean();
  m.longitudinal.is_defined_jerk = r.boolean();

  return r.ok();
}

}  // namespace autoware
}  // namespace carla
