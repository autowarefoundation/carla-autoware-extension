#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include <autoware_control_msgs/msg/control.hpp>
#include <autoware_vehicle_msgs/msg/gear_command.hpp>
#include <autoware_vehicle_msgs/msg/hazard_lights_command.hpp>
#include <autoware_vehicle_msgs/msg/turn_indicators_command.hpp>

#include "carla/autoware/control/AutowareSteeringCompensation.h"
#include "carla/autoware/messages/RosIdl.h"
#include "carla/ros2/extension/CarlaRos2Extension.h"
#include "subscribers/ControlSubscribers.h"

using namespace carla::autoware;

// ===========================================================================
// Steering-compensation table fidelity (ported tier4 lookup table).
//
// GetSteeringInput is the INVERSE lookup (key = observed "actual" column, value
// = commanded "desired" column): given Autoware's target tire angle it returns
// the CARLA input to command. GetSteeringOutput is the FORWARD lookup (key =
// desired, value = actual) and is exercised here purely for the round-trip
// property. Expectations are derived FROM the tier4 data points, not guessed.
// ===========================================================================

TEST(steering_compensation, inverse_lookup_recovers_commanded_input) {
  // Row (desired=1.0, actual=0.700223224833506): feeding the observed actual
  // back through the inverse lookup must recover the commanded 1.0.
  EXPECT_NEAR(GetSteeringInput(0.700223224833506f), 1.0f, 1e-4f);
}

TEST(steering_compensation, forward_lookup_maps_desired_to_actual) {
  EXPECT_NEAR(GetSteeringOutput(1.0f), 0.700223224833506f, 1e-4f);
}

TEST(steering_compensation, below_first_point_interpolates_linearly_from_zero) {
  // First data point is (0.01, 6.7395889065761E-05). Halfway to it (0.005) the
  // forward lookup lerps from 0 -> first actual, i.e. half the first actual.
  EXPECT_NEAR(GetSteeringOutput(0.005f), 6.7395889065761E-05f / 2.0f, 1e-9f);
}

TEST(steering_compensation, clamps_at_or_above_last_point) {
  // Last actual is 1.05646350419544; any target at/above it clamps to the last
  // commanded desired (1.2). GetSteeringInput(1.2) therefore returns 1.2.
  EXPECT_FLOAT_EQ(GetSteeringInput(1.2f), 1.2f);
}

TEST(steering_compensation, is_odd_symmetric_in_sign) {
  for (float x : {0.05f, 0.3f, 0.75f, 1.5f}) {
    EXPECT_FLOAT_EQ(GetSteeringInput(-x), -GetSteeringInput(x)) << "x=" << x;
    EXPECT_FLOAT_EQ(GetSteeringOutput(-x), -GetSteeringOutput(x)) << "x=" << x;
  }
}

TEST(steering_compensation, forward_then_inverse_is_identity_on_mid_range) {
  // Within a single linear segment the two lookups are exact inverses.
  for (float x : {0.1f, 0.2f, 0.4f, 0.6f}) {
    EXPECT_NEAR(GetSteeringOutput(GetSteeringInput(x)), x, 1e-3f) << "x=" << x;
  }
}

// ===========================================================================
// Control -> Ackermann conversion (pure function).
// ===========================================================================

TEST(control_conversion, longitudinal_maps_speed_accel_jerk) {
  autoware_control_msgs::msg::Control c;
  c.longitudinal.velocity = 5.0f;
  c.longitudinal.acceleration = 1.5f;
  c.longitudinal.jerk = 0.25f;
  const CarlaRos2AckermannPod p = control_to_ackermann(c);
  // Plan contract (deviation from tier4's acceleration-only path): all three
  // longitudinal fields are forwarded into CARLA's target-based Ackermann pod.
  EXPECT_FLOAT_EQ(p.speed, 5.0f);
  EXPECT_FLOAT_EQ(p.acceleration, 1.5f);
  EXPECT_FLOAT_EQ(p.jerk, 0.25f);
}

