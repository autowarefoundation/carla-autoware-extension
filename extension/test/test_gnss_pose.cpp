#include <gtest/gtest.h>

#include <cmath>
#include <cstdint>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

#include "carla/autoware/geo/MgrsOffset.h"
#include "carla/autoware/messages/Cdr.h"
#include "publishers/GnssPosePublisher.h"

using namespace carla::autoware;

// ===========================================================================
// MGRS offset transform. Byte-identical to the verified
// scripts/phase_b/verify_mgrs_handedness.py world_to_mgrs_local (cm frame).
// ===========================================================================
TEST(mgrs, origin_maps_to_offset) {
  auto [x, y, z] = world_to_mgrs_local(0.0, 0.0, 0.0);
  EXPECT_NEAR(x, 81655.73, 1e-3);
  EXPECT_NEAR(y, 50137.43, 1e-3);
  EXPECT_NEAR(z, 42.49998, 1e-3);
}

TEST(mgrs, y_is_flipped) {
  // +1 m of CARLA Y (100 cm) moves MGRS Y NEGATIVE (left-handed -> right-handed).
  auto [x, y, z] = world_to_mgrs_local(0.0, 100.0, 0.0);
  EXPECT_NEAR(x, 81655.73, 1e-3);
  EXPECT_NEAR(y, 50137.43 - 1.0, 1e-3);
  EXPECT_NEAR(z, 42.49998, 1e-3);
}

TEST(mgrs, x_and_z_are_not_flipped_and_scale_by_100) {
  auto [x, y, z] = world_to_mgrs_local(250.0, -400.0, 175.0);  // cm
  EXPECT_NEAR(x, 81655.73 + 2.50, 1e-3);
  EXPECT_NEAR(y, 50137.43 + 4.00, 1e-3);  // -(-400 cm) = +4 m
  EXPECT_NEAR(z, 42.49998 + 1.75, 1e-3);
}

// ===========================================================================
// Quaternion handedness. The position transform is a
// mirror M = diag(1,-1,1); a rotation conjugates as R' = M R M, which for a
// unit quaternion (qx,qy,qz,qw) is (-qx, qy, -qz, qw): roll (X) and yaw (Z)
// negate, pitch (Y) is preserved. These tests PIN that mapping via known
// angles -- if they contradict the (-qx,qy,-qz,qw) signs the implementation is
// wrong, not the tests (the tests are the authority for the sign convention).
// ===========================================================================
namespace {
// ZYX yaw extracted from a quaternion, for the semantic heading assertion.
double quat_yaw(double qx, double qy, double qz, double qw) {
  return std::atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz));
}
constexpr double kS45 = 0.70710678118654752440;  // sin(45 deg) = cos(45 deg)
}  // namespace

TEST(quat, identity_maps_to_identity) {
  auto [qx, qy, qz, qw] = carla_quat_to_mgrs(0.0, 0.0, 0.0, 1.0);
  EXPECT_DOUBLE_EQ(qx, 0.0);
  EXPECT_DOUBLE_EQ(qy, 0.0);
  EXPECT_DOUBLE_EQ(qz, 0.0);
  EXPECT_DOUBLE_EQ(qw, 1.0);
}

TEST(quat, carla_yaw_plus_90_becomes_mgrs_yaw_minus_90) {
  // CARLA yaw +90 deg about +Z: (0,0,sin45,cos45). Heading rotates CARLA +X ->
  // +Y; CARLA +Y is MGRS -Y (south), so the mapped pose must face MGRS -Y, i.e.
  // MGRS yaw -90 deg.
  auto [qx, qy, qz, qw] = carla_quat_to_mgrs(0.0, 0.0, kS45, kS45);
  EXPECT_NEAR(qx, 0.0, 1e-12);
  EXPECT_NEAR(qy, 0.0, 1e-12);
  EXPECT_NEAR(qz, -kS45, 1e-12);  // z (yaw) axis negated
  EXPECT_NEAR(qw, kS45, 1e-12);
  EXPECT_NEAR(quat_yaw(qx, qy, qz, qw), -M_PI / 2.0, 1e-9);
}

