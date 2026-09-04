# python-bridge launch recipe (Task 13 bring-up)

This is a launch-recipe writeup, not a source diff. No Autoware source or launch file is edited by
anything here — every fix below is a `ros2 launch` command-line argument choice, made against the
stock `autoware_carla_interface` / `autoware_launch` packages in `bridge-bench:latest`. It exists as a
reviewable artifact for the map-correctness bug found while smoke-testing the stock Python-bridge
approach (Task 13); full findings, evidence, and the still-open drive-gate result live in
`task-13-report.md` (outside this repo, under the plan's `.superpowers/sdd/` tree).

## The stock candidate command — WRONG

```bash
ros2 launch autoware_launch e2e_simulator.launch.xml \
  map_path:=/autoware_map/town10 vehicle_model:=sample_vehicle \
  sensor_model:=carla_sensor_kit simulator_type:=carla rviz:=false
```

This command has two independent bugs.

### Bug 1 — silently drives Town01 instead of Town10HD_Opt

`autoware_carla_interface.launch.xml` declares `carla_map` with `default="Town01"`.
`e2e_simulator.launch.xml`'s `<group ... if="simulator_type == carla">` includes it with
`<include file="$(find-pkg-share autoware_carla_interface)/autoware_carla_interface.launch.xml"/>` —
**zero arguments passed through**. There is no top-level `carla_map` arg on `e2e_simulator.launch.xml`
to forward it with. `carla_autoware.py:82` then unconditionally calls
`client.load_world(self.carla_map)` on startup. The net effect: `map_path:=/autoware_map/town10` is
silently discarded, and the simulator ends up running Town01 while the rest of the launch line makes it
look like Town10HD_Opt is in use — no warning, no error.

Live evidence (this pass, `carla.Client` queried immediately after running the stock command above):

```text
$ python3 -c "import carla; c=carla.Client('localhost',2000); c.set_timeout(10.0); print(c.get_world().get_map().name)"
current map: Carla/Maps/Town01
```

### Bug 2 — crashes on a CPU-only image before perception even starts

`tier4_perception_launch/launch/obstacle_segmentation/ground_segmentation/ground_segmentation.launch.py`
unconditionally declares a launch argument whose _default value_ resolves
`FindPackageShare("autoware_ground_segmentation_cuda")`, regardless of whether the CUDA node is ever
selected (`use_cuda_ground_segmentation` defaults to `false`). `DeclareLaunchArgument.execute()`
resolves that default eagerly, at declare-time — so on a CPU-only image where
`autoware_ground_segmentation_cuda` isn't ament-registered, the whole launch tree aborts immediately:

```text
[ERROR] [launch]: Caught exception in launch (see debug for traceback): "package 'autoware_ground_segmentation_cuda' not found, searching: ['/opt/autoware', '/opt/ros/humble']"
```

Workaround (CPU-only base image): `perception:=false` on `e2e_simulator.launch.xml` skips the whole
perception module and avoids the crash — but this has a downstream consequence (a structural
`autonomous`-mode-availability conflict, superseded below by the pin update, see "Drive-gate
result").

**Update:** this bug is now avoided at the root, not worked around, by pinning `bridge-bench` to the
CUDA-enabled Autoware base image instead of switching `perception:=false`. See "Pin update" below.

## Pin update — CUDA-enabled Autoware base required

`benchmarks/pins.yaml`'s `autoware_universe_devel.digest` now points at
`ghcr.io/autowarefoundation/autoware:universe-devel-cuda`
(`sha256:5c22369a312f1cd8a03fb65b30c1ab542919c2c7a2cbd18e799956daef3ae8ee`, the multi-arch manifest-list
digest, same digest kind as the previous pin) instead of the CPU-only `universe-devel` variant. This is
an environment/pin change only — `benchmarks/docker/bridge-bench.Dockerfile` needed no edit, since it
already parameterizes the base image via `ARG BASE`.

With the CUDA base, `autoware_ground_segmentation_cuda` actually resolves:

```text
$ docker run --rm bridge-bench:latest bash -lc \
  "source /opt/autoware/setup.bash 2>/dev/null || source /opt/ros/humble/setup.bash; \
   ros2 pkg prefix autoware_ground_segmentation_cuda"
/opt/autoware
```

...which means `perception:=false` is **no longer required** to avoid Bug 2 — the corrected invocation
below leaves perception at its default (on) and drops the flag. Note this pin makes the image
GPU-dependent: `docker run` needs `--gpus all` (nvidia-container-toolkit) from this point on.

## The corrected invocation

### Container prerequisites

Both of the following `docker run` flags are load-bearing; the stack cannot start without them.

```bash
docker run --rm -it --gpus all --net=host --ipc=host \
  -v "$HOME/autoware_map:/autoware_map:ro" \
  -v "$HOME/autoware_data:/root/autoware_data" \
  bridge-bench:latest bash
```

- `--gpus all` (nvidia-container-toolkit) — required by the CUDA-pinned base, see "Pin update" above.
- `-v "$HOME/autoware_data:/root/autoware_data"` — the perception ML model/weights directory. It is
  **not** baked into any upstream Autoware image; it is fetched separately on the host via
  `ansible-playbook autoware.dev_env.download_artifacts` (~3.8 GB, 228 files). Without this mount the
  launch tree aborts on the missing
  `lidar_centerpoint/centerpoint_tiny_ml_package.param.yaml`. Mounting the host copy resolves the
  blocker recorded in the previous revision of this file.

```bash
# stage 1 — bridge only, launched separately so its own carla_map default can be overridden
ros2 launch autoware_carla_interface autoware_carla_interface.launch.xml \
  carla_map:=Town10HD_Opt host:=localhost port:=2000 sensor_kit_name:=carla_sensor_kit_description

# stage 2 — rest of the stack; simulator_type:=awsim so it does not auto-include a second,
# conflicting bridge instance with the wrong default map. perception left at its default (ON) —
# this requires the CUDA-pinned image and --gpus all on the container.
ros2 launch autoware_launch e2e_simulator.launch.xml \
  map_path:=/autoware_map/town10 vehicle_model:=sample_vehicle \
  sensor_model:=carla_sensor_kit simulator_type:=awsim \
  sensing:=true rviz:=false
```

`sensing:=true` is load-bearing: an earlier attempt at this recipe used `sensing:=false` (reasoning
that the bridge already publishes raw sensor topics directly), which broke the
GNSS -> EKF -> `/localization/kinematic_state` chain (EKF never activated, GNSS topic looked silent).
With `sensing:=true`, `/sensing/gnss/pose_with_covariance` publishes at ~20 Hz, EKF activates, and
`/localization/kinematic_state` publishes real fused pose at ~16 Hz — confirmed live, see
`task-13-report.md`.

Live evidence that the corrected recipe stays on the right map (this pass):

```text
$ python3 -c "import carla; c=carla.Client('localhost',2000); c.set_timeout(10.0); print(c.get_world().get_map().name)"
current map: Carla/Maps/Town10HD_Opt
```

## Drive-gate result — NOT PASSED, and the LiDAR gap is structural

With both container prerequisites above satisfied, the launch tree no longer aborts: the bridge spawns
9 sensors on `Carla/Maps/Town10HD_Opt`, the full CUDA perception stack loads, and all stack processes
start. The `lidar_centerpoint` model-data blocker recorded in earlier revisions is **resolved** —
mounting `$HOME/autoware_data` is sufficient, and nothing under it is written to (verified
byte-identical by `md5sum` before/after).

The drive gate nevertheless **does not pass**, and the cause is now root-caused to two independent
structural defects, confirmed by a controlled re-run on an idle host with cleared DDS shared memory.

### The failing link: Autoware rejects the bridge's pointcloud outright

The first stage of the sensing preprocessing chain refuses every message the bridge publishes:

```text
[sensing.lidar.crop_box_filter_self]: Invalid PointCloud: is_dense is false.
                                      The point cloud should be organized (dense)
```

The CARLA Python bridge emits a `sensor_msgs/PointCloud2` with `is_dense = false`; Autoware's
`pointcloud_preprocessor` requires a dense/organized cloud. This is a **data-contract mismatch**, not
a tuning or resource problem, and it severs the chain at its very first hop. Measured on the idle
host (25 s window):

```text
  8.59 Hz  n=215  /sensing/lidar/top/pointcloud_before_sync   <- bridge output, healthy
  0.00 Hz  n=  0  /sensing/lidar/top/pointcloud               <- nothing survives crop_box_filter
  0.04 Hz  n=  1  /sensing/lidar/concatenated/pointcloud
  0.04 Hz  n=  1  /localization/util/downsample/pointcloud
  0.04 Hz  n=  1  /localization/pose_estimator/pose_with_covariance   <- NDT effectively dead
```

Everything downstream follows deterministically, and all of it still reproduces on the idle host:

```text
[localization.pose_estimator.ndt_scan_matcher]: No InputSource. Please check the input lidar topic
[system.service_log_checker]: /api/localization/initialize: status code 4 'align server failed.'
[system.topic_state_monitor_pointcloud_map]: /map/pointcloud_map has not received.
                                             Set ERROR in diagnostics.
```

### Second defect: the bridge stalls CARLA's synchronous tick and drops its actors

The bridge drives CARLA in **synchronous mode** (`fixed_delta_seconds = 0.05`), making it the sole
ticking authority. After roughly ten minutes it stops ticking, and its actors vanish:

```text
$ python3 -c "...carla.Client('localhost',2000)..."
sync_mode= True fixed_dt= 0.05
frames advanced: 0    sim seconds advanced: 0.0     # over 3 s of wall clock
actors: 0             vehicles: 0                   # ego and all 9 sensors gone
```

The bridge process is still alive and burning ~30 % CPU at this point, and logs no error. Because
every Autoware node runs with `use_sim_time:=True`, a frozen sim clock freezes the **entire** ROS
graph: topics go to 0 Hz and AD API service calls time out. This is what previously looked like "DDS
wedged" — it is a symptom, not the cause.

### Drive-gate evidence

Ego never moved. `/localization/kinematic_state`, sampled via rclpy:

```text
SAMPLES n=105 span=6.65s
FIRST t=149.950 x=-28.3485 y=-69.7247
LAST  t=156.600 x=-28.3602 y=-69.7223
NET_DISPLACEMENT 0.012 PATH_LEN 0.014
```

`/api/routing/set_route_points` and `/api/operation_mode/change_to_autonomous` were both discovered
but timed out, because the sim clock had frozen by the time they were called. The goal pose itself is
sound and was validated independently: with `projector_type: Local` the nearest `subtype=road`
centerline point to ego is 0.26 m away at yaw -0.0013 rad, confirming OSM `local_x`/`local_y` are
map-frame; the chosen goal was lanelet 2924 at `x=71.513 y=-69.840 yaw=-0.0013`, 99.9 m directly
ahead in the same lane direction.

### What host load and `/dev/shm` actually affect

Re-running on an idle host (load average 1.8 vs 23-44) with `/dev/shm` stale `fastrtps_*` segments
cut from 1177 to 91 changed exactly one thing, and it is worth knowing:

- **Improved:** localization stability. `/localization/kinematic_state` held a steady 14.07 Hz
  (GNSS/EKF-driven) instead of dropping out within ~2 minutes.
- **Unchanged:** every LiDAR-chain symptom above. `/sensing/lidar/top/pointcloud` still received
  exactly 0 messages.

So host load is a real operational prerequisite for stable localization, but it is **not** the cause
of the LiDAR gap. Note also that shared-memory segments climb back on their own (91 -> 383 within ten
minutes) purely from running this stack — SHM pressure is generated by the stack itself, and the
graph went silent well below the earlier 1177-file mark, which further exonerates SHM as a cause.

### Verdict

The stock Python bridge cannot drive Autoware on this configuration without source-level fixes:
`is_dense` on the published pointcloud, and the synchronous-tick/actor-lifetime stall. Both are
bridge-side defects, independent of host resources.
