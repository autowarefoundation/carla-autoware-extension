#include "BenchCloudPublisher.h"

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>

#include <builtin_interfaces/msg/time.hpp>

#include "carla/autoware/messages/RosIdl.h"

namespace carla {
namespace autoware {

namespace {

constexpr const char* kEnvVar = "CARLA_BENCH_SEAM_CLOUD";
constexpr const char* kTopic = "/bench/seam_cloud";
constexpr const char* kFrameId = "base_link";

// Canonical Autoware PointXYZIRCAEDT layout: byte-for-byte the SAME field
// table as the fork's kLidarFieldsExtended (LibCarla/source/carla/ros2/
// publishers/PointCloudFieldsLayout.h) -- the two bench publishers must
// describe an identical wire message, not merely an identically-sized one.
constexpr uint32_t kPointStep = 32u;
constexpr uint32_t kPointCount = 28800u;
constexpr std::chrono::milliseconds kPeriod{100};  // 10 Hz

// CAL-seam QoS: PublisherQos::SensorData() unmodified (best_effort /
// volatile / keep-last depth 1) -- the fork's CarlaPointCloudPublisher
// default when a point-cloud publisher is constructed with no per-sensor
// override, which /bench/incore_cloud is (it is not a registered actor).
// CarlaRos2Extension.h documents the field encoding: reliability 1 =
// best_effort, durability 0 = volatile.
CarlaRos2Qos BenchCloudQos() {
  return CarlaRos2Qos{/*reliability=*/1u, /*durability=*/0u, /*history_depth=*/1u};
}

sensor_msgs::msg::PointField MakeField(const char* name, uint32_t offset, uint8_t datatype) {
  sensor_msgs::msg::PointField f;
  f.name = name;
  f.offset = offset;
  f.datatype = datatype;
  f.count = 1u;
  return f;
}

// Builds the fixed-size preallocated message once: field table, dimensions
// and the all-zero data buffer never change again -- only OnTick()'s
// header.stamp write touches this object after this point.
sensor_msgs::msg::PointCloud2 MakeCloudTemplate() {
  using sensor_msgs::msg::PointField;
  sensor_msgs::msg::PointCloud2 m;
  m.header.frame_id = kFrameId;
  m.height = 1u;
  m.width = kPointCount;
  m.is_bigendian = false;
  m.point_step = kPointStep;
  m.row_step = kPointCount * kPointStep;
  // is_dense=false matches the fork's CarlaPointCloudPublisher convention
  // (CarlaPointCloudPublisher.cpp: "upstream convention... subscribers must
  // not assume tightly packed valid data"); irrelevant to a zero-payload
  // cloud but kept identical for a byte-for-byte matching message.
  m.is_dense = false;
  m.fields = {
      MakeField("x", 0u, PointField::FLOAT32),
      MakeField("y", 4u, PointField::FLOAT32),
      MakeField("z", 8u, PointField::FLOAT32),
      MakeField("intensity", 12u, PointField::UINT8),
      MakeField("return_type", 13u, PointField::UINT8),
      MakeField("channel", 14u, PointField::UINT16),
      MakeField("azimuth", 16u, PointField::FLOAT32),
      MakeField("elevation", 20u, PointField::FLOAT32),
      MakeField("distance", 24u, PointField::FLOAT32),
      MakeField("time_stamp", 28u, PointField::UINT32),
  };
  // Zero payload (contract): allocated once, never rewritten.
  m.data.assign(static_cast<std::size_t>(m.row_step), 0u);
  return m;
}

bool IsEnvEnabled(const char* var) {
  const char* v = std::getenv(var);
  return v != nullptr && std::strcmp(v, "1") == 0;
}

}  // namespace

void BenchCloudPublisher::Init(const CarlaRos2Host& host) {
  enabled_ = IsEnvEnabled(kEnvVar);
  if (!enabled_) {
    // Production behaviour (env var unset) must be byte-identical to
    // before this publisher existed: no publisher created, no state built.
    return;
  }
  host_ = host;
  const CarlaRos2Qos qos = BenchCloudQos();
  pub_ = host_.create_publisher(host_.host_ctx, kTopic,
                                dds_type_name<sensor_msgs::msg::PointCloud2>(),
                                rihs01_hash<sensor_msgs::msg::PointCloud2>().c_str(), &qos);
  msg_ = MakeCloudTemplate();
}

void BenchCloudPublisher::OnTick() {
  if (!enabled_) {
    return;
  }
  const auto now = std::chrono::steady_clock::now();
  if (has_published_ && (now - last_pub_) < kPeriod) {
    return;
  }
  has_published_ = true;
  last_pub_ = now;

  // header.stamp = wall now() (contract): both bench publishers stamp with
  // the same host's wall clock, so their paired one-hop latency
  // (arrival_system_ns - header_stamp_ns) needs no sim/wall conversion.
  const int64_t wall_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                              std::chrono::system_clock::now().time_since_epoch())
                              .count();
  msg_.header.stamp.sec = static_cast<int32_t>(wall_ns / 1000000000LL);
  msg_.header.stamp.nanosec = static_cast<uint32_t>(wall_ns % 1000000000LL);

  std::vector<uint8_t> buf;
  cdr_serialize(msg_, buf);
  host_.publish(host_.host_ctx, pub_, buf.data(), buf.size());
}

}  // namespace autoware
}  // namespace carla
