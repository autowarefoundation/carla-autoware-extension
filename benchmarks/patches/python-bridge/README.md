# python-bridge launch recipe and patch inventory

Two things live here. **Sections 1-6** are the launch-recipe writeup from the Task 13 bring-up: no
Autoware source or launch file is edited by any of it, every fix is a `ros2 launch` command-line
argument choice against the stock `autoware_carla_interface` / `autoware_launch` packages in
`bridge-bench:latest`. **Sections 7 onwards** are Task 10's, and those DO edit source: the two
committed patch files beside this README, the image built from them, and the live bring-up evidence
for cell E. Full Task 13 findings live in `task-13-report.md` (outside this repo, under the plan's
`.superpowers/sdd/` tree).

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

## Patch inventory (Task 10)

Two patch files, both applied by `benchmarks/docker/bridge-bench-patched.Dockerfile` with `patch -p0`
from `/`, both carrying container-absolute paths in their headers. Cells **E** and **E-opt** run the
patched image (`pins.yaml bridge_bench_patched`); cell **E0** runs the unpatched `bridge_bench`,
which is the whole reason the two tags exist. `cells/python-bridge.sh plan` greps the resolved image
for `is_dense=True` and refuses in BOTH directions, so "measured the unpatched bridge and filed it as
E" and "measured the patched bridge and filed it as as-shipped E0" are both inexpressible.

**`0001-lidar-is-dense.patch`** — one line in
`/opt/autoware/lib/python3.10/site-packages/autoware_carla_interface/modules/carla_utils.py`:
`is_dense=False` → `is_dense=True` in `create_cloud`. This is `benchmarks/README.md`'s named,
pre-registered patch-policy exception, and it is also *correct*: the bridge's cloud contains no
invalid points, so `is_dense=false` was a mislabel.

**`0002-sensor-config-harmonized.patch`** — the harmonized kit, as one reviewable diff over three
files: `share/autoware_carla_interface/config/sensor_mapping.yaml`,
`share/autoware_carla_interface/autoware_carla_interface.launch.xml`, and
`share/carla_sensor_kit_launch/launch/pointcloud_preprocessor.launch.py`. It sets LiDAR 16 ch /
288 000 pts/s / `rotation_frequency 10` / range 100 / FOV +15/−15; moves `topic_suffix` to
`/pointcloud_raw_ex` and `crop_box_filter_self`'s hardcoded input with it; drops the six cameras from
the enabled list (M4-only) while leaving their `sensor_mappings` entries in place so the M4 arm
re-enables them by listing them again; disables `multi_camera_combiner`; harmonizes the GNSS
covariance diagonal to the extension's `GnssPosePublisher` values; and raises `frequency_hz` 11 → 20.

