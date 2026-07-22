#pragma once

// rosidl-backed message identity + CDR codec for every ROS 2 message this
// extension bridges across the host vtable. Serialization is delegated to
// the apt-installed packages' generated rosidl_typesupport_fastrtps_cpp
// functions (fastcdr, XCDRv1/PLAIN_CDR little-endian, 4-byte encapsulation
// header included — the exact host publish/subscribe buffer contract), and
// the REP-2011 RIHS01 type hash comes from the typesupport handle at
// runtime. No rclcpp/rmw/DDS enters the process: these are pure
// serialization calls.
//
// The primary templates are deliberately not defined; only the explicit
// specializations in RosIdl.cpp (one block per bridged message type) link.
// test_rosidl.cpp pins the wire bytes and hash strings against the former
// hand-written codec's goldens.

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace carla {
namespace autoware {

// DDS type name in the rmw convention "pkg::msg::dds_::Type_".
template <typename T>
const char* dds_type_name();

// "RIHS01_<64 lowercase hex>" runtime hash string (REP-2011).
template <typename T>
const std::string& rihs01_hash();

// Serialize into a full CDR buffer (encapsulation header included),
// overwriting `out`; returns the total byte count.
template <typename T>
size_t cdr_serialize(const T& m, std::vector<uint8_t>& out);

// Deserialize a full CDR buffer (encapsulation header included). Returns
// false on null/truncated/malformed input; trailing padding is ignored.
template <typename T>
bool cdr_deserialize(const uint8_t* p, size_t n, T& m);

}  // namespace autoware
}  // namespace carla
