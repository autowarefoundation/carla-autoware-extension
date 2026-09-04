# Phase 0 - UE 5.8 / CARLA `ue58-dev` bring-up record

Date: 2026-09-03. Machine: RTX 5090 (driver 580.173.02), 24 cores, 62 GB RAM,
Ubuntu 24.04, ROS 2 Jazzy at `/opt/ros/jazzy`.

Phase 0 asked one question: does upstream's in-tree Autoware layer on CARLA
`ue58-dev` come up on UE 5.8 on this machine, publishing its native ROS 2
topics? It does. This file records the versions, the measured numbers, and the
deviations from the plan that a later phase has to account for.

## Versions

| Component     | Value                                                                        |
| ------------- | ---------------------------------------------------------------------------- |
| Engine        | `CarlaUnreal/UnrealEngine@ue58-dev-carla` `cacb25b99f14` (5.8)               |
| CARLA         | `upstream/ue58-dev` `5f58df579` (worktree `~/src/carla-ue58`)                |
| Content       | `carla-content@ue58-dev-carla` `981cdcbae2`                                  |
| Toolchain SDK | `v26_clang-20.1.8-rockylinux8`                                               |
| DLSS SDK      | `a291cc7`                                                                    |
| Python client | `carla-0.10.0-cp312` wheel built from this tree, installed in `~/carla-venv` |

## Steps and outcomes

- Engine switched in place (`git checkout -f -B ue58-dev-carla`), 5.5 binaries
  removed; `Setup.sh` and `GenerateProjectFiles.sh` OK; the stale
  `v23_clang-18.1.0-rockylinux8` SDK was deleted; the ccache clang wrapper was
  re-applied to the new v26 SDK.
- `make UnrealEditor ShaderCompileWorker`: UnrealEditor `Total execution time:
2500.51 seconds`, ShaderCompileWorker `78.90 seconds` - about 43 minutes
  wall-clock in total, against the plan's estimate of 2-4 hours
  (`05-ue-build.log`). ccache was cold for this build: `Hits: 0 / 3327`.
- CARLA configure (Development preset, `ENABLE_ROS2=ON`, `BUILD_CARLA_UNREAL=ON`)
  OK against the v26 sysroot; `carla-client`, `carla-server` and
  `carla-python-api` all built (`rc=0`); wheel
  `carla-0.10.0-cp312-cp312-linux_x86_64.whl` installed into `~/carla-venv`.
- `libcarla_test_server` (benchmarks excluded): `279 tests from 52 test suites
ran. (12286 ms total)`, `[  PASSED  ] 279 tests.`, no failures
  (`09-gtest.log`). Upstream reports 266 tests on their own tree; this is our
  count on this branch, not a parity claim.
- The filtered `*cyclonedds_fragment_gather*:*ros2*` run is green: `8 tests from
3 test suites ran`, `[  PASSED  ] 8 tests.`, including all six
  `cyclonedds_fragment_gather` cases, which confirms the CycloneDDS `from_ser`
  fragment-reassembly fix is present and working on this branch
  (`09-gtest-ros2.log`).
- `carla-unreal-editor` built; the simulator runs headless as
  `-game -RenderOffScreen -nosound -ros2 -rmw=fastdds -ros-domain-id=42`.
  `LogCarlaServer: Initialized CarlaServer: Ports(rpc=2000, streaming=2001,
secondary=2002)` followed by `ROS2: enabled with middleware 'fastdds'` and
  `Fast-DDS transport: UDPv4 only`.
- **No `VK_ERROR_DEVICE_LOST`.** Zero occurrences across both launch logs on
  RTX 5090 / driver 580.173.02, so upstream issue `#9826` does not reproduce
  on this machine.
- `autoware_demo.py --load_map Town10HD_Opt`: ego spawned, sensor kit attached
  (`LogCarla: VehicleStatusSensor attached to a vehicle`). `--mgrs_off` was
  **not** needed - the GNSS blueprint the demo wants exists on this build.
- 23 ROS 2 topics visible from the host, of which 15 are the Autoware-facing
  sensing / vehicle-status / clock set. `ros2 topic echo --once
/vehicle/status/velocity_status` returned a real, well-formed sample.
- `smoke.test_ros2`: `OK`, 5 tests, 131.546 s - see "Smoke test" below.

## Startup cost: cold vs warm shader DDC

The first launch on UE 5.8 took **815 s (13 m 35 s)** from process start to the
RPC port accepting connections, because UE 5.8's global shaders
(`SF_VULKAN_SM6`, 35-64 s per job) had no Derived Data Cache entries yet.

With the DDC warm, the same launch line reaches RPC in **22 s** and **20 s** on
two subsequent launches - a ~37x reduction. Anything that budgets simulator
start-up should assume ~20 s warm and reserve the 13-minute figure only for the
first launch after an engine or shader-format change.

## Large-sample DDS throughput: `net.core.rmem_default`

The first topic survey showed message loss that split cleanly by sample size:
small topics were exact at their configured rate, while the 236 KB LiDAR
point cloud ran at **2.0-2.6 Hz against a configured 10 Hz** (`sensor_tick 0.1`)
and camera images at **0.8 Hz**. Cumulative UDP receive-buffer errors climbed
**532 -> 4820** during that measurement window.

The cause was `net.core.rmem_default = 212992` (208 KB) - smaller than a single
LiDAR sample, so the kernel dropped datagrams before Fast-DDS could reassemble
them. `rmem_max` was already 64 MB, but a socket that does not explicitly ask
for a larger buffer is bounded by `rmem_default`, and the Fast-DDS participant
does not ask.

After raising `net.core.rmem_default` to **8388608** (8 MB), the survey was
repeated against a freshly spawned kit (`13b-topics.txt`):

