#include "EngageStateMachine.h"

#include <autoware_vehicle_msgs/msg/engage.hpp>

#include "carla/autoware/messages/RosIdl.h"

namespace carla {
namespace autoware {

uint8_t engage_to_mode(bool engaged) {
  return engaged ? 1 /*ControlModeReport::AUTONOMOUS*/ : 4 /*ControlModeReport::MANUAL*/;
}

// Deserialize a { builtin_interfaces/Time stamp; bool engage } message and
// report the engaged bool via `out`, returning whether the parse succeeded.
// Trailing DDS padding is ignored by the positional typed deserializer. On
// malformed/truncated input this returns false and leaves `out` untouched,
// so the caller keeps the cached mode unchanged.
static bool parse_engage(const uint8_t* cdr, size_t len, bool& out) {
  autoware_vehicle_msgs::msg::Engage m;
  if (!cdr_deserialize(cdr, len, m)) return false;
  out = m.engage;
  return true;
}

void EngageStateMachine::Init(const CarlaRos2Host& host) {
  host_ = host;

  // reliable/VOLATILE/keep-last-1 (CarlaRos2Qos: reliability 0 = reliable,
  // durability 0 = volatile, history_depth 1), NOT transient_local (an earlier draft's choice).
  // A transient_local SUBSCRIBER does not match a volatile PUBLISHER (requested
  // durability must be <= offered durability), and the G2 harness engages via
  // `ros2 topic pub`, whose default QoS is reliable/volatile -- a
  // transient_local subscription here would simply never match and G2 would
  // fail with no error, only silence. This also matches vehicle_cmd_gate's own
  // engage_sub_ QoS (see the header's Step-1 comment): reliable/volatile/1.
  // Trade-off: volatile forgoes latched replay of an engage published before
  // this extension came up. Acceptable because the live bring-up order is
  // "extension up, then engage" (the runner engages explicitly after the
  // extension is loaded), so there is never a missed-latch window in practice.
  CarlaRos2Qos qos{/*reliability=*/0u, /*durability=*/0u, /*history_depth=*/1u};

  // Topic/type pinned in Step 1 (see header comment): /autoware/engage,
  // autoware_vehicle_msgs/Engage. Like ControlSubscribers' *Command topics,
  // the CycloneDDS blob subscriber ignores type_hash, so "" is
  // correct -- no RIHS01 golden was computed for Engage (out of scope here;
  // see test_rosidl.cpp's RIHS01 golden precedent for how one would be added).
  host_.create_subscriber(
      host_.host_ctx, "/autoware/engage", "autoware_vehicle_msgs::msg::dds_::Engage_", "", &qos,
      [](void* user, const uint8_t* cdr, size_t len) {
        auto* self = static_cast<EngageStateMachine*>(user);
        bool engaged = false;
        if (!parse_engage(cdr, len, engaged)) return;  // malformed/truncated -> mode unchanged
        self->mode_.store(engage_to_mode(engaged), std::memory_order_relaxed);
      },
      this);
}

}  // namespace autoware
}  // namespace carla
