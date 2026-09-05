# Phase 3 — Nishi-Shinjuku gate results and the MGRS-offset fallback

Three live gate cells plus one behavioural probe, run 2026-09-04/05 on the AWSIM
v2.0.0 Nishi-Shinjuku map against CARLA's in-tree Autoware layer on UE 5.8,
measured with this repository's `scripts/e2e/run_gates.sh`. Both MGRS-offset
sources — the level's `UMgrsDataAsset` and the new blueprint fallback — drive the
full closed loop to ARRIVED with G1, G2 and G3-LiDAR passing; the level's asset is
proven to win over a deliberately divergent blueprint value. One gate verdict
fails: G3 control in the Humble cell, at 36.33 Hz. That failure is a property of
how the gate scores its measurement, not of Humble — the diagnosis is in "The G3
control gate is single-sample-scored" below, and the gate was deliberately **not**
changed this phase.

This file is the authoritative Phase 3 record. Where a per-task report and this
file disagree, this file wins: several reports were corrected more than once
during the run, and the final state of each correction is what is written here.

## Versions

| Component           | Value                                                                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| CARLA (cells)       | `youtalk/carla` `feat/ue58-gnss-mgrs-fallback` `ef6d25875`                                                                                 |
| CARLA stack, bottom | `feat/ue58-run-map-origin` `6ad5c65a7` -> `feat/ue58-demo-spawn-pose` `e02fa4dbc` -> `feat/ue58-gnss-mgrs-fallback` `ef6d25875`            |
| CARLA stack base    | `feat/ue58-autoware-layer` `47ecc5cb8`                                                                                                     |
| CARLA upstream base | `upstream/ue58-dev` `5f58df57998030cb602a0fc588db6cc5b8a23988`                                                                             |
| Engine              | `CarlaUnreal/UnrealEngine@ue58-dev-carla` `cacb25b99f14` (5.8)                                                                             |
| Content             | `carla-content@ue58-dev-carla` `981cdcbae2`, **plus the untracked Nishi-Shinjuku pack** (see below)                                        |
| `DA_MGRS_Shinjuku`  | offset `x=81655.730000 y=50137.430000 z=42.499980` m, grid `54SUE`, name `Shinjuku` (`~/ue58-logs/p3/08-summary.md`)                       |
| AWSIM map           | `Shinjuku-Map.zip` v2.0.0, 129,585,415 bytes, CC BY-NC 4.0 — referenced in place, never committed                                          |
| Autoware (Jazzy)    | `ghcr.io/autowarefoundation/autoware:universe-cuda-jazzy` `sha256:9c7d51a820a0…` (`~/ue58-logs/21-autoware-docker.log`)                    |
| Autoware (Humble)   | `ghcr.io/autowarefoundation/autoware:universe-cuda-humble` `sha256:724c2049897d…` (`~/ue58-logs/p3-12-cell-nishi-humble/image-digest.txt`) |
| Gates               | this repository, `feat/ue58-nishishinjuku` `c5842b4`, off `feat/ue58-gates` `e0d772a`                                                      |

**Two SHAs above were superseded after the work they name was done, and both
supersessions are content-preserving.** On the gates side the cells ran
`feat/ue58-nishishinjuku` `4b52e7d`, which a later `ruff format` fix replaced with
`c5842b4`; the two differ only by three re-wrapped `log()` calls in
`scripts/nishishinjuku/wire_mgrs_asset.py`, which no gate runs, so every gate
script is byte-identical between them (`git diff 4b52e7d c5842b4` touches that one
file). On the CARLA side `feat/ue58-gnss-mgrs-fallback` `ef6d25875` — the commit
the cells ran — was amended to `927a0eb00` before hand-off, adding the
`CHANGELOG.md` entry and renaming `parse_map_origin` to `parse_mgrs_offset` plus
two test names; `git diff ef6d25875 927a0eb00 -- Unreal/` is empty, so no plugin
C++ changed and every measurement below carries over unaltered.

Logs are local only, under `~/ue58-logs/p3/` (offline steps and probes) and the
per-cell directories `~/ue58-logs/p3-10-cell-nishi-content/`,
`~/ue58-logs/p3-11-cell-nishi-fallback/`, `~/ue58-logs/p3-12-cell-nishi-humble/`
and `~/ue58-logs/p3-10b-precedence/`, with per-cell harness logs
`~/ue58-logs/p3-1{0,1,2}-cell.log` and summaries `~/ue58-logs/p3-1{0,1,2}-summary.md`.

## The map and its two states

`NishishinjukuMap.umap` is CC BY-NC content and is **not** in this repository or in
CARLA's. Two states of it were used, hashed at every transition:

| State    | `sha256` (first 8) | Meaning                                                     |
| -------- | ------------------ | ----------------------------------------------------------- |
| pristine | `7bb76f1e`         | `AutowareWorldSettings.MgrsDataAsset` soft pointer is unset |
| wired    | `24ca4ea4`         | `DA_MGRS_Shinjuku` assigned to that soft pointer, 3.3 MB    |

Backups: `~/ue58-logs/p3/NishishinjukuMap.umap.pristine` and `…umap.wired`.
`~/ue58-logs/p3/00-umap-pristine.sha256` records **only** the pristine hash
(twice — once for the live file and once for the backup, captured before any
wiring). The wired hash is not in any recorded file: it is obtained by hashing
`…umap.wired` or the live `.umap` directly, and both read `24ca4ea4…` today.
This asymmetry is also why the plan's umap-state guards never worked; see "Plan
defects found during Phase 3".

**Why the fallback exists.** On the pristine level the soft pointer is empty, and
the editor's own `RepairWorldSettings` path re-creates the `AWorldSettings` object
without carrying it over. Captured directly before wiring, in
`~/ue58-logs/p3/08-summary.md`:

