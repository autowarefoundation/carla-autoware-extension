#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <vector>

#include <autoware_control_msgs/msg/control.hpp>
#include <autoware_vehicle_msgs/msg/control_mode_report.hpp>
#include <autoware_vehicle_msgs/msg/engage.hpp>
#include <autoware_vehicle_msgs/msg/gear_command.hpp>
#include <autoware_vehicle_msgs/msg/gear_report.hpp>
#include <autoware_vehicle_msgs/msg/hazard_lights_command.hpp>
#include <autoware_vehicle_msgs/msg/hazard_lights_report.hpp>
#include <autoware_vehicle_msgs/msg/steering_report.hpp>
#include <autoware_vehicle_msgs/msg/turn_indicators_command.hpp>
#include <autoware_vehicle_msgs/msg/turn_indicators_report.hpp>
#include <autoware_vehicle_msgs/msg/velocity_report.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>

#include "carla/autoware/messages/RosIdl.h"

using namespace carla::autoware;
namespace aw = autoware_vehicle_msgs::msg;
namespace ac = autoware_control_msgs::msg;
namespace gm = geometry_msgs::msg;

// ===========================================================================
// RIHS01 hash equivalence. The pinned strings are the former AwGoldens.inc /
// GeoGoldens.inc goldens, computed from the .msg closure extracted out of the
// pinned Humble Autoware image and verified against real Autoware wiring at
// the G0 gate. The runtime hashes from the Jazzy apt packages MUST equal them:
// this is the proof that the apt-installed definitions are wire-identical to
// what the Humble container speaks.
// ===========================================================================

TEST(rosidl, rihs01_hashes_match_the_g0_verified_goldens) {
  EXPECT_EQ(rihs01_hash<aw::VelocityReport>(),
            "RIHS01_9052adda949c32f4a98500abc1fb5bd23f2560e321eebdfbb25318d6108d4ce4");
  EXPECT_EQ(rihs01_hash<aw::SteeringReport>(),
            "RIHS01_aa3acc9ca95ebc4daf9dec0ecf87911ad9c196392857c3026bfead589db65a94");
  EXPECT_EQ(rihs01_hash<aw::GearReport>(),
            "RIHS01_4d14bc3f186c1a6af6a732bb5ebd540cdd742a56770012f4c3cb9e762de8f391");
  EXPECT_EQ(rihs01_hash<aw::ControlModeReport>(),
            "RIHS01_968feaa6441be3c3b161f2eb65972a4b15394d0a7ddc4664318551280d1ff222");
  EXPECT_EQ(rihs01_hash<aw::TurnIndicatorsReport>(),
            "RIHS01_c05a54cd244f1c9d683613b11c87a5b3ef816eed7a5f207368301221731a0964");
  EXPECT_EQ(rihs01_hash<aw::HazardLightsReport>(),
            "RIHS01_01ce3b4293a5c2799fd7483b2d62a790e26fe8f2b5d60e48149163475685f28a");
  EXPECT_EQ(rihs01_hash<ac::Control>(),
            "RIHS01_7818be59aa790ebb777db06e55a2c15e3756de4cc35c80b1e8271afc5bab2e9d");
  EXPECT_EQ(rihs01_hash<gm::PoseStamped>(),
            "RIHS01_10f3786d7d40fd2b54367835614bff85d4ad3b5dab62bf8bca0cc232d73b4cd8");
  EXPECT_EQ(rihs01_hash<gm::PoseWithCovarianceStamped>(),
            "RIHS01_26432f9803e43727d3c8f668d1fdb3c630f548af631e2f4e31382371bfea3b6e");
}

