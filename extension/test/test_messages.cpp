#include <gtest/gtest.h>

#include <cstdint>
#include <string>
#include <vector>

#include "carla/autoware/messages/AutowareMessages.h"
#include "carla/autoware/messages/Cdr.h"

using namespace carla::autoware;

// ===========================================================================
// CdrWriter primitives / alignment (byte-exact)
// ===========================================================================

TEST(cdr_writer, emits_le_encapsulation_header) {
  CdrWriter w;
  const auto& b = w.bytes();
  ASSERT_EQ(b.size(), 4u);
  EXPECT_EQ(b[0], 0x00);
  EXPECT_EQ(b[1], 0x01);  // 0x0001 big-endian == CDR_LE
  EXPECT_EQ(b[2], 0x00);
  EXPECT_EQ(b[3], 0x00);
}

TEST(cdr_writer, i32_is_little_endian) {
  CdrWriter w;
  w.i32(0x01020304);
  const auto& b = w.bytes();
  ASSERT_EQ(b.size(), 8u);
  EXPECT_EQ(b[4], 0x04);
  EXPECT_EQ(b[5], 0x03);
  EXPECT_EQ(b[6], 0x02);
  EXPECT_EQ(b[7], 0x01);
}

TEST(cdr_writer, u8_then_f32_inserts_3_pad_bytes) {
  CdrWriter w;
  w.u8(0xAB);
  w.f32(1.0f);
  const auto& b = w.bytes();
  // header(4) + u8(1) + pad(3) + f32(4) = 12
  ASSERT_EQ(b.size(), 12u);
  EXPECT_EQ(b[4], 0xAB);
  EXPECT_EQ(b[5], 0x00);  // 3 alignment pad bytes
  EXPECT_EQ(b[6], 0x00);
  EXPECT_EQ(b[7], 0x00);
  // 1.0f == 0x3F800000 -> LE 00 00 80 3F
  EXPECT_EQ(b[8], 0x00);
  EXPECT_EQ(b[9], 0x00);
  EXPECT_EQ(b[10], 0x80);
  EXPECT_EQ(b[11], 0x3F);
}

TEST(cdr_writer, u8_then_f64_inserts_7_pad_bytes) {
  CdrWriter w;
  w.u8(0x01);
  w.f64(2.0);
  const auto& b = w.bytes();
  // header(4) + u8(1) + pad(7) + f64(8) = 20
  ASSERT_EQ(b.size(), 20u);
  for (size_t i = 5; i < 12; ++i) {
    EXPECT_EQ(b[i], 0x00) << "expected pad byte at " << i;
  }
}

TEST(cdr_writer, string_is_length_including_nul_then_bytes_then_nul) {
  CdrWriter w;
  w.str("abc");
  const auto& b = w.bytes();
  // header(4) + len u32(4) + "abc"(3) + NUL(1) = 12
  ASSERT_EQ(b.size(), 12u);
  EXPECT_EQ(b[4], 0x04);  // length = 3 + NUL = 4 (LE)
  EXPECT_EQ(b[5], 0x00);
  EXPECT_EQ(b[6], 0x00);
  EXPECT_EQ(b[7], 0x00);
  EXPECT_EQ(b[8], 'a');
  EXPECT_EQ(b[9], 'b');
  EXPECT_EQ(b[10], 'c');
  EXPECT_EQ(b[11], 0x00);  // NUL terminator
}

// ===========================================================================
// CdrReader round-trip + bounds checking
// ===========================================================================

TEST(cdr_reader, roundtrips_all_primitives) {
  CdrWriter w;
  w.u8(0x7F);
  w.i32(-123456);
  w.u32(0xDEADBEEFu);
  w.f32(3.5f);
  w.f64(-2.25);
  w.str("hello");
  const auto& b = w.bytes();

  CdrReader r(b.data(), b.size());
  EXPECT_EQ(r.u8(), 0x7F);
  EXPECT_EQ(r.i32(), -123456);
  EXPECT_EQ(r.u32(), 0xDEADBEEFu);
  EXPECT_FLOAT_EQ(r.f32(), 3.5f);
  EXPECT_DOUBLE_EQ(r.f64(), -2.25);
  EXPECT_EQ(r.str(), "hello");
  EXPECT_TRUE(r.ok());
}

