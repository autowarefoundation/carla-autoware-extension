#include <gtest/gtest.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <sensor_msgs/msg/point_cloud2.hpp>

#include "carla/autoware/messages/RosIdl.h"
#include "publishers/BenchCloudPublisher.h"

using namespace carla::autoware;

namespace {

constexpr const char* kEnvVar = "CARLA_BENCH_SEAM_CLOUD";

// ===========================================================================
// Fake host -- same pattern as test_status_publishers.cpp / test_gnss_pose.cpp:
// the host vtable is a struct of C function pointers, so the fakes capture
// into file-scope state (only a non-capturing lambda / free function is
// convertible to a C function pointer). g_state is redirected to the
// per-test fixture instance in SetUp; gtest runs cases serially in-process.
// ===========================================================================

struct FakePub {
  std::string topic;
  std::string type_name;
  std::string type_hash;
  CarlaRos2Qos qos;
};

struct FakeHostState {
  std::vector<FakePub> pubs;  // creation order; handle returned is (index + 1)
  std::vector<std::pair<CarlaRos2PubHandle, std::vector<uint8_t>>> published;
};

FakeHostState* g_state = nullptr;

CarlaRos2PubHandle FakeCreatePublisher(void* /*ctx*/, const char* topic,
                                       const char* type_name, const char* type_hash,
                                       const CarlaRos2Qos* qos) {
  g_state->pubs.push_back(FakePub{topic, type_name, type_hash, *qos});
  return static_cast<CarlaRos2PubHandle>(g_state->pubs.size());  // 1-based; 0 = invalid
}

int FakePublish(void* /*ctx*/, CarlaRos2PubHandle h, const uint8_t* cdr, size_t len) {
  g_state->published.emplace_back(h, std::vector<uint8_t>(cdr, cdr + len));
  return 0;
}

CarlaRos2Host MakeFakeHost() {
  CarlaRos2Host host{};
  host.api_version = CARLA_ROS2_EXTENSION_API_VERSION;
  host.host_ctx = nullptr;
  host.create_publisher = &FakeCreatePublisher;
  host.publish = &FakePublish;
  return host;
}

// HERMETIC $CARLA_BENCH_SEAM_CLOUD, mirroring test_init.cpp's SetMapEnv
// pattern: every case starts with it UNSET regardless of the ambient shell
// (an operator shell running the live CAL-seam gate would export it), and
// the prior value is restored in TearDown so this suite cannot leak state
// into whichever test file gtest happens to run next.
class BenchCloudPublisherTest : public ::testing::Test {
 protected:
  void SetUp() override {
    g_state = &state_;
    const char* prev = std::getenv(kEnvVar);
    had_env_ = prev != nullptr;
    if (had_env_) prev_env_ = prev;
    unsetenv(kEnvVar);
  }
  void TearDown() override {
    if (had_env_) {
      setenv(kEnvVar, prev_env_.c_str(), 1);
    } else {
      unsetenv(kEnvVar);
    }
    g_state = nullptr;
  }

  FakeHostState state_;

 private:
  bool had_env_ = false;
  std::string prev_env_;
};

}  // namespace

// ---------------------------------------------------------------------------
// Production inertness: $CARLA_BENCH_SEAM_CLOUD UNSET means Init() creates no
// publisher and OnTick() never publishes -- the invariant the whole gate
// exists to guarantee (a production run must be byte-identical to before
// this publisher existed).
// ---------------------------------------------------------------------------
TEST_F(BenchCloudPublisherTest, unset_env_var_creates_no_publisher) {
  BenchCloudPublisher pub;
  pub.Init(MakeFakeHost());

  EXPECT_FALSE(pub.IsEnabled());
  EXPECT_TRUE(state_.pubs.empty());

  pub.OnTick();
  pub.OnTick();
  EXPECT_TRUE(state_.published.empty());
}

// Only the exact string "1" enables the gate -- "0", "true", "" must not,
// so an operator's typo (or a shell exporting an empty override) cannot
// silently turn on a bench-only topic in a scored run.
TEST_F(BenchCloudPublisherTest, only_the_literal_value_1_enables_the_gate) {
  for (const char* v : {"0", "true", "TRUE", "yes", ""}) {
    setenv(kEnvVar, v, 1);
    BenchCloudPublisher pub;
    pub.Init(MakeFakeHost());
    EXPECT_FALSE(pub.IsEnabled()) << "value=" << v;
    EXPECT_TRUE(state_.pubs.empty()) << "value=" << v;
    state_.pubs.clear();
  }
}

// ---------------------------------------------------------------------------
// Enabled: exactly one publisher, right topic/type/hash/QoS.
// ---------------------------------------------------------------------------
TEST_F(BenchCloudPublisherTest, env_var_1_creates_the_bench_cloud_publisher) {
  setenv(kEnvVar, "1", 1);
  BenchCloudPublisher pub;
  pub.Init(MakeFakeHost());

  EXPECT_TRUE(pub.IsEnabled());
  ASSERT_EQ(state_.pubs.size(), 1u);
  const FakePub& p = state_.pubs[0];
  EXPECT_EQ(p.topic, "/bench/seam_cloud");
  EXPECT_EQ(p.type_name, dds_type_name<sensor_msgs::msg::PointCloud2>());
  EXPECT_EQ(p.type_hash, rihs01_hash<sensor_msgs::msg::PointCloud2>().c_str());
  // PublisherQos::SensorData() unmodified: best_effort(1) / volatile(0) /
  // keep-last depth 1 -- the fork's CarlaPointCloudPublisher default for a
  // point-cloud publisher with no per-sensor QoS override (CarlaRos2Extension.h
  // field comments: reliability 1 = best_effort, durability 0 = volatile).
  EXPECT_EQ(p.qos.reliability, 1u);
  EXPECT_EQ(p.qos.durability, 0u);
  EXPECT_EQ(p.qos.history_depth, 1u);
}

