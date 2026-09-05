# Nishi-Shinjuku map assets

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

Town10 + lanelet2 auto-generation (CARLA .xodr -> lanelet2) is out of scope. No
CARLA(.xodr)->lanelet2 reverse converter exists: `autoware_lanelet2_to_opendrive` only
converts Lanelet2 -> OpenDRIVE, not the other direction. The reusable scaffolding for a
future reverse converter is that same package's tag-mapping tables, MGRS projection
utilities, and the `analyze` QC harness.

## Ego geometry reconciliation (live 2026-07-21)

> Historical record from the out-of-tree extension/runner era (`runner/spawn.py`,
> `verify_editor_artifact.sh`); both are gone (see `docs/ue58/`). Kept for the ego
> geometry findings below (spawn point, vehicle blueprint, base_link placement),
> which are still accurate.

Live measurement on `NishishinjukuMap` (headless `UnrealEditor ... -game -nosound`, CARLA
0.10 / UE5 Chaos, the fork's integration branch; Python API only, no
`-ros2` — a stale editor `.so` is acceptable for a non-ROS2 measurement, so
`verify_editor_artifact.sh` was deliberately skipped). Port 2000 came up in ~16 s; the map
exposes exactly 1 spawn point at `loc(-278.39, 220.54, 0.00) yaw -34.98`.

### Ego blueprint (resolves the open question of which vehicle to spawn)

- **`vehicle.lincoln.mkz`** — the Lincoln MKZ the ported `AutowareSteeringCompensation.h`
  LERP table was measured on. The CARLA 0.10 blueprint library drops the 0.9-era
  year suffix, so `vehicle.lincoln.mkz_2020` **does not exist** in this build
  (verified live: 17 vehicle blueprints enumerated; only `vehicle.lincoln.mkz` is the MKZ).
  Finding the `_2020` id raises, which was the initial live spawn failure; `runner/spawn.py`
  now uses `vehicle.lincoln.mkz`. Front wheels are physics-control indices 0/1
  (`axle_type` 1, steered, `max_steer_angle` 70°), rear 2/3 (`axle_type` 2, unsteered);
  `wheel_radius` 0.355 m; `center_of_mass` (0.15, 0.0, 0.35) m.

### Wheelbase reconcile (open question: reconciling measured vs assumed wheelbase) — method unavailable in 0.10

- The planned measurement (physics-control wheel positions ÷ 100 cm→m) **cannot run
  on CARLA 0.10 Chaos**: every wheel's `location`, `offset` and `old_location` report
  `(0, 0, 0)`, and there is no `get_wheel_position` client API (wheel geometry lives in the
  vehicle's binary skeletal-mesh sockets). This is why a measured wheelbase was never
  available on this build.
- **Corroborating geometry (live):** bounding box `extent (2.446, 0.918, 0.762)` →
  full length **4.892 m**. The real Lincoln MKZ wheelbase is ~**2.85 m** (spec open-item
  value); 2.85 m + ~1.0 m front + ~1.05 m rear overhang ≈ 4.9 m is fully consistent with the
  measured length, but the length alone does not isolate the wheelbase.
- **RESOLVED by the G1 NDT gate (2026-07-23):** the deferred "coarser question — whether to
  publish base_link AT the CARLA vehicle origin, zeroing the +wheelbase/2 shift entirely" is
  now answered **yes**. The live G1 run localized but tracked a steady **1.44 m ≈ wheelbase/2**
  error along the ego heading; it root-caused to exactly the `+wheelbase/2`
  `base_link_to_vehicle_center` shift, which Autoware's TF (rebuilt from the same kit yamls,
  base_link→sensor with no vehicle term) never compensated, so NDT back-solved base_link
  wheelbase/2 ahead of the CARLA vehicle origin that the gate reads as ground truth. The shift
  (and the now-moot wheelbase reconcile, `SAMPLE_VEHICLE_WHEELBASE`, and `ego_wheelbase()`)
  were **removed**: `carla_attach_location` now returns the composed base_link pose verbatim,
  pinning base_link to the CARLA vehicle origin. This makes the NDT↔GT error cancel to ~0
  regardless of where the vehicle origin sits on the chassis, so the un-measurable wheelbase
  no longer matters for G1. See `docs/e2e-report.md` issue #6 for the full geometry.

### Attach math + Z-origin (gross-error gate) — PASS

- Top LiDAR spawned attached to the ego at its kit-composed pose. **NOTE (superseded by the
  G1 fix above):** this run predates the shift removal, so it attached at `vehicle centre
(2.295, 0, 2.0)` (= 0.9 + 2.79/2). The current runner attaches at the composed base_link
  pose `(0.9, 0, 2.0)` with NO shift; the historical numbers below are kept as the live
  translation/Z evidence, but the horizontal offset is now 0.9 m, not 2.295 m.
  TRANSLATION/Z live world transforms (original identity-attach run): ego
  `(-278.390, 220.540, -0.052)`, lidar `(-276.510, 219.224, 1.948)` → lidar−ego delta
  `(1.880, -1.316, 2.000)`, **horizontal distance 2.295 m** (= 0.9 + 2.79/2) and **dz
  2.000 m** — matched the composition-with-shift exactly, no gross Z error. (That run attached
  at identity rotation, so lidar yaw then equalled the ego's; mount rotations are now APPLIED —
  see the next subsection, which re-verifies the attach on the current build.)