TEST(rosidl, dds_type_names_follow_rmw_convention) {
  EXPECT_STREQ(dds_type_name<aw::VelocityReport>(),
               "autoware_vehicle_msgs::msg::dds_::VelocityReport_");
  EXPECT_STREQ(dds_type_name<aw::SteeringReport>(),
               "autoware_vehicle_msgs::msg::dds_::SteeringReport_");
  EXPECT_STREQ(dds_type_name<aw::GearReport>(),
               "autoware_vehicle_msgs::msg::dds_::GearReport_");
  EXPECT_STREQ(dds_type_name<aw::ControlModeReport>(),
               "autoware_vehicle_msgs::msg::dds_::ControlModeReport_");
  EXPECT_STREQ(dds_type_name<aw::TurnIndicatorsReport>(),
               "autoware_vehicle_msgs::msg::dds_::TurnIndicatorsReport_");
  EXPECT_STREQ(dds_type_name<aw::HazardLightsReport>(),
               "autoware_vehicle_msgs::msg::dds_::HazardLightsReport_");
  EXPECT_STREQ(dds_type_name<aw::GearCommand>(),
               "autoware_vehicle_msgs::msg::dds_::GearCommand_");
  EXPECT_STREQ(dds_type_name<aw::TurnIndicatorsCommand>(),
               "autoware_vehicle_msgs::msg::dds_::TurnIndicatorsCommand_");
  EXPECT_STREQ(dds_type_name<aw::HazardLightsCommand>(),
               "autoware_vehicle_msgs::msg::dds_::HazardLightsCommand_");
  EXPECT_STREQ(dds_type_name<aw::Engage>(),
               "autoware_vehicle_msgs::msg::dds_::Engage_");
  EXPECT_STREQ(dds_type_name<ac::Control>(),
               "autoware_control_msgs::msg::dds_::Control_");
  EXPECT_STREQ(dds_type_name<gm::PoseStamped>(),
               "geometry_msgs::msg::dds_::PoseStamped_");
  EXPECT_STREQ(dds_type_name<gm::PoseWithCovarianceStamped>(),
               "geometry_msgs::msg::dds_::PoseWithCovarianceStamped_");
}

// ===========================================================================
// geometry_msgs Pose round-trips. These are the highest alignment-risk types
// in the bridged set: every position/orientation/covariance field is a
// double, so a single wrong offset or endianness slip would silently corrupt
// alignment data without tripping the (float/int-only) tests above.
// ===========================================================================

TEST(rosidl, pose_stamped_roundtrips_at_pinned_size) {
  gm::PoseStamped in;
  in.header.frame_id = "map";
  in.header.stamp.sec = 100;
  in.header.stamp.nanosec = 200u;
  in.pose.position.x = 1.5;
  in.pose.position.y = -2.25;
  in.pose.position.z = 3.75;
  in.pose.orientation.x = 0.1;
  in.pose.orientation.y = 0.2;
  in.pose.orientation.z = 0.3;
  in.pose.orientation.w = 0.9;

  std::vector<uint8_t> b;
  // header(4) + sec(4) + nanosec(4) + strlen(4) + "map\0"(4)
  //   + 3*f64 position(24) + 4*f64 orientation(32) = 76
  ASSERT_EQ(cdr_serialize(in, b), 76u);

  gm::PoseStamped out;
  ASSERT_TRUE(cdr_deserialize(b.data(), b.size(), out));
  EXPECT_EQ(out, in);  // rosidl types define operator==
}

