# Semi-native Autoware support — architecture proposal

This document describes the proposed architecture for running Autoware against CARLA `ue5-dev`'s native ROS 2 (DDS) publishers with no bridge in the data path. It condenses the design the verification assets in this repository were built against; the CARLA-core pieces are proposals for upstream `carla-simulator/carla` PRs, not shipped code.

## Design tiers

The support splits into three tiers so that Autoware vocabulary never enters the CARLA core:

1. **Tier A — CARLA core extension API** (upstream `carla-simulator/carla` work): a server flag `--ros2-extension=<path.so>` loads an extension shared library after ROS 2 startup. The ABI is a narrow `extern "C"` struct-of-function-pointers handshake (`carla_ros2_extension_init`) with an API version check; no C++ types cross the boundary. The host interface exposes five capability groups: sensor observation (POD-view callbacks on the dispatch thread), CDR-blob publisher creation on the existing DDS participant, raw-CDR subscriber registration, a control sink into the core actuation path, and clock/actor queries. Supporting core items: `ros_topic_name` override, per-sensor QoS attributes, an acceleration-control apply path, `SetPublishTF` coverage, and an opt-in extended per-point LiDAR layer.
2. **Tier B — `libcarla-autoware-extension.so`** (this repository, future `extension/`): hand-written POD structs + CDR serialization + REP-2011 type hashes for the Autoware message set (`autoware_vehicle_msgs`, `autoware_control_msgs`); publishes `/vehicle/status/*` from the ego status stream and `PointCloud2` in `PointXYZIRCAEDT` layout with Autoware QoS; subscribes `/control/command/*` and maps `Control` to acceleration control. Type-hash goldens pin to the Autoware container's distro.
3. **Tier C — declarative runner** (this repository, future `runner/`): a Python CARLA client that reads the sensor-kit calibration YAML as the single source of truth, spawns the ego + sensor set with the right `ros_name`/topic/QoS attributes, and owns the synchronous tick loop.

On the Autoware side, the official Docker image (`universe-devel`) runs unmodified except for launch/description overlays (sensor kit, vehicle profile, an `e2e_simulator.launch.xml` native-mode branch that launches nothing in the data path).

## What is verified today (G0)

The assets in this repository prove the transport layer end-to-end with **zero new CARLA code** beyond the prerequisite branch: a CARLA dev build launched with `--ros2 --rmw=cyclonedds` publishes the spike sensor stack (`scripts/spike_stack.json`), and from inside the Autoware container every topic in `scripts/expected_topics.yaml` is present, correctly typed, publisher-QoS-correct, and deserializable (`ros2 topic echo` succeeds). The captured run records live in [environment.md](environment.md) and [g0-report.md](g0-report.md) (added with the verification assets in this PR stack).

## Verification design

- The interop gate's verdict logic (`scripts/interop_lib.py`) is pure: the subprocess runner is injected, so the presence/type/QoS/echo/rate rules are unit-tested in CI without ROS or CARLA.
- The gate's runtime dependencies inside the container are deliberately minimal: the `ros2` CLI and PyYAML. It stays in Python because it is **off the data path** — it observes topics; it never carries data. The performance-relevant C++ lives in CARLA core (`Ros2Native`) and the future extension `.so`.
- **Future work (G3):** at the full configured LiDAR rate, CLI-based measurement (`ros2 topic hz`, Python subscribers) becomes the bottleneck and under-reports. G3 adds an rclcpp-based C++ rate-measurement harness; the YAML contract and the `interop_lib` verdict logic are measurement-backend-agnostic and consume its output unchanged.

## Non-goals

Lanelet2 publishing from CARLA, per-vendor forks, `scenario_simulator_v2` integration, and camera-based functions (traffic-light recognition) are out of scope for this proposal. The CARLA 0.9.15 bridge (`autoware_carla_interface`) is unaffected.
