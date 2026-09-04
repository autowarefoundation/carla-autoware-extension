# PR candidates for `carla-simulator/carla` `ue58-dev` (from Phases 0-1)

Each entry becomes one fork-staged draft PR (`youtalk/carla`, base `ue58-dev`)
and then one upstream PR, per the spec's "one PR = one defect or one generality
gap, with live evidence" rule.

Status legend: `evidence` (reproduced live, no fix written yet), `fix-local`,
`fork-pr`, `upstream-pr`, `retired` (closed by upstream, no PR needed).

Evidence paths are relative to `~/ue58-logs/` unless they name a source file.
Line numbers are against `upstream/ue58-dev` at
`5f58df57998030cb602a0fc588db6cc5b8a23988`. Paths under
`PythonAPI/examples/av_stacks/autoware/` are abbreviated `av_stacks/`. A few
rows cite `task-N-report.md`: those are the SDD task reports under
`~/src/carla/.superpowers/sdd/2026-09-03-autoware-in-tree-phase0-phase1-plan/`,
cited where the verbatim output was captured in the report rather than written
to a log file.

Rows are ordered by value, highest first. The `Ledger` column carries the id
used in the controller ledger and the per-task reports, so cross-references
survive the reordering. 16 live candidates and 1 retired.

| #   | Ledger | Title                                                                                                                                                                                                                                                                                              | Upstream file(s)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Evidence                                                                                                                                                                                                                                                                | Status                                                                                                                      |
| --- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 1   | 12     | The README's only documented goal is 19.4 m off the nearest lane centreline, so a verbatim run comes up healthy and then silently refuses to drive                                                                                                                                                 | `av_stacks/README.md:195`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | `run1/autoware.log:1723, 1725-1726, 1730-1731`, `23-live-run.log`, `28-goal-xcheck.txt`, `24-metrics.txt`                                                                                                                                                               | evidence                                                                                                                    |
| 2   | 15     | The shipped Town10HD lanelet2 map references the shared centre linestring of each opposing-lane pair un-inverted from both lanelets, so 17 of 160 road lanelets have their bounds ordered against travel; roughly one spawn point in five starts inside one                                        | `av_stacks/map_tools/maps/Town10HD/lanelet2_map.osm` (tracked in-repo, 11.3 MB); producer to be determined before filing                                                                                                                                                                                                                                                                                                                                                                                   | `31-lanelet-bound-orientation.txt`, `run3/autoware.log:1141, 1172, 1173, 1185`, `run4/autoware.log:1099-1106`, `29-groundtruth.txt`, `33-run4-route-selection.txt`, plus the re-derivation in this file                                                                 | evidence                                                                                                                    |
| 3   | 5      | `fixup_centerpoint_layout()` returns silently when the model directory is absent, so the one case that matters produces no warning and defers the consequence to a hard ONNX-load failure inside a much later live run                                                                             | `av_stacks/install/install_autoware.sh:388-389`                                                                                                                                                                                                                                                                                                                                                                                                                                                            | `21-autoware-docker.log` (no centerpoint section emitted at all), `20-autoware-check.log:30`                                                                                                                                                                            | evidence                                                                                                                    |
| 4   | 4      | `install_autoware.sh --check` presents as a prerequisite report but probes neither the 64 MB UDP socket buffers nor the NVIDIA container runtime, both of which the README documents as required                                                                                                   | `av_stacks/install/install_autoware.sh:222-311` (`do_check`); `rmem_max` appears only as heredoc prose at `:633`                                                                                                                                                                                                                                                                                                                                                                                           | `20-autoware-check.log`                                                                                                                                                                                                                                                 | evidence                                                                                                                    |
| 5   | 6      | Two of the four expected centerpoint filenames the installer lists (`pts_voxel_encoder.onnx`, `pts_backbone_neck_head.onnx`) are bare names, stale against the `_centerpoint`-suffixed names the shipped launcher hardcodes; the other two entries already carry their variant suffix or need none | `av_stacks/install/install_autoware.sh:85-90` (`CENTERPOINT_FLAT_FILES`)                                                                                                                                                                                                                                                                                                                                                                                                                                   | `20-autoware-check.log:30`, plus in-image `perception.launch.xml:176-183` and `e2e_simulator.launch.xml:8` from digest `sha256:9c7d51a8...`                                                                                                                             | evidence                                                                                                                    |
| 6   | 2      | The "do not use `-rmw=cyclonedds` on the simulator" warning is stale: `b9c33737a` fixed the fragmented-receive bug, and a full CycloneDDS-on-simulator run reaches ARRIVED                                                                                                                         | `av_stacks/README.md:431-439`; `av_stacks/run/run_carla_autoware.sh:23-24, 81, 121-122, 608-609`                                                                                                                                                                                                                                                                                                                                                                                                           | `25-cyclonedds-sim.log`, `25c/25d-metrics-cyclonedds-block1/2.txt`, `25e-final-state-cyclonedds.txt`, `run2/carla_server.log:523`, `run2/autoware.log:1105`, `26-probes.txt` PROBE2                                                                                     | evidence                                                                                                                    |
| 7   | 17     | The simulator process exits with SIGSEGV on teardown SIGTERM, on every live run and under both middlewares                                                                                                                                                                                         | not localized; entry point is the editor `-game` shutdown path                                                                                                                                                                                                                                                                                                                                                                                                                                             | `23-live-run.log`, `27-live-run-goal2.log`, `28-live-run-clean-spawn.log` (fastdds) and `25-cyclonedds-sim.log` (cyclonedds), each ending `run/run_carla_autoware.sh: line 314: <pgid> Segmentation fault (core dumped)`; also `23-live-run.attempt1-wheelmismatch.log` | evidence                                                                                                                    |
| 8   | 1      | MGRS offset is content-only: no runtime fallback exists when a level has no `UMgrsDataAsset`, and the Autoware game mode's no-asset branch also skips `ParseOpenDrive()` and `StoreSpawnPoints()`                                                                                                  | `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Sensors/AutowareGnssSensor.cpp:110-136`; `.../Autoware/Game/AutowareWorldSettings.h:28-29`; `.../Autoware/Game/AutowareGameModeBase.cpp:40-43` (the skipped `Super::LoadGeoReference()` is `.../Game/CarlaGameModeBase.cpp:232-240`, which is where `ParseOpenDrive()` and `StoreSpawnPoints()` run); `.../Actor/ActorBlueprintFunctionLibrary.cpp:1485-1490` and `:2380`; `LibCarla/source/carla/ros2/publishers/AutowareGNSSPublisher.cpp:60-62` | `26-probes.txt` PROBE1, `run2/carla_server.log:3289`                                                                                                                                                                                                                    | evidence (blocked on a Phase 3 live need; Town10HD is `projector_type: Local`, so Phase 1 never exercised it)               |
| 9   | 9      | The ROS 2 smoke suite hardcodes RPC port 3654 with no override, so it cannot run against the simulator port the Autoware flow uses                                                                                                                                                                 | `PythonAPI/test/smoke/__init__.py:23`                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | `task-6-report.md:11-15` (5 x `RuntimeError: Connection refused` against a `-carla-rpc-port=2000` simulator); `14-smoke-ros2.log` / `smoke.out` (`Ran 5 tests in 131.546s` / `OK` once relaunched on 3654)                                                              | evidence                                                                                                                    |
| 10  | 7      | `autoware_demo.py` hardcodes `client.set_timeout(60.0)` with no override; a cold-start `get_world()` measured 65.9 s on this machine and the demo failed with `RuntimeError: std::exception`                                                                                                       | `PythonAPI/examples/autoware_demo.py:758`                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | `task-5-report.md:85-110` (traceback at `autoware_demo.py:559`, then a 180 s-timeout probe reporting `get_world OK in 65.9s`)                                                                                                                                           | evidence                                                                                                                    |
| 11  | 8      | `autoware_demo.py` ignores `SIGINT` (blocked in `futex_do_wait` inside the LibCarla tick), so an orphaned client needs `SIGKILL`; the tick loop should be interruptible                                                                                                                            | `PythonAPI/examples/autoware_demo.py` (tick loop)                                                                                                                                                                                                                                                                                                                                                                                                                                                          | `task-5-report.md:354-362` (two `SIGINT`s ~25 s apart ignored; the simulator itself exited cleanly on the same signal)                                                                                                                                                  | evidence                                                                                                                    |
| 12  | 13     | The run script's preflight checks that `carla` imports but never which build it is; a wheel from a foreign worktree aborted `load_town` with `std::bad_array_new_length` after a 15-minute setup                                                                                                   | `av_stacks/run/run_carla_autoware.sh:739-751`                                                                                                                                                                                                                                                                                                                                                                                                                                                              | `23-live-run.attempt1-wheelmismatch.log`                                                                                                                                                                                                                                | evidence                                                                                                                    |
| 13  | 11     | No `--server-args` passthrough to the editor fallback, and `-nosound` / `-log` are not defaulted, so the reproduction cannot be given the flags Phase 0 proved working without editing the script                                                                                                  | `av_stacks/run/run_carla_autoware.sh:815-816` (`SERVER_FLAGS`, defined at `:815` and appended to at `:816`)                                                                                                                                                                                                                                                                                                                                                                                                | `22-dry-run.log`, `11-launch-cmd.txt`                                                                                                                                                                                                                                   | evidence                                                                                                                    |
| 14  | 14     | CARLA's native ROS 2 PointCloud2 publisher sets `is_dense = false`, which Autoware's cloud validator warns on and says will become a hard error                                                                                                                                                    | `LibCarla/source/carla/ros2/publishers/CarlaPointCloudPublisher.cpp:107-110`                                                                                                                                                                                                                                                                                                                                                                                                                               | `run1/autoware.log` (99 x `[sensing.lidar.top.crop_box_filter_self]: Invalid PointCloud: is_dense is false`), and it recurs throughout `run4/autoware.log`                                                                                                              | evidence (scope corrected, see note below)                                                                                  |
| 15  | 10     | `run_carla_autoware.sh` never forwards `DLSS_SDK` to the editor fallback; only `FASTRTPS_DEFAULT_PROFILES_FILE` or `CYCLONEDDS_URI` enters `SIM_ENV`                                                                                                                                               | `av_stacks/run/run_carla_autoware.sh:803-805` (`SIM_ENV` construction), consumed at `:819` and `:821`                                                                                                                                                                                                                                                                                                                                                                                                      | `22-dry-run.log` (grep for `DLSS_SDK` returns 0)                                                                                                                                                                                                                        | evidence (not a blocker: no DLSS features under `-RenderOffScreen`, and an exported value is inherited by `setsid bash -c`) |
| 16  | 16     | Transient NDT scan-matching degradation fires 11 `EMERGENCY_STOP` events in an otherwise clean run; the ego drives through them, but the cause is undiagnosed                                                                                                                                      | not localized; surfaced via `/autoware/localization/scan_matching_status`                                                                                                                                                                                                                                                                                                                                                                                                                                  | `run4/autoware.log:1236-1242` and the blocks at `:1266`, `:1296`, `:1378`; 11 operated / 11 cancelled                                                                                                                                                                   | evidence (needs diagnosis before filing; may be an Autoware-side tuning issue rather than a CARLA defect)                   |
| 17  | 3      | `Map::GenerateChunkedMesh` empty-mesh guard (port of fork `a203b7ce4`)                                                                                                                                                                                                                             | `LibCarla/source/carla/road/Map.cpp:1323, 1330, 1344, 1361`                                                                                                                                                                                                                                                                                                                                                                                                                                                | `26-probes.txt` PROBE3                                                                                                                                                                                                                                                  | **retired** - already upstream, see below                                                                                   |

