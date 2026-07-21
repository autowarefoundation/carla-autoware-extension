// Copyright (c) 2026 Computer Vision Center (CVC) at the Universitat Autonoma
// de Barcelona (UAB). MIT license.
//
// Narrow C ABI seam between CARLA core and an out-of-tree ROS 2 extension .so.
// DDS-FREE BY CONTRACT: this header is compiled into BOTH carla-server (no DDS
// vendor macros) and the out-of-tree extension. It must not include any DDS
// header nor odr-use PublisherImpl<>::Init (a header-inline DDS-entity
// constructor; odr-using it would silently pull DDS-vendor code into, and
// thus force a DDS-vendor link onto, whichever TU calls it).
// No C++ types cross the boundary: only PODs and function pointers.
// SAME-ARCH-ONLY CONTRACT: the seam is a same-process dlopen of a .so built
// against the same compiler/ABI as the host, not a network or cross-arch
// wire format, so plain `size_t`/`int` (platform-width C types) are safe at
// the boundary — there is no independent "extension platform" to skew them.
// The POD view structs (CarlaRos2Qos, CarlaRos2Transform,
// CarlaRos2VehicleStatusView, CarlaRos2AckermannPod, CarlaRos2SensorSample)
// deliberately carry NO size/reserved forward-compat padding fields: the ABI
// versioning model is a single `==` lockstep on CARLA_ROS2_EXTENSION_API_VERSION
// (see carla_ros2_extension_init below), so ANY layout change to a boundary
// struct (reorder/widen/insert a field) MUST bump that version, not grow a
// reserved field. test/common/test_ros2_extension_abi.cpp pins the exact
// sizeof/offsetof of every such struct for exactly this reason.
#ifndef CARLA_ROS2_EXTENSION_H
#define CARLA_ROS2_EXTENSION_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CARLA_ROS2_EXTENSION_API_VERSION 1u

// Sensor streams the extension can observe (values pinned; append-only).
typedef enum {
  CARLA_ROS2_SENSOR_LIDAR          = 1,  // legacy 16-byte cloud
  CARLA_ROS2_SENSOR_LIDAR_EXT      = 2,  // 10-float PointXYZIRCAEDT cloud
  CARLA_ROS2_SENSOR_IMU            = 3,
  CARLA_ROS2_SENSOR_GNSS           = 4,
  CARLA_ROS2_SENSOR_VEHICLE_STATUS = 5   // per-frame ego status/odometry stream
} CarlaRos2SensorKind;

// DDS QoS as plain enums (mirrors carla::ros2::PublisherQos without depending on it).
typedef struct {
  uint8_t  reliability;    // 0 = reliable, 1 = best_effort
  uint8_t  durability;     // 0 = volatile, 1 = transient_local
  uint32_t history_depth;  // keep-last depth (0 clamped to 1 by the host)
} CarlaRos2Qos;

// Ego world transform: CARLA left-handed centimetres + quaternion.
typedef struct {
  double x_cm, y_cm, z_cm;
  double qx, qy, qz, qw;
} CarlaRos2Transform;

// Per-frame ego status POD delivered to a VEHICLE_STATUS observer. Buffers
// (ros_name) are valid ONLY during the callback; copy if retained.
typedef struct {
  uint32_t actor_id;
  const char* ros_name;
  CarlaRos2Transform transform;
  double   velocity_mps;            // longitudinal, body frame
  double   lateral_velocity_mps;
  double   yaw_rate_rps;
  double   steering_tire_angle_rad; // positive = left (Autoware convention, already
                                     // applied by the host — do NOT negate again)
  int32_t  gear;                    // CARLA gear
  double   sim_time_s;               // ROS2 sim clock; a DIFFERENT clock basis from
                                      // on_tick's UE world clock below
} CarlaRos2VehicleStatusView;

// Raw LiDAR/IMU/GNSS observers deliver a type-erased buffer + kind; v1 extension
// uses only VEHICLE_STATUS (poses/status synthesized from it). The generic
// sample keeps the seam future-proof without adding message vocabulary to core.
typedef struct {
  int      kind;                        // CarlaRos2SensorKind
  uint32_t actor_id;
  const char* ros_name;
  const void* data;                     // kind-specific POD; VEHICLE_STATUS => CarlaRos2VehicleStatusView*
  size_t   data_size;
} CarlaRos2SensorSample;

typedef uint64_t CarlaRos2PubHandle;    // 0 = invalid
typedef uint64_t CarlaRos2SubHandle;    // 0 = invalid

// Ackermann command the extension routes into the core actuation path.
typedef struct {
  float steer;         // rad (CARLA sign, after the extension's compensation/flip)
  float steer_speed;   // rad/s
  float speed;         // m/s
  float acceleration;  // m/s^2
  float jerk;          // m/s^3
} CarlaRos2AckermannPod;

