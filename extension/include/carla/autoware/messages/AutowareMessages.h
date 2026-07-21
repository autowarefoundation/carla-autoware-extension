#pragma once

// Hand-written PODs + type metadata for the Autoware ROS 2 messages this
// extension publishes (vehicle status) and consumes (control command).
//
// Field layouts are pinned to the EXACT .msg definitions the target Humble
// image ships (extension/msg/**), NOT to any local checkout -- the two diverge.
// Several structs here deliberately differ from an earlier draft's PODs;
// each deviation is annotated inline with the .msg field it was forced by.
// Getting a layout wrong is silent: Autoware would misparse or drop the sample.
//
// AwTopicInfo<T> mirrors CARLA's CdrTopicInfo pattern
// (LibCarla/source/carla/ros2/types/CdrTopicInfo.h): the specializations are
// DECLARED here so every consuming TU (StatusPublishers, GnssPosePublisher,
// ControlSubscribers) sees them, and DEFINED out-of-line in the .cpp -- the one
// place the generated RIHS01 goldens (AwGoldens.inc) are included.

#include <cstddef>
#include <cstdint>
#include <vector>

namespace carla {
namespace autoware {

// builtin_interfaces/Time
struct Time {
  int32_t sec;
  uint32_t nanosec;
};

// std_msgs/Header. Its frame_id string is not stored on the POD: the status
// publishers always emit a fixed frame ("base_link"), written directly by the
// serializer (see .cpp). The stamp is what varies per sample.
struct Header {
  Time stamp;
};

// --- autoware_vehicle_msgs (published by this extension) ---

// VelocityReport.msg: `std_msgs/Header header` + 3×float32 (carries frame_id).
struct VelocityReport {
  Header header;
  float longitudinal_velocity;
  float lateral_velocity;
  float heading_rate;
};

// SteeringReport.msg is a BARE `builtin_interfaces/Time stamp` + float32 --
// there is NO std_msgs/Header and NO frame_id (a naive draft POD/serializer
// wrongly gave it a Header + "base_link"; refuted by SteeringReport.msg line 1).
struct SteeringReport {
  Time stamp;
  float steering_tire_angle;
};

// The four enum reports below are each `builtin_interfaces/Time stamp` + uint8
// (bare Time stamp, no Header/frame_id -- their .msg files confirm).
struct GearReport {
  Time stamp;
  uint8_t report;  // GearReport constants (NONE=0, DRIVE=2, REVERSE=20, PARK=22, ...)
};
struct ControlModeReport {
  Time stamp;
  uint8_t mode;  // AUTONOMOUS=1, MANUAL=4, ...
};
struct TurnIndicatorsReport {
  Time stamp;
  uint8_t report;  // DISABLE=1, ENABLE_LEFT=2, ENABLE_RIGHT=3
};
struct HazardLightsReport {
  Time stamp;
  uint8_t report;  // DISABLE=1, ENABLE=2
};

// --- autoware_control_msgs (consumed by this extension) ---
//
// Lateral.msg / Longitudinal.msg / Control.msg each carry a SECOND
// `builtin_interfaces/Time control_time` field and trailing `bool` flags that
// a naive draft's PODs would omit entirely. They are on the wire, so the
// deserializer MUST account for them or every field after the first gap
// decodes from the wrong offset.
struct Lateral {
  Time stamp;
  Time control_time;
  float steering_tire_angle;
  float steering_tire_rotation_rate;
  bool is_defined_steering_tire_rotation_rate;
};
struct Longitudinal {
  Time stamp;
  Time control_time;
  float velocity;
  float acceleration;
  float jerk;
  bool is_defined_acceleration;
  bool is_defined_jerk;
};
struct Control {
  Time stamp;
  Time control_time;
  Lateral lateral;
  Longitudinal longitudinal;
};

// Per-type metadata (type_name / RIHS01 type_hash). Primary template is
// intentionally undefined -- only the specializations below are valid.
template <typename T>
struct AwTopicInfo;

#define AW_TOPIC_INFO_DECL(T)                        \
  template <>                                        \
  struct AwTopicInfo<T> {                            \
    static const char* type_name();                  \
    static const char* type_hash();                  \
  };
AW_TOPIC_INFO_DECL(VelocityReport)
AW_TOPIC_INFO_DECL(SteeringReport)
AW_TOPIC_INFO_DECL(GearReport)
AW_TOPIC_INFO_DECL(ControlModeReport)
AW_TOPIC_INFO_DECL(TurnIndicatorsReport)
AW_TOPIC_INFO_DECL(HazardLightsReport)
AW_TOPIC_INFO_DECL(Control)
#undef AW_TOPIC_INFO_DECL

// Serializers (publisher side). Each returns the total byte count written
// (including the 4-byte encapsulation header) and overwrites `out`.
size_t cdr_serialize(const VelocityReport&, std::vector<uint8_t>&);
size_t cdr_serialize(const SteeringReport&, std::vector<uint8_t>&);
size_t cdr_serialize(const GearReport&, std::vector<uint8_t>&);
size_t cdr_serialize(const ControlModeReport&, std::vector<uint8_t>&);
size_t cdr_serialize(const TurnIndicatorsReport&, std::vector<uint8_t>&);
size_t cdr_serialize(const HazardLightsReport&, std::vector<uint8_t>&);

// Deserializer (subscriber side). Returns false on truncated/short input
// (never reads out of bounds); on false, `out` is partially/zero populated.
bool cdr_deserialize(const uint8_t*, size_t, Control&);

}  // namespace autoware
}  // namespace carla