## Notes on the top two

### 1 - the README goal (`README.md:195`)

The PR should replace the goal and say how it was chosen, because "pick another
goal" is not actionable on its own.

`--goal "80.0,-16.5,90"` resolves to CARLA waypoint `(99.441, -16.335)` on a
3.50 m lane, a lateral offset of **19.44 m from the lane centreline** - about
**17.7 m from the lane edge**. The heading is fine (yaw error -0.15 deg).
`autoware_mission_planner` answered `Goal's footprint exceeds lane! / Goal is
not valid!` (`run1/autoware.log:1725-1726`), no route was published,
`/api/routing/state` stayed `1` (UNSET), and `change_to_autonomous` was refused
12 times while the ego sat at 0.00 m/s, 77.03 m away.

**Pre-empting "isn't this just a sign error?"** It is not.

- The y-negation between CARLA and the lanelet2 map is intentional and
  documented at `map_tools/generate_lanelet2_map.py:14-19` ("OpenDRIVE is
  right-handed while CARLA is left-handed ... Do NOT flip the converter
  output").
- The convention is exercised and correct in practice: GATE1, which compares
  CARLA ground truth against `/localization/kinematic_state` through that same
  transform, agreed to 0.02-0.05 m in all three engaging runs.
- Flipping the sign does not rescue the goal anyway. Measured against the
  converted lanelet2 map, CARLA `(80.0, +16.5)` lands 0.52 m from lanelet
  `18191`'s centreline - but that centreline's heading is **179.84 deg**, not
  the documented 90. The mirrored point sits on a road running the wrong way
  for the documented yaw.

Two derived, cross-checked replacements are available, both computed as the
**arclength midpoint of a road lanelet's centreline, with the heading taken as
the centreline tangent at that point**, then cross-checked against CARLA's own
`get_waypoint()` for lateral offset and yaw error:

| Goal (CARLA `x,y,yaw`) | Lanelet                         | Lateral offset | Yaw error | Clearance to lanelet ends | Result                                 |
| ---------------------- | ------------------------------- | -------------- | --------- | ------------------------- | -------------------------------------- |
| `98.90,68.73,90.4`     | `31570`, 29.87 m, 3.50 m wide   | 0.00 m         | 0.01 deg  | 14.7 m                    | route published, 8 lanelets / ~153.5 m |
| `-1.16,28.37,0.16`     | `16406`, 55.13 m, dead straight | 0.19 m         | 0.00 deg  | 27.6 m                    | full drive to ARRIVED                  |

`-1.16,28.37,0.16` paired with `--spawn-index 24` is the one that reaches
ARRIVED, and is the recommended README replacement. Method and per-segment
numbers: `33-run4-route-selection.txt`, `34-run4-goal-xcheck.txt`,
`28-goal-xcheck.txt`.

**This candidate is entangled with candidate 2, and the PR should say so.**
Run 1's rejected candidate sequence (`run1/autoware.log:1723`) is
`16406 34932 10868 22411 11685 36849 13373 26524 13571 13721 18842 19425 9913
14515`, and `10868` is one of the 17 malformed lanelets. Fixing only the README
would very likely have produced a documented path that hits the map defect
instead. The two are separable as code changes; they are not separable as a
user-facing fix.

### 2 - the Town10HD lanelet2 map

**Lead with the mechanism, not the symptom.** "17 lanelets look reversed"
invites the reply "maybe Autoware is mishandling them". The structural evidence
rules that out:

- Of 160 road lanelets, **17 ways are referenced as the `left` bound by exactly
  two different road lanelets each** - the shared centre linestring of an
  opposing-lane pair. No way is shared as a `right` bound at all (0 cases).
- In **17 of 17** such pairs, exactly one member is in the malformed set, and
  the union of those single members is exactly the 17 malformed lanelets.
- The file contains **zero** inverted member references (`grep -c 'ref="-"'` on
  `lanelet2_map.osm` returns 0).

So the converter emits the shared centre linestring once and references it
un-inverted from both opposing lanelets. One member of each pair therefore has
its bounds ordered against its own direction of travel. That is a defect in the
artefact CARLA ships, not in how Autoware reads it.

Downstream symptom chain from run 3, all pre-engage. Counts are re-derived from
`run3/autoware.log` for this file, because the per-node breakdown in the task
report was wrong:

| Message                                                               | Count         | Emitting node(s)                                                                   |
| --------------------------------------------------------------------- | ------------- | ---------------------------------------------------------------------------------- |
| `Backward path is NOT supported, just returning input path`           | **377 total** | `behavior_velocity_planner` 171, `elastic_band_smoother` 103, `path_optimizer` 103 |
| `Caution! Invalid Trajectory published.`                              | 166           | `planning_validator`                                                               |
| `planning trajectory is too far from ego in longitudinal direction!!` | 166           | `planning_validator`                                                               |
| `EMERGENCY_STOP is operated.`                                         | 171, latched  | `mrm_handler`                                                                      |
| `Emergency!`                                                          | 427           | `control.vehicle_cmd_gate`                                                         |

The controlled comparison is the evidence a maintainer will want. Same map,
same stack, same image; the only difference is which lanelet the ego started
inside:

| Signature                                    | run 3 (started inside malformed `12236`)                                                                                 | run 4 (started inside clean `5013`)                 |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------- |
| `Backward path is NOT supported`             | 377                                                                                                                      | 0                                                   |
| `Invalid Trajectory published`               | 166                                                                                                                      | 0                                                   |
| `too far from ego in longitudinal direction` | 166                                                                                                                      | 0                                                   |
| `EMERGENCY_STOP is operated`                 | 171, latched                                                                                                             | 11, all self-cancelled                              |
| Outcome                                      | trajectory pinned 118 m behind the ego, running west with negative velocity; never turned; stopped 17.75 m from the goal | drove the full 7-lanelet route, both turns, ARRIVED |

#### Blast radius: roughly one spawn point in five

Projecting each of the 155 CARLA spawn points into map coordinates and testing
it against the orientation-corrected polygon of every road lanelet gives
**30 of 155 spawns (19.4 %)** inside at least one malformed lanelet. Assigning
each spawn instead to the lanelet whose orientation-corrected centreline is
nearest gives **31 of 155 (20.0 %)**. Both methods agree on "about one in five".

**Do not use the 3.9 % figure that appears in the task reports and the
controller ledger.** It came from `~/ue58-logs/match_spawns.py`, which applies a
40-degree heading gate when matching a spawn to a lanelet. A malformed
lanelet's derived tangent is 180 degrees off, so it can never pass that gate,
and the script silently reassigns the spawn to a neighbouring lanelet. Example:
spawn 8 sits 0.06 m from `4789`'s orientation-corrected centreline and several
metres from `4801`, yet is reported as `4801`. The gate that was meant to
improve matching quality systematically excluded exactly the lanelets being
counted.

Reality check that favours the higher figure: run 3's own start pose is 1.46 m
from spawn index 129, which lies inside `12236`, and Autoware did in fact route
from `12236`.

#### Before filing

- **Establish the producer.** The shipped file is tracked in the repository;
  `map_tools/fetch_prebuilt_maps.sh` also sources these maps from
  `carla-simulator/autoware-contents`, while `map_tools/generate_lanelet2_map.py`
  can regenerate them. Which path produced the committed artefact has not been
  established, and this record does not guess.
- **Establish whether the bug is CARLA's or its dependency's.** The generator
  wraps `commonroad-scenario-designer`; if the un-inverted shared-bound
  reference originates there, the fix belongs in that project and CARLA's role
  is to work around or pin it. That decides the target repository, so it has to
  be settled first.
- **Demonstrate the fix, not just the avoidance.** Inverting one offending
  bound and re-running run 3's exact spawn and goal would turn "avoided" into
  "fixed". No run has done that yet.
- **Check the other artefacts.** `lanelet2_map_2019_legacy.osm` in the same
  directory has never been scanned; if it is clean, that localizes which
  converter generation broke. Town10HD is the only map shipped in-tree under
  `map_tools/maps/`, so every other town is unmeasured.

## Note on candidate 14 (`is_dense` / `row_step`)

The controller ledger recorded this as "the native ROS 2 PointCloud2 publisher
emits `row_step = 0` and `is_dense = false`". Re-checking the log per node and
reading the publisher source narrows it: only the `is_dense` half is
CARLA-attributable.

- All **99** `is_dense is false` warnings in run 1 come from
  `sensing.lidar.top.crop_box_filter_self`, the first Autoware node to consume
  CARLA's `/sensing/lidar/top/pointcloud_raw_ex`. CARLA sets `is_dense = false`
  deliberately at `CarlaPointCloudPublisher.cpp:110`, with a comment at
  `:107-109` explaining the choice. This is the real, CARLA-side finding, and
  it recurs in run 4. The validator does not drop the cloud -- it warns and
  processes it anyway, and NDT converged on this data -- but the deadline the
  warning itself quotes, "This will be an ERROR starting in 2026 July", has
  already passed, which sharpens the case for filing.
- The **104** `row_step mismatch ... Got: 0` warnings come from
  `localization.util.crop_box_filter_measurement_range` (81) and
  `perception.obstacle_segmentation.crop_box_filter` (23), and from **zero**
  occurrences at the first-hop node. Their clouds are `base_link`-framed with
  `point_step 16`, i.e. Autoware's own `PointXYZIRC` produced by its
  preprocessing chain, not CARLA's `XYZIRCAEDT` output. CARLA's publisher sets
  `row_step = width * point_step` at `CarlaPointCloudPublisher.cpp:106`, and
  the LiDAR call site passes a non-zero width
  (`LibCarla/source/carla/ros2/ROS2.cpp:736-741`, `height = 1`,
  `width = points`), so CARLA's own message cannot carry `row_step = 0`.

Caveat, stated because it is not verified: Autoware's validator reports one
reason per message, so the first-hop node may stop at `is_dense` and never
evaluate `row_step` on CARLA's cloud. That does not change the attribution for
the messages we can trace, but the PR should re-measure `row_step` at the first
hop after the `is_dense` change lands.

## Note on candidate 17 (retired)

Fork commit `a203b7ce4` guards `Map::GenerateChunkedMesh` against a
`.front()`-on-empty SIGSEGV. The plan and spec §2 both listed porting it as a
known gap. It is **not** a gap: upstream already has an equivalent guard, and
it is an independent re-derivation rather than a cherry-pick of ours.

- `LibCarla/source/carla/road/Map.cpp:1323` - `if (out_mesh_list.empty()) { return {}; }`
- `:1330`, `:1344`, `:1361` - `mesh->GetVertices().empty()` checks
- `:1317-1322` - a comment describing the same `.front()`-on-empty SIGSEGV
- Provenance: German Ros's `4ca6c4776`, 2026-08-03, "OpenDRIVE runtime maps:
  materials, crosswalks, lane markings, semantic tags" (ours is dated
  2026-07-10)