TEST(control_conversion, steering_is_sign_flipped_and_compensated) {
  autoware_control_msgs::msg::Control c;
  c.lateral.steering_tire_angle = 0.2f;  // Autoware positive = left
  const CarlaRos2AckermannPod p = control_to_ackermann(c);
  // Autoware +left -> CARLA -steer; magnitude is the inverse-lookup compensation
  // of the target angle. Asserted via the function, not a hardcoded constant.
  EXPECT_LT(p.steer, 0.0f);
  EXPECT_FLOAT_EQ(p.steer, GetSteeringInput(-0.2f));
  EXPECT_NEAR(std::abs(p.steer), GetSteeringInput(0.2f), 1e-4f);
  EXPECT_NEAR(GetSteeringInput(0.2f), 0.542282f, 1e-3f);  // sanity vs the real table
}

TEST(control_conversion, negative_target_yields_positive_carla_steer) {
  autoware_control_msgs::msg::Control c;
  c.lateral.steering_tire_angle = -0.2f;
  const CarlaRos2AckermannPod p = control_to_ackermann(c);
  EXPECT_GT(p.steer, 0.0f);
  EXPECT_FLOAT_EQ(p.steer, GetSteeringInput(0.2f));
}

TEST(control_conversion, steer_speed_zero_when_rate_undefined) {
  autoware_control_msgs::msg::Control c;
  c.lateral.steering_tire_rotation_rate = 1.0f;
  c.lateral.is_defined_steering_tire_rotation_rate = false;
  const CarlaRos2AckermannPod p = control_to_ackermann(c);
  EXPECT_FLOAT_EQ(p.steer_speed, 0.0f);
}

TEST(control_conversion, steer_speed_negated_when_rate_defined) {
  autoware_control_msgs::msg::Control c;
  c.lateral.steering_tire_rotation_rate = 0.3f;
  c.lateral.is_defined_steering_tire_rotation_rate = true;
  const CarlaRos2AckermannPod p = control_to_ackermann(c);
  EXPECT_FLOAT_EQ(p.steer_speed, -0.3f);  // same axis convention as steering
}

// ===========================================================================
// Fake host: the host vtable is a struct of C function pointers, so the fakes
// capture into file-scope state (only a non-capturing lambda / free function is
// convertible to a C function pointer). g_state is redirected to the per-test
// fixture instance in SetUp; gtest runs cases serially in-process.
// ===========================================================================
namespace {

struct FakeSub {
  std::string topic;
  std::string type_name;
  std::string type_hash;
  CarlaRos2Qos qos;
  CarlaRos2SubCallback cb;
  void* user;
};

struct FakeHostState {
  std::vector<FakeSub> subs;  // creation order; handle returned is (index + 1)
  uint32_t ego_id = 0;
  std::vector<std::pair<uint32_t, CarlaRos2AckermannPod>> applied;
};

FakeHostState* g_state = nullptr;

CarlaRos2SubHandle FakeCreateSubscriber(void* /*ctx*/, const char* topic,
                                        const char* type_name, const char* type_hash,
                                        const CarlaRos2Qos* qos, CarlaRos2SubCallback cb,
                                        void* user) {
  g_state->subs.push_back(FakeSub{topic, type_name, type_hash, *qos, cb, user});
  return static_cast<CarlaRos2SubHandle>(g_state->subs.size());  // 1-based; 0 = invalid
}

uint32_t FakeGetEgoActorId(void* /*ctx*/) { return g_state->ego_id; }

void FakeApplyAckermann(void* /*ctx*/, uint32_t actor_id, const CarlaRos2AckermannPod* pod) {
  g_state->applied.emplace_back(actor_id, *pod);
}

CarlaRos2Host MakeFakeHost() {
  CarlaRos2Host host{};
  host.api_version = CARLA_ROS2_EXTENSION_API_VERSION;
  host.host_ctx = nullptr;
  host.create_subscriber = &FakeCreateSubscriber;
  host.get_ego_actor_id = &FakeGetEgoActorId;
  host.apply_ackermann_control = &FakeApplyAckermann;
  return host;
}

// Byte-exact Control CDR buffer via the rosidl codec (replaces the former hand
// serializer now that Control is a generated message type).
std::vector<uint8_t> serialize_control(const autoware_control_msgs::msg::Control& c) {
  std::vector<uint8_t> b;
  cdr_serialize(c, b);
  return b;
}

// GearCommand/TurnIndicatorsCommand/HazardLightsCommand are all
// { builtin_interfaces/Time stamp; uint8 command }; CmdT selects the concrete
// generated type so the codec picks the right rosidl typesupport.
template <typename CmdT>
std::vector<uint8_t> serialize_command(int32_t sec, uint32_t nsec, uint8_t cmd) {
  CmdT m;
  m.stamp.sec = sec;
  m.stamp.nanosec = nsec;
  m.command = cmd;
  std::vector<uint8_t> b;
  cdr_serialize(m, b);
  return b;
}

class ControlSubscribersTest : public ::testing::Test {
 protected:
  void SetUp() override { g_state = &state_; }
  void TearDown() override { g_state = nullptr; }
  FakeHostState state_;
};

}  // namespace

