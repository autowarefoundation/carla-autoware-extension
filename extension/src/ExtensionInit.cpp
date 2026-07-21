// The single exported symbol of libcarla-autoware-extension.so. The CARLA core
// loader (CarlaRos2ExtensionLoader, in the CARLA integration repo) dlopen's this .so
// and dlsym's `carla_ros2_extension_init`; core fills a CarlaRos2Host vtable,
// calls this function, and -- on a 0 return with a matching out->api_version --
// keeps the returned CarlaRos2Extension vtable for the episode lifetime.
//
// This TU is the one place the four otherwise-independent subsystems are wired
// together:
//   StatusPublishers   -- 6x /vehicle/status/* publishers
//   GnssPosePublisher  -- 2x /sensing/gnss/pose* publishers
//   ControlSubscribers -- 4x /control/command/* subscribers
//   EngageStateMachine -- 1x /autoware/engage subscriber
// The status stream is synthesized from ONE host observer
// (CARLA_ROS2_SENSOR_VEHICLE_STATUS): each frame, this file threads the engage
// machine's control mode and the control subscribers' cached command bytes into
// StatusInputs so the six status reports and both GNSS poses publish together.
//
// Contract mirrored from the mock extension (integration repo
// LibCarla/source/test/ros2_mock_extension/mock_extension.cpp), which passed the
// contract suite against the REAL host: check host + api_version, allocate an
// opaque ext_ctx, register the observer, populate the out-vtable, return 0.
// Endpoint lifetime is HOST-OWNED (CarlaRos2Extension.h): core calls
// TeardownExtensionEndpoints() BEFORE on_shutdown, so on_shutdown only frees the
// extension's own state and MUST NOT call any host teardown function.

#include "carla/ros2/extension/CarlaRos2Extension.h"

#include <new>

#include "engage/EngageStateMachine.h"
#include "publishers/GnssPosePublisher.h"
#include "publishers/StatusPublishers.h"
#include "subscribers/ControlSubscribers.h"

namespace {

// The opaque ext_ctx handed back to core: it owns every subsystem, so a single
// `delete` in on_shutdown reclaims the whole extension. Held by the host only as
// an opaque void*; its layout never crosses the C ABI seam.
struct ExtensionState {
  carla::autoware::StatusPublishers status;
  carla::autoware::GnssPosePublisher gnss;
  carla::autoware::ControlSubscribers control;
  carla::autoware::EngageStateMachine engage;
};

// Distinct nonzero return codes per failure class. The header
// only mandates "0 == success, nonzero aborts the load" -- the specific nonzero
// value is NOT contractual (the mock extension returns 1 for every reject), so these
// codes exist purely to localize a load failure in a core log.
enum InitResult {
  kOk = 0,
  kNullHost = 1,        // host vtable pointer missing
  kNullOut = 2,         // out vtable pointer missing
  kVersionMismatch = 3, // host ABI version != this extension's
  kAllocFailed = 4,     // ExtensionState allocation failed
};

// VEHICLE_STATUS observer: invoked synchronously on the host's sensor-dispatch
// thread. Threads the cross-subsystem state (engage mode + cached command bytes)
// into the status publishers, then drives the GNSS pose decimator. Both cached
// reads are atomic (see ControlSubscribers / EngageStateMachine), so no lock is
// held on this dispatch thread -- satisfying the observer's "return quickly,
// non-blocking" contract.
void ext_on_status(void* user, const CarlaRos2SensorSample* sample) {
  auto* st = static_cast<ExtensionState*>(user);
  // Defensive ABI-drift guard: core only ever routes the registered kind to
  // this callback (ROS2::DispatchVehicleStatusView filters by kind), but pin
  // that intent here so a future host that reused the observer for another kind
  // could never make us reinterpret a foreign POD as a vehicle-status view.
  if (!st || !sample || sample->kind != CARLA_ROS2_SENSOR_VEHICLE_STATUS ||
      sample->data == nullptr || sample->data_size < sizeof(CarlaRos2VehicleStatusView)) {
    return;
  }
  const auto* v = static_cast<const CarlaRos2VehicleStatusView*>(sample->data);

  // The observer view carries only the kinematic state; the mode/gear/turn/
  // hazard values come from the OTHER subsystems. Without this threading, the
  // control-mode and command-status reports would publish only their idle
  // defaults regardless of what Autoware commanded.
  carla::autoware::StatusInputs in;
  in.control_mode = st->engage.Mode();
  in.gear = st->control.CachedGear();
  in.turn_indicators = st->control.CachedTurnIndicators();
  in.hazard_lights = st->control.CachedHazardLights();
  st->status.OnVehicleStatus(*v, in);
  st->gnss.OnVehicleStatus(*v);
}

// on_tick: the UE world-clock per-frame hook. This extension is fully
// event-driven -- status is synthesized from the observer, actuation from the
// DDS subscriber callbacks -- so there is deliberately nothing to do per tick.
// A no-op here is contract-legal (the mock extension's on_tick is likewise a no-op).
void ext_on_tick(void* /*ext_ctx*/, double /*sim_time_s*/) {}

// on_shutdown: core has already run TeardownExtensionEndpoints() (host-owned
// endpoint lifetime), so no publisher/subscriber handle is live here. Just
// reclaim the extension's own state; do NOT call any host teardown function.
void ext_on_shutdown(void* ext_ctx) { delete static_cast<ExtensionState*>(ext_ctx); }

}  // namespace

extern "C" int carla_ros2_extension_init(const CarlaRos2Host* host, CarlaRos2Extension* out) {
  // Defensive argument + handshake checks. None of these touch
  // `out` or allocate: a rejected load must leave the caller's out-struct
  // exactly as it was. Order matters -- the version compare dereferences host,
  // so the null-host check must precede it.
  if (host == nullptr) return kNullHost;
  if (out == nullptr) return kNullOut;
  if (host->api_version != CARLA_ROS2_EXTENSION_API_VERSION) return kVersionMismatch;

  auto* st = new (std::nothrow) ExtensionState();
  if (st == nullptr) return kAllocFailed;

  // Create every endpoint FIRST (all four subsystems), so the state is fully
  // constructed before any callback can fire into it. create_publisher /
  // create_subscriber are not thread-safe against dispatch, but this runs on
  // the loader/game thread with no dispatch in flight (host-vtable rule).
  st->status.Init(*host);
  st->gnss.Init(*host);
  st->control.Init(*host);
  st->engage.Init(*host);

  // Register the observer LAST: once registered, the host may
  // dispatch a status sample into ext_on_status at any time, so nothing may run
  // ahead of a fully-initialized state. The subscriber callbacks captured above
  // are likewise safe -- they only touch atomics that are alive from
  // construction.
  host->register_sensor_observer(host->host_ctx, CARLA_ROS2_SENSOR_VEHICLE_STATUS,
                                 &ext_on_status, st);

  out->api_version = CARLA_ROS2_EXTENSION_API_VERSION;
  out->ext_ctx = st;
  out->on_tick = &ext_on_tick;
  out->on_shutdown = &ext_on_shutdown;
  return kOk;
}