`frequency_hz` is the bridge's own publish throttle (`sensor_manager.should_publish`:
`time_diff >= 1 / frequency_hz` in SIM seconds), not a CARLA `sensor_tick` — the bridge sets no
`sensor_tick` at all, so the LiDAR fires once per sim frame and 20 matches the 0.05 s tick. That is
what makes it pacing parity with the baseline rather than a rate change: cell A's top LiDAR is
`rotation_frequency 10` with `sensor_tick 0.05` too (`runner/spawn.py`, "one ~half-rotation cloud per
tick at ~20 Hz"), so both cells emit 20 Hz half-rotation clouds at 288 000 pts/s. Leaving it at the
shipped 11 would have thrown away every other CARLA measurement, publishing 11 Hz clouds that each
cover only 180° of sweep.

## Cell E / E0 run recipes

Both cells run through `benchmarks/run.sh`; `cells/python-bridge.sh` owns the split-launch recipe
(stage 1 = the bridge alone so `carla_map` can be overridden, barrier on the loaded map, stage 2 =
the rest of the stack with `simulator_type:=awsim`). `--dds-profile none` is **not optional** — see
the observer transport matrix below.

```bash
# cell E: patched image, closed-loop arm
bash benchmarks/run.sh E --arm closed-loop --dds-profile none --rpc-port 2100

# cell E: patched image, static arm (the arm the D3 companion bias is measured on)
bash benchmarks/run.sh E --arm static --dds-profile none --rpc-port 2100

# cell E0: AS-SHIPPED image, static arm only (cells.yaml registers no other)
bash benchmarks/run.sh E0 --arm static --dds-profile none --rpc-port 2100
```

`run.sh` resolves the image per cell (`E0` → `bridge_bench.tag`, everything else →
`bridge_bench_patched.tag`) and records it in the manifest; the launcher reads that same string back
rather than re-deriving it, so the image a run used and the image its manifest claims cannot diverge.

## Observer transport matrix (Task 10, measured)

`bench_observer` — the real recorder binary, not the `ros2` CLI — run against a live bridge for 20 s
per row, one fresh container per row, `benchmarks/config/observer_topics/E.yaml` as the topic list.
Rows are `clock.csv` and `observer.csv` data rows after the SIGINT flush.

| rmw      | profile                            | clock rows | observer rows |
| -------- | ---------------------------------- | ---------- | ------------- |
| cyclone  | `docker/cyclonedds.xml` (`lo`)     | **0**      | **0**         |
| cyclone  | DEFAULT (no `CYCLONEDDS_URI`)      | 366        | 365           |
| fastrtps | image default (SHM on)             | 386        | 385           |
| fastrtps | `observer/config/udp_only.xml`     | 385        | 386           |

The `lo`-pinned profile is the one that fails, and it is `run.sh`'s per-invocation DEFAULT for
`--rmw rmw_cyclonedds_cpp`. Cause: this cell's stack is Fast-DDS (the image default) and Fast-DDS
announces no loopback unicast locators, so a Cyclone participant confined to `lo` never matches it.
That is the entire explanation of cell E `run-001`'s header-only `observer.csv` and `clock.csv`, and
it is a property of the harness's default, not of the bridge. `benchmarks/README.md`'s DDS confound
table already registers the E family's observer as "rmw_cyclonedds_cpp, default profile" — the matrix
confirms that row works and the launcher now refuses any other Cyclone profile rather than recording
an empty observer as a measurement.

**The `ros2` CLI is not a usable instrument in this cell.** In the same minute that an rclpy counter
inside the container measured `/clock` at 20.00 Hz, `/sensing/lidar/top/pointcloud_raw_ex` at
19.67 Hz, `/sensing/gnss/pose_with_covariance` at 19.83 Hz and `/sensing/imu/tamagawa/imu_raw` at
19.83 Hz, `ros2 topic hz --no-daemon` reported every one of them SILENT and `ros2 topic info -v
/clock` reported `Publisher count: 0`. Every rate claim about this cell must come from
`bench_observer` or from a purpose-written subscriber; a silent `ros2 topic hz` here means nothing.

## Cell E bring-up gate (Task 10)

### Acceptance (a) and (b): PASS

`0001` works. Measured in-container on the 2026-07-29 bring-up probe, with the full stack up:

```text
  19.802 Hz  /sensing/lidar/top/pointcloud_raw_ex              <- patched bridge, as emitted
   7.981 Hz  /sensing/lidar/concatenated/pointcloud            <- through crop_box_filter_self
  13.072 Hz  /localization/util/downsample/pointcloud          <- NDT's input
  13.050 Hz  /localization/pose_estimator/pose_with_covariance <- NDT, >= 9 Hz
```

`Invalid PointCloud: is_dense is false` does not appear anywhere in the stack log any more (P1
recorded it as the first hop's rejection of every message, with
`/sensing/lidar/top/pointcloud` at 0.00 Hz). Note that acceptance (a) as originally worded names
`/sensing/lidar/top/pointcloud`, which **does not exist in `carla_sensor_kit` at all** — that kit's
chain is `crop_box_filter_self` → `crop_box_filter_mirror` → a `topic_tools` relay onto
`/sensing/lidar/concatenated/pointcloud` (see `benchmarks/README.md`'s sensing-graph confound row).
The rates above are that chain, which is the live downstream for this cell.

### Two non-bridge bring-up failures, root-caused

Neither is a defect in the patches, and neither is a reason to change them.

1. **`pointcloud_container` drops a `load_node` response under start-up load.**
   `results/E/run-003` logged `failed to send response to
   /pointcloud_container/_container/load_node (timeout): client will not receive response` four
   times, and `/localization/util/random_downsample_filter` — the node that publishes
   `/localization/util/downsample/pointcloud`, NDT's only input — was never instantiated, while
   `crop_box_filter_measurement_range` and `voxel_grid_downsample_filter` from the same
   `<load_composable_node>` group were. `ndt_scan_matcher` therefore reported `No InputSource` for
   the full 442 s and localization stayed UNINITIALIZED, with `ekf_localizer` repeating "The node is
   not activated" 207 times — while **perception, fed off the same concatenated cloud, ran
   normally** (`lidar_centerpoint` logged 684 preprocess attempts). A dropped rclcpp/rmw service
   response blocks the rest of its loader group; it is a host-load-sensitive race, it did not
   reproduce on the next bring-up, and `cells/python-bridge.sh` now lists the surviving
   `/localization/util/*` nodes on the timeout path so the next occurrence is named rather than
   reported as "kinematic_state never published".
2. **The launcher's `/api/localization/initialize` retry was based on a refuted premise, and is
   gone.** Autoware's own `autoware_automatic_pose_initializer` calls that API roughly every 2 s for
   as long as localization is UNINITIALIZED (measured: `run-003` over 442 s, and the bring-up probe,
   where `Call align server` repeats at ~2 s intervals until it succeeds). The launcher's extra call
   carried an empty pose array — the same GNSS-initialize request — so it added nothing, and each
   `ros2 service call` stood up a participant against a stack whose composable loads are sensitive
   to exactly that churn.

### The sync-tick stall, re-measured (refines P1 Verdict 1)

P1 recorded "after roughly ten minutes it stops ticking, and its actors vanish". Both halves are
refined by Task 10's measurements, and the correction matters because the campaign's exclusion
criterion 4 rests on it:

- **It is not a timer, and it is not the bridge on its own.** With CARLA 0.9.15 and the bridge alone
  (stage 1, no Autoware stack), the bridge ticked continuously for **14 minutes** of wall clock and
  277 s of sim time, free-running at up to ~1800 frames per 3 s once nothing consumed its output.
  It froze only with the full stack attached, **~70 s of sim time in, in the same second that
  localization first initialized** — after which every node on sim time stopped logging, because a
  frozen `/clock` freezes the whole graph.
- **The actors do NOT vanish.** On the frozen world, a client reports `frame 0`, `actors 0`. One
  external `world.tick()` returned frame 1396 and 27 actors, including `vehicle.toyota.prius` with
  `role_name=ego`, the `sensor.lidar.ray_cast`, the IMU and the GNSS. "The ego and all 9 sensors are
  gone" is a **client-side artifact of querying a frozen synchronous world**, not actor destruction.
- **Where it hangs.** The bridge process stays alive at low CPU with its main thread in
  `futex_do_wait`, i.e. blocked on a Python lock or the GIL — not on a socket and not on a sensor
  queue (`SensorInterface.get_data()` is `block=False` and cannot block). The lock-holding
  candidates are the two callbacks that take `_state_lock` and then touch the ego actor,
  `control_callback` (which starts firing only once the control stack has a pose) and
  `initialpose_callback`. Ticking the world from the harness would unfreeze it and is exactly the
  kind of workaround this campaign forbids: the bridge is the measured ticking authority, so a
  harness tick would make the recorded pacing an artifact of the instrument.
