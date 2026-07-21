# G0 interop spike report

Gate **G0** for the CARLA native-DDS -> Autoware ROS 2 interop spike: prove that
every topic the CARLA integration branch publishes over CycloneDDS is visible,
correctly typed, QoS-correct and deserializable from inside an Autoware
container, and that the message wire types match their canonical REP-2011
definitions.

- Date: 2026-07-09
- Integration branch: `feat/autoware-seminative-integration` @ `288bc9b1c`
  (base `upstream/ue5-dev` = `601966371`).
- Companion (this) repo: `main` @ `8348e9d`.

## Environment

Recorded in full in [`environment.md`](environment.md); the load-bearing facts:

| Field                   | Value                                                                              |
| ----------------------- | ---------------------------------------------------------------------------------- |
| Container image         | `ghcr.io/autowarefoundation/autoware:universe-devel`                               |
| Image digest            | `sha256:405225eda6c05161bfde39cc7885511f3f4d9699d126891891420dd80c2e024a`          |
| `ROS_DISTRO`            | `humble`                                                                           |
| RMW implementation      | `rmw_cyclonedds_cpp` (via `RMW_IMPLEMENTATION` in `docker/compose.yaml`)           |
| `CYCLONEDDS_URI`        | `file://.../docker/cyclonedds.xml` (localhost-only profile, shared host+container) |
| `ROS_DOMAIN_ID`         | `0` (forced by `run_g0.sh`; see note below)                                        |
| Host / container kernel | `6.17.0-35-generic` (container uses `network_mode: host`)                          |
| Docker                  | `29.6.1`                                                                           |

`carla_msgs` is not available as a `ros-humble-*` apt package; it was built from
source (`carla-simulator/ros-carla-msgs`) into `~/carla_msgs_ws` inside the
container. Container-side sourcing therefore requires all three overlays:
`source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && source ~/carla_msgs_ws/install/setup.bash`.

`ROS_DOMAIN_ID` note: the developer's login shell exports `ROS_DOMAIN_ID=123`,
which leaks into the CARLA process and yields zero discovery against the
domain-0 container. `run_g0.sh` forces `export ROS_DOMAIN_ID=0` before launching
the simulator so both ends share domain 0.

## Final topic matrix

Produced by `scripts/interop_check.py` inside the Autoware container against a
live simulator, verbatim from `reports/interop_results.md` (re-run 2026-07-09,
`run_g0.sh` exit 0):

| topic                            | presence | type | durability      | reliability | echo | rate      |
| -------------------------------- | -------- | ---- | --------------- | ----------- | ---- | --------- |
| /clock                           | ok       | ok   | -               | RELIABLE    | ok   | -         |
| /carla/map                       | ok       | ok   | TRANSIENT_LOCAL | RELIABLE    | ok   | -         |
| /carla/ego/lidar_top/point_cloud | ok       | ok   | -               | BEST_EFFORT | ok   | 81.911 Hz |
| /carla/ego/imu                   | ok       | ok   | -               | RELIABLE    | ok   | -         |
| /carla/ego/gnss                  | ok       | ok   | -               | RELIABLE    | ok   | -         |
| /carla/ego/vehicle_status        | ok       | ok   | -               | RELIABLE    | ok   | -         |
| /carla/ego/vehicle_info          | ok       | ok   | TRANSIENT_LOCAL | RELIABLE    | ok   | -         |
| /carla/ego/odometry              | ok       | ok   | -               | RELIABLE    | ok   | -         |

**8/8 topics passed.** Each row proves, in order: the topic is published with at
least one publisher (`presence`), the advertised type matches (`type`), the
publisher's QoS matches the contract where pinned (`durability`/`reliability`),
and one message deserialized successfully inside the container (`echo`). For the
lidar, `rate` is a liveness floor (`min_hz: 15.0`), not a cadence assertion (see
open questions).

`/tf` and `/carla/ego/vehicle_control_cmd` are observed but intentionally
excluded from the matrix, and this is correct, not a gap:

- `/tf` carries **per-sensor** transforms from the pre-existing
  `CarlaTransformPublisher` (wire topic `rt/tf`; 3 sensors -> 3 publishers).
  This branch excludes only the **ego TF tree** (`map -> odom -> base_link`);
  `/tf_static` is correctly absent.
- `/carla/ego/vehicle_control_cmd` is CARLA's control-input **subscription**
  (0 publishers), not a topic this gate can observe as published.