TEST(cdr_reader, rejects_short_buffer_instead_of_overrunning) {
  // Valid header but only 2 body bytes; an i32 read needs 4.
  std::vector<uint8_t> b = {0x00, 0x01, 0x00, 0x00, 0x01, 0x02};
  CdrReader r(b.data(), b.size());
  (void)r.i32();
  EXPECT_FALSE(r.ok());
}

TEST(cdr_reader, rejects_buffer_smaller_than_encapsulation_header) {
  std::vector<uint8_t> empty;
  CdrReader r(empty.data(), 0);
  EXPECT_FALSE(r.ok());
  (void)r.u8();
  EXPECT_FALSE(r.ok());
}

// ===========================================================================
// Type names + RIHS01 goldens (all seven, well-formed)
// ===========================================================================

template <typename T>
static void expect_wellformed_rihs01() {
  const std::string h = AwTopicInfo<T>::type_hash();
  EXPECT_EQ(h.rfind("RIHS01_", 0), 0u) << "not RIHS01-prefixed: " << h;
  ASSERT_EQ(h.size(), 71u) << "RIHS01 must be prefix(7) + 64 hex: " << h;
  for (size_t i = 7; i < h.size(); ++i) {
    const char c = h[i];
    const bool hex = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    EXPECT_TRUE(hex) << "non-lowercase-hex char in hash: " << h;
  }
}

TEST(messages, type_names_follow_dds_convention) {
  EXPECT_STREQ(AwTopicInfo<VelocityReport>::type_name(),
               "autoware_vehicle_msgs::msg::dds_::VelocityReport_");
  EXPECT_STREQ(AwTopicInfo<SteeringReport>::type_name(),
               "autoware_vehicle_msgs::msg::dds_::SteeringReport_");
  EXPECT_STREQ(AwTopicInfo<GearReport>::type_name(),
               "autoware_vehicle_msgs::msg::dds_::GearReport_");
  EXPECT_STREQ(AwTopicInfo<ControlModeReport>::type_name(),
               "autoware_vehicle_msgs::msg::dds_::ControlModeReport_");
  EXPECT_STREQ(AwTopicInfo<TurnIndicatorsReport>::type_name(),
               "autoware_vehicle_msgs::msg::dds_::TurnIndicatorsReport_");
  EXPECT_STREQ(AwTopicInfo<HazardLightsReport>::type_name(),
               "autoware_vehicle_msgs::msg::dds_::HazardLightsReport_");
  EXPECT_STREQ(AwTopicInfo<Control>::type_name(),
               "autoware_control_msgs::msg::dds_::Control_");
}

TEST(messages, all_seven_type_hashes_are_wellformed_rihs01) {
  expect_wellformed_rihs01<VelocityReport>();
  expect_wellformed_rihs01<SteeringReport>();
  expect_wellformed_rihs01<GearReport>();
  expect_wellformed_rihs01<ControlModeReport>();
  expect_wellformed_rihs01<TurnIndicatorsReport>();
  expect_wellformed_rihs01<HazardLightsReport>();
  expect_wellformed_rihs01<Control>();
}

// ===========================================================================
// Report serializers (byte-exact layout)
// ===========================================================================

// SteeringReport.msg is a bare `builtin_interfaces/Time stamp` + float32 --
// crucially there is NO std_msgs/Header, hence NO frame_id string. Asserting
// the total size is exactly 16 pins that: had we (wrongly, per the brief draft)
// written a frame_id, the buffer would be far larger.
TEST(messages, steering_report_serializes_without_frame_id) {
  SteeringReport m{};
  m.stamp.sec = 0x11223344;
  m.stamp.nanosec = 0x55667788u;
  m.steering_tire_angle = 1.0f;

  std::vector<uint8_t> out;
  const size_t n = cdr_serialize(m, out);
  EXPECT_EQ(n, 16u);
  ASSERT_EQ(out.size(), 16u);
  // encapsulation header
  EXPECT_EQ(out[0], 0x00);
  EXPECT_EQ(out[1], 0x01);
  EXPECT_EQ(out[2], 0x00);
  EXPECT_EQ(out[3], 0x00);
  // stamp.sec (LE)
  EXPECT_EQ(out[4], 0x44);
  EXPECT_EQ(out[5], 0x33);
  EXPECT_EQ(out[6], 0x22);
  EXPECT_EQ(out[7], 0x11);
  // stamp.nanosec (LE)
  EXPECT_EQ(out[8], 0x88);
  EXPECT_EQ(out[9], 0x77);
  EXPECT_EQ(out[10], 0x66);
  EXPECT_EQ(out[11], 0x55);
  // steering_tire_angle 1.0f (LE 00 00 80 3F)
  EXPECT_EQ(out[12], 0x00);
  EXPECT_EQ(out[13], 0x00);
  EXPECT_EQ(out[14], 0x80);
  EXPECT_EQ(out[15], 0x3F);
}