- Z pass-through assumption **validated**: ego `bbox.location.z 0.763 ≈ extent.z 0.762`, so
  the CARLA vehicle origin sits at the body bottom (ground = base_link height). No Z
  correction constant is needed (the composed base_link Z is used verbatim at attach).

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

## Phase 3 use

`scripts/e2e/run_gates.sh` and the gate scripts it drives take this map's origin as
`--map-origin "81655.73,50137.43,42.49998"` — the same converter offset recorded above
(`NISHISHINJUKU_ORIGIN` in `scripts/e2e/map_frame.py`). Omit `--map-origin` entirely for a
Local-projector map such as Town10HD.

## In-tree flow (Phase 3)

The full sequence three live cells were driven with. Gate results and every
citation are in [`docs/ue58/phase3-nishishinjuku.md`](ue58/phase3-nishishinjuku.md).

### The two umap states

`NishishinjukuMap.umap` is CC BY-NC content: it lives only in the per-worktree
`Content/`, is never committed, and both states of it are kept as local backups.

| State    | `sha256` (first 8) | Meaning                                                                                                               |
| -------- | ------------------ | --------------------------------------------------------------------------------------------------------------------- |
| pristine | `7bb76f1e`         | `AutowareWorldSettings.MgrsDataAsset` soft pointer unset — the state the editor's `RepairWorldSettings` leaves behind |
| wired    | `24ca4ea4`         | `DA_MGRS_Shinjuku` assigned to that soft pointer                                                                      |

Back up the pristine file before wiring, and treat that backup as read-only —
it is the only copy of a state the editor cannot restore:

```bash
UMAP=<CARLA>/Unreal/CarlaUnreal/Content/Carla/Maps/NishishinjukuMap.umap
sha256sum "$UMAP" | tee ~/ue58-logs/p3/00-umap-pristine.sha256
cp -n "$UMAP" ~/ue58-logs/p3/NishishinjukuMap.umap.pristine
```

Compare hashes directly when switching states — do not diff a one-line
`sha256sum` against a multi-line recorded file, which never matches.

### Wire the level's MGRS asset (the `wired` state)

```bash
export UE_ROOT=~/src/UnrealEngine CARLA_UE58=<CARLA>
bash scripts/nishishinjuku/run_wire_mgrs_asset.sh inspect ~/ue58-logs/p3/08-wire-inspect.log
bash scripts/nishishinjuku/run_wire_mgrs_asset.sh apply   ~/ue58-logs/p3/09-wire-apply.log
```

`inspect` prints the asset's offset and the level's current soft pointer without
changing anything; `apply` assigns and saves. Both grep their own `RESULT:` line
out of the editor log and fail if it is absent. The asset reads
`x=81655.730000 y=50137.430000 z=42.499980`, grid `54SUE` — the same converter
offset as `--map-origin`.

### Derive on-lane poses (offline, no simulator)

```bash
PYTHONPATH=. python -m scripts.e2e.lanelet_pose \
  --osm ~/autoware_map/nishishinjuku/lanelet2_map.osm \
  --map-origin 81655.73,50137.43,42.49998 \
  --lanelet 255 --s 7.477
```

Use the `=` form for a negative coordinate (`--nearest-to-carla=-278.39,220.54`);
`argparse` rejects the space form. The tool emits map-frame and CARLA-frame poses
plus ready-made `--goal` / `--spawn-pose` strings. **Z is not derived offline** —
the CARLA ground height must come from a live `cast_ray`, and the spawn Z used in
Phase 3 is that height plus 0.3 m.

The Phase 3 poses, cross-checked live against CARLA's OpenDRIVE waypoints to
0.018 m / 0.09° (spawn) and 0.036 m / 0.04° (goal):

```bash
SPAWN_POSE="-278.383,220.550,-0.975,-33.780"
GOAL="-84.114,117.602,-10.442"
ORIGIN="81655.73,50137.43,42.49998"
```

### Run a cell and measure it

From CARLA's `PythonAPI/examples/av_stacks/autoware`:

```bash
./run/run_carla_autoware.sh --mode classical --stack docker --server editor \
  --town NishishinjukuMap --map-path ~/autoware_map/nishishinjuku \
  --map-origin "$ORIGIN" --spawn-pose "$SPAWN_POSE" --goal "$GOAL" \
  --log-dir "$CELL" 2>&1 | tee "$CELL.log"
```

Then, from this repository, as soon as `autonomous mode engaged` appears in the
runner's own stdout (**not** in `automation.log`, which does not carry it):

```bash
CARLA_PYTHON=~/carla-venv/bin/python bash scripts/e2e/run_gates.sh \
  --log-dir "$CELL" --goal "$GOAL" --map-origin "$ORIGIN" \
  --lidar-hz 10 --g2-window 420
bash scripts/e2e/aw_exec.sh "$CELL" 42 \
  "timeout 20 ros2 topic echo --once /api/routing/state"
```

Add `--image ghcr.io/autowarefoundation/autoware:universe-cuda-humble` to the
runner for a Humble cell. Stop any `ros2cli` daemon from another ROS distro
first: the container runs `--network host`, and a stale daemon on the same domain
makes the pre-engage gate report a localisation failure while the topic publishes
normally.

At teardown, copy the engine log into the cell directory — UE rotates
`Saved/Logs/CarlaUnreal.log` on the next launch, so a citation of that path rots
immediately. Re-grep after refreshing any log copy: a copy taken while the
process is still flushing is short by roughly the teardown block.

### Restore

```bash
cp ~/ue58-logs/p3/NishishinjukuMap.umap.wired "$UMAP"   # or .pristine
sha256sum "$UMAP"
```
