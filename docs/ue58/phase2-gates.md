# Phase 2 — gate results on Town10HD for CARLA's in-tree Autoware layer

Three live cells, run 2026-09-04 against CARLA's in-tree Autoware layer on UE 5.8,
measured with this repository's `scripts/e2e/run_gates.sh`. All four gates PASS in
every cell.

This file is the authoritative Phase 2 record. Where a per-task report and this
file disagree, this file wins: several reports carry figures that later audits
corrected, and the corrections are folded in here.

## Versions

| Component         | Value                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------- |
| CARLA             | `youtalk/carla` `fix/ue58-installer-check` `82ef62095` (top of the nine-PR Part-A stack)    |
| CARLA base        | `upstream/ue58-dev` `5f58df579`, plus one fork-only CI commit `60c1b30d9`                   |
| Engine            | `CarlaUnreal/UnrealEngine@ue58-dev-carla` `cacb25b99f14` (5.8)                              |
| Content           | `carla-content@ue58-dev-carla` `981cdcbae2`                                                 |
| Toolchain SDK     | `v26_clang-20.1.8-rockylinux8`                                                              |
| Python client     | `carla-0.10.0-cp312` wheel built from this tree (`sha256 4484599f5886…`), in `~/carla-venv` |
| Autoware (Jazzy)  | `ghcr.io/autowarefoundation/autoware:universe-cuda-jazzy` `sha256:9c7d51a820a0…`            |
| Autoware (Humble) | `ghcr.io/autowarefoundation/autoware:universe-cuda-humble` `sha256:724c2049897d…`           |
| `autoware_launch` | **0.52.0 in both images** — see "Deviations" below                                          |
| Gates             | this repository, `feat/ue58-gates` `ef6bfb8`                                                |

Logs are local only, under `~/ue58-logs/p2-17-cell-jazzy-fastdds/`,
`~/ue58-logs/p2-18-cell-jazzy-cyclonedds/` and `~/ue58-logs/p2-19-cell-humble-fastdds/`,
with per-cell harness logs `~/ue58-logs/p2-{17,18,19}-cell.log`.

## The three cells

Every cell: `--mode classical --stack docker --server editor --town Town10HD_Opt
--spawn-index 24 --goal "-1.16,28.37,0.16"`, `ROS_DOMAIN_ID=42`, on the same CARLA
build with no rebuild between cells. The goal converts to map `(-1.160, -28.370)`.

| Cell           | Sim RMW    | Autoware              | Spawn/Goal              | G1 max err | G2 closest | G3 LiDAR | G3 control | routing/state | Verdict  |
| -------------- | ---------- | --------------------- | ----------------------- | ---------- | ---------- | -------- | ---------- | ------------- | -------- |
| `J-fastdds`    | Fast DDS   | Jazzy / Ubuntu 24.04  | 24 / `-1.16,28.37,0.16` | 0.074 m    | 0.218 m    | 10.00 Hz | 20.00 Hz\* | 3 = ARRIVED   | **PASS** |
| `J-cyclonedds` | CycloneDDS | Jazzy / Ubuntu 24.04  | 24 / `-1.16,28.37,0.16` | 0.266 m    | 0.218 m    | 10.00 Hz | 20.69 Hz\* | 3 = ARRIVED   | **PASS** |
| `H-fastdds`    | Fast DDS   | Humble / Ubuntu 22.04 | 24 / `-1.16,28.37,0.16` | 0.085 m    | 0.213 m    | 10.00 Hz | 20.00 Hz   | 3 = ARRIVED   | **PASS** |

Thresholds: G1 < 1.0 m, G2 < 1.0 m, G3 LiDAR 10 ± 1 Hz, G3 control 20 ± 5 Hz.