```text
World settings (before apply): class: AutowareWorldSettings, soft_ptr: None
```

and at runtime, in `~/ue58-logs/p3/02-server-grep.txt` (that file is three lines
long — the `4763:` inside it is a `grep -n` prefix from the simulator log the grep
was taken over, `~/ue58-logs/p3/sim.log`, which later probes overwrote: it now
holds the 07:02 `N-precedence` run, not the 04:37 one these lines came from):

```text
LogCarla: Warning: MGRS Data Asset SoftPtr not set in WorldSettings.
```

So an MGRS map arrives with no offset unless somebody re-wires the level asset by
hand. `scripts/nishishinjuku/wire_mgrs_asset.py` is the editor-Python tool that
does the wiring (it survives an editor reload — re-inspected in
`~/ue58-logs/p3/08b-wire-reinspect.log`); the blueprint fallback on
`sensor.other.autoware_gnss` is the runtime alternative that does not need it.

## Poses

Nishi-Shinjuku exposes exactly **one** CARLA spawn point, so no pose can be picked
freely from the map's own list; `scripts/e2e/lanelet_pose.py` derives poses from
the lanelet2 geometry instead and the live run cross-checks them against CARLA's
OpenDRIVE waypoints.

| Pose  | lanelet | s (m)  | off-centre | CARLA `x, y, yaw`            | map `x, y`             |
| ----- | ------- | ------ | ---------- | ---------------------------- | ---------------------- |
| SPAWN | 255     | 7.477  | 0.012 m    | `-278.383, 220.550, -33.780` | `81377.347, 49916.880` |
| GOAL  | 226     | 23.300 | 0.000 m    | `-84.114, 117.602, -10.442`  | `81571.616, 50019.828` |

Sources: `~/ue58-logs/p3/11-spawn-derivation.txt`, `~/ue58-logs/p3/10-goal-derivation.txt`.

Live OpenDRIVE cross-check (`Map.get_waypoint`, `lane_type=Driving`), from
`~/ue58-logs/p3/12-poses.txt`, against thresholds of 0.5 m and 5 deg:

| Pose  | nearest waypoint            | road / lane | lateral dist | dyaw       |
| ----- | --------------------------- | ----------- | ------------ | ---------- |
| SPAWN | `-278.366, 220.557, -1.227` | 108 / 2     | **0.018 m**  | **+0.09°** |
| GOAL  | `-84.079, 117.594, -0.366`  | 91 / 2      | **0.036 m**  | **−0.04°** |

The final spawn pose adds the live ground height: `cast_ray` returns
`ground_z = -1.274694800376892`, and `SPAWN_POSE="-278.383,220.550,-0.975,-33.780"`
is that plus 0.3 m (`~/ue58-logs/p3/12-poses.txt`).

Offline, the derived goal reproduces the historically recorded goal to 1 mm and
0.012 deg: lanelet 226 at `s = 23.3` gives map `(81571.616, 50019.828, 10.442°)`
against the recorded `(81571.616, 50019.827, 10.43°)`.

### The "7.478 m off-lane" premise is dead

The extension-era record held that Nishi's single spawn point sits **7.478 m** off
the lanelet2 centreline, and that `mission_planner` therefore routes on the
neighbouring lane and never reaches a goal. **Four independent measurements
contradict it**, and every commit message and PR body in this phase was rewritten
to stop asserting it:

| Measurement                                                             | Value       | Source                                   |
| ----------------------------------------------------------------------- | ----------- | ---------------------------------------- |
| Distance to the nearest OpenDRIVE driving-lane waypoint (live)          | **0.030 m** | `~/ue58-logs/p3/01-map-probe.txt`        |
| Off-centre distance on the lanelet2 centreline of lanelet 255 (offline) | **0.012 m** | `~/ue58-logs/p3/11-spawn-derivation.txt` |
| Live lateral distance of the derived spawn pose to its waypoint         | **0.018 m** | `~/ue58-logs/p3/12-poses.txt`            |
| Live yaw difference of the same                                         | **+0.09°**  | `~/ue58-logs/p3/12-poses.txt`            |

The `--spawn_pose` feature survives the correction on its own justification —
imported maps expose no curated spawn points, Nishi exposes exactly one, and the
cells need a specific reproducible pose — but **no text may claim the spawn point
is off-lane**.

A second inherited "fact" was also falsified: the plan states that
`world.get_ego_spawn_points()` does not exist on the server. It does, and returns
1 on this build (`ego_spawn_points: 1`, `~/ue58-logs/p3/01-map-probe.txt`).

## Cells

Every gate cell: `--mode classical --stack docker --server editor --town
NishishinjukuMap`, `--spawn-pose "-278.383,220.550,-0.975,-33.780"`,
`--goal "-84.114,117.602,-10.442"`, `--map-origin "81655.73,50137.43,42.49998"`,
`ROS_DOMAIN_ID=42`, Fast DDS, gates run with `--lidar-hz 10 --g2-window 420` and
`SETTLE_S` at its default 20 s, on the same CARLA build with **no rebuild between
cells**. Gates were triggered on the `autonomous mode engaged` line in the runner's
own stdout, at zero latency (`ENGAGED_SEEN == GATES_START` in every cell's
`wallclock.txt`).