// ---------------------------------------------------------------------------
// The published message: canonical 28 800-point / 32 B-stride PointXYZIRCAEDT
// layout, zero payload -- byte-for-byte the same field table as the fork's
// kLidarFieldsExtended (PointCloudFieldsLayout.h), which the two bench
// publishers must describe identically for the paired measurement to be
// meaningful.
// ---------------------------------------------------------------------------
TEST_F(BenchCloudPublisherTest, on_tick_first_call_publishes_the_canonical_cloud) {
  setenv(kEnvVar, "1", 1);
  BenchCloudPublisher pub;
  pub.Init(MakeFakeHost());

  pub.OnTick();

  ASSERT_EQ(state_.published.size(), 1u);
  sensor_msgs::msg::PointCloud2 m;
  ASSERT_TRUE(cdr_deserialize(state_.published[0].second.data(),
                               state_.published[0].second.size(), m));

  EXPECT_EQ(m.header.frame_id, "base_link");
  EXPECT_EQ(m.height, 1u);
  EXPECT_EQ(m.width, 28800u);
  EXPECT_FALSE(m.is_bigendian);
  EXPECT_EQ(m.point_step, 32u);
  EXPECT_EQ(m.row_step, 28800u * 32u);
  EXPECT_FALSE(m.is_dense);

  struct Expected {
    const char* name;
    uint32_t offset;
    uint8_t datatype;
  };
  using sensor_msgs::msg::PointField;
  const Expected expected[10] = {
      {"x", 0u, PointField::FLOAT32},          {"y", 4u, PointField::FLOAT32},
      {"z", 8u, PointField::FLOAT32},           {"intensity", 12u, PointField::UINT8},
      {"return_type", 13u, PointField::UINT8},  {"channel", 14u, PointField::UINT16},
      {"azimuth", 16u, PointField::FLOAT32},    {"elevation", 20u, PointField::FLOAT32},
      {"distance", 24u, PointField::FLOAT32},   {"time_stamp", 28u, PointField::UINT32},
  };
  ASSERT_EQ(m.fields.size(), 10u);
  for (int i = 0; i < 10; ++i) {
    EXPECT_EQ(m.fields[i].name, expected[i].name) << "field " << i;
    EXPECT_EQ(m.fields[i].offset, expected[i].offset) << "field " << i;
    EXPECT_EQ(m.fields[i].datatype, expected[i].datatype) << "field " << i;
    EXPECT_EQ(m.fields[i].count, 1u) << "field " << i;
  }

  // Zero payload (contract): the full 28800*32 B buffer is present and every
  // byte is zero.
  ASSERT_EQ(m.data.size(), 921600u);
  EXPECT_TRUE(std::all_of(m.data.begin(), m.data.end(), [](uint8_t b) { return b == 0u; }));
}

// header.stamp is WALL now(), not the sim clock -- OnTick() does not even
// receive a sim_time_s (unlike the other publishers' OnVehicleStatus), so
// this also structurally proves there is no sim-time input to stamp from.
TEST_F(BenchCloudPublisherTest, on_tick_stamps_header_with_wall_clock_now) {
  setenv(kEnvVar, "1", 1);
  BenchCloudPublisher pub;
  pub.Init(MakeFakeHost());

  const auto before_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                             std::chrono::system_clock::now().time_since_epoch())
                             .count();
  pub.OnTick();
  const auto after_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                            std::chrono::system_clock::now().time_since_epoch())
                            .count();

  ASSERT_EQ(state_.published.size(), 1u);
  sensor_msgs::msg::PointCloud2 m;
  ASSERT_TRUE(cdr_deserialize(state_.published[0].second.data(),
                               state_.published[0].second.size(), m));
  const int64_t stamp_ns =
      static_cast<int64_t>(m.header.stamp.sec) * 1000000000LL + m.header.stamp.nanosec;
  EXPECT_GE(stamp_ns, before_ns);
  EXPECT_LE(stamp_ns, after_ns);
}

// ---------------------------------------------------------------------------
// 10 Hz decimation: an immediate second call (well under 100 ms of real wall
// time -- a unit test's whole body runs in microseconds) must NOT publish
// again; once the period has genuinely elapsed, the next call must.
// ---------------------------------------------------------------------------
TEST_F(BenchCloudPublisherTest, on_tick_decimates_to_10hz_by_wall_clock) {
  setenv(kEnvVar, "1", 1);
  BenchCloudPublisher pub;
  pub.Init(MakeFakeHost());

  pub.OnTick();  // first call always publishes
  ASSERT_EQ(state_.published.size(), 1u);

  pub.OnTick();  // immediate re-call: well under the 100 ms period
  EXPECT_EQ(state_.published.size(), 1u);

  std::this_thread::sleep_for(std::chrono::milliseconds(110));
  pub.OnTick();  // period elapsed: must publish again
  EXPECT_EQ(state_.published.size(), 2u);
}
