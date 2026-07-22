#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include <autoware_vehicle_msgs/msg/control_mode_report.hpp>
#include <autoware_vehicle_msgs/msg/gear_report.hpp>
#include <autoware_vehicle_msgs/msg/hazard_lights_report.hpp>
#include <autoware_vehicle_msgs/msg/steering_report.hpp>
#include <autoware_vehicle_msgs/msg/turn_indicators_report.hpp>
#include <autoware_vehicle_msgs/msg/velocity_report.hpp>

#include "carla/autoware/messages/RosIdl.h"
#include "publishers/StatusPublishers.h"

using namespace carla::autoware;

// ===========================================================================
// Value helpers (the two free functions under test). Declared in the SAME
// namespace they are defined in (StatusPublishers.cpp) so they link -- a bare
// global-scope declaration would NOT resolve against the namespaced definition.
// ===========================================================================
namespace carla {
namespace autoware {
float steering_report_tire_angle(double view_steering_tire_angle_rad);
float velocity_report_longitudinal(double body_velocity_mps);
}  // namespace autoware
}  // namespace carla

// The CARLA-side host ALREADY converts the FL wheel angle into the Autoware
// convention (positive = left) before it reaches the view -- see
// CarlaRos2Extension.h: steering_tire_angle_rad "positive = left (Autoware
// convention, already applied by the host -- do NOT negate again)". So the
// extension passes the view value through UNCHANGED; it must NOT re-flip the
// sign (an earlier pre-observer draft's -0.1f expectation was the double
// negation this corrects).
TEST(status, steering_angle_is_passed_through_not_flipped) {
  EXPECT_FLOAT_EQ(steering_report_tire_angle(0.1), 0.1f);
  EXPECT_FLOAT_EQ(steering_report_tire_angle(-0.2), -0.2f);
}

TEST(status, velocity_is_longitudinal_body_frame) {
  EXPECT_FLOAT_EQ(velocity_report_longitudinal(3.5), 3.5f);
}

// ===========================================================================
// Fake host: the host vtable is a struct of C function pointers, so the fakes
// capture into file-scope state (a non-capturing lambda / free function is the
// only thing convertible to a C function pointer). g_state is redirected to the
// per-test fixture instance in SetUp; gtest runs cases serially in-process.
// ===========================================================================
namespace {

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

class StatusPublishersTest : public ::testing::Test {
 protected:
  void SetUp() override { g_state = &state_; }
  void TearDown() override { g_state = nullptr; }
  FakeHostState state_;
};

}  // namespace

// ---------------------------------------------------------------------------
// Init wires exactly six publishers: right topic, right AwTopicInfo type name /
// hash, and the status QoS (reliable / volatile / keep-last-1) on every one.
// ---------------------------------------------------------------------------
TEST_F(StatusPublishersTest, init_creates_six_publishers_with_topics_typeinfo_and_qos) {
  StatusPublishers pub;
  pub.Init(MakeFakeHost());

  ASSERT_EQ(state_.pubs.size(), 6u);

  using autoware_vehicle_msgs::msg::ControlModeReport;
  using autoware_vehicle_msgs::msg::GearReport;
  using autoware_vehicle_msgs::msg::HazardLightsReport;
  using autoware_vehicle_msgs::msg::SteeringReport;
  using autoware_vehicle_msgs::msg::TurnIndicatorsReport;
  using autoware_vehicle_msgs::msg::VelocityReport;

  struct Expected {
    const char* topic;
    const char* type_name;
    const char* type_hash;
  };
  const Expected expected[6] = {
      {"/vehicle/status/velocity_status", dds_type_name<VelocityReport>(),
       rihs01_hash<VelocityReport>().c_str()},
      {"/vehicle/status/steering_status", dds_type_name<SteeringReport>(),
       rihs01_hash<SteeringReport>().c_str()},
      {"/vehicle/status/gear_status", dds_type_name<GearReport>(),
       rihs01_hash<GearReport>().c_str()},
      {"/vehicle/status/control_mode", dds_type_name<ControlModeReport>(),
       rihs01_hash<ControlModeReport>().c_str()},
      {"/vehicle/status/turn_indicators_status", dds_type_name<TurnIndicatorsReport>(),
       rihs01_hash<TurnIndicatorsReport>().c_str()},
      {"/vehicle/status/hazard_lights_status", dds_type_name<HazardLightsReport>(),
       rihs01_hash<HazardLightsReport>().c_str()},
  };

  for (int i = 0; i < 6; ++i) {
    const FakePub& p = state_.pubs[i];
    EXPECT_EQ(p.topic, expected[i].topic) << "topic mismatch at index " << i;
    EXPECT_EQ(p.type_name, expected[i].type_name) << "type_name mismatch at index " << i;
    EXPECT_EQ(p.type_hash, expected[i].type_hash) << "type_hash mismatch at index " << i;
    // Status QoS: reliability 0 = RELIABLE, durability 0 = VOLATILE,
    // history_depth 1 = KEEP_LAST depth 1 (CarlaRos2Extension.h field comments).
    EXPECT_EQ(p.qos.reliability, 0u) << "reliability at index " << i;
    EXPECT_EQ(p.qos.durability, 0u) << "durability at index " << i;
    EXPECT_EQ(p.qos.history_depth, 1u) << "history_depth at index " << i;
  }
}

