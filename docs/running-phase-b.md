# Running Phase B (Nishi-Shinjuku, native CycloneDDS)

Phase B drives official Autoware Humble over native CycloneDDS from CARLA's
own ROS 2 layer plus this repo's out-of-tree extension `.so` — no
carla-ros-bridge involved. This doc is the one-command-per-step bring-up.

## 1. Build

- CARLA editor: `cmake --build Build/Development --target carla-unreal-editor`
  (checked by `scripts/phase_b/verify_editor_artifact.sh`, which fails loudly
  if the editor plugin `.so` is stale relative to CARLA HEAD).
- Extension: `CARLA_ROOT=~/src/carla-autoware-integration CARLA_UNREAL_ENGINE_PATH=~/src/UnrealEngine cmake --build extension/build -j`
  (produces `extension/build/libcarla-autoware-extension.so`, entrypoint
  `carla_ros2_extension_init`).

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
bash scripts/phase_b/run_phase_b.sh
```

`docker/env.sh` exports `CARLA_ROOT`, `CARLA_UNREAL_ENGINE_PATH`,
`ROS_DOMAIN_ID=0`, and `CYCLONEDDS_URI` for a human shell building/running
Phase B by hand. `run_phase_b.sh` itself pins `ROS_DOMAIN_ID`/`CYCLONEDDS_URI`
independently (so it stays correct even if this file was never sourced) and
needs only `CARLA_ROOT`/`CARLA_UNREAL_ENGINE_PATH` from the environment;
sourcing `docker/env.sh` first keeps a manual build/run consistent with what
the harness does. `run_phase_b.sh` preflights the extension `.so` (fresh
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
    simulator_type:=carla launch_vehicle_interface:=false use_sim_time:=true'
```

These launch args were verified inside the running `autoware` container
(image `ghcr.io/autowarefoundation/autoware:universe-devel`) against the
pinned image's package set and `autoware_launch/launch/e2e_simulator.launch.xml`,
not copied from a draft:

- `sensor_model:=awsim_labs_sensor_kit` — the pinned image ships both
  `awsim_sensor_kit_description`/`_launch` AND
  `awsim_labs_sensor_kit_description`/`_launch`; the runner's committed
  `runner/config/sensor_kit_calibration.yaml`/`sensors_calibration.yaml` were
  extracted verbatim from `awsim_labs_sensor_kit_description` (Task 23), so
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

The extension `.so` publishes the six `/vehicle/status/*` reports and
`/sensing/gnss/pose[_with_covariance]`, and subscribes `/control/command/*`
and `/autoware/engage`. The LiDAR cloud `/sensing/lidar/top/pointcloud_raw_ex`
is published by CARLA's own native in-tree LiDAR publisher (the runner
configures it via the `ros_topic_name` and `ros2_extended_lidar` blueprint
attributes on the spawned sensor), not by the extension `.so`.

Overlay branch `feat/carla-native-nishishinjuku` on `youtalk/autoware_launch`
is created ONLY if a concrete change is forced (e.g. a `traffic_light` module
disable, or a QoS param fix) — not preemptively.
