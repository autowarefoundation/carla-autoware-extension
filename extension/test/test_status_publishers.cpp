#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "carla/autoware/messages/AutowareMessages.h"
#include "carla/autoware/messages/Cdr.h"
#include "publishers/StatusPublishers.h"

using namespace carla::autoware;

// ===========================================================================
// Value helpers (the two free functions the brief pins). Declared in the SAME
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
// sign (the pre-observer brief draft's -0.1f expectation was the double
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

  struct Expected {
    const char* topic;
    const char* type_name;
    const char* type_hash;
  };
  const Expected expected[6] = {
      {"/vehicle/status/velocity_status", AwTopicInfo<VelocityReport>::type_name(),
       AwTopicInfo<VelocityReport>::type_hash()},
      {"/vehicle/status/steering_status", AwTopicInfo<SteeringReport>::type_name(),
       AwTopicInfo<SteeringReport>::type_hash()},
      {"/vehicle/status/gear_status", AwTopicInfo<GearReport>::type_name(),
       AwTopicInfo<GearReport>::type_hash()},
      {"/vehicle/status/control_mode", AwTopicInfo<ControlModeReport>::type_name(),
       AwTopicInfo<ControlModeReport>::type_hash()},
      {"/vehicle/status/turn_indicators_status", AwTopicInfo<TurnIndicatorsReport>::type_name(),
       AwTopicInfo<TurnIndicatorsReport>::type_hash()},
      {"/vehicle/status/hazard_lights_status", AwTopicInfo<HazardLightsReport>::type_name(),
       AwTopicInfo<HazardLightsReport>::type_hash()},
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
    const auto& b = state_.published[0].second;
    CdrReader r(b.data(), b.size());
    EXPECT_EQ(r.i32(), kSec);
    EXPECT_EQ(r.u32(), kNsec);
    EXPECT_EQ(r.str(), "base_link");
    EXPECT_FLOAT_EQ(r.f32(), 3.5f);    // longitudinal_velocity
    EXPECT_FLOAT_EQ(r.f32(), -1.25f);  // lateral_velocity
    EXPECT_FLOAT_EQ(r.f32(), 0.5f);    // heading_rate
    EXPECT_TRUE(r.ok());
  }
  // [1] SteeringReport: bare Time stamp + steering_tire_angle (NO Header/frame_id).
  {
    const auto& b = state_.published[1].second;
    CdrReader r(b.data(), b.size());
    EXPECT_EQ(r.i32(), kSec);
    EXPECT_EQ(r.u32(), kNsec);
    EXPECT_FLOAT_EQ(r.f32(), 0.1f);  // passed through, NOT -0.1f
    EXPECT_TRUE(r.ok());
  }
  // [2] GearReport: bare Time stamp + uint8 report.
  {
    const auto& b = state_.published[2].second;
    CdrReader r(b.data(), b.size());
    EXPECT_EQ(r.i32(), kSec);
    EXPECT_EQ(r.u32(), kNsec);
    EXPECT_EQ(r.u8(), 2u);  // DRIVE from StatusInputs::gear
    EXPECT_TRUE(r.ok());
  }
  // [3] ControlModeReport: bare Time stamp + uint8 mode.
  {
    const auto& b = state_.published[3].second;
    CdrReader r(b.data(), b.size());
    EXPECT_EQ(r.i32(), kSec);
    EXPECT_EQ(r.u32(), kNsec);
    EXPECT_EQ(r.u8(), 1u);  // AUTONOMOUS from StatusInputs::control_mode
    EXPECT_TRUE(r.ok());
  }
  // [4] TurnIndicatorsReport: bare Time stamp + uint8 report.
  {
    const auto& b = state_.published[4].second;
    CdrReader r(b.data(), b.size());
    EXPECT_EQ(r.i32(), kSec);
    EXPECT_EQ(r.u32(), kNsec);
    EXPECT_EQ(r.u8(), 2u);  // ENABLE_LEFT from StatusInputs::turn_indicators
    EXPECT_TRUE(r.ok());
  }
  // [5] HazardLightsReport: bare Time stamp + uint8 report.
  {
    const auto& b = state_.published[5].second;
    CdrReader r(b.data(), b.size());
    EXPECT_EQ(r.i32(), kSec);
    EXPECT_EQ(r.u32(), kNsec);
    EXPECT_EQ(r.u8(), 2u);  // ENABLE from StatusInputs::hazard_lights
    EXPECT_TRUE(r.ok());
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
  auto tail_u8 = [](const std::vector<uint8_t>& b) {
    CdrReader r(b.data(), b.size());
    (void)r.i32();  // stamp.sec
    (void)r.u32();  // stamp.nanosec
    return r.u8();
  };
  EXPECT_EQ(tail_u8(state_.published[2].second), 0u);  // gear NONE
  EXPECT_EQ(tail_u8(state_.published[3].second), 4u);  // control_mode MANUAL
  EXPECT_EQ(tail_u8(state_.published[4].second), 1u);  // turn_indicators DISABLE
  EXPECT_EQ(tail_u8(state_.published[5].second), 1u);  // hazard_lights DISABLE
}