TEST(messages, gear_report_serializes_time_then_uint8) {
  GearReport m{};
  m.stamp.sec = 5;
  m.stamp.nanosec = 6u;
  m.report = 22;  // PARK

  std::vector<uint8_t> out;
  const size_t n = cdr_serialize(m, out);
  // header(4) + sec(4) + nanosec(4) + report u8(1) = 13
  EXPECT_EQ(n, 13u);
  ASSERT_EQ(out.size(), 13u);
  EXPECT_EQ(out[4], 5);
  EXPECT_EQ(out[8], 6);
  EXPECT_EQ(out[12], 22);
}

// VelocityReport.msg carries a std_msgs/Header, so its frame_id ("base_link")
// IS on the wire -- the opposite of SteeringReport above.
TEST(messages, velocity_report_serializes_header_frame_id_and_floats) {
  VelocityReport m{};
  m.header.stamp.sec = 1;
  m.header.stamp.nanosec = 2u;
  m.longitudinal_velocity = 4.0f;
  m.lateral_velocity = 0.0f;
  m.heading_rate = -1.0f;

  std::vector<uint8_t> out;
  const size_t n = cdr_serialize(m, out);
  // header(4) + sec(4) + nanosec(4) + strlen(4) + "base_link\0"(10) + pad(2)
  //   + 3*f32(12) = 40
  EXPECT_EQ(n, 40u);
  ASSERT_EQ(out.size(), 40u);
  // frame_id length = "base_link"(9) + NUL = 10
  EXPECT_EQ(out[12], 10);
  EXPECT_EQ(out[13], 0);
  EXPECT_EQ(out[14], 0);
  EXPECT_EQ(out[15], 0);
  const char* fid = "base_link";
  for (int i = 0; i < 9; ++i) {
    EXPECT_EQ(out[16 + i], static_cast<uint8_t>(fid[i]));
  }
  EXPECT_EQ(out[25], 0x00);  // NUL
  EXPECT_EQ(out[26], 0x00);  // 2 alignment pad bytes before the floats
  EXPECT_EQ(out[27], 0x00);
  // longitudinal_velocity 4.0f == 0x40800000 -> LE 00 00 80 40
  EXPECT_EQ(out[28], 0x00);
  EXPECT_EQ(out[29], 0x00);
  EXPECT_EQ(out[30], 0x80);
  EXPECT_EQ(out[31], 0x40);
}

// ===========================================================================
// Control deserializer (round-trip + bounds)
// ===========================================================================

// Build a byte-exact Control CDR buffer with distinct values for every field,
// matching Control/Lateral/Longitudinal.msg (both control_time fields and every
// trailing bool included -- the fields the brief draft omitted).
static std::vector<uint8_t> build_control_buffer(const Control& in) {
  CdrWriter w;
  w.i32(in.stamp.sec);
  w.u32(in.stamp.nanosec);
  w.i32(in.control_time.sec);
  w.u32(in.control_time.nanosec);
  // lateral
  w.i32(in.lateral.stamp.sec);
  w.u32(in.lateral.stamp.nanosec);
  w.i32(in.lateral.control_time.sec);
  w.u32(in.lateral.control_time.nanosec);
  w.f32(in.lateral.steering_tire_angle);
  w.f32(in.lateral.steering_tire_rotation_rate);
  w.boolean(in.lateral.is_defined_steering_tire_rotation_rate);
  // longitudinal
  w.i32(in.longitudinal.stamp.sec);
  w.u32(in.longitudinal.stamp.nanosec);
  w.i32(in.longitudinal.control_time.sec);
  w.u32(in.longitudinal.control_time.nanosec);
  w.f32(in.longitudinal.velocity);
  w.f32(in.longitudinal.acceleration);
  w.f32(in.longitudinal.jerk);
  w.boolean(in.longitudinal.is_defined_acceleration);
  w.boolean(in.longitudinal.is_defined_jerk);
  return w.bytes();
}