| Cell           | level state | offset source                                    | ROS distro | G1 NDT max | G2 closest | G3 LiDAR | G3 control   | routing/state | Verdict               |
| -------------- | ----------- | ------------------------------------------------ | ---------- | ---------- | ---------- | -------- | ------------ | ------------- | --------------------- |
| `N-content`    | wired       | level data asset                                 | Jazzy      | 0.198 m    | 0.081 m    | 10.00 Hz | 20.00 Hz\*   | 3 = ARRIVED   | **PASS**              |
| `N-fallback`   | pristine    | blueprint fallback                               | Jazzy      | 0.139 m    | 0.075 m    | 10.00 Hz | 20.00 Hz\*   | 3 = ARRIVED   | **PASS**              |
| `N-humble`     | wired       | level data asset                                 | Humble     | 0.297 m    | 0.075 m    | 10.00 Hz | **36.33 Hz** | 3 = ARRIVED   | **FAIL** (G3 control) |
| `N-precedence` | wired       | asset, with a divergent blueprint value supplied | Jazzy      | —          | —          | —        | —            | —             | probe, no gates       |

Thresholds: G1 < 1.0 m, G2 < 1.0 m, G3 LiDAR 10 ± 1 Hz, G3 control 20 ± 5 Hz.
Verdict files: `~/ue58-logs/p3-1{0,1,2}-cell-nishi-*/gates/gates.txt` and
`…/gates/routing_state.txt`.

\* Both Jazzy PASSes are **lucky final windows**, not clean series. See "The G3
control gate is single-sample-scored".

The one `gnss-source.txt` line per cell — the direct evidence of which branch of
`AutowareGnssSensor::LoadMgrsData()` executed:

`N-content` (`~/ue58-logs/p3-10-cell-nishi-content/gnss-source.txt`), two lines at
the identical timestamp:

```text
LogCarla: AutowareGnssSensor: MGRS offset from level data asset (81655.730000, 50137.430000, 42.499980)
LogCarla: Warning: AutowareGnssSensor: level data asset present; ignoring blueprint mgrs_offset (81655.730000, 50137.430000, 42.499980)
```

`N-fallback` (`~/ue58-logs/p3-11-cell-nishi-fallback/gnss-source.txt`):

```text
LogCarla: AutowareGnssSensor: no MGRS data asset in WorldSettings; using blueprint mgrs_offset fallback (81655.730000, 50137.430000, 42.499980)
```

`N-humble` (`~/ue58-logs/p3-12-cell-nishi-humble/gnss-source.txt`): identical to
`N-content` to six decimals.

In `N-content` and `N-humble`, `MGRS Data Asset SoftPtr not set` appears 0 times;
in `N-fallback`, so do both of the data-asset lines. Each cell's grep is
corroborated in both `carla_server.log` and the engine's own log at the same
timestamp and frame.

**The engage precheck is the second, independent witness** and is the stronger of
the two kinds of evidence for a different reason than the grep: it shows the
offset reached Autoware's **map frame**, not merely that a branch printed a line.
Identical in all three gate cells (`…/automation.log`):

```text
GATE1: truth (81376.10, 49916.10) yaw 34.0 deg | belief (81376.13, 49916.12) yaw 34.0 deg | delta 0.04 m, 0.0 deg
```

Carry **both**: the precheck cannot say which source supplied the offset, and the
grep cannot say the value propagated. The agreement is identity at 1 cm — the
print precision is 2 dp — so do not call it "bit-identical".

## Asset precedence, proved behaviourally

In `N-content` and `N-humble` the `--map-origin` fallback carried a value
_identical_ to the asset's, so those cells cannot distinguish "the asset won" from
"either source would have produced the same number". The `N-precedence` probe
closes that gap: wired level, plus a deliberately divergent
`--mgrs_offset=1000,2000,3000`.

From `~/ue58-logs/p3-10b-precedence/compute.txt` (second paired sample):

| Quantity                         | Value                                     |
| -------------------------------- | ----------------------------------------- |
| published GNSS pose              | `(81375.952382, 49916.583549, 43.035453)` |
| candidate from the **asset**     | `(81375.952382, 49916.586601, 43.035328)` |
| candidate from the **blueprint** | `(720.222382, 1779.156601, 3000.535348)`  |
| \|published − asset\|            | **0.003054 m**                            |
| \|published − blueprint\|        | **93975.026 m** (93.975 km)               |

The blueprint value was genuinely supplied — `mgrs_offset_x/y/z has_attribute =
True` on the live server (`~/ue58-logs/p3-10b-precedence/blueprint-attrs.txt`) —
and 1000/2000/3000 appear nowhere in the level. Both log lines now carry
**different** numbers, so the "ignoring blueprint mgrs_offset" line is finally
load-bearing instead of echoing the asset's own values, which is what it did in
both gate cells.

The ~3 mm residual is a tick-pairing artefact, not offset error: the ROS publish
and the MGRS arithmetic use the same `SensorWorldTransform` captured within one
tick, and the residual is the external client's `get_transform()` landing on a
later tick while the ego micro-settles (yaw drifted −36.315° → −35.924°). The
_later_ of the two paired samples has the _smaller_ residual (3.05 mm against
10.58 mm). Sensor noise is ruled out independently: `noise_*_stddev` and `*_bias`
all default to `0.0f`, `autoware_demo.py` never sets them, and the published
covariance is all zeros.

**Scope the claim to this sensor.** `LoadMgrsData()` is a pure _presence_ check —
`if (MgrsDataAsset) { …; return; }` followed by `if (bHasMgrsOffsetFallback)` —
with no magnitude or sign comparison anywhere, so "one direction of disagreement"
is a much weaker limitation than n = 1 usually implies: no code path exists in
which the relative size or sign of the two offsets could change which branch wins.
The licensed wording is:

> Verified on Nishi-Shinjuku with `sensor.other.autoware_gnss` given a deliberately
> divergent blueprint fallback (1000/2000/3000 m, ~94 km away): the server log
> confirms the data-asset offset was read and the blueprint offset explicitly
> ignored, and the published `/sensing/gnss/pose_with_covariance` matches the asset
> candidate to ~3 mm while sitting ~94 km from the blueprint candidate.

A bare universal "the asset always takes precedence" is **not** licensed.

## Before and after for the fallback

The candidate-8 evidence, on the same map with the same level state (pristine).

|                                                     | Before (`~/ue58-logs/p3/03-gnss-before.txt`)          | After (`~/ue58-logs/p3-11-cell-nishi-fallback/`)                  |
| --------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------- |
| published `/sensing/gnss/pose_with_covariance`      | `x=-279.058 y=-220.875 z=0.545`                       | offset applied; belief `(81376.13, 49916.12)` in `automation.log` |
| expected **without** the MGRS offset                | `x=-279.059 y=-220.875 z=0.545` — **matches**         | —                                                                 |
| expected **with** the MGRS offset                   | `x=81376.671 y=49916.555 z=43.045` — no match         | —                                                                 |
| `MGRS Data Asset SoftPtr not set` in the server log | present (`~/ue58-logs/p3/02-server-grep.txt`, line 3) | **0**                                                             |
| gate verdicts                                       | **never run in this state** — see below               | all four in `gates/gates.txt`, G3 control caveated below          |

For scale, the lanelet2 map's own extent is `x[81167.7, 82280.1]
y[49769.7, 50856.1]` (`~/ue58-logs/p3/03-gnss-before.txt`), so an unoffset pose
lands roughly 81 km outside it.

**The "before" column is one topic sample, not a failed run, and the record must
not be read as if the gates were measured in that state.** What was measured is
the published pose and the server-log warning. **No cell ever ran the gates with
the offset absent** — `N-fallback` is pristine-level _with_ the fallback
supplying the offset, and `N-content` and `N-humble` are wired. That NDT would
never initialise ~81 km outside the point-cloud map is a reasoned expectation
from the measured displacement, not a result: it is unmeasured, and no PR body
may present it as one. Measuring it would need a fourth cell run with the offset
deliberately suppressed, which Phase 3 did not do.

The rewrite also closes a pre-existing latent bug that no test covered: the old
`LoadMgrsData` assigned `MgrsDataAsset` unconditionally after
`LoadSynchronous()`, so a **broken** soft reference left it null with no
diagnostic at all. The new flow falls through to the warning. Separately, the
warning now also fires when the `WorldSettings` cast fails, which was previously
silent — a strict superset of the old condition.

A gtest pins the Nishi golden numbers and the Y-mirror in
`TransformQuaternion.h`: 10 tests pass across `AutowareGnssOffset` (3) and
`TransformQuaternion` (7), in both `libcarla_test_server` and
`libcarla_test_client` (`~/ue58-logs/p3/13-gtest.txt`). Read its coverage
honestly — the test reproduces `AutowareGNSSPublisher::Write`'s composition rather
than invoking it, so a reordering _inside_ `Write()` would leave it green.

**The new C++ is provably live in the editor binary that ran the cells**, not a
stale build: `nm -DC …/Binaries/Linux/libUnrealEditor-Carla.so | grep -c
SetMgrsOffsetFallback` returns 1, and the module `.so` is timestamped inside the
build window (`~/ue58-logs/p3/13-build-editor.log`). Use `nm -DC`; plain `nm -C`
reports "no symbols" on this `.so`.

That binary was compiled at `d46055e56` — the pre-replay revision of the same
tip commit, not a predecessor of the `ef6d25875` the cells ran. It survives
only on the local branch `backup/pre-fix-mgrs` (`git rev-parse
backup/pre-fix-mgrs` resolves to it); like the rest of this work, that branch
is local only — nothing here is pushed. No rebuild happened in between:
`git diff d46055e56 ef6d25875 -- Unreal/ LibCarla/` is empty — the two
commits differ only in two lines of `run_carla_autoware.sh` (the `=`-form
argv fix, rebased into the commits that owned it when `d46055e56` was
replayed into `ef6d25875`) — so the C++ in the binary is byte-identical to
the C++ of the commit under test, and the `nm -DC` count of 1 confirms the
new symbol is in it.

## Static QC of the map assets

Read-only, no asset modified (`~/ue58-logs/p3/04-lanelet2-qc.txt`,
`~/ue58-logs/p3/05-pcd-header.txt`):

| Check                        | Result                                                                    |
| ---------------------------- | ------------------------------------------------------------------------- |
| `lanelet2_bounds.py --check` | 979 lanelet relations checked, **0 misoriented**, `rc=0`; no `--fix` run  |
| Relation counts              | 1711 `<relation>` elements total, of which 979 are `k="type" v="lanelet"` |
| Generator                    | `VMB`, `format_version 1`, `map_version 180`                              |
| Point cloud                  | `POINTS 18758823`, `DATA binary`, `FIELDS x y z`                          |
| Metadata cell                | `[80000, 48000]` at 4000 m resolution                                     |
| Projector                    | `projector_type: MGRS`, `mgrs_grid: 54SUE`, `vertical_datum: WGS84`       |

So the Town10HD lanelet2 bound-orientation defect (Phase 2, candidate 2) does
**not** exist on this map. The `.osm` was verified untouched by sha256 and mtime
after the check.

## The G3 control gate is single-sample-scored

`measure_rates.py:17` returns `m[-1]` — **only the last rate window**. An
intermittent zero-gap duplicate-delivery burst on `control_cmd` contaminates
windows in **all three Phase-3 cells**, and the verdict therefore depends on
whether the burst happens to touch the final window.

| Cell         | contaminated windows | signature                                           | final window                | verdict  |
| ------------ | -------------------- | --------------------------------------------------- | --------------------------- | -------- |
| `N-content`  | **4 of 13**          | `min: 0.001s`, rates 20.685–21.428, σ 0.0088–0.0122 | 19.997 Hz, clean            | PASS     |
| `N-fallback` | **3 of 13**          | `min: 0.000s`, rates 23.077–25.006, σ 0.0167–0.0196 | 20.000 Hz, clean            | PASS     |
| `N-humble`   | **5 of 13**          | `min: 0.000s`, rates 27.918–40.022, σ 0.0222–0.0244 | 36.332 Hz, **contaminated** | **FAIL** |

Raw windows: `~/ue58-logs/p3-1{0,1,2}-cell-nishi-*/gates/g3_control_hz.txt`.
Every cell's first eight windows sit at 19.99–20.01 Hz with σ ≤ 0.0012 s.

So **the FAIL is a gate-scoring artefact, not a Humble result**. Both Jazzy passes
were saved by a clean final window; `N-content` under-reported this in its own
report because it was checked with the literal string `min: 0.000s`, which its
milder `min: 0.001s` bursts do not match. Phase 2's Humble cell had 0 contaminated
windows, so the flake is intermittent and distro-independent, and it affects
`control_cmd` only, never LiDAR.

**The gate was deliberately not changed this phase.** The plan states no gate code
changes are needed for Nishi, and altering `measure_rates.py`'s scoring now would
both exceed Phase 3's scope and destroy comparability with the Phase 2 baseline
these cells are measured against. The scoring weakness is candidate 22 on the PR
list; the fix (median over std-dev-filtered windows) is specified there.

A live re-measurement on the same running Humble stack read **1 publisher
(`vehicle_cmd_gate`), 20.000 Hz over 206 samples**. That probe was **not
preserved** — it exists only as report text and must not be cited as an artefact.
The preserved `g3_control_hz.txt`, with its eight clean 19.99 Hz windows before
the first contaminated one, carries the diagnosis on its own.

## A cross-distro trap that presents as a localisation failure

`N-humble`'s first attempt failed the engage precheck with `GATE1: no
kinematic_state sample` on all six retries — **while the topic was publishing at
19.99 Hz**. Artefacts preserved at
`~/ue58-logs/p3-12-cell-nishi-humble-ATTEMPT1-ros2daemon/` and
`~/ue58-logs/p3-12-cell-ATTEMPT1-ros2daemon.log`.

The cause was a **stale Jazzy `ros2cli` daemon** (pid 226138, started during the
Jazzy cells) still sitting on `ROS_DOMAIN_ID=42`. The Autoware container runs
`--network host` (`run_carla_autoware.sh:917,940` on `upstream/ue58-dev`
`5f58df579`; `:1044,1067` on the Phase 3 branch tip), so Humble's `ros2 topic
echo` reached that Jazzy daemon and died on `unknown tag
'rclpy.type_hash.TypeHash'` before ever subscribing. Stopping it by exact PID and
relaunching the cell unchanged gave the identical `delta 0.04 m` immediately.

Two structural facts make this worth a preflight assertion rather than a war
story:

- **`run_carla_autoware.sh:1145` (on `upstream/ue58-dev` `5f58df579`; `:1275` on
  the Phase 3 branch tip) discards the child's stderr** —
  `aw_ros2 "timeout 15 ros2 topic echo --once /localization/kinematic_state