**The plan's probe pattern was a false-negative generator, and that is the
transferable lesson.** `git grep -c 'Vertices.empty()'` returns 0 because `.`
matches exactly one character between `Vertices` and `empty()`, while both
upstream's code and our own fix write `GetVertices().empty()` - three
characters. The probe would have reported "absent" even when run against our
own patch. A probe that asserts an absence needs a positive control on the same
tree and pattern before its zero is believed; the MGRS content probe
(candidate 8) was re-run with one, which is why its zero is trusted.

If Phase 3 still reproduces a SIGSEGV at that call site, it is a different
defect from the one `a203b7ce4` addresses and needs its own diagnosis rather
than a port.

## Findings recorded elsewhere, not PR candidates against CARLA

- **Spec §6 threshold defect.** Spec §6 states "G3 LiDAR 20 +/- 1 Hz". The
  `awsim_sensor_kit` that upstream's launch line uses configures the top LiDAR
  at `sensor_tick 0.1`, i.e. 10 Hz, and it measured exactly 10.000 Hz in the
  passing runs. The threshold should read "matches the configured rate". This
  is a correction to our own spec, not to CARLA.
- **Host `net.core.rmem_default`.** Raised 212992 -> 8388608 to stop
  large-sample DDS loss. A host tuning prerequisite, arguably a README
  addition, but no CARLA code change; recorded in `phase0-bringup.md`.
- **`is_autonomous_mode_available: false` while `mode = 2` (AUTONOMOUS).**
  Present in both run-3 metrics blocks and, with `mode: 1`, in run 4 after
  arrival. Unexplained, and not attributed to any component, so not yet a
  candidate.
