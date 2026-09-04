# PR candidates for `carla-simulator/carla` `ue58-dev` (from Phases 0-1)

Each entry becomes one fork-staged draft PR (`youtalk/carla`, base `ue58-dev`)
and then one upstream PR, per the spec's "one PR = one defect or one generality
gap, with live evidence" rule.

Status legend: `evidence` (reproduced live, no fix written yet), `fix-local`,
`fork-pr` (draft PR open on `youtalk/carla`, awaiting fork CI before an upstream
PR is proposed), `upstream-pr`, `retired` (closed by upstream, no PR needed).

**Updated at the end of Phase 2 (2026-09-04).** Candidates 1-6, 9, 10, 12, 13 and
14 are now `fork-pr`: nine draft PRs, `youtalk/carla` **#25-#33**, linked as stack
**#34** with base `ue58-dev`. They are drafts on purpose and their `Ubicloud-PR`
checks cannot pass until the UE 5.8 toolchain image is published - see
`~/ue58-logs/handoff/phase2/README.md`. No upstream PR has been opened; the
upstream side is a hand-off. Candidates 18-24 were found during Phase 2 and have
no PR yet. Gate results are in `phase2-gates.md`.

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
survive the reordering. Candidates 1-17 are from Phases 0-1 and keep their
value order; 18-24 are appended in Phase 2 discovery order. 23 live candidates
and 1 retired.