## Type-hash verification

**Method and its limit.** The container runs `ROS_DISTRO=humble`. Humble
predates REP-2011 and ships **no type-hash machinery**: a scan of
`/opt/ros/humble` found **0** files containing `RIHS01` and **0** per-message
REP-2011 `.json` files, and `ros2 topic info --verbose` emits no type-hash
field. Therefore G0's "type-hash-correct" criterion is **not observable over
Humble discovery**. It reduces to an **offline** check: the hashes CARLA embeds
(pinned in `LibCarla/source/test/server/test_type_hash.cpp`, matching
`CdrTopicInfo<T>::type_hash()`) must equal the canonical REP-2011 RIHS01 hashes
computed from the installed interface definitions.

The RIHS01 hash is a function of the message definition only, so it is identical
on every distro that implements REP-2011 (Iron and newer). The canonical hashes
were computed with `Util/ros2/compute_type_hash.sh`, which builds each `.msg`
inside `osrf/ros:jazzy-desktop` and reads the generated `type_hashes` metadata.

**Tooling footprint.** Obtaining RIHS01 tooling — which ROS 2 Humble does not
ship — required pulling four Docker images: `autoware:universe-devel-jazzy`,
`ghcr.io/autowarefoundation/autoware:universe-devel-jazzy`,
`osrf/ros:jazzy-desktop`, and `ros:jazzy-ros-base`, totalling roughly 31 GB by
`docker images` size (the first two share the same image ID, so the unique
bytes pulled are smaller than the naive sum). A reader reproducing this
verification should budget for that download.

**Result: all four required types MATCH the pinned literals.**

| type                                   | computed (canonical, Jazzy)                                               | pinned in `test_type_hash.cpp`                                            | result |
| -------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ------ |
| `std_msgs/msg/String`                  | `RIHS01_df668c740482bbd48fb39d76a70dfd4bd59db1288021743503259e948f6b1a18` | `RIHS01_df668c740482bbd48fb39d76a70dfd4bd59db1288021743503259e948f6b1a18` | MATCH  |
| `nav_msgs/msg/Odometry`                | `RIHS01_3cc97dc7fb7502f8714462c526d369e35b603cfc34d946e3f2eda2766dfec6e0` | `RIHS01_3cc97dc7fb7502f8714462c526d369e35b603cfc34d946e3f2eda2766dfec6e0` | MATCH  |
| `carla_msgs/msg/CarlaEgoVehicleStatus` | `RIHS01_3565cc74470f5c37eb316a36426effd811ac1baf835df3fc2bb7a88574bb3e07` | `RIHS01_3565cc74470f5c37eb316a36426effd811ac1baf835df3fc2bb7a88574bb3e07` | MATCH  |
| `carla_msgs/msg/CarlaEgoVehicleInfo`   | `RIHS01_b8dc3866014924ce7fe57e0cff05a5448ec18f27156656b3b1b69f4da558e956` | `RIHS01_b8dc3866014924ce7fe57e0cff05a5448ec18f27156656b3b1b69f4da558e956` | MATCH  |

Independent cross-checks strengthening the two standard types: their hashes read
directly from Jazzy's pre-installed REP-2011 JSON
(`/opt/ros/jazzy/share/<pkg>/msg/<Type>.json`) equal the values above, and their
`.msg` definitions are byte-identical between Humble and Jazzy (confirming the
hash is genuinely distro-invariant for them).

**Evidence asymmetry.** That cross-check is not available for all four types
equally. `std_msgs/msg/String` and `nav_msgs/msg/Odometry` were verified against
Jazzy's own distro-shipped REP-2011 type-description JSON — an authoritative
source independent of CARLA. `carla_msgs/msg/CarlaEgoVehicleStatus` and
`carla_msgs/msg/CarlaEgoVehicleInfo` have no distro-shipped JSON to check
against, because `carla_msgs` is not a ROS distro package; their hashes rest
solely on `compute_type_hash.sh` running the same `rosidl` tooling over the
`ros-carla-msgs` definitions. Both computations are sound — it is the same
RIHS01 algorithm either way — but the standard types carry a redundant
independent cross-check that the `carla_msgs` types do not.