TEST(quat, pure_pitch_is_unchanged) {
  // Rotation about +Y (pitch): (0, sin(t/2), 0, cos(t/2)). Y component survives.
  auto [qx, qy, qz, qw] = carla_quat_to_mgrs(0.0, kS45, 0.0, kS45);
  EXPECT_NEAR(qx, 0.0, 1e-12);
  EXPECT_NEAR(qy, kS45, 1e-12);  // preserved
  EXPECT_NEAR(qz, 0.0, 1e-12);
  EXPECT_NEAR(qw, kS45, 1e-12);
}

TEST(quat, pure_roll_negates) {
  // Rotation about +X (roll): (sin(t/2), 0, 0, cos(t/2)). X component negates.
  auto [qx, qy, qz, qw] = carla_quat_to_mgrs(kS45, 0.0, 0.0, kS45);
  EXPECT_NEAR(qx, -kS45, 1e-12);  // negated
  EXPECT_NEAR(qy, 0.0, 1e-12);
  EXPECT_NEAR(qz, 0.0, 1e-12);
  EXPECT_NEAR(qw, kS45, 1e-12);
}

// ===========================================================================
// Fake host (same pattern as test_status_publishers.cpp): the host vtable is a
// struct of C function pointers, so the fakes capture into file-scope state
// redirected to the per-test fixture in SetUp. gtest runs cases serially.
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

// Build a status view for one ego frame.
CarlaRos2VehicleStatusView MakeView(double t, double x_cm = 0.0, double y_cm = 0.0,
                                    double z_cm = 0.0, double qx = 0.0, double qy = 0.0,
                                    double qz = 0.0, double qw = 1.0) {
  CarlaRos2VehicleStatusView v{};
  v.sim_time_s = t;
  v.transform.x_cm = x_cm;
  v.transform.y_cm = y_cm;
  v.transform.z_cm = z_cm;
  v.transform.qx = qx;
  v.transform.qy = qy;
  v.transform.qz = qz;
  v.transform.qw = qw;
  return v;
}

class GnssPoseTest : public ::testing::Test {
 protected:
  void SetUp() override { g_state = &state_; }
  void TearDown() override { g_state = nullptr; }
  FakeHostState state_;
};

}  // namespace

// ---------------------------------------------------------------------------
// (a) Init wires EXACTLY two publishers: the two topics, exact DDS type names,
// the computed RIHS01 goldens, and AWSIM GNSS QoS (reliable/volatile/depth-1).
// ---------------------------------------------------------------------------
TEST_F(GnssPoseTest, init_creates_two_publishers_with_topics_typeinfo_and_qos) {
  GnssPosePublisher pub;
  pub.Init(MakeFakeHost());

  ASSERT_EQ(state_.pubs.size(), 2u);

  const FakePub& p0 = state_.pubs[0];
  EXPECT_EQ(p0.topic, "/sensing/gnss/pose");
  EXPECT_EQ(p0.type_name, "geometry_msgs::msg::dds_::PoseStamped_");
  EXPECT_EQ(p0.type_name, pose_stamped_type_name());
  EXPECT_EQ(p0.type_hash, pose_stamped_type_hash());

  const FakePub& p1 = state_.pubs[1];
  EXPECT_EQ(p1.topic, "/sensing/gnss/pose_with_covariance");
  EXPECT_EQ(p1.type_name, "geometry_msgs::msg::dds_::PoseWithCovarianceStamped_");
  EXPECT_EQ(p1.type_name, pose_with_covariance_stamped_type_name());
  EXPECT_EQ(p1.type_hash, pose_with_covariance_stamped_type_hash());

  // Both goldens are real RIHS01_<64hex> (never an empty/placeholder string).
  for (const char* h : {pose_stamped_type_hash(), pose_with_covariance_stamped_type_hash()}) {
    const std::string s = h;
    EXPECT_EQ(s.substr(0, 7), "RIHS01_");
    EXPECT_EQ(s.size(), 7u + 64u);
  }

  // AWSIM GNSS QoS: reliability 0 = RELIABLE, durability 0 = VOLATILE,
  // history_depth 1 = KEEP_LAST depth 1 (CarlaRos2Extension.h field comments).
  for (const FakePub& p : state_.pubs) {
    EXPECT_EQ(p.qos.reliability, 0u);
    EXPECT_EQ(p.qos.durability, 0u);
    EXPECT_EQ(p.qos.history_depth, 1u);
  }
}