2>/dev/null" || true` — so a crashing `echo` yields empty stdin,
  `engage_gate1.py` prints exactly `no kinematic_state sample` and exits 2, and the
  true error is destroyed. Every one of the six attempts was exit-2 ("no data"),
  never exit-1 ("diverged"), which is what a genuinely mislocalised stack produces.
- **`ros2topic`'s `echo` uses `NodeStrategy` (daemon-proxying) while `hz` uses
  `DirectNode` (bypasses the daemon)**, which is exactly the observed asymmetry
  between "no sample" and "19.99 Hz".

Independent corroboration in the preserved `ATTEMPT1/autoware.log`:
`ekf_localizer`'s "not activated" warnings stop at `t=…008.55` while the log runs
to `t=…133.15` — about 125 s of an activated, silent-to-`echo` publisher spanning
the entire six-retry window. The daemon probes themselves (the PID, its
`/proc` `ROS_DISTRO=jazzy`, the `TypeHash` traceback, the 19.99 Hz reading) were
**not preserved as files**; the claim survives on the evidence above, which was.

Every prior Jazzy cell passed partly by coincidence of distro.

## A real defect in our own branch, found only by a live run

`N-content`'s first attempt produced **no gate verdicts and no ego vehicle**. The
cause was not the harness but our own stack:
`run_carla_autoware.sh` composed `${SPAWN_POSE:+ --spawn_pose $SPAWN_POSE}`, so
the value arrived as a **separate argv word**. Nishi's pose starts with `-` and is
not a bare negative number, so `argparse` rejected it and `autoware_demo.py` died
at parse time. The evidence is the demo's own stderr,
`~/ue58-logs/p3-10-cell-nishi-content-FAILED-argv/autoware_demo.log`:

```text
autoware_demo.py: error: argument --spawn_pose: expected one argument
```

The full failed run is preserved at
`~/ue58-logs/p3-10-cell-nishi-content-FAILED-argv/`; `AutowareGnssSensor` appears
0 times in both that cell's `carla_server.log` and the engine log, with Log-level
capture confirmed working (56 `LogCarla` lines), so the sensor genuinely was never
constructed.