| Topic                                  | Sample size                            | Before     | After              |
| -------------------------------------- | -------------------------------------- | ---------- | ------------------ |
| `/sensing/lidar/top/pointcloud_raw_ex` | 47.5 KB this run (236.7 KB previously) | 2.0-2.6 Hz | **10.000 Hz**      |
| `/sensing/camera/front/image`          | 3.69 MB                                | 0.8 Hz     | **10.000 Hz**      |
| `/vehicle/status/velocity_status`      | small                                  | exact      | 100.000 Hz (exact) |
| `/clock`                               | small                                  | exact      | 99.999 Hz (exact)  |

Cumulative UDP receive-buffer errors over the entire re-measurement window,
including a 20 s `ros2 topic bw` on the 3.69 MB camera topic sustaining
**37.06 MB/s**: **4820 -> 4820, a delta of zero**, against a delta of 4288 in
the previous window.

The LiDAR point clouds happened to be smaller this run (47.5 KB - a
scene-dependent quantity), so the camera topic is the decisive large-sample
evidence: 3.69 MB samples arriving at the full configured 10 Hz with no
kernel drops at all. The `rmem_default` fix is confirmed.

The measured rates track the demo's `--hz_rate` (default 100, i.e. a 0.01 s
fixed step), which is why `/clock` and `/vehicle/status/velocity_status` read
100 Hz here and 20 Hz in the earlier survey; the sensors keep their own
`sensor_tick` of 0.1 s in both.

## Smoke test

`python -m nose2 -v smoke.test_ros2` from `$CARLA_UE58/PythonAPI/test`.

Against a simulator launched with `-carla-rpc-port=3654` (see the first
deviation below), the suite is green: `Ran 5 tests in 131.546s` / `OK`, exit
code 0 (`14-smoke-ros2.log`).

| Test                                                                             | Result |
| -------------------------------------------------------------------------------- | ------ |
| `test_ros2_additional_sensors` - radar, DVS camera, semantic LiDAR publish paths | ok     |
| `test_ros2_api` - `enable_for_ros` / `disable_for_ros` / `is_enabled_for_ros`    | ok     |
| `test_ros2_enable_disable_cycle` - enable, tick, disable, tick, re-enable, tick  | ok     |
| `test_ros2_multi_sensor_publish` - 4 sensors + hero, 100-tick stress run         | ok     |
| `test_ros2_sensor_publish` - camera and LiDAR publish over DDS                   | ok     |

## Deviations and findings

- **The smoke suite does not use the RPC port the plan launches on.**
  `PythonAPI/test/smoke/__init__.py` hardcodes `TESTING_ADDRESS = ('localhost',
3654)`, with no CLI or environment override. Against the plan's
  `-carla-rpc-port=2000` simulator all five tests fail in `setUp` with
  `RuntimeError: Connection refused`. The simulator must be launched with
  `-carla-rpc-port=3654` for this suite. This is a harness/plan mismatch, not a
  defect in the build.

- **Host RMW: the earlier `rmw_cyclonedds_cpp` blindness did not reproduce.**
  An earlier survey found `rmw_cyclonedds_cpp` on the host seeing only
  `/parameter_events` and `/rosout` against the Fast-DDS simulator, while
  `rmw_fastrtps_cpp` saw everything. Re-run in this session, **both RMWs
  enumerate the identical 23 topics** (`13b-topics.txt`, sections B). The most
  likely explanation for the earlier result is a stale `ros2 daemon` cached
  against a different RMW or domain, since the daemon is keyed by both. Practical
  guidance: prefer `RMW_IMPLEMENTATION=rmw_fastrtps_cpp` for host-side checks
  against a `-rmw=fastdds` simulator because it is vendor-matched, and if
  CycloneDDS ever comes up empty, run `ros2 daemon stop` before concluding
  anything.

- **`ros2 topic hz` / `ros2 topic bw` hang past their timeout on large topics.**
  Both had to be `SIGKILL`ed on `/sensing/camera/front/image` after `timeout`'s
  `SIGTERM` was ignored. Any scripted measurement of a large topic needs
  `timeout -k` or an explicit kill.

- **`autoware_demo.py` hardcodes `client.set_timeout(60.0)`**
  (`PythonAPI/examples/autoware_demo.py:758`) with no CLI override. That is
  shorter than a cold-start `get_world()` on this machine, so the demo must not
  be started until the simulator has finished loading. It is not a problem with
  a warm DDC, where RPC is up in ~20 s.

- **`autoware_demo.py` ignores `SIGINT`.** Shutting down cleanly means
  `kill -INT` on the simulator first, confirming the RPC port is released, then
  `SIGKILL` on the demo process. `SIGINT` alone leaves it running.

- **UE 5.8 deprecates `bAllowUBALocalExecutor`.** The build log carries
  `The setting "bAllowUBALocalExecutor" is deprecated. Support for this setting
will be removed in a future version of Unreal Engine.` It still takes effect
  today, and it is still required for the ccache clang wrapper to work, but a
  replacement mechanism will be needed before it is removed.

- **Unity build was temporarily ON for the engine and plugin builds** and has
  been reverted to `<bUseUnityBuild>false</bUseUnityBuild>` in
  `~/.config/Unreal Engine/UnrealBuildTool/BuildConfiguration.xml` for
  incremental work. The next `carla-unreal-editor` build will recompile the
  plugin once as unity blobs become per-file objects; that is expected, not a
  regression.

## Logs

`~/ue58-logs/00-baseline.txt` through `14-smoke-ros2.log`, plus
`11b-game-launch.log` and `13b-topics.txt` from this session. Local only, not
committed.