// ---------------------------------------------------------------------------
// (b) OnVehicleStatus at t=0 publishes BOTH; the PoseStamped bytes parse back to
// stamp (sec/nsec), frame_id "map", position = MGRS transform of the input cm
// values, orientation = the mapped quaternion. Fields are read in wire order
// (the reader handles alignment) rather than hardcoding byte offsets.
// ---------------------------------------------------------------------------
TEST_F(GnssPoseTest, on_vehicle_status_publishes_pose_stamped_with_expected_fields) {
  GnssPosePublisher pub;
  pub.Init(MakeFakeHost());
  ASSERT_EQ(state_.pubs.size(), 2u);

  // Non-trivial pose: 10 m east, 20 m +Y (CARLA), 5 m up; CARLA yaw +90.
  const double x_cm = 1000.0, y_cm = 2000.0, z_cm = 500.0;
  auto v = MakeView(0.0, x_cm, y_cm, z_cm, 0.0, 0.0, kS45, kS45);
  pub.OnVehicleStatus(v);

  ASSERT_EQ(state_.published.size(), 2u);
  EXPECT_EQ(state_.published[0].first, static_cast<CarlaRos2PubHandle>(1));  // PoseStamped
  EXPECT_EQ(state_.published[1].first, static_cast<CarlaRos2PubHandle>(2));  // PoseWithCov

  const auto [mx, my, mz] = world_to_mgrs_local(x_cm, y_cm, z_cm);
  const auto [eqx, eqy, eqz, eqw] = carla_quat_to_mgrs(0.0, 0.0, kS45, kS45);

  const auto& b = state_.published[0].second;
  CdrReader r(b.data(), b.size());
  EXPECT_EQ(r.i32(), 0);        // stamp.sec
  EXPECT_EQ(r.u32(), 0u);       // stamp.nanosec
  EXPECT_EQ(r.str(), "map");    // header.frame_id
  EXPECT_DOUBLE_EQ(r.f64(), mx);
  EXPECT_DOUBLE_EQ(r.f64(), my);
  EXPECT_DOUBLE_EQ(r.f64(), mz);
  EXPECT_DOUBLE_EQ(r.f64(), eqx);
  EXPECT_DOUBLE_EQ(r.f64(), eqy);
  EXPECT_DOUBLE_EQ(r.f64(), eqz);
  EXPECT_DOUBLE_EQ(r.f64(), eqw);
  EXPECT_TRUE(r.ok());
  // Exact wire size: 4 encaps + [sec4 nsec4 str(4+4)] + 7*f64 = 4 + 16 + 56 = 76.
  EXPECT_EQ(b.size(), 76u);
}

