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
the rest of the stack with `simulator_type:=awsim`).

```bash
# cell E: patched image, closed-loop arm
bash benchmarks/run.sh E --arm closed-loop --rpc-port 2100

# cell E: patched image, static arm (the arm the D3 companion bias is measured on)
bash benchmarks/run.sh E --arm static --rpc-port 2100

# cell E0: AS-SHIPPED image, static arm only (cells.yaml registers no other)
bash benchmarks/run.sh E0 --arm static --rpc-port 2100
```

No `--dds-profile` is passed: `run.sh` resolves it to `none` for this family once the approach is
known, which is the configuration `benchmarks/README.md`'s DDS confound table registers for it. An
explicit `--dds-profile <path>` still wins, and the launcher then refuses the `lo`-pinned profile
outright — the matrix below is why.

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

### What these runs did and did NOT retain, and where their provenance is broken

Two limitations on this evidence, disclosed because a reader would otherwise assume neither.

**Provenance: `run-001` to `run-004` record a `harness_git_sha` that cannot be true.** All four claim
`d0612c4`, a commit in which `cells/python-bridge.sh` contains no `save_stage_logs` function at all —
yet `run-003` and `run-004` contain the `bridge-stage1.log` / `bridge-stage2.log` files that only that
function writes. All four also claim `patches_git_sha: ec998b4`, which **predates the patch files**
their `bridge-bench-patched` image was built from. The explanation is that they ran from an
uncommitted working tree, so `git rev-parse HEAD` named a commit that did not contain the code being
executed. **These four records cannot be repaired truthfully — no commit exists that contains what
ran — so the tie-back guarantee in `benchmarks/README.md`'s Pre-registration section does not hold for
them.** They are bring-up iterations, all excluded, and none carries a measurement. `run-005` onward
ran from clean, committed trees and their shas are exact. To stop this recurring,
`scripts/write_manifest.py` now appends `-dirty` to both sha fields whenever tracked files differ from
HEAD (`benchmarks/results/` excluded, since the run writes there as it runs), so a manifest can no
longer silently assert a tie-back it does not have.

**One provenance remap, disclosed.** Task 10's own history was later split so the pre-registration
amendments sat in dedicated commits, per `benchmarks/README.md`'s amendment rule. That rewrote every
commit sha from the patch commit onwards, leaving `run-005`..`run-008` recording
`harness_git_sha` / `patches_git_sha` / `harness:<commit>` values that pointed at commits which are now
**unreachable** — they still exist as objects, but nothing in the repository references them, so they
are unresolvable by name and collectable. Those four records were remapped. The remap is
content-preserving and was verified before it was applied: the rewritten tip's tree hash is
**byte-identical** to the pre-rewrite tip's, so each new sha names exactly the code the old one named.
The mapping was `845cd55→b81200d`, `a35c9b9→fac5cb7`, `cdbc129→7425084`, `69344a1→4557e5c`. Every sha
in every E-family manifest now resolves in this repository. `run-001`..`run-004` were left untouched,
because their problem is the one above and no remap can fix it.

**Retained artifacts.** `run-008` carries `bridge-stage1.log` and `bridge-stage2.log`; the gate run
`run-007` does **not**, because teardown's stage-log copy landed only after it (`4557e5c`), so the
gate's own diag-graph dump is gone and the (c) diagnosis above is read from the retry. The observer
transport matrix and the bring-up probe wrote into a scratch directory outside the repository and
retained **no committed artifacts** — their numbers are reported here and are not independently
re-derivable from this tree. Every number attributed to `run-006`, `run-007` and `run-008` IS
re-derivable from the committed CSVs.

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

The stall did NOT occur on either gate run: `run-007`'s clock.csv holds 1683 rows at 19.93 Hz with a
largest gap of 0.060 s, `run-008`'s 1383 rows at 19.92 Hz with 0.077 s. It is intermittent, and the
launcher's `wait_for_tick` check now names it when it happens.

### Acceptance (c): FAIL. Cell E degrades to static-arm only — PROVISIONALLY

