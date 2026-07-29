# benchmarks

## Purpose

This directory holds the reproducible measurement harness for the
three-approach CARLA↔Autoware integration evaluation described in the
project's design spec, "Three-Approach CARLA↔Autoware Integration
Evaluation Design". It exists to turn that spec's claims (C1–C3) into
pre-registered, regenerable evidence rather than one-off numbers.

## Data contract

A future `bench_observer` must emit the following files for every run:

| File                 | Columns / schema                                                                | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `observer.csv`       | `topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes` | `clock_ns` is the latest `/clock` value seen at arrival; `-1` before the first clock is received.                                                                                                                                                                                                                                                                                                                                       |
| `clock.csv`          | `clock_ns,arrival_system_ns`                                                    | One row per `/clock` receipt.                                                                                                                                                                                                                                                                                                                                                                                                           |
| `published_time.csv` | `topic,source_header_ns,published_ns`                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `resources.csv`      | `sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf`        | One row per process per sample. `gpu_util_pct`/`vram_bytes` are `-1` for a process with no GPU context. `rtf` is the sim/wall rate at that instant (`-1` before the first `/clock`) and repeats across the processes sharing a `sample_system_ns`; it is the per-sample series `evaluate_ceiling` consumes.                                                                                                                             |
| `odometry.csv`       | `topic,header_stamp_ns,x_m,y_m`                                                 | One row per `/localization/kinematic_state` receipt, written by bench_observer's typed subscription. That same receipt also emits a row to `observer.csv` with `size_bytes = 0` — a typed (deserialized) subscription has no serialized-size handle, unlike the generic subscriptions used for pointcloud/camera topics. M2/M4 byte metrics only ever read those generic-kind topics, so the sentinel is never consumed as a real size. |
| `gt.csv`             | `arrival_system_ns,sim_ns,x_m,y_m,z_m,yaw_rad`                                  | One row per CARLA world tick, written by `benchmarks/scripts/collect_gt.py`, the M5 ground-truth source.                                                                                                                                                                                                                                                                                                                                |
| `manifest.json`      | the `RunManifest` schema implemented in `benchmarks/analysis/manifest.py`       |                                                                                                                                                                                                                                                                                                                                                                                                                                         |

Results are laid out on disk as:

```text
benchmarks/results/<cell>/run-<NNN>/{manifest.json,observer.csv,clock.csv,published_time.csv,resources.csv,odometry.csv,gt.csv}
```

## Patch policy

> No changes to any approach's data-path, conversion, or transport code.
> Sensor-parameter, launch-parameter, and scenario-script edits are
> permitted, are the minimum possible, and are committed as reviewable
> patches under `benchmarks/patches/<approach>/` with full diffs
> reproduced in the report appendix.

### Named exception (pre-registered 2026-07-28, before any P3 run)

`patches/python-bridge/0001-lidar-is-dense.patch` — a one-line
change on the bridge's publish path (`is_dense = True` on a cloud that
contains no invalid points, so the flag is also _correct_). Without it
every E-family closed-loop cell is unmeasurable (P1 Verdict 1) and C2
degrades to structural analysis. The as-shipped behaviour is preserved
as cell E0's measured result. Cells E and E-opt run WITH this patch and
say so. Like the spec's E-opt arm, this exception is flagged for the
owner to strike; striking it drops cells E and E-opt, not E0.

## Metrics

### M5 definitions (pre-registered 2026-07-28)

