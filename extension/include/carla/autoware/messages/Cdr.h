#pragma once

// Minimal classic-CDR (a.k.a. plain CDR / XCDR1 with FINAL extensibility)
// little-endian codec, matching what rmw_cyclonedds emits/consumes on x86_64
// for the ROS 2 message types this extension bridges. Everything is laid out
// inline with natural alignment; there are NO DHEADERs (the Autoware messages
// used here are all FINAL structs), so nested structs (e.g. Control's Lateral /
// Longitudinal) serialize as if their fields were spliced in place.
//
// Wire prefix is the 4-byte DDS encapsulation header 00 01 00 00:
//   bytes[0..1] = representation id, big-endian 0x0001 = CDR_LE
//   bytes[2..3] = options (always 0)
// Alignment padding is measured from the START OF THE BODY (byte 4), NOT from
// the start of the buffer -- the encapsulation header does not count toward
// alignment. Both writer and reader implement that same rule; keep them in
// lock-step or every field past the first misaligned member decodes garbage.

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace carla {
namespace autoware {

class CdrWriter {
 public:
  CdrWriter() { buf_ = {0x00, 0x01, 0x00, 0x00}; }  // CDR_LE encapsulation header

  void u8(uint8_t v)   { align(1); put(&v, 1); }
  void boolean(bool v) { uint8_t b = v ? 1 : 0; u8(b); }   // ROS 2 bool == 1 CDR byte
  void u16(uint16_t v) { align(2); put(&v, 2); }
  void i32(int32_t v)  { align(4); put(&v, 4); }
  void u32(uint32_t v) { align(4); put(&v, 4); }
  void f32(float v)    { align(4); put(&v, 4); }
  void f64(double v)   { align(8); put(&v, 8); }
  // ROS 2 string: uint32 length INCLUDING the trailing NUL, then the bytes,
  // then the NUL terminator.
  void str(const std::string& s) {
    u32(static_cast<uint32_t>(s.size()) + 1u);
    put(s.data(), s.size());
    uint8_t z = 0;
    put(&z, 1);
  }

  const std::vector<uint8_t>& bytes() const { return buf_; }

 private:
  void put(const void* p, size_t n) {
    const auto* b = static_cast<const uint8_t*>(p);
    buf_.insert(buf_.end(), b, b + n);
  }
  void align(size_t a) {
    size_t body = buf_.size() - 4;  // header excluded from alignment
    while (body % a) { buf_.push_back(0); ++body; }
  }
  std::vector<uint8_t> buf_;
};

// Bounds-checked reader. Every accessor validates that the requested bytes
// (plus any alignment padding skipped to reach them) lie within [0, n); on any
// short/truncated input the reader latches an error (ok() -> false) and returns
// a zero-valued default instead of reading out of bounds. This is load-bearing:
// the Control deserializer feeds raw, attacker-influenceable DDS network bytes
// straight into this reader (Task 20), so an overrun must be impossible.
class CdrReader {
 public:
  CdrReader(const uint8_t* p, size_t n)
      : p_(p), n_(n), o_(4), ok_(n >= 4) {}  // <4 bytes: not even an encapsulation header

  uint8_t  u8()   { return read<uint8_t>(); }
  bool     boolean() { return read<uint8_t>() != 0; }
  int32_t  i32()  { return read<int32_t>(); }
  uint32_t u32()  { return read<uint32_t>(); }
  float    f32()  { return read<float>(); }
  double   f64()  { return read<double>(); }
  std::string str() {
    uint32_t len = u32();  // includes the trailing NUL
    std::string s;
    if (!ok_ || len == 0) { return s; }
    if (o_ + len > n_) { ok_ = false; return s; }
    s.assign(reinterpret_cast<const char*>(p_ + o_), len - 1);  // drop the NUL
    o_ += len;
    return s;
  }

  // True while every read so far stayed in bounds. Once false it stays false.
  bool ok() const { return ok_; }

 private:
  template <typename T>
  T read() {
    align(sizeof(T));  // primitive alignment == its size in CDR
    T v{};
    if (!ok_ || o_ + sizeof(T) > n_) { ok_ = false; return v; }
    std::memcpy(&v, p_ + o_, sizeof(T));
    o_ += sizeof(T);
    return v;
  }
  void align(size_t a) {
    while (ok_ && (o_ - 4) % a) {  // (o_ - 4): alignment measured from body start
      if (o_ >= n_) { ok_ = false; return; }
      ++o_;
    }
  }
  const uint8_t* p_;
  size_t n_;
  size_t o_;
  bool ok_;
};

}  // namespace autoware
}  // namespace carla