The gate is `results/E/run-007` (`bash benchmarks/run.sh E --arm closed-loop --rpc-port 2100`, the
first closed-loop run made after (a) and (b) had both passed through the real observer). It was
excluded `gate:arm-failed`. The findings' method was then applied ONCE, as `results/E/run-008`, which
failed at **the same step, for the same reported reason, and in a measurably different state** — see
the side-by-side table below, which is why "failed identically" would overstate it.

**E therefore degrades to static-arm only, per the spec's pre-committed risk clause: "the E2E-latency
half of C2 is dropped."** No third attempt was made.

**That degradation is PROVISIONAL, not final, and the condition that settles it is named.** The
failure is specifically that the AD API's `change_to_autonomous` refused, and **that engage path has
never been verified live for ANY cell** — the only arming path this repository has driven to a live
gate publishes `/autoware/engage` (`scripts/e2e/gate_g2_closed_loop.sh`, with `arm_closed_loop.sh`
turning MRM off), a divergence `run.sh` already records as unresolved. Task 13 (cell B) and Task 15
(cell C) verify the AD-API path live. **If either of them needs the `/autoware/engage` fallback, cell
E's (c) runs are reclassified `harness:<commit>` and E is re-gated**; only if the AD-API path is shown
to work on a cell that demonstrably drives does this FAIL become a property of the bridge.

One correction to the retry's framing, since it was reported as "idle host": `run-008` started at
1-min **loadavg 2.21** against the gate's **1.37**, so the retry was not on a quieter host than the
gate. Nor did it clear more shared memory — its own manifest records `shm_root_cleared: 0` and
`shm_root_remaining: 0`, because `run-007`'s preflight had already cleared 300 segments and none had
regrown; the 300 belongs to the gate, not to the retry. What the retry did apply was a
verified-empty `/dev/shm` and fresh processes. Both loadavg values are far below the ≥ 8 preflight
bar, so neither run is excludable on host load — the point of recording the difference is that "idle
host" was not the variable the retry actually changed.

Both runs reached a live, localizing stack, but they were **not** equally healthy and an earlier
revision of this file wrongly said they were. Side by side:

| topic                                               | run-007 (gate)     | run-008 (retry)    |
| --------------------------------------------------- | ------------------ | ------------------ |
| `/sensing/lidar/top/pointcloud_raw_ex`              | 19.86 Hz           | 19.87 Hz           |
| `/localization/pose_estimator/pose_with_covariance` | 9.79 Hz            | 12.87 Hz           |
| `/localization/kinematic_state`                     | 19.94 Hz           | 19.88 Hz           |
| `/control/command/control_cmd`                      | **1.30 Hz**        | **8.52 Hz**        |
| `/clock` (largest gap)                              | 19.93 Hz (0.060 s) | 19.92 Hz (0.077 s) |

`run-007`'s gated control output at 1.30 Hz is **indistinguishable from a static-arm run** — the
vehicle command gate was emitting little more than its periodic emergency command — while `run-008`'s
8.52 Hz shows the gate cycling far more actively. The two runs therefore failed at the same step but
not in the same state, and any account that treats them as one repeated observation is overstating the
evidence. Neither run moved: ground-truth net displacement **0.000 m** in both, goal closest approach
250.859 m, which is the spawn-to-goal distance. The route planned in both (no "Planning failed", no
"route is empty") and a trajectory was produced. Ego never moved because it was never engaged.

`arm_and_goal.py`'s `change_to_autonomous` was refused for 60 s with "The target mode is not
available. Please check the diagnostics." The diag graph, from the dump immediately after the last
attempt (`bridge-stage2.log`, saved by teardown), names exactly three things — perception, control,
vehicle, system and map are all OK by then:

```text
- /autoware/modes/autonomous ERROR
    - /autoware/localization ERROR
        - /autoware/localization/state STALE
        - /autoware/localization/topic_rate_check/transform ERROR
    - /autoware/planning ERROR
        - /autoware/planning/topic_rate_check/trajectory ERROR
    - /adapi/mrm_request/delegate STALE
```