Because all four match, **no test code was changed**. The pinned literals in
`test_type_hash.cpp` (introduced by the #9787 port) are verified correct
against the canonical definitions.

**By-name compile-in gate.** `LibCarla/CMakeLists.txt` globs `test/server/*.cpp`
**without** `CONFIGURE_DEPENDS`, so a stale CMake cache could silently omit
`test_type_hash.cpp` while a test run still reported exit 0. To defend
against that, the golden suite is gated by exact name:

```bash
Build/Development/LibCarla/libcarla_test_server \
  --gtest_filter='TypeHash.GoldenValuesMatchCanonicalPackages'
```

A zero-match filter makes gtest exit 1, so this fails loudly if the suite was
never compiled in. Result: **1 test matched, PASSED, exit 0** — the golden suite
is present and green.

## Issues found and their commits

One real defect was found and fixed on the integration branch during this spike:

- `288bc9b1c` — `fix(ros2): define ego vehicle publisher constructors in
Ros2Native so middleware creation succeeds`. The three ego publishers
  (`vehicle_status`, `vehicle_info`, `odometry`) defined their constructor inline
  in the header, so `MiddlewareFactory::CreatePublisher<Traits>()` was
  instantiated in `carla-server` (which lacks the DDS vendor macros) and returned
  `nullptr`, so `PublisherImpl::Init` failed with "failed to create middleware
  publisher" and those three topics never appeared. Unit tests missed it because
  `PublisherImpl::Init` has an `#ifdef LIBCARLA_WITH_GTEST` branch that skips the
  factory when a mock middleware is pre-injected; the gap is only exercised by a
  live simulator run, which is exactly what G0 does.

**Not upstream-reportable.** This is an artifact of ue5's `carla-server` /
`Ros2Native` two-build split (the constructor must be defined in the translation
unit that carries the DDS vendor macros). ue4-dev has no such split, so there is
no corresponding upstream bug. No `[stack-fix, reportable to #NNNN]` commit was
produced by this task; the golden hashes required no fix.

## Deviations from the plan

- **`test_type_hash.cpp` step became verification, not authoring.** The planned
  step to _replace_ format-only assertions with `EXPECT_EQ` against literal
  hashes was already satisfied: the #9787 port ships the pinned golden literals
  and `TypeHash.GoldenValuesMatchCanonicalPackages` was already green. This gate
  therefore _verified_ the pinned literals against container/Jazzy-computed
  canonical hashes (all match) rather than adding them. No test code changed.
- **gtest benchmark exclusion (user-approved).** All gtest checkpoints run with
  `--gtest_filter='-benchmark_streaming.*'`. Those benchmarks assert >=90%
  delivery of 12 concurrent 1920x1080 streams @90 FPS, fail on an idle 24-core
  machine against unmodified upstream code, and their failing members vary run to
  run. Excluding them, the server test suite is **285/285 pass, exit 0**. (The
  real gtest target is `libcarla_test_server`; `BUILD_LIBCARLA_TESTS` is a CMake
  option, not a target.)
- **Editor-rebuild requirement.** `cmake --build --target carla-unreal` compiles
  the plugin but does **not** refresh
  `Unreal/CarlaUnreal/Plugins/Carla/Binaries/Linux/libUnrealEditor-Carla.so`,
  which is what `UnrealEditor -game` actually loads. Any task that changes UE
  plugin code and then runs the simulator must build `carla-unreal-editor`.
  During bring-up this cost two tasks of confusion (the running simulator
  executed pre-port UE code, so the ego topics were absent while sensors and
  `/clock` published normally).

## Open questions for the next plan

- **Lidar cadence.** `/carla/ego/lidar_top/point_cloud` measured ~82 Hz (this
  run) / ~84 Hz (prior run) against a configured `rotation_frequency: 20`.
  `ros2 topic hz` measures wall-clock arrival and the headless sync-master
  free-runs faster than real time, so the matrix validates **liveness, not
  cadence**. Open: are these point clouds full sweeps or per-tick partials, and
  what wall-clock rate should the downstream stack expect?
- **Lossy `CarlaEgoVehicleInfo` fields.** `CarlaEgoVehicleInfo` publishes `0.0`
  for physics fields with no UE5-Chaos equivalent (`clutch_strength`, wheel /
  throttle damping rates), each commented in-code. The message is shape-correct
  and passes type/echo, but these fields must not be consumed quantitatively
  downstream.
- **Humble has no type-hash discovery.** Type-hash correctness cannot be checked
  at the wire/discovery level on this Humble container; it is only checkable
  offline against canonical definitions (as done here). If a future gate wants
  discovery-level RIHS01 validation, it needs an Iron+ subscriber.
- **Unchecked `ECarlaServerResponse` in `CarlaEngine.cpp`.**
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Game/CarlaEngine.cpp:477` calls
  `View->GetVehicleControl(VehicleControl)` and ignores the returned
  `ECarlaServerResponse`, unlike the sibling call site
  `Actor/ActorDispatcher.cpp:263`, which gates on
  `== ECarlaServerResponse::Success`. On failure the control struct keeps its
  zero default and `vehicle_status` would publish a zero control. The failure
  branch is unreachable for an actor already confirmed to be a registered
  vehicle, so this is recorded as a handoff note rather than changed here.
- **Odometry `twist` frame mismatch.** In
  `LibCarla/source/carla/ros2/ROS2.cpp` (~lines 801-806) the odometry
  `twist.linear` is expressed in the body frame while `twist.angular` is
  world-axis-mapped (deg->rad plus a y/z sign flip, with no rotation into the
  body frame). `nav_msgs/msg/Odometry` specifies both in `child_frame_id`. The
  discrepancy is negligible for a level ground vehicle (world-z ~= body-z, yaw
  dominates) and is faithful to upstream PR #9787, so it should be reconciled
  with #9787's semantics rather than patched on this branch.

## G0 verdict: PASS

What was proven, by evidence pointed at above:

- **Visibility, typing, QoS, deserializability:** all 8 contract topics present,
  correctly typed, QoS-correct where pinned, and echo-deserialized from inside
  the Autoware (Humble, `rmw_cyclonedds_cpp`) container — `run_g0.sh` reproduced
  8/8 pass, exit 0.
- **Type-hash correctness (offline):** the four required message hashes CARLA
  embeds equal the canonical REP-2011 RIHS01 hashes (computed via
  `compute_type_hash.sh`, cross-checked against Jazzy's installed JSON for the
  standard types); the by-name golden gtest gate is green (1 test, exit 0).

What was **not** proven, stated honestly:

- **Discovery-level type-hash verification** was not performed and is not
  possible on this container: Humble ships no RIHS01 machinery, so the type-hash
  guarantee rests entirely on the offline computation matching the pinned
  literals — not on anything the container observed on the wire.
- **Lidar cadence** is not validated (liveness only).
- Quantitative fidelity of the zeroed `CarlaEgoVehicleInfo` physics fields is not
  claimed.

On the G0 contract as scoped ("visible, deserializable and QoS/type-hash-correct
from inside an Autoware container", with type-hash-correct interpreted as the
offline check the Humble environment permits), **G0 is a PASS** and is a **go**
for the next plan.

## Branch history (Phase A)

`git log --oneline --first-parent 601966371..HEAD` on the integration branch
(base `upstream/ue5-dev` = `601966371`; do not use the local `ue5-dev` branch,
which carries an extra local-only fork-CI commit):

```text
288bc9b1c fix(ros2): define ego vehicle publisher constructors in Ros2Native so middleware creation succeeds
7606c2db4 feat(ros2): port ego vehicle status/info and odometry publishers from #9787 (TF tree excluded)
9afb44ce3 feat(ros2): port publisher durability QoS and latched map topic from #9786
8d53a45f9 chore: integration stack of preconditions complete (#9757 #9758 #9807-#9816)
e9ac71be5 merge: stack draft PR #9816 (#9762 series) [precondition]
4dd47d40f merge: stack draft PR #9815 (#9762 series) [precondition]
011aebeb6 merge: stack draft PR #9814 (#9762 series) [precondition]
6f4f2a67e merge: stack draft PR #9813 (#9762 series) [precondition]
7da55ab5b merge: stack draft PR #9811 (#9762 series) [precondition]
5243f281c merge: stack draft PR #9810 (#9762 series) [precondition]
936ddbca2 merge: stack draft PR #9809 (#9762 series) [precondition]
c0243d160 merge: stack draft PR #9808 (#9762 series) [precondition]
d7905e3fa merge: stack draft PR #9807 (#9762 series) [precondition]
2147aabd2 merge: stack draft PR #9758 (WalkerManager null guard) [precondition]
796a7124a merge: stack draft PR #9757 (V2X sensor family) [precondition]
```

The history reads as expected: 11 stack merges + the completion commit
(`8d53a45f9`) -> #9786 port -> #9787 port -> the ego-publisher fix
(`288bc9b1c` = current HEAD). Phase A is complete.