// ---------------------------------------------------------------------------
// Init wires exactly four subscribers: control_cmd with the REAL Control golden,
// and the three *_cmd command topics with hand-authored type names + "" hash,
// all at best_effort / volatile / keep-last-1 QoS.
// ---------------------------------------------------------------------------
TEST_F(ControlSubscribersTest, init_creates_four_subscribers_with_topics_typeinfo_and_qos) {
  ControlSubscribers sub;
  sub.Init(MakeFakeHost());

  ASSERT_EQ(state_.subs.size(), 4u);

  struct Expected {
    const char* topic;
    const char* type_name;
    const char* type_hash;
  };
  const Expected expected[4] = {
      {"/control/command/control_cmd", dds_type_name<autoware_control_msgs::msg::Control>(),
       rihs01_hash<autoware_control_msgs::msg::Control>().c_str()},
      {"/control/command/gear_cmd", "autoware_vehicle_msgs::msg::dds_::GearCommand_", ""},
      {"/control/command/turn_indicators_cmd",
       "autoware_vehicle_msgs::msg::dds_::TurnIndicatorsCommand_", ""},
      {"/control/command/hazard_lights_cmd",
       "autoware_vehicle_msgs::msg::dds_::HazardLightsCommand_", ""},
  };

  for (int i = 0; i < 4; ++i) {
    const FakeSub& s = state_.subs[i];
    EXPECT_EQ(s.topic, expected[i].topic) << "topic mismatch at index " << i;
    EXPECT_EQ(s.type_name, expected[i].type_name) << "type_name mismatch at index " << i;
    EXPECT_EQ(s.type_hash, expected[i].type_hash) << "type_hash mismatch at index " << i;
    // Control command QoS: reliability 1 = BEST_EFFORT, durability 0 = VOLATILE,
    // history_depth 1 = KEEP_LAST depth 1 (CarlaRos2Extension.h field comments).
    EXPECT_EQ(s.qos.reliability, 1u) << "reliability at index " << i;
    EXPECT_EQ(s.qos.durability, 0u) << "durability at index " << i;
    EXPECT_EQ(s.qos.history_depth, 1u) << "history_depth at index " << i;
    EXPECT_EQ(s.user, &sub) << "user pointer at index " << i;
  }
}

// ---------------------------------------------------------------------------
// A serialized Control fed through the control_cmd callback applies the expected
// converted pod to the current ego actor id.
// ---------------------------------------------------------------------------
TEST_F(ControlSubscribersTest, control_callback_applies_converted_pod_to_ego) {
  ControlSubscribers sub;
  sub.Init(MakeFakeHost());
  ASSERT_EQ(state_.subs.size(), 4u);
  state_.ego_id = 42u;

  autoware_control_msgs::msg::Control c;
  c.lateral.steering_tire_angle = 0.2f;
  c.lateral.steering_tire_rotation_rate = 0.3f;
  c.lateral.is_defined_steering_tire_rotation_rate = true;
  c.longitudinal.velocity = 4.0f;
  c.longitudinal.acceleration = 1.5f;
  c.longitudinal.jerk = -0.75f;
  const std::vector<uint8_t> b = serialize_control(c);

  const FakeSub& s = state_.subs[0];
  s.cb(s.user, b.data(), b.size());

  ASSERT_EQ(state_.applied.size(), 1u);
  EXPECT_EQ(state_.applied[0].first, 42u);
  const CarlaRos2AckermannPod& p = state_.applied[0].second;
  const CarlaRos2AckermannPod expect = control_to_ackermann(c);
  EXPECT_FLOAT_EQ(p.steer, expect.steer);
  EXPECT_FLOAT_EQ(p.steer_speed, expect.steer_speed);
  EXPECT_FLOAT_EQ(p.speed, expect.speed);
  EXPECT_FLOAT_EQ(p.acceleration, expect.acceleration);
  EXPECT_FLOAT_EQ(p.jerk, expect.jerk);
  // Concrete values: sign-flipped/compensated steer, negated rate.
  EXPECT_LT(p.steer, 0.0f);
  EXPECT_FLOAT_EQ(p.steer_speed, -0.3f);
  EXPECT_FLOAT_EQ(p.speed, 4.0f);
}