So the proximate refusal is a **`/tf` map→base_link rate check**
(`system.topic_state_monitor_transform_map_to_base_link`: "/tf topic is timeout" and "/tf topic rate
has dropped to the error level"), with the trajectory rate failing downstream of it
(`autoware_operation_mode_transition_manager`: "Subscribed trajectory is timed out"). The monitor's
own thresholds, from `autoware_launch/config/system/component_state_monitor/topics.yaml`, are
`warn_rate: 5.0`, `error_rate: 1.0`, `timeout: 1.0` — so it is asserting that the map→base_link
transform updated at **under 1 Hz**, or not at all for a second.

#### The cause is NOT isolated. These are the live hypotheses

An earlier revision of this file asserted a single cause — that `ekf_localizer` was being fed two
mutually inconsistent pose sources, the bridge's GNSS pose and NDT's. **That account is retracted. It
is refuted by the launch tree, and its corroboration was too thin to carry it.**

Refuted, read out of the running image:

- `tier4_localization_launch/.../pose_twist_fusion_filter.launch.xml` gives `ekf_localizer`
  `input_pose_with_cov_name = /localization/pose_estimator/pose_with_covariance` — and with
  `use_autoware_pose_covariance_modifier` at its default `false`, `ndt_scan_matcher` publishes
  *directly* to that topic. **`/sensing/gnss/pose_with_covariance` is not an `ekf_localizer` pose
  input at all.**
- Its only two consumers in this tree are `ndt_scan_matcher`'s `input_regularization_pose_topic` —
  and `regularization.enable` is **`false`** in the `autoware_launch` NDT param file — and
  `pose_initializer`'s `sub_gnss_pose_cov`, i.e. the INITIAL pose only.
- So the Mahalanobis rejections compare NDT's pose against the EKF's own prediction, not GNSS against
  NDT. The sentence "the filter is being handed two pose sources that disagree" was simply wrong.

Too thin to carry it, even had it not been refuted: 4 Mahalanobis lines and 15 queue warnings across
roughly 2400 recorded messages.

And the contrary evidence is strong. In the exact window containing "/tf topic is timeout"
(timestamps `…845.227` and `…848.230`), the observer recorded `/localization/kinematic_state` —
published by the **same node that broadcasts that TF** — at **19.84 Hz with a largest gap of
0.062 s**. At `…847.982`, in-container `behavior_velocity_planner` reported the map↔base_link lookup
failing by **50 ms of extrapolation**, which is positive proof the transform was flowing. A monitor
claiming < 1 Hz against 19.84 Hz of output from the same node is not yet an explained observation.

Crucially, this cell has a **documented history of consumer-side false silence** (see "Observer
transport matrix" above: `ros2 topic hz` reported SILENT on four topics an rclpy counter measured at
19.7–20.0 Hz in the same minute, and a stale `ros2cli` daemon reported a publishing topic as absent
for 420 s). Any diagnosis here must weigh that class of explanation, and the earlier revision did not.

The live hypotheses, with what would discriminate them:

| # | Hypothesis | Discriminator |
| - | ---------- | ------------- |
| H1 | The map→base_link TF genuinely updates below 1 Hz — the TF broadcast is decoupled from the odometry publish, so 19.84 Hz on `/localization/kinematic_state` says nothing about it. | Measure the **map→base_link pair specifically**, which needs a frame-filtering subscriber — see "What will and will not discriminate H1" below. Adding `/tf` to the observer topic list does NOT do it. |
| H2 | The monitor's own measurement is unreliable here, in the same class as the false silence above — a property of the consumer, not of the DUT. | Run the identical monitor against a cell known to drive (A or C). If it also errors there while that cell drives, the monitor is not measuring what the mode check assumes. |
| H3 | A diagnostics-delivery or sim-time-scheduling problem: three sibling entries in the same dump (`/autoware/localization/state`, `/adapi/mrm_request/delegate`, and earlier the whole graph) are STALE, which is a diagnostics symptom rather than a localization symptom. | Record `/diagnostics` and `/diagnostics_graph` rates alongside `/tf`; a graph that is itself late explains STALE without any localization defect. |

H1 and H2 are not mutually exclusive with each other, and none of the three is established. **The
honest state is: (c) fails at the AD-API mode-availability check on a `/tf` rate assertion whose
truth is unverified.**

##### What will and will not discriminate H1

An earlier revision of this file said the H1 test was "add `/tf` to
`config/observer_topics/E.yaml`… the cheapest and most decisive test", framed as "a topic-list change,
not a source change". **That was wrong on both counts and is withdrawn.** It cannot answer the
question, for two independent reasons in `observer/src/bench_observer.cpp`:

- **The `generic` kind mis-parses `TFMessage`.** `stamp_from_cdr` assumes a leading
  `std_msgs/Header`: it reads `stamp.sec` at CDR byte 4 and `stamp.nanosec` at byte 8.
  `tf2_msgs/msg/TFMessage` is a *sequence* of `TransformStamped`, so byte 4 is the sequence length and
  byte 8 is the first transform's `stamp.sec`. The rows would still carry valid *arrival* stamps, so
  they would look plausible, while `header_stamp_ns` would be nonsense — worse than an obvious failure.
- **There is no frame filter.** A `generic` subscription records every message on `/tf` from every
  broadcaster. The quantity in question is one pair, map→base_link, and `/tf` also carries the
  vehicle's own high-rate chain. A healthy aggregate rate would therefore make H1 look **refuted when
  it is untested** — exactly backwards at the point the re-gate exists to settle.

What would actually discriminate it, with the cost stated plainly rather than minimised:

- **As a recorded, re-derivable metric: an observer source change.** A typed `tf` kind subscribing
  `tf2_msgs/msg/TFMessage` and filtering `header.frame_id == "map" && child_frame_id == "base_link"`.
  That is C++ in `bench_observer.cpp`, a rebuild of `bench-observer:universe-devel`, and a new
  `local_digest` in `pins.yaml` — **not** a topic-list line. **Flagged for R3**, which is already
  adding a typed observer kind for the NDT pose topic; the two changes are the same shape and should
  land together rather than being built twice.
- **As a one-off answer at the re-gate, without touching the observer:** either a purpose-written
  typed subscriber in the container that filters the frame pair and logs its rate into the run
  directory (the same instrument class that already measured 20.00 Hz on `/clock` in this cell when
  the `ros2` CLI reported silence), or `ros2 run tf2_ros tf2_monitor map base_link`, which is present
  in the image and reports the average rate and delay for exactly that chain. Both are bring-up
  artifacts rather than observer metrics, so they answer H1 without feeding M1/M2.

The honest summary: H1's discriminator is **not** free. Either R3's typed kind carries it, or the
re-gate runs a separate probe and records the result as evidence beside the run.

#### On the granted second patch exception

The owner has granted a second patch-policy exception (registered in `benchmarks/README.md`,
**registered only, not applied**). It was requested on the retracted hypothesis above, and the
refutation matters for how it is spent: because `/sensing/gnss/pose_with_covariance` is not an
`ekf_localizer` pose input and NDT regularization is disabled, **correcting the GNSS pose frame cannot
affect this `/tf` rate failure through the filter.** Its reachable effect is on the INITIAL pose that
`pose_initializer` seeds. So the patch should be written and applied at E's re-gate, against a cause
that has actually been isolated — not now, on this one.

### E static localization bias (the D3 companion measurement)

Measured on `results/E/run-006` (static arm, ego stationary, 1179 paired samples after a 5 s warm-up
discard, joined with the analysis package's own nearest-stamp join at its own 25 ms tolerance):

| quantity                            | value                      |
| ----------------------------------- | -------------------------- |
| signed mean dx (localization − GT)  | **−1.4045 m** (sd 0.0049)  |
| signed mean dy (localization − GT)  | **+0.0731 m** (sd 0.0004)  |
| \|error\| p50 / p95 / max           | 1.4061 / 1.4149 / 1.4198 m |
| ground-truth motion over the window | 0.000 m                    |

**Ruling: the y bias is ≈ 0, not ≈ +0.48 m, so cell E keeps the STOCK pcd bundle.** The
bundle-internal offset that A and B carry does not reproduce on 0.9.15: +0.0731 m is 15 % of the
+0.48 m branch point, and it is not itself a frame artifact (at the spawn heading of 0.32°, a 1.4 m
longitudinal offset contributes only 0.008 m to y).

Two caveats belong beside that ruling, and both are open items rather than results:

1. **The dx term is a frame convention, not a map error — and the chain is now read out, not
   inferred.** An earlier revision guessed at two candidate constants (1.345 and 1.395 m) without
   reading the transform chain. Read from the running image, it is a single declared constant and the
   geometry is self-consistent:

   - `carla_sensor_kit_description/config/sensor_kit_calibration.yaml`'s own header states the
     convention: "base_link at rear axle center on ground … Conversion from CARLA vehicle origin
     ('car center') to base_link: `x_base = x_car_center + 1.425` (WB=2.850 m)", and every sensor x
     in that file carries the conversion in its comment — e.g.
     `velodyne_top_base_link: x: 1.035 # -0.390 + 1.425`.
   - `sensors_calibration.yaml` puts `sensor_kit_base_link` at all-zero relative to `base_link`, so
     the kit frame IS `base_link`.
   - The bridge converts BACK when it spawns: `sensor_kit_loader.py:585` calls
     `CoordinateTransformer.carla_base_link_to_vehicle_center_location(...)`, which is
     `x_vehicle_center = x - wheelbase / 2.0` with `DEFAULT_WHEELBASE = 2.850`, i.e. **−1.425 m**. So
     the CARLA LiDAR is attached at car-centre −0.390 m, exactly the native value in the kit comment.

   The chain is therefore consistent: the sensor is physically where the kit intends relative to the
   true rear axle, NDT recovers `base_link` at the rear axle, and `collect_gt.py` records
   `ego_actor.get_transform()` — the CARLA actor origin at the car centre. Predicted
   dx = −1.425·cos(yaw) ≈ −1.425 m; **measured −1.4045 m, within 0.021 m.** The residual is the
   `vehicle.toyota.prius` pivot's actual placement versus mid-wheelbase, which no static read settles
   and which would need a live `bounding_box.location` query.

   Two consequences, both open items rather than results:

   - **The localization is not biased in x at all.** dx is entirely a ground-truth convention offset.
     It sits in the M5 `pose_error` of **every** cell that uses `collect_gt`, not just E, and nothing
     in `benchmarks/README.md` registered it until this task's confound row. Task 16 owes either the
     correction (offset GT to `base_link`) or the confound row's arithmetic.
   - **The bridge's `DEFAULT_WHEELBASE = 2.850` disagrees with `sample_vehicle`'s `wheel_base: 2.79`**
     (`front_overhang` 1.0, `rear_overhang` 1.1). The bridge places every sensor using 1.425 m while
     Autoware's TF chain is built for a 1.395 m vehicle, so each E-family sensor sits **0.03 m**
     further forward than the TF says. That is a real, previously unrecorded harmonization defect in
     the E family's sensor placement; it is small next to the 1.4 m convention offset but it is not
     zero, and it is now a confound row.
2. **This number is `/localization/kinematic_state`, not the NDT pose, because the NDT pose has no
   recorded x/y.** `cells.yaml` binds `ndt_topic` to
   `/localization/pose_estimator/pose_with_covariance`, and `bench_observer` only writes x/y for
   `odometry`-kind entries, whose subscription type is `nav_msgs/msg/Odometry` — a
   `PoseWithCovarianceStamped` cannot be recorded that way. So `evaluate_quality`'s `ndt_xy` argument
   is not satisfiable from the CSV contract as it stands, for any cell. An earlier revision added that
   `kinematic_state` "cannot cleanly isolate a pcd-internal offset" because the bridge's GNSS pose is
   one of the EKF's inputs — **that reason is withdrawn, for the same reason the (c) mechanism above
   was withdrawn**: `ekf_localizer`'s only pose input in this tree is the NDT topic, so
   `kinematic_state` is NDT-derived and carries no ground-truth-derived pose at all. It is an
   EKF-smoothed NDT estimate rather than the raw NDT pose, which is the only remaining reason to want
   the NDT topic recorded directly. The y ruling stands unchanged and is, if anything, better founded
   than that caveat suggested; recording the NDT pose is still a pre-P3 gap for Task 16.