TEST(rosidl, pose_with_covariance_stamped_roundtrips_at_pinned_size) {
  gm::PoseWithCovarianceStamped in;
  in.header.frame_id = "map";
  in.header.stamp.sec = 100;
  in.header.stamp.nanosec = 200u;
  in.pose.pose.position.x = 1.5;
  in.pose.pose.position.y = -2.25;
  in.pose.pose.position.z = 3.75;
  in.pose.pose.orientation.x = 0.1;
  in.pose.pose.orientation.y = 0.2;
  in.pose.pose.orientation.z = 0.3;
  in.pose.pose.orientation.w = 0.9;
  in.pose.covariance.fill(0.0);
  in.pose.covariance[0] = 0.1;
  in.pose.covariance[7] = 0.1;
  in.pose.covariance[14] = 0.1;
  in.pose.covariance[21] = 0.05;
  in.pose.covariance[28] = 0.05;
  in.pose.covariance[35] = 0.05;

  std::vector<uint8_t> b;
  // header(4) + sec(4) + nanosec(4) + strlen(4) + "map\0"(4)
  //   + 3*f64 position(24) + 4*f64 orientation(32) + 36*f64 covariance(288)
  //   = 364
  ASSERT_EQ(cdr_serialize(in, b), 364u);

  gm::PoseWithCovarianceStamped out;
  ASSERT_TRUE(cdr_deserialize(b.data(), b.size(), out));
  EXPECT_EQ(out, in);  // rosidl types define operator==
}

// ===========================================================================
// Byte equivalence. The expected buffers are the old hand codec's pinned
// outputs (from the former test_messages.cpp), carried over verbatim: the
// rosidl path must produce the exact same wire bytes.
// ===========================================================================

TEST(rosidl, steering_report_bytes_match_the_old_codec) {
  aw::SteeringReport m;
  m.stamp.sec = 0x11223344;
  m.stamp.nanosec = 0x55667788u;
  m.steering_tire_angle = 1.0f;

  std::vector<uint8_t> out;
  const size_t n = cdr_serialize(m, out);
  const std::vector<uint8_t> expect = {
      0x00, 0x01, 0x00, 0x00,  // PLAIN_CDR little-endian encapsulation
      0x44, 0x33, 0x22, 0x11,  // stamp.sec (LE)
      0x88, 0x77, 0x66, 0x55,  // stamp.nanosec (LE)
      0x00, 0x00, 0x80, 0x3F,  // steering_tire_angle 1.0f
  };
  EXPECT_EQ(n, 16u);
  EXPECT_EQ(out, expect);
}

TEST(rosidl, gear_report_bytes_match_the_old_codec) {
  aw::GearReport m;
  m.stamp.sec = 5;
  m.stamp.nanosec = 6u;
  m.report = 22;  // GearReport::PARK

  std::vector<uint8_t> out;
  const size_t n = cdr_serialize(m, out);
  // header(4) + sec(4) + nanosec(4) + report u8(1) = 13
  EXPECT_EQ(n, 13u);
  ASSERT_EQ(out.size(), 13u);
  EXPECT_EQ(out[4], 5);
  EXPECT_EQ(out[8], 6);
  EXPECT_EQ(out[12], 22);
}

TEST(rosidl, velocity_report_bytes_match_the_old_codec) {
  aw::VelocityReport m;
  m.header.stamp.sec = 1;
  m.header.stamp.nanosec = 2u;
  m.header.frame_id = "base_link";
  m.longitudinal_velocity = 4.0f;
  m.lateral_velocity = 0.0f;
  m.heading_rate = -1.0f;

  std::vector<uint8_t> out;
  const size_t n = cdr_serialize(m, out);
  // header(4) + sec(4) + nanosec(4) + strlen(4) + "base_link\0"(10) + pad(2)
  //   + 3*f32(12) = 40
  EXPECT_EQ(n, 40u);
  ASSERT_EQ(out.size(), 40u);
  EXPECT_EQ(out[12], 10);  // frame_id length = "base_link"(9) + NUL
  const char* fid = "base_link";
  for (int i = 0; i < 9; ++i) {
    EXPECT_EQ(out[16 + i], static_cast<uint8_t>(fid[i]));
  }
  EXPECT_EQ(out[25], 0x00);  // NUL
  // longitudinal_velocity 4.0f == 0x40800000 -> LE 00 00 80 40
  EXPECT_EQ(out[28], 0x00);
  EXPECT_EQ(out[29], 0x00);
  EXPECT_EQ(out[30], 0x80);
  EXPECT_EQ(out[31], 0x40);
}

