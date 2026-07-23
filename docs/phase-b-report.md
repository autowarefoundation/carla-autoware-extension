# Phase B M4 gate report (Autoware semi-native, Nishi-Shinjuku)

Milestone **M4** ran the live gate campaign for the CARLA native-DDS <-> Autoware
semi-native integration: G1 (NDT localization), G2 (closed-loop route completion), and G3
(sensor/control cadence) against a running Autoware `universe-devel` container and CARLA on
the AWSIM v2.0.0 Nishi-Shinjuku map. Per the 2026-07-23 decision, this report documents the
gate outcomes as measured, including the FAILs and their root causes — the same evidence
discipline this project already applies to the NuRec NO-GO gates (`reports/nurec-n2.md`):
an honest, precisely-localized FAIL with preserved refuted hypotheses is itself the
deliverable, not a reason to soften the record.

- Date: 2026-07-23 (UTC ~00:35-01:16).
- All work local-only; no repo files were modified by the campaign itself (`git status`
  after teardown showed only the pre-existing untracked `CLAUDE.md`).

**Verdict summary:** G1 NDT localization **FAIL**, G2 closed-loop route **FAIL** (both sync
and async), G3 LiDAR cadence **PASS**, G3 control loop **FAIL**. All FAILs trace to two
CARLA<->Autoware sensing-integration gaps that leave the localization chain dead, plus a
GNSS position-scale bug; see [Root-caused blockers](#root-caused-blockers).

## Environment

| Item                     | Value                                                                                                                    |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| Autoware container image | `ghcr.io/autowarefoundation/autoware:universe-devel`                                                                     |
| Container image digest   | `sha256:405225eda6c05161bfde39cc7885511f3f4d9699d126891891420dd80c2e024a`                                                |
| `ROS_DISTRO`             | `humble`                                                                                                                 |
| CARLA fork               | `feat/autoware-seminative-phase-b` @ `584743b24`                                                                         |
| Extension (this repo)    | `phase-b/9-m4-gates` @ `dcd4de0` (rosidl message layer; R1 DT_RPATH `.so`; R2 live-run enablement; R3 gate-script fixes) |
| Middleware               | `rmw_cyclonedds_cpp`; `ROS_DOMAIN_ID=0`; `CYCLONEDDS_URI=docker/cyclonedds.xml`                                          |
| Map                      | AWSIM v2.0.0 Nishi-Shinjuku, `Shinjuku-Map.zip` (129,585,415 B, see `docs/nishishinjuku-map.md`); MGRS 54SUE             |

The extension HEAD above (`dcd4de0`) postdates the live campaign by one commit: the runs
recorded below were executed against `f2f9133` (R2, before the R3 gate-script fixes), and
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
non-ML fallback (full detail: `docs/running-phase-b.md`). Neither gap is specific to this
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

| Gate                 | Threshold                   | Measured                                           | Result   | Mode           |
| -------------------- | --------------------------- | -------------------------------------------------- | -------- | -------------- |
| G1 NDT localization  | max err <= 0.5 m            | `ndt_samples=0, max_err=nan` (NDT never converged) | **FAIL** | sync-paced     |
| G2 closed-loop route | reach goal <= 1.0 m         | `closest_approach 40.008 m`; ego peak 0.000 m/s    | **FAIL** | sync AND async |
| G3 LiDAR cadence     | 20 Hz +-1 (real-time paced) | 19.95 Hz                                           | **PASS** | sync-paced     |
| G3 control loop      | ~60 Hz (+-15)               | 19.96 Hz sync / 30.5 Hz async                      | **FAIL** | sync / async   |

The G3 control-loop threshold (60±15 Hz) is carried over from an earlier assumption and has
not been independently validated against this stack; the 30.55 Hz async free-running
measurement suggests ~30 Hz may be Autoware Humble's actual
`/control/command/control_cmd` design rate, and the target should be re-validated before the
next campaign.

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

The committed `scripts/phase_b/gate_g1_localization.sh`, `gate_g2_closed_loop.sh`,
`gate_g3_performance.sh`, and their `measure_*.py` modules exist and, as of commit `dcd4de0`
(subject `fix(gate): make G1/G2/G3 gate scripts measure`), MEASURE correctly: that commit
fixed the `timeout`-exit-124 abort (GNU `timeout` returning 124 when it kills a
never-terminating `ros2 topic hz` was previously fatal under `set -euo pipefail` / `|| {
fail }`), the missing MGRS affine offset in the ground-truth collector, the missing
`/opt/autoware/setup.bash` source for the control-topic rate measurement, and the sync-mode
cold-client `StopIteration` race (a cold `carla.Client(...).get_actors()` reads an empty
world before the first tick). The FAILs recorded in the [Gates](#gates) table above are real
gate outcomes, not tooling artifacts: they were captured via corrected manual measurement
during the M4 campaign (using the same official `measure_ndt.py` / `measure_rates.py` /
`measure_route.py` modules the scripts call, with the four bugs above worked around by hand)
and are reproducible end-to-end by the now-fixed scripts once the blockers in
[Root-caused blockers](#root-caused-blockers) are closed.

## Deferred integration work (future)

Per the user's 2026-07-23 decision, closing the CARLA<->Autoware sensing-chain integration
gaps that G1/G2 depend on is deferred past Phase B M4:

- **(a)** Name the CARLA LiDAR frame to the kit's `velodyne_top` (or publish the
  `base_link -> ray_cast__` TF) — CARLA-fork change.
- **(b)** Either a single-LiDAR preprocessing/concatenation config (a forced
  `autoware_launch` overlay) or spawning 3 CARLA LiDARs (top/left/right) to match the
  `awsim_labs_sensor_kit` concatenator's expectations.
- **(c)** Fix the GNSS host-side centimetres/metres units bug in the extension's
  transform-to-pose path (Root-caused blockers, item 3).
- **(d)** Bring-up ordering, or dropping `autoware_carla_interface` outright for the
  native-DDS path, so it cannot reload the world out from under a live ego (Root-caused
  blockers, item 4).

Closing (a)-(d) is what would let the localization chain — and therefore G1 and G2 — run
against the fixed gate scripts above.

## Non-goals / Deferred

- G4 package gate (`make package` + drop-in) — out of Phase B scope (user decision).
- Town10 + lanelet2 auto-generation — future work; no CARLA(.xodr) -> lanelet2 reverse
  converter exists (`docs/nishishinjuku-map.md`).
- NuRec and VisionPilot — explicitly EXCLUDED from Phase B everywhere (no tasks, no scripts,
  no deps).

## M4 verdict: FAIL (G1, G2, G3-control) / PASS (G3-LiDAR)

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
committed scripts measure correctly, and they reproduce the same FAILs. On the M4 contract
as scoped, **M4 is a FAIL**, root-caused to the sensing-integration gaps listed in
[Deferred integration work](#deferred-integration-work-future).
