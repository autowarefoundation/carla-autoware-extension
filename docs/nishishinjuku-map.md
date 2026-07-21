# Nishi-Shinjuku map assets (Phase B)

E2E gates G1-G3 run on the AWSIM v2.0.0 Nishi-Shinjuku map.

## Autoware side (`~/autoware_map/nishishinjuku`, not committed)

- Source: AWSIM v2.0.0 `Shinjuku-Map.zip`, 129,585,415 bytes,
  <https://github.com/autowarefoundation/AWSIM/releases/download/v2.0.0/Shinjuku-Map.zip>
- Files: lanelet2_map.osm, pointcloud_map.pcd, pointcloud_map_metadata.yaml, map_projector_info.yaml
- Projector: MGRS, grid 54SUE, vertical_datum WGS84 (triangulated across converter conf,
  fixture lanelet2 mgrs_code, DA_MGRS_Shinjuku UE asset, AWSIM docs).
- License: CC BY-NC 4.0 (LICENSE shipped in the zip; data referenced in place, never committed).

## CARLA side (`Content/`, per-worktree, git-ignored, not committed)

- Prebuilt AWSIM->UE5 content pack + converter OpenDRIVE (`NishishinjukuMap.xodr`, ~6.06 MB).
- MGRS 54SUE; converter offset x=81655.73 y=50137.43 z=42.49998
  (autoware_lanelet2_to_opendrive conf/map/nishishinjuku.yaml).

## Non-goal (future work)

Town10 + lanelet2 auto-generation (CARLA .xodr -> lanelet2) is out of Phase B scope. No
CARLA(.xodr)->lanelet2 reverse converter exists: `autoware_lanelet2_to_opendrive` only
converts Lanelet2 -> OpenDRIVE, not the other direction. The reusable scaffolding for a
future reverse converter is that same package's tag-mapping tables, MGRS projection
utilities, and the `analyze` QC harness.

## Phase B ego reconciliation (live 2026-07-21)

Live measurement on `NishishinjukuMap` (headless `UnrealEditor ... -game -nosound`, CARLA
0.10 / UE5 Chaos, integration branch `feat/autoware-seminative-phase-b`; Python API only, no
`-ros2` — a stale editor `.so` is acceptable for a non-ROS2 measurement, so
`verify_editor_artifact.sh` was deliberately skipped). Port 2000 came up in ~16 s; the map
exposes exactly 1 spawn point at `loc(-278.39, 220.54, 0.00) yaw -34.98`.

### Ego blueprint (resolves the open question of which vehicle to spawn)

- **`vehicle.lincoln.mkz`** — the Lincoln MKZ the ported `AutowareSteeringCompensation.h`
  LERP table was measured on. The CARLA 0.10 blueprint library drops the 0.9-era
  year suffix, so `vehicle.lincoln.mkz_2020` **does not exist** in this build
  (verified live: 17 vehicle blueprints enumerated; only `vehicle.lincoln.mkz` is the MKZ).
  Finding the `_2020` id raises, which was the initial 4b spawn failure; `runner/spawn.py`
  now uses `vehicle.lincoln.mkz`. Front wheels are physics-control indices 0/1
  (`axle_type` 1, steered, `max_steer_angle` 70°), rear 2/3 (`axle_type` 2, unsteered);
  `wheel_radius` 0.355 m; `center_of_mass` (0.15, 0.0, 0.35) m.

### Wheelbase reconcile (open question: reconciling measured vs assumed wheelbase) — method unavailable in 0.10