// ---------------------------------------------------------------------------
// OnVehicleStatus publishes exactly six samples, in the creation order, whose
// CDR bytes parse back to the expected field values: velocity/lateral/heading
// from the view, steering passed through unchanged, gear/mode/turn/hazard from
// StatusInputs, and every stamp = sim_time split into (sec, nanosec).
// ---------------------------------------------------------------------------
TEST_F(StatusPublishersTest, on_vehicle_status_publishes_six_samples_with_expected_fields) {
  StatusPublishers pub;
  pub.Init(MakeFakeHost());
  ASSERT_EQ(state_.pubs.size(), 6u);

  CarlaRos2VehicleStatusView v{};
  v.velocity_mps = 3.5;
  v.lateral_velocity_mps = -1.25;
  v.yaw_rate_rps = 0.5;
  v.steering_tire_angle_rad = 0.1;  // already Autoware-signed by the host
  v.sim_time_s = 12.5;              // fractional: -> sec 12, nanosec 500000000

  StatusInputs in{};
  in.control_mode = 1;    // AUTONOMOUS (non-default, proves engage threading)
  in.gear = 2;            // DRIVE
  in.turn_indicators = 2; // ENABLE_LEFT
  in.hazard_lights = 2;   // ENABLE

  pub.OnVehicleStatus(v, in);

  ASSERT_EQ(state_.published.size(), 6u);
  // Publish order matches Init creation order, so handle == index + 1.
  for (int i = 0; i < 6; ++i) {
    EXPECT_EQ(state_.published[i].first, static_cast<CarlaRos2PubHandle>(i + 1))
        << "publish handle/order mismatch at index " << i;
  }

  const int32_t kSec = 12;
  const uint32_t kNsec = 500000000u;

  // [0] VelocityReport: Header stamp + frame_id "base_link" + 3 floats.
  {
    autoware_vehicle_msgs::msg::VelocityReport m;
    const auto& bytes = state_.published[0].second;
    ASSERT_TRUE(cdr_deserialize(bytes.data(), bytes.size(), m));
    EXPECT_EQ(m.header.stamp.sec, kSec);
    EXPECT_EQ(m.header.stamp.nanosec, kNsec);
    EXPECT_EQ(m.header.frame_id, "base_link");
    EXPECT_FLOAT_EQ(m.longitudinal_velocity, 3.5f);
    EXPECT_FLOAT_EQ(m.lateral_velocity, -1.25f);
    EXPECT_FLOAT_EQ(m.heading_rate, 0.5f);
  }
  // [1] SteeringReport: bare Time stamp + steering_tire_angle (NO Header/frame_id).
  {
    autoware_vehicle_msgs::msg::SteeringReport m;
    const auto& bytes = state_.published[1].second;
    ASSERT_TRUE(cdr_deserialize(bytes.data(), bytes.size(), m));
    EXPECT_EQ(m.stamp.sec, kSec);
    EXPECT_EQ(m.stamp.nanosec, kNsec);
    EXPECT_FLOAT_EQ(m.steering_tire_angle, 0.1f);  // passed through, NOT -0.1f
  }
  // [2] GearReport: bare Time stamp + uint8 report.
  {
    autoware_vehicle_msgs::msg::GearReport m;
    const auto& bytes = state_.published[2].second;
    ASSERT_TRUE(cdr_deserialize(bytes.data(), bytes.size(), m));
    EXPECT_EQ(m.stamp.sec, kSec);
    EXPECT_EQ(m.stamp.nanosec, kNsec);
    EXPECT_EQ(m.report, 2u);  // DRIVE from StatusInputs::gear
  }
  // [3] ControlModeReport: bare Time stamp + uint8 mode.
  {
    autoware_vehicle_msgs::msg::ControlModeReport m;
    const auto& bytes = state_.published[3].second;
    ASSERT_TRUE(cdr_deserialize(bytes.data(), bytes.size(), m));
    EXPECT_EQ(m.stamp.sec, kSec);
    EXPECT_EQ(m.stamp.nanosec, kNsec);
    EXPECT_EQ(m.mode, 1u);  // AUTONOMOUS from StatusInputs::control_mode
  }
  // [4] TurnIndicatorsReport: bare Time stamp + uint8 report.
  {
    autoware_vehicle_msgs::msg::TurnIndicatorsReport m;
    const auto& bytes = state_.published[4].second;
    ASSERT_TRUE(cdr_deserialize(bytes.data(), bytes.size(), m));
    EXPECT_EQ(m.stamp.sec, kSec);
    EXPECT_EQ(m.stamp.nanosec, kNsec);
    EXPECT_EQ(m.report, 2u);  // ENABLE_LEFT from StatusInputs::turn_indicators
  }
  // [5] HazardLightsReport: bare Time stamp + uint8 report.
  {
    autoware_vehicle_msgs::msg::HazardLightsReport m;
    const auto& bytes = state_.published[5].second;
    ASSERT_TRUE(cdr_deserialize(bytes.data(), bytes.size(), m));
    EXPECT_EQ(m.stamp.sec, kSec);
    EXPECT_EQ(m.stamp.nanosec, kNsec);
    EXPECT_EQ(m.report, 2u);  // ENABLE from StatusInputs::hazard_lights
  }
}