// Invoked SYNCHRONOUSLY on the host's sensor dispatch thread (whichever thread
// produces the sample) inside register_sensor_observer's registration; it must
// return quickly and non-blocking (no I/O, no locks the dispatch thread could
// contend), and the host gives no reentrancy guarantee (the same or a
// different observer may be invoked again, from the same or another thread,
// before this call returns).
typedef void (*CarlaRos2SensorObserver)(void* user, const CarlaRos2SensorSample* sample);
// Delivers ONE received message as a full raw CDR buffer: `cdr`/`len` span the
// complete serialized message INCLUDING the leading 4-byte CDR encapsulation
// header (classic PLAIN_CDR little-endian is 0x00 0x01 0x00 0x00), exactly as it
// arrives on the wire — the host does no stripping. `cdr` is valid ONLY for the
// duration of the call; copy if retained.
typedef void (*CarlaRos2SubCallback)(void* user, const uint8_t* cdr, size_t len);

// Host vtable: filled by core, consumed by the extension. host_ctx is passed
// back to every function (recovers the ROS2 singleton context).
typedef struct CarlaRos2Host {
  uint32_t api_version;
  void*    host_ctx;

  // Registration is NOT thread-safe against dispatch: only call this from
  // carla_ros2_extension_init or the game thread, never concurrently with an
  // in-flight sensor dispatch.
  void (*register_sensor_observer)(void* host_ctx, int kind,
                                   CarlaRos2SensorObserver cb, void* user);

  // Endpoint lifetime is HOST-OWNED: there is deliberately no destroy_publisher/
  // destroy_subscriber in this ABI. The host reclaims every extension-created reader
  // and writer at unload (core calls TeardownExtensionEndpoints() BEFORE the
  // extension's on_shutdown and before dlclose), so a subscriber's data-available
  // listener can never fire into a freed extension state or an unloaded .so. The
  // extension therefore must NOT retain a handle past on_shutdown.
  CarlaRos2PubHandle (*create_publisher)(void* host_ctx, const char* topic,
                                         const char* type_name, const char* type_hash,
                                         const CarlaRos2Qos* qos);
  // `cdr`/`len` MUST be a full serialized CDR message INCLUDING the leading
  // 4-byte encapsulation header (classic PLAIN_CDR little-endian is
  // 0x00 0x01 0x00 0x00); the host wraps these bytes verbatim onto the wire and
  // does not prepend a header. Returns 0 on success, -1 on an unknown handle or
  // a write failure.
  int (*publish)(void* host_ctx, CarlaRos2PubHandle h, const uint8_t* cdr, size_t len);

  CarlaRos2SubHandle (*create_subscriber)(void* host_ctx, const char* topic,
                                          const char* type_name, const char* type_hash,
                                          const CarlaRos2Qos* qos,
                                          CarlaRos2SubCallback cb, void* user);

  // Fire-and-forget, like the native ROS 2 vehicle-control subscriber: an
  // unknown or stale actor_id (already unregistered, or never the ego) is
  // silently dropped, not reported back to the extension.
  void (*apply_ackermann_control)(void* host_ctx, uint32_t actor_id,
                                  const CarlaRos2AckermannPod* pod);

  // 0 if none registered. A reloaded episode invalidates any actor id the
  // extension cached — re-query this rather than reusing an old one.
  uint32_t (*get_ego_actor_id)(void* host_ctx);
  const char* (*get_actor_ros_name)(void* host_ctx, uint32_t actor_id);
} CarlaRos2Host;

// Extension vtable: filled by the extension, consumed by core.
typedef struct CarlaRos2Extension {
  uint32_t api_version;
  void*    ext_ctx;
  // sim_time_s here is the UE world clock — a DIFFERENT clock basis from
  // CarlaRos2VehicleStatusView::sim_time_s (the ROS2 sim clock) — and it
  // resets on episode reload.
  void (*on_tick)(void* ext_ctx, double sim_time_s);
  void (*on_shutdown)(void* ext_ctx);
} CarlaRos2Extension;

// The single exported symbol. Returns 0 on success; nonzero aborts the load.
// The extension MUST verify host->api_version == CARLA_ROS2_EXTENSION_API_VERSION
// and set out->api_version to its own before returning success. The HOST
// completes the handshake: after init returns 0, it re-checks
// out->api_version == CARLA_ROS2_EXTENSION_API_VERSION itself and aborts the
// load on mismatch — a version check is never trusted from only one side.
int carla_ros2_extension_init(const CarlaRos2Host* host, CarlaRos2Extension* out);

#ifdef __cplusplus
}  // extern "C"
#endif
#endif  // CARLA_ROS2_EXTENSION_H