// No ego registered -> the callback drops the sample (fire-and-forget).
TEST_F(ControlSubscribersTest, control_callback_drops_when_no_ego) {
  ControlSubscribers sub;
  sub.Init(MakeFakeHost());
  state_.ego_id = 0u;  // no ego

  autoware_control_msgs::msg::Control c;
  c.longitudinal.velocity = 4.0f;
  const std::vector<uint8_t> b = serialize_control(c);
  const FakeSub& s = state_.subs[0];
  s.cb(s.user, b.data(), b.size());

  EXPECT_TRUE(state_.applied.empty());
}

// Truncated CDR -> deserialize fails -> the callback drops the sample.
TEST_F(ControlSubscribersTest, control_callback_drops_truncated_cdr) {
  ControlSubscribers sub;
  sub.Init(MakeFakeHost());
  state_.ego_id = 42u;

  autoware_control_msgs::msg::Control c;
  c.longitudinal.velocity = 4.0f;
  const std::vector<uint8_t> b = serialize_control(c);
  const FakeSub& s = state_.subs[0];
  s.cb(s.user, b.data(), b.size() - 1);  // one byte short of the final bool

  EXPECT_TRUE(state_.applied.empty());
}

// The three command callbacks cache their uint8 into the atomic accessors.
TEST_F(ControlSubscribersTest, command_callbacks_update_atomic_caches) {
  ControlSubscribers sub;
  sub.Init(MakeFakeHost());
  ASSERT_EQ(state_.subs.size(), 4u);

  const std::vector<uint8_t> gear =
      serialize_command<autoware_vehicle_msgs::msg::GearCommand>(1, 2u, 2u);  // DRIVE
  const std::vector<uint8_t> turn =
      serialize_command<autoware_vehicle_msgs::msg::TurnIndicatorsCommand>(3, 4u,
                                                                            3u);  // ENABLE_RIGHT
  const std::vector<uint8_t> hazard =
      serialize_command<autoware_vehicle_msgs::msg::HazardLightsCommand>(5, 6u, 2u);  // ENABLE
  state_.subs[1].cb(state_.subs[1].user, gear.data(), gear.size());
  state_.subs[2].cb(state_.subs[2].user, turn.data(), turn.size());
  state_.subs[3].cb(state_.subs[3].user, hazard.data(), hazard.size());

  EXPECT_EQ(sub.CachedGear(), 2u);
  EXPECT_EQ(sub.CachedTurnIndicators(), 3u);
  EXPECT_EQ(sub.CachedHazardLights(), 2u);
}

// DDS may pad the payload to a 4-byte boundary; the last byte can be a pad byte,
// so the command byte must be parsed by position (the typed deserializer), not
// read as the last byte. A buffer with 3 trailing pad bytes must still decode
// correctly.
TEST_F(ControlSubscribersTest, command_callback_tolerates_trailing_padding) {
  ControlSubscribers sub;
  sub.Init(MakeFakeHost());

  std::vector<uint8_t> gear =
      serialize_command<autoware_vehicle_msgs::msg::GearCommand>(7, 8u, 22u);  // PARK
  gear.push_back(0);
  gear.push_back(0);
  gear.push_back(0);  // 3 middleware pad bytes
  state_.subs[1].cb(state_.subs[1].user, gear.data(), gear.size());

  EXPECT_EQ(sub.CachedGear(), 22u);  // not 0 from a trailing pad byte
}

// Before any command arrives, the accessors report the safe idle defaults that
// the status publishers expect (StatusInputs mirrors these).
TEST_F(ControlSubscribersTest, accessors_default_to_safe_idle_state) {
  ControlSubscribers sub;
  sub.Init(MakeFakeHost());
  EXPECT_EQ(sub.CachedGear(), 0u);            // GearReport NONE
  EXPECT_EQ(sub.CachedTurnIndicators(), 1u);  // TurnIndicatorsReport DISABLE
  EXPECT_EQ(sub.CachedHazardLights(), 1u);    // HazardLightsReport DISABLE
}