// StatusInputs defaults must be the safe idle/manual state (a frame before any
// command still yields coherent status): MANUAL, gear NONE, indicators DISABLE.
TEST_F(StatusPublishersTest, on_vehicle_status_uses_safe_defaults_for_uncommanded_inputs) {
  StatusPublishers pub;
  pub.Init(MakeFakeHost());

  CarlaRos2VehicleStatusView v{};
  v.sim_time_s = 0.0;
  pub.OnVehicleStatus(v, StatusInputs{});

  ASSERT_EQ(state_.published.size(), 6u);

  autoware_vehicle_msgs::msg::GearReport gear_m;
  ASSERT_TRUE(cdr_deserialize(state_.published[2].second.data(),
                               state_.published[2].second.size(), gear_m));
  EXPECT_EQ(gear_m.report, 0u);  // gear NONE

  autoware_vehicle_msgs::msg::ControlModeReport mode_m;
  ASSERT_TRUE(cdr_deserialize(state_.published[3].second.data(),
                               state_.published[3].second.size(), mode_m));
  EXPECT_EQ(mode_m.mode, 4u);  // control_mode MANUAL

  autoware_vehicle_msgs::msg::TurnIndicatorsReport turn_m;
  ASSERT_TRUE(cdr_deserialize(state_.published[4].second.data(),
                               state_.published[4].second.size(), turn_m));
  EXPECT_EQ(turn_m.report, 1u);  // turn_indicators DISABLE

  autoware_vehicle_msgs::msg::HazardLightsReport hazard_m;
  ASSERT_TRUE(cdr_deserialize(state_.published[5].second.data(),
                               state_.published[5].second.size(), hazard_m));
  EXPECT_EQ(hazard_m.report, 1u);  // hazard_lights DISABLE
}