**How three reviews, unit tests, shellcheck and a dry run all missed it:** a dry
run _prints_ the composed command string but never hands it to `argparse`. A
text-level check of the printed line therefore passes while the bug is live. The
printed line is not even faithful — `start_proc`'s dry-run display re-wraps an
already-quoted string, so it is not a reliable representation of the executed
argv in either direction.

Fixed by switching to the `=` form, in the commit that **owns** each defect rather
than as a patch on the stack top: `--spawn_pose` in `e02fa4dbc`, and the same
latent bug for `--mgrs_offset` in `ef6d25875`. `--mgrs_offset` worked only because
Nishi's origin is positive; the `--map-origin` validator explicitly permits a
leading `-`, so any map west or south of its MGRS grid origin would have hit the
identical failure. `--spawn_index` is left alone: a bare integer is accepted by
`argparse`'s negative-number matcher.

Both fixes were verified at the **parser** level, not by text match: composing the
command the way `start_proc` does and feeding the resulting argv to
`autoware_demo.py`'s real parsers — the new form parses, the old form splits into
four words and raises.

## G1 has substantial run-to-run variability

`N-content` was run three times. Run 1 is the argv failure above. Run 2 started
the gates about two minutes after engage on a route that takes ~45 s, so G1 and G2
sampled a **stationary** vehicle; it is preserved at
`~/ue58-logs/p3-10-cell-nishi-content-STATIONARY-WINDOW/`. Run 3, with the window
placed at engage, is the run of record. Nothing but the watcher's trigger changed
between them — poses, gate scripts and thresholds are byte-identical across runs 2
and 3.

| Run                                     | G1 max      | G2 closest |
| --------------------------------------- | ----------- | ---------- |
| run 2, stationary window                | **0.055 m** | 0.354 m    |
| run 3, engage-triggered window (record) | **0.198 m** | 0.081 m    |

G1 moved the _wrong_ way and G2 the _right_ way, which is exactly what a correctly
placed window predicts. Motion in run 3's window is proven, not asserted:
`g1_gt.txt` covers 31.53 m of path in 30 s, and `g2_dist.txt` descends 221.27 m to
a genuine minimum at index 619 instead of rising monotonically.

**Consequence for the plan's cross-cell rule.** The same configuration produced
0.055 m and 0.198 m — a **0.143 m same-config spread, wider than the 0.059 m
asset-vs-fallback delta** between `N-content` and `N-fallback`. Two things follow:
"no finding" for the fallback is far more robust than "0.059 < 0.1" makes it
sound, because the metric varies more with window placement than with offset
source; and the plan's ">0.1 m between cells is a finding" rule is **tighter than
the metric's own run-to-run variability** and could produce a false positive. This
should be flagged back to the plan.

### G1's spread across cells is not a distro or source finding

`N-humble`'s 0.297 m against Jazzy's 0.198 m has an obvious-looking explanation
that is **false**, and the false version was in a task report before an audit
killed it. The G1 maxima land at different points along the route:

| Cell         | G1 max   | at ground-truth `x` |
| ------------ | -------- | ------------------- |
| `N-content`  | 0.1983 m | 81549.1             |
| `N-fallback` | 0.1388 m | 81556.0             |
| `N-humble`   | 0.2966 m | 81557.7             |

Restricted to the span **all three** cells covered, `x ∈ [81555, 81561]` — 15 NDT
samples each when the span is applied to the NDT sample's own `x`, and 15 / 15 /
14 when it is applied to the paired ground-truth `x`, with identical maxima
either way — the maxima are 0.072 / 0.139 / 0.297 m. So `N-humble`'s maximum lies
**inside** the shared span, not in the extra distance its longer window covered.
The 42 samples in that extra leading span max at **0.0645 m**. Local speed at
each maximum, **measured on the ground-truth series `g1_gt.txt`** and not on the
NDT series, is 4.134 / 4.201 / 4.252 m/s — essentially identical — by finite
difference over ±3 ground-truth samples, a 0.3 s span at the series' 0.05 s
sampling. Name that half-width when re-deriving: all three values are stable
from ±3 through ±9, but at ±1 the Humble series is locally noisy enough to swing
between 0.00 and 8.53 m/s. So "a longer,
faster window mechanically yields a larger maximum" does not hold: the headline
`mean_speed` figures (1.05 vs 1.58 m/s) are 30-second means over a
drive-then-stop profile and do not describe the speed where the maximum occurs.

The conclusion survives and is better supported this way: **each cell's maximum is
a transient two-sample spike landing in a different segment**, well inside the
0.143 m same-config spread, at n = 1 on Humble. G1 max is not a tracking-quality
measure. Recomputable from `~/ue58-logs/p3-1{0,1,2}-cell-nishi-*/gates/g1_ndt.txt`
and `…/g1_gt.txt`.

## What the evidence does and does not license

**Proved.**

- Both offset sources drive the full closed loop to ARRIVED with the gates passing
  on identical map, route, poses, build and harness.
- The asset branch executes and **explicitly ignores** the blueprint when the level
  is wired.
- The fallback branch executes and correctly **suppresses** the pre-existing
  `SoftPtr not set` warning when the level is pristine.
- The offset reaches Autoware's **map frame**, evidenced by an origin-independent
  truth-vs-belief agreement of 0.04 m, identical in all three gate cells.
- The asset **wins over a divergent fallback**, by ~94 km against ~3 mm.
- The fallback is **not a regression** on the asset path.

**Not proved. No PR body may claim any of these:**

