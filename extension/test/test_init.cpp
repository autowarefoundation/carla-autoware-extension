#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "carla/autoware/messages/Cdr.h"
#include "carla/ros2/extension/CarlaRos2Extension.h"

// The single exported entrypoint under test (ExtensionInit.cpp). Declared here
// with C linkage exactly as the core loader (Task 11) dlsym's it, rather than
// pulling in a private header -- the seam is the symbol, not a C++ signature.
extern "C" int carla_ros2_extension_init(const CarlaRos2Host*, CarlaRos2Extension*);

using namespace carla::autoware;

// ===========================================================================
// Fake host: the host vtable is a struct of C function pointers, so the fakes
// capture into file-scope state (only a non-capturing lambda / free function is
// convertible to a C function pointer). g_state is redirected to the per-test
// fixture instance in SetUp; gtest runs cases serially in-process. This mirrors
// the established fake-host pattern in test_status_publishers.cpp /
// test_control_conversion.cpp / test_engage.cpp, unified into ONE host that
// wires every vtable slot the entrypoint touches (publishers + subscribers +
// observer registration + the control sink), so the init test can drive the
// whole extension end to end across a real host boundary.
// ===========================================================================
namespace {

struct FakePub {
  std::string topic;
  std::string type_name;
  std::string type_hash;
  CarlaRos2Qos qos;
};

struct FakeSub {
  std::string topic;
  std::string type_name;
  std::string type_hash;
  CarlaRos2Qos qos;
  CarlaRos2SubCallback cb;
  void* user;
};

struct FakeObserver {
  int kind;
  CarlaRos2SensorObserver cb;
  void* user;
};

struct FakeHostState {
  std::vector<FakePub> pubs;   // creation order; handle returned is (index + 1)
  std::vector<FakeSub> subs;   // creation order; handle returned is (index + 1)
  std::vector<FakeObserver> observers;
  std::vector<std::pair<CarlaRos2PubHandle, std::vector<uint8_t>>> published;
  uint32_t ego_id = 0;
  std::vector<std::pair<uint32_t, CarlaRos2AckermannPod>> applied;
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

CarlaRos2SubHandle FakeCreateSubscriber(void* /*ctx*/, const char* topic,
                                        const char* type_name, const char* type_hash,
                                        const CarlaRos2Qos* qos, CarlaRos2SubCallback cb,
                                        void* user) {
  g_state->subs.push_back(FakeSub{topic, type_name, type_hash, *qos, cb, user});
  return static_cast<CarlaRos2SubHandle>(g_state->subs.size());  // 1-based; 0 = invalid
}

void FakeRegisterObserver(void* /*ctx*/, int kind, CarlaRos2SensorObserver cb, void* user) {
  g_state->observers.push_back(FakeObserver{kind, cb, user});
}

uint32_t FakeGetEgoActorId(void* /*ctx*/) { return g_state->ego_id; }

void FakeApplyAckermann(void* /*ctx*/, uint32_t actor_id, const CarlaRos2AckermannPod* pod) {
  g_state->applied.emplace_back(actor_id, *pod);
}

const char* FakeGetActorRosName(void* /*ctx*/, uint32_t /*actor_id*/) { return "ego"; }

CarlaRos2Host MakeFakeHost() {
  CarlaRos2Host host{};
  host.api_version = CARLA_ROS2_EXTENSION_API_VERSION;
  host.host_ctx = nullptr;
  host.register_sensor_observer = &FakeRegisterObserver;
  host.create_publisher = &FakeCreatePublisher;
  host.publish = &FakePublish;
  host.create_subscriber = &FakeCreateSubscriber;
  host.apply_ackermann_control = &FakeApplyAckermann;
  host.get_ego_actor_id = &FakeGetEgoActorId;
  host.get_actor_ros_name = &FakeGetActorRosName;
  return host;
}

// Engage.msg / *Command.msg CDR builders (mirror test_engage.cpp /
// test_control_conversion.cpp; re-authored locally to avoid cross-TU coupling).
std::vector<uint8_t> serialize_engage(int32_t sec, uint32_t nsec, bool engaged) {
  CdrWriter w;
  w.i32(sec);
  w.u32(nsec);
  w.boolean(engaged);
  return w.bytes();
}

std::vector<uint8_t> serialize_command(int32_t sec, uint32_t nsec, uint8_t cmd) {
  CdrWriter w;
  w.i32(sec);
  w.u32(nsec);
  w.u8(cmd);
  return w.bytes();
}

// Locate the subscriber / registered publisher buffer by topic, so assertions
// bind to a topic name rather than a fragile creation-order index.
const FakeSub* SubForTopic(const std::string& topic) {
  for (const FakeSub& s : g_state->subs) {
    if (s.topic == topic) return &s;
  }
  return nullptr;
}

const std::vector<uint8_t>* PublishedForTopic(const std::string& topic) {
  for (const auto& pr : g_state->published) {
    const CarlaRos2PubHandle h = pr.first;
    if (h >= 1 && h <= g_state->pubs.size() && g_state->pubs[h - 1].topic == topic) {
      return &pr.second;
    }
  }
  return nullptr;
}

class InitTest : public ::testing::Test {
 protected:
  void SetUp() override { g_state = &state_; }
  void TearDown() override { g_state = nullptr; }
  FakeHostState state_;
};

}  // namespace

// ---------------------------------------------------------------------------
// Defensive argument / handshake rejections (Resolution 2). Each failure class
// returns a distinct nonzero code, and NONE of them touch `out`: a rejected
// load must leave the caller's out-struct exactly as it was (zeroed here).
// ---------------------------------------------------------------------------
TEST_F(InitTest, rejects_null_host) {
  CarlaRos2Extension e{};
  EXPECT_NE(carla_ros2_extension_init(nullptr, &e), 0);
  EXPECT_EQ(e.api_version, 0u);
  EXPECT_EQ(e.ext_ctx, nullptr);
  EXPECT_EQ(e.on_tick, nullptr);
  EXPECT_EQ(e.on_shutdown, nullptr);
}

TEST_F(InitTest, rejects_null_out) {
  CarlaRos2Host h = MakeFakeHost();
  EXPECT_NE(carla_ros2_extension_init(&h, nullptr), 0);
  // No out to inspect; a crash would fail the test. Also proves the entrypoint
  // never registered an observer on the rejected path.
  EXPECT_TRUE(state_.observers.empty());
}

TEST_F(InitTest, rejects_bad_version_and_leaves_out_zeroed) {
  CarlaRos2Host h = MakeFakeHost();
  h.api_version = 999u;
  CarlaRos2Extension e{};
  EXPECT_NE(carla_ros2_extension_init(&h, &e), 0);
  // Resolution 2: version mismatch must not touch out or allocate.
  EXPECT_EQ(e.api_version, 0u);
  EXPECT_EQ(e.ext_ctx, nullptr);
  EXPECT_EQ(e.on_tick, nullptr);
  EXPECT_EQ(e.on_shutdown, nullptr);
  EXPECT_TRUE(state_.observers.empty());
  EXPECT_TRUE(state_.pubs.empty());
  EXPECT_TRUE(state_.subs.empty());
}

TEST_F(InitTest, distinct_reject_codes_per_failure_class) {
  CarlaRos2Extension e{};
  CarlaRos2Host h = MakeFakeHost();
  h.api_version = 999u;
  const int null_host = carla_ros2_extension_init(nullptr, &e);
  const int null_out = carla_ros2_extension_init(&h /*valid ptr*/, nullptr);
  const int bad_ver = carla_ros2_extension_init(&h, &e);
  EXPECT_NE(null_host, 0);
  EXPECT_NE(null_out, 0);
  EXPECT_NE(bad_ver, 0);
  EXPECT_NE(null_host, null_out);
  EXPECT_NE(null_host, bad_ver);
  EXPECT_NE(null_out, bad_ver);
}

// ---------------------------------------------------------------------------
// Success handshake: returns 0, out fully populated (every function pointer
// non-null, api_version exact, ext_ctx non-null), and all four subsystems got
// Init'd (8 publishers: 6 status + 2 GNSS; 5 subscribers: 4 control + 1 engage).
// ---------------------------------------------------------------------------
TEST_F(InitTest, accepts_and_fully_populates_out) {
  CarlaRos2Host h = MakeFakeHost();
  CarlaRos2Extension e{};
  ASSERT_EQ(carla_ros2_extension_init(&h, &e), 0);

  EXPECT_EQ(e.api_version, CARLA_ROS2_EXTENSION_API_VERSION);
  EXPECT_NE(e.ext_ctx, nullptr);
  ASSERT_NE(e.on_tick, nullptr);
  ASSERT_NE(e.on_shutdown, nullptr);

  // All four subsystems were Init'd against the host.
  EXPECT_EQ(state_.pubs.size(), 8u);  // 6 status + 2 GNSS
  EXPECT_EQ(state_.subs.size(), 5u);  // 4 control + 1 engage

  // on_tick is a documented no-op (Resolution 1) -- callable without effect.
  e.on_tick(e.ext_ctx, 1.0);
  EXPECT_TRUE(state_.published.empty());

  e.on_shutdown(e.ext_ctx);
}

// ---------------------------------------------------------------------------
// The observer is registered EXACTLY ONCE, for the VEHICLE_STATUS kind, with the
// user pointer == ext_ctx (so the callback recovers the ExtensionState).
// ---------------------------------------------------------------------------
TEST_F(InitTest, registers_observer_once_for_vehicle_status_with_ext_ctx_user) {
  CarlaRos2Host h = MakeFakeHost();
  CarlaRos2Extension e{};
  ASSERT_EQ(carla_ros2_extension_init(&h, &e), 0);

  ASSERT_EQ(state_.observers.size(), 1u);
  EXPECT_EQ(state_.observers[0].kind, CARLA_ROS2_SENSOR_VEHICLE_STATUS);
  EXPECT_NE(state_.observers[0].cb, nullptr);
  EXPECT_EQ(state_.observers[0].user, e.ext_ctx);

  e.on_shutdown(e.ext_ctx);
}

// ---------------------------------------------------------------------------
// End-to-end cross-subsystem threading: engage=true and gear_cmd=2 arrive on
// their captured DDS callbacks as real CDR buffers, then a fake vehicle-status
// sample is delivered to the captured observer. All EIGHT publishes fire on the
// first frame (6 status + 2 GNSS), and the ControlModeReport / GearReport bytes
// parse back to the values that were threaded in from the OTHER subsystems --
// proving the engage machine (Task 21) and control subscribers (Task 20) reach
// the status publishers (Task 18) through the entrypoint's StatusInputs wiring.
// ---------------------------------------------------------------------------
TEST_F(InitTest, end_to_end_threads_engage_and_gear_into_status_publishes) {
  CarlaRos2Host h = MakeFakeHost();
  CarlaRos2Extension e{};
  ASSERT_EQ(carla_ros2_extension_init(&h, &e), 0);
  ASSERT_EQ(state_.observers.size(), 1u);

  // Drive engage=true -> the engage machine caches AUTONOMOUS (mode 1).
  const FakeSub* engage = SubForTopic("/autoware/engage");
  ASSERT_NE(engage, nullptr);
  const std::vector<uint8_t> eng = serialize_engage(1, 0u, true);
  engage->cb(engage->user, eng.data(), eng.size());

  // Drive gear_cmd=2 (DRIVE) -> the control subscribers cache gear 2.
  const FakeSub* gear = SubForTopic("/control/command/gear_cmd");
  ASSERT_NE(gear, nullptr);
  const std::vector<uint8_t> gc = serialize_command(2, 0u, 2u);
  gear->cb(gear->user, gc.data(), gc.size());

  // Deliver one vehicle-status frame to the captured observer.
  CarlaRos2VehicleStatusView view{};
  view.actor_id = 7u;
  view.ros_name = "ego";
  view.velocity_mps = 3.5;
  view.steering_tire_angle_rad = 0.1;
  view.sim_time_s = 12.5;
  CarlaRos2SensorSample sample{};
  sample.kind = CARLA_ROS2_SENSOR_VEHICLE_STATUS;
  sample.actor_id = 7u;
  sample.ros_name = "ego";
  sample.data = &view;
  sample.data_size = sizeof(view);
  state_.observers[0].cb(state_.observers[0].user, &sample);

  // 6 status + 2 GNSS (first frame always publishes both poses).
  ASSERT_EQ(state_.published.size(), 8u);

  // ControlModeReport carries the engage machine's mode: bare Time + uint8 mode.
  const std::vector<uint8_t>* mode_buf = PublishedForTopic("/vehicle/status/control_mode");
  ASSERT_NE(mode_buf, nullptr);
  {
    CdrReader r(mode_buf->data(), mode_buf->size());
    (void)r.i32();  // stamp.sec
    (void)r.u32();  // stamp.nanosec
    EXPECT_EQ(r.u8(), 1u);  // AUTONOMOUS, threaded from EngageStateMachine::Mode()
    EXPECT_TRUE(r.ok());
  }

  // GearReport carries the control subscribers' cached gear: bare Time + uint8.
  const std::vector<uint8_t>* gear_buf = PublishedForTopic("/vehicle/status/gear_status");
  ASSERT_NE(gear_buf, nullptr);
  {
    CdrReader r(gear_buf->data(), gear_buf->size());
    (void)r.i32();  // stamp.sec
    (void)r.u32();  // stamp.nanosec
    EXPECT_EQ(r.u8(), 2u);  // DRIVE, threaded from ControlSubscribers::CachedGear()
    EXPECT_TRUE(r.ok());
  }

  // on_shutdown is callable once after a live frame without crashing.
  e.on_shutdown(e.ext_ctx);
}

// ---------------------------------------------------------------------------
// The observer defensively ignores a sample of a kind it did not register for
// (guards ABI drift; the host only ever routes the registered kind, but the
// check pins intent and prevents reinterpreting foreign bytes as a status view).
// ---------------------------------------------------------------------------
TEST_F(InitTest, observer_ignores_non_vehicle_status_sample) {
  CarlaRos2Host h = MakeFakeHost();
  CarlaRos2Extension e{};
  ASSERT_EQ(carla_ros2_extension_init(&h, &e), 0);
  ASSERT_EQ(state_.observers.size(), 1u);

  CarlaRos2VehicleStatusView view{};
  view.sim_time_s = 1.0;
  CarlaRos2SensorSample sample{};
  sample.kind = CARLA_ROS2_SENSOR_GNSS;  // NOT the registered kind
  sample.data = &view;
  sample.data_size = sizeof(view);
  state_.observers[0].cb(state_.observers[0].user, &sample);

  EXPECT_TRUE(state_.published.empty());  // nothing published for a foreign kind

  e.on_shutdown(e.ext_ctx);
}