- `goal_closest_approach_m`: min distance ego-to-goal inside the scoring
  window (the gate metric, threshold 1.0 m — continuity with P1's G2).
- `goal_terminal_distance_m`: ego-to-goal at window end (reported next
  to closest approach; distinguishes precise arrival from overshoot).
- `lateral_deviation_m`: distance from ego odometry to the committed
  route polyline (`config/routes/<map>.yaml`) — p95 over the window.
- `pose_error_m`: NDT pose minus CARLA ground truth (`gt.csv`), joined
  at nearest sim-time stamp within 25 ms.
- Per-cell validation gate (must pass before a cell's numbers count):
  NDT output rate ≥ 90% of expected AND goal_closest_approach < 1.0 m
  AND the localization criterion of the pre-registered G1 ladder:
  (a) if the Town10 pcd registration fix (Task 11) landed: max
  pose_error < 0.5 m; (b) otherwise: no drift (|mean of last 20% −
  mean of first 20%| < 0.2 m) and p95 − p50 < 0.3 m, with the constant
  bias reported. Which branch applied is recorded per cell.
- Scoring windows: closed-loop = spatial gate between the route-station
  bounds in `config/routes/<map>.yaml` after a 20 s warm-up discard;
  static = wall window [t0 + 20 s, end].

## Cell matrix

`benchmarks/config/cells.yaml` is the pre-registered workload matrix. Each
entry's `id` (e.g. `A`, `B`, `E0`, `CAL-rmw`) is the label a measurement run
is filed under — it is what `benchmarks/run.sh <cell>` takes as its argument
and what `benchmarks/results/<cell>/` is named after. P0 registered the
matrix; `run.sh` (P2, Task 8) executes it.

`benchmarks/config/exclusions.md` is the pre-registered set of criteria
under which a run may be marked `excluded: true`; it may not be edited
after the first P3 measurement run.

## Known confounds

Differences between cells that are not part of the design (C1–C3) but bear
on how their results should be read together. Recorded here, pre-registered
like everything else in this file, so Task 22's confound table for the P3
report has a single source instead of being reconstructed from task reports
after the fact.

### Route difficulty: Town10 (cells A/B) vs. Nishi-Shinjuku (cells C/D)

`benchmarks/config/routes/<map>.yaml`'s route is not a free choice per map —
each is the exact spawn/goal a prior gate was already measured on, so
swapping either for a "harder" or "easier" one would break continuity with
those measurements. `benchmarks/scripts/pick_route.py` pre-registers four
gate-honesty properties (shortest-path length, accumulated heading change,
straight-line separation, no early approach to the goal) that stop the tool
from _selecting_ a route that flatters the 1.0 m G2 goal gate; here they are
used diagnostically, on routes that were fixed before the properties existed,
not as a filter:

| Route                   | Cells | Total length | Straight-line separation  | Accumulated turn       | Closest prior approach |
| ----------------------- | ----- | ------------ | ------------------------- | ---------------------- | ---------------------- |
| `Town10HD_Opt.yaml`     | A, B  | 438.9 m      | 250.9 m (57.2% of length) | 233.0° — PASS ≥ 60°    | 33.5 m — PASS ≥ 10 m   |
| `NishishinjukuMap.yaml` | C, D  | 230.5 m      | 227.3 m (98.6% of length) | 35.8° — **FAIL** ≥ 60° | 29.4 m — PASS ≥ 10 m   |

The Nishi-Shinjuku route does not clear the accumulated-turn property: it is
98.6% a straight line, with 35.8° of total heading change against Town10's
233.0°. **This is a genuine confound, not a defect to fix**: cells A/B and
C/D are not scored on comparable route difficulty, so a closed-loop quality
metric (e.g. `lateral_deviation_m`, `goal_closest_approach_m`) that passes on
a Nishi cell is a weaker statement than the same metric passing on a Town10
cell — a mostly-straight 230 m drive is an easier control problem than a
439 m drive through several junction turns. Any P3 report comparing M5
closed-loop numbers across map families must state this alongside the
numbers, not just alongside the route's provenance.

### Perception load: clear-road stand-in (A/B/C/D) vs. real CUDA perception (E family)

The UE5-tree cells run Autoware with its perception module **off** and
`benchmarks/injector/dummy_perception.py` supplying the empty "clear road, no
dynamic objects" outputs plus all-green traffic signals in its place. The
python-bridge cells (E, E0, E-opt) run the **real** perception stack, CUDA
`lidar_centerpoint` included: the pinned `bridge-bench` base resolves
`autoware_ground_segmentation_cuda`, so `perception:=false` is no longer
needed there, and disabling it would measure a bridge configuration nobody
would deploy (`benchmarks/patches/python-bridge/README.md`, "Pin update").
`benchmarks/cells/python-bridge.sh` therefore sets `INJECTOR_ENABLED=0` while
`benchmarks/cells/{extension,tier4-native}.sh` set it to 1.

**This is a genuine confound, not a defect to fix**, and it is first-order for
two metrics:

- **M3 (resource cost).** The E family's Autoware container carries a full DNN
  detection + ground-segmentation load that A/B/C/D's does not. A
  cross-approach CPU/GPU/VRAM comparison that pools them is comparing
  workloads, not integrations: the E family's M3 numbers bound the bridge
  configuration's total cost, and are not a like-for-like difference against
  the natives.
- **M5 (closed-loop quality).** A/B/C/D drive against a perfectly clean,
  always-green world; the E family drives against whatever its detector
  actually reports. A `lateral_deviation_m` or `goal_closest_approach_m`
  result is a weaker statement on the E family than the same number on a
  native cell, and a worse one is not by itself evidence about the
  integration.

The alternative — running the dummy injector on top of live perception — would
have two publishers on `/perception/object_recognition/objects` and is not a
configuration either approach ships. Task 22's confound table must state this
alongside the numbers, not merely note the difference.

## Pre-registration

The git history of this directory is the pre-registration record: metric
definitions (`benchmarks/analysis/`), equivalence margins
(`benchmarks/config/margins.yaml`), and the exclusion criteria above are
all committed before the first measurement run. Each result's
`manifest.json` records `harness_git_sha`, so any result can be tied back
to the exact analysis code that scored it.

### Amendment rule

Stated for margins in `benchmarks/config/margins.yaml` and applying to every
pre-registered artifact here: they may be changed only **before the first P3
measurement run**, in a dedicated commit that states the reason per item, and
only to close a gap against the spec — never to accommodate a number already
measured. After the first run neither kind of change is legitimate.

Amendments made so far:

- **2026-07-27** — `analysis/manifest.py`: `validate()` is now called by
  `save()` and by `report.summarize_run`, and cross-checks `cell` against
  `config/cells.yaml`. Completeness: the rule existed but ran on no path, and
  an unregistered cell id splits a duel across two rendered cells, so the
  pre-registered n ≥ 10 could be missed silently.
- **2026-07-27** — `analysis/ceiling.py`: `evaluate_ceiling` gained the
  unpaced arm's `tick_rate_ratio` disjunct. Completeness: the spec
  pre-registers four ceiling disjuncts and only three were expressible.
- **2026-07-27** — the `resources.csv` contract above gained
  `gpu_util_pct`, `vram_bytes` and `rtf`, with `analysis/bench_io.py`
  `read_resources_csv` to read them. Completeness: M3 names GPU util/VRAM and
  the ceiling criterion needs a per-sample RTF series; neither had a column.
- **2026-07-28** — `analysis/manifest.py`: `RunManifest` gained a
  `placement` block (`run_mode`, `container_image`, `observer_env`, plus
  `engine_build_id` for UE-based approaches), enforced in `validate()`;
  the existing manifest-constructing tests were updated to supply it.
  Completeness: the spec requires per-cell process placement and run
  mode recorded, and no field existed for it.
- **2026-07-28** — `config/cells.yaml`: E0's `arms` changed from
  `[closed-loop]` to `[static]`. Completeness: P1 Verdict 1 found the
  as-shipped bridge cannot close the loop (is_dense rejection +
  sync-tick stall); E0 now measures the as-shipped configuration to its
  failure point instead of registering an arm it cannot run.
- **2026-07-28** — `config/cells.yaml`: gained a `camera_classes` list
  (cam1/cam3/cam6, applying to A/B/E). Completeness: the spec's M4
  camera-load arm had no registered classes.
- **2026-07-28** — `config/exclusions.md`: gained criteria 4-8 (clock
  stall, Nishi-Shinjuku warm-up, host load, RPC port collision, engine
  BuildId mismatch). Completeness: all five are P1-verdict-backed
  failure modes that would otherwise be ad-hoc judgement calls made
  mid-campaign instead of pre-registered.
- **2026-07-28** — the data contract above gained `odometry.csv` and
  `gt.csv`. Completeness: M5 needs ego pose and ground truth, and no
  file carried either.
- **2026-07-28** — the patch policy above gained a named exception for
  `patches/python-bridge/0001-lidar-is-dense.patch`. Completeness: P1
  Verdict 1 found every E-family closed-loop cell unmeasurable without
  it; the exception records the deviation before any P3 run rather than
  after.
- **2026-07-28** — this file gained the `## Metrics` section above,
  defining M5's `goal_closest_approach_m`, `goal_terminal_distance_m`,
  `lateral_deviation_m`, `pose_error_m`, the per-cell validation gate,
  and the scoring windows. Completeness: P1 Verdict 6 flagged the
  closest/terminal ambiguity and none of M5 had a pre-registered
  definition.
- **2026-07-28** — `pins.yaml` gained `engine.build_id`,
  `extension_carla_fork`, and `tier4_carla_fork` provenance slots.
  Completeness: later tasks need to record the engine BuildId and fork
  SHAs a run used, and `pins.yaml` had no place for them.
- **2026-07-28** — this file gained the `## Known confounds` section above
  (Town10 vs. Nishi-Shinjuku route difficulty: 233.0° vs. 35.8° accumulated
  turn, computed with `benchmarks/scripts/pick_route.py`'s own four
  gate-honesty properties directly on `benchmarks/config/routes/*.yaml`'s
  committed polylines; also recorded as a comment block in
  `NishishinjukuMap.yaml` itself). Completeness: Task 7 review found the
  Nishi route inherited from P1 does not clear the accumulated-turn
  property Town10's route does, and nothing recorded that cells A/B and
  C/D are not scored on comparable route difficulty before any P3 run.
- **2026-07-28** — `## Known confounds` gained the perception-load entry
  (clear-road injector on A/B/C/D vs. real CUDA perception on the E
  family). Completeness: Task 8's cell launchers fixed that split
  (`INJECTOR_ENABLED`), and it is a first-order M3 and M5 comparability
  difference that was recorded only in a task report.
- **2026-07-28** — `config/exclusions.md` criterion 1 widened to also
  cover the cell launcher itself failing to come up (`crash:cell-launch`
  for a readiness-probe timeout or a launcher prerequisite refusal), not
  only a process exiting abnormally. Completeness: a Task 8 re-review
  found `run.sh` filing that case under criterion 1 while its text
  described only a process crash — a materially different claim about
  the approach under test, and Task 22 tabulates by reason.
- **2026-07-28** — `config/exclusions.md` criterion 2 widened from "M5
  validation-gate failure" to "bring-up gate failure", explicitly naming
  the clear-road perception injector failing to start
  (`gate:injector-failed`) and the gated control command never flowing
  after a successful engage (`gate:control_cmd-silent`) alongside the M5
  localization/goal sanity check (`gate:arm-failed`). Completeness: the
  same re-review found `run.sh` already filing both under criterion 2
  without its text describing either.
- **2026-07-28** — `config/exclusions.md` criterion 4's reason narrowed
  from the wildcard `stall:<detail>` to the literal `stall:clock`, and
  new criterion 10 added for `stall:unpaced-window-cap`. Completeness:
  the wildcard read as if criterion 4 also registered a short-but-still-
  advancing unpaced window, which is the opposite of the frozen-clock
  condition the watchdog actually detects (by design, per `run.sh`'s own
  comment, the watchdog never fires on this case) — two distinct failure
  classes need two criteria, not one wildcard covering both.
- **2026-07-28** — `config/exclusions.md` gained criterion 9 for a
  harness recorder (the resource sampler, GT collector, or clock
  watchdog) exiting during start-up (`crash:sampler`, `crash:collect_gt`,
  `crash:clock_watchdog`). Completeness: criterion 1's process list names
  the simulator and stack under test, not the harness's own recorders — a
  recorder dying says nothing about whether the approach under test
  crashed, so it needed its own criterion rather than borrowing theirs.
- **2026-07-28** — `analysis/manifest.py`: `validate()` now checks
  `exclusion_reason` against the pre-registered vocabulary above (a fixed
  set of exact reasons plus a small set of prefixes for reasons that
  legitimately carry a variable per-run detail), rejecting anything else.
  Completeness: `validate()` previously only checked that
  `exclusion_reason` was non-empty, which is exactly why the five
  amendments above were invisible until a manual re-review instead of
  failing at manifest-write time.

## How to run

`benchmarks/run.sh` is the single measurement entry point. One invocation
produces one `benchmarks/results/<cell>/run-<NNN>/`:

```bash
bash benchmarks/run.sh A --arm closed-loop            # one run of cell A
bash benchmarks/run.sh A --arm closed-loop --dry-run  # print the 14 steps
bash benchmarks/scripts/duel.sh A B --arm closed-loop --pairs 10
```

`--dry-run` resolves the cell, runs preflight read-only (`--no-clean`),
writes and validates the manifest into a scratch directory, runs the cell
launcher's `plan` (prerequisite checks only), and prints every command it
would run — without touching `benchmarks/results/` or booting anything.

Flags: `--class <sweep-or-camera-class>`, `--unpaced`, `--runs N`,
`--no-observer` (records `/clock` only), `--rpc-port N`, `--rmw`, `--shm`,
`--dds-profile`.

The analysis modules live in `benchmarks/analysis/` (manifest schema,
clock fit, CSV loading, cadence, latency, stats/margins, ceiling
evaluation, spatial window, M5 quality). The entry point for rendering a
per-cell report is `python3 -m benchmarks.report <results_dir>`; `run.sh`
runs it as its own last step, so a run directory that does not render is a
loud failure rather than a silent one.
