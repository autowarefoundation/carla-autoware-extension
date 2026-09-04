# Phase 1 - Reproducing upstream's Town10HD `classical` run (CARLA `ue58-dev`)

> **`[CORRECTED]` 2026-09-04, after Phase 2. Read this before citing anything
> below it.** The measurements in this file are real and unaltered. What is
> withdrawn is the _causal_ story it tells about the Town10HD lanelet2 map -
> that the 17 misoriented bounds cause backward planning, latched emergency
> stops and a ~20 % spawn failure rate. That chain was **falsified by this
> campaign's own logs**. What survives: 17 of 160 road lanelets (17 of 246
> relations) reference a shared bound ordered against travel, the legacy 2019
> map has 0 of 168, and the generator reproduces the repaired map
> byte-identically. What does not: on the _fixed_ map `Backward path is NOT
> supported` still occurred 290 and 190 times, the _unfixed_ map produced the
> identical route from a pose 0.024 m away and halted at the same metre by the
> same mechanism, and a static `lanelet2` probe showed `geometry::align`
> already recovers the correct orientation for **all 17** today, with the
> derived centreline and the routing graph unchanged. **The map fix is
> preventive**: it removes a dependence on a loader heuristic that currently
> guesses right.
>
> Five statements below carry withdrawn wording and are each marked
> `[CORRECTED]` in place, so a reader who greps into the middle of this file
> cannot land on them without the correction: the two `EMERGENCY_STOP` table
> rows reading "171, latched" (actually 171 operated / 172 canceled, last event
> a cancel, so nothing latched; median cycle 2.200 s, not ~100 ms), the
> `Backward path` row of the run-3-vs-run-4 table (the counts are real, the
> attribution of the contrast to the map defect is not), and the two "roughly
> one spawn point in five" passages, which measure the size of the affected map
> region and are **never** an expected failure rate.
>
> Do not re-add "fixes Backward path", any emergency-stop claim, any failure
> rate, or a "377 -> 0". Corrected record: `phase2-gates.md` and
> `~/ue58-logs/p2-03-evidence.md` - **not** `~/ue58-logs/24-metrics.txt`, whose
> body still carries the withdrawn narrative below its correction header.

Date: 2026-09-03. Machine: RTX 5090 (driver 580.173.02), 24 cores, 62 GB RAM,
Ubuntu 24.04, ROS 2 Jazzy at `/opt/ros/jazzy`.

| Component | Value |
| --- | --- |
| CARLA | `upstream/ue58-dev` `5f58df57998030cb602a0fc588db6cc5b8a23988` (worktree `~/src/carla-ue58`) |
| Engine | `CarlaUnreal/UnrealEngine@ue58-dev-carla` `cacb25b99f14d3f584e2c7626a63d868e204809f` (5.8) |
| Content | `carla-content@ue58-dev-carla` `981cdcbae26b015f2d4537eed4e5464e1cd5aed7` |
| Autoware image | `ghcr.io/autowarefoundation/autoware:universe-cuda-jazzy` digest `sha256:9c7d51a820a064c07ed2d8386b464bb69d8676e262ae20e88723918185ec0eaa`, image ID `9c7d51a820a0`, built 2026-09-02, 16.9 GB |
| Map | `Town10HD_Opt`, map dir `PythonAPI/examples/av_stacks/autoware/map_tools/maps/Town10HD` (`projector_type: Local`) |

Phase 1 asked one question: following upstream's own README verbatim, does the
in-tree Autoware layer on `ue58-dev` drive the ego to a goal on Town10HD? The
answer took four live runs, because the README's own documented command does
not, and the first substitute exposed a second, independent defect.

## Reproducibility note on the image

The plan assumed the locally pre-pulled `universe-cuda-jazzy` (image ID
`019a301ee0f1`, 2026-07-16, 17 GB) would be reused. It was not:
`install/install_autoware.sh --docker` pulls unconditionally, the tag had moved,
and every run in this record used the 2026-09-02 digest listed above
(`21-autoware-docker.log`, `Digest: sha256:9c7d51a8...`). The 2026-07-16 image
is now dangling. Reproducing these numbers requires pinning that digest.

