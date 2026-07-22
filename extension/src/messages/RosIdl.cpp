#include "carla/autoware/messages/RosIdl.h"

#include <cstdio>

#include <fastcdr/Cdr.h>
#include <fastcdr/FastBuffer.h>
#include <fastcdr/exceptions/Exception.h>
#include <rosidl_runtime_c/type_hash.h>
#include <rosidl_typesupport_cpp/message_type_support.hpp>

#include <autoware_control_msgs/msg/control.hpp>
#include <autoware_control_msgs/msg/detail/control__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/control_mode_report.hpp>
#include <autoware_vehicle_msgs/msg/detail/control_mode_report__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/detail/engage__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/detail/gear_command__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/detail/gear_report__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/detail/hazard_lights_command__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/detail/hazard_lights_report__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/detail/steering_report__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/detail/turn_indicators_command__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/detail/turn_indicators_report__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/detail/velocity_report__rosidl_typesupport_fastrtps_cpp.hpp>
#include <autoware_vehicle_msgs/msg/engage.hpp>
#include <autoware_vehicle_msgs/msg/gear_command.hpp>
#include <autoware_vehicle_msgs/msg/gear_report.hpp>
#include <autoware_vehicle_msgs/msg/hazard_lights_command.hpp>
#include <autoware_vehicle_msgs/msg/hazard_lights_report.hpp>
#include <autoware_vehicle_msgs/msg/steering_report.hpp>
#include <autoware_vehicle_msgs/msg/turn_indicators_command.hpp>
#include <autoware_vehicle_msgs/msg/turn_indicators_report.hpp>
#include <autoware_vehicle_msgs/msg/velocity_report.hpp>
#include <geometry_msgs/msg/detail/pose_stamped__rosidl_typesupport_fastrtps_cpp.hpp>
#include <geometry_msgs/msg/detail/pose_with_covariance_stamped__rosidl_typesupport_fastrtps_cpp.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>