- **Cruise-phase localisation equivalence.** `run_gates.sh` orders G2 → sleep
  `SETTLE_S` → G3 → G1, so G1 opens ~52 s into a ~62 s route and covers the
  terminal ~31 m of a 221 m drive. Every G1 window in this phase is terminal
  approach, not cruise. It is genuine in-motion data from the unmodified harness —
  run 3's maximum occurs inside a ~6 s segment whose 2 s speed bins read
  4.0–4.1 m/s (the finite-difference speed at the sample itself is 4.134 m/s;
  same series, different smoothing) — but 20 of the 30 s
  are parked, and a longer route or concurrent G1/G2 would be needed to say
  anything about cruise.
- **Generality.** n = 1 per arm, one map, one offset, Fast DDS, one build. The
  only axis with n = 2 is the ROS distro.
- **No Town10HD regression was re-driven live in Phase 3.** The evidence that the
  three-commit stack leaves the default-origin path unchanged is a `--dry-run`
  comparison (goal still map `x=-1.160 y=-28.370`, no `--mgrs_offset` forwarded)
  plus a text comparison against the base version of the script in a throwaway
  shadow tree. No vehicle was driven on Town10HD in this phase.
- **`--spawn-pose` was never exercised under `--mode e2e`.** All three gate cells
  ran `--mode classical`, and `N-precedence` invoked `autoware_demo.py` directly
  with no runner at all. The branch that suppresses the runner's e2e
  `--spawn_index` default when `--spawn-pose` is given is covered only by the unit
  tests and by `--dry-run`.
- **The zero-offset edge case.** `SetMgrsOffsetFallback` sets
  `bHasMgrsOffsetFallback = !IsNearlyZero()`, so a deliberate
  `--mgrs_offset=0,0,0` is indistinguishable from "attribute absent" and emits
  neither log line. Untested by any cell; arguably correct on a Local-projector map.

## Deviations from the plan

- **A precedence probe was added.** `N-precedence` is not in the written plan. It
  exists because a review established that the two gate cells could not
  behaviourally distinguish asset-wins from either-source-agrees, and asset
  precedence is the design's central safety property.
- **`N-content` was run three times.** Run 1 was blocked by the argv defect; run 2's
  gate window was misplaced by a disclosed process error and sampled a stationary
  vehicle. All three runs are preserved; only run 3 is cited.
- **`N-humble` was run, not skipped.** It was the plan's optional cell, run because
  "one ROS distro" was named as a generality limit and it is the cheapest axis to
  add. It completed in 21 minutes of a 90-minute box; the budgeted TensorRT rebuild
  cost nothing because the plans were already cached from Phase 2.
- **Two Task-7 tool fixes beyond the plan's literal text.** `pose_at` returned yaw
  0.0 instead of the true heading when a centreline's first segment is zero-length,
  and `load_lanelets` silently dropped a lanelet whose bound way had fewer than two
  usable nodes. Both are now fixed with regression tests. Neither was live on the
  real map — the loader returns 979/979 lanelets and the derived poses are
  byte-identical after the fix — so no pose in this record is affected.
- **The gate scoring was deliberately left alone.** See "The G3 control gate is
  single-sample-scored".

## Facts a future reader should not re-investigate

- **`carla_server.log` loses the tail of the engine's output, and it is not a
  crash.** `Signal 11 caught.` appears exactly once in each cell's
  `carla_server.log`, spliced mid-line onto the end of whatever engine line
  stdout was flushing at the time — an asset-load line in `N-content`,
  `LogDerivedDataCache` in `N-fallback`, a `LogRenderer` virtual-shadow-map
  warning in `N-humble` — and immediately followed in every cell by the
  `UnrealTraceServer` bring-up sequence (`Opening
shared memory` / `Forking process`). There are **zero** crash-callstack markers
  (`Fatal error`, `Callstack`, `Critical error` all absent) and the file ends
  cleanly on `Received signal 15` / `Daemon is exiting without errors.`. The string
  does come from UE Core's crash handler
  (`UnixPlatformCrashContext.cpp:1052`, an `fprintf` to `stderr` that bypasses
  `GLog`), so the consistent reading is a transient fault in the short-lived child
  forked for the trace server, which inherits the parent's handler. The editor
  demonstrably survived: it drove the route, arrived, and served gates for ~10 more
  minutes. **What matters operationally is that engine-timestamped output to
  stdout stops at that point while the engine keeps writing its own log** — in
  `N-content` run 3, stdout's last engine line is at `06.29.02:107` and the engine
  log continues to `06.31.47:490`, about 2 m 45 s of engine output stdout never
  received, covering the drive and the arrival. This claim was wrong twice before
  it was right; do not re-derive it from line counts, which is what produced both
  earlier errors.
- **A second `Segmentation fault (core dumped)` at teardown is the known benign
  one.** It fires immediately after `SIGTERM -> 'carla_server'` in every cell
  (`N-content` pid 613808, `N-fallback` pid 647633) and is the simulator's own
  teardown SIGSEGV that Phase 2 already recorded as candidate 7. A reviewer
  grepping published evidence for "Segmentation fault" will find it; it is not new.
- **Copy a log while the process is still flushing and your grep will under-report
  it.** Two separate false negatives in this phase came from exactly that: a copy
  taken mid-teardown is short by roughly 840 bytes — the teardown block — and both
  `N-content`'s and `N-precedence`'s first `Signal 11` counts were taken against
  such a copy and read 0. **Re-grep after refreshing a copy, or grep the source.**
- **`Saved/Logs/CarlaUnreal.log` rotates on the next launch.** `N-content`'s
  citation of that path rotted within one simulator start; run 3's engine log is
  `CarlaUnreal-backup-2026.09.05-06.31.47.log`. Later cells copy the engine log
  into their own directory at teardown (`…/CarlaUnreal-enginelog.log`, with the
  rotated original named in `…/CarlaUnreal-enginelog.source.txt`) and cite the
  in-cell copy. `N-content` predates that rule; its grep output is preserved
  independently of rotation in `gnss-source-enginelog.txt`. In `N-content`, the
  decisive GNSS pair cleared the stdout cutoff by **445 ms** (pair at
  `06.29.01:662`, stdout stops at `06.29.02:107`) — that evidence survived on luck,
  which is why the copy rule exists.