// ===========================================================================
// Control round-trip + bounds. 78 bytes total is the old codec's pinned size
// (the Lateral trailing bool forces a 3-byte re-align before Longitudinal).
// ===========================================================================

static ac::Control sample_control() {
  ac::Control in;
  in.stamp.sec = 10;
  in.stamp.nanosec = 11u;
  in.control_time.sec = 12;
  in.control_time.nanosec = 13u;
  in.lateral.stamp.sec = 20;
  in.lateral.stamp.nanosec = 21u;
  in.lateral.control_time.sec = 22;
  in.lateral.control_time.nanosec = 23u;
  in.lateral.steering_tire_angle = 0.25f;
  in.lateral.steering_tire_rotation_rate = 0.5f;
  in.lateral.is_defined_steering_tire_rotation_rate = true;
  in.longitudinal.stamp.sec = 30;
  in.longitudinal.stamp.nanosec = 31u;
  in.longitudinal.control_time.sec = 32;
  in.longitudinal.control_time.nanosec = 33u;
  in.longitudinal.velocity = 4.0f;
  in.longitudinal.acceleration = 1.5f;
  in.longitudinal.jerk = -0.75f;
  in.longitudinal.is_defined_acceleration = true;
  in.longitudinal.is_defined_jerk = false;
  return in;
}

TEST(rosidl, control_roundtrips_every_field_at_the_pinned_size) {
  const ac::Control in = sample_control();
  std::vector<uint8_t> b;
  ASSERT_EQ(cdr_serialize(in, b), 78u);

  ac::Control out;
  ASSERT_TRUE(cdr_deserialize(b.data(), b.size(), out));
  EXPECT_EQ(out, in);  // rosidl types define operator==
}

TEST(rosidl, control_rejects_truncated_buffers) {
  std::vector<uint8_t> b;
  cdr_serialize(sample_control(), b);
  ac::Control out;
  EXPECT_FALSE(cdr_deserialize(b.data(), 77, out));  // one byte short
  EXPECT_FALSE(cdr_deserialize(b.data(), 40, out));  // truncated mid-message
}

TEST(rosidl, control_rejects_empty_and_garbage_buffers) {
  ac::Control out;
  EXPECT_FALSE(cdr_deserialize(nullptr, 0, out));
  const std::vector<uint8_t> header_only = {0x00, 0x01, 0x00, 0x00};
  EXPECT_FALSE(cdr_deserialize(header_only.data(), header_only.size(), out));
  const std::vector<uint8_t> garbage(10, 0xFF);
  EXPECT_FALSE(cdr_deserialize(garbage.data(), garbage.size(), out));
}

// ===========================================================================
// Subscriber-side command/engage messages: round-trip plus DDS padding
// tolerance (a publisher may pad the payload to a 4-byte boundary; trailing
// bytes must be ignored, mirroring the old positional parsers).
// ===========================================================================

TEST(rosidl, gear_command_roundtrips) {
  aw::GearCommand in;
  in.stamp.sec = 7;
  in.stamp.nanosec = 8u;
  in.command = 2;  // GearCommand::DRIVE
  std::vector<uint8_t> b;
  cdr_serialize(in, b);
  aw::GearCommand out;
  ASSERT_TRUE(cdr_deserialize(b.data(), b.size(), out));
  EXPECT_EQ(out.command, 2u);
}

TEST(rosidl, engage_roundtrips_and_tolerates_trailing_padding) {
  aw::Engage in;
  in.stamp.sec = 1;
  in.stamp.nanosec = 2u;
  in.engage = true;
  std::vector<uint8_t> b;
  cdr_serialize(in, b);

  b.resize(b.size() + 3, 0x00);  // simulate DDS 4-byte-boundary padding
  aw::Engage out;
  ASSERT_TRUE(cdr_deserialize(b.data(), b.size(), out));
  EXPECT_TRUE(out.engage);
}