namespace carla {
namespace autoware {
namespace {

// XCDRv1 == classic PLAIN_CDR for these final, fixed-layout messages; the
// serialize_encapsulation() call writes the 4-byte header (LE: 00 01 00 00)
// the host contract requires.
template <typename T, typename SerFn, typename SizeFn>
size_t serialize_impl(const T& m, std::vector<uint8_t>& out, SerFn serialize,
                      SizeFn serialized_size) {
  out.assign(4 + serialized_size(m, 0), 0);
  eprosima::fastcdr::FastBuffer fb(reinterpret_cast<char*>(out.data()), out.size());
  eprosima::fastcdr::Cdr cdr(fb, eprosima::fastcdr::Cdr::DEFAULT_ENDIAN,
                             eprosima::fastcdr::CdrVersion::XCDRv1);
  cdr.serialize_encapsulation();
  serialize(m, cdr);
  out.resize(cdr.get_serialized_data_length());
  return out.size();
}

// fastcdr signals truncated/malformed input via exceptions; map them to the
// bool verdict the subscriber callbacks act on. read_encapsulation() adapts
// the reader to the header's endianness, and positional reads simply leave
// any trailing DDS padding unconsumed.
template <typename T, typename DesFn>
bool deserialize_impl(const uint8_t* p, size_t n, T& m, DesFn deserialize) {
  if (p == nullptr || n < 4) {
    return false;
  }
  try {
    eprosima::fastcdr::FastBuffer fb(const_cast<char*>(reinterpret_cast<const char*>(p)), n);
    eprosima::fastcdr::Cdr cdr(fb, eprosima::fastcdr::Cdr::DEFAULT_ENDIAN,
                               eprosima::fastcdr::CdrVersion::XCDRv1);
    cdr.read_encapsulation();
    return deserialize(cdr, m);
  } catch (const eprosima::fastcdr::exception::Exception&) {
    return false;
  }
}

template <typename T>
std::string rihs01_impl() {
  const rosidl_message_type_support_t* ts =
      rosidl_typesupport_cpp::get_message_type_support_handle<T>();
  const rosidl_type_hash_t* h = ts->get_type_hash_func(ts);
  char buf[7 + 2 * ROSIDL_TYPE_HASH_SIZE + 1] = "RIHS01_";
  for (int i = 0; i < ROSIDL_TYPE_HASH_SIZE; ++i) {
    std::snprintf(buf + 7 + 2 * i, 3, "%02x", h->value[i]);
  }
  return std::string(buf, 7 + 2 * ROSIDL_TYPE_HASH_SIZE);
}

}  // namespace

// One block per bridged type: the four specializations, delegating to the
// package's generated typesupport_fastrtps_cpp functions.
#define CARLA_AW_BRIDGE(PKG, TYPE, DDS_NAME)                                    \
  template <>                                                                   \
  const char* dds_type_name<PKG::msg::TYPE>() {                                 \
    return DDS_NAME;                                                            \
  }                                                                             \
  template <>                                                                   \
  const std::string& rihs01_hash<PKG::msg::TYPE>() {                            \
    static const std::string h = rihs01_impl<PKG::msg::TYPE>();                 \
    return h;                                                                   \
  }                                                                             \
  template <>                                                                   \
  size_t cdr_serialize<PKG::msg::TYPE>(const PKG::msg::TYPE& m,                 \
                                       std::vector<uint8_t>& out) {             \
    return serialize_impl(                                                      \
        m, out,                                                                 \
        [](const PKG::msg::TYPE& x, eprosima::fastcdr::Cdr& c) {                \
          return PKG::msg::typesupport_fastrtps_cpp::cdr_serialize(x, c);       \
        },                                                                      \
        [](const PKG::msg::TYPE& x, size_t a) {                                 \
          return PKG::msg::typesupport_fastrtps_cpp::get_serialized_size(x, a); \
        });                                                                     \
  }                                                                             \
  template <>                                                                   \
  bool cdr_deserialize<PKG::msg::TYPE>(const uint8_t* p, size_t n,              \
                                       PKG::msg::TYPE& m) {                     \
    return deserialize_impl(p, n, m,                                            \
                            [](eprosima::fastcdr::Cdr& c, PKG::msg::TYPE& x) {  \
                              return PKG::msg::typesupport_fastrtps_cpp::       \
                                  cdr_deserialize(c, x);                        \
                            });                                                 \
  }

CARLA_AW_BRIDGE(autoware_vehicle_msgs, VelocityReport,
                "autoware_vehicle_msgs::msg::dds_::VelocityReport_")
CARLA_AW_BRIDGE(autoware_vehicle_msgs, SteeringReport,
                "autoware_vehicle_msgs::msg::dds_::SteeringReport_")
CARLA_AW_BRIDGE(autoware_vehicle_msgs, GearReport,
                "autoware_vehicle_msgs::msg::dds_::GearReport_")
CARLA_AW_BRIDGE(autoware_vehicle_msgs, ControlModeReport,
                "autoware_vehicle_msgs::msg::dds_::ControlModeReport_")
CARLA_AW_BRIDGE(autoware_vehicle_msgs, TurnIndicatorsReport,
                "autoware_vehicle_msgs::msg::dds_::TurnIndicatorsReport_")
CARLA_AW_BRIDGE(autoware_vehicle_msgs, HazardLightsReport,
                "autoware_vehicle_msgs::msg::dds_::HazardLightsReport_")
CARLA_AW_BRIDGE(autoware_vehicle_msgs, GearCommand,
                "autoware_vehicle_msgs::msg::dds_::GearCommand_")
CARLA_AW_BRIDGE(autoware_vehicle_msgs, TurnIndicatorsCommand,
                "autoware_vehicle_msgs::msg::dds_::TurnIndicatorsCommand_")
CARLA_AW_BRIDGE(autoware_vehicle_msgs, HazardLightsCommand,
                "autoware_vehicle_msgs::msg::dds_::HazardLightsCommand_")
CARLA_AW_BRIDGE(autoware_vehicle_msgs, Engage,
                "autoware_vehicle_msgs::msg::dds_::Engage_")
CARLA_AW_BRIDGE(autoware_control_msgs, Control,
                "autoware_control_msgs::msg::dds_::Control_")
CARLA_AW_BRIDGE(geometry_msgs, PoseStamped,
                "geometry_msgs::msg::dds_::PoseStamped_")
CARLA_AW_BRIDGE(geometry_msgs, PoseWithCovarianceStamped,
                "geometry_msgs::msg::dds_::PoseWithCovarianceStamped_")
#undef CARLA_AW_BRIDGE

}  // namespace autoware
}  // namespace carla