// ---------------------------------------------------------------------------
// (c) The PoseWithCovarianceStamped payload = the SAME header+pose prefix, then
// EXACTLY 36 float64 covariance values (fixed-size float64[36] -> NO length
// prefix) with the small diagonal {0.1,0.1,0.1,0.05,0.05,0.05} and zeros
// elsewhere. Total byte size is asserted so a stray length prefix or missing
// element is caught.
// ---------------------------------------------------------------------------
TEST_F(GnssPoseTest, pose_with_covariance_has_36_element_diagonal_no_length_prefix) {
  GnssPosePublisher pub;
  pub.Init(MakeFakeHost());

  const double x_cm = 1000.0, y_cm = 2000.0, z_cm = 500.0;
  auto v = MakeView(0.0, x_cm, y_cm, z_cm, 0.0, 0.0, kS45, kS45);
  pub.OnVehicleStatus(v);
  ASSERT_EQ(state_.published.size(), 2u);

  const auto [mx, my, mz] = world_to_mgrs_local(x_cm, y_cm, z_cm);
  const auto [eqx, eqy, eqz, eqw] = carla_quat_to_mgrs(0.0, 0.0, kS45, kS45);

  const auto& b = state_.published[1].second;
  CdrReader r(b.data(), b.size());
  EXPECT_EQ(r.i32(), 0);
  EXPECT_EQ(r.u32(), 0u);
  EXPECT_EQ(r.str(), "map");
  EXPECT_DOUBLE_EQ(r.f64(), mx);
  EXPECT_DOUBLE_EQ(r.f64(), my);
  EXPECT_DOUBLE_EQ(r.f64(), mz);
  EXPECT_DOUBLE_EQ(r.f64(), eqx);
  EXPECT_DOUBLE_EQ(r.f64(), eqy);
  EXPECT_DOUBLE_EQ(r.f64(), eqz);
  EXPECT_DOUBLE_EQ(r.f64(), eqw);

  // float64[36] is a FIXED-size array: read 36 f64 straight, NO u32 length.
  const double diag[6] = {0.1, 0.1, 0.1, 0.05, 0.05, 0.05};
  for (int row = 0; row < 6; ++row) {
    for (int col = 0; col < 6; ++col) {
      const double got = r.f64();
      const double want = (row == col) ? diag[row] : 0.0;
      EXPECT_DOUBLE_EQ(got, want) << "covariance[" << row << "][" << col << "]";
    }
  }
  EXPECT_TRUE(r.ok());
  // 4 encaps + 16 header + 56 pose + 36*8 covariance = 4 + 16 + 56 + 288 = 364.
  EXPECT_EQ(b.size(), 364u);
}

// ---------------------------------------------------------------------------
// (d) 1 Hz decimation: t=0 publishes (first call), t=0.5 and t=0.99 are
// suppressed, t=1.0 publishes again. Each publish emits BOTH topics.
// ---------------------------------------------------------------------------
TEST_F(GnssPoseTest, decimates_to_one_hz) {
  GnssPosePublisher pub;
  pub.Init(MakeFakeHost());

  pub.OnVehicleStatus(MakeView(0.0));
  EXPECT_EQ(state_.published.size(), 2u);  // first call publishes

  pub.OnVehicleStatus(MakeView(0.5));
  pub.OnVehicleStatus(MakeView(0.99));
  EXPECT_EQ(state_.published.size(), 2u);  // both suppressed (< 1 s since last)

  pub.OnVehicleStatus(MakeView(1.0));
  EXPECT_EQ(state_.published.size(), 4u);  // exactly 1 s elapsed -> publishes
}

// ---------------------------------------------------------------------------
// (e) Backwards clock (episode reload restarts the sim clock; M2 documented
// reload id invalidation). After publishing at t=5.0, a call at t=0.2 must
// publish -- the decimator must NOT deadlock waiting for the stale large
// last_pub time to be exceeded.
// ---------------------------------------------------------------------------
TEST_F(GnssPoseTest, backwards_clock_publishes_fresh) {
  GnssPosePublisher pub;
  pub.Init(MakeFakeHost());

  pub.OnVehicleStatus(MakeView(5.0));
  ASSERT_EQ(state_.published.size(), 2u);

  pub.OnVehicleStatus(MakeView(0.2));  // clock went backwards -> treat as fresh
  EXPECT_EQ(state_.published.size(), 4u);
}
