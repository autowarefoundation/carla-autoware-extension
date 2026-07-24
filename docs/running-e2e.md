# Running the live E2E stack (Nishi-Shinjuku, native CycloneDDS)

The live E2E stack drives official Autoware Humble over native CycloneDDS from
CARLA's own ROS 2 layer plus this repo's out-of-tree extension `.so` — no
carla-ros-bridge involved. This doc is the one-command-per-step bring-up; the
measured gate results live in [e2e-report.md](e2e-report.md).

## 1. Build

- CARLA editor: `cmake --build Build/Development --target carla-unreal-editor`
  (checked by `scripts/e2e/verify_editor_artifact.sh`, which fails loudly
  if the editor plugin `.so` is stale relative to CARLA HEAD).
- Extension: `source /opt/ros/jazzy/setup.bash && cmake -S extension -B extension/build -G Ninja && cmake --build extension/build -j`
  (needs `ros-jazzy-autoware-control-msgs`, `ros-jazzy-autoware-vehicle-msgs`, and
  `ros-jazzy-geometry-msgs` installed; produces
  `extension/build/libcarla-autoware-extension.so`, entrypoint
  `carla_ros2_extension_init`. The build links with
  `-Wl,--disable-new-dtags`, so the `.so` carries a build-tree `DT_RPATH`
  (not the default `DT_RUNPATH`) pointing at the ROS libraries; unlike
  `DT_RUNPATH`, which only resolves an object's direct dependencies,
  `DT_RPATH` propagates to the transitive rosidl/typesupport deps too, so
  carla-server dlopens the `.so` without extra environment.)

## 2. Container up + carla_msgs

```bash
docker compose -f docker/compose.yaml up -d
bash scripts/bootstrap_carla_msgs.sh
```

`bash scripts/bootstrap_carla_msgs.sh` is idempotent but not optional: the
`~/carla_msgs_ws` workspace it builds lives inside the container, outside
every compose mount, so a `docker compose ... up -d` that recreates the
container (e.g. after editing `docker/compose.yaml`) destroys it and it must
be rebuilt.

## 3. CARLA + extension + runner

```bash
source docker/env.sh
bash scripts/e2e/run_e2e.sh
```

`docker/env.sh` exports `CARLA_ROOT`, `CARLA_UNREAL_ENGINE_PATH`,
`ROS_DOMAIN_ID=0`, and `CYCLONEDDS_URI` for a human shell building/running
the stack by hand. `run_e2e.sh` itself pins `ROS_DOMAIN_ID`/`CYCLONEDDS_URI`
independently (so it stays correct even if this file was never sourced) and
needs only `CARLA_ROOT`/`CARLA_UNREAL_ENGINE_PATH` from the environment;
sourcing `docker/env.sh` first keeps a manual build/run consistent with what
the harness does. `run_e2e.sh` preflights the extension `.so` (fresh
editor artifact, `--extension-check` ABI probe), boots CARLA headless with
`--ros2 --rmw=cyclonedds --ros2-extension=<so>`, and runs
`python3 -m runner --host localhost --port 2000 --map NishishinjukuMap` in
the foreground so it owns `SIGINT` directly. The runner accepts
`--sensor-kit-calibration`/`--sensors-calibration` (default to the committed
copies under `runner/config/`), `--initial-pose X_M Y_M Z_M ROLL_DEG
PITCH_DEG YAW_DEG` (metres/degrees, default = map spawn point 0), and
`--async` (validated fallback if the ego does not propel in sync mode on this
CARLA 0.10/Chaos build).

## 4. Autoware (stock kit — overlay is YAGNI unless a change is forced)

```bash
docker compose -f docker/compose.yaml exec autoware bash -lc '
  source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash
  ros2 launch autoware_launch e2e_simulator.launch.xml \
    map_path:=/autoware_map/nishishinjuku \
    sensor_model:=awsim_labs_sensor_kit vehicle_model:=sample_vehicle \
    simulator_type:=carla launch_vehicle_interface:=false use_sim_time:=true \
    perception:=false rviz:=false'
```

These launch args were verified inside the running `autoware` container
(image `ghcr.io/autowarefoundation/autoware:universe-devel`) against the
pinned image's package set and `autoware_launch/launch/e2e_simulator.launch.xml`,
not copied from a draft:

- `sensor_model:=awsim_labs_sensor_kit` — the pinned image ships both
  `awsim_sensor_kit_description`/`_launch` AND
  `awsim_labs_sensor_kit_description`/`_launch`; the runner's committed
  `runner/config/sensor_kit_calibration.yaml`/`sensors_calibration.yaml` were
  extracted verbatim from `awsim_labs_sensor_kit_description`, so
  the kit name given to Autoware must match what the runner actually spawns
  (frame names `camera0..5/camera_link`, `velodyne_top/left/right_base_link`,
  `gnss_link`, `tamagawa/imu_link`). The image also ships an unrelated
  `carla_sensor_kit_description`/`_launch` (a different, single-lidar
  6-camera rig, `CAM_FRONT`/`CAM_BACK`/... frame names) that does **not**
  match the runner's sensor rig — do not use it.
- `simulator_type:=carla` — `e2e_simulator.launch.xml`'s own arg
  documents allowed values as `'awsim' or 'carla'`, and the pinned image
  ships a dedicated `autoware_launch/config/system/diagnostics/autoware-carla.yaml`
  (vs. `autoware-awsim.yaml`) with extended diagnostic timeouts for
  CARLA's network latency/update-rate profile and with the
  transform/pose-twist-fusion monitors removed as failing to load; this is
  the CARLA-native run, so it takes the CARLA diagnostics graph, not AWSIM's.
