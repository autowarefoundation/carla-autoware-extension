#pragma once

// CAMPAIGN STATUS -- COMMITTED BUT NEVER EXERCISED (2026-07-30). Cell
// CAL-seam was STRUCK by the owner's core-duel scope cut
// (benchmarks/config/cells.yaml `dropped:`; benchmarks/README.md's
// 2026-07-30 amendment), so this publisher never runs in a measurement and
// the C1(a) seam-overhead claim is UNMEASURED. Its unit tests
// (extension/test/test_bench_cloud_publisher.cpp) do exercise it, so it is
// verified code -- but no benchmark result rests on it, and its presence in
// the tree must not be read as evidence that the seam was measured. Kept
// rather than deleted, on purpose: a later campaign can pick the instrument
// up, and it costs a production run nothing (the $CARLA_BENCH_SEAM_CLOUD
// gate below leaves an unset environment byte-identical to today).
//
// CAL-seam isolation instrument, extension side. Publishes a synthetic
// sensor_msgs/PointCloud2 through the extension's C-ABI seam so its one-hop
// wall latency can be paired against the fork's in-core twin publisher on
// the SAME CARLA fork process with the SAME RMW -- the only measurement the
// seam-overhead claim rests on (Task 14 brief). The fork-side twin is
// env-gated CARLA_BENCH_INCORE_CLOUD=1 -> /bench/incore_cloud (see
// ROS2::SetTimestamp / ROS2::Enable in the integration repo's ROS2.cpp).
//
// The two publishers must be identical in EVERYTHING except which side of
// the seam they sit on: 28 800 points x 32 B point step (the canonical
// Autoware PointXYZIRCAEDT layout -- same field table as the fork's
// kLidarFieldsExtended, LibCarla/source/carla/ros2/publishers/
// PointCloudFieldsLayout.h), zero payload, 10 Hz, header.stamp = wall
// now(), a fixed-size preallocated message, tick-driven. Gated on
// $CARLA_BENCH_SEAM_CLOUD=1 so a production run (env var unset) is
// byte-identical to today: Init() creates no publisher and OnTick() never
// fires a publish. This header is an implementation detail of the
// extension .so, not part of the frozen C ABI seam.
//
// Unlike its siblings (GnssPosePublisher, StatusPublishers), the message
// object is a MEMBER, built once in Init() and left untouched by OnTick()
// apart from header.stamp: the payload is constant (all zero), so nothing
// else about the message should ever differ between publishes -- exactly
// what "fixed-size preallocated message" requires for a fair paired
// comparison against the fork's twin.

#include <chrono>
#include <cstdint>

#include <sensor_msgs/msg/point_cloud2.hpp>

#include "carla/ros2/extension/CarlaRos2Extension.h"

namespace carla {
namespace autoware {

class BenchCloudPublisher {
 public:
  // Reads $CARLA_BENCH_SEAM_CLOUD once. Unset (or any value other than "1")
  // leaves every other member a no-op: no publisher is created and OnTick()
  // never publishes, so production behaviour is untouched.
  void Init(const CarlaRos2Host& host);

  // Tick-driven -- called every frame from ext_on_tick; decimates to 10 Hz
  // by WALL-CLOCK elapsed time. This publisher's stamp basis is wall now(),
  // NOT the sim clock ext_on_tick's argument carries (CarlaRos2Extension.h:
  // CarlaRos2Extension::on_tick's sim_time_s is the UE world clock -- yet
  // another basis from the ROS2 sim clock the other publishers key off), so
  // decimation uses a steady clock rather than that argument.
  void OnTick();

  // Test/inspection accessor: true once $CARLA_BENCH_SEAM_CLOUD resolved to
  // "1" at Init() time. Lets unit tests confirm the gate without depending
  // on process-wide environment mutation ordering.
  [[nodiscard]] bool IsEnabled() const noexcept { return enabled_; }

 private:
  CarlaRos2Host host_{};
  CarlaRos2PubHandle pub_{0};
  bool enabled_{false};
  bool has_published_{false};
  std::chrono::steady_clock::time_point last_pub_{};
  sensor_msgs::msg::PointCloud2 msg_;
};

}  // namespace autoware
}  // namespace carla