| #   | Ledger | Title                                                                                                                                                                                                                                                                                                                                                                                       | Upstream file(s)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Evidence                                                                                                                                                                                                                                                                                                                                                 | Status                                                                                                                                                                                                                                                                                                                                                                 |
| --- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | 12     | The README's only documented goal is 19.4 m off the nearest lane centreline, so a verbatim run comes up healthy and then silently refuses to drive                                                                                                                                                                                                                                          | `av_stacks/README.md:195`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | `run1/autoware.log:1723, 1725-1726, 1730-1731`, `23-live-run.log`, `28-goal-xcheck.txt`, `24-metrics.txt`                                                                                                                                                                                                                                                | **`fork-pr`** - [#26](https://github.com/youtalk/carla/pull/26), `docs/ue58-autoware-readme-goal`; the replacement goal drove to ARRIVED in all three Phase 2 cells                                                                                                                                                                                                    |
| 2   | 15     | The shipped Town10HD lanelet2 map references the shared centre linestring of each opposing-lane pair un-inverted from both lanelets, so 17 of 160 road lanelets have their bounds ordered against travel `[CORRECTED]`                                                                                                                                                                      | `av_stacks/map_tools/maps/Town10HD/lanelet2_map.osm` (tracked in-repo, 11.3 MB); producer to be determined before filing                                                                                                                                                                                                                                                                                                                                                                                   | `31-lanelet-bound-orientation.txt`, `run3/autoware.log:1141, 1172, 1173, 1185`, `run4/autoware.log:1099-1106`, `29-groundtruth.txt`, `33-run4-route-selection.txt`, plus the re-derivation in this file                                                                                                                                                  | **`fork-pr`** - [#25](https://github.com/youtalk/carla/pull/25), `fix/ue58-lanelet2-shared-bounds`; **scope corrected to preventive**, see the correction note below                                                                                                                                                                                                   |
| 3   | 5      | `fixup_centerpoint_layout()` returns silently when the model directory is absent, so the one case that matters produces no warning and defers the consequence to a hard ONNX-load failure inside a much later live run                                                                                                                                                                      | `av_stacks/install/install_autoware.sh:388-389`                                                                                                                                                                                                                                                                                                                                                                                                                                                            | `21-autoware-docker.log` (no centerpoint section emitted at all), `20-autoware-check.log:30`                                                                                                                                                                                                                                                             | **`fork-pr`** - [#33](https://github.com/youtalk/carla/pull/33), `fix/ue58-installer-check` (commit 2 of 3)                                                                                                                                                                                                                                                            |
| 4   | 4      | `install_autoware.sh --check` presents as a prerequisite report but probes neither the 64 MB UDP socket buffers nor the NVIDIA container runtime, both of which the README documents as required                                                                                                                                                                                            | `av_stacks/install/install_autoware.sh:222-311` (`do_check`); `rmem_max` appears only as heredoc prose at `:633`                                                                                                                                                                                                                                                                                                                                                                                           | `20-autoware-check.log`                                                                                                                                                                                                                                                                                                                                  | **`fork-pr`** - [#33](https://github.com/youtalk/carla/pull/33), `fix/ue58-installer-check` (commit 1 of 3); the probe cannot make `--check` _fail_, which is candidate 21                                                                                                                                                                                             |
| 5   | 6      | Two of the four expected centerpoint filenames the installer lists (`pts_voxel_encoder.onnx`, `pts_backbone_neck_head.onnx`) are bare names, stale against the `_centerpoint`-suffixed names the shipped launcher hardcodes; the other two entries already carry their variant suffix or need none                                                                                          | `av_stacks/install/install_autoware.sh:85-90` (`CENTERPOINT_FLAT_FILES`)                                                                                                                                                                                                                                                                                                                                                                                                                                   | `20-autoware-check.log:30`, plus in-image `perception.launch.xml:176-183` and `e2e_simulator.launch.xml:8` from digest `sha256:9c7d51a8...`                                                                                                                                                                                                              | **`fork-pr`** - [#33](https://github.com/youtalk/carla/pull/33), `fix/ue58-installer-check` (commit 3 of 3); parameterised on `CENTERPOINT_MODEL_NAME` (default `centerpoint_tiny`), because the launcher's suffix is `$(var model_name)` and a flat `_centerpoint` suffix would misreport the default model. The same wrong names in the two READMEs are candidate 23 |
| 6   | 2      | The "do not use `-rmw=cyclonedds` on the simulator" warning is stale: `b9c33737a` fixed the fragmented-receive bug, and a full CycloneDDS-on-simulator run reaches ARRIVED                                                                                                                                                                                                                  | `av_stacks/README.md:431-439`; `av_stacks/run/run_carla_autoware.sh:23-24, 81, 121-122, 608-609`                                                                                                                                                                                                                                                                                                                                                                                                           | `25-cyclonedds-sim.log`, `25c/25d-metrics-cyclonedds-block1/2.txt`, `25e-final-state-cyclonedds.txt`, `run2/carla_server.log:523`, `run2/autoware.log:1105`, `26-probes.txt` PROBE2                                                                                                                                                                      | **`fork-pr`** - [#27](https://github.com/youtalk/carla/pull/27), `docs/ue58-cyclonedds-note`; strengthened by Phase 2 cell `J-cyclonedds` (4/4 gates PASS), within the claim boundary in `phase2-gates.md`                                                                                                                                                             |
| 7   | 17     | The simulator process exits with SIGSEGV on teardown SIGTERM, on every live run and under both middlewares                                                                                                                                                                                                                                                                                  | not localized; entry point is the editor `-game` shutdown path                                                                                                                                                                                                                                                                                                                                                                                                                                             | `23-live-run.log`, `27-live-run-goal2.log`, `28-live-run-clean-spawn.log` (fastdds) and `25-cyclonedds-sim.log` (cyclonedds), each ending `run/run_carla_autoware.sh: line 314: <pgid> Segmentation fault (core dumped)`; also `23-live-run.attempt1-wheelmismatch.log`                                                                                  | `evidence` - reconfirmed in all three Phase 2 cells; established as a recurring, pre-existing, benign UE5-on-SIGTERM quirk rather than instability in this build, so it stays unfiled pending diagnosis                                                                                                                                                                |
| 8   | 1      | MGRS offset is content-only: no runtime fallback exists when a level has no `UMgrsDataAsset`, and the Autoware game mode's no-asset branch also skips `ParseOpenDrive()` and `StoreSpawnPoints()`                                                                                                                                                                                           | `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Sensors/AutowareGnssSensor.cpp:110-136`; `.../Autoware/Game/AutowareWorldSettings.h:28-29`; `.../Autoware/Game/AutowareGameModeBase.cpp:40-43` (the skipped `Super::LoadGeoReference()` is `.../Game/CarlaGameModeBase.cpp:232-240`, which is where `ParseOpenDrive()` and `StoreSpawnPoints()` run); `.../Actor/ActorBlueprintFunctionLibrary.cpp:1485-1490` and `:2380`; `LibCarla/source/carla/ros2/publishers/AutowareGNSSPublisher.cpp:60-62` | `26-probes.txt` PROBE1, `run2/carla_server.log:3289`                                                                                                                                                                                                                                                                                                     | `evidence` (blocked on a Phase 3 live need; Town10HD is `projector_type: Local`, so neither Phase 1 nor Phase 2 exercised it)                                                                                                                                                                                                                                          |
| 9   | 9      | The ROS 2 smoke suite hardcodes RPC port 3654 with no override, so it cannot run against the simulator port the Autoware flow uses                                                                                                                                                                                                                                                          | `PythonAPI/test/smoke/__init__.py:23`                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | `task-6-report.md:11-15` (5 x `RuntimeError: Connection refused` against a `-carla-rpc-port=2000` simulator); `14-smoke-ros2.log` / `smoke.out` (`Ran 5 tests in 131.546s` / `OK` once relaunched on 3654)                                                                                                                                               | **`fork-pr`** - [#29](https://github.com/youtalk/carla/pull/29), `feat/ue58-smoke-port-env`; observed working live in Phase 2 (`CARLA_SMOKE_PORT=2000` redirected the suite and `test_version` passed). Hitting it against an editor server exposes candidate 19                                                                                                       |
| 10  | 7      | `autoware_demo.py` hardcodes `client.set_timeout(60.0)` with no override; a cold-start `get_world()` measured 65.9 s on this machine and the demo failed with `RuntimeError: std::exception`                                                                                                                                                                                                | `PythonAPI/examples/autoware_demo.py:758`                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | `task-5-report.md:85-110` (traceback at `autoware_demo.py:559`, then a 180 s-timeout probe reporting `get_world OK in 65.9s`)                                                                                                                                                                                                                            | **`fork-pr`** - [#30](https://github.com/youtalk/carla/pull/30), `feat/ue58-demo-timeout`; its Python-side guard against a non-positive `--timeout` works around candidate 20, the underlying C++ cast                                                                                                                                                                 |
| 11  | 8      | `autoware_demo.py` ignores `SIGINT` (blocked in `futex_do_wait` inside the LibCarla tick), so an orphaned client needs `SIGKILL`; the tick loop should be interruptible                                                                                                                                                                                                                     | `PythonAPI/examples/autoware_demo.py` (tick loop)                                                                                                                                                                                                                                                                                                                                                                                                                                                          | `task-5-report.md:354-362` (two `SIGINT`s ~25 s apart ignored; the simulator itself exited cleanly on the same signal)                                                                                                                                                                                                                                   | `evidence` - root cause still unknown; `run_sync_simulation_loop` already catches `KeyboardInterrupt`, so the hang is inside the C++ tick and needs its own investigation                                                                                                                                                                                              |
| 12  | 13     | The run script's preflight checks that `carla` imports but never which build it is; a wheel from a foreign worktree aborted `load_town` with `std::bad_array_new_length` after a 15-minute setup                                                                                                                                                                                            | `av_stacks/run/run_carla_autoware.sh:739-751`                                                                                                                                                                                                                                                                                                                                                                                                                                                              | `23-live-run.attempt1-wheelmismatch.log`                                                                                                                                                                                                                                                                                                                 | **`fork-pr`** - [#32](https://github.com/youtalk/carla/pull/32), `feat/ue58-run-wheel-provenance`; the new preflight fired correctly on its first live outing in Phase 2                                                                                                                                                                                               |
| 13  | 11     | No `--server-args` passthrough to the editor fallback, and `-nosound` / `-log` are not defaulted, so the reproduction cannot be given the flags Phase 0 proved working without editing the script                                                                                                                                                                                           | `av_stacks/run/run_carla_autoware.sh:815-816` (`SERVER_FLAGS`, defined at `:815` and appended to at `:816`)                                                                                                                                                                                                                                                                                                                                                                                                | `22-dry-run.log`, `11-launch-cmd.txt`                                                                                                                                                                                                                                                                                                                    | **`fork-pr`** - [#31](https://github.com/youtalk/carla/pull/31), `feat/ue58-run-server-args`; two commits, kept separately revertable                                                                                                                                                                                                                                  |
| 14  | 14     | CARLA's native ROS 2 PointCloud2 publisher sets `is_dense = false`, which Autoware's cloud validator warns on and says will become a hard error                                                                                                                                                                                                                                             | `LibCarla/source/carla/ros2/publishers/CarlaPointCloudPublisher.cpp:107-110`                                                                                                                                                                                                                                                                                                                                                                                                                               | `run1/autoware.log` (99 x `[sensing.lidar.top.crop_box_filter_self]: Invalid PointCloud: is_dense is false`), and it recurs throughout `run4/autoware.log`                                                                                                                                                                                               | **`fork-pr`** - [#28](https://github.com/youtalk/carla/pull/28), `fix/ue58-pointcloud-is-dense`; **after-count 0 in all three Phase 2 cells** against a before-count of 99, non-vacuity argued per cell in `phase2-gates.md`. Its build-graph hazard is candidate 24                                                                                                   |
| 15  | 10     | `run_carla_autoware.sh` never forwards `DLSS_SDK` to the editor fallback; only `FASTRTPS_DEFAULT_PROFILES_FILE` or `CYCLONEDDS_URI` enters `SIM_ENV`                                                                                                                                                                                                                                        | `av_stacks/run/run_carla_autoware.sh:803-805` (`SIM_ENV` construction), consumed at `:819` and `:821`                                                                                                                                                                                                                                                                                                                                                                                                      | `22-dry-run.log` (grep for `DLSS_SDK` returns 0)                                                                                                                                                                                                                                                                                                         | `evidence` (not a blocker: no DLSS features under `-RenderOffScreen`, and an exported value is inherited by `setsid bash -c`)                                                                                                                                                                                                                                          |
| 16  | 16     | Transient NDT scan-matching degradation fires 11 `EMERGENCY_STOP` events in an otherwise clean run; the ego drives through them, but the cause is undiagnosed                                                                                                                                                                                                                               | not localized; surfaced via `/autoware/localization/scan_matching_status`                                                                                                                                                                                                                                                                                                                                                                                                                                  | `run4/autoware.log:1236-1242` and the blocks at `:1266`, `:1296`, `:1378`; 11 operated / 11 cancelled                                                                                                                                                                                                                                                    | `evidence` (needs diagnosis before filing; may be an Autoware-side tuning issue rather than a CARLA defect)                                                                                                                                                                                                                                                            |
| 17  | 3      | `Map::GenerateChunkedMesh` empty-mesh guard (port of fork `a203b7ce4`)                                                                                                                                                                                                                                                                                                                      | `LibCarla/source/carla/road/Map.cpp:1323, 1330, 1344, 1361`                                                                                                                                                                                                                                                                                                                                                                                                                                                | `26-probes.txt` PROBE3                                                                                                                                                                                                                                                                                                                                   | **retired** - already upstream, see below                                                                                                                                                                                                                                                                                                                              |
| 18  | P2-a   | `carla-unreal-editor` does not build with `bUseUnityBuild=false`: four Carla-plugin files and two StreetMap files fail on transitive includes under `-Werror`, so a developer who disables unity builds (the setting that makes single-file edits cheap) cannot build the editor at all                                                                                                     | `Unreal/CarlaUnreal/Plugins/Carla/Source/...` (four files) and the StreetMap plugin (two files); exact list on the existing fix branches                                                                                                                                                                                                                                                                                                                                                                   | `~/ue58-logs/p2-17-build.log` (the `-game` sub-target fails RC=1 with IWYU/`-Werror` errors); the fixes already exist as `youtalk/carla` `fix/plugin-iwyu-unity-off` and `youtalk/StreetMap` `fix/iwyu-unity-off`, neither of which is on `ue58-dev`                                                                                                     | `evidence` - **a port, not an investigation**: replay the two existing fix branches onto `ue58-dev`. Did not block Phase 2, because the stack changes no plugin code and the affected editor binaries were proven current by a zero-diff `Unreal/` tree plus matching engine/plugin BuildIds                                                                           |
| 19  | P2-b   | `PythonAPI/test/smoke/__init__.py`'s `tearDown` unconditionally calls `load_world("Town03")`, which always throws against an editor `-game` single-map server, so smoke tests report `ERROR` **after having passed**                                                                                                                                                                        | `PythonAPI/test/smoke/__init__.py:38`                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | `~/ue58-logs/p2-17-smoke-port-override.log`: `test_version` runs, then `RuntimeError: std::exception` from `tearDown` at line 38, reported as `FAILED (errors=1)`                                                                                                                                                                                        | `evidence` - directly relevant to candidate 9 / PR #29, whose newly documented `CARLA_SMOKE_HOST`/`PORT` instructions lead straight into it; recorded as a known limitation in that PR's body                                                                                                                                                                          |
| 20  | P2-c   | `TimeDurationFromSeconds` casts a negative `double` to `size_t`, formally UB and empirically a near-maximum millisecond duration (`-5.0` becomes `18446744073709546616`), so a negative timeout hangs indefinitely with no diagnostic instead of erroring                                                                                                                                   | `PythonAPI/carla/include/PythonAPI.h:641-643`                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Cast compiled standalone (`g++ -O2`, x86_64) during the Task 7 review: `-5.0` -> `18446744073709546616`, `-0.001` -> `18446744073709551615`, `0.0` -> `0`                                                                                                                                                                                                | `evidence` - cross-cutting (`set_timeout`, `Tick`, `WaitForTick`, `ApplySettings` all share the helper), so it deserves its own PR rather than riding along with candidate 10, whose Python-side guard only closes the one call path it introduced                                                                                                                     |
| 21  | P2-d   | `install_autoware.sh --check` always exits 0, so it reports prerequisites but can never fail - it cannot serve as a CI gate or a scripted precondition                                                                                                                                                                                                                                      | `av_stacks/install/install_autoware.sh` (`do_check`)                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Read directly: `do_check` is informational by design, ends with `=== Check complete (nothing was modified) ===` and returns 0 even at 0/4 prerequisites satisfied                                                                                                                                                                                        | `evidence` - deliberately **out of scope** for candidate 4 / PR #33, which only made the reported text accurate; a non-zero exit (or a `--strict` mode) is a behaviour change that could break anyone already scripting it, so it needs its own PR                                                                                                                     |
| 22  | P2-e   | G3's reported control-cmd rate is the **last** rate window rather than a robust statistic, so a duplicate-timestamp burst window can dominate the printed figure                                                                                                                                                                                                                            | this repository: `scripts/e2e/measure_rates.py` / `scripts/e2e/gate_g3_performance.sh`                                                                                                                                                                                                                                                                                                                                                                                                                     | `phase2-gates.md`: `J-cyclonedds` reported 20.69 Hz (window 13 of 13) while its clean-window range is 19.997-20.023 Hz. Burst windows are identified by **std dev**, not by `min: 0.000s`: bursts sit at 0.00644-0.02019 s against 0.00060-0.00127 s for clean windows (a five-fold gap, so any threshold in 0.0013-0.006 s partitions all three cells identically). `min: 0.000s` misses the very window complained of here - 20.691 Hz has `min: 0.001s`, std dev 0.00880 s. Raw windows: `~/ue58-logs/p2-{17,18,19}-cell-*/gates/g3_control_hz.txt`                                                                                                                                                                                  | `evidence` - **extension-repo candidate, not a CARLA PR**. Deliberately not changed mid-series: swapping the measurement instrument between cells would have made the three cells non-comparable, which is worse than a fragile display figure. The verdict logic is unaffected (tolerance is +/-5 Hz). Fix as **median-of-windows over std-dev-filtered windows** - and only in that order, because both simpler forms are no-ops on the case cited: discarding `min: 0.000s` windows leaves 20.691 in the set, and a plain median over all 13 windows gives 20.686 Hz, because 7 of `J-cyclonedds`'s 13 windows are bursts and the median therefore lands inside them. Filtering on std dev first and then taking the median gives 20.002 Hz (`J-fastdds`), 19.999 Hz (`J-cyclonedds`) and 20.000 Hz (`H-fastdds`)     |
| 23  | P2-f   | Both READMEs, and the installer's own comment, document bare `pts_voxel_encoder.onnx` / `pts_backbone_neck_head.onnx` filenames that the shipped launcher never looks for - it resolves `pts_voxel_encoder_$(var model_name).onnx`                                                                                                                                                          | the two `av_stacks` READMEs documenting the centerpoint model files                                                                                                                                                                                                                                                                                                                                                                                                                                        | In-image `lidar_centerpoint.launch.xml`, read from `universe-cuda-jazzy`; the installer's own `CENTERPOINT_FLAT_FILES` was corrected in candidate 5 / PR #33, the READMEs were deliberately left alone                                                                                                                                                   | `evidence` - a documentation defect distinct from the `--check` probe; kept out of PR #33 rather than swelling a three-commit PR                                                                                                                                                                                                                                       |
| 24  | P2-g   | `carla-ros2-native-lib` has no `BUILD_ALWAYS`, and its build stamp depends only on its configure stamp, so an edit under `LibCarla/source/carla/ros2/publishers/` is invisible to `--target carla-server`. Worse, the post-build staging copy re-runs whenever any stamp is newer, so a stale build still re-copies an old `.so` and **prints activity** - it manufactures false confidence | `Ros2Native/CMakeLists.txt` (`ExternalProject_Add(carla-ros2-native-lib ...)`); observable at `Build/Development/build.ninja`                                                                                                                                                                                                                                                                                                                                                                              | `grep -rn BUILD_ALWAYS` over the project returns nothing; the `carla-ros2-native-lib` build edge in `build.ninja` names no `carla/ros2/**` source. Worked around in Phase 2 by building the sub-project directly and requiring a `Building CXX object .../CarlaPointCloudPublisher.cpp.o` line, then asserting the staged `.so` is newer than the source | `evidence` - the durable fix (`BUILD_ALWAYS 1`) is a legitimate separate PR; it did not belong in candidate 14's one-flag change                                                                                                                                                                                                                                       |

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

> **`[CORRECTED]` 2026-09-04, after Phase 2. Read this before citing anything
> below it.** The structural defect is confirmed and the repair shipped, but the
> _causal_ story this section tells - malformed bounds cause backward planning,
> emergency stops and a ~20 % spawn failure rate - was **falsified by this
> campaign's own logs** and is withdrawn. What survives: 17 of 160 road lanelets
> (17 of 246 relations) reference a shared bound ordered against travel, the
> legacy 2019 map has 0 of 168, and the generator reproduces the repaired map
> byte-identically. What does not: on the _fixed_ map `Backward path is NOT
supported` still occurred 290 and 190 times, the _unfixed_ map produced the
> identical route from a pose 0.024 m away and halted at the same metre by the
> same mechanism, and a static `lanelet2` probe showed `geometry::align` already
> recovers the correct orientation for **all 17** today, with the derived
> centreline and the routing graph unchanged. **The fix is preventive**: it
> removes a dependence on a loader heuristic that currently guesses right.
> PR #25's body cites no live-drive evidence at all, on purpose. Do not re-add
> "fixes Backward path", any emergency-stop claim, any failure rate, or a
> "377 -> 0". Full corrected record: `phase2-gates.md` and
> `~/ue58-logs/p2-03-evidence.md` - **not** `~/ue58-logs/24-metrics.txt`, whose
> body still carries the withdrawn narrative below its correction header.

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

| Message                                                               | Count                                                                                                                   | Emitting node(s)                                                                   |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `Backward path is NOT supported, just returning input path`           | **377 total**                                                                                                           | `behavior_velocity_planner` 171, `elastic_band_smoother` 103, `path_optimizer` 103 |
| `Caution! Invalid Trajectory published.`                              | 166                                                                                                                     | `planning_validator`                                                               |
| `planning trajectory is too far from ego in longitudinal direction!!` | 166                                                                                                                     | `planning_validator`                                                               |
| `EMERGENCY_STOP is operated.`                                         | 171 operated / 172 canceled, **nothing latched** `[CORRECTED]`; median cycle 2.200 s, not the ~100 ms originally stated | `mrm_handler`                                                                      |
| `Emergency!`                                                          | 427                                                                                                                     | `control.vehicle_cmd_gate`                                                         |

The comparison below was originally offered as the controlled evidence a
maintainer would want. **`[CORRECTED]` It is not controlled**: Phase 2 re-ran the
same spawn and goal on the _repaired_ map three times and got one ARRIVED and two
failures with 290 and 190 `Backward path` occurrences, so the run 3 / run 4 split
is not attributable to the map. It is retained as a record of what was observed,
not as a causal argument.

| Signature                                    | run 3 (started inside malformed `12236`)                                                                                 | run 4 (started inside clean `5013`)                 |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------- |
| `Backward path is NOT supported`             | 377                                                                                                                      | 0                                                   |
| `Invalid Trajectory published`               | 166                                                                                                                      | 0                                                   |
| `too far from ego in longitudinal direction` | 166                                                                                                                      | 0                                                   |
| `EMERGENCY_STOP is operated`                 | 171 operated / 172 canceled, nothing latched `[CORRECTED]`                                                               | 11, all self-cancelled                              |
| Outcome                                      | trajectory pinned 118 m behind the ego, running west with negative velocity; never turned; stopped 17.75 m from the goal | drove the full 7-lanelet route, both turns, ARRIVED |

#### Blast radius: roughly one spawn point in five `[CORRECTED]`

> The arithmetic below is sound as _geometry_ - about one spawn in five does sit
> inside one of the 17 lanelets - but it was written as a failure-rate estimate,
> and there is **no demonstrated failure** to project. The `align()` probe found
> the loader already resolves all 17 correctly. Read this as the size of the
> affected map region, never as an expected failure rate.

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

Reality check that favours the higher figure: run 3's own start pose lies
inside `12236`, and Autoware did in fact route from `12236`. **`[CORRECTED]` The
"1.46 m from spawn index 129" originally stated here is wrong** - `mission_planner`
logs the initial pose at 6 dp (`GATE1` prints 2 dp, which is what the original
reading used), and the two poses are **0.024 m** apart. Maximum spread across all
four Phase 2 runs of that pose: 0.0414 m, and it does not sort by outcome.

#### Before filing - all four resolved in Phase 2 `[CORRECTED]`

> **Producer established:** regenerating from `~/ue58-logs/Town10HD_Opt.xodr` with
> the pristine generator reproduces the same 17 ids, pinning the producer to
> `commonroad-scenario-designer` 0.8.5 plus the current
> `generate_lanelet2_map.py`. A report for that project is drafted at
> `~/ue58-logs/handoff/phase2/crdesigner-issue.md` and **not filed** - it is a
> hand-off, since this campaign was not authorised to open issues there.
> **Target repository:** CARLA carries the workaround (a `--fix` post-processor in
> `map_tools`) because it ships the affected artefact; the upstream generator
> defect is reported separately.
> **Demonstration:** attempted and it _falsified_ the causal claim - see the
> correction banner at the top of this section. The repair now ships on its
> structural case plus a QC tool, with no drive-level claim.
> **Other artefacts:** `lanelet2_map_2019_legacy.osm` was scanned - **0 of 168**,
> and 9214 of 9214 of its nodes carry `local_x`/`local_y`, so the control is a
> real result rather than a vacuous pass. Every other town remains unmeasured;
> Town10HD is still the only map shipped in-tree under `map_tools/maps/`.

Retained for the record, as originally written:

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