## What was run

The README's only documented goal (`README.md:195`, under "### 3. Run", "Full
classical stack, drive to a goal"):

```bash
./run/run_carla_autoware.sh --mode classical --goal "80.0,-16.5,90"
```

was run as run 1, with the plan's explicit town/stack/server arguments added:

```bash
run/run_carla_autoware.sh --mode classical --stack docker --server editor \
    --town Town10HD_Opt --goal "80.0,-16.5,90"
```

The script generated its own DDS topology, identically in all four runs
(`22-dry-run.log` and the four orchestrator logs): bridge interface `docker0`
at `172.17.0.1`, simulator Fast-DDS UDPv4 whitelisted to that IP
(`run<N>/dds/fastdds_profile.xml`), Autoware CycloneDDS pinned to the same
interface with `MaxAutoParticipantIndex=300`, `MaxMessageSize=65500B` and
10-64 MB receive buffers (`run<N>/dds/cyclonedds.xml`), `ROS_DOMAIN_ID=42`, and
kernel UDP buffers `net.core.{r,w}mem_max = 67108864`.

The Autoware launch line was unchanged by us in every run:

```text
ros2 launch autoware_launch e2e_simulator.launch.xml vehicle_model:=sample_vehicle
  sensor_model:=awsim_sensor_kit perception_mode:=lidar rviz:=false
  simulator_type:=carla launch_simulator_interface:=false map_path:=/maps/Town10HD
```

The CARLA-side Autoware overrides were applied by the script, not by us, and
are identical in all four runs: NDT convergence likelihood to 1.0,
`stop_check_enabled` to false, ADAPI diagnostics timeouts to 30.0, and
`launch_traffic_light_module` to false.

## The four runs

Each run changes one variable from the one before it.

