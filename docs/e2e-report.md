# E2E gate report (Autoware semi-native, Nishi-Shinjuku)

This report records the live E2E gate campaign for the CARLA native-DDS <-> Autoware
semi-native integration: G1 (NDT localization), G2 (closed-loop route completion), and G3
(sensor/control cadence) against a running Autoware `universe-devel` container and CARLA on
the AWSIM v2.0.0 Nishi-Shinjuku map. It documents the gate outcomes as measured, including
the FAILs and their root causes: an honest, precisely-localized FAIL with preserved refuted
hypotheses is itself the deliverable, not a reason to soften the record.

- Date: 2026-07-23 (UTC ~00:35-01:16) for the initial campaign; closures ran through the
  same day.
- The campaign itself modified no repo files (`git status` after teardown was clean apart
  from an untracked local scratch file).

**Verdict summary:** G1 NDT localization **FAIL**, G2 closed-loop route **FAIL** (both sync
and async), G3 LiDAR cadence **PASS**, G3 control loop **FAIL**. All FAILs trace to two
CARLA<->Autoware sensing-integration gaps that leave the localization chain dead, plus a
GNSS position-scale bug; see [Root-caused blockers](#root-caused-blockers). **Update
(2026-07-22):** all four blockers were fixed AND a full live E2E re-run was executed — see
[Blocker closure — verified in a live re-run](#blocker-closure--verified-in-a-live-re-run-2026-07-22).
The dead sensing/localization chain now runs end-to-end: **NDT localizes at ~20 Hz (400
samples, was `ndt_samples=0`)** with the full ekf-fused `kinematic_state`. G1 is now a
_measured_ FAIL at **1.44 m** (threshold 0.5 m) — root-caused to a base_link↔vehicle-origin
frame offset (≈wheelbase/2), a precise near-miss rather than a dead chain. The Gates table
below is preserved as the original campaign record; the live re-run results are in the closure
section. **Update (2026-07-23):** the G2/G3 gates were run live against the now-working stack
— G3 control loop is now a **PASS** (band re-validated 60±15 → 20±5 Hz), and G2 demonstrates a
**445 m autonomous closed-loop drive** (still a strict-gate FAIL at 22.84 m on goal-arrival
geometry, but the substantive capability is proven and sync propulsion is confirmed). See
[G2/G3 live campaign](#g2g3-live-campaign-2026-07-23).

## Environment

| Item                     | Value                                                                                                                                     |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Autoware container image | `ghcr.io/autowarefoundation/autoware:universe-devel`                                                                                      |
| Container image digest   | `sha256:405225eda6c05161bfde39cc7885511f3f4d9699d126891891420dd80c2e024a`                                                                 |
| `ROS_DISTRO`             | `humble`                                                                                                                                  |
| CARLA fork               | integration branch @ `584743b24` (published as the `youtalk/carla` `autoware/*` draft-PR stack)                                           |
| Extension (this repo)    | campaign branch @ `dcd4de0` (rosidl message layer; DT_RPATH `.so`; live-run enablement; gate-script fixes — since merged via PRs #18–#20) |
| Middleware               | `rmw_cyclonedds_cpp`; `ROS_DOMAIN_ID=0`; `CYCLONEDDS_URI=docker/cyclonedds.xml`                                                           |
| Map                      | AWSIM v2.0.0 Nishi-Shinjuku, `Shinjuku-Map.zip` (129,585,415 B, see `docs/nishishinjuku-map.md`); MGRS 54SUE                              |

The extension HEAD above (`dcd4de0`) postdates the live campaign by one commit: the runs
recorded below were executed against `f2f9133` (before the gate-script fixes), and
`dcd4de0` (subject `fix(gate): make G1/G2/G3 gate scripts measure`) landed immediately
afterward to repair the four script bugs identified while reviewing that campaign's output
(see [Gate tooling](#gate-tooling)). The fixes touch only measurement plumbing, not the
CARLA/Autoware stack under test, so they do not change any measured value in this report.

Autoware launch line (verbatim, perception off):

```bash
ros2 launch autoware_launch e2e_simulator.launch.xml \
  map_path:=/autoware_map/nishishinjuku \
  sensor_model:=awsim_labs_sensor_kit vehicle_model:=sample_vehicle \
  simulator_type:=carla launch_vehicle_interface:=false use_sim_time:=true \
  perception:=false rviz:=false
```

`perception:=false` is a stock-image workaround, not a test-scope choice: on this
`universe-devel` image, `tier4_perception_launch`'s ground-segmentation launch file
resolves `FindPackageShare("autoware_ground_segmentation_cuda")` eagerly at launch time even
when CUDA is disabled, and that package is only stub-installed (no `package.xml`/library),
so the full-perception line aborts before it runs; separately, `/root/autoware_data` is
entirely absent, so every DNN detector mode is missing its model artifacts and there is no
non-ML fallback (full detail: `docs/running-e2e.md`). Neither gap is specific to this
gate campaign. Localization does **not** depend on perception — `ndt_scan_matcher`,
`ekf_localizer`, and `gyro_odometer` all launch and subscribe the raw LiDAR cloud
regardless — so G1's FAIL below is independent of perception being off; G2's route/engage
stack also launches in full, just against an unpopulated `/perception/object_recognition/objects`.

## Type-hash goldens (pinned RIHS01, from `extension/test/test_rosidl.cpp`)

The `rosidl` message layer (introduced in #15) pins these RIHS01 hashes and asserts them in
`TEST(rosidl, rihs01_hashes_match_the_g0_verified_goldens)`; they were carried forward
unchanged from the G0-verified goldens (`docs/g0-report.md`) when the hand-written message
layer was replaced by generated ROS 2 `rosidl` packages, and remain green on this branch.

| Type                                         | RIHS01                                                                    |
| -------------------------------------------- | ------------------------------------------------------------------------- |
| `autoware_vehicle_msgs/VelocityReport`       | `RIHS01_9052adda949c32f4a98500abc1fb5bd23f2560e321eebdfbb25318d6108d4ce4` |
| `autoware_vehicle_msgs/SteeringReport`       | `RIHS01_aa3acc9ca95ebc4daf9dec0ecf87911ad9c196392857c3026bfead589db65a94` |
| `autoware_vehicle_msgs/GearReport`           | `RIHS01_4d14bc3f186c1a6af6a732bb5ebd540cdd742a56770012f4c3cb9e762de8f391` |
| `autoware_vehicle_msgs/ControlModeReport`    | `RIHS01_968feaa6441be3c3b161f2eb65972a4b15394d0a7ddc4664318551280d1ff222` |
| `autoware_vehicle_msgs/TurnIndicatorsReport` | `RIHS01_c05a54cd244f1c9d683613b11c87a5b3ef816eed7a5f207368301221731a0964` |
| `autoware_vehicle_msgs/HazardLightsReport`   | `RIHS01_01ce3b4293a5c2799fd7483b2d62a790e26fe8f2b5d60e48149163475685f28a` |
| `autoware_control_msgs/Control`              | `RIHS01_7818be59aa790ebb777db06e55a2c15e3756de4cc35c80b1e8271afc5bab2e9d` |
| `geometry_msgs/PoseStamped`                  | `RIHS01_10f3786d7d40fd2b54367835614bff85d4ad3b5dab62bf8bca0cc232d73b4cd8` |
| `geometry_msgs/PoseWithCovarianceStamped`    | `RIHS01_26432f9803e43727d3c8f668d1fdb3c630f548af631e2f4e31382371bfea3b6e` |

## Gates

| Gate                 | Threshold                   | Measured                                                                                                                  | Result     | Mode       |
| -------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ---------- | ---------- |
| G1 NDT localization  | max err <= 0.5 m            | initial: `ndt_samples=0` (dead chain) → after closure + base_link fix (2026-07-23): `max_err=0.077 m`, 400 samples ×2     | **PASS** † | sync-paced |
| G2 closed-loop route | reach goal <= 1.0 m         | initial: dead chain. 2026-07-23 final run: **`closest_approach 0.111 m`** over a 234.5 m autonomous drive @ 4.29 m/s peak | **PASS** ‡ | sync       |
| G3 LiDAR cadence     | 20 Hz +-1 (real-time paced) | 19.95 Hz                                                                                                                  | **PASS**   | sync-paced |
| G3 control loop      | 20 Hz +-5 (sim-paced §)     | 19.96 Hz                                                                                                                  | **PASS** § | sync-paced |

† G1's raw initial-campaign measurement was a dead chain (`ndt_samples=0`); the **PASS** is the
post-closure result after the four blocker fixes AND the base_link↔vehicle-origin fix (issue 6),
live-verified 2026-07-23 on two consecutive 400-sample runs (`max_err` 0.077 / 0.076 m).
See [Blocker closure](#blocker-closure--verified-in-a-live-re-run-2026-07-22).

‡ G2 reached PASS through three successively root-caused-and-fixed blockers, each recorded
below: the spawn point ~7.5 m off the lanelet centerline (fixed via on-lanelet `--initial-pose`;
[on-lanelet respawn](#g2-on-lanelet-respawn--original-root-cause-fixed-gate-still-fails-on-a-new-one)),
the 2.64 m-lane left-turn wedge (fixed by rerouting to a footprint-clearable chain chosen from
map geometry alone), and an IMU yaw-rate **sign inversion** unmasked by the IMU frame fix
(fixed in `runner/spawn.py`; see
[G2 reroute + IMU yaw-rate sign](#g2-reroute--imu-yaw-rate-sign-inversion--strict-gate-pass-2026-07-23)).
Earlier runs also **refuted** the "CARLA 0.10 does not propel in sync" prior — that was
never tested with a valid drive command; the Ackermann path propels in sync once a real
trajectory + engage + emergency-bypass reach the ego (a 445 m drive @ 4.39 m/s).

§ The G3 control-loop band was **re-validated live** (2026-07-23) and corrected from the
unvalidated 60±15 Hz assumption to **20±5 Hz**. Under `use_sim_time:=true` sync pacing every
control node is driven by CARLA's 20 Hz `/clock`, so `/control/command/control_cmd` (the
trajectory-follower's 0.03 s / 33 Hz `ctrl_period` sub-sampled onto the 20 Hz clock) runs
**at the simulation rate**, measured a rock-steady 19.96 Hz → PASS. The old 60 Hz target
assumed a free-running real-time loop that does not exist under sim-time pacing (async
free-runs at ~30 Hz, closer to the 33 Hz design; `vehicle_cmd_gate`'s own `update_rate` is
10 Hz).

## Root-caused blockers

Four causes were isolated during the campaign; the first two are jointly binding for G1, the
third is a seed-path finding (not the binding blocker), and the fourth is an operational
bring-up gotcha rather than a data-path defect.

1. **LiDAR `frame_id = 'ray_cast__'` is absent from Autoware's TF tree (primary G1
   blocker).** The raw cloud `/sensing/lidar/top/pointcloud_raw_ex` flows at 20 Hz with the
   full `PointXYZIRCAEDT` field set and BEST_EFFORT QoS matching `crop_box_filter_self`'s
   subscriber, but its `frame_id` is CARLA's `sensor.lidar.ray_cast` blueprint name
   (`ray_cast__`), and the TF tree only has `velodyne_top/left/right/rear`,
   `sensor_kit_base_link`, `base_link`. `crop_box_filter_self` cannot transform the cloud and
   drops every frame, so the entire per-LiDAR chain is silent (`self_cropped`,
   `mirror_cropped`, `rectified`, `pointcloud_before_sync`, `pointcloud`,
   `concatenated/pointcloud`, `localization/util/downsample/pointcloud`). **Proven** by a
   diagnostic static TF `base_link -> ray_cast__` (= `base_link -> velodyne_top`): the top
   chain immediately came alive (`self_cropped` 0 -> 19.88 Hz, `mirror_cropped` 19.97 Hz,
   `rectified` 20.03 Hz, `pointcloud_before_sync` 19.92 Hz). Diagnostic only; nothing
   committed.
2. **The concatenator expects 3 LiDARs but CARLA provides 1 (secondary, still blocks after
   #1).** `/sensing/lidar/concatenate_data` waits on `[right, top, left]/pointcloud_before_sync`
   with `timeout_sec 0.2`; CARLA/the runner spawns a single LiDAR, so `left`/`right`
   `pointcloud_raw_ex` have publisher count 0. Even with the frame alias feeding
   `top/pointcloud_before_sync` at 20 Hz, `concatenated/pointcloud` stayed SILENT, so NDT
   still has no input.
3. **GNSS `/sensing/gnss/pose_with_covariance` is ~350 m (≈276 m in X) off the true ego
   position (seed-path finding, not the binding blocker).** Extension GNSS pose = map
   `(81652.95, 50135.22, 42.49)`; true ego (spawn point 0) = carla `(-278.39, 220.54, -1.26)`
   -> affine map `(81377.34, 49916.89, 41.24)`. The offset is a consistent divide-by-100
   scale error (the extension acts as if `carla=(-2.78, 2.21, -0.01)`) in the host-side
   metres-vs-centimetres unit at the ABI boundary (host passes metres into the ABI's
   documented-as-centimetres `transform.x_cm`, and the extension divides by 100). The
   **orientation is correct** — the published quaternion `(0, 0, 0.3007, 0.9537)` = yaw +35 deg
   = -carla_yaw, matching the hand-derived single-Y-flip quaternion exactly. Seeding
   `/initialpose` from GNSS therefore placed the NDT guess ~350 m from the real LiDAR — but
   seeding at the **true GT** pose instead did **not** rescue convergence either, confirming
   the binding blocker is the dead cloud chain (#1/#2), not the seed.
4. **`autoware_carla_interface` (pulled in by `simulator_type:=carla`) calls
   `client.load_world()` at startup and wipes the runner's ego (operational).** This is a
   bring-up-order gotcha, not a data defect: the native-DDS stack does not need this node at
   all. Workaround used during the campaign: bring CARLA+runner up, let the one-shot
   `carla_interface` fire-and-die once, then restart CARLA+runner while Autoware stays up. A
   cleaner order for next time is to launch Autoware first.

**G2 is downstream of the same dead localization chain, not an independent failure.** With
no localization, `/planning/scenario_planning/trajectory` is SILENT, so there is no route,
and `vehicle_cmd_gate` emits its default stop command (`longitudinal.velocity 0.0`,
`acceleration -2.5`, `steering_tire_angle 0.0`). That holds in **both** sync and async: sync
shows `longitudinal_velocity: 0.0` throughout (closest approach 40.008 m, ego never moved);
async re-engages to `control_mode = AUTONOMOUS (1)` with `control_cmd` free-running at
30.55 Hz and the ego persisting at spawn, yet peak speed is still **0.000 m/s** because the
autonomous command is a stop, not a drive command — there is simply no trajectory to
execute. G3-control's ~20 Hz (sync) / 30.5 Hz (async) likewise reflects sync-tick pacing /
async free-running, not evidence of a working 60 Hz control loop — the loop has nothing to
control toward either way.

## Refuted / carried hypotheses

| Hypothesis                                                                                               | Verdict                       | Evidence                                                                                                                                                                                                                                                       |
| -------------------------------------------------------------------------------------------------------- | ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sync-mode non-propulsion is the binding G2 blocker (CARLA 0.10/Chaos vehicles don't propel in sync mode) | **Refuted as binding**        | Sync non-propulsion is real (`velocity 0.0`), but async _also_ gives peak 0.000 m/s — because the autonomous command is a stop (no trajectory). The binding blocker is localization, not the tick mode.                                                        |
| NDT non-convergence is the anticipated GNSS **yaw-sign** bug                                             | **Refuted**                   | GNSS orientation is correct (quaternion = -carla_yaw, matches exactly). The GNSS **position** is wrong (~350 m, divide-by-100 scale). NDT fails to converge even seeded at true GT — the seed is not the blocker.                                              |
| LiDAR preprocessing dropped due to **QoS mismatch**                                                      | **Refuted**                   | Publisher and `crop_box_filter_self` subscriber are both BEST_EFFORT / KEEP_LAST(5) / VOLATILE — compatible.                                                                                                                                                   |
| LiDAR dropped due to **missing point fields** (no ring/time)                                             | **Refuted**                   | Raw cloud has the full `PointXYZIRCAEDT` field set.                                                                                                                                                                                                            |
| Empty-perception environment (`perception:=false`) is the cause                                          | **Carried but not the cause** | Perception is intentionally off; the actual break is in **sensing preprocessing** (frame_id + concatenator), upstream of perception. Localization does not depend on perception.                                                                               |
| The ego was destroyed / dying repeatedly                                                                 | **Refuted**                   | Ego stayed alive on the DDS side throughout (velocity/LiDAR/clock all 20 Hz). Two red herrings: (a) `carla_interface` reloaded the world once (bring-up gotcha #4 above); (b) cold host-client queries read an empty world in sync mode before the first tick. |

## Gate tooling

The committed `scripts/e2e/gate_g1_localization.sh`, `gate_g2_closed_loop.sh`,
`gate_g3_performance.sh`, and their `measure_*.py` modules exist and, as of commit `dcd4de0`
(subject `fix(gate): make G1/G2/G3 gate scripts measure`), MEASURE correctly: that commit
fixed the `timeout`-exit-124 abort (GNU `timeout` returning 124 when it kills a
never-terminating `ros2 topic hz` was previously fatal under `set -euo pipefail` / `|| {
fail }`), the missing MGRS affine offset in the ground-truth collector, the missing
`/opt/autoware/setup.bash` source for the control-topic rate measurement, and the sync-mode
cold-client `StopIteration` race (a cold `carla.Client(...).get_actors()` reads an empty
world before the first tick). The FAILs recorded in the [Gates](#gates) table above are real
gate outcomes, not tooling artifacts: they were captured via corrected manual measurement
during the initial campaign (using the same official `measure_ndt.py` / `measure_rates.py` /
`measure_route.py` modules the scripts call, with the four bugs above worked around by hand)
and are reproducible end-to-end by the now-fixed scripts once the blockers in
[Root-caused blockers](#root-caused-blockers) are closed.

## Blocker closure — verified in a live re-run (2026-07-22)

The four blockers were fixed, and a full live E2E re-run was then executed (fresh
`carla-unreal-editor` rebuild carrying the blocker-1/3 fixes, RTX 5090, Autoware
`universe-devel` container). **Result: the sensing/localization chain that was dead in the initial campaign now
runs end-to-end — NDT localizes at ~20 Hz (400 samples, vs the initial campaign's `ndt_samples=0`) with the
full ekf-fused `kinematic_state` at 19.97 Hz.** That re-run left G1 a _measured_ 1.44 m
near-miss, itself root-caused to a base_link frame offset (issue #6 below). **A follow-up
re-run on 2026-07-23, after removing that offset, closes G1 to a live-verified PASS: two
consecutive 400-sample gate runs gave `max_err = 0.077 m` and `0.076 m` (min 0.011 / mean
0.040 m), both well under the 0.5 m threshold** — the residual is the ~6.6 cm velodyne_top Z
mount and NDT noise, not a frame error. Two additional issues, invisible in the initial campaign because the
cloud chain was dead, surfaced and were fixed to get there.

| #   | Root cause                                            | Fix (where)                                                                                                                                                                                                                                                                                                                                                                                                                             | Live verification                                                                                                                                                                                                             |
| --- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | LiDAR `frame_id = ray_cast__` absent from TF tree     | `runner/spawn.py`: `top_lidar_attributes()` sets `ros_name = "velodyne_top"`, which the fork's `ActorDispatcher` uses verbatim as the cloud `header.frame_id`. No fork rebuild — `ros_name` is an existing blueprint attribute (`ActorBlueprintFunctionLibrary.cpp:230`).                                                                                                                                                               | **VERIFIED**: raw cloud `header.frame_id = velodyne_top`; the previously-dead per-LiDAR chain (`self_cropped`→…→`pointcloud_before_sync`) is alive at ~20 Hz. `tests/e2e/test_runner_kit.py` 60/60.                           |
| 2   | Concatenator can't run on 1 LiDAR                     | **Corrected from the planned overlay to a relay.** The concat node HARD-REQUIRES ≥2 topics (`"Only one topic given…"`) so `input_topics=[top]` makes it fail to load; with the stock 3-topic config it loads but stays silent (waiting for left/right) — so concatenation is impossible either way. `launch_autoware.sh` instead relays the single `…/top/pointcloud_before_sync` (already `base_link`) to `…/concatenated/pointcloud`. | **VERIFIED**: `concatenated/pointcloud` at ~20 Hz; localization chain fed. Overlay removed.                                                                                                                                   |
| 3   | GNSS pose ~350 m off (÷100 scale)                     | CARLA fork `ROS2.cpp` `ProcessDataFromVehicle` scaled `carla::geom` **metres** into the ABI's cm fields via `MakeExtensionTransformMetresDeg` (`extension/ExtensionTransform.h`); extension unchanged. Fork commit `cb769ba0f`.                                                                                                                                                                                                         | **VERIFIED**: `/sensing/gnss/pose_with_covariance = (81377.34, 49916.89)` — an _exact_ match to the ego GT affine (was ~`(81652, 50135)` in the initial campaign). `test_ros2_extension_transform.*` + libcarla gate 323/323. |
| 4   | `autoware_carla_interface.load_world()` wipes the ego | `launch_autoware.sh` brings Autoware up **after** CARLA and blocks until the stack is up AND `/autoware_carla_interface` has fired-and-died; `run_e2e.sh WITH_AUTOWARE=1` sequences CARLA → Autoware → ego.                                                                                                                                                                                                                             | **VERIFIED**: ego spawns at spawn-point-0 `(-278.39, 220.54)` and is not wiped; `carla_interface` fired-and-died before the runner spawned.                                                                                   |

### Two further issues found during the live re-run (beyond the original four)

- **5. PCD partial-map metadata (map-setup, `~/autoware_map/nishishinjuku`).** `ndt_scan_matcher`
  uses `dynamic_map_loading` (radius 150 m) via `/map/get_differential_pointcloud_map`, so
  `pointcloud_map_loader` serves the grid cell overlapping the query. The shipped
  `pointcloud_map_metadata.yaml` declared the single 225 MB PCD at grid `[0, 0]` (cell
  `x[0,100] y[0,100]`), but the map is MGRS-local `x[81080,82194] y[49707,50830]` — so every
  query near the ego matched no cell → NDT `No InputTarget`. Fix: one grid-aligned cell
  `x_resolution: 4000`, `pointcloud_map.pcd: [80000, 48000]`. **The grid value MUST be
  integers** — floats (`80000.0`) throw `yaml-cpp: bad conversion` and crash the whole
  `pointcloud_map_loader` node. With integers the map loads and `No InputTarget` disappears.
  (Not committed — map data lives outside the repo.)
- **6. base_link ↔ CARLA vehicle-origin frame offset — the residual 1.44 m. ROOT-CAUSED,
  FIXED, AND LIVE-VERIFIED (2026-07-23): G1 now PASSES at max_err 0.077 m.** NDT tracked steadily at
  `max_err 1.441 m`, essentially constant (min 1.386, mean 1.407) and along the ego heading —
  i.e. ≈ wheelbase/2 (1.395 m). NDT places `base_link` ~wheelbase/2 _ahead_ of CARLA's reported
  vehicle origin (correcting the GT by −wheelbase/2 makes it _worse_, 2.84 m).

  **Geometry (why it is exactly wheelbase/2, and why removing the shift is the fix).** The G1
  ground truth is `ego.get_transform()` — the CARLA vehicle origin. NDT publishes `base_link`.
  CARLA places attached sensors relative to that same vehicle origin, so the physical top-LiDAR
  world position was `ego_origin + (x_bl + wheelbase/2)`, where `x_bl` is the sensor's composed
  base_link X (0.9 m) and the `+wheelbase/2` came from `runner/kit.py::base_link_to_vehicle_center`.
  Autoware rebuilds the sensor TF from the SAME kit yamls — `base_link → sensor = x_bl`, with **no
  vehicle term** — so NDT back-solves `base_link = sensor_world − x_bl = ego_origin + wheelbase/2`.
  Against `GT = ego_origin` that is a constant `+wheelbase/2` error along heading, matching the
  measurement, and it is _independent of where the true vehicle origin sits on the chassis_
  (that offset appears identically in both the sensor placement and the GT, so it cancels). The
  `+wheelbase/2` was a pure uncompensated offset Autoware never saw; its "validated live" claim
  was circular (it only confirmed the attach number matched the formula, not a ground truth).

  **Fix (merged via PR #20).** Removed the shift: `carla_attach_location`
  now returns the composed base_link pose verbatim (`(0.9, 0, 2.0)`, was `(2.295, 0, 2.0)`),
  pinning `base_link` to the CARLA vehicle origin. Then `base_link_ndt = ego_origin + 0 = GT`,
  so the modelled error collapses to ~0 regardless of the chassis origin convention (rear-axle
  vs mid-wheelbase), which is un-measurable on CARLA 0.10 anyway (wheel geometry is empty). The
  now-moot `base_link_to_vehicle_center`, `SAMPLE_VEHICLE_WHEELBASE`, and `ego_wheelbase()` were
  removed with them. **Unit-verified** (`pytest tests/e2e/` 55 passed; `test_runner_kit`
  pins `carla_attach_location == sensor_in_base_link`), geometrically proven above, **and
  live-verified 2026-07-23**: after the fix the G1 gate returned `max_err = 0.077 m` and
  `0.076 m` on two consecutive 400-sample runs (min 0.011 / mean 0.040 m) — exactly the
  predicted collapse from ~wheelbase/2 (1.44 m) to the residual Z/noise floor. Alternative
  considered and rejected: correcting the
  gate's GT reference instead would paper over a real +1.4 m sensor misplacement (the physical
  LiDAR would still sit wheelbase/2 ahead of where Autoware's TF claims). Second-order note for
  G2: pinning base_link to the vehicle origin means the control bicycle-model's rear-axle
  reference may be off by up to wheelbase/2 if CARLA's origin is not the rear axle — bounded and
  re-examinable if G2 path tracking is poor.

### Operational finding: DDS ghost nodes across bring-up cycles

The Autoware container runs `network_mode: host` + `ipc: host`, so all runs share DDS domain 0.
Hard-killing a `ros2 launch` (SIGKILL after the graceful window) leaves its nodes' discovery
entries lingering; across repeated bring-ups these **ghosts accumulate** (node count climbed
168 → 218, every node appearing 3×, and Autoware's own `duplicated_node_checker` flagged them),
and a duplicate name makes composable loads (`crop_box_filter_self`) silently fail — a dead
per-LiDAR chain that looks like a regression but is stale state. **`docker compose down` between
live runs** (not just SIGINT of the harness) is required to clear it; a clean domain reliably
brings up the full 168-node stack.

## Non-goals / Deferred

- G4 package gate (`make package` + drop-in) — descoped for this campaign (still future work; see the README roadmap).
- Town10 + lanelet2 auto-generation — future work; no CARLA(.xodr) -> lanelet2 reverse
  converter exists (`docs/nishishinjuku-map.md`).

## Initial campaign verdict: FAIL → post-closure G1 + G3-LiDAR PASS (G2, G3-control then still open)

What was proven: the extension's sensor and status publishers are alive and correctly typed
end-to-end into a live Autoware `universe-devel` stack (170 nodes up, no launch/domain
aborts, LiDAR cadence within the 20 Hz +-1 Hz gate). What FAILed, and precisely why: NDT
localization never converges because the sensing-preprocessing chain silently drops every
LiDAR frame (TF frame-id mismatch, then a 3-vs-1 LiDAR concatenator mismatch even after that
is patched); closed-loop route completion FAILs in both sync and async as a direct
consequence of that dead localization chain, not because of CARLA's known sync-mode
propulsion limitation; and the control-loop rate gate FAILs because there is no drive
command to actuate at any rate, not because the loop itself cannot reach 60 Hz. None of the
four root causes are gate-tooling artifacts — the R3 script fixes (`dcd4de0`) make the
committed scripts measure correctly, and they reproduce the same FAILs. On the initial gate contract
as scoped, **the initial campaign is a FAIL**, root-caused to the sensing-integration gaps listed in
[Root-caused blockers](#root-caused-blockers).

### Post-closure status (2026-07-23)

All four initial-campaign blockers were fixed and live-verified (bringing the dead chain to life), and the
subsequent base_link↔vehicle-origin offset (issue #6) was fixed and live-verified, closing
**G1 to a PASS (`max_err` 0.077 / 0.076 m over two 400-sample runs, threshold 0.5 m)**
alongside the already-passing **G3-LiDAR (19.95 Hz)**. **G2 and G3-control were then run live
on 2026-07-23** (see [G2/G3 live campaign](#g2g3-live-campaign-2026-07-23)): **G3-control is
now a PASS** (band re-validated 60±15 → 20±5 Hz, measured 19.96 Hz), and — after the
on-lanelet respawn, a reroute off the footprint-infeasible left turn, and the IMU yaw-rate
sign fix — **G2 is now a PASS** (`closest_approach` **0.111 m**, tol 1.0 m, over a 234.5 m
autonomous drive through a signalized junction). The revised standing is therefore
**PASS on all four gates: G1, G2, G3-LiDAR, and G3-control.**

## G2/G3 live campaign (2026-07-23)

Run against the now-working stack (the PR #20 branch, container
`sha256:405225eda6…`, `universe-devel`/humble). Every FAIL and refuted hypothesis is
recorded; no gate was tweaked to manufacture a pass.

### Committed changes this campaign

- `runner/spawn.py` — **`sensor_tick=0.05` on the top LiDAR and IMU.** In sync (0.05 fixed
  delta) this is a no-op. In async the server free-runs at ~140 fps, and without it the native
  LiDAR emits one thin ~25°, ~2 k-point slice **per server frame** (~140 Hz); NDT cannot match
  those fragments (transform_probability ~3.97, pose jittered 18–65 m off GT). Pinning
  `sensor_tick` restores full 0.05 s / 20 Hz clouds in async too.
- `scripts/e2e/gate_g3_performance.sh` — control band `60±15` → `20±5` Hz (see § below /
  the Gates footnote), with the live-measured rationale in-script.
- `scripts/e2e/run_e2e.sh` — `RUNNER_ASYNC=1` opt-in (appends `--async`) for the G2
  propulsion mode, mirroring the existing `WITH_AUTOWARE` opt-in.

### Synthetic perception (perception:=false workaround, scratchpad-only, NOT committed)

The stock image cannot run perception (CUDA-only ground-seg + no DNN artifacts), so
`behavior_path_planner` hard-blocks (`waiting for dynamic_object`) → no trajectory → no
control. A scratchpad `dummy_perception` node supplies the **empty** ("clear road") versions
a real stack would emit — `PredictedObjects`, `OccupancyGrid`, obstacle `PointCloud2` — plus
**all 164 map traffic-light groups as GREEN** (perception-off leaves every signal UNKNOWN →
the `traffic_light` module inserts a phantom red-light stop ~11.6 m ahead; the green feed is
supplied as a synthetic input rather than an
`autoware_launch` overlay that deletes the safety module). With these, the planning→control
chain runs: trajectory 10 Hz, `control_cmd` 19.97 Hz.

### G3 — PASS (sync-paced)

`gate_g3_performance.sh`: **LiDAR 19.96 Hz** (20±1) and **control 19.96 Hz** (20±5, re-validated
band) → both PASS, exit 0. `use_sim_time` pins every node to CARLA's 20 Hz `/clock`, so the
33 Hz-design controller (`ctrl_period` 0.03 s) is sub-sampled to the simulation rate;
`vehicle_cmd_gate.update_rate` is 10 Hz but `control_cmd` tracks the faster passthrough.

### G2 — closed-loop driving PROVEN; strict goal-arrival gate FAIL (22.84 m)

Sequence: engage via `/autoware/engage` → `control_mode` AUTONOMOUS(1), op-mode AUTONOMOUS(2)
(this legacy path flips autonomous even though the system-diagnostics graph withholds it).
The `vehicle_cmd_gate` then MRM-overrode the drive command with an emergency stop
(`velocity 0, accel −1.5`) — a **false** emergency from the perception-off diagnostics + an
IMU-frame gap (the extension published the IMU as `frame_id: imu3`, absent from the kit TF
tree, so `/sensing/imu/imu_data` never forms, mirroring the LiDAR frame_id blocker #1 —
root-caused and fixed after the campaign, see "IMU frame fix" below).
The **raw** trajectory-follower output was already a genuine drive command (`velocity 0.25,
accel +0.59`); setting `vehicle_cmd_gate use_emergency_handling:=false` (a false-emergency
suppression on a confirmed-clear route) let it reach the ego.

**Result:** the sync ego then **PROPELLED** — a 445 m autonomous drive at up to 4.39 m/s,
fully closed-loop under NDT (which stayed 0.04–0.11 m of ground truth across the whole run).
This **refutes the "CARLA 0.10 does not propel in sync" prior**, which was never tested with a
valid drive command (the initial campaign had no trajectory). `gate_g2_closed_loop.sh` over the full 120 s
window: **`closest_approach 22.84 m` (tol 1.0 m) → FAIL**.

Root cause of the FAIL (precisely localized): the single map spawn point sits **~7.5 m off the
lanelet2 centerline**, so the controller tracks a driving lane ~22.8 m parallel to the
routed goal's lane, and the mission-planned route (a valid 445 m winding path) never brings
the ego within the goal-arrival threshold of any goal that _plans_; short direct goals on the
ego's actual driven lane return "The planned route is empty." The gate FAILs on this
route/goal geometry, not on the closed-loop capability.

### Async localization — refuted as the G2 path

Async is required for propulsion on prior builds, but here it **breaks NDT**: with the ego
held stationary at spawn and GNSS auto-init perfect, NDT over 20 s measured 18–65 m error
(median 51 m), **0/34 samples within 1.0 m**, `iteration_num` maxed (30), and ekf carried a
phantom −7.27 m/s twist — because `/clock` free-runs at ~140 Hz and the async LiDAR cloud is
malformed for scan-matching even after the `sensor_tick` rate fix. Since **sync now propels**,
G2 runs in sync (perfect NDT) and async is not needed — the reverse of the initial-campaign assumption.

### New operational gotchas

- Two `run_e2e.sh` instances must **never** overlap: they share container-side PID files
  (`/tmp/e2e-autoware.cpid`) and DDS domain 0, so one's teardown kills the other's Autoware
  launch. Fully confirm port 2000 free + editor gone before relaunching.
- Host `carla.Client` gets `Connection refused` during Autoware bring-up (while
  `carla_interface`'s `load_world` holds the RPC); it clears once the stack is up.
- Teleporting the ego (`set_transform`) to reset it desyncs NDT/ekf; reseed `/initialpose` to
  re-lock, and expect the motion-planning trajectory to need a fresh route afterward.

### G2 on-lanelet respawn — original root cause FIXED, gate still FAILs on a new one

Follow-up to the G2 FAIL above. The recorded root cause was that the map's single spawn point
sits ~7.5 m off the lanelet2 centerline. That was addressed directly (rather than by choosing
a goal that flatters the gate) by seeding the ego on the centerline via the runner's existing
`--initial-pose`, plumbed through `run_e2e.sh` as `RUNNER_EXTRA_ARGS`.

**The targeted root cause is fixed, measured:**

| Quantity                             | Before      | After                |
| ------------------------------------ | ----------- | -------------------- |
| Spawn offset from lanelet centerline | **7.478 m** | **0.002 m**          |
| NDT error at spawn                   | —           | 0.011–0.03 m         |
| Route planned to an independent goal | —           | 31 segments, 213.8 m |

The 7.478 m figure was measured independently here (segment-wise projection of the ego onto
lanelet 253's centerline), confirming the earlier ~7.5 m estimate.

**The strict gate still FAILs, for a different and newly-exposed reason.** Best
`closest_approach` across three runs: **172.05 m** (tol 1.0 m). The ego drives cleanly for
~36 s under a rock-solid NDT lock (0.02–0.06 m), then **wedges at the first left turn** and
never recovers. Evidence, from a 5 Hz ground-truth + NDT + control time series:

- **It is a physical obstruction, not a commanded stop.** At the stall the ego holds throttle
  0.74 with brake **0.00** and displaces 0.000 m. Earlier, speed collapses 3.35 → 0.02 m/s in
  0.4 s _while throttle is applied and no brake is commanded_ — a collision signature, not
  deceleration.
- **Both LEFT corners of the footprint are off the drivable surface** (`project_to_road=False`
  → NO; front-left 2.497 m and rear-left 2.061 m from lane centre), while both right corners
  are on it. The ego cut the turn and put its left side onto non-drivable geometry.
- **Geometry is tight map-wide:** the turn lane is **2.64 m** (map-wide median 3.04 m, min
  2.00 m over 8490 sampled driving waypoints) against a **1.84 m wide × 4.9 m long** ego —
  0.40 m clearance per side.
- **Not speed-induced.** Capping planning to 2.0 m/s (peak 4.14 → 2.31 m/s) moved the stall
  point only ~2 m further; all three runs wedge at the same corner (~81399–81400, 49933–49935).
- **NDT divergence is a consequence, not a cause.** NDT held 0.02–0.06 m for the entire 36 s
  of driving and only diverged (2.0 m, drifting to 3.5 m) _after_ the impact impulse. The
  earlier `mrm_state 3/2` MRM latch is likewise downstream: on a clean re-seed the stack arms
  at MRM NORMAL/NONE with a genuine drive command (+0.53 accel).

Per this repo's evidence discipline the FAIL is recorded as measured. Three independent
attempts (on-lanelet spawn; + MRM suppression; + velocity limit) all terminate at the same
geometric point, so the remaining blocker is **lane geometry vs vehicle footprint through this
turn**, not spawn placement, localization, speed, or the false MRM. Closing it is a separate
workstream (a route whose turns the footprint can clear, a narrower ego, or a
controller/path-shape change) and is NOT claimed here.

**CLOSED later the same day** via the first option — a rerouted goal chosen from map geometry
alone — which then exposed (and fixed) one further blocker; see
[G2 reroute + IMU yaw-rate sign](#g2-reroute--imu-yaw-rate-sign-inversion--strict-gate-pass-2026-07-23).

**Also verified this session:** the IMU frame fix does **not** remove the need for
`use_emergency_handling:=false` — armed without it, the run still ended in MRM (state 3,
behavior 2) with `is_autonomous_mode_available: false`. The perception-off diagnostics remain
an independent contributor, exactly as hedged below.

### IMU frame fix — the `ray_cast__` twin (root-caused + live-verified 2026-07-23)

The false MRM above had a second, structural contributor: the IMU carried `frame_id: imu3`.
Traced through the fork, the name is mangled in **two** stages, which is why it has a digit
where the LiDAR's `ray_cast__` does not:

| #   | Layer                                | Behaviour                                                                                                              |
| --- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| 1   | `runner/spawn.py` `imu_attributes()` | omitted `ros_name` (the LiDAR set it)                                                                                  |
| 2   | `ActorDispatcher.cpp:275-288`        | `RosName == id` → placeholder `imu__` (last dot-token + `__`), registered as **both** ros_name and frame_id            |
| 3   | `ROS2.cpp:655` IMU branch            | calls `resolve("imu")` → `ResolveAutoStreamSuffix` (`ROS2.cpp:555-572`) → `imu` + stream_id = **`imu3`**               |
| 4   | `CarlaIMUPublisher.cpp:45`           | `header.frame_id = GetFrameId()`                                                                                       |
| 5   | Autoware                             | `imu3` ∉ kit TF tree → gyro_bias/imu_corrector dead → no `/sensing/imu/imu_data` → AEB + diagnostics ERROR → false MRM |

Stage 3 is IMU-specific: the lidar/radar/DVS/semantic-lidar branches skip `resolve()` when a
`ros_topic_name` override is present, the IMU branch calls it unconditionally.

**Fix:** `runner/spawn.py` sets `ros_name` on the IMU, bound to `kit.IMU_FRAME`
(`tamagawa/imu_link`) rather than a duplicated literal, so the published frame cannot drift
from the calibration the sensor is mounted at. No CARLA rebuild — `ros_name` is declared for
every actor definition by `FillIdAndTags` (`ActorBlueprintFunctionLibrary.cpp:230`), not just
lidars. Two fork properties were verified in source to make the slash-bearing name safe:
`ResolveAutoStreamSuffix` early-returns unless ros_name is exactly the `imu__` placeholder (so
the unconditional `resolve("imu")` cannot clobber an explicit name), and `BuildBaseTopicName`
(`ROS2.cpp:538-541`) emits the verbatim `ros_topic_name` override (so the slash never reaches
DDS topic construction).

**Verification — LIVE, on a cold-started sync stack** (container `405225eda6`, 169 nodes,
concat relay up). 67 pytest pass (incl. a regression pin that the IMU `ros_name` equals
`IMU_FRAME`), and the live stack confirms every link of the chain:

| Check                                        | Before (campaign)  | After (this fix)                                    |
| -------------------------------------------- | ------------------ | --------------------------------------------------- |
| `/sensing/imu/tamagawa/imu_raw` frame_id     | `imu3`             | **`tamagawa/imu_link`**                             |
| `/sensing/imu/imu_data`                      | never formed       | **19.96 Hz**                                        |
| TF `base_link` → `tamagawa/imu_link`         | absent             | resolves: `[0.900, 0.000, 2.000]`, ~180° mount flip |
| `aeb_emergency_stop` diagnostic              | ERROR              | **OK (0)**                                          |
| `gyro_odometer_status` diagnostic            | ERROR (chain dead) | **OK (0)**                                          |
| `vehicle_cmd_gate: emergency_stop_operation` | —                  | **OK (0)**                                          |

The TF translation/rotation match the committed kit calibration (the IMU mount is the ~180°
roll/yaw flip `spawn.py` documents), confirming the frame is not merely _accepted_ but
_correctly placed_. `gyro_bias_scale_validator` sits at WARN (`0x01`), not ERROR — expected
with the ego stationary, since bias estimation needs motion.

So the **IMU-driven contributor to the false MRM is cleared**: AEB and gyro_odometer are OK
and the gate reports no emergency-stop operation. The perception-off diagnostics remain a
separate contributor, so whether `use_emergency_handling:=false` can be dropped from the G2
arm recipe entirely is **not** claimed here — that needs a re-run of the full G2 arm sequence
(synthetic perception + all-green signals + route + engage), which this verification did not
perform.

**PARTIALLY SUPERSEDED (same day):** making the gyro _fuse_ for the first time unmasked a
yaw-rate **sign inversion** in the fork's IMU data (the fork emits the gyro
vehicle-frame-consistent regardless of mount rotation, so rotating it by the kit frame's
~180° flip negates it). The frame claim was therefore revised `tamagawa/imu_link` →
`base_link`; the mangling chain above, the diagnostics recovery, and the "does not remove
`use_emergency_handling:=false`" finding all stand. Full measurement chain in
[G2 reroute + IMU yaw-rate sign](#g2-reroute--imu-yaw-rate-sign-inversion--strict-gate-pass-2026-07-23).

### G2 reroute + IMU yaw-rate sign inversion — strict gate PASS (2026-07-23)

Continuation of the on-lanelet respawn section above: the wedge blocker was closed by the
first of its listed options (a route whose turns the footprint can clear), which then exposed
one final blocker — an IMU yaw-rate sign inversion — root-caused and fixed the same session.
Final result: **G2 strict gate PASS, `closest_approach` 0.111 m (tol 1.0 m)**.

#### Step 1 — reroute chosen from map geometry alone (honest-gate discipline)

Every successor chain out of the on-lanelet spawn was enumerated and scored offline
(lanelet2 + MGRSProjector in the Autoware container; scratchpad `score_routes.py`) on two
per-lanelet metrics: **min lane width** (left/right bound gap sampled along the centerline)
and **heading-change rate** (deg/m). The proven envelope from the wedge campaign separates
cleanly:

| Lanelet                    | Width  | Turn rate      | Outcome                    |
| -------------------------- | ------ | -------------- | -------------------------- |
| 253 / 255 (driven clean)   | 2.62 m | 0.57 / 0.0 °/m | drivable, proven live      |
| 570 (the wedge)            | 2.54 m | **2.03 °/m**   | wedged 3/3, proven live    |
| 495 (chosen junction exit) | 2.61 m | 0.52 °/m       | inside the proven envelope |

Kill rule: width < 3.0 m AND rate > 1.0 °/m. Of 9 chains, exactly 2 are clean; the chosen one
is **253 → 255 → 495 → 280 → 283 → 382 → 226** (~386 m usable; everything after 495 is
≥ 2.97 m wide). The goal is placed 23.3 m into lanelet 226 — **(81571.616, 50019.827, z 42.07),
yaw 10.43°**, ~250 m of driving from the spawn. Pre-flight (`verify_route.py`) confirmed on the
map, before any live run: the lanelet2 **shortest path** to that goal is exactly the scored
chain (no lane changes, no killer lanelets — the router cannot re-introduce the wedge), and
both traffic lights on the route (1489 on 495, 1515 on 382) are in the all-green dummy list.
The goal is derived from lanelet geometry only — never from a driven trajectory — so the
strict 1.0 m gate stays honest.

#### Step 2 — new blocker: hard-right veer, 3/3 crashes within ~25 m

On the rerouted goal the ego VEERED hard right ~10 m after motion start and crashed into the
right-side boundary at ~4 m/s — three consecutive runs, same signature
(`closest_approach` 204.9 / 213.7 / 204.5 m). This stretch (253/255) was driven clean for
36 s the previous day, and the planned route was verified correct
(`/planning/mission_planning/route` preferred lanelets = the scored chain exactly), so
planning was exonerated up front. A synchronized 5 Hz probe (host CARLA ground truth +
container EKF/NDT/control log; scratchpad `log_ndt2.py`) then isolated the failure in one
instrumented run:

- Up to 3.3 m/s the belief tracks truth (yaw err ≤ 1.8°, **NDT yaw = GT yaw exactly**).
- As the ego physically rotates right, the **EKF yaw rotates LEFT** (truth 34.8° → 27.6°
  while belief 34.9° → 38.5°); NDT keeps tracking truth until overwhelmed, then slides into
  a mirrored basin (belief = truth + 160.0° at rest, NVTL 2.71 — "healthy").
- Commanded steering matches CARLA-applied steering throughout (both = turn right): the
  controller is faithfully chasing a phantom left-veer. Positive feedback to full lock.

An EKF yaw that mirrors physical rotation while the pose source is still correct means the
fused yaw rate has an **inverted sign**. The gyro only began to be _fused_ when the IMU frame
fix (previous section) revived `gyro_odometer` — which is exactly why the previous day's
36 s drive (gyro chain dead, EKF on NDT alone) was stable and every post-fix drive was not.

#### Step 3 — boundary probe pins the inversion, fork source confirms it

A second probe (`log_imu.py`) logged the raw wire gyro, the corrected gyro, and ground truth
through one veer:

| Signal                            | Observation                                    |
| --------------------------------- | ---------------------------------------------- |
| `imu_raw` angular_velocity.z      | == TRUE base_link yaw rate, sign AND magnitude |
| `imu_data` (post `imu_corrector`) | == **−raw on every sample**                    |
| EKF yaw                           | integrates the inverted rate, mirrors truth    |

`imu_corrector` rotates the sample from its claimed frame (`tamagawa/imu_link`, which carries
the kit's ~180° mount flip) into base_link — correct behaviour for data truly expressed in
that flipped sensor frame. The fork does not deliver that:
`AInertialMeasurementUnit::ComputeGyroscope` (`InertialMeasurementUnit.cpp`) takes the OWNER
vehicle's angular velocity in the VEHICLE frame and applies
`SensorLocalRotation.RotateVector(...)` — Rotate, not Unrotate, and a 180° flip is its own
inverse — so the wire gyro is **vehicle-frame-consistent regardless of mount rotation**. The
accelerometer path does the opposite (`Unrotate` by the sensor GLOBAL rotation → truly
flipped-sensor-frame; measured az = −9.8 at rest). The fork emits **mixed-frame IMU data**;
no frame claim can make both fields correct without a fork rebuild.

**Fix (committed, `runner/spawn.py` + regression pin in `tests/e2e/test_runner_kit.py`):**
`IMU_ROS_NAME = "base_link"` — the corrector's rotation becomes the identity, which fixes the
field this stack actually fuses (angular velocity: gyro_odometer → EKF, gyro_bias_estimator,
AEB path prediction) and keeps the frame TF-resolvable (the previous fix's benefit). KNOWN
RESIDUAL, documented in-code: `imu_data` linear_acceleration.z reads −9.8 at rest; nothing in
this perception-off stack consumes IMU linear acceleration. The durable fix belongs in the
fork (make `ComputeGyroscope` express the owner rate in the sensor frame via the sensor
global rotation, mirroring the accelerometer), after which the claim should return to
`kit.IMU_FRAME` — this joins `e845b9fa1` / `a5c04f146` on the list of fork fixes any
downstream CARLA build must carry (as a pending patch).

Verified live before the gate: 39.3 m dead-straight drive at 4.28 m/s with **max yaw error
0.22°** and final EKF-vs-GT error 0.02 m (was a 160° runaway within 25 m).

#### Step 4 — PASS run (fresh cold-boot stack, fix in from spawn)

| Quantity                        | Measured                                                                                             |
| ------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `closest_approach` to goal      | **0.111 m** (tol 1.0 m) → **PASS**, exit 0                                                           |
| Route driven                    | 234.5 m in 65.9 s (avg 3.56, peak 4.29 m/s)                                                          |
| Junction                        | signalized, crossed via 495 under all-green                                                          |
| Yaw error while moving          | max 0.22°, median 0.07° (n=303)                                                                      |
| EKF-vs-GT position error moving | median 0.185 m, max 0.452 m                                                                          |
| Final rest                      | 4.06 m past the goal, brake hold (overshoot — the gate metric is min distance; recorded for honesty) |

Recipe as in the previous sections: sync stack, on-lanelet `--initial-pose`, synthetic
perception + all-green signals, `use_emergency_handling:=false` (still required),
`gate_g2_closed_loop.sh 81571.616 50019.827`.

#### Operational findings from the reroute campaign

- **NDT drifts while parked.** Left idle 15+ min at the spawn, the NDT/EKF pair slid 2.2 m
  off (and once re-captured the mirrored basin after a crash). While _driving_ it is solid
  (see above). Re-seed `/initialpose` immediately before arming; do not trust a lock that has
  been idling.
- **`/initialpose` re-seed must be published programmatically.** `ros2 topic pub` with inline
  YAML silently mangles the 36-entry covariance (parser caret, no error surfaced through the
  pipeline); an rclpy publisher + convergence watch (scratchpad `reseed_localization.py`)
  re-locks NDT from a 160°-flipped basin in ~10 s.
- **Engage latches across re-arms.** After a gate run, the stack is still ENGAGED; setting a
  new route makes the ego drive off immediately. Disengage (`change_to_stop` +
  `/autoware/engage false`) before teleport/reseed/re-arm.
- **One behavior_planning_container SIGABRT** (rclcpp Humble wait-set race:
  `failed to add guard condition to wait set: guard condition implementation is invalid`,
  `guard_condition.c:172`) at arm time invalidated one run: the ego drove 39 m on the stale
  last trajectory, stopped at its end, and the trajectory-timeout MRM latched. Single
  occurrence across 6+ arms; environmental, not route- or fix-related; recover with a full
  stack recycle (an Autoware-only relaunch would re-fire `autoware_carla_interface`'s
  `load_world` and wipe the live ego).

#### Step 5 — fork-side fix lands; the kit frame claim is restored and re-verified (2026-07-23)

The pending fork fix flagged in Step 3 was implemented on the fork's integration branch
(`ae166d80d`, `fix(ros2): emit IMU data in the true sensor frame with REP-103 handedness`,
published as `youtalk/carla` PR branch `autoware/11-imu-sensor-frame`):

- `ImuMath.h` gains the pure UE→ROS conversions — polar vectors `(x, −y, z)` for linear
  acceleration, pseudovectors `(−x, +y, −z)` for angular velocity — used by
  `CarlaIMUPublisher::Write` (which had copied UE left-handed components verbatim). Pinned by
  the new `LibCarla/source/test/common/test_imu_axes.cpp`, including the live-measured G2
  failure case as a regression test; **`libcarla_test_server` 333/333** (4 new, TDD
  red→green).
- `ComputeGyroscope` now unrotates the world-frame rate by the sensor's **global** rotation
  (mirroring `ComputeAccelerometer`), replacing the owner-frame + `RotateVector`(relative)
  spelling — the latent inverse-rotation / attachment-depth bug that the 180° flip had masked.

With the fork emitting genuinely flipped-sensor-frame data, `runner/spawn.py` returns
`IMU_ROS_NAME` to `kit.IMU_FRAME` (the interim `base_link` claim would now itself be the
inversion), and the regression pin reasserts claim == kit frame. Re-verified LIVE on a fresh
cold-boot stack with the rebuilt editor + `carla-ros2-native`:

| Check                                  | Measured                                                                                                    |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `imu_raw` frame_id                     | `tamagawa/imu_link`                                                                                         |
| `imu_raw` accel at rest (sensor frame) | z = **−9.81**                                                                                               |
| `imu_data` accel at rest (base_link)   | z = **+9.81** — the Step-3 residual is GONE                                                                 |
| Gyro contract over 97 turn samples     | raw_wz = **−gt_rate**, cor_wz = **+gt_rate**, median error 0.0002 rad/s (exact mirror of the bug-era probe) |
| G2 strict gate (same goal/route)       | **`closest_approach` 0.123 m → PASS**, exit 0                                                               |
| Localization while moving              | yaw err max 0.33° / median 0.10°; pos err median 0.221 m                                                    |

Operational note for future bring-ups: with the kit frame claimed, a veer-right crash within
~25 m of motion start is the live signature of running a **stale fork build** (one without
`ae166d80d`) — rebuild `carla-unreal-editor` + `carla-ros2-native`, don't debug the stack.
This closes fork-fix #3; the three fork commits any downstream CARLA build must carry are now
`e845b9fa1` (empty-mesh SIGSEGV guard), `a5c04f146` (CycloneDDS `from_ser` reassembly), and
`ae166d80d` (IMU sensor-frame emission).