- **`carla_server.log` and the engine log are complementary, not redundant.** The
  engine log is the evidence of record for `LogCarla` content; `carla_server.log`
  is where crash-handler output lives, because it writes to stdout rather than
  through the log writer.
- **UE `TEXT()` literals are UTF-16LE.** `strings` on a plugin `.so` returns 0 for
  every log format string and looks like proof they are missing; `strings -e l`
  returns them. Likewise `nm -C` reports "no symbols" on the plugin `.so` — use
  `nm -DC`. Runtime logging goes through `GLog`, which emits UTF-8, so plain-text
  greps of the _logs_ are unaffected.
- **A freshly connected client must call `world.wait_for_tick()` before
  `get_actors()`, `cast_ray()` or `get_waypoint()`** on this build, or it observes
  an empty actor list and an empty world.
- **`autoware_demo.py`'s stdout is fully buffered when redirected**, and the demo
  needs SIGKILL, so `autoware_demo.log` comes back empty (0 bytes in all three
  cells). Any cell wanting client-side assertions needs `python -u`.
- **The ego creeps ~2.1 mm/s after arrival**, starting exactly at the G2 minimum:
  0.745 m over ~358 s in `N-content` run 3, 0.923 m over ~420 s in run 2, and the
  same rate in `N-fallback` — so the fallback is ruled out as its cause. Nothing
  holds the vehicle after arrival. Inside tolerance here; it would bite a longer
  hold or a tighter tolerance. Undiagnosed.
- **The `clangd` errors on the touched plugin files are false positives.**
  `~/src/carla-ue58` has no `compile_commands.json` and UE plugin sources are built
  by UnrealBuildTool, not by the CMake/Ninja build, so `clangd` has no include
  paths for them. They give **no** signal about whether plugin C++ compiles.

## Plan defects found during Phase 3

The plan is a tracked document, so its own defects are recorded here.

| Defect                                                                                               | Correction                                                                                                                                                                                                                      |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The umap-state hash guards diff a single-line `sha256sum` against a **two-line** recorded file       | They never work: one always takes the "wired" branch, the other never reports a successful restore. Compare the two hashes directly instead, keeping each step's intended polarity.                                             |
| "watch `automation.log` for `autonomous mode engaged`"                                               | That string is **not** in `automation.log`; it is in the runner's own stdout log (`~/ue58-logs/p3-1{0,1,2}-cell.log`). Following the plan literally makes the watcher time out and the drive go unmeasured.                     |
| The Task 9 `BuildConfiguration.xml` snippet writes `<MaxProcessorCount>` inside `<ParallelExecutor>` | Schema-invalid in UE 5.8. UBT logs `warning: The element 'ParallelExecutor' … has invalid child element 'MaxProcessorCount' … expected: 'ProcessorCountMultiplier, …'` and the cap never binds. Use `ProcessorCountMultiplier`. |
| "the spawn point is 7.478 m off the lanelet2 centreline / routes on the neighbouring lane"           | Falsified by four measurements; see "The 7.478 m off-lane premise is dead".                                                                                                                                                     |
| "`world.get_ego_spawn_points()` does not exist on the server"                                        | It exists and returns 1 on this build.                                                                                                                                                                                          |
| ">0.1 m G1 difference between cells is a finding"                                                    | Tighter than the metric's own same-config variability (0.143 m). Usable only as a prompt to investigate, never as a verdict.                                                                                                    |
| Step 4's `--nearest-to-carla "-278.39,220.54"` space form                                            | `argparse` rejects a leading-dash value that is not a bare negative number. Use the `=` form. The same trap, unnoticed in a composed shell command, is what broke `--spawn_pose` live.                                          |
| The Task 7 test file's verbatim first line `import math`                                             | Unused; `ruff check` reports F401 and the repo's own pre-commit would reject the committed state. Deleted.                                                                                                                      |

## Open questions

1. **G3 control scoring (candidate 22).** Zero-gap duplicate-delivery bursts on
   `control_cmd` now observed in all three Phase-3 cells and both Phase-2 Jazzy
   cells. The gate reports the last window, so the verdict is a coin flip on
   whether the burst touches it. Fix specified in `pr-candidates.md`; deliberately
   deferred to preserve the Phase 2 baseline.
2. **What causes the bursts.** Unknown. `control_cmd` only, never LiDAR;
   intermittent and distro-independent; one publisher (`vehicle_cmd_gate`)
   confirmed live during `N-humble`.
3. **A cruise-phase G1 window.** Structurally unreachable at this route length with
   the current gate ordering. Needs a longer route or G1 running concurrently with
   G2 — a harness change the plan explicitly says Phase 3 does not need.
4. **Post-arrival creep at ~2.1 mm/s.** Reproduces in three cells with both offset
   sources. Root cause unknown (no hold brake / residual throttle / Chaos slide).
5. **The zero-offset edge case.** `IsNearlyZero()` makes a deliberate `0,0,0`
   indistinguishable from "not supplied".
6. **A distro-matching preflight for the `ros2` daemon.** `run_carla_autoware.sh`
   runs the container with `--network host` and has no assertion that a running
   `ros2cli` daemon on the domain matches the container's distro. See the
   cross-distro trap section; candidates 29 and 30.
7. **`carla_server.log`'s early stdout cutoff.** Reproduces in every live run.
   Contained by copying the engine log per cell, not fixed.