| Run | Log dir | Simulator RMW | Spawn | Goal (CARLA `x,y,yaw`) | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | `run1` | fastdds | random (matched lanelet `16406`) | `80.0,-16.5,90` (the README's) | **FAIL** - goal rejected, ego never moved |
| 3 | `run3` | fastdds | random (matched lanelet `12236`, malformed) | `98.90,68.73,90.4` (derived, valid) | **FAIL** - route set, planning broke |
| 4 | `run4` | fastdds | `--spawn-index 24` (lanelet `5013`, clean) | `-1.16,28.37,0.16` (derived, valid) | **PASS** - drove the route, ARRIVED |
| 2 | `run2` | `--rmw cyclonedds` | `--spawn-index 24` (lanelet `5013`, clean) | `-1.16,28.37,0.16` | **PASS** - drove the route, ARRIVED |

Run 2 is numbered out of chronological order because it was scheduled as the
CycloneDDS probe; it ran last (server pgid 1665193, after run 4's 1609969). The
runs are described below in execution order.

### Run 1 - the README's own goal is off-road

Every pre-drive stage passed. The run script raised no preflight failure; the
CARLA RPC port came up in 22 s; localization initialized after four retries;
both engage gates passed (`GATE1: truth (15.85, -28.07) yaw -4.6 deg | belief
(15.88, -28.05) yaw -4.7 deg | delta 0.04 m, 0.1 deg`; `GATE2: distortion
corrector clean`).

Then nothing drove. `autoware_mission_planner` enumerated a 14-lanelet
candidate sequence and then rejected the goal:

```text
getMainLanelets: lanelet_sequence = [ids: 16406 34932 10868 22411 11685 36849
  13373 26524 13571 13721 18842 19425 9913 14515 ]
Goal's footprint exceeds lane!
Goal is not valid! Please check position and angle of goal_pose
```

(`run1/autoware.log:1723`, `:1725-1726`). No route was published, so
`/api/routing/state` stayed at `1` (UNSET), `is_autonomous_mode_available`
stayed `false`, and `change_to_autonomous` was refused 12 times
(`run1/autoware.log:1730-1731`, `23-live-run.log`). CARLA ground truth: the ego
sat at `(17.29, 28.24)` at `0.00 m/s` for the full 50 s sample window, 77.03 m
from the goal (`24-metrics.txt`).

Why: CARLA `80.0,-16.5,90` maps to waypoint `(99.441, -16.335)` on a 3.50 m
lane, a **lateral offset of 19.44 m from the nearest lane centreline** - about
17.7 m from the nearest lane edge, taking the lane's own 3.50 m width
(`28-goal-xcheck.txt`). The heading is fine (yaw error -0.15 deg). Measuring
the same point against the converted lanelet2 map independently gives 19.44 m
to the nearest road-lanelet centreline (lanelet `14515`, centreline heading
-89.87 deg, consistent with the documented 90 deg yaw), so CARLA's OpenDRIVE
and the lanelet2 map agree.

This is a documentation defect rather than a transcription slip on our side.
`README.md:195` is the only goal documented anywhere in `av_stacks`, so anyone
following the README verbatim gets a stack that comes up healthy, passes both
pre-engage gates, and then silently refuses to drive, with the reason buried
deep in `autoware.log`.

**The two Phase 1 defects are not cleanly separable.** Run 1's rejected
candidate sequence above contains lanelet `10868`, which is one of the 17
malformed lanelets described below. Had the goal been valid, this run would
most likely have hit the map defect instead. Fixing only the README would not
have produced a working documented path.

### Run 3 - a valid goal exposes a malformed lanelet2 map

The replacement goal was derived, not guessed: the arclength midpoint of
lanelet `31570` (`subtype=road`, 29.87 m long, 3.50 m wide, 14.7 m clear of
either end), heading taken as the centreline tangent by construction. Its
CARLA-OpenDRIVE cross-check is lateral offset **0.00 m**, yaw error **0.01 deg**
(`28-goal-xcheck.txt`).

Mission planning accepted it: an 8-lanelet / ~153.5 m route was published
(`run3/autoware.log:1102-1114`), `/api/routing/state` reached `2` (SET), and
`change_to_autonomous` succeeded on the 2nd attempt instead of being refused 12
times. Goal selection was therefore solved.

Planning then broke, 0.4 s after the route was set. Counts are re-derived from
`run3/autoware.log` for this record, because the per-node breakdown in the task
report was wrong:

`[CORRECTED]` The counts in this table are real; the causal chain this section
draws from them to the map defect is withdrawn - see the banner at the top of
this file. One cell is corrected in place.

| Message | Count | Emitting node(s) |
| --- | --- | --- |
| `Backward path is NOT supported, just returning input path` | **377 total** | `behavior_velocity_planner` 171, `elastic_band_smoother` 103, `path_optimizer` 103 |
| `Caution! Invalid Trajectory published.` | 166 | `planning_validator` |
| `planning trajectory is too far from ego in longitudinal direction!!` | 166 | `planning_validator` |
| `EMERGENCY_STOP is operated.` | 171 operated / 172 canceled, last event a cancel, so **nothing latched** `[CORRECTED]`; median cycle 2.200 s, not ~100 ms | `mrm_handler` |
| `Emergency!` | 427 | `control.vehicle_cmd_gate` |

`/planning/trajectory` stayed pinned at the route start, running west with
negative longitudinal velocity, 118 m behind the ego, while still publishing at
10.000 Hz. The ego drove straight from x=22.2 to x=116.6 m with yaw never
leaving -3.9..+0.7 deg - straight through the route's required left turn - then
stood still for ~310 s. Closest approach to the goal was 5.09 m (a straight-line
coincidence while passing the goal's easting), final distance 17.75 m
(`29-groundtruth.txt`).

Root cause: `map_tools/maps/Town10HD/lanelet2_map.osm` contains **17 of 160
road lanelets whose left and right boundary ways run in opposing directions**
(`31-lanelet-bound-orientation.txt`), including lanelet `12236` - the route's
first segment on this run, and the lanelet the ego started inside. The
mechanism and the blast radius are in `pr-candidates.md`.

### Run 4 - clean spawn, and the gates pass

Run 4 pinned the spawn instead of leaving it random, and chose a goal whose
whole route avoids all 17 malformed lanelets.

Selection method (`33-run4-route-selection.txt`): Dijkstra by centreline length
was run on two graphs - a strict successor graph and a permissive one that also
connects the malformed lanelets, modelling what Autoware's own router did in
run 3 - keeping only candidates whose globally shortest route on the
*permissive* graph is itself entirely clean and has no malformed lane-change
neighbour. Spawn 24 and the arclength midpoint of lanelet `16406` satisfied
both.

The published route matched the offline prediction exactly, 7 segments, all
clean: `5013 -> 27144 -> 12771 -> 36676 -> 13373 -> 25058 -> 16406`
(`run4/autoware.log:1099-1106`).

The controlled comparison against run 3, `[CORRECTED]`: the counts below are
real and reproducible, but this table was written as a map-fix result and is
not one. Run 3 and run 4 differ in spawn and route, not in the map file - both
ran the *unrepaired* map - and on the *repaired* map the same pinned scenario
still produced 290 and 190 `Backward path` occurrences. Read the table as
"a clean route plans, a route through a malformed lanelet does not", and note
that even that reading is not attributable to the bound orientation, because
`geometry::align` already recovers it for all 17. See the banner at the top of
this file.

| Signature | Run 3 (started inside malformed `12236`) | Run 4 (started inside clean `5013`) |
| --- | --- | --- |
| `Backward path is NOT supported` `[CORRECTED]` (counts real, map attribution withdrawn) | 377 | **0** |
| `Invalid Trajectory published` | 166 | **0** |
| `too far from ego in longitudinal direction` | 166 | **0** |
| `EMERGENCY_STOP is operated` `[CORRECTED]` (run 3: 171 operated / 172 canceled, nothing latched) | 171, **not latched** | 11 operated / 11 cancelled |
| `Emergency!` | 427 | 9 |

`AutowareState` walked `Initializing -> WaitingForRoute -> Planning ->
WaitingForEngage -> Driving -> ArrivedGoal -> WaitingForRoute` once, cleanly.
`/api/routing/state` reached `3` (ARRIVED) and still read `3` thirteen minutes
later (`37-run4-final-state.txt`). The ego covered ~155 m in ~45 s at a steady
4.1-4.2 m/s, taking both planned junction turns (yaw 176 -> -130 -> -90 -> -57
-> -6 -> 0) (`35-groundtruth-run4.txt`).

The 11 `EMERGENCY_STOP` events all self-cancelled within about a second and the
ego drove through them at 4.17 m/s. The only reason the diagnostic graph ever
prints alongside them is `/autoware/localization/scan_matching_status WARN`
(`run4/autoware.log:1236-1242` and three further blocks at `:1266`, `:1296`,
`:1378`), i.e. a transient NDT scan-matching degradation. The traffic-signals
topic-state monitor does fire 295 times across the whole run, but it never
appears in a `The target mode is not available for the following reasons` tree,
so it does not explain a 21-second burst and must not be blamed for it.

### Run 2 - the same drive with the simulator on CycloneDDS

Identical spawn and goal, only `--rmw cyclonedds` added. The script warns
against it (`25-cyclonedds-sim.log:1`) but does not refuse it; the server
really launched with `-ros2 -rmw=cyclonedds` (`run2/carla_server.log:523`). The
same 7-lanelet route was published (`run2/autoware.log:1105`), the ego reached
`/api/routing/state = 3` (ARRIVED), and there were zero occurrences of the
three run-3 planning signatures and no fragment, drop or deserialization errors
in `run2/carla_server.log`.

Scope caveat on the drive evidence: the CycloneDDS ground-truth tracker
(`25b-groundtruth-cyclonedds.txt`, 48 samples over t=0-235 s) started **after**
the ego had already arrived - every sample reads `dist2goal` 1.23-1.24 m - so it
records the post-arrival hold, not the drive. The drive itself rests on two
point measurements: the GATE1 truth pose `(-16.96, -130.26)` at engage and the
final actor origin `(0.057, 28.542)`, a straight-line displacement of about
103 m, plus the state machine reaching ARRIVED. That is sufficient for the
conclusion drawn here, but it is not a tracked path.

## Gate results

Gates are evaluated against run 4, the verbatim-topology PASS.

| Gate | Threshold (spec §6) | Measured | Source | Result |
| --- | --- | --- | --- | --- |
| G1 NDT localization error | < 1 m | **0.128 m** at the sampled instant; 0.04-0.05 m at both engage gates | `task-9c` decomposition; `23`/`27`/`28-live-run*.log` GATE1 lines | PASS |
| G2 closest approach to goal | < 1 m | **0.24 m** (`base_link`) at arrival, **0.58 m** after ~6 minutes of settling drift | `24-metrics.txt` run 4 verdict block; recomputed from `35-groundtruth-run4.txt`; see basis note | PASS |
| G3 control rate | 20 +/- 5 Hz | **19.998 / 19.999 / 20.000 Hz** stationary (min interval 0.045-0.046 s), 20.376-20.398 Hz driving | `36-metrics-run4-block1/2.txt`, `37-run4-final-state.txt` | PASS |
| G3 LiDAR rate | spec says 20 +/- 1 Hz; see defect below | **10.000 Hz** against a configured 10 Hz | `36-metrics-run4-block1/2.txt` | PASS against the configured rate |

**Spec defect.** Spec §6 states "G3 LiDAR 20 +/- 1 Hz". The `awsim_sensor_kit`
that upstream's launch line uses configures the top LiDAR at `sensor_tick 0.1`,
i.e. 10 Hz, and it measured 10.000 Hz exactly in runs 3 and 4 and 9.999-10.001
Hz in run 2. The 20 Hz figure was inherited from a differently-configured kit.
The threshold should read "matches the configured rate"; as written, a correct
run fails the gate.

**Precision caveat on G1.** The 0.128 m figure is one comparison at one
instant, not a run-wide error. The two run-4 metrics blocks report NDT beliefs
0.15 m apart from each other (`(-1.3113, -28.4765)` and `(-1.3200, -28.6316)`),
and the ground-truth rear axle itself drifts during the stationary window, so
comparing each belief against the rear axle across that window gives a spread
of roughly 0.04-0.44 m depending on which sample is paired. Every value is well
inside the 1 m gate, but a single flat "0.128 m" overstates the precision of
the measurement.

### Basis of the G2 distance figure

Autoware controls `base_link` (the rear axle) to the goal pose; CARLA's actor
transform is the vehicle centre. Run 4's arrival position decomposes as
(`task-9c` report, using the harness's own `HALF_WHEELBASE = 1.425` from
`run_carla_autoware.sh:1048`, the same constant used at `spawn_vad_rig.py:43`):

```text
ground-truth actor origin      map ( 0.065, -28.463) yaw 1.90 deg
ground-truth rear axle         map (-1.359, -28.510)
NDT belief                     map (-1.320, -28.632)
commanded goal                 map (-1.160, -28.370)

base_link    -> goal   0.244 m
actor origin -> goal   1.229 m
```

`base_link` is the correct basis for G2 because Autoware's goal is itself a
`base_link` pose. The offset is not an assumption: GATE1 compares CARLA ground
truth against `/localization/kinematic_state` using the same 1.425 m offset and
passed at 0.02-0.05 m in all three engaging runs. Were the offset wrong or
misapplied, GATE1 would have shown roughly 1.4 m rather than 2-5 cm.

`base_link` is not directly derivable from the CARLA client here: CARLA 0.10
Chaos vehicles return `(0,0,0)` for every `physics_control.wheels[].location`,
which is why `25e-final-state-cyclonedds.txt` records `rear-axle base_link
CARLA (0.000, 0.000)`. The rear axle above is reconstructed from the actor
transform and that wheelbase constant.

**The vehicle does not hold perfectly still after arrival, and the earlier
"under 5 mm" claim was x-only.** Recomputing from `35-groundtruth-run4.txt`
over the stationary window (t = 65 s to 415 s): x stays within **0.014 m**, but
y creeps from 28.448 to 28.674 (**0.226 m**) and yaw rotates from -1.32 to
-9.70 deg. Because the rear axle sits 1.425 m behind the actor origin, that
8.4 deg of yaw moves it: `base_link` to goal is **0.23 m at arrival (t = 65 s)**
and **0.58 m at the last sample (t = 415 s)**. The 0.23 m here and the 0.244 m
in the decomposition above are the same arrival on two different samples -- the
decomposition uses the `task-9c` arrival sample, this recomputation the t = 65 s
row of `35-groundtruth-run4.txt` -- so the ~1 cm gap is sampling, not a
disagreement. Both are inside the 1 m gate, so G2 passes on either reading,
but the honest statement is "0.24 m at arrival, 0.58 m after about six minutes
of settling drift", not a static 0.24 m.

### Fast-DDS vs CycloneDDS on the simulator side

Both runs used the same spawn and goal, so they are directly comparable. The
comparison is put on the actor-origin basis, the only one measured identically
in both.

| Metric | run 4 (fastdds) | run 2 (cyclonedds) |
| --- | --- | --- |
| `/control/command/control_cmd` | 19.998 - 20.398 Hz | 20.000 - 20.001 Hz |
| `/sensing/lidar/top/pointcloud_raw_ex` | 10.000 Hz | 9.999 - 10.001 Hz |
| GATE1 localization delta | 0.02 m, 0.0 deg | 0.02 m, 0.0 deg |
| ego actor origin -> goal (ground truth) | 1.25 m | 1.229 m |
| NDT belief -> goal (metrics block 1) | 0.185 m | 0.241 m |
| `/api/routing/state` | 3 (ARRIVED) | 3 (ARRIVED) |
| `Backward path` / `Invalid Trajectory` / `too far from ego` | 0 / 0 / 0 | 0 / 0 / 0 |

**DDS interop works, in both directions and with both vendors on the simulator
side.** The outbound (simulator to Autoware) fragmented path carried 10 Hz
LiDAR well enough for NDT to converge, and the inbound (Autoware to simulator)
path actually actuated the vehicle: the ego reached ARRIVED under CycloneDDS.

An earlier host-side probe reported `rmw_cyclonedds_cpp` seeing only
`/parameter_events` and `/rosout` against the Fast-DDS simulator. That result
did not reproduce and is attributed to a stale `ros2 daemon`, which is keyed by
both RMW and domain; it should not be repeated as a fact. Practical guidance:
run `ros2 daemon stop` before concluding anything about discovery.

## `VK_ERROR_DEVICE_LOST` (spec risk 4) did not occur

The designated Phase 0 blocker, `VK_ERROR_DEVICE_LOST` as reported upstream in
`#9826`, appears **zero times across the 53 top-level `*.log` and `*.txt`
files** in `~/ue58-logs/`, and zero again across all 77 such files once the
per-run subdirectories are included (165 files in the tree in total);
`VK_ERROR` of any kind is likewise zero. Counted with binary-safe `grep -ac`,
because plain `grep -c` mis-reports on the 1.7 MB launch logs. Scope: this is
one machine, an RTX 5090 on driver 580.173.02; upstream's report is against an
RTX 3090 on driver 595.84, so this is a non-reproduction on different hardware,
not a refutation of the report.

## Deviations from the README

- **The image was re-pulled rather than reused** (see the reproducibility note
  above). `21-autoware-docker.log`.
- **`install_autoware.sh --check` reported the centerpoint model directory
  absent** - `centerpoint dir: /home/youtalk/autoware_data/ml_models/lidar_centerpoint
  not present (needed for classical perception_mode:=lidar)`
  (`20-autoware-check.log:30`). This host's `~/autoware_data` is in the older
  pre-`ml_models` layout. Three relative symlinks
  (`~/autoware_data/ml_models/{lidar_centerpoint,traffic_light_classifier,traffic_light_fine_detector}
  -> ../<same>`) were created after verifying inside the image which paths the
  launcher actually resolves. TensorRT then loaded every ONNX with no
  model-path errors and rebuilt the two missing `.engine` files once
  (79 messages, self-healing).
- **`net.core.rmem_default` was raised from 212992 to 8388608.** The README
  documents the 64 MB `rmem_max`/`wmem_max` prerequisite only; `rmem_default`
  bounds any socket that does not explicitly enlarge its buffer, and at 208 KB
  it was smaller than a single LiDAR sample. Detail in `phase0-bringup.md`.
- **Runs 3, 4 and 2 did not use the README's goal**, for the reason in run 1.
  Runs 4 and 2 also pinned `--spawn-index 24`, which the README does not
  document as part of the classical flow.
- **The run script's server line omits `-nosound` and `-log`** relative to the
  launch line Phase 0 proved working (`22-dry-run.log`). It was left unpatched
  deliberately, since Phase 1 is defined as verbatim reproduction. Consequence
  for diagnostics: `run<N>/carla_server.log` is the redirected stdout, and the
  richer editor log lives at `Unreal/CarlaUnreal/Saved/Logs/CarlaUnreal.log`.
- **Jazzy, not Humble.** The spec asks for Humble first; upstream's README
  default is Jazzy, and Phase 1 is defined as verbatim reproduction, so the
  Jazzy 1.9.0 cell was run. The Humble cell moves to Phase 2. Our historical
  G1-G3 numbers are on Humble, so no parity between the two cells is claimed
  here.
- **`--check` also reported the workspace and the VAD model directory absent**
  (`20-autoware-check.log:28-29`). Neither is needed: the run used
  `--stack docker`, and the VAD check is `--mode e2e` gated.

## Probes

- **PROBE1 - MGRS is content-only, and dormant on this branch.** The offset has
  exactly one source, `AAutowareGnssSensor::LoadMgrsData()` reading
  `AAutowareWorldSettings::MgrsDataAssetSoftPtr`, an editor-set
  `TSoftObjectPtr` on the level World Settings. No runtime override path
  exists: the `autoware_gnss` blueprint is `MakeGnssDefinition` plus noise
  attributes only, and `SetAutowareGnss` sets only noise. Content references to
  `MgrsDataAsset` on `ue58-dev-carla@981cdcbae2`: **0** - validated by a
  positive control on the same tree and pattern (`AutowareWorldSettings` 85
  files, `WorldSettings` 256, `CarlaGameMode` 6). Town10HD declares
  `projector_type: Local`, so Phase 1 never exercised MGRS; the sensor logged
  `MGRS Data Asset SoftPtr not set in WorldSettings.` once
  (`run2/carla_server.log:3289`) and published raw CARLA-local coordinates,
  which is correct for `Local`. Full text in `26-probes.txt`.
- **PROBE2 - the CycloneDDS-on-simulator warning is stale.** See the Fast-DDS
  vs CycloneDDS comparison above, with its evidence caveat.
  `25-cyclonedds-sim.log`, `26-probes.txt`.
- **PROBE3 - the empty-mesh guard is already upstream.** The plan's probe
  pattern `Vertices.empty()` returns 0 matches, but that is a false negative:
  `.` matches exactly one character between `Vertices` and `empty()`, whereas
  both upstream's code and our own fix write `GetVertices().empty()`. The guard
  is present at `LibCarla/source/carla/road/Map.cpp:1323`
  (`if (out_mesh_list.empty()) { return {}; }`) with further
  `mesh->GetVertices().empty()` checks at `:1330`, `:1344` and `:1361`, and a
  comment at `:1317-1322` describing the same `.front()`-on-empty SIGSEGV our
  fork commit `a203b7ce4` addresses. It arrived in German Ros's `4ca6c4776`
  (2026-08-03), an independent re-derivation rather than a cherry-pick. The
  port is retired; see `pr-candidates.md`.

## Open questions this record does not answer

- **No run demonstrates the map fix.** Inverting one offending bound and
  re-running run 3's exact spawn and goal would turn "avoided" into "fixed".
  That experiment has not been done.
- **Blast radius beyond Town10HD is unmeasured.** Town10HD is the only map
  shipped in-tree under `map_tools/maps/`, so no other town's lanelet2 file was
  scanned for the same defect.
- **`lanelet2_map_2019_legacy.osm` was never scanned.** If the legacy file is
  clean, that would localize which converter generation introduced the defect.
- **There is no interim guidance for a user.** `[CORRECTED]`: "one spawn in
  five" is the share of CARLA spawn points that sit inside one of the 17
  affected lanelets (30 of 155, 19.4 %), i.e. the size of the affected map
  region - **not** a failure rate. No spawn failure attributable to the bound
  orientation was ever demonstrated, so there is no residual failure for a
  workaround to address. What remains true is narrower: the documented default
  path leaves the direction of travel of those lanelets up to the loader's
  `align` heuristic, and this record does not propose a workaround short of the
  map fix.
- **`is_autonomous_mode_available: false` while `mode = 2` (AUTONOMOUS) and
  `is_autoware_control_enabled: true`** in both run-3 metrics blocks
  (`30-metrics-run3-block1.txt:32-35`, `block2` the same), and again in run 4
  after arrival with `mode: 1` (`37-run4-final-state.txt:5-7`). Unexplained.
- **The simulator exits with SIGSEGV on teardown in all four runs.**
  `run/run_carla_autoware.sh:314` reports `Segmentation fault (core dumped)`
  for the `carla_server` process group in `23-live-run.log`,
  `27-live-run-goal2.log`, `28-live-run-clean-spawn.log` and
  `25-cyclonedds-sim.log`, i.e. under both middlewares. It happens after
  teardown begins, so no drive result is affected, but it is not root-caused.
  Filed as a PR candidate.
- **The transient NDT scan-matching degradation in run 4** that triggered the
  11 self-cancelling `EMERGENCY_STOP` events was identified but not diagnosed.

## Comparison to our earlier Nishi-Shinjuku gates (extension `.so` era)

Our 2026-07-24 G1-G3 PASS used both sides on CycloneDDS over `--net=host` with
a Humble `universe-devel` image and the extension `.so`. This record used
upstream's own topology (simulator Fast-DDS, container CycloneDDS, bridge-IP
whitelist), Jazzy 1.9.0, the in-tree Autoware layer, and Town10HD rather than
Nishi-Shinjuku. Both cells are recorded so Phase 2 can attribute any
difference; no equivalence between them is claimed.

## Bottom line

The in-tree Autoware layer on `ue58-dev` achieves full closed-loop autonomous
driving on Town10HD under UE 5.8, with all three spec gates green - but only
once two upstream defects are worked around, and they are entangled rather than
independent: the README's only documented goal is 19.4 m off the nearest lane
centreline, and 17 of 160 lanelets in the shipped Town10HD lanelet2 map have
opposing boundary directions, overlapping roughly one spawn point in five
`[CORRECTED]` - a region size (30 of 155 spawns, 19.4 %), **not** a failure
rate, and not a demonstrated failure at all; the map repair is preventive. The
README's own rejected route ran through one of the malformed lanelets. Both are
self-contained, evidenced and independently reproducible; they head the list in
`pr-candidates.md`.

## Logs

`~/ue58-logs/20-autoware-check.log` through `38-run4-teardown.log`, plus
`run1/`, `run2/`, `run3/` and `run4/`. Local only, not committed.