- `vehicle_model:=sample_vehicle`, `launch_vehicle_interface:=false`,
  `use_sim_time:=true` — confirmed present as real `e2e_simulator.launch.xml`
  args with these values; `sample_vehicle_description` and
  `awsim_labs_vehicle_description` ship identical `wheel_base: 2.79`, matching
  `SAMPLE_VEHICLE_WHEELBASE` in `runner/spawn.py`, so either vehicle package
  gives the same ego geometry — `sample_vehicle` is used as the simpler,
  non-AWSIM-branded name.

`perception:=false rviz:=false` were added after a 2026-07-22 investigation found
the documented full-perception line cannot come up on this `-devel` image. Two
independent hard blockers live entirely inside the perception subtree, so the
top-level perception toggle is the one stock-argument lever that clears both:

- `tier4_perception_launch/.../ground_segmentation.launch.py:649-653` resolves
  `FindPackageShare("autoware_ground_segmentation_cuda")` inside a
  `DeclareLaunchArgument` DEFAULT. Humble evaluates that default eagerly at
  launch time regardless of the `use_cuda_ground_segmentation:=false` gate, and
  the package is only stub-installed here (env-hook shells, no
  `package.xml`/lib/ament marker), so the launch aborts before it runs.
- `/root/autoware_data` is entirely absent, so every DNN detector `mode`
  (`perception.launch.xml`, default `camera_lidar_fusion`) is missing its model
  artifacts, and there is **no** non-ML perception mode — the cascade inside
  the perception subtree is effectively unbounded.

`perception:=false` (`e2e_simulator.launch.xml` → `launch_perception`) skips
the whole perception group, so neither the CUDA `FindPackageShare` nor any
`autoware_data` model path is ever evaluated. What it costs: **G1 NDT
localization is unaffected** — localization is not under perception, so
`ndt_scan_matcher`/`ekf_localizer`/`gyro_odometer` all still launch and NDT
still subscribes the raw LiDAR cloud. **G2 route + engage still runs** — the
full mission/scenario/behavior/motion planning + control + operation-mode stack
launches — but against an EMPTY perceived environment: nothing publishes
`/perception/object_recognition/objects` or the obstacle-segmentation occupancy
grid, so there is no dynamic-obstacle detection, avoidance, or obstacle stop. A
clear-route engage-and-drive test is exercised; any test that must perceive or
avoid an obstacle is not. Full perception requires a CUDA-enabled,
model-artifact-bearing Autoware image variant (a `*-cuda` and/or non-`-devel`
`:universe` tag with `autoware_data` baked in) — future work, not this image.
`rviz:=false` is headless-environment convenience only (no `DISPLAY` in the
container). Both are launch ARGS on the otherwise-stock line: the stock kit
config is untouched and the `feat/carla-native-nishishinjuku` overlay branch
remains un-forced.

The extension `.so` publishes the six `/vehicle/status/*` reports and
`/sensing/gnss/pose[_with_covariance]`, and subscribes `/control/command/*`
and `/autoware/engage`. The LiDAR cloud `/sensing/lidar/top/pointcloud_raw_ex`
is published by CARLA's own native in-tree LiDAR publisher (the runner
configures it via the `ros_topic_name` and `ros2_extended_lidar` blueprint
attributes on the spawned sensor), not by the extension `.so`.

Overlay branch `feat/carla-native-nishishinjuku` on `youtalk/autoware_launch`
is created ONLY if a concrete change is forced (e.g. a `traffic_light` module
disable, or a QoS param fix) — not preemptively.

## 5. Watching the run in RViz

The stock launch keeps `rviz:=false` (the launch itself is headless), but the
image ships the Autoware RViz plugins, so the run is watchable from the host
desktop:

```bash
xhost +local:                     # once per desktop session
bash scripts/e2e/launch_rviz.sh   # RViz2 inside the container, on the host display
```

The script execs `rviz2` in the `autoware` container with the
`autoware_launch` RViz profile (vehicle overlay, TF, LiDAR cloud, route and
trajectory displays) and `use_sim_time:=true` so the sim-paced TF tree is
accepted. `docker/compose.yaml` mounts the host X socket; rendering defaults
to Mesa software GL (`LIBGL_ALWAYS_SOFTWARE=0` to override when the container
has GPU access). RViz here is an **observer** — the gates below stay
script-driven — but the 2D Goal Pose tool works normally if you want to route
interactively instead of via `arm_closed_loop.sh`.

## 6. Arming a closed-loop drive (the G2 recipe)

With the stack up (steps 2–4, `WITH_AUTOWARE=1`, on-lanelet
`RUNNER_EXTRA_ARGS="--initial-pose -284.597 224.709 0.0 0 0 -34.187"`):

```bash
bash scripts/e2e/arm_closed_loop.sh          # reseed -> dummy perception -> route -> MRM off
bash scripts/e2e/gate_g2_closed_loop.sh 81571.616 50019.827   # engage + measure
```

`arm_closed_loop.sh` encodes the verified arm order (each step exists because
its absence cost a live run; see `e2e-report.md`): re-seed `/initialpose` at
the ego's current ground truth (NDT drifts while parked), start
`dummy_perception.py` **before** routing (clear-road objects/grid/pointcloud +
all-green signals — without it `behavior_path_planner` never emits a
trajectory), set the route via the AD API, and suppress the perception-off
false MRM (`vehicle_cmd_gate use_emergency_handling=false`, still required on
this image). Engage latches across re-arms: run
`arm_closed_loop.sh --disarm` before teleporting/re-seeding/re-arming.

G1/G3 need no arming: with the stack localizing, run
`bash scripts/e2e/gate_g1_localization.sh` and
`bash scripts/e2e/gate_g3_performance.sh` directly.