- The planned measurement (physics-control wheel positions ÷ 100 cm→m) **cannot run
  on CARLA 0.10 Chaos**: every wheel's `location`, `offset` and `old_location` report
  `(0, 0, 0)`, and there is no `get_wheel_position` client API (wheel geometry lives in the
  vehicle's binary skeletal-mesh sockets). `runner.spawn.ego_wheelbase()` therefore returns
  `0.0` here — documented in-code as "unavailable, fall back to bbox / sample_vehicle".
- **Corroborating geometry (live):** bounding box `extent (2.446, 0.918, 0.762)` →
  full length **4.892 m**. The real Lincoln MKZ wheelbase is ~**2.85 m** (spec open-item
  value); 2.85 m + ~1.0 m front + ~1.05 m rear overhang ≈ 4.9 m is fully consistent with the
  measured length, but the length alone does not isolate the wheelbase.
- **Reconcile decision:** keep `SAMPLE_VEHICLE_WHEELBASE = 2.79`
  (`base_link_to_vehicle_center` shift = +1.395 m). Nominal delta vs the ~2.85 m real MKZ is
  **0.06 m**, i.e. a per-sensor forward-offset impact of **delta/2 = 0.03 m** — under the
  0.15 m STOP threshold. Concern: the exact delta is not directly measurable in 0.10, and the
  coarser question (whether the extension publishes base_link AT the CARLA vehicle origin,
  which would zero the +wheelbase/2 shift entirely) is a placement-convention item deferred
  to the G1 NDT gate.

### Attach math + Z-origin (gross-error gate) — PASS

- Top LiDAR spawned attached to the ego at its kit-composed pose
  (`velodyne_top_base_link` → base_link (0.9, 0, 2.0) → vehicle centre (2.295, 0, 2.0)).
  TRANSLATION/Z live world transforms (original identity-attach run): ego
  `(-278.390, 220.540, -0.052)`, lidar `(-276.510, 219.224, 1.948)` → lidar−ego delta
  `(1.880, -1.316, 2.000)`, **horizontal distance 2.295 m** (= 0.9 + 2.79/2) and **dz
  2.000 m** — matches the composition exactly, no gross Z error. (That run attached at
  identity rotation, so lidar yaw then equalled the ego's; mount rotations are now APPLIED —
  see the next subsection, which re-verifies the attach on the current build.)
- Z pass-through assumption **validated**: ego `bbox.location.z 0.763 ≈ extent.z 0.762`, so
  the CARLA vehicle origin sits at the body bottom (ground = base_link height). No Z
  correction constant is needed in `base_link_to_vehicle_center`.

### Sensor mount rotations — now APPLIED (live re-verified 2026-07-21)

Autoware owns the TF tree: the runner calls `world.set_publish_tf(False)` before
spawning, and Autoware generates each sensor's TF from the SAME committed kit yamls (which
carry large mounts — `velodyne_top` yaw 1.575 rad ≈ 90°, `tamagawa/imu_link` roll/yaw π).
The physical CARLA sensor frame must therefore be attached WITH those rotations, or the top
cloud arrives ~90°-rotated in base_link (NDT/G1 dead on arrival) and the IMU axes flip
(ekf/G2 corrupted). `runner.spawn` now applies them.

- **Convention (`runner.kit.ros_rpy_to_carla_rotation`):** compose the full base_link→sensor
  rotation matrix across BOTH yamls in the ROS frame (`R = R(base_link→kit) · R(kit→sensor)`),
  extract the composed ROS rpy, then convert ONCE to a CARLA/UE Rotator. CARLA/UE is
  left-handed (Y right) vs ROS right-handed (Y left), related by the Y-flip `M = diag(1,-1,1)`;
  conjugating by M plus UE's left-handed Rotator sign convention nets a componentwise mapping
  **roll:+, pitch:−, yaw:−** (identical to carla-ros-bridge's `carla_rotation_to_RPY` inverse,
  consistent with the quaternion pin `carla_quat_to_mgrs = (-qx, qy, -qz, qw)`, an
  involution derived via `R(θ,n) → R(θ,-Mn)`). NEVER map the two yamls' rpy entries
  componentwise before composing — extrinsic `Rz·Ry·Rx` does not commute.
- **Composed CARLA mounts (from the committed yamls):** top LiDAR
  `(roll 0.860°, pitch −0.054°, yaw −88.156°)` — note the composed yaw −88.156° is the raw kit
  yaw −90.240° MINUS the base→kit yaw −2.086°, i.e. the chain is composed, not read from one
  yaml. IMU `(roll −179.943°, pitch 0.859°, yaw −177.914°)` — a ~180° flip about the mount.
- **Live re-verification (headless `UnrealEditor … CarlaUnreal.uproject -game -RenderOffScreen
-nosound`, API-only so a stale editor `.so` is acceptable; `ROS_DOMAIN_ID=0`; default project
  map `Town10HD_Opt`, spawn point yaw −89.609°; PID-file teardown via SIGINT, port 2000 released
  cleanly):** the top LiDAR and IMU spawned via the REAL `runner.spawn` native-attribute path
  (`native_attr_path=True` — this build already carries the native sensor attributes, so the attribute-injection fallback did not fire). For BOTH
  sensors the child WORLD transform equalled `ego_world ∘ local_attach` to a **max 4×4 matrix
  element diff of 3e-6** (PASS < 1e-3). Top-LiDAR **world_yaw − ego_yaw = −88.156°** (equals the
  composed local yaw, and crucially NOT 0° as an identity attach would give); IMU
  **world_yaw − ego_yaw = −177.914°** with world roll −179.943° (the mount flip is applied).
  On `NishishinjukuMap` (ego yaw −34.98°) this offset puts the top cloud at world yaw ≈
  −123.14°; the offset is map-independent.

### Teardown note

The editor was stopped by SIGTERM to the recorded PID (never `pkill`/`pgrep -f`). A
shutdown-time SIGSEGV (Chaos teardown) core-dumps _after_ the measurement has completed and
printed all results — benign to the measurement, but recorded as a live-run watch item
(distinct from the boot-time "Signal 11 caught" UnrealTraceServer artifact).