\* **The reported control figure is the last rate window, not a robust statistic.**
Both Jazzy cells contain duplicate-timestamp burst windows (identifiable by
`min: 0.000s`). Comparing only clean windows gives **19.999–20.012 Hz**
(`J-fastdds`) against **19.997–20.023 Hz** (`J-cyclonedds`) — indistinguishable
within measurement noise. `H-fastdds` was the only burst-free series of the three,
at 19.991–20.011 Hz across 13 windows. Making this figure robust
(median-of-windows, or discarding `min: 0.000s` windows) is a recorded candidate;
it was deliberately **not** changed mid-series, because changing the instrument
between cells would have made them non-comparable, and the verdict is unaffected
either way.

Supporting distributions, recomputed from raw per-sample rows rather than the
summary lines:

| Cell           | G1 samples | G1 max    | G1 median | G2 raw minimum |
| -------------- | ---------- | --------- | --------- | -------------- |
| `J-fastdds`    | 300        | 0.0735 m  | 0.0364 m  | 0.2180 m       |
| `J-cyclonedds` | 299        | 0.2664 m  | 0.0276 m  | 0.2178 m       |
| `H-fastdds`    | 300        | 0.08531 m | 0.03918 m | 0.2127 m       |

`J-cyclonedds`'s 3.6× higher G1 maximum is confined to a single ~4 s transient in
the first ~14 s of a ~29.8 s drive; its median is the _lowest_ of the three. At
n = 1 per arm this is **not attributable to the transport** in either direction.
`H-fastdds` matches `J-fastdds` at every G1 quantile (zero samples above 0.15 m in
both), which independently supports reading the `J-cyclonedds` excursion as a
transient. The two Jazzy `g2_dist.txt` files are genuinely independent runs
(different md5s, 2232 differing lines of 2996) that converge only near the
minimum.

## `is_dense` — before and after

The fix is `fix(ros2): publish CARLA point clouds as is_dense`
(`LibCarla/source/carla/ros2/publishers/CarlaPointCloudPublisher.cpp`), fork PR #28.

|                                                                                   | Before (Phase 1)             | After (Phase 2, all three cells) |
| --------------------------------------------------------------------------------- | ---------------------------- | -------------------------------- |
| `[sensing.lidar.top.crop_box_filter_self]: Invalid PointCloud: is_dense is false` | **99** (`run1/autoware.log`) | **0**                            |

The zero is **non-vacuous**, established per cell rather than inferred from absence:

- The emitting node loaded in every cell (`autoware.log`, `crop_box_filter_self`).
- LiDAR streamed continuously at 10 Hz throughout — in `J-fastdds`, 12 consecutive
  windows at 9.995–10.009 Hz in the raw G3 file, not one averaged number.
- G1 collected 300 / 299 / 300 NDT samples, so the localisation chain was
  consuming those clouds.
