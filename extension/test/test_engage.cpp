#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <vector>

#include "carla/autoware/messages/Cdr.h"
#include "carla/ros2/extension/CarlaRos2Extension.h"
#include "engage/EngageStateMachine.h"

using namespace carla::autoware;

// ===========================================================================
// engage_to_mode: pure bool -> ControlModeReport mode mapping (the
// ControlModeReport.msg constants).
// ===========================================================================

TEST(engage, true_is_autonomous_false_is_manual) {
  EXPECT_EQ(engage_to_mode(true), 1);   // ControlModeReport::AUTONOMOUS
  EXPECT_EQ(engage_to_mode(false), 4);  // ControlModeReport::MANUAL
}

// ===========================================================================
// Fake host: mirrors ControlSubscribersTest's fake-host pattern
// (test_control_conversion.cpp) -- the host vtable is a struct of C function
// pointers, so the fake captures into file-scope state (only a non-capturing
// lambda / free function is convertible to a C function pointer). g_state is
// redirected to the per-test fixture instance in SetUp; gtest runs cases
// serially in-process.
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
};

FakeHostState* g_state = nullptr;

CarlaRos2SubHandle FakeCreateSubscriber(void* /*ctx*/, const char* topic,
                                        const char* type_name, const char* type_hash,
                                        const CarlaRos2Qos* qos, CarlaRos2SubCallback cb,
                                        void* user) {
  g_state->subs.push_back(FakeSub{topic, type_name, type_hash, *qos, cb, user});
  return static_cast<CarlaRos2SubHandle>(g_state->subs.size());  // 1-based; 0 = invalid
}

CarlaRos2Host MakeFakeHost() {
  CarlaRos2Host host{};
  host.api_version = CARLA_ROS2_EXTENSION_API_VERSION;
  host.host_ctx = nullptr;
  host.create_subscriber = &FakeCreateSubscriber;
  return host;
}

// Engage.msg (extracted extension/msg/autoware_vehicle_msgs/Engage.msg):
// { builtin_interfaces/Time stamp; bool engage }.
std::vector<uint8_t> serialize_engage(int32_t sec, uint32_t nsec, bool engaged) {
  CdrWriter w;
  w.i32(sec);
  w.u32(nsec);
  w.boolean(engaged);
  return w.bytes();
}

class EngageStateMachineTest : public ::testing::Test {
 protected:
  void SetUp() override { g_state = &state_; }
  void TearDown() override { g_state = nullptr; }
  FakeHostState state_;
};

}  // namespace

// ---------------------------------------------------------------------------
// Init wires exactly one subscriber, at the Step-1-pinned topic/type, "" hash
// (no RIHS01 golden -- out of scope here, mirrors ControlSubscribers'
// *Command topics), reliable/volatile/keep-last-1 QoS, with the
// machine as the user pointer.
// ---------------------------------------------------------------------------
TEST_F(EngageStateMachineTest, init_creates_one_subscriber_with_topic_typeinfo_and_qos) {
  EngageStateMachine machine;
  machine.Init(MakeFakeHost());

  ASSERT_EQ(state_.subs.size(), 1u);
  const FakeSub& s = state_.subs[0];
  EXPECT_EQ(s.topic, "/autoware/engage");
  EXPECT_EQ(s.type_name, "autoware_vehicle_msgs::msg::dds_::Engage_");
  EXPECT_EQ(s.type_hash, "");
  // reliability 0 = reliable, durability 0 = volatile, history_depth 1.
  EXPECT_EQ(s.qos.reliability, 0u);
  EXPECT_EQ(s.qos.durability, 0u);
  EXPECT_EQ(s.qos.history_depth, 1u);
  EXPECT_EQ(s.user, &machine);
}

// Default mode is MANUAL (4) before any engage message arrives.
TEST_F(EngageStateMachineTest, default_mode_is_manual_before_any_message) {
  EngageStateMachine machine;
  machine.Init(MakeFakeHost());
  EXPECT_EQ(machine.Mode(), 4u);
}

// A serialized engage=true fed through the captured callback sets AUTONOMOUS.
TEST_F(EngageStateMachineTest, engage_true_sets_mode_autonomous) {
  EngageStateMachine machine;
  machine.Init(MakeFakeHost());
  const std::vector<uint8_t> b = serialize_engage(1, 2u, true);
  const FakeSub& s = state_.subs[0];
  s.cb(s.user, b.data(), b.size());
  EXPECT_EQ(machine.Mode(), 1u);
}

// engage=false sets MANUAL; also proves an explicit disengage overrides a
// prior AUTONOMOUS.
TEST_F(EngageStateMachineTest, engage_false_sets_mode_manual) {
  EngageStateMachine machine;
  machine.Init(MakeFakeHost());
  const FakeSub& s = state_.subs[0];

  const std::vector<uint8_t> engaged = serialize_engage(1, 2u, true);
  s.cb(s.user, engaged.data(), engaged.size());
  ASSERT_EQ(machine.Mode(), 1u);

  const std::vector<uint8_t> disengaged = serialize_engage(3, 4u, false);
  s.cb(s.user, disengaged.data(), disengaged.size());
  EXPECT_EQ(machine.Mode(), 4u);
}

// DDS may pad the payload to a 4-byte boundary; a buffer with 3 trailing pad
// bytes after the bool must still decode correctly -- CdrReader stops reading
// after the bool (parse_engage), leaving the pad bytes simply unconsumed.
TEST_F(EngageStateMachineTest, padded_buffer_still_decodes) {
  EngageStateMachine machine;
  machine.Init(MakeFakeHost());
  std::vector<uint8_t> b = serialize_engage(5, 6u, true);
  b.push_back(0);
  b.push_back(0);
  b.push_back(0);  // 3 middleware pad bytes
  const FakeSub& s = state_.subs[0];
  s.cb(s.user, b.data(), b.size());
  EXPECT_EQ(machine.Mode(), 1u);
}

// A truncated buffer (one byte short of the engage bool) fails to parse and
// must leave the cached mode UNCHANGED, not fall back to a default or garbage.
TEST_F(EngageStateMachineTest, truncated_buffer_leaves_mode_unchanged) {
  EngageStateMachine machine;
  machine.Init(MakeFakeHost());
  const FakeSub& s = state_.subs[0];

  // Engage first so the cached mode is the non-default value (1) -- otherwise
  // an "unchanged" assertion would be vacuously true against the 4 default.
  const std::vector<uint8_t> engaged = serialize_engage(1, 2u, true);
  s.cb(s.user, engaged.data(), engaged.size());
  ASSERT_EQ(machine.Mode(), 1u);

  const std::vector<uint8_t> b = serialize_engage(3, 4u, false);
  s.cb(s.user, b.data(), b.size() - 1);  // one byte short of the engage bool
  EXPECT_EQ(machine.Mode(), 1u);         // unchanged, not 4
}