static Control sample_control() {
  Control in{};
  in.stamp = {10, 11u};
  in.control_time = {12, 13u};
  in.lateral.stamp = {20, 21u};
  in.lateral.control_time = {22, 23u};
  in.lateral.steering_tire_angle = 0.25f;
  in.lateral.steering_tire_rotation_rate = 0.5f;
  in.lateral.is_defined_steering_tire_rotation_rate = true;
  in.longitudinal.stamp = {30, 31u};
  in.longitudinal.control_time = {32, 33u};
  in.longitudinal.velocity = 4.0f;
  in.longitudinal.acceleration = 1.5f;
  in.longitudinal.jerk = -0.75f;
  in.longitudinal.is_defined_acceleration = true;
  in.longitudinal.is_defined_jerk = false;
  return in;
}

TEST(messages, control_roundtrips_every_field) {
  const Control in = sample_control();
  const std::vector<uint8_t> b = build_control_buffer(in);
  // The bool at the end of Lateral (body offset 41) forces a 3-byte re-align
  // before Longitudinal's stamp; total body 74 + header 4 = 78.
  ASSERT_EQ(b.size(), 78u);

  Control out{};
  ASSERT_TRUE(cdr_deserialize(b.data(), b.size(), out));
  EXPECT_EQ(out.stamp.sec, 10);
  EXPECT_EQ(out.stamp.nanosec, 11u);
  EXPECT_EQ(out.control_time.sec, 12);
  EXPECT_EQ(out.control_time.nanosec, 13u);
  EXPECT_EQ(out.lateral.stamp.sec, 20);
  EXPECT_EQ(out.lateral.stamp.nanosec, 21u);
  EXPECT_EQ(out.lateral.control_time.sec, 22);
  EXPECT_EQ(out.lateral.control_time.nanosec, 23u);
  EXPECT_FLOAT_EQ(out.lateral.steering_tire_angle, 0.25f);
  EXPECT_FLOAT_EQ(out.lateral.steering_tire_rotation_rate, 0.5f);
  EXPECT_TRUE(out.lateral.is_defined_steering_tire_rotation_rate);
  EXPECT_EQ(out.longitudinal.stamp.sec, 30);
  EXPECT_EQ(out.longitudinal.stamp.nanosec, 31u);
  EXPECT_EQ(out.longitudinal.control_time.sec, 32);
  EXPECT_EQ(out.longitudinal.control_time.nanosec, 33u);
  EXPECT_FLOAT_EQ(out.longitudinal.velocity, 4.0f);
  EXPECT_FLOAT_EQ(out.longitudinal.acceleration, 1.5f);
  EXPECT_FLOAT_EQ(out.longitudinal.jerk, -0.75f);
  EXPECT_TRUE(out.longitudinal.is_defined_acceleration);
  EXPECT_FALSE(out.longitudinal.is_defined_jerk);
}

TEST(messages, control_rejects_truncated_buffer) {
  const std::vector<uint8_t> b = build_control_buffer(sample_control());
  ASSERT_EQ(b.size(), 78u);
  Control out{};
  // One byte short of the final bool.
  EXPECT_FALSE(cdr_deserialize(b.data(), 77, out));
  // Truncated mid-message.
  EXPECT_FALSE(cdr_deserialize(b.data(), 40, out));
}

TEST(messages, control_rejects_empty_and_garbage_buffers) {
  Control out{};
  EXPECT_FALSE(cdr_deserialize(nullptr, 0, out));  // no bytes at all
  const std::vector<uint8_t> header_only = {0x00, 0x01, 0x00, 0x00};
  EXPECT_FALSE(cdr_deserialize(header_only.data(), header_only.size(), out));
  const std::vector<uint8_t> garbage(10, 0xFF);
  EXPECT_FALSE(cdr_deserialize(garbage.data(), garbage.size(), out));
}