- The warning is throttled at a **measured** 5.0079 s interval (mean over the 98
  gaps between Phase 1's 99 occurrences; min 4.960 s, max 5.200 s). Over each
  cell's span from `crop_box_filter_self` load to its last log timestamp, a
  persisting defect would therefore have fired roughly:

  | Cell           | Log span | Expected occurrences had the defect persisted | Observed |
  | -------------- | -------- | --------------------------------------------- | -------- |
  | `J-fastdds`    | 449.2 s  | 89.7 → **~90**                                | 0        |
  | `J-cyclonedds` | 422.9 s  | 84.4 → **~84**                                | 0        |
  | `H-fastdds`    | 455.0 s  | 90.8 → **~91**                                | 0        |

  The three task reports each use a "~7 min ≈ 420 s" shorthand and quote "~80".
  That shorthand undercounts by 10–15 %; the figures above are the corrected ones
  and are what should be quoted. They are reproducible from the logs: the span is
  from the first `crop_box_filter_self` line to the last timestamp in each cell's
  `autoware.log`, divided by the 5.0079 s throttle.

Build freshness was a real hazard here and was closed with positive evidence, not
assumed: `carla-ros2-native-lib` carries no `BUILD_ALWAYS`, its build stamp depends
only on its configure stamp, and its post-build staging copy re-runs (printing
activity) even for a stale `.so`. So the sub-project was built directly and a
`Building CXX object …/CarlaPointCloudPublisher.cpp.o` line required in the log;
the staged `.so` (04:22:55) is newer than the source (04:17:50) and byte-identical
to the install copy. Adding `BUILD_ALWAYS 1` is a recorded candidate.

## Town10HD map fix and README goal — the Task 3 record

Reproduced from `~/ue58-logs/p2-03-evidence.md`, which is the corrected record.
**Do not cite `~/ue58-logs/24-metrics.txt`**: its body still carries the falsified
narrative beneath its correction header.

| Run                                  | Spawn                   | Goal               | Map                      | routing/state                                                   | Backward path | Invalid Trajectory | too far from ego | EMERGENCY_STOP                                           | closest base_link→goal           |
| ------------------------------------ | ----------------------- | ------------------ | ------------------------ | --------------------------------------------------------------- | ------------- | ------------------ | ---------------- | -------------------------------------------------------- | -------------------------------- |
| Phase 1 run 3 (before)               | random, matched `12236` | `98.90,68.73,90.4` | tracked (17 misoriented) | never SET→ARRIVED; overshot the goal and halted 17.75 m past it | 377           | 166                | 166              | 171 operated / **172 canceled, last event a cancel**     | 5.09 m at t+35 s                 |
| `p2-03-run3-repro-fixed-attempt1`    | 129 (inside `12236`)    | `98.90,68.73,90.4` | fixed (0 misoriented)    | 3 (ARRIVED)                                                     | 0             | 0                  | 0                | 7 (7 canceled)                                           | 0.34 m                           |
| `p2-03-run3-repro-fixed` (attempt 2) | 129                     | `98.90,68.73,90.4` | fixed                    | 2 (ARRIVING)                                                    | 290           | 127                | 127              | 129 operated / 128 canceled, still operating at teardown | 6.27 m, halted 16.32 m past goal |
| `p2-03-run3-repro-fixed-attempt3`    | 129                     | `98.90,68.73,90.4` | fixed                    | 2 (ARRIVING)                                                    | 190           | 82                 | 82               | 80 operated / 79 canceled, still operating at teardown   | 6.09 m, halted 16.33 m past goal |
| `p2-03-readme-verbatim`              | 24                      | `-1.16,28.37,0.16` | fixed                    | 3 (ARRIVED)                                                     | 0             | 0                  | 0                | 10 (10 canceled)                                         | 0.22 m                           |

Counts are cumulative over each run's full `autoware.log` and scale with how long
the stack was left up; attempt 3 (190/82/82/80) is the like-for-like comparison
against attempt 1 (0/0/0/7).

**The map fix is preventive, and the plan's causal claim was falsified by this
campaign's own logs.** Carry this framing, not a stronger one:

- The defect is structural and independently proven: 17 of 160 road lanelets (17
  of 246 lanelet relations) reference the shared centre linestring of an opposing
  lane pair un-inverted, so their bounds are ordered against travel. The legacy
  2019 map has 0 of 168. The generator reproduces the committed repaired map
  byte-identically.
- The causal chain the plan assumed (misoriented bounds → `align()` flips travel →
  `Backward path is NOT supported` → latched emergency stop) is **contradicted**.
  `Backward path` still occurred 290 and 190 times on the _fixed_ map; the unfixed
  map produced the identical eight-lanelet route (`12236` -> `22286` -> `10771` ->
  `34831` -> `17813` -> `29554` -> `4634` -> `31570`) from a pose 0.024 m away and
  halted at the same metre by the same mechanism. Spawn 129 arrived in only 1 of 3 runs on the identical committed fixed
  map, and the four initial poses' spread (max 0.0414 m) **does not sort by
  outcome** — the closest pair of all, 0.0032 m apart, is one unfixed FAILED run
  against one fixed FAILED run.
- A static `lanelet2` probe settled it: loading the pre-fix map in
  `universe-cuda-jazzy`, `geometry::align` reverses the left bound of **all 17**
  and lands on exactly the repaired orientation, while reversing nothing among the
  other 229 relations and nothing on the post-fix map. The loader-derived
  centreline agrees for 17/17, and a `RoutingGraph` built on both maps gives
  identical following/previous/left/right/besides for all 17. So today's loader
  heuristic already recovers the correct orientation in every case, there is no
  mis-oriented subset to build a drive scenario on, and the falsified drive-level
  claim could never have been true.
- Read the probe's "17/17" as **one binary agreement per lanelet**, not as 17
  independent precision measurements: the repair reverses the same node ids
  `align()` reverses, so the reported `dot = 1.0000` / `0.0 deg` is arithmetically
  forced once the flip agrees. It is not circular — it could have come out −1 — but
  do not lean on the dot value as a tolerance.
- Scope the claim to "`lanelet2` as shipped in `autoware:universe-cuda-jazzy`, on
  Town10HD". Autoware's own `map_loader` path
  (`autoware_lanelet2_extension`, `overwriteLaneletsCenterline`, the local/MGRS
  projector, `lanelet2_validation`) was not exercised, nor any other map or
  `lanelet2` version.
- **A new Phase 2 finding:** the run-to-run non-determinism on spawn 129 is real
  and undiagnosed. The discriminator across the five runs is a **reverse pull-out
  path** — negative `vehicle_cmd_gate` input velocity, present in exactly the three
  runs that logged `Backward path` (18 / 9 / 12 occurrences) and absent in the two
  clean ones. `clothoid_pull_out` engaged in a clean run too, so the pull-out
  module alone is not the discriminator.

The README goal fix (fork PR #26) rests on its own clean evidence: the previously
documented `80.0,-16.5,90` is 19.44 m off the nearest lane centreline and
`mission_planner` refuses it; the replacement `-1.16,28.37,0.16` drove to ARRIVED
at 0.22 m, and did so again in all three Phase 2 cells.

## Deviations from the plan

### The Humble cell is not an older-Autoware probe

The plan specified `universe-cuda-humble-0.45.1`. **That tag does not exist**
(`docker manifest inspect` → `manifest unknown`), and neither do
`universe-humble-0.45.1` or `universe-cuda-0.45.1`: 0.45.x predates the distro
suffix. The cell used the plan's own fallback, `universe-cuda-humble`, which is
**`autoware_launch` 0.52.0 — the same release as the Jazzy image**. Verified
directly on both images:

```bash
docker run --rm --entrypoint bash <image> -lc \
  'grep -m1 -o "<version>[^<]*</version>" \
   /opt/autoware/autoware_launch/share/autoware_launch/package.xml'
# universe-cuda-jazzy   -> 0.52.0
# universe-cuda-humble  -> 0.52.0
```

(`~/ue58-logs/p2-19-autoware-launch-version.txt`.)

So `H-fastdds` tested **Humble / Ubuntu 22.04 against Jazzy / Ubuntu 24.04 at one
Autoware release**. The plan's older-release compatibility probe went **unmet**.
Separately, the installer's `TIERIV_BASELINE_TAG` pin is source-mode-only
(`resolve_source_version` is reached only from `do_source`), so
`--docker --distro humble` could never have produced a pinned older tag anyway.

The genuinely useful positive result from this cell: everything CARLA publishes
measured **nominal inside the Humble container** throughout — LiDAR 9.973–10.001 Hz,
IMU 19.960 Hz, `/clock` 19.987–19.999 Hz. Nothing CARLA publishes is rejected by a
Humble-side node.

### The Humble cell's 54 s localisation stall was environmental

`H-fastdds` logged a 54 s stall (42 × `align server failed` / `No InputSource`,
against 1 on Jazzy). Diagnosed as a **first-run TensorRT engine rebuild**, with
evidence rather than plausibility: `Starting to build engine` occurs 5 times on
Humble and 0 times in both Jazzy cells; the stall window 05:40:00–05:40:54 brackets
the two `centerpoint` engine writes at 05:40:06 and 05:40:52; and
`EKF/NDT Activation succeeded` lands at 05:40:56.971, 2.27 s after the last stall
line. (The `mission_planner` "Initial pose" print 39 s later is a planning-side
echo, not a localisation signal — do not use it as the convergence marker.)

One anomaly is left **unexplained on purpose**: a single 9.849 Hz LiDAR window,
inside tolerance. The engine-rebuild story was tested against it and does not fit —
bounding the build intervals leaves one candidate, but the control sample inside
that same interval was the cleanest series of all three cells.

### One deliberate divergence from the plan's script text

`run_gates.sh` as the plan literally specified it **exited 0 when G2 crashed**:
`gate_g2_closed_loop.sh` prints a `G2 goal: …` progress line before measuring, and
the harvest collected any line whose first field was `G2`, so that echo was taken
as a verdict containing no "FAIL". Reproduced with the real script and a stub that echoes then
dies. Fixed by harvesting only `^G[123] .* -> (PASS|FAIL)$` and requiring each of
G1/G2/G3 to be represented, plus renaming the echo; pinned by
`tests/e2e/test_run_gates.py`. This resolves the plan's own internal conflict in
favour of its Interfaces contract.

## Facts a future reader should not re-investigate

- **G3 samples early, not late.** `run_gates.sh` launches G2 in the background,
  sleeps `SETTLE_S` (default 20 s), then runs G3, then G1; and
  `gate_g3_performance.sh` captures LiDAR for 15 s and then control for 15 s. So
  every G3 figure in this record describes roughly the **first 50 s** of a run
  (≈ GATES_START+20…35 s for LiDAR, +35…50 s for control), and the burst windows in
  the two Jazzy cells are **early-run artifacts**. `SETTLE_S` was left unset in all
  three cells.
- **The `carla_server` SIGTERM segfault at teardown is benign.** Every cell log ends
  with `Segmentation fault (core dumped)` from the simulator's own internal teardown
  after SIGTERM. It is recurring and pre-existing across at least six other run logs,
  under both middlewares, and is not instability introduced by this build. It remains
  candidate 7 on the PR list, unfiled.
- **`~/autoware_data/` is bind-mounted read-write.** `run_carla_autoware.sh:1025`
  mounts it as `-v "$HOME/autoware_data":/root/autoware_data` with **no `:ro`**. The
  Humble cell's first-run TensorRT rebuild therefore **overwrote five `.engine`
  plans** in the user's own directory. Consequences: `J-fastdds` and `J-cyclonedds`
  are no longer bit-reproducible without paying the same rebuild stall (both had
  read the cache — 5 × `Loading engine`, 0 × `Starting to build engine` — and
  modified nothing), and per-distro model directories are worth deciding before any
  further cells.

## What these three cells do and do not establish

**Supported.** CARLA's in-tree Autoware layer, at `82ef62095` on UE 5.8, passes all
four gates on Town10HD from spawn 24 to goal `-1.16,28.37,0.16` under
Jazzy/Fast DDS, Jazzy/CycloneDDS and Humble/Fast DDS. `is_dense` warnings are 0 in
all three against a Phase 1 before-count of 99 and a non-vacuity argument per cell.
G2 arrival is stable at 0.213–0.218 m across three independent drives, and the G1
distributions of the two Fast DDS cells agree at every quantile.

**Not supported. The record says so plainly because these are the claims a future
reader would otherwise assume:**

- **Not "validated against older Autoware releases".** Both images are
  `autoware_launch` 0.52.0; see "Deviations". The older-release probe went unmet.
- **Not "Humble is cleaner (or worse) than Jazzy".** n = 1 per arm throughout. The
  Humble cell's stall is attributed to a cold TensorRT cache, and its burst-free
  control series is one sample.
- **Not a durability or regression-tested claim of any kind.** Three single runs,
  one per cell, on one machine, one town, one route.
- **Not a transport verdict.** CycloneDDS reaches ARRIVED with all four gates PASS
  and a LiDAR rate identical to Fast DDS to within 0.01 Hz on the same build; the
  control rate is `20 ± 5 Hz` in both, with clean-window ranges of
  19.997–20.023 Hz (CycloneDDS) against 19.999–20.012 Hz (Fast DDS) — i.e.
  indistinguishable within measurement noise. No directional
  statement is made about localisation accuracy: `J-cyclonedds`'s 3.6× G1 maximum is
  attributable at n = 1 to an early transient, but it is not _disprovable_ as
  transport noise either.
- **Not a DDS health check via the plan's grep.** The plan's
  `grep -ciE 'fragment|deserializ'` expecting 0 is mis-specified: it returns 11 on a
  healthy run, every hit Vulkan _shader-fragment_ vocabulary
  (`VK_EXT_fragment_shader_interlock`, `r.Vulkan.EnableDefragmentation`, …) and zero
  DDS errors. A DDS-specific pattern is needed; the count as phrased means nothing.
- **The map fix is preventive**, per the section above — not a demonstrated
  drive-level repair.

## Plan defects found during Phase 2

The plan is a tracked document, so its own defects are recorded here.

| Defect                                                                             | Correction                                                                                                                                                                                                                                                                                        |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "`gates.txt` carries three verdict lines; exit 0 iff all PASS"                     | A healthy run carries **four** — `gate_g3_performance.sh` scores LiDAR and control separately. Asserting exactly three would fail every healthy run. The invariant used instead is "each of G1/G2/G3 is represented by at least one verdict line".                                                |
| The `run_gates.sh` text as specified                                               | Exited 0 when G2 crashed (progress echo harvested as a verdict). See "One deliberate divergence" above.                                                                                                                                                                                           |
| `SERVER_FLAGS+=" $SERVER_ARGS"` prescribed verbatim                                | Fed through `start_proc()`'s nested `bash -c "$cmd"`, this would itself have been a **shell-injection vector**. Replaced by a quote-aware tokenize plus per-element `printf ' %q'` re-quote, verified with an argv-echoing fake editor: `-post=$(touch …);echo INJECTED` arrives as literal text. |
| `grep -ciE 'fragment\|deserializ'` expected to return 0 as DDS health evidence     | Mis-specified; returns 11 Vulkan shader-fragment hits with zero DDS errors. Not a health check as phrased.                                                                                                                                                                                        |
| Humble image `universe-cuda-humble-0.45.1`                                         | Does not exist (404), with two variants likewise absent. See "Deviations".                                                                                                                                                                                                                        |
| ARRIVED cited as `run2/autoware.log:1105`                                          | That line is `mission_planner` route logging. The real `Driving => ArrivedGoal` transition is `run2/autoware.log:1378`.                                                                                                                                                                           |
| "171 `EMERGENCY_STOP` operated, **latched**"                                       | 171 operated / **172 canceled**, last event a cancel, so **nothing latched** at teardown. The "~100 ms each" characterisation is also wrong: median cycle **2.200 s** over 171 cycles. Both Phase 2 _failing_ runs, by contrast, did end with MRM still operating.                                |
| "the spawn-129 pose is 1.46 m from Phase 1 run 3's"                                | The two poses are **0.024 m** apart (`mission_planner` logs the initial pose at 6 dp; `GATE1` prints 2 dp, which is what the original reading used). Max spread across all four runs 0.0414 m.                                                                                                    |
| "run A was the cold start (526 s)"                                                 | Unsupported. All four runs show 54.2–55.1 s from Autoware start to `Driving` and 117–123 s from harness start, with the same `Town10HD_Opt already loaded` marker. There is no warm/cold distinction to explain the outcome split.                                                                |
| The stack diagram drew Tasks 1 and 2 as siblings                                   | The Part-A stack is linear, as every `git switch -c` in the task steps says.                                                                                                                                                                                                                      |
| Task 12's delete list omitted `tests/conftest.py`                                  | The step's `rm -f` was operative and correct; the file list was incomplete.                                                                                                                                                                                                                       |
| Every line number in a Part-A task's file list                                     | Advisory only — each stacked branch shifts the line numbers recorded against `upstream/ue58-dev`. Edits must be located by content.                                                                                                                                                               |
| Task 3 Step 1 re-captured the live OpenDRIVE over the file Task 1 had already used | Would have made Task 1's committed map unreproducible from the file it names. Captured to a new path and diffed instead (byte-identical).                                                                                                                                                         |
| Two task briefs prescribed claim wording that outran their own evidence            | The CycloneDDS "identical rates" table cell and the `is_dense` before/after framing were both hedged against the plan's literal text, on the spec's binding requirement that claims be evidenced.                                                                                                 |

## Known limitations carried forward

Findings that reviews rated Minor or Low and that were deliberately deferred
rather than fixed. None can turn a failing gate into a passing one; they are
recorded so a future reader does not mistake any of them for a fresh discovery.

### This repository (gates and tests)

- `tests/e2e/test_run_gates.py` hard-codes the verdict-line shapes as stub
  strings, so nothing pins the coupling between `run_gates.sh`'s harvest regex and
  the three real emitters (`measure_ndt.py:45`, `measure_route.py:24`,
  `measure_rates.py:31`). A reformat of any `measure_*.py` would break every live
  gate with no test failing. Cheap fix: one assertion per emitter that its output
  matches `^G[123] .* -> (PASS|FAIL)$`.
- `gate_g3_performance.sh`'s `G3 FAIL: ros2 topic hz … rc=` echo does not match
  the verdict regex, so a `capture()` abort surfaces as "G3 produced no verdict"
  rather than as a harvested FAIL. The exit status and the named gate are both
  correct; only the message is one hop indirect.
- A whitespace-only first line in `carla_autoware.containers` passes both
  preflights and lands as "produced no verdict" — right outcome, unhelpful message.
- `measure_route.py` / `measure_ndt.py` compare with `<=` where the spec says
  `< 1.0 m`. Pre-existing, and no measurement has landed within a float of the
  threshold.
- `tests/e2e/test_map_frame.py` has no test for `parse_origin` on malformed input
  (wrong arity, non-numeric). Behaviour verified safe — it raises `ValueError`.
- `.gitignore:5`'s `extension/build/` is a dead entry since the `extension/`
  deletion. Inert.
- `docs/mgrs-handedness.md`'s `Superseded` banner points readers at `docs/ue58/`,
  but the handedness _reasoning_ is not there — that file's body is the only
  written record of why the transform is what it is. The body is preserved intact
  below the banner.

### CARLA fork CI (`ci/ue58-ubicloud`)

- The gtest steps have no tests-run floor, so a bad `--gtest_filter` would pass
  while running zero tests.
- The `Record/Upload benchmark result` steps are carry-over sizing
  instrumentation, now dead config with vCPU fixed at 8.
- shellcheck install and lint are packed into one step, so a red X cannot
  distinguish an install failure from a lint failure.
- `numpy` is unpinned in CI while `map_tools/requirements.txt` pins `2.5.2`.
- `ubicloud_pr.yml` has no `paths:` filter, so the `tools` job runs on every PR in
  the stack.

### CARLA fork changes (in the nine draft PRs)

- `CARLA_SMOKE_PORT`'s bare `int()` `ValueError` names the bad literal but not the
  variable, so a raw traceback makes a mistyped variable name hard to spot.
- `smoke/test_encoding_cameras.py:20`'s docstring launch example still shows a
  plain `-carla-rpc-port=3654` with no mention of the override — correct as-is,
  since it matches the unchanged default.
- `install_autoware.sh --check`'s NVIDIA remediation string presumes Docker is
  installed when Docker is absent. It never produces a false OK, and the
  `--- Tooling ---` block above it already reports `docker : MISSING`.
- PR #28 cites Autoware's "announced" hard error for `is_dense` without a link;
  no citable upstream reference was reachable, and the PR does not rest on it.
- The PR bodies use first-person phrasing in places, which is fine on a fork and
  is to be swept when they are reused upstream.

### Hand-off scripts (`~/ue58-logs/handoff/`)

- `upstream-branches.sh`'s `STACK` ordering is load-bearing for
  `own_contribution()` with only a descriptive `# Bottom-first.` comment and no
  in-script guard.
- Its `OK:` line takes the else branch on "not greater than" rather than checking
  `-eq`, so a theoretical `NCOMMITS < OWN_COMMITS` would print "exactly right".
  Unreachable given the stack's real history, and an authoritative commit log is
  printed unconditionally beside it either way.
- `~/ue58-logs/24-metrics.txt` is **annotated, not corrected**: its 239
  measurement lines are intact below a dated header, so a reader grepping into its
  middle can still land on the withdrawn narrative. Quote
  `~/ue58-logs/p2-03-evidence.md` instead.

## Open questions

Carried forward from `pr-candidates.md`, plus what Phase 2 added.

1. **Candidate 7 — simulator SIGSEGV on teardown SIGTERM.** Reproduces on every
   live run under both middlewares, including all three Phase 2 cells. Benign
   (it happens inside the simulator's own shutdown, after the run) but undiagnosed;
   entry point is the editor `-game` shutdown path.
2. **Candidate 11 — `autoware_demo.py` ignores SIGINT.** `run_sync_simulation_loop`
   already catches `KeyboardInterrupt`, so the hang is inside the C++ tick and needs
   its own investigation.
3. **Candidate 16 — transient NDT scan-matching degradation.** Fired 11
   `EMERGENCY_STOP` events in an otherwise clean Phase 1 run. May be Autoware-side
   tuning rather than a CARLA defect; needs diagnosis before filing.
4. **Candidate 8 — MGRS runtime fallback.** Blocked on a Phase 3 live need;
   Town10HD is `projector_type: Local`, so no Phase 1 or Phase 2 cell exercised it.
5. **Spawn-129 non-determinism (new).** 1 of 3 arrivals on the identical committed
   fixed map, discriminated by a reverse pull-out path rather than by the map or by
   warm/cold start. Undiagnosed.
6. **The older-Autoware compatibility probe (new).** Unmet — the plan's pinned
   Humble tag does not exist and the installer's `TIERIV_BASELINE_TAG` is
   source-mode-only. Needs a real older tag, or a source-mode build, to answer.
7. **Per-distro `autoware_data` model directories (new).** The read-write bind
   mount means a Humble cell rewrites the TensorRT plans a Jazzy cell reads. Worth
   deciding before any further cells; the next Jazzy run pays the same one-time
   rebuild.
8. **The Humble cell's unexplained 9.849 Hz LiDAR window (new).** Inside tolerance,
   and the engine-rebuild explanation was tested and does not fit.

## A note on method, because it shaped this record

Five separate corrections in this campaign share one shape, and it is worth stating
once: **testing the paths that are easy to reach instead of the path that carries
the claim.** The falsified map causal claim, the CycloneDDS parity framing, an
untested cold-start table row, the gate false-pass whose stub omitted the real
script's progress echo, and a hand-off guard verified only on its easy error paths.
Every figure in this file was recomputed from raw per-sample rows or re-derived
from the code, not copied from a summary line — and where a task report and a later
audit disagreed, the audit's number is the one written here.
