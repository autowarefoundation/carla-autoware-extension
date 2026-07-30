# benchmarks

## Purpose

This directory holds the reproducible measurement harness for the
three-approach CARLA↔Autoware integration evaluation described in the
project's design spec, "Three-Approach CARLA↔Autoware Integration
Evaluation Design". It exists to turn that spec's claims (C1–C3) into
pre-registered, regenerable evidence rather than one-off numbers.

## Data contract

A future `bench_observer` must emit the following files for every run:

| File                    | Columns / schema                                                                                                                          | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `observer.csv`          | `topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes`                                                           | `clock_ns` is the latest `/clock` value seen at arrival; `-1` before the first clock is received.                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `clock.csv`             | `clock_ns,arrival_system_ns`                                                                                                              | One row per `/clock` receipt.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `published_time.csv`    | `topic,source_header_ns,published_ns`                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `resources.csv`         | `sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf,loadavg_1m`                                                       | One row per process per sample. `gpu_util_pct`/`vram_bytes` are `-1` for a process with no GPU context. `rtf` is the sim/wall rate at that instant (`-1` before the first `/clock`) and repeats across the processes sharing a `sample_system_ns`; it is the per-sample series `evaluate_ceiling` consumes. `loadavg_1m` is the **host-wide** 1-min load average at that instant and repeats the same way — see "`loadavg_1m` — in-run host load" below for what it does and does not mean, and for the NaN convention on runs filed before the column existed. |
| `odometry.csv`          | `topic,header_stamp_ns,x_m,y_m`                                                                                                           | One row per `/localization/kinematic_state` receipt, written by bench_observer's typed subscription. That same receipt also emits a row to `observer.csv` with `size_bytes = 0` — a typed (deserialized) subscription has no serialized-size handle, unlike the generic subscriptions used for pointcloud/camera topics. M2/M4 byte metrics only ever read those generic-kind topics, so the sentinel is never consumed as a real size.                                                                                                                         |
| `pose.csv`              | `topic,header_stamp_ns,x_m,y_m`                                                                                                           | One row per NDT pose receipt (the cell's registered `ndt_topic`), written by bench_observer's typed `pose` subscription, with the same `size_bytes = 0` sentinel row in `observer.csv` as `odometry.csv`. A SEPARATE file from `odometry.csv` even though the schema is identical: that one carries the EKF-fused `/localization/kinematic_state`, a different quantity, and M5's `pose_error_m` is defined on the NDT pose alone. Read with `analysis/bench_io.py` `read_pose_csv`.                                                                            |
| `tf.csv`                | `topic,frame_id,child_frame_id,header_stamp_ns`                                                                                           | One row per `/tf` transform whose `child_frame_id` matches the one registered in that cell's topic list (kind `tf`, whose fourth spec field is that frame), written by bench_observer's typed `tf` subscription with the same `size_bytes = 0` sentinel row in `observer.csv`. The parent `frame_id` is recorded but NOT filtered on, so a map→base_link claim is verified rather than assumed. Read with `read_tf_csv`.                                                                                                                                        |
| `gt.csv`                | `arrival_system_ns,sim_ns,x_m,y_m,z_m,yaw_rad`                                                                                            | One row per CARLA world tick, written by `benchmarks/scripts/collect_gt.py`, the M5 ground-truth source.                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `publisher_counts.json` | `{"schema": "publisher_counts/2", "topics": {<topic>: {"count": n, "sim_stamps_ns": [...]}}}`                                             | The M2 reconciliation's publisher-side term, written by `collect_gt.py --count-lidar` and read through `analysis/publisher_counts.py`. One SIM stamp per published message (`gt.csv`'s `sim_ns` domain and rounding), so the count can be windowed to the run's scoring window exactly as the expected and observed counts are. ABSENT by design on the python-bridge cells, where the bridge's own `sensor.listen` callback is the publish path — see "Reconciliation window and scope" below.                                                                 |
| `manifest.json`         | the `RunManifest` schema implemented in `benchmarks/analysis/manifest.py`                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `quality.json`          | `dataclasses.asdict(analysis.quality.QualityStats)` plus `arm`, `window_sim_ns`, `goal_window_sim_ns`, `ladder_branch`, `expected_ndt_hz` | The M5 gate's recorded verdict for the run; `gate_pass` is the single field a consumer may treat as that verdict. See "M5 gate result (`quality.json`)" below. Written by `benchmarks/scripts/write_quality.py`, run as `run.sh` step 13. ABSENT when the gate REFUSED to score the run (an unselected G1 ladder branch, a null `ndt_expected_hz`, a missing input): absence means not scored, never a pass.                                                                                                                                                    |

Results are laid out on disk as:

```text
benchmarks/results/<cell>/run-<NNN>/{manifest.json,observer.csv,clock.csv,published_time.csv,resources.csv,odometry.csv,pose.csv,tf.csv,gt.csv,publisher_counts.json,quality.json}
```

### `loadavg_1m` — in-run host load (added 2026-07-30, before any P3 run)

`resources.csv`'s eighth column. **Source:** `/proc/loadavg` **field 1** (the
1-minute average), read by `benchmarks/sampler/sample_resources.py`
`read_loadavg_1m` once per sample cycle and stamped onto every process row of
that cycle. **Why field 1 and not the 5- or 15-minute averages:**
`scripts/preflight.sh` gates on exactly this field (`awk '{print $1}'
/proc/loadavg`, abort at ≥ 8), so the in-run series is on the same basis as the
pre-run gate; and Task 13's ad hoc sampling recorded the same field (mean 25.80,
peak 50.05 on `results/B/run-009`), so this series is comparable with the
figures already in this record. Over a scoring window of this length the
smoother averages are dominated by load from **before** the run started.

**What it means.** "Was this run contended, and how much?" — answerable per
run, from the run's own filed data, after the fact. That is what the M3
comparability consequence below needed and did not have.

**What it does NOT mean**, stated because each of these is an easy misreading:

- **It is not attributable to any one process.** It is a whole-host figure, so
  it repeats across the rows sharing a `sample_system_ns` (exactly as `rtf`
  does) and the process on a row is not the cause of the number on it.
- **It is not a substitute for the per-process `cpu_pct` series.** Load average
  counts runnable-or-blocked tasks, not CPU time; the attribution table below
  (`autoware` 1832.5% mean, `carla-server` 280.5%, …) comes from `cpu_pct` and
  cannot be derived from this column.
- **It does not resolve a spike.** The 1-minute figure is itself a ~60 s
  exponential average, so it records the SUSTAINED level. `run-005` lost three
  rmw service responses inside one **0.4 s** window; this column would not have
  shown that window, only the elevated level around it.
- **It bounds nothing.** Recording is not capping — see "Host load during a run
  is unbounded" below, which stays open as a session-discipline matter.

**Three values, three distinct facts**, and none of them is interchangeable
(`analysis/bench_io.py` `RESOURCE_OPTIONAL_FLOAT_COLS`):

| value | meaning                                                                                                                                                                                                                        |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `NaN` | **not recorded** — the run predates the column, or the field is empty because the sampler was SIGTERMed mid-write. `loadavg_1m` is an OPTIONAL column and reads as NaN when absent, never as `0.0` and never as a missing key. |
| `-1`  | the column exists, the sampler tried, and `/proc/loadavg` was unreadable at that instant (`sample_resources.NOT_APPLICABLE`, as for `gpu_util_pct`). Preserved verbatim, so a caller masks it deliberately.                    |
| `0.0` | a real measurement: the host was idle at that instant.                                                                                                                                                                         |

**Backward compatibility is part of the contract, not a courtesy.** Every run
already filed — `results/B/run-007…012` and all of `results/E/`, which may not
be modified — carries the seven-column header.

**What makes that work is name-based access, not column position.**
`read_resources_csv` goes through `csv.DictReader`, keyed by header **name**;
`sampler/finalize_rtf.py` resolves `header.index("sample_system_ns")` /
`header.index("rtf")` out of the header it just read and writes that same header
back. So re-finalizing an already-filed run fills its `rtf` and **does not** add
a `loadavg_1m` it never sampled, and `read_resources_csv` returns an all-NaN
column of the right length for it. No committed consumer of `resources.csv`
reads it positionally.

**Appending the column last is a legibility convention, not the mechanism.** It
keeps the pre-2026-07-30 header a strict prefix, so a diff of a filed run against
a new one shows one **added** column rather than a shifted table — those runs are
retained evidence that has to stay comparable by eye. Do not read it as "position
is load-bearing": reordering would not break a reader, and neither would
inserting elsewhere. Keep new columns at the end for the prefix property alone.

Both halves are pinned — the NaN-on-absence behaviour against an old-format
fixture **and** against every real filed run, and the position-independence
against a deliberately shuffled header (`tests/benchmarks/test_bench_io.py`,
`test_finalize_rtf.py`).

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

### Second named exception (pre-registered 2026-07-29, before any P3 run)

**REGISTERED, NOT YET WRITTEN OR APPLIED.** A second one-file change on the
bridge's publish path is granted, on the same owner-strikable footing as the
first: `carla_ros.py`'s `pose()` publishes `ego_actor.get_transform()` as
`/sensing/gnss/pose_with_covariance` in the `map` frame, i.e. the CARLA actor
origin at the vehicle centre, where Autoware's contract for that topic is
`base_link` at the rear axle. The offset is measured, not assumed: 1.4045 m
along the heading against the 1.425 m the bridge itself applies in the opposite
direction when it spawns sensors
(`patches/python-bridge/README.md`, "E static localization bias").

No patch file exists yet and none is applied, deliberately. The grant was
requested on a hypothesis — that this offset was what blocked cell E's
closed-loop engage — which was then **refuted**: with
`use_autoware_pose_covariance_modifier` at its default `false`,
`ekf_localizer`'s pose input is NDT's topic and not this one, and NDT's
`regularization.enable` is `false`, so the only thing this topic reaches is
`pose_initializer`'s initial-pose seed. Spending the exception now would spend it
on a contested cause. It is therefore written and applied at cell E's re-gate,
where the causal attribution can be clean, and it is recorded here so that the
grant itself sits inside the pre-registration window rather than being invented
after a number is known.

## Metrics

### M5 definitions (pre-registered 2026-07-28)

- `goal_closest_approach_m`: min distance ego-to-goal inside the GOAL
  window (the gate metric, threshold 1.0 m — continuity with P1's G2).
- `goal_terminal_distance_m`: ego-to-goal at the goal window's end
  (reported next to closest approach; distinguishes precise arrival from
  overshoot).
- `lateral_deviation_m`: distance from ego odometry to the committed
  route polyline (`config/routes/<map>.yaml`) — p95 over the window.
- `pose_error_m`: NDT pose minus CARLA ground truth, joined at nearest
  sim-time stamp within 25 ms. The NDT pose comes from `pose.csv`'s rows
  for the cell's registered `ndt_topic` (bench_observer's typed `pose`
  kind) and the ground truth from `gt.csv`. NOT `odometry.csv`'s
  `/localization/kinematic_state`, which is the EKF-fused pose: scoring
  this metric on that would mask NDT error behind IMU/odometry fusion.
- Per-cell validation gate (must pass before a cell's numbers count):
  NDT output rate ≥ 90% of expected AND — **on every arm except
  `static`** — goal_closest_approach < 1.0 m AND the localization
  criterion of the pre-registered G1 ladder, whose
  branch is a property of **the map bundle THAT CELL localized against**,
  not of whether a fix has landed somewhere in the campaign:
  (a) the cell localized against a bundle whose pcd is registered to the
  world it runs in (for Town10, the **REGENERATED** bundle Task 11's ladder
  rung 2 produced — `pins.yaml` `town10_pcd_regen`, measured at max
  0.089 m; **not** the rigid `town10_pcd_shifted` / `town10_pcd_refit`
  variants, which were measured at 0.824 m and 0.570 m and so fall under
  (b)): max pose_error < 0.5 m; (b) the cell localized against a bundle
  carrying a known or unmeasured bundle-internal offset: no drift
  (|mean of last 20% − mean of first 20%| < 0.2 m) and p95 − p50 < 0.3 m,
  with the constant bias reported. Which branch applied is recorded per
  cell (`quality.json`'s `ladder_branch`).
  **On the `static` arm the two goal criteria do not apply at all**: a
  parked ego has no goal approach, so the gate there is the NDT-rate
  criterion plus the ladder criterion, and both goal fields are recorded
  as `null` rather than as a distance that measures nothing. Every other
  arm — including the sweep arms, which `run.sh` drives under either a
  static or a closed-loop `window_arm` — gets the goal criterion, since
  only the manifest's own `static` states that the ego was parked.
  Why it is keyed on the bundle: the Town10 fix is registered to the UE5
  world, so it applies to cells A/B; whether E's 0.9.15 world carries the
  same bundle-internal offset is MEASURED (E's static NDT bias, Task 10)
  before deciding which pcd variant E localizes against.
  A campaign-level "the fix landed" would gate cell E at 0.5 m against a
  bundle it may sit ~0.475 m off — failing E for a reason that reads as
  the bridge's. Task 11's rung-2 result makes this sharper still, since
  the branch now DIFFERS between two bundles of the same map: the
  regenerated Town10 bundle takes (a) and every rigid variant of it takes
  (b), so "which Town10 bundle" is not a detail. The bundle is whichever
  one that cell's launcher mounts:
  `scripts/e2e/map_defaults.sh`'s `/autoware_map/town10-regen` for the
  extension cells (via `run_e2e.sh` → `launch_autoware.sh`), the
  unshifted `~/autoware_map/town10` that `cells/python-bridge.sh` pins
  for the E family, and — for the tier4 cells, whose launcher defers the
  map to Task 13's `$TIER4_DEMO` — whatever that task wires, which it
  must do explicitly since it does not inherit `map_defaults.sh`. That is
  also why cells B/B-hf/B45 keep a `null` ladder binding: Task 11 could
  not settle their branch without knowing which bundle Task 13 mounts.
- Scoring windows: closed-loop = spatial gate between the route-station
  bounds in `config/routes/<map>.yaml` after a 20 s warm-up discard;
  static = wall window [t0 + 20 s, end].
- Goal window (owner ruling 2026-07-29): the two goal metrics above are
  computed over the **full armed span after the 20 s warm-up discard**
  — `window.static_window` over the ego odometry's own first and last
  SIM stamp — **warm-up-trimmed, NOT station-trimmed**, and recorded per
  run as `quality.json`'s `goal_window_sim_ns`. `pose_error_m`,
  `lateral_deviation_m` and the NDT rate stay on the scoring window
  above. The split is not a convenience: the station window's registered
  purpose (`analysis/window.py`'s own docstring) is that "every run
  scores the same stretch of road regardless of small speed
  differences", i.e. comparability of the rate/latency/resource metrics,
  while the goal criterion's registered purpose is continuity with
  P0/P1's G2 — which measured closest approach over the WHOLE run
  (0.064 m). Both committed routes set `stations.end_m` at (route length
  − 20 m) while their goal sits at the route's end, so the station
  window's last possible sample is 19.772 m (Town10) / 20.039 m
  (Nishi-Shinjuku) from the goal: scored there, the 1.0 m criterion
  could not be met by any honest run, and "terminal distance at window
  end" would not mean at end of run, which is what "distinguishes
  precise arrival from overshoot" requires. `stations.end_m` was NOT
  extended instead, deliberately: the paragraph below registers the same
  window for all five margin-carrying duel metrics, so moving it would
  move the campaign's headline equivalence measurement.

### Primary-duel metric definitions (pre-registered 2026-07-28)

The five metrics `benchmarks/config/margins.yaml` carries margins for. They
are the campaign's headline result — the A/B equivalence verdict — so each is
defined here to the level a second implementer needs to reproduce the number:
source file and columns, join rule and tolerance, aggregation, scoring window.
Margins are NOT touched here; this section defines what the metrics mean, not
what counts as equivalent.

**Arm scoping.** A cell's runs are not one population: `cells.yaml` gives cell
A `arms: [static, closed-loop]`, and the two arms measure different things
under different windows. The duel is therefore computed **per arm and reported
as separate rows, never pooled** — the runs under `results/<cell>/` must be
filtered by each run's `manifest.arm` before any aggregation, and the arm named
in the row. Task 18 runs `duel.sh --arm static --pairs 10` and `duel.sh --arm
closed-loop --pairs 10` as two separate sessions, each meeting the
pre-registered n ≥ 10 on its own, so pooling would both mix two quantities and
double-count toward that n. `control_staleness_ms` exists only on the
closed-loop arm; its static row is absent, never zero.

**Per-cell bindings.** No tool may hardcode a topic, a process label or a
rate. Each cell's entry in `benchmarks/config/cells.yaml` carries a `metrics:`
block (`lidar_topic`, `ndt_topic`, `control_topic`,
`control_published_time_topic`, `cpu_process_label`, `tick_hz`,
`lidar_expected_hz`, `ndt_expected_hz`, `ladder_branch`,
`abs_pose_gate_m`), read with
`benchmarks.scripts.cell_info.metrics_for(load_cells_doc(), <cell>)`. A `null`
binding is not a default to fill in at analysis time: the value is not
pre-registered yet, so the metric is UNAVAILABLE for that cell and the tool
must report it as such. `cells.yaml` names the task that owes each `null`, and
states the bar for a non-null value: committed evidence in this repo (a
constant in committed code, or a live measurement recorded in a committed
document). An out-of-repo script's literal does not clear it, in either
direction.

`tick_hz` (paced world tick, `1 / fixed_delta_seconds`), `lidar_expected_hz`
(sensor publish target) and `ndt_expected_hz` (NDT pose-output target) are
three different numbers. They coincide at 20.0 on cells `A` and `C` and are
independent everywhere: `--fixed-delta` moves the world tick, the rig's
`sensor_tick` is a separate knob, and the NDT rate follows the sensor. The
high-frequency cells are where that separation bites — Task 26 configures both
`A-hf` and `B-hf` by setting the tick AND the sensor ticks explicitly, so
neither cell's sensor rate can be derived from its tick rate, and all three
bindings on both cells are `null` naming Task 26 as their owner.

> **Status note (2026-07-30): those six `null`s are now PERMANENT, and that is a
> legitimate end state rather than a gap.** Task 26 was struck by the owner's
> core-duel scope cut (`cells.yaml` `dropped:` on `A-hf`/`B-hf`, and the
> amendment of that date below), so nothing is going to register what it applied
> and **no reader should expect a resolution.** What the nulls mean changes with
> it: they were provisional pending a measurement, and they are now final. This
> is the campaign's own registered vocabulary, not a new rule — a value that no
> committed evidence fixes and that no run's data mechanically discriminates is
> registered `null` **naming its owner**, so a tool reports the metric
> UNAVAILABLE for that cell instead of inventing one (`cells.yaml`'s header
> block; `cell_info.metrics_for` returns `None` as-is and the caller must say
> so). `cells.yaml`'s `A-hf` entry pre-registered exactly this outcome before it
> happened: "If the owner strikes Task 26 the cell is dropped and these stay
> null permanently — a legitimate end state, not a gap." **This note changes no
> binding, no threshold and no definition** — every rate binding, every divisor
> rule in this section and both `-hf` entries' values are exactly as they were;
> only the expectation of a future filler is withdrawn. The `sensor_tick`
> question `cells.yaml`'s `A-hf` comment raised with the plan owner (0.1 vs 0.01)
> is likewise closed as never-to-be-applied rather than answered.

Substituting one for another is never correct, even where they happen to
agree. An expected message COUNT must be derived from
`lidar_expected_hz`; only the M4 ceiling's unpaced `tick_rate_ratio` disjunct
divides by `tick_hz`; and the M5 gate's "NDT rate ≥ 90% of expected" criterion
(`analysis/quality.py`'s `expected_ndt_hz`) divides by `ndt_expected_hz`, which
follows the SENSOR rate and never the tick rate. `ndt_expected_hz: 20.0` on the
extension cells rests on a live measurement recorded in this repo —
`docs/e2e-report.md`'s re-run, NDT at ~20 Hz over 400 samples with the
ekf-fused `kinematic_state` at 19.97 Hz — not on the (true, but out-of-repo)
argument that `ndt_scan_matcher` emits one pose per input cloud.

**Scoring window.** All five are computed over the run's registered scoring
window (see "Scoring windows" above), resolved once per run:

The warm-up discard is `20_000_000_000` ns throughout (an int, matching
`window.py`'s `warmup_ns` parameter).

- closed-loop arm: `analysis/window.py` `spatial_window` over `odometry.csv`'s
  `/localization/kinematic_state` rows against the polyline and
  `stations.start_m`/`end_m` of `config/routes/<map>.yaml` — bounds are SIM
  ns.
- every other arm (`static`, `paced`, `unpaced`, `ablation`): see the two
  branches below, selected per run by a mechanical test on the run's own data,
  not by any config field.

**The window's branch is decided by the run's `clock.csv`, not by a cell
attribute.** What makes a sim/wall fit possible is whether a `/clock` series
exists — nothing else — so that is what the rule tests, applied per run:

- **Fittable branch — `clock.csv` holds ≥ 2 data rows** (exactly
  `fit_sim_wall_affine`'s own stated precondition, "need >= 2 paired (sim,
  wall) samples"): `static_window(t0, end, 20_000_000_000)` where `t0` and
  `end` are the FIRST and LAST `arrival_system_ns` in `clock.csv` — bounds are
  WALL ns. The other domain's bounds come from the run's affine fit
  (`analysis/clockfit.py` `fit_sim_wall_affine`): sim → wall by `sim_to_wall`,
  wall → sim by its exact inverse `(wall_ns - fit.intercept_ns) / fit.slope`.
  Rows are filtered on the column native to their file: `observer.csv` on
  `header_stamp_ns` (sim), `published_time.csv` on `source_header_ns` (sim),
  `resources.csv` on `sample_system_ns` (wall).
- **Unfittable branch — fewer than 2 data rows**: `static_window(t0, end,
20_000_000_000)` over **`observer.csv`**'s `arrival_system_ns`, first and
  last row of the cell's `lidar_topic`. There is no sim domain, so no
  conversion exists and none is applied; `observer.csv` rows are filtered on
  **`arrival_system_ns`** here — the same column the bounds are taken from, so
  the warm-up boundary is exact rather than offset by one message's transport.
  `header_stamp_ns` is itself wall time on such a run (the bench publishers
  stamp with wall `now()`), so the metric definitions below read the same way
  with no special case, and `one_hop_wall_ms` reduces to the direct
  `arrival_system_ns - header_stamp_ns` — `cal_report._one_hop_ms`'s form.

**Expected branch per cell, so a surprise is loud.** The calibration-approach
cells (`cells.yaml` `approach: calibration` — `CAL-rmw` and `CAL-seam`) are
expected to take the unfittable branch: they are transport/serialization
instruments with no simulation loop, and `config/processes/CAL-seam.yaml`
registers no ticking runner, unlike cells A/C which register `python3 -m
runner`. Every other cell is expected to take the fittable branch. A run that
takes the branch its cell was not expected to take is a **loud finding to be
reported, not a silent fallback** — it means the cell did not run the way it
is registered to.

**Who builds that check.** Nothing enforces the paragraph above today, and it
is the half of this rule that makes the discriminator safe rather than merely
correct — so it is an obligation with a named owner, not an aspiration. The
check belongs in the window-resolution step, beside the branch selection
itself: **Task 22** implements it for `scripts/duel_verdict.py` (which owes
windowing at all — see the same task's D7), and **Task 23** mirrors it in
`scripts/sweep_verdict.py`. Required behaviour: resolve the branch from the
run's `clock.csv`, compare it against the cell's expected branch (derived from
`cells.yaml` `approach`), and when they differ, surface the run in the rendered
table's notes naming both branches. It must be visible in the artifact a reader
sees, not only in a log. If the two tools grow a shared window resolver, the
check lives there once rather than twice.

> **Open contradiction in committed code, and now PERMANENTLY UNSETTLED
> (2026-07-30).** Cell CAL-seam was **struck** by the owner's core-duel scope
> cut (`cells.yaml` `dropped:`, and the 2026-07-30 amendment below), which took
> Task 14's live half with it — so there will be no CAL-seam run, nobody owes
> this resolution any more, and it cannot now be settled by measurement. The
> contradiction is kept on the record exactly as it was found: both halves are
> still in committed code, and a later campaign reviving the cell inherits it.
> **Nothing downstream is blocked**, for the reason the original entry gives at
> its end — `cells/calibration.sh` refuses the cell — and the metric rule above
> is correct either way, because it tests the data instead of the attribute.
>
> `cells.yaml` gives `CAL-seam` `carla: 0.10-fork`, so
> `cell_info.merge`'s `has_sim_clock` is true, so `run.sh` starts the clock
> watchdog for it (step 7), waits for a sim span off `clock.csv` on the unpaced
> path (step 10), and routes step 15 to `report.py`'s fit-strict renderer. But
> `scripts/cal_report.py` — which is the **CAL-seam** tool specifically, not a
> generic calibration one; its own first line says so — asserts that this cell
> has no `/clock` and that no fit is "needed, or even possible". Both cannot
> hold. If CAL-seam really has no `/clock`, every run of it is excluded
> `stall:clock` before analysis sees it, and `has_sim_clock` (or the `carla:`
> field it derives from) is wrong; if it does tick, `cal_report.py`'s premise
> is. This amendment does not pick: the metric rule above is correct either
> way, because it tests the data instead of the attribute. Task 14 must settle
> it — and register `CAL-seam`'s `tick_hz`, left `null` here for the same
> reason — before the cell is first run. It is unlaunchable today
> (`cells/calibration.sh` refuses it), so nothing is blocked meanwhile.

**Recorded consequence for Task 16.** The `one_hop_wall_ms` margin is frozen
from CAL-rmw, which takes the unfittable branch: an observer-windowed, unfitted
wall term. It is applied to a duel term that is `/clock`-windowed and
fit-converted. The measurand is the same; the window basis and the fit are not.
Task 16 must state that alongside the frozen number rather than presenting the
transfer as exact.

Windowing is not optional for these five. The 20 s warm-up covers map load,
NDT convergence and stack settling, which A and B do differently; against a
2.0 ms margin on `one_hop_wall_ms` a whole-run median is dominated by it.

**Aggregation.** Per run: the MEDIAN of the in-window per-message (or
per-sample) series — one run-level scalar per run. Across runs:
`analysis/stats.py` `bootstrap_ci_median_diff` + `equivalence_decision` on the
two cells' run-level scalars, `delta = median(A) - median(B)`, lower better.
Messages are never pooled across runs. Excluded runs never contribute. **Runs
of another arm never contribute** — see "Arm scoping" above; the filter is on
`manifest.arm` and it is part of the aggregation step, not a separate concern.

`achieved_rate_ratio` is the one EXEMPTION from the median-of-a-series rule:
it is already a single run-level scalar, `(n − 1) / span` over the in-window
rows, and there is no per-message series to take a median of. Building a
`1 / Δt` series and taking its median would be a different number, and the two
diverge exactly when frames drop — which is the phenomenon the metric exists
to measure. See its own entry below.

#### `one_hop_wall_ms` — transport (margin 2.0)

`analysis/latency.py` `one_hop_wall_ms(header_stamp_ns, arrival_system_ns,
fit)` over `observer.csv` rows for the cell's `lidar_topic`: observer arrival
wall time minus the wall time the run's clock fit maps that message's own sim
header stamp to. Single topic, so no join.

`report.py` `summarize_run` computes the same per-message quantity with the
same helper and reports it as `one_hop_p50_ms`, but over a DIFFERENT scope:
every topic, over the whole run, unwindowed. The duel metric is one topic, in
window, reduced to a median. The two names describe the same arithmetic and
must not be assumed to be the same number.

Relation to `scripts/cal_report.py`: the SAME measurand, a DIFFERENT code path,
deliberately. On **`CAL-rmw`** the publisher stamps `header.stamp` with wall
`now()` and nothing publishes `/clock`, so `cal_report._one_hop_ms` takes the
direct `arrival_system_ns - header_stamp_ns` and no fit is possible. Both
halves are evidenced for that cell and only that cell:
`benchmarks/observer/src/bench_pub.cpp`'s own first line scopes itself to
CAL-rmw and states "stamp is system now() so the CAL analysis
(`cal_report.py`) is a same-host wall-clock difference", and
`cells/calibration.sh` launches `bench_pub` plus the observer and nothing else.
**`CAL-seam` is not covered by this sentence**: its publisher pair is Task 14
and does not exist, so neither its stamp domain nor its `/clock` status is
known — see the open contradiction recorded under "Scoring window" above. A
simulated cell's stamps are sim-domain, so the fit is required there. The duel
term therefore carries the fit's error on top of the transport it measures, and
a duel row must be read next to that run's `fit_residual_ns`
(`report.summarize_run`).
Task 16 freezes this margin from CAL-rmw, i.e. from the `cal_report` path:
the transfer is legitimate because the measurand is identical, not because the
arithmetic or the window basis is — see "Recorded consequence for Task 16"
above.

#### `lidar_to_ndt_sim_ms` — pipeline (margin 5.0)

The sim-time elapsed between a scan's arrival at the observer and the arrival
of the NDT pose computed from that same scan, in SIMULATED milliseconds. It is
an observer-side proxy for the LiDAR-to-NDT pipeline, not a publisher-side
measurement of it: the name shortens "LiDAR to NDT", and the formula below is
what that means here.

- Join: `analysis/latency.py` `match_stamps` on `observer.csv`'s
  `header_stamp_ns` between the cell's `lidar_topic` and `ndt_topic`, EXACT
  equality, tolerance 0 ns. The hop propagates the stamp verbatim (the scan
  matcher re-stamps its output pose with the stamp of the scan it matched),
  which is why `latency.py` names lidar → NDT as one of the few hops
  `match_stamps` may be used on at all. Duplicate stamps on either side
  collapse to one pair (`match_stamps`' own documented behaviour).
- If the exact join yields no pairs, stamp propagation is broken for that run
  and the metric is UNAVAILABLE: report it. A nearest-stamp join is
  explicitly NOT permitted as a fallback — it would silently pair a pose with
  the wrong scan exactly when the assumption the metric rests on has failed.
- Quantity: because the two stamps are equal by construction,
  `segment_sim_ms` on them is identically zero and must not be used. The
  measured quantity is the matched pair's observer-arrival gap expressed in
  sim time, i.e. the wall gap divided by the run's clock-fit slope:
  `(arrival_system_ns[ndt] - arrival_system_ns[lidar]) / fit.slope / 1e6`.
- NOT `clock_ns`. `observer.csv`'s `clock_ns` is the latest `/clock` value
  cached at arrival, so it advances once per world tick — 50 ms at the
  registered `tick_hz: 20.0`. Diffing it gives the metric a 50 ms quantum
  against a 5.0 ms margin: every Δmedian would be a multiple of the tick, not
  a measurement.
- The arrival gap includes each message's own one-hop transport, so it is
  (pipeline) + (NDT transport − LiDAR transport). Both hops land on the same
  observer image, RMW, QoS and host in both cells, so that difference is a
  shared-mode term that largely cancels in A − B; `one_hop_wall_ms` measures
  it directly and is reported alongside.

#### `control_staleness_ms` — M1b staleness (margin 10.0)

Source: `published_time.csv` rows whose `topic` equals the cell's
`control_published_time_topic`. That is the PublishedTime topic's own name,
NOT `control_topic` — `bench_observer` writes the topic it subscribed to, and
the PublishedTime companion is a different topic. It is registered `null` on
every cell today: Tasks 13/20 append it to `observer_topics/<cell>.yaml`
after live discovery, and must register it here in the same commit.

Quantity: `analysis/latency.py` `staleness_ms(source_header_ns, published_ns)`
in ms — but only when both stamps are in the same clock domain. Which domain
each stamp carries is an empirical property of the Autoware image a cell pins
(`published_stamp` may come from the node's sim clock or from a default system
clock; `source_header_ns` is the publishing node's own header stamp), and must
be RECORDED by Tasks 13/20 alongside the topic name, not assumed. It must be
recorded **per image**, not once: `B45` pins a different Autoware image
(`pins.yaml` `autoware_045`) from every other stack cell, and nothing
guarantees the two agree. The discriminator below is applied per column, so all
FOUR combinations are distinguishable and all four are pre-registered here —
the choice cannot be made after seeing the number:

- (a) BOTH stamps in the SIM domain →
  `staleness_ms(source_header_ns, published_ns)`.
- (b) `source_header_ns` SIM, `published_stamp` WALL →
  `one_hop_wall_ms(source_header_ns, published_ns, fit)`, the publisher-side
  analogue of the transport term.
- (c) BOTH stamps in the WALL domain (the node is not on sim time) →
  `staleness_ms(...)` again: the domains match, so the plain difference is
  correct, and the result is a wall-domain staleness with sub-tick resolution.
- (d) `source_header_ns` WALL, `published_stamp` SIM → **no formula; the metric
  is UNAVAILABLE and the observation must be reported.** This combination is
  incoherent rather than merely inconvenient: it says a node stamped a
  sim-clock publish time onto a message whose own header it wrote from the
  wall clock, which no single-clock node does. Treating it as (b)-reversed
  would produce a large negative staleness that reads like a real result.
  Registered as a fail-loud so the discovery pass re-checks the topic rather
  than the analysis inventing an arithmetic for it.

The discriminator is mechanical and unambiguous: a wall stamp is a Unix epoch
(> 1e18 ns); a sim stamp is a run-length offset (< 1e13 ns for any window this
harness records).

**Contingent response under branch (a), pre-registered now.** This needs no
data: if both stamps land on the `/clock` grid, every per-message value is a
multiple of the tick period (50 ms at `tick_hz: 20.0`), so every per-run median
is too, so Δmedian is a multiple of 50 ms — and a TOST against ±10 ms can only
ever return `parity` at exactly Δ = 0 or a directional verdict, never anything
in between. Therefore: **under branch (a) `control_staleness_ms` is reported
descriptively (per-cell median and spread, both arms' rows labelled) and is
EXCLUDED from the equivalence verdict.** It contributes no `parity` /
`a_better` / `b_better` decision and no row to the headline table's verdict
column. The margin is NOT widened to accommodate the quantum: moving the
equivalence bar to fit an instrument's resolution is a worse remedy than
declining to decide. Branches (b) and (c) have sub-tick resolution and the
metric participates in the verdict normally under either.

#### `carla_process_cpu_pct` — M3 simulator CPU (margin 10.0 absolute points)

Source: `resources.csv` rows whose `process` equals the cell's
`cpu_process_label`, read with `analysis/bench_io.py` `read_resources_csv`.
That column is the `label` field of the matching entry in
`config/processes/<cell>.yaml` — `sampler/sample_resources.py` writes
`entry["label"]` verbatim — so the binding is a label, never a pattern and
never a process name.

Every cell that runs a simulator registers the label `carla-server`. What
differs per approach is the PATTERN behind that label (the extension fork's
uproject path, the tier4 fork's sibling path, or CARLA 0.9.15's
`CarlaUE4-Linux-Shipping`), which is precisely the comparison the metric
exists to make; a tool that hardcodes any string other than the registered
label matches zero rows and reads as "the simulator used no CPU". `CAL-rmw`
runs no simulator and registers `null`.

Quantity: `cpu_pct`, the sampler's sum over every PID matching the entry as a
percentage of ONE core — a multi-threaded server routinely exceeds 100. Median
over in-window samples. The 10.0 margin is absolute percentage points of that
same quantity.

#### `achieved_rate_ratio` — M2 rate (margin 0.02)

Source: `observer.csv` rows for the cell's `lidar_topic`. Quantity:
`analysis/cadence.py` `inter_arrival_stats(header_stamp_ns).hz /
lidar_expected_hz`, over the in-window rows.

This is already the run-level scalar — the exemption from the blanket
median-of-a-series aggregation rule noted above. `inter_arrival_stats.hz` is
`(n − 1) / span`; there is no per-message series here to take a median of, and
constructing one (`1 / Δt` per gap, then median) would be a different and
worse statistic: the median of instantaneous rates is insensitive to exactly
the dropped frames the metric is meant to catch.

`inter_arrival_stats` is domain-agnostic ((n−1)/span over any int64-ns
series); it is given the SIM header stamps and not the wall arrivals on
purpose. A wall-domain rate falls with the simulator's real-time factor, which
would put an RTF difference straight into a 0.02 margin; RTF is separately
measured as `resources.csv`'s `rtf` and is the M4 ceiling's own input. Taken in
the sim domain, the ratio measures dropped or skipped frames instead, which is
what M2 is for.

This is the OBSERVED rate, so it also carries observer-side loss. Both cells
are observed by the same `bench-observer` image, QoS and host, so that is a
shared-mode term in A − B; the M2 three-way reconciliation
(`cadence.reconcile_drops` over `publisher_counts.json`) separates publisher
drop from observer loss and is reported per cell alongside the duel row.

**A PERMANENT BOUND on that reconciliation, not pending a run (Task 13).**
`observer_loss_rate` is **uncomputable for the entire E family, for good** — not
"unmeasured yet". It needs `publisher_counts.json`, which `collect_gt.py`
produces only under `--count-lidar`, and that flag is **refused by design** for
`approach: python-bridge` (`LISTEN_OWNING_APPROACHES`): the bridge's publish path
_is_ a Python `sensor.listen` callback, so attaching a counter would displace the
very thing being measured. Only the **native** approaches can ever carry a
publisher-side term. A reader must not assume the E family's wire numbers carry
the same observer-loss correction B's do — they cannot, and no amount of
re-running changes it.

**And it is unmeasured for cell A as of Task 13**, for a different and fixable
reason: `benchmarks/results/A/` does not exist, so cell A has never been run
through this harness at all and has no `publisher_counts.json` either. Every
cell-A number the campaign holds (G1 0.089 m, G2 0.244 m) came from
`scripts/e2e/`, a different harness. Until a cell-A bench run exists the
reconciliation has a publisher-side term for **exactly one cell**, so the A − B
observer-loss asymmetry cannot be quantified.

**Measured on cell B, so the term's size is not hypothetical** (Task 13,
`lidar_expected_hz: 10.0`, `/sensing/lidar/top/pointcloud_raw_ex`):

| run                 | expected | published | observed | `publisher_drop_rate` | `observer_loss_rate` |
| ------------------- | -------- | --------- | -------- | --------------------- | -------------------- |
| `results/B/run-008` | 930      | 940       | 699      | **0.0000**            | **0.2564**           |
| `results/B/run-009` | 798      | 799       | 662      | **0.0000**            | **0.1715**           |

The publisher delivers everything expected on both runs, so the whole deficit is
observer-side. **But the bench observer is NOT a bad instrument** — measured
independently from inside the Autoware container on `run-010`, Autoware itself
receives that topic at **8.47 Hz** against the observer's 8.53 Hz on the
comparable run. Two unrelated subscribers losing the same ~15% means the loss is
**real on the wire**, on this family's mandatory SHM-off UDP transport with
~460 KB clouds, so the observed count is trustworthy rather than an artifact.

**Reconciliation window and scope.** Computed over the SAME resolved
scoring window this metric uses for that run — never a second,
independent window — and reported per cell AND per arm, never pooled
across either axis (mirroring "Arm scoping" above). **All three counts
are windowed to that one interval**; a term left whole-run against
windowed counterparts is not a coarser answer but a different quantity,
and on a healthy run it clamps `publisher_drop_rate` to 0.000 while
fabricating `observer_loss_rate` out of the interval mismatch alone.

- expected: `max(1, round(window_s * lidar_expected_hz))`, `window_s`
  the window's own span in **SIM** seconds (`lidar_expected_hz` is a
  sim-domain rate — see below).
- observed: `observer.csv` rows for the cell's `lidar_topic` whose
  `header_stamp_ns` lies in the closed interval `[sim_lo, sim_hi]`.
- published: `publisher_counts.json` entries for the same topic whose
  recorded sim stamp lies in that same closed interval.

`publisher_counts.json` (schema `publisher_counts/2`, written by
`scripts/collect_gt.py --count-lidar`, read by
`analysis/publisher_counts.py`) records one sim stamp per published
message — CARLA's episode `elapsed_seconds` through
`collect_gt.sim_ns_from_elapsed`, i.e. the same domain and rounding rule
as `gt.csv`'s `sim_ns` — precisely so the publisher-side term can be
windowed identically to the other two. A file in the earlier
`{topic: count}` shape holds a whole-run count that cannot be windowed
after the fact: it is REFUSED by name (surfaced as that run's FAILED
note), never read as though its count had been windowed.

An absent `publisher_counts.json` (the E-cell case: the bridge is the
sensor stream's only listener, so no independent publisher-side count
exists) is NOT MEASURABLE, distinct from a present file recording a real
zero throughput (`cadence.reconcile_drops`'s own NaN `observer_loss_rate`
branch) and from a refused one (a file that exists and cannot be
interpreted).

**Output states.** Four states this table renders. All are mechanically
discriminable from the data, so both branches of each are registered
here rather than settled in the implementation:

1. `lidar_topic` or `lidar_expected_hz` **not registered** (`null`) for a
   cell: that cell's row is `UNAVAILABLE` with all four rates `-`,
   decided without touching a single run directory. The counterpart
   cell's row is still computed — this diagnostic is per cell, unlike
   the duel row itself, which needs both sides bound to render at all.
2. `lidar_expected_hz` **registered but invalid** (`<= 0`): the same
   `UNAVAILABLE` row, mirroring `achieved_rate_ratio`'s own guard for
   the same binding. Without it the `max(1, …)` floor above would report
   a clean-looking ~0.000 drop rate beside that metric failing outright
   for the very same cell.
3. **Every measurable run had `published_count == 0`**: both observer
   statistics render `NaN`, not absent. `-` is reserved for "no
   measurable run at all"; a cell that measurably published nothing is a
   finding, and the two must not print the same.
4. A **per-run failure** (window unresolvable, `publisher_counts.json`
   refused, `lidar_topic` absent from that run's `observer.csv`): the run
   enters neither statistic and neither count, and is named in the row's
   notes with its exception type — never dropped silently.

**Cross-run reduction — owner ruling, 2026-07-28: median AND max, both
reported**, for both `publisher_drop_rate` and `observer_loss_rate`,
over each cell's measurable runs for that arm. Median keeps continuity
with the campaign's per-run → per-cell convention; max is reported
alongside because this output is an instrument-artefact DETECTOR, not
a central-tendency estimate of one — at the registered minimum of
n = 3 measurable runs, a single run in which the observer lost 40% of
its frames IS the finding, and median alone would report a clean 0.000
over it. `observer_loss_rate`'s reduction (both median and max)
excludes runs where it is NaN (a real, file-backed zero-throughput
run), with that count reported separately so it is never silently
folded into either statistic.

The two axes therefore reduce over different populations, and **both
sample sizes are printed**: `n measurable` is the publisher pair's n,
and `n observer` (`n measurable` − `n zero-published`) is the observer
pair's. One printed n beside four rates would misstate whichever pair it
did not belong to.

`lidar_expected_hz` is the cell's registered sensor target, filled by the
relation P1 Verdict 4 measured live: effective rate = `min(1 / sensor_tick,
tick_hz)`. It is a **sim-domain** rate — `sensor_tick` is a period of
simulation time, and `tick_hz` is `1 / fixed_delta_seconds`, also
simulation time — so every expected COUNT derived from it multiplies a SIM
span. A wall span overstates the count by `1 / RTF` on any run that is not
real-time, converting a rate expectation into a pacing measurement, which
the M4 ceiling already makes separately with its own `rtf` and
`tick_rate_ratio` disjuncts. Both consumers of `analysis/cadence.py`'s
`expected_count` therefore pass a sim span: `duel_verdict.py` the resolved
scoring window's `[sim_lo, sim_hi]`, `sweep_verdict.py` `clock.csv`'s
whole-run `clock_ns` extent. It is registered only where committed code
fixes it today (the
extension cells, from `runner/spawn.py`'s `_SENSOR_TICK`; `CAL-rmw`, from
`cells/calibration.sh`'s `PUB_RATE_HZ`). It is `null` on the tier4 and
python-bridge families, so this row of the A/B duel table cannot be computed
until Task 13 registers cell B's value — which is the pre-registration point,
not a defect: the target rate must be fixed before the data exists, and the
tier4 harmonization genuinely has not chosen it.

### M5 gate result (`quality.json`, pre-registered 2026-07-28)

The M5 gate's verdict is a recorded fact of the run, written once into the run
directory as `quality.json` — not recomputed by each consumer, and not folded
into `manifest.json`:

- Recomputation would decide the gate with whatever analysis code is installed
  at READ time, while every other number in this campaign is tied by
  `manifest.json`'s `harness_git_sha` to the code that produced it at RUN
  time; and two consumers recomputing independently can disagree.
- `manifest.json` is the run's provenance record, written before the run
  starts; its only legitimate post-hoc mutation is the exclusion marker. A
  derived analysis result does not belong there.

Schema: `dataclasses.asdict(analysis.quality.QualityStats)` verbatim —
`pose_err_p50_m`, `pose_err_p95_m`, `pose_err_max_m`, `pose_bias_m`,
`lateral_dev_p95_m`, `goal_closest_approach_m`, `goal_terminal_distance_m`,
`ndt_rate_ratio`, `gate_pass` (bool), `reasons` (list of str) — plus five
provenance keys the gate definition above requires to be interpretable:
`arm`, `window_sim_ns` (`[lo, hi]`), `goal_window_sim_ns` (`[lo, hi]`, or
`null` on an arm the goal criteria do not apply to), `ladder_branch`
(`"absolute"` | `"relative"`, the G1 branch that applied) and
`expected_ndt_hz`.

`goal_closest_approach_m` and `goal_terminal_distance_m` are `null` — not
a number — on the `static` arm, where the two goal criteria do not apply
(see the M5 definitions above). `goal_window_sim_ns` is `null` on exactly
those runs, so "the criteria did not apply" and "the ego never got near
the goal" are distinguishable in the record rather than both reading as a
bad number. The two goal metrics are computed over `goal_window_sim_ns`
and the rest over `window_sim_ns`; a reader comparing a goal number
against a scoring-window bound is comparing two different intervals.

`expected_ndt_hz` is written from the cell's `metrics.ndt_expected_hz` binding
and nothing else — it is `evaluate_quality`'s divisor for the "NDT rate ≥ 90%
of expected" criterion, and taking it from `tick_hz` would fail every A-hf run
by a factor of five while looking like a localization result. A cell whose
`ndt_expected_hz` is `null` cannot be gated: the M5 gate must refuse to write
a verdict for it rather than assume a rate.

`ladder_branch` is written from the cell's `metrics.ladder_branch` binding and
nothing else — never inferred from whether `abs_pose_gate_m` happens to be
null. The two are separate keys precisely so that inference is impossible:
`evaluate_quality(abs_pose_gate_m=None)` IS the relative branch, so one
nullable threshold could not distinguish a cell whose relative branch was
selected from a cell for which nothing has selected a branch at all — and the
second must refuse, not gate. The three registered states are

| `ladder_branch` | `abs_pose_gate_m` | effect                                                   |
| --------------- | ----------------- | -------------------------------------------------------- |
| `absolute`      | float             | absolute branch: `max pose_error < abs_pose_gate_m`      |
| `relative`      | `null`            | relative branch: no drift, bounded spread, bias reported |
| `null`          | `null`            | REFUSE: no verdict is written for this cell              |

and every other combination (`absolute` with a null threshold, `relative` with
a non-null one, an unrecognised branch name) is an inconsistent registration,
refused by name rather than repaired. WHICH branch a cell gets is a property of
the map bundle THAT CELL localized against, per the M5 definitions above; both
branches' thresholds are registered there and are unchanged here.

`gate_pass` is the single field a consumer may treat as the verdict.

The writer is `benchmarks/scripts/write_quality.py`, run as `run.sh` step 13
(after `finalize_rtf`, before the exclusion and smoke steps). It is NOT
`run.sh`'s `gate:arm-failed`, which is the bring-up arm check
(`injector/arm_and_goal.py`) and a different thing entirely.

That step REFUSES — writing nothing, exiting non-zero, naming the input —
rather than writing a defaulted verdict, whenever `ladder_branch` is
unselected, `ndt_expected_hz` or `ndt_topic` is `null`, an input file is
missing or unreadable, the run's `clock.csv` puts a non-closed-loop arm on the
unfittable window branch (there is no sim domain, so there is no sim window to
convert to), the manifest is already excluded, or the run's own data does not
support the measurement. `run.sh` treats that refusal as a WARNING, not an
abort: the run's data is already on disk and the exclusion step still owes the
directory a label, so aborting would leave it unlabelled and wedge every later
run of the cell. The ABSENCE of the file is what carries the refusal — a
consumer must fail loudly on it for any arm that closes the loop and never
default it to a pass, which is what `sweep_verdict._quality_ok` does, with
`ablation` as the one registered exception.

## Cell matrix

`benchmarks/config/cells.yaml` is the pre-registered workload matrix. Each
entry's `id` (e.g. `A`, `B`, `E0`, `CAL-rmw`) is the label a measurement run
is filed under — it is what `benchmarks/run.sh <cell>` takes as its argument
and what `benchmarks/results/<cell>/` is named after. P0 registered the
matrix; `run.sh` (P2, Task 8) executes it. Each entry's `metrics:` block is
the per-cell binding the analysis tools read (see "Primary-duel metric
definitions" above).

`benchmarks/config/exclusions.md` is the pre-registered set of criteria
under which a run may be marked `excluded: true`; it may not be edited
after the first P3 measurement run.

### Scope: the core duel only (owner decision, 2026-07-30)

**Six of the twelve registered cells will not be measured.** The owner cut the
campaign's scope to the core duel; the full per-item reasoning is the
2026-07-30 "core-duel scope cut" entry under `## Amendments made so far`, and
the strike is machine-readable in `cells.yaml` as a `dropped:` key.

| status                                                   | cells                                                          |
| -------------------------------------------------------- | -------------------------------------------------------------- |
| **in scope**                                             | `A`, `B` (the primary duel, n ≥ 10), `C`, `E0`, `E`, `CAL-rmw` |
| **struck** — was `mandatory: true` (amendment items)     | `CAL-seam`, `B45`                                              |
| **struck** — was already `mandatory: false` (note items) | `D`, `E-opt`, `A-hf`, `B-hf`                                   |

The M4 LiDAR-load sweep is reduced to a ceiling confirmation at the duel size,
so `sweep_classes`' `32ch` and `128ch` are struck too, and the M4 **camera-load
arm is struck in full** (`camera_classes` cam1/cam3/cam6). CAL-rmw runs at the
duel size only.

**`32ch` is the pre-registered step-up, on a branch the data decides.** If the
M4 ceiling criterion **fires** at `vlp16`, the spec's success criterion is met
by its first disjunct and `vlp16` alone suffices — the branch the strike
assumes. If it **does not fire**, the M4 claim's second falsifier has falsified
the claim and the ceiling is unlocated, so `32ch` is reinstated as the step-up
class; doing so is an **anticipated** amendment, registered here before any P3
run, not a novel one. `128ch` stays struck on either branch. Both branches are
written into `cells.yaml` beside `sweep_classes` for the same reason
`ladder_branch` / `abs_pose_gate_m` are two keys: a choice a run's own data
makes mechanically must be pre-registered on both sides, never settled after
seeing the number.

**What reinstating it actually costs, stated precisely rather than as "no work".**
The **registry** needs no edit — `cell_info --class 32ch` resolves today, because
the entry was kept registered rather than deleted, so no `cells.yaml` change is
required to run the class. But a `32ch` run is **not** turnkey: both sweep
launchers refuse a `--class` whose sensor arguments are not spelled out, because
nothing maps a class id onto them (`cells/tier4-native.sh`'s
`BENCH_TIER4_SWEEP_ARGS` refusal and `cells/extension.sh`'s
`BENCH_RUNNER_SWEEP_ARGS` refusal — a sweep run that quietly used the baseline
VLP16 rig would be filed as a `32ch` measurement). So the operator must supply
those arguments by hand — for the tier4 side, in the form that launcher's own
message gives: `BENCH_TIER4_SWEEP_ARGS="--lidar-channels 32 --lidar-pps 1200000"`
(patch 0003's flags, matching `32ch`'s registered `channels` / `points_per_second`).
The class→arguments mapping itself is still unwritten on **both** sides, and the
two name different owners: the tier4 side was owed to **Task 26**, which is
struck, so it now has **no owner** and that refusal is permanent until someone
writes it; the extension side is owed to **Task 12** per
`cells/extension.sh`'s own refusal text. The ruling that reinstatement is "a
decision, not an edit" is about the **pre-registration** — the branch needs no
new amendment — and is not a claim that no operator work is involved.

**Read the reason precisely.** Every strike is an owner **time-budget**
decision, taken on two measurements (recorded in the amendment). **None of
these cells was technically infeasible, blocked, or unmeasurable**, and no
result about any of them may be inferred from its absence. `B45` in particular
was expected to surface a hard-fork-maintenance result: the campaign is
choosing not to look, which is a different statement from "it failed". The
struck entries stay **registered, not deleted** — `mandatory: true` still
stands on `CAL-seam` and `B45`, because that flag is what records that a
mandatory cell was given up.

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
| `Town10HD_Opt.yaml`     | A, B  | 258.9 m      | 209.0 m (80.7% of length) | 169.4° — PASS ≥ 60°    | 33.2 m — PASS ≥ 10 m   |
| `NishishinjukuMap.yaml` | C, D  | 230.5 m      | 227.3 m (98.6% of length) | 35.8° — **FAIL** ≥ 60° | 29.4 m — PASS ≥ 10 m   |

Every row's closest-prior-approach is computed the way `pick_route.py` itself
computes it — excluding the last `APPROACH_SKIP_NODES = 15` polyline nodes
(~30 m), the genuine final approach. An earlier revision of the Town10 row
excluded only 5 nodes (~9 m) and so reported 11.3 m, which was **not**
comparable to the Nishi row beside it and understated the route's own margin.
Recomputed consistently: 33.468 m on the pre-re-pick Town10 route and 33.181 m
on the re-picked one. Both are recomputable from the tree — the re-picked route
is the committed one, and the pre-re-pick route is retained at
`benchmarks/evidence/route-town10-pre-repick/`, whose `PROVENANCE.md` carries
the exact snippet. (An earlier revision cited
`reports/task-15-town10/pick_route.log` for the 33.468 m, which is
`.gitignore`d and therefore not checkable from a clone — the same defect this
round fixed one directory over.)

The Town10 row moved with the 2026-07-29 route re-pick; it previously read
438.9 m / 250.9 m (57.2%) / 233.0° / 33.5 m. The re-picked route still clears
all four properties. **Closest prior approach is essentially unchanged**
(33.5 → 33.2 m); an earlier claim that it "moved toward its bound" was an
artifact of the inconsistent method above and is withdrawn. What did move is
straightness: separation is now 80.7% of length rather than 57.2%, so the two
routes are LESS different in that respect than they were. Accumulated turn
stays clear at 169.4°, so the Town10 route is still a genuinely turning drive
and the paragraph below still holds directionally — though by a smaller margin
than the original 233.0° vs 35.8°.

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

### Map provenance: self-built Town10 pcd (A/A-hf) vs. sourced Nishi-Shinjuku pcd (C)

**C4, added 2026-07-29.** The Town10 bundle the extension cells localize
against (`pins.yaml` `town10_pcd_regen`) was **rebuilt from this rig's own
LiDAR sweeps**, ground-truth-registered, by
`benchmarks/scripts/build_pcd_from_gt.py`. Nishi-Shinjuku's bundle is
independently sourced. That difference flatters Town10's localization numbers
and the comparison must say so:

- The regenerated map contains the returns this exact sensor produces, at the
  poses it drove — including the pose G1 measures from. A scan match against
  it is a materially easier problem than matching an independently-authored HD
  map, so **max NDT error 0.089 m on cell A is NOT directly comparable to
  Nishi-Shinjuku's 0.078 m on cell C**, even though the two look alike.
- It is nonetheless a legitimate G1 result rather than a tautology: the map is
  registered by CARLA **ground truth**, never by NDT's own estimate, so the
  pose it implies is the true pose and the error measured against ground truth
  is real. Ladder rung 2 pre-registered exactly this construction.
- Coverage is bounded by where the ego drove (see `town10_pcd_regen`), so the
  bundle is dense along the committed corridor and thins beyond it. The route
  re-pick keeps the drive inside the dense region — which also means the
  route and the map's dense region were chosen together, a circularity
  disclosed in the route-re-pick amendment.

Any P3 report comparing M5 localization numbers across map families must state
this alongside the numbers, exactly as it must for route difficulty above.

**Scope: RESOLVED 2026-07-30 by Task 13 — this stays a cross-map caveat and does
NOT escalate to a duel-level confound.** The conditional was: C4 leaves the A/B
primary duel intact only if cells A and B localize against the same bundle, and
cell B's ladder binding was `null` because Task 13 owned what the tier4 launcher
mounts. It mounts **`town10-regen`, the same bundle cell A localizes against**:
`benchmarks/cells/tier4_autoware.sh` resolves its map through
`scripts/e2e/map_defaults.sh` — the extension path's own table, read
deliberately rather than duplicated — and `benchmarks/scripts/preflight.sh`
resolves this family's bundle through that same table, so every B-family run's
`manifest.json` records `map_bundle_pin: town10_pcd_regen` as a checked fact
rather than an intention. Cells B/B-hf/B45 are registered on the ABSOLUTE branch
at 0.5 m accordingly. The alternative branch is kept for the record: had Task 13
mounted a rigid or unshifted variant, A would localize against a bundle built
from its own sweeps while B did not, the two cells' ladder branches would differ
(absolute vs relative) as the visible symptom, and C4 would have had to escalate.

**What that costs, said plainly, because parity here is not neutrality.** The duel
now compares both approaches against a map **built from one of them** — the
regenerated bundle was assembled from the EXTENSION rig's own ground-truth-
registered sweeps (`pins.yaml` `town10_pcd_regen`, built by
`benchmarks/scripts/build_pcd_from_gt.py` from a cell-A-style drive), including at
the pose G1 measures. Cell B's LiDAR is a different sensor spec (16 channels /
288000 pts/s / 100 m range against A's 128 / 600000 / 120 m) mounted through a
different transform chain, so it is matching scans against a cloud produced by
neither its own rig nor an independent survey. That is a shared, single reference
rather than a level one, and it is a reason the duel's M5 localization terms are
comparable **to each other** and still not readable as absolute accuracy for
either cell. Task 22's confound table must carry this sentence, not merely the
"same bundle" conclusion. No margin or threshold changes: this fixes what must be
checked, not what counts as equivalent.

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

### Sensing graph: `carla_sensor_kit` (E family) vs. `awsim_labs_sensor_kit` (A/B/C/D)

The spec's harmonization target was `sensor_model:=awsim_labs_sensor_kit` for
every cell, with a pre-committed fallback: "E keeps `carla_sensor_kit`; the
different sensing graph becomes a controlled confound row and M1 is anchored at
a topic common to both graphs". **Task 10 took that fallback**, and this is the
row it owes. The two graphs between the as-emitted cloud and
`/sensing/lidar/concatenated/pointcloud` are not the same length:

| Cells      | Kit                     | Chain from the as-emitted cloud to `concatenated/pointcloud`                                                                                                                                                                                   |
| ---------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A, B, C, D | `awsim_labs_sensor_kit` | the kit's own `common_awsim_labs_sensor_launch` container (crop-box self/mirror, distortion correction, ring outlier filter, concatenate-and-time-sync)                                                                                        |
| E, E-opt   | `carla_sensor_kit`      | `crop_box_filter_self` → `crop_box_filter_mirror` → a `topic_tools` relay — three composable nodes, no distortion corrector, no ring-outlier filter, no time synchronizer (`carla_sensor_kit_launch/launch/pointcloud_preprocessor.launch.py`) |

**This is a genuine confound, not a defect to fix.** Two consequences:

- **The topic NAME is now common; the graph is not.** 0002 moves the bridge's
  `topic_suffix` to `/pointcloud_raw_ex` and moves `crop_box_filter_self`'s
  input with it, so `one_hop_wall_ms` and `achieved_rate_ratio` are computed on
  the same-named topic in every cell — an as-emitted-cloud-to-observer hop in
  both, which is what makes those two comparable. `lidar_to_ndt_sim_ms` is NOT
  on that footing: it spans the preprocessing chain, and E's is shorter by two
  filter stages and a synchronizer. A smaller E number there is partly a
  shorter graph, not only a faster one.
- **`/sensing/lidar/top/pointcloud` does not exist in E's graph at all.** The
  `carla_sensor_kit` chain publishes `self_cropped/pointcloud`,
  `mirror_cropped/pointcloud` and then relays to
  `/sensing/lidar/concatenated/pointcloud`. The P1 finding's "0.00 Hz
  `/sensing/lidar/top/pointcloud`" reading was therefore two facts at once (the
  `is_dense` rejection AND a topic with no publisher in this kit); the live
  downstream check for cell E is the chain above, not that name.

Residual, recorded rather than patched: with cameras out of the kit, the bridge
launch tree still starts seven `image_transport republish` nodes and two
`topic_tools relay` nodes with no input. 0002 disables only
`multi_camera_combiner`, which is the node the spec names. The idle nodes'
process cost is inside E's `autoware` container M3 series.

### Ground truth is the CARLA actor origin; localization is `base_link`

`benchmarks/scripts/collect_gt.py` records `ego_actor.get_transform()`, whose
origin is the CARLA vehicle's own pivot at the **car centre**. Every Autoware
pose the harness compares it against — `/localization/kinematic_state`, the NDT
pose — is **`base_link`, at the rear axle**. The two differ by a constant
longitudinal offset, so **every** M5 `pose_error` computed from `gt.csv` carries
it, in every cell that uses `collect_gt`, not only the E family.

**Measured, on cell E's static arm (`results/E/run-006`, 1179 paired samples,
ego stationary):** signed dx **−1.4045 m** (sd 0.0049), signed dy **+0.0731 m**
(sd 0.0004). The dx term matches the conversion the bridge itself applies in the
opposite direction when it spawns sensors —
`CoordinateTransformer.carla_base_link_to_vehicle_center_location` subtracts
`DEFAULT_WHEELBASE / 2 = 1.425 m`, and
`carla_sensor_kit_description/config/sensor_kit_calibration.yaml`'s header
declares the same 1.425 m conversion — to within **0.021 m**, the residual being
the `vehicle.toyota.prius` pivot's actual placement versus mid-wheelbase.

**This is a confound to correct or to subtract, not a localization error.** The
localization in that run is unbiased in x once the convention is accounted for.
Two remedies were available: offset `gt.csv` to `base_link` before computing
`pose_error`, or state this offset beside every `pose_error` number. What neither
may do is read ~1.4 m of constant offset as approach-dependent accuracy, which is
exactly what the raw comparison invites.

**RESOLVED 2026-07-30 (Task 13), before any P3 run — see the amendment below.**
Originally assigned to Task 16; it landed in **Task 13** because it stopped being
a reporting caveat and became a blocker on half the primary duel (cell B's
closed-loop gate cannot pass without it). Landing it earlier than a registered
deadline is not a pre-registration violation — that deadline bounds the LATEST
legitimate edit — but it amends a metric definition (`pose_error`'s GT anchor),
so it carries its reason here and landed in a dedicated commit. **Task 16 no
longer owes this.**

#### Amendment: the GT anchor is per-approach, not campaign-wide (2026-07-30)

**The finding that forced the redesign, in three parts. The record is the
deliverable, because the obvious fix is wrong.**

1. **There is no missing shared transform.** Each approach _defines_ where
   `base_link` sits, by where it attaches its sensors: Autoware's TF chain
   carries no vehicle term, so NDT back-solves
   `base_link = sensor_world − TF(base_link→sensor)` and lands on whatever
   reference the rig was hung off. The harness's actor-origin ground truth is
   therefore a correct `base_link` GT **exactly when the approach pins
   `base_link` to the actor origin**. A uniform ~1.4 m correction would have
   **broken the approach that is already correct** — measured, not argued:
   applying the tier4 anchor to cell A's own retained G1 series turns `max_err`
   from 0.089 m into **1.415 m**.
2. **Cell B is reproducing the extension's own issue #6, inside the fork.** The
   extension once applied a `+wheelbase/2` shift that Autoware's TF did not know
   about; it biased NDT's `base_link` and cost a **1.44 m G1 near-miss**,
   root-caused in `docs/e2e-report.md` (issue #6) and fixed by _deleting_
   `base_link_to_vehicle_center`, `SAMPLE_VEHICLE_WHEELBASE` and
   `ego_wheelbase()`. The tier4 demo does the same thing today
   (`autoware_demo.py:405-416`). **This is a hard-fork maintenance finding**: a
   defect fixed in one tree persists in the other, and nothing links them.
3. **The direction is counterintuitive — do not "fix" cell A.** **Cell B follows
   Autoware's real URDF convention** (`base_link` at the rear-axle ground
   projection). **Cell A deliberately deviates**, pinning `base_link` to the
   CARLA vehicle origin — `runner/kit.py`'s docstring says so outright. Cell A's
   ground truth is correct _because of_ that deviation, and the extension's
   removal of the shift is what made it true. A later reader who "restores"
   Autoware's convention in the extension reintroduces issue #6.

**What landed.** `benchmarks/analysis/gt_anchor.py` registers a per-approach
body-frame longitudinal offset from the CARLA actor origin to that approach's
`base_link`, and applies it — rotated by ego yaw — at the two sites that consume
it: `benchmarks/scripts/collect_gt.py`'s `map_pose` (so `pose_error` is anchored)
and `cells/tier4_autoware.sh`'s localization seed (so `pose_initializer` receives
a `base_link` pose). One registry, both operands, both sites, so they cannot
drift apart.

| approach        | offset            | source of truth                                                            | `sample_vehicle` 2.79/2 |
| --------------- | ----------------- | -------------------------------------------------------------------------- | ----------------------- |
| `extension`     | **0.0**           | no vehicle-frame shift at all (`runner/kit.py`, `runner/spawn.py`)         | n/a                     |
| `tier4-native`  | **−1.39706787 m** | hardcoded literal, "as measured in Unreal Editor" (`autoware_demo.py:410`) | 1.395 — **≠**           |
| `python-bridge` | **−1.425 m**      | bridge `DEFAULT_WHEELBASE`/2 = 2.850/2                                     | 1.395 — **≠**           |
| `calibration`   | 0.0               | no Autoware stack, no `pose_error`                                         | n/a                     |

**Not derived from the vehicle model, deliberately.** An earlier plan computed
the offset from the wheelbase. That is wrong for _both_ non-zero approaches, as
the last column shows. The bridge's `−1.425` stays at the bridge's own 2.850,
because **−1.425 is where the bridge actually puts `base_link`, which is what NDT
solves for**; the 0.03 m disagreement against 2.79 remains the registered
E-family confound recorded above — a real sensor-placement inconsistency, not an
arithmetic error to round away.

**Rotated, not subtracted.** The offset is constant in the _body_ frame, so in the
map frame it rotates with yaw. "State the offset beside every number" is dead on a
technical ground rather than a preference: a map-frame constant is correct at
exactly one heading, and the committed Town10 route turns **169.4°**, over which
the correction swings from −1.397 m to +1.373 m — **2.77 m** of error for a stated
constant, against a 1.0 m goal gate.

**Drift cannot reintroduce the bias silently.** A hardcoded copy of the fork's
literal would be the same defect class as the one this fixes, so each launcher
re-reads the approach's own source at bring-up and aborts on mismatch:
`cells/tier4_autoware.sh` parses `pivot_to_base_link_transform` out of the demo and
compares it against the registry; `cells/extension.sh` asserts the three issue-#6
symbols are still absent from `runner/`; and `cells/python-bridge.sh` reads
`DEFAULT_WHEELBASE` out of the bridge's own `sensor_kit_loader.py` **inside the
image** and compares it (added 2026-07-30 by fix round 1 — this guard was
initially wired for two of the three families while this paragraph claimed all
three, and the claim was the part that was wrong). All three are verified to pass
against their live sources. If patch 0003 ever parameterizes that spawn offset, or
the fork's or the bridge's value changes, the run **fails loudly** instead of being
measured on a stale value.

**The promoted cell-A evidence survives, and it is checked rather than asserted.**
Cell A's offset is 0.0, so the transform short-circuits to an exact identity —
verified over all 399 retained G1 GT samples (byte-identical output, identical
float objects) — and both gates were re-derived through the amended path:

| gate                                     | re-derived through the amendment   | promoted    |
| ---------------------------------------- | ---------------------------------- | ----------- |
| G1 (`evidence/g1-rung2-regen/`)          | `max_err=0.089 m -> PASS`          | **0.089 m** |
| G2 (`evidence/g2-regen-repicked-route/`) | `closest_approach=0.244 m -> PASS` | **0.244 m** |

**Rejected: patching the demo to remove its shift.** It would have needed owner
sign-off as a third named patch exception, but the stronger objection is on the
merits: it **patches the approach that follows Autoware's convention so it matches
the one that deviates**. That would make the harness's GT assumption — rather than
Autoware's URDF convention — the campaign's definition of correct, and it would
delete a real interop difference. Recorded so the rejection keeps its reason.

**Closed-loop geometry metrics: bounded, and no recomputation needed.** With the
anchor applied, each cell's `gt.csv` reports _that approach's own_ `base_link` —
the point its controller is driving — so lateral deviation and
`goal_closest_approach` measure each approach's own tracking error, which is the
like-for-like comparison. What remains is that the two put _different body points_
on the centreline (A's vehicle origin, B's rear axle, 1.397 m apart), so through
curvature they trace slightly different curves. That is bounded by
`sqrt(R² + d²) − R ≈ d²/2R`; the committed Town10 route's tightest discrete radius
is **41.38 m**, giving **0.0236 m** — 2.4% of the 1.0 m goal tolerance and 4.7% of
the 0.5 m absolute pose gate. The along-track term shifts the scoring station band
by 1.397 m out of 218.9 m (0.64%). Note also that **no duel margin reads a geometry
metric at all**: `benchmarks/config/margins.yaml` registers only
`one_hop_wall_ms`, `lidar_to_ndt_sim_ms`, `control_staleness_ms`,
`carla_process_cpu_pct` and `achieved_rate_ratio`, so these two are M5 _gate
thresholds_, not equivalence comparisons. At 2.4 cm the difference is immaterial
to both, so the A-vs-B duel does **not** need them recomputed at a common
reference point.

A smaller, independent defect rides along in the E family only: the bridge's
`DEFAULT_WHEELBASE = 2.850` disagrees with `sample_vehicle`'s
`wheel_base: 2.79`, so the bridge places every E-family sensor **0.03 m**
further forward than Autoware's TF chain believes it is. Recorded rather than
patched — it is inside the harmonization the E family is measured under, and
correcting it is a sensor-config change that would have to be re-gated.

### Physics substepping (Task 13): B disables it at 20 Hz, A leaves CARLA's default on

**Added 2026-07-30 (Task 13), before any P3 run.** `benchmarks/config/physics.yaml`
exists so that both approaches apply the same `max_substep_delta_time` /
`max_substeps`. Sourcing those two values from the tier4 demo showed that
agreeing on them does **not** by itself make the substepping equal:

- The tier4 demo applies the pair only on its non-"pure step execution"
  branch, and then computes `substepping = fixed_delta_seconds <=
max_substep_delta_time * max_substeps` — CARLA's own condition. At the
  harmonized 20 Hz tick (`fixed_delta` 0.05) that is `0.05 <= 0.01` →
  **false**, so cell B runs with physics substepping OFF whether or not
  `--substepping` is passed (without it the other branch disables it
  outright). Line-numbered in `physics.yaml`.
- `cells/extension.sh` passes no `--substep-config`, so cell A runs with
  CARLA's own `WorldSettings` substepping defaults, i.e. **ON**. Passing this
  file to `runner/__main__.py --substep-config` would not close the gap
  either: `runner/loop.py::apply_substep_config` sets only these two keys and
  leaves `substepping` untouched, so A would keep substepping enabled with a
  0.01 s budget below its own 0.05 s tick.

**This is a genuine confound, not a defect to fix here.** Closing it needs a
`substepping` switch on the extension runner (Task 12/26's surface), and
Task 13 registered the two values rather than changing either runner's
behaviour. Its direction is stated but its magnitude is unmeasured: a
substepped vehicle-dynamics integration and a single-step one are not the same
physics, so an A-vs-B difference in M5's `lateral_deviation_m` or
`goal_closest_approach_m` — the terms that depend on how the ego actually
tracks a trajectory — carries this alongside the integration difference.
Nothing in the campaign isolates it. Task 22's confound table must state it
beside the B-family M5 numbers.

### CAL-seam (Task 14): a per-publish allocation the fork side alone carries

> **MOOT AS A CONFOUND — the cell is struck and there are no CAL-seam numbers (2026-07-30).** The
> owner's core-duel scope cut dropped cell CAL-seam (`cells.yaml` `dropped:`; the 2026-07-30
> amendment below), so **C1(a) seam overhead is UNMEASURED**: the paired seam-vs-in-core delta this
> entry qualifies was, in `scripts/cal_report.py`'s own words, "the only measurement the
> seam-overhead claim rests on", and it will not be taken. Two consequences for the text below.
> First, its closing instruction — "Task 22's confound table must state this alongside the CAL-seam
> numbers" — **is withdrawn**: there are no CAL-seam numbers to state it alongside. What Task 22
> owes instead is the plain statement that C1(a) has **no evidence**, not weak evidence.
> Second, the asymmetry itself is **still a true fact about the committed code** on both sides, so
> the entry is kept in full rather than deleted: it is the analysis a revived CAL-seam would need on
> day one, and it also records that the extension side's preallocated `msg_` is not merely a style
> choice. An owner **time-budget** decision, not a defect and not an infeasibility — this confound
> was never a reason the cell could not run.

CAL-seam pairs the same synthetic `sensor_msgs/PointCloud2` message published two ways on one
CARLA fork process — through the extension's C-ABI seam (`/bench/seam_cloud`) and by an in-core
publisher (`/bench/incore_cloud`, spec in `benchmarks/patches/extension/README.md`) — so that the
paired one-hop wall-latency delta between the two topics is attributable to the seam alone. Both
publishers were built to be symmetric on every field that spec controls (topic shape, env gate,
message shape, decimation clock, QoS, `frame_id`, and preallocation of the zero payload buffer).

One asymmetry is outside that spec's control: the fork's shared
`CarlaPointCloudPublisher::WritePointCloud` (`CarlaPointCloudPublisher.cpp:118`,
`~/src/carla-autoware-integration`) rebuilds `message->fields = BuildPointFields(...)` — a fresh
`std::vector<msg::PointField>` of the 10-field table — on **every** publish, for every subclass,
including the new `CarlaBenchIncoreCloudPublisher`. This is pre-existing base-class behaviour
(also present today in `CarlaLidarPublisher` and every other `CarlaPointCloudPublisher`
subclass), not something introduced by or fixable from Task 14's spec. The extension side has no
equivalent: `BenchCloudPublisher`'s `msg_.fields` is built once, in `MakeCloudTemplate()`
(`extension/src/publishers/BenchCloudPublisher.cpp:65-76`), and `OnTick()` never touches it again.

**This is a genuine confound, not a defect to fix.** It burdens the fork (in-core) side only, in
the direction that makes the in-core publisher look relatively _more_ expensive per publish than
the extension seam — the opposite direction from what "seam overhead" would predict. CAL-seam's
measured one-hop latency delta therefore bounds the seam's cost **plus** this base-class
per-publish allocation asymmetry, not the seam's cost alone: a small measured delta (or one with
an unexpected sign) cannot be attributed to the seam without accounting for it, and a report that
attributes the whole delta to the seam would be biased in the seam's favour. Task 22's confound
table must state this alongside the CAL-seam numbers, not merely note the difference.

### DDS middleware and transport (Task 9): the B family runs a different one

Every other cell family gets the harness's default middleware. The
tier4-native family (B, B-hf, B45, D) cannot, so its cells are the only
ones that change the middleware **inside the DUT** as well as inside the
instrument. Three distinct configurations now exist across the campaign:

| Cells           | Autoware's own middleware / transport                             | Observer                              |
| --------------- | ----------------------------------------------------------------- | ------------------------------------- |
| A, C            | `rmw_cyclonedds_cpp`, `docker/cyclonedds.xml` (`lo` only)         | `rmw_cyclonedds_cpp`, same profile    |
| E, E0, E-opt    | `rmw_fastrtps_cpp`, image default (**SHM on**)                    | `rmw_cyclonedds_cpp`, default profile |
| B, B-hf, B45, D | `rmw_fastrtps_cpp` + `observer/config/udp_only.xml` (**SHM off**) | `rmw_fastrtps_cpp`, same profile      |

This is forced, not chosen. The tier4 fork's publishers announce
**SHM-only user-data locators** and cannot be reconfigured from their own
side: `create_participant` selects an XML-derived QoS by pointer identity
with `PARTICIPANT_QOS_DEFAULT`, and every fork endpoint copies that object
before mutating it, so `FASTRTPS_DEFAULT_PROFILES_FILE` and
`FASTDDS_BUILTIN_TRANSPORTS` are both inert for it. Fast-DDS 2.11.2's SHM
segments are unreadable by ROS 2 Humble's 2.6.11, so with shared memory
left on the B family delivers **neither** sensing out of the fork nor
control into it, while every endpoint still matches and every log still
looks healthy. Evidence for both directions:
`benchmarks/patches/tier4-native/README.md`, "ROS 2 wire visibility".

**This is a genuine confound, not a defect to fix**, and it is broader
than the `observer_env` row it shows up in:

- **What `CAL-rmw` bounds.** `CAL-rmw` is `bench_pub` -> `bench_observer`,
  both inside the one observer image, with **no simulator and no
  Autoware** (`cells/calibration.sh:7-12`). It measures how much of an
  observed one-hop M1/M2 number is attributable to the recording
  transport, and it bounds exactly that: the **instrument** difference
  between a Cyclone-on-`lo` observer and a Fast-DDS-UDP observer.
- **What `CAL-rmw` does not bound.** It contains no Autoware, so it says
  nothing about the DUT-side difference. In the B family Autoware's own
  intra-stack topics travel over Fast-DDS/UDP-loopback instead of
  CycloneDDS-on-`lo` (A/C) or Fast-DDS/SHM (E family). That difference
  sits **inside** the measured system for **M3** (a UDP-loopback path
  forgoes shared-memory zero-copy for the large PointCloud2 traffic that
  never leaves the stack), for the intra-stack portion of **M2**, and
  potentially for **M5** through control-loop timing. No calibration cell
  isolates it; its sign and magnitude are unmeasured.
- **Why it bites the headline duel specifically.** The duel is cell A
  (extension) against cell B (tier4-native) on Town10 -- precisely the two
  rows above with different DUT middleware. A cross-arm M3 or M2
  difference is therefore a difference in integration **and** in
  Autoware's own transport, and cannot be attributed to the integration
  alone.

Task 22's confound table must state this alongside the B-family numbers
and must not present `CAL-rmw` as bounding it. Quantifying the DUT-side
part would need a calibration cell that runs the same Autoware stack twice
under two middlewares, which the campaign does not have.

### Localization initialization (Task 13): the stop check blocks every path on cell B

**Added 2026-07-30 (Task 13), before any P3 run.** As first measured this was a
FAIL and not a caveat: cell B did not close the loop, on four filed runs. The
cause is below, the per-approach measurement it produced is below and stays, and
the campaign-wide amendment that removes the block — plus the re-gate outcome —
is in "Amendment: `stop_check_enabled: false` for every cell" at the end of this
section. Evidence for the FAIL, with retention stated per figure:
`benchmarks/evidence/b-closed-loop-stopcheck/`.

`autoware_pose_initializer` refuses **every** initialization request with
`'The vehicle is not stopped.'` — through the AD-API
(`/api/localization/initialize`, which its own automatic initializer calls every
1–3 s), through `/initialpose`, and through its own
`/localization/initialize` service. Its stop check reads
`/sensing/vehicle_velocity_converter/twist_with_covariance`, and on cell B that
twist carries **2.17 mm/s of LATERAL velocity** on 180/180 measured samples
while `linear.x` is 1.5e-12 m/s: the ego is stationary along its own axis and
the checker compares the squared norm of the whole linear vector. The lateral
term is the fork's — `/vehicle/status/velocity_status` reports
`lateral_velocity` ≈ 2.3 mm/s for a parked ego, and
`autoware_vehicle_velocity_converter` forwards it into `twist.linear.y`. So NDT
never initializes, `/localization/kinematic_state` never publishes, and the run
fails in the launcher before `run.sh` reaches its arm step.

**Three things this changes, and they are not all about cell B:**

- **The M5 gate has no B-family input.** No `quality.json` exists for any B run,
  so cell B has no NDT rate, no `pose_error_m` and no `goal_closest_approach_m`.
  The ladder and rate bindings registered for B/B-hf/B45 in `cells.yaml` are
  registrations of what a run _would_ be scored against, not results.
- **The campaign has no working localization-seed step for ANY cell.** Both
  approaches publish only `/sensing/gnss/pose{,_with_covariance}` and
  `/vehicle/status/*`; neither self-initializes. `run.sh`'s shared arm step
  cannot seed (`injector/arm_and_goal.py` runs inside the container with no
  simulator client, by design), so each cell's LAUNCHER owes it, and
  `scripts/e2e/run_e2e.sh` does not have one. `scripts/e2e/reseed_localization.py`
  — the extension harness's proven re-seed — publishes `/initialpose`, which on
  this image's `pose_initializer` is **not a subscribed topic at all**. Task 13
  wrote `benchmarks/injector/seed_localization.py` (the direct-service path) for
  every cell to share; Task 20 must not assume the `/initialpose` route works.
- **The defect is B-SPECIFIC, and that is MEASURED on both sides of the duel.**
  The mechanism is not fork-specific — the extension publishes
  `lateral_velocity` too (`extension/src/publishers/StatusPublishers.cpp:99`) —
  but the VALUE differs, and the value is what decides. Recorded as a
  per-approach observation, the same treatment the `control_mode` gap above gets:

  | cell | parked-ego `VelocityReport` (longitudinal, lateral, heading_rate) | over the 1e-3 m/s stop threshold |
  | ---- | ----------------------------------------------------------------- | -------------------------------- |
  | A    | 0.0, 0.0, 0.0 — exactly zero                                      | **0 / 400 samples**              |
  | B    | ~1.5e-12, 2.17–2.41e-3, ~1.9e-4                                   | **180 / 180 samples**            |

  Cell A's reading is from a live cell-A rig on 2026-07-30
  (`scripts/e2e/run_e2e.sh` with `WITH_AUTOWARE` unset: CARLA fork + extension
  `.so` + runner at the committed route's spawn pose, probed over cell A's
  registered CycloneDDS consumer transport, 400 samples in 20 s). Cell B's is
  `benchmarks/evidence/b-closed-loop-stopcheck/`. **Cell A's figure is NOT
  retained as a tracked artifact** — the probe was interactive, the same status
  step 11.6's readings have — so it is recomputable only by repeating that boot,
  and is labelled accordingly. Cells C, D and the E family are unmeasured; the E
  family localizes today, so its check evidently passes, which is an inference
  from behaviour and not a reading.

  So the stop check is doing its job on cell A and producing a **false positive**
  on cell B: A's parked ego is bit-exactly stopped, B's is reported drifting
  sideways at 2 mm/s while its longitudinal velocity is 1e-12 m/s. That is also
  the direct explanation for why cell A initialized and drove in Task 11 (G1
  0.089 m, G2 0.244 m) while cell B cannot initialize at all.

**Escalated rather than worked around, then AMENDED.** The three available
remedies all cross a line this campaign drew: patching the fork's velocity
report (or the extension's) changes a DUT and erases the interop difference,
exactly as the `control_mode` section argues; overriding `pose_initializer`'s
`stop_check_enabled`/`stop_check_duration` means bind-mounting a modified
Autoware param file; and accepting the FAIL costs the duel its B half. Task 13
reported the choice to the plan owner instead of taking it. **The owner chose
the param override, scoped campaign-wide**, and it is disclosed below.

#### Amendment: `stop_check_enabled: false` for every cell (2026-07-30)

**Pre-registration status: amended 2026-07-30 (Task 13), still before any P3
run.** Recorded here with its reason, in the same disclosure section and the
same spirit as the campaign-wide `perception:=false` above — a configuration of
the shared measurement environment, decided and written down before any number
it could affect exists.

1. **What.** `stop_check_enabled: false` for `autoware_pose_initializer`,
   applied uniformly to **every** cell.
   `benchmarks/config/autoware/pose_initializer.param.yaml` is a verbatim copy
   of the pinned image's own
   `/opt/autoware/share/autoware_launch/config/localization/pose_initializer.param.yaml`
   (sha256 `a7ed49a2fabad3e46d023969f16b63d3d1ab3d66a555d88f5914f3ef48baeee2`,
   read from `ghcr.io/autowarefoundation/autoware@sha256:5c22369a312f…`, i.e.
   `pins.yaml`'s `autoware_universe_devel.digest`) with **exactly one line
   changed**: `stop_check_enabled`, from that file's launch substitution to a
   literal `false`. It is bind-mounted read-only over that same path
   **identically in all three cell families** — `docker/compose.yaml`
   (A/A-hf/C), `benchmarks/cells/tier4_autoware.sh` (B/B-hf/B45/D) and
   `benchmarks/cells/python-bridge.sh` (E/E0/E-opt). Identical in all three IS
   the justification, not a convenience: a mount present for B but absent for A
   would make it an approach-side change to one half of the primary duel. The
   source file was verified **byte-identical, same sha256**, in all four
   locally present images a mounting family runs (`universe-devel-cuda`,
   `universe-devel`, `bridge-bench:latest`, `bridge-bench-patched:latest`), so
   it is a one-line change in each and not a cross-version file swap. **Cell
   B45's pinned `universe-devel-0.45.1` is NOT verified** — that image is not on
   this workstation. That comparison was Task 21's, and it is now **moot rather
   than owed**: cell B45 was struck by the owner's core-duel scope cut
   (2026-07-30, see the amendment below), so this mount never reaches that
   image. The gap is recorded, not closed — it is a **logistics** gap (the image
   is absent from this box) and never a finding about the 0.45 image or about
   carrying the tier4 fork across releases.
2. **Why it is not "relaxing a safety check": Autoware itself ships this value
   for simulation.** `tier4_simulator_launch/launch/simulator.launch.xml:193`
   and `:211` both pass `stop_check_enabled` with value `false`, and
   `tier4_localization_launch/launch/pose_twist_estimator/pose_twist_estimator.launch.xml:5-6`
   derives it `true` for `system_run_mode == 'online'` and **`false` for
   `'logging_simulation'`**, under Autoware's own comment on the line above
   them: _"only when running with a real vehicle, the pose_initializer judges
   the stop"_. The `e2e_simulator` path this campaign uses simply defaults
   `system_run_mode` to `online`
   (`autoware_launch/launch/autoware.launch.xml:37`) and never forwards an
   override, so it lands on the real-vehicle branch by default. This applies
   upstream's own simulator configuration; it does not invent a relaxation.
3. **Why not `system_run_mode:=logging_simulation` instead.**
   `e2e_simulator.launch.xml` does not forward that argument, so it is
   unreachable from the launch command line; and it has a **second** consumer —
   `autoware_launch/launch/components/tier4_system_component.launch.xml:10`
   passes it on as `run_mode` — so flipping it would change a second thing
   inside the measured system. The threshold itself is not a parameter at all:
   the comparison is against a `constexpr` inside
   `autoware::motion_utils::VehicleStopCheckerBase`, and `stop_check_duration`
   cannot help because the value is persistently over threshold, not
   transiently.
4. **Why it changes no measured quantity.** The stop check gates only
   `pose_initializer::on_initialize` — an initialization **precondition**, not
   an acceptance threshold. No registered metric reads it (`metrics.md`/
   `cells.yaml` register none; `write_quality` scores NDT rate, pose error and
   goal approach). And it already **passes** where it is exercised: cell A
   measures 0.0 m/s on all three `VelocityReport` components, 0/400 samples over
   the 1e-3 m/s threshold (the table above), and the E family localizes today.
   So the override removes a **false positive on cell B** and changes nothing
   observable elsewhere.
5. **The finding is preserved, not laundered.** The per-approach table above —
   cell A's exact 0.0 against cell B's 2.17–2.41 mm/s parked lateral velocity —
   **stays, and still reads as a real difference between the two approaches**,
   the same treatment the `control_mode` gap below gets. The override is the
   **harness working around** that difference so the duel has a B half; it is
   not a claim that the difference does not exist, and Task 22's confound table
   must carry both.

**What it does NOT change.** No DUT is patched: the tier4 fork's
`VelocityReport` still reports its lateral term, the extension still reports
zero, and neither approach's data-path, conversion or transport code is
touched. No new file appears under `benchmarks/patches/`, so no approach's patch
set grows and the patch policy's two named exceptions are unaffected.

### MRM suppression: the perception-off false MRM, cleared uniformly (Task 13)

**Amended 2026-07-30 (Task 13), before any P3 run.** Campaign-wide disclosure,
same class and same uniformity argument as the `stop_check_enabled` amendment
above.

**What.** `benchmarks/injector/arm_and_goal.py` sets `use_emergency_handling=false`
on `/control/vehicle_cmd_gate` before attempting to engage. `run.sh` step 9 runs
that script for **every** cell, so the setting is uniform by construction and
cannot drift between families. No approach is patched, and nothing under
`benchmarks/patches/` changes.

**Why it is not a new relaxation — the decisive reason.** **Every promoted gate
number in this repo was already produced with MRM off.** `CLAUDE.md` documents
the extension arming sequence as "reseed → dummy perception → route → **MRM
off**", and `scripts/e2e/arm_closed_loop.sh` step 5 (`SUPPRESS_MRM=1` by default)
sets exactly this parameter, calling it _"still required … without this the gate
MRM-overrides the drive command"_. Cell A's G1 0.089 m and G2 0.244 m came from
that path. Doing it in the shared arm makes every bench cell's arm **identical to
the configuration the promoted A-side evidence came from**; _not_ doing it would
put an asymmetry inside the shared measurement environment, between the two arms
of the primary duel.

**Second reason: it is a false positive of an already-registered setting.** The
MRM fires because `perception:=false`, which this document already registers and
discloses campaign-wide with the clear-road injector standing in. Clearing it
removes a consequence of a pre-registered choice rather than making an
independent one.

**Measured, so the effect is not asserted** (`results/B/run-008`, excluded
`gate:arm-failed`, before this amendment):

| evidence                                                                                 | count            |
| ---------------------------------------------------------------------------------------- | ---------------- |
| `mrm_handler: MRM State changed: NORMAL -> MRM_OPERATING`; `EMERGENCY_STOP is operated.` | 1 each           |
| `no mrm operation available: operate emergency_stop`                                     | 231              |
| `/autoware/modes/autonomous ERROR`                                                       | 35               |
| `change_to_autonomous: 'The target mode is not available'`                               | 3                |
| `/autoware/planning/topic_rate_check/trajectory ERROR`                                   | 34 of 35 samples |

**Rejected, and recorded with its reason rather than merely unchosen:** supplying
the `operation_mode_availability` / diagnostics input that perception would have
supplied, so the system genuinely believes it is safe instead of being told to
ignore emergencies. That is the **more faithful design**. It loses here only
because adopting it now would diverge from the configuration that produced
promoted cell-A evidence, and keeping both duel arms identical would then require
re-gating cell A — re-deriving promoted evidence, which is exactly what the GT
anchor's no-op requirement exists to prevent. **If the campaign ever re-gates
cell A for an independent reason, reconsider it then.**

**Recorded per run, not inferred.** `run.sh` step 9 now tees the arm to
`<run>/arm.log`, so each run retains the MRM configuration it used alongside the
AD-API outcome and the post-engage mode/control flags. Before this, none of that
was retained anywhere — `run-008`'s evidence had to be read out of a console
scrollback.

### `base_link` anchoring: a per-approach interop difference, normalized in the harness not patched (Task 13)

**Added 2026-07-30 (Task 13), before any P3 run.** Same treatment as the
`control_mode` gap below and the parked lateral velocity above: the harness
normalizes so the metric compares like with like, the **difference itself is
recorded**, and no approach is patched.

| cell               | where the approach puts `base_link`                                                               | offset from the CARLA actor origin | follows Autoware's URDF convention?                        |
| ------------------ | ------------------------------------------------------------------------------------------------- | ---------------------------------- | ---------------------------------------------------------- |
| A / A-hf / C       | the **CARLA vehicle origin** — sensors attach at raw `base_link` coordinates with no vehicle term | **0.0**                            | **No — deliberate deviation** (`runner/kit.py` states it)  |
| B / B-hf / B45 / D | the **rear-axle ground projection** — an explicit `base_link` actor 1.397 m behind the pivot      | **−1.39706787 m**                  | **Yes**                                                    |
| E / E0 / E-opt     | vehicle centre minus `DEFAULT_WHEELBASE`/2                                                        | **−1.425 m**                       | Yes, at a wheelbase that disagrees with `sample_vehicle`'s |

**Why this is a finding and not a harness detail.** Where an integration anchors
the ego pose it publishes is part of the interop completeness this campaign
exists to compare, and the three approaches disagree. The **counterintuitive**
part is the direction: the approach the harness's raw ground truth happened to
suit (A) is the one that deviates from Autoware's convention, and the approach
that looked broken (B) is the one that follows it. Normalizing without recording
that would have converted a real difference into a harness detail — and worse,
would have invited a later "fix" to the wrong side. The full reasoning, the
drift guards, and the measured proof that the normalization is a strict no-op for
cell A are in the amendment under "Ground truth is the CARLA actor origin"
above.

### Host load during a run is unbounded, and it changes outcomes (Task 13)

**Added 2026-07-30 (Task 13), before any P3 run. Session discipline every P3 run
inherits — read this before starting one.**

`benchmarks/scripts/preflight.sh` gates the 1-min loadavg at **8**
(`exclusions.md` criterion 6) **only BEFORE a run starts**. Nothing bounds it
during the run, and the run's own stack plus anything else on the box drives it
far past that gate.

**Measured, same cell, same commit, same day, two runs:**

| run                 | loadavg at preflight | during bring-up   | outcome                                                                                                                                                                                                                                                                    |
| ------------------- | -------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `results/B/run-005` | 4.21                 | **64** (24 cores) | **three rclcpp/rmw service responses lost in one 0.4 s window** — `mrm_emergency_stop_operator/…/load_node`, `pointcloud_container/…/load_node`, and `/localization/pose_estimator/trigger_node`. The last wedged `pose_initializer` in `futex_do_wait` for the whole run. |
| `results/B/run-006` | 2.64                 | ~15               | no dropped responses; `pose_initializer` served normally                                                                                                                                                                                                                   |

The dropped-response class is not new: `results/E/run-003` lost four
`pointcloud_container` `load_node` responses the same way, and
`cells/python-bridge.sh` records it as load-sensitive and non-reproducing on the
next bring-up. Task 13 is the second cell to hit it and the first to tie it to a
measured loadavg.

**Two consequences, separated because they need different fixes.**

- **Comparability (M3). CLOSED 2026-07-30 for runs filed from now on.** Any
  cross-run `carla_process_cpu_pct` or `rtf` comparison assumes the runs saw
  similar host contention. As first written, nothing in the record established
  that: `resources.csv` carried no loadavg column — its contract was
  `sample_system_ns, process, cpu_pct, rss_bytes, gpu_util_pct, vram_bytes,
rtf` — and `grep -rniE 'loadavg|getloadavg|/proc/loadavg' benchmarks/sampler/`
  returned nothing, so a filed run could not answer "was this run contended?"
  after the fact. **That column now exists**: `resources.csv` gained
  `loadavg_1m` (see "`loadavg_1m` — in-run host load" in the data contract
  above), landed before Task 16 as this entry required, so it is usable by the
  P3 analysis. Two limits stay: the already-filed runs
  (`results/B/run-007…012`, all of `results/E/`) predate it and read as NaN —
  **not** as an uncontended host — so no cross-run contention comparison
  involving them is available; and the column **records** contention without
  bounding it, which is the next bullet's problem and not this one's.
- **Validity (bring-up).** A contended host does not merely make a run slow; it
  can make one **fail in a way that reads as an approach defect**. Run-005's
  wedge would look like "cell B cannot initialize localization" to anyone who did
  not grep for `client will not receive response`.
  `cells/tier4_autoware.sh`'s seed-timeout message now names that signature.

**Session discipline: one cell at a time, nothing else on the box, and do not
probe a live stack during bring-up.** Task 13's own in-container diagnostics
contributed to run-005's 64 — recorded because it is the specific mistake to
avoid, not as an excuse. **The `loadavg_1m` column does not retire this rule.**
It was originally written as "until a loadavg series exists"; that was wrong, and
the series existing changes nothing about it. Recording load is not bounding
load: nothing caps it during a run, so a contended run still fails in ways that
read as an approach defect — the column only makes the contention visible
afterwards. The rule stands for every P3 session, and it stays a
session-discipline matter rather than a harness one.

**The reflexive hazard, stated because it is easy to forget while building the
instrument.** An agent's own probing contributed to run-005's loadavg of 64, so
observer-side work sits **inside** the perturbation it measures: the sampler
that now records `loadavg_1m` is itself one of the processes contributing to it,
and so is any diagnostic run alongside a live stack. The harness's own share is
measured and small (injector + observer = 60% of 2400%, i.e. 2.5%, in the
attribution table below), which bounds the effect without eliminating it — and
that measurement is exactly why the saturation cannot be blamed on
instrumentation.

**DIRECTLY SAMPLED, and it is not only about external interference (Task 13,
`results/B/run-009`).** A 2 s-interval `/proc/loadavg` sample across a whole
cell-B run, with **nothing else running on the box**, recorded:

| statistic         | 1-min loadavg |
| ----------------- | ------------- |
| at launch         | 2.6           |
| mean over the run | **25.80**     |
| peak              | **50.05**     |

on **24 cores**, from 75 samples. So the cell's **own** stack — the CARLA UE5
editor, the demo's tick loop, ~163 Autoware nodes, the observer and the sampler —
oversubscribes this host by more than 2x unaided. This is not contention from
other work; it is the configuration the campaign measures under. (Sampled
ad hoc, because `resources.csv` had no loadavg column **at the time**; the
series itself is not retained, and re-deriving it costs one run plus a
2 s-interval sampler. It has one now — `loadavg_1m`, 2026-07-30 — so a run
filed from here on retains its own series and these two figures are the last
that will be ad hoc. The 2026-07-30 column does **not** retrofit runs 009/010:
their `resources.csv` predates it, so the peak/mean above stay
non-recomputable, which is why they are labelled here rather than promoted to
`benchmarks/evidence/`.)

**ATTRIBUTED, from the M3 sampler's own retained per-process CPU
(`results/B/run-010/resources.csv`, 78 samples). It is NOT harness overhead.**

| process           | mean CPU % | peak % | share of a 24-core (2400%) box |
| ----------------- | ---------- | ------ | ------------------------------ |
| `autoware`        | **1832.5** | 1930.3 | 76%                            |
| `carla-server`    | 280.5      | 544.3  | 12%                            |
| `injector`        | 37.7       | 44.6   | 1.6%                           |
| `observer`        | **22.7**   | 93.2   | **0.9%**                       |
| **total sampled** | **2173.5** |        | **91%**                        |

**DUT stack (Autoware + CARLA) = 2113%, i.e. 88% of the box. Harness (injector +
observer) = 60%, i.e. 2.5%.** So the saturation is **not** eliminable by session
discipline or by removing instrumentation: the **DUT stack alone saturates 24
cores at the harmonized 16-channel baseline**, the Autoware container alone
averaging ~18.3 cores — and that is with `perception:=false`.

**Consequence 1: host quiescence is violated BY THE MEASUREMENT ITSELF.** Every
rate metric this campaign takes is taken under ~90% saturation. That is a
campaign-wide disclosure, not a per-run note.

#### Registered claim (Task 13): the M4 sweep's premise may be false at its own baseline

**Stated at full strength as a named, falsifiable claim rather than a caveat,
because if it holds it is a headline result about running Autoware on this class of
machine — not a footnote about this harness.**

> **Claim.** The M4 sweep is premised on the harmonized **vlp16 baseline sitting
> below this host's throughput ceiling**, with the heavier classes probing upward
> from there. On this workstation that premise may be **false at the starting
> point**: the baseline configuration already consumes **91% of 24 cores**, with
> `perception:=false`.
>
> **Measured under `intel_pstate` + `powersave`** (range 0.8–5.4 GHz, idle sample
> 2.39 GHz) — the campaign's registered governor. That is a **dynamic** governor,
> **not** a pin to minimum, so this figure is not taken on frequency-crippled
> cores; falsifier 3 below turns the governor into a measured bound rather than
> an argument.

**Evidence** (all measured, all retained):

| measurement                             | value                                                 | source                                        |
| --------------------------------------- | ----------------------------------------------------- | --------------------------------------------- |
| total sampled CPU at the vlp16 baseline | **2173.5%** of 2400% (**91%**)                        | `results/B/run-010/resources.csv`, 78 samples |
| Autoware container alone                | **1832.5%** mean (~**18.3 cores**), perception OFF    | same                                          |
| in-run 1-min loadavg                    | peak **50.05** / **54.01**; mean 25.80 / 29.80        | direct 2 s sampling, runs 009 / 010           |
| downstream symptom 1                    | sensing chain **8.47 → 0.52 Hz**                      | `run-010`, in-container PublishedTime         |
| downstream symptom 2                    | **3** AD-API services timing out rather than refusing | runs 005 / 009 / 011                          |

**What would falsify it. FALSIFIERS 1 AND 2 ARE NOW ANSWERED (2026-07-30, Task
15b); falsifier 3 is still owed:**

1. **Cell A's baseline load — ANSWERED. The saturation is SPECIFIC TO CELL B, not
   environmental.** Cell A has now run through this harness:
   `results/A/run-001` (static) and `results/A/run-002` (closed-loop), both
   contract-valid, non-excluded and M5-PASS on the first attempt. Whole-run mean
   CPU, the same reduction and the same `container: autoware` process label this
   table's cell-B column uses:

   | series                    | `autoware`                     | `carla-server` | total of 2400%      |
   | ------------------------- | ------------------------------ | -------------- | ------------------- |
   | A `run-002` (closed-loop) | **208.8%** (~**2.09 cores**)   | 262.9%         | 503.4% (**21.0%**)  |
   | A `run-001` (static)      | 155.0% (~1.55 cores)           | 258.5%         | 441.9% (18.4%)      |
   | B `run-010` (this table)  | **1832.5%** (~**18.33 cores**) | 280.5%         | 2173.5% (**90.6%**) |
   | B `run-012`               | 1848.9% (~18.49 cores)         | 281.1%         | 2191.6% (91.3%)     |

   So cell A's Autoware runs at **1/8.78** of cell B's while `carla-server` is
   matched to within **6.7%** — the simulator side of both cells costs the same on
   this host, which is what makes the Autoware difference a difference between the
   cells rather than a host-wide effect or an artifact of the label. **Cell A does
   not average ~18 cores, so the first branch above is refuted:** the 91%
   saturation is not a property of _this environment_, and Task 13's load finding
   survives as a real finding **about cell B**.

   Two things sharpen it, one in each direction. Cell A carries the **heavier**
   sensing load — ~639 000 pts/s measured (below) against cell B's registered
   288 000 — so it does more sensor work for one ninth of the Autoware CPU. And
   cell B's figure was recorded on `run-010`, which is `excluded` /
   `gate:arm-failed`: **cell B consumed ~18.5 cores while never actually
   arming**, where cell A consumed ~2.1 while driving the route. "Arm-matched"
   between the two rows above therefore holds only for the manifest's `arm`
   field, and the asymmetry runs against cell B.

   **NOT yet separable from the IMAGE, and this is the live confound.** Cell A
   runs `ghcr.io/autowarefoundation/autoware:universe-devel`; cell B runs
   `pins.yaml`'s `universe-devel-**cuda**` digest. A CUDA-enabled image can spin
   CUDA-aware nodes at much higher CPU even with `perception:=false`, so
   "approach B costs 8.78×" is **not** yet distinguishable from "that image costs
   8.78×", and nothing in the campaign isolates it today. **Task 18 measures M3
   CPU with n ≥ 10 on both cells**, which is where this gets its error bars.
   Task 22's confound table must carry this sentence beside any B-side M3 number.

2. **Whether the M4 ceiling criterion actually fires — ANSWERED. IT DOES NOT
   FIRE, so THIS CLAIM IS FALSIFIED.** `analysis/ceiling.evaluate_ceiling` on both
   cell-A runs' registered inputs returns `reached=False, reasons=[]` — every one
   of the four pre-registered disjuncts silent, by wide margins:

   | `evaluate_ceiling` input | A `run-001` static        | A `run-002` closed-loop   | fires when           |
   | ------------------------ | ------------------------- | ------------------------- | -------------------- |
   | `rtf`                    | min 0.9965, median 0.9980 | min 0.9958, median 0.9982 | < 0.9 sustained 10 s |
   | `tick_rate_ratio`        | n/a (paced arm)           | n/a (paced arm)           | < 0.9 sustained 10 s |
   | `publisher_rate_ratio`   | 0.9993                    | 1.0000                    | < 0.9                |
   | `quality_ok`             | True                      | True                      | is False             |

   **Stated as falsified rather than quietly dropped:** the claim above predicted
   the baseline sits at or above this host's throughput ceiling, and on cell A it
   does not — RTF never leaves 0.996–1.003 and there is roughly **4× headroom**
   (21.0% of 24 cores). The sweep's premise is therefore comfortably **true** for
   cell A, and the 91% figure the premise was doubted on is cell B's alone.

   **The class the runs were actually at, measured rather than labelled.**
   `runner/spawn.py` pins `_TOP_LIDAR_CHANNELS = "128"` and
   `_TOP_LIDAR_POINTS_PER_SECOND = "600000"`, and `cells/extension.sh` passes no
   sweep overrides, so these runs are **not** at the registered `vlp16` class
   (16 ch / 288 000 pts/s) and not at `128ch` (4 600 000) either. Confirmed from
   the committed series, not just the constants: `run-002`'s
   `/sensing/lidar/top/pointcloud_raw_ex` median is **511 288 B/msg** at
   **20.00 Hz** → ~31 956 pts/cloud → **~639 000 pts/s**. The rig therefore
   carries **~2.2× the vlp16 point rate**, so a criterion that does not fire here
   would not fire at the lighter baseline under load monotonicity in point rate —
   an **assumption, stated as one**, which makes the falsification more robust
   than a `vlp16` run would have, not less. A strict `vlp16` confirmation remains
   unavailable: both sweep launchers refuse a `--class` whose sensor arguments are
   not spelled out, and `config/cells.yaml`'s header records that the class →
   argument mapping "was owed to Task 26, which is struck, so it has NO owner now".
   **Consequence, and it needs a DECISION rather than a new amendment:** `32ch` is
   the step-up this file and `cells.yaml` already pre-registered as an
   _anticipated_ amendment for exactly this branch. Reinstating it is the owner's
   call and is not acted on here.

3. **One paired baseline run under `powersave` vs `performance`** (registered
   2026-07-30 by owner ruling; **not yet run**). Neither falsifier above separates
   the governor confound, and `powersave` ramps more slowly than `performance` on
   bursty latency-sensitive paths — which is exactly where the AD-API spin
   timeouts sit. This pair turns the governor from an argument into a measured
   bound. It is a live measurement, so the owner schedules it.

**Not acted on here.** No sweep class, margin or analysis is changed; this registers
the claim and its evidence so the sweep is not designed on an assumption its own
baseline data contradicts. The owner schedules any change, **including falsifier 3.**

**What that does and does not explain.** `RTF` stayed **1.0000** on both runs that
recorded a clock series, so the _simulator_ keeps up and the deficits are in the
ROS layer above it. And they **vary between runs of one unchanged
configuration**: the observer failed to record 25.6% of published clouds on
`run-008` and 17.1% on `run-009`, with NDT at 2.02 Hz and 3.42 Hz respectively.
Variability of that size is itself evidence that these figures are
contention-sensitive rather than fixed properties of the approach — which is why
they must not be reported as tier4-native's rates.

### Sensing-chain rate deficits on cell B: TWO of them, separately localized (Task 13)

**Added 2026-07-30 (Task 13), before any P3 run.** Cell B fails the M5 NDT-rate
criterion and the observer LiDAR-rate criterion. **The gate FAIL stands and no
threshold is touched.** What follows is the characterization, because attributing
a harness- or host-induced deficit to the approach under test would be a false
finding about that approach — worse than no finding.

> **⚠ THE FAIL IS NOT ATTRIBUTABLE TO APPROACH B — but the reason has CHANGED
> (updated 2026-07-30, Task 15b).** Read this before quoting any number below.
>
> Everything here — the ~18.3-core Autoware container, the ~15% wire loss, the
> AD-API timeouts, the 2.02 / 3.42 / 0.52 Hz NDT figures — was measured on **one
> cell**. **The control now exists**: `benchmarks/results/A/run-001` (static) and
> `run-002` (closed-loop) are filed, contract-valid and M5-PASS.
>
> - **The "this environment" branch is REFUTED.** Cell A's Autoware averages
>   **~2.09 cores** (whole-run, `run-002`) against cell B's **~18.33**
>   (`run-010`), with `carla-server` matched to within 6.7% and cell A carrying
>   the heavier sensor rig. The host is not saturated; **cell B is.** So the
>   saturation is a real finding **about cell B**, and this host no longer
>   explains it.
> - **What remains unattributable is the IMAGE, not the environment.** Cell B
>   runs a _different image_ (`universe-devel-**cuda**`), so "approach B costs
>   8.78×" is still not separable from "that image costs 8.78×". **Task 18**
>   measures M3 CPU with n ≥ 10 on both cells, which is where that separation
>   gets its error bars.
>
> **CORRECTED while updating this box:** the "_extra_ concat-relay node" was
> never a cell-B-only difference. `scripts/e2e/launch_autoware.sh` starts one for
> the extension family too — visible as `concat relay pid …` in
> `results/A/run-001/launch.log`
> (`/sensing/lidar/top/pointcloud_before_sync -> /sensing/lidar/concatenated/pointcloud`).
> It must **not** be listed as an A-vs-B asymmetry in Task 22's confound table.
>
> "Cell B fails its closed-loop gate" is therefore a statement about **cell B as
> measured here** — now with a control that rules out the host — and still not a
> finding about the tier4-native approach, because the image is uncontrolled.
>
> Note also that cell B was made the campaign's first bench-harness closed-loop
> cell even though **cell A is the cell already proven to drive**, so harness
> defects and approach defects were conflated by construction: the LiDAR
> attach-tree walk, the GT anchor, the MRM suppression and the arm observability
> were all found via B and **apply to every cell**.

**These are TWO independent deficits, not one story.** Taking the observer's own
count as the true input, `run-009` still goes 8.53 Hz → 3.42 Hz, a further ~60%.
The wire loss does not explain the NDT figure.

**Deficit 1 — publisher → subscriber, ~15–26%, and it is LOAD, not the
transport.** `publisher_drop_rate = 0.0000` on both runs, so the source is
perfect, and Autoware's own container sees **8.47 Hz** against the bench
observer's **8.53 Hz**.

**Two DIFFERENT claims must be separated, because the same numbers do not settle
both.** Two subscribers agreeing clears the observer of **miscounting**. It does
not by itself clear the observer of **perturbing**, since the SHM-off transport
could be an observer requirement whose side effect both subscribers then suffer.
Both are now answered, on three independent lines of retained evidence:

1. **Not miscounting.** 8.47 Hz vs 8.53 Hz — 0.06 Hz apart, from unrelated
   subscribers in different containers.
2. **The transport is NOT adopted for the observer's benefit, so this is not
   observer perturbation.** Task 9's transport matrix
   (`benchmarks/patches/tier4-native/README.md`) records `fastrtps` with
   `none (SHM on)` as **`ECHO = no`, `RATE = —`** on rows 1, 3 and 8: with shared
   memory ON the fork's cloud is **not readable at all**, because it announces
   SHM-only user-data locators that Fast-DDS matches but cannot read. Rows 8/9 are
   in **Autoware's own pinned image** — row 8 (SHM on) reads nothing, row 9
   (`udp_only.xml`) reads **10.070 Hz** — so Autoware needs this transport
   independently of the observer. The control-ingress table adds that with SHM on
   the ego "never leaves rest: 0.000 m/s" and control is "not delivered". The
   transport is not a revertible choice made for the instrument; it is the only
   configuration in which this fork talks to a Fast-DDS consumer at all.
3. **Not perturbing by CPU either.** The observer's own mean CPU is **22.7%** of a
   2400% box — **0.9%** of the host (load attribution below).

**The same matrix supplies the discriminator for what the deficit IS.** Rows 2, 4
and 9 measured **10.006 / 10.071 / 10.070 Hz** on this exact
`fastrtps + udp_only.xml` transport, and that file states rows 8–11 run in "the
exact pinned `autoware_universe_devel.digest` image cell B launches Autoware
from". **Two corroborations in the same file are stronger still, and they are what
make CPU starvation the live explanation:** its acceptance check recorded the
**stock `bench_observer`, invoked exactly as `run.sh` invokes it, at 243 rows in
24 s = 10.1 Hz** on this transport, with the CARLA-API-side cadence over that same
run at **10.002 Hz**. So the instrument this campaign actually uses has already
achieved ~10.1 Hz here — and that probe ran **without** the full Autoware stack,
hence without the ~91% load. What differs is load: those rows were a
wire-visibility diagnostic on a quiet host, while these runs put the box at **91%
of 24 cores** with the Autoware container alone at **1832%**.
**Deficit 1 is therefore attributed to CPU starvation, not UDP fragmentation** —
a change from this section's first reading, made because those matrix rows refute
the fragmentation story.

**Consequence for the gate:** the FAIL is a true finding about **cell B's
configuration on a saturated host**, and not an artifact of the bench observer.
The SHM-on control run that would otherwise be the decisive test **cannot be
performed and does not need to be** — its answer is already in the record, and it
is "no data at all", not "~10 Hz".

**Deficit 2 — inside the Autoware container, and it is the larger one.** Measured
on `run-010` from inside that container over a 40.05 s window after a 20 s
discovery settle:

| stage                                             | n   | Hz       |
| ------------------------------------------------- | --- | -------- |
| `/sensing/lidar/top/pointcloud_raw_ex` (arriving) | 339 | **8.47** |
| `self_cropped/pointcloud_ex` PublishedTime        | 111 | **2.77** |
| `mirror_cropped/pointcloud_ex` PublishedTime      | 111 | 2.77     |
| `pointcloud_before_sync` PublishedTime            | 111 | 2.77     |
| `/sensing/lidar/concatenated/pointcloud`          | 196 | 4.89     |
| `measurement_range/pointcloud` PublishedTime      | 157 | 3.92     |
| `voxel_grid_downsample/pointcloud` PublishedTime  | 157 | 3.92     |
| `downsample/pointcloud` PublishedTime             | 157 | 3.92     |
| `/localization/pose_estimator/pose` (NDT out)     | 21  | **0.52** |

**Why this instrument is valid, and it is the reason the measurement means
anything:** the PublishedTime topics are **tiny** messages, one per cloud a node
publishes, so unlike the ~460 KB `PointCloud2` topics they are **not subject to
the UDP fragmentation loss that is under suspicion**. They report what each
Autoware stage actually published. They are also read from inside Autoware's own
container, so they are independent of the bench observer — which could not answer
this, being the instrument under suspicion.

The largest single drop is **NDT itself**: 3.92 Hz of input to 0.52 Hz of pose
output on that window. The first preprocessing stage is the next largest
(8.47 → 2.77 Hz).

**Candidates, and what is ruled out by measurement:**

| candidate                               | verdict                                                                                                                                                                                                                                |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| source/publisher decimation             | **RULED OUT** — 9.994 Hz sim, stamps at 100,000,001 ns, `publisher_drop_rate` 0.0000                                                                                                                                                   |
| slow simulator (RTF < 1)                | **RULED OUT** — RTF **1.0000** on both runs with a clock series                                                                                                                                                                        |
| bench observer being a lossy instrument | **RULED OUT** — Autoware sees 8.47 Hz vs the observer's 8.53 Hz                                                                                                                                                                        |
| SHM-off UDP transport on ~460 KB clouds | **CONSISTENT, not isolated** — the registered Task 9 B-family confound                                                                                                                                                                 |
| host CPU starvation                     | **CONSISTENT, not isolated** — directly sampled in-run loadavg peaks **50.05** and **54.01** on 24 cores (means 25.80 / 29.80); and the deficits VARY between runs of one unchanged configuration (25.6% / 2.02 Hz vs 17.1% / 3.42 Hz) |
| NDT parameters vs the regen bundle      | **NOT RULED OUT** — untested                                                                                                                                                                                                           |
| the single-LiDAR concat relay           | **NOT RULED OUT** — and `/sensing/lidar/concatenated/pointcloud` had **2 publishers** in a separate probe, so it needs a look                                                                                                          |

**CONFIRMED CONTRIBUTOR: two publishers on NDT's input topic, and the launcher's
own stated assumption is wrong.** Probed live on `run-012` from inside the
container:

```text
/sensing/lidar/concatenated/pointcloud  publishers=2 subscribers=1
  PUB node=/sensing/lidar/concatenate_data
  PUB node=//relay
```

`cells/tier4_autoware.sh`'s comment justifies its relay by asserting that the
awsim_labs concatenate node "HARD-REQUIRES >= 2 input topics and **never loads**
with one". **It does load, and it publishes** — onto the same topic the relay
publishes to, which is NDT's input. That explains a rate (4.89 Hz) that is neither
the publisher's 10 Hz nor a clean fraction of the 2.77 Hz stage upstream of the
relay: it is the **sum of two sources**. If `concatenate_data` emits empty or
single-frame clouds, NDT is being fed an alternating mix of usable and unusable
inputs, which would depress its output rate independently of any CPU effect.
**Not fixed here** — removing or gating one publisher changes what the cell
measures, so it needs its own decision — but it is now a measured defect rather
than a suspicion, and the launcher comment that licensed it is falsified.

**So the second deficit is NOT localized to a single cause, and is recorded as
uncharacterized with the candidates above rather than attributed.** The two that
remain both have measured support but neither is isolated. What is settled: it is
not the source, not the simulator, and not the observer.

**Do not read 2.02 Hz, 3.42 Hz or 0.52 Hz as tier4-native's NDT rate.** They are
measurements of this stack on this host under this transport, and they move
between runs of one configuration. O-13.3 registered `ndt_expected_hz: 10.0` as
the deliberately conservative choice precisely so a decimating chain would FAIL
the criterion rather than hide inside a lower expectation — **on its first live
use, that registration did exactly its job.**

### `control_mode` reporting (R4): a per-approach interop gap, recorded not patched

Step 11.6 (`benchmarks/evidence/step-11_6-adapi-engage/`) found that on cell A —
a control that demonstrably drives — the AD-API `change_to_autonomous` service
refused for a full 60 s ("The target mode is not available", ~30 retries,
`adapi_change_to_autonomous.log`) while `set_route_points` had already
succeeded and localization/trajectory were healthy. Seconds later, in the
SAME state, the legacy `/autoware/engage` publish engaged instead:
`is_autoware_control_enabled: true`, and the gated `/control/command/control_cmd`
running at 20.07 Hz commanding +4.170 m/s on 281/281 samples
(`gated_control_cmd.log`) — while the same post-engage snapshot recorded
`is_autonomous_mode_available: false` (`legacy_autoware_engage.log`; a single
reading, not a continuous observation — "throughout" would overclaim it). The
decisive fact is that one: **which interface consults the flag differs; the
vehicle state does not.** Root cause is localized (inferred, not measured —
caveat below) to
`/vehicle/status/control_mode` reporting `4` (MANUAL), so the operation-mode
transition manager never marks autonomous available while `/autoware/engage`
bypasses that gate entirely. That specific reading was taken interactively
and is **not retained** (`benchmarks/evidence/README.md`'s step-11_6 row).

**A REFUTED claim about this, recorded with what refuted it (Task 13).** Task 13
asserted — in commit `296c8cb`'s message and its own report — that R4's arming
guard was structurally broken because "the legacy `/autoware/engage` publish
bypasses the operation-mode transition manager and never sets
`mode == AUTONOMOUS`", so `armed_ok`'s authority term could never pass. **That is
refuted by the retained evidence it should have been checked against first.**
`benchmarks/evidence/step-11_6-adapi-engage/legacy_autoware_engage.log` records
the post-legacy-engage snapshot on cell A as:

```text
mode: 2
is_autoware_control_enabled: true
is_autonomous_mode_available: false
```

and `OperationModeState.AUTONOMOUS == 2`. **So the legacy path DOES set the
operation mode on cell A**, R4's guard is satisfiable through its own fallback,
and there is no structural contradiction. The claim was a correct-sounding
generalization from cell B's single observation, which is the hazard this
document already names: a correct general rule applied to a case it does not
govern reads exactly like a correct specific claim.

**RESOLVED by measurement, and a SECOND claim of mine is retracted with it.**
After `run-008` (MRM active, `mode_autonomous=False`) I called this a per-approach
difference on the strength of `run-009`. **That was also wrong**, and it was the
same over-generalization from a single confounded observation. **The earliest
refuting artifact is `results/B/run-010/arm.log`**, which already records
`post-engage state: mode_autonomous=True is_autoware_control_enabled=True` — and
it was committed in `d2d3715`, two commits _before_ the claim was corrected, so
the refutation was sitting in the tree while the claim stood. `run-012`'s fully
observed arm below is the corroborating reading, not the first one. With MRM cleared and the arm fully observed, cell B reads:

```text
arm observations [pre-engage]:  mode=1 autonomous=False is_autoware_control_enabled=True
                                is_autonomous_mode_available=False
                                nonzero_longitudinal=0/10 peak_abs_velocity=0.000
arm observations [post-engage]: mode=2 autonomous=True  is_autoware_control_enabled=True
                                is_autonomous_mode_available=False
                                nonzero_longitudinal=0/10 peak_abs_velocity=0.000
```

**`mode` goes 1 → 2 at engage on cell B, exactly as on cell A.** So the legacy
`/autoware/engage` publish sets the operation mode on **both** approaches, there is
**no per-approach difference** in mode-setting, and R4's authority term is sound and
satisfiable on both. The "authority trilemma" was an artifact of two confounded
readings, not a real design problem — **no term needs re-picking.**

**Two further things these readings settle, both previously hypothetical:**

- **R4 round 1's rejection of `is_autoware_control_enabled` was CORRECT**, and the
  campaign never had the reading to prove it. It is **`True` PRE-engage** on cell B,
  with `mode=1` and **0/10 nonzero commands at peak 0.000 m/s** — so using it as the
  authority term would pass **vacuously**, exactly as that round feared. Its
  objection rested on "_if_ it is true in STOP mode on any cell"; it is, measured.
- **`is_autonomous_mode_available` stays `false` even at `mode=2`** — the same flag
  disagreement this section documents on cell A, now confirmed on B.

**What the arm fails on instead is LIVENESS, and that is a different finding.** With
`mode == AUTONOMOUS` satisfied, the gated `/control/command/control_cmd` measured
**0.00 Hz** post-engage (1.67 Hz pre-engage), `0/10` nonzero. The cause is upstream
of control: `/autoware/planning/topic_rate_check/trajectory` is **ERROR on 27
samples** — a route was accepted but **no trajectory was ever produced**, so
`vehicle_cmd_gate` had nothing to forward. The ego still shows
`ego_displacement_m=0.609` at `0.033 m/s`, i.e. drift rather than commanded motion.

**This is recorded as a per-approach finding, not fixed.** Two remedies were
available: make each approach publish `control_mode = AUTONOMOUS`, or arm
through the proven `/autoware/engage` path in the harness. R4 took the
second. Patching every approach's reported `control_mode` would erase
whether an approach reports its own control mode correctly — itself part of
the interop completeness this campaign exists to compare — and would
silently convert a genuine finding into a harness detail.
`benchmarks/injector/arm_and_goal.py` (R4) now attempts `change_to_autonomous`
on every cell and logs its outcome specifically so this observation keeps
getting made per approach, then unconditionally falls back to the proven
`/autoware/engage` publish so a refusal never blocks arming.

**Rate alone cannot substitute for this flag, and `arm_and_goal.py`'s arm
check does not try to.** R4's first cut verified only that the gated
`/control/command/control_cmd` sustains ~5 Hz nominal (near the geometric
mean of 1.30 Hz, `run-007`'s measured rate, and 20.07 Hz, step 11.6's
actually-engaged rate). Review found that threshold passes
`benchmarks/results/E/run-008` — 8.52 Hz on that same topic
(`run-008/observer.csv`), while `run-008/gt.csv` recomputes to 0.0000 m net
displacement and 0.0000 m path length: the ego never moved. That
`change_to_autonomous` was refused on that run too is an **inference**, not
a direct measurement of this flag — `run-008/bridge-stage2.log` retains 78
occurrences of that service's "target mode is not available" refusal and
zero `/autoware/engage` publications, over a harness commit that predates
`092dc9a`; neither run's `observer_topics.yaml` captured
`/api/operation_mode/state` itself. (`run-007` retains no arm-attempt
evidence at all beyond its own 1.30 Hz rate — not even that inference is
available for it.) A rate-only guard is therefore not sufficient on data
this campaign has already measured, and cell A's own control_cmd runs
~19.9 Hz of zero-velocity commands pre-engage in STOP mode (not retained as
tracked evidence — see step-11_6's row in `benchmarks/evidence/README.md`),
so a rate check with no lower bound on WHEN it samples can pass vacuously
before any engage at all.

A second review round found the first fix's authority term was itself the
wrong field: `arm_and_goal.py` initially gated on
`is_autoware_control_enabled`, but that flag reports **who drives**, not
**which operation mode** — some vehicle interfaces report it true in STOP
mode, which would let a stationary, un-engaged ego satisfy it (the same
false-ARMED shape, through a different door). `verify_control_flowing()`
now gates on `mode == OperationModeState.AUTONOMOUS` instead — the flag
this section's own retained snapshot (`mode: 2`) actually states a value
for — AND the rate, with BOTH reset at the engage call.
`is_autoware_control_enabled` is still read and logged (a recorded, not
gating, per-approach observation) rather than dropped, since whether it
tracks `mode` correctly is itself part of the interop comparison.

**Status: cell A measured; cell B PARTLY measured (2026-07-30, Task 13); cells
B45, D and the E family unmeasured** — and for B45 and D that is now
**permanent**, since both were struck by the owner's core-duel scope cut
(2026-07-30, see the amendment below), so this observation will never be
recorded for either. The E family's half stays owed (Task 20). Task 13 (cell
B's closed-loop gate) and Task 15 (cell C's re-gate) must record their own
`change_to_autonomous` outcome here, in this same form: which cell, refused or
succeeded. `arm_and_goal.py` logs `change_to_autonomous: SUCCEEDED` or
`did not succeed` to its own stdout/stderr
at `run.sh` step 9, but `run.sh` does not currently redirect that step into a
per-run file (`launch.log` is written by the cell launcher's earlier bring-up, a
different step) — the observer capturing that invocation's console output is what
makes this observation recomputable; a bare "succeeded/refused" claim without it
would not clear this file's own evidence rule.

**Cell B's half of the observation, and it is a real per-approach difference.**
The value the gap is about differs between the two duel cells:

| cell | `/vehicle/status/control_mode` while parked | published by                                                                                                                                                                      |
| ---- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A    | `4` (MANUAL)                                | the extension, from the ego's live state (step 11.6, not retained)                                                                                                                |
| B    | `1` (AUTONOMOUS)                            | the tier4 fork, **unconditionally** — `ROS2.cpp:1117` `SetControlMode(ControlMode::AUTONOMOUS)`, with the fork's own `TODO: Add logic to use the input of control mode` beside it |

Cell B's reading was taken live from `/vehicle/status/control_mode` during
`benchmarks/results/B/run-002` (`mode: 1`, stamp 28.41 s of sim time). So the
approaches differ on exactly the flag this section is about: one under-reports
its mode, the other reports AUTONOMOUS whether or not it is. **Neither is
patched**, for this section's original reason — whether an approach reports its
own control mode correctly is part of the interop completeness being compared.

**What is still unobserved on cell B:** the `change_to_autonomous` outcome
itself. `run.sh` never reached step 9 on any B run — the cell launcher failed
first, on the localization-initialization block described in the next section —
so `arm_and_goal.py` has still never run against a real stack, on any cell. That
is the R4 verification the plan expected from Task 13 and it remains owed.

**Caveat carried forward from step 11.6:** the link from `control_mode =
MANUAL` to the transition manager's refusal is inferred, not measured — the
alternative candidate is the `control_mode_request` handshake. The
observation that the two engage paths consult different state holds either
way, but this has not been upgraded to a measurement.

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
- **2026-07-28** — `## Known confounds` gained the CAL-seam per-publish
  allocation entry (the fork's shared `CarlaPointCloudPublisher::
WritePointCloud` rebuilds `message->fields` from scratch on every
  publish, a cost the extension side's preallocated `msg_` does not
  carry). Completeness: Task 14 round-2 review found this base-class
  asymmetry burdens the in-core publisher only, biasing the paired
  seam-overhead delta, and nothing recorded it before any P3 CAL-seam
  run.
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
- **2026-07-28** — this file's `## Metrics` section gained "Primary-duel
  metric definitions", registering `one_hop_wall_ms`,
  `lidar_to_ndt_sim_ms`, `control_staleness_ms`, `carla_process_cpu_pct`
  and `achieved_rate_ratio` (source columns, join rule and tolerance,
  aggregation, and the scoring window each is computed over).
  Completeness: `config/margins.yaml` pre-registered a margin for all
  five and the M5 definitions above define a different set, so the
  campaign's headline A/B verdict was "Δmedian versus margin" on metrics
  whose computation was undefined — and two implementers had already had
  to invent semantics for them, which is precisely what pre-registration
  exists to prevent. Margins are unchanged.
- **2026-07-28** — `config/cells.yaml`: every cell entry gained a
  `metrics:` block (`lidar_topic`, `ndt_topic`, `control_topic`,
  `control_published_time_topic`, `cpu_process_label`, `tick_hz`,
  `lidar_expected_hz`), with `null` where the value is genuinely not
  chosen yet and the owing task named beside it. Completeness: the
  definitions above need a per-cell topic, process label and expected
  rate, and none of the three was machine-readable anywhere, so each
  tool that needed one supplied its own constant — leaving the campaign
  with no single registered answer to "which topic / label / rate is
  this cell's", and no way to tell a considered value from a default.
- **2026-07-28** — the data contract above gained `quality.json`, and
  this file gained the "M5 gate result" section registering its schema
  (`QualityStats` plus `arm`, `window_sim_ns`, `ladder_branch`,
  `expected_ndt_hz`) and why the gate verdict is a recorded fact of the
  run rather than a manifest field or a per-consumer recomputation.
  Completeness: the M5 gate has no committed writer, so the first
  consumer of its verdict invented a file and a schema for it.
- **2026-07-28** — `scripts/cell_info.py` gained `metrics_for()`, the
  single accessor for the block above; it raises on a cell with no
  `metrics:` block or a missing key. Completeness: a registry a tool
  reaches into with a bare dictionary lookup fails as a `KeyError` deep
  in an analysis run, which is how an unregistered cell would first be
  noticed mid-campaign.
- **2026-07-28** — "Primary-duel metric definitions" gained an **arm
  scoping** rule: the duel is computed per arm and reported as separate
  rows, never pooled. Completeness: the section registered a window per
  arm while `cells.yaml` gives cell A two arms and `margins.yaml` is
  silent, so two implementers pointing a tool at `results/A/` would pool
  whatever arms they found; Task 18 also runs the two arms as separate
  n ≥ 10 sessions, which pooling would double-count.
- **2026-07-28** — `control_staleness_ms` gained its **contingent
  response under branch (a)**: reported descriptively and excluded from
  the equivalence verdict, with the margin left untouched. It also
  gained a third clock-domain branch (both stamps wall) and a
  per-Autoware-image (not once-per-campaign) recording requirement.
  Completeness: the branch-(a) consequence follows from the tick period
  alone and needs no data — a 50 ms quantum makes a ±10 ms TOST able to
  return only Δ = 0 parity or a directional verdict — so leaving it to
  be decided after Tasks 13/20 land an artifact would have been a
  definition settled after seeing data, which the rule above forbids.
- **2026-07-28** — the aggregation rule gained an explicit **exemption
  for `achieved_rate_ratio`**, which is a run-level `(n − 1) / span`
  scalar rather than a per-message series. Completeness: the blanket
  "median of the in-window series" wording contradicted that metric's
  own definition, and the two constructions diverge precisely when
  frames drop, i.e. on the phenomenon it measures.
- **2026-07-28** — `config/cells.yaml` gained `ndt_expected_hz` and
  `cell_info.METRIC_KEYS` with it. Completeness: the `quality.json`
  schema registered above makes `expected_ndt_hz` a required key and
  `analysis/quality.py` divides by it, but the `metrics:` block created
  for exactly that purpose did not carry it — and on the high-frequency
  cells sourcing it from `tick_hz` would fail every run five-fold while
  reading as a localization result.
- **2026-07-28** — "Scoring window" gained a second, unfittable branch
  (`static_window` over `observer.csv`'s `arrival_system_ns`, no domain
  conversion) and the recorded consequence for Task 16's margin
  transfer. Completeness: every non-closed-loop arm was bound to a
  window over `clock.csv` and a conversion through the clock fit, and a
  cell that publishes no `/clock` has neither — including `CAL-rmw`, the
  cell `one_hop_wall_ms`'s margin is frozen from.
- **2026-07-28** (supersedes the entry above, same amendment window) —
  the branch is now selected **per run** by a mechanical test on the
  run's own `clock.csv` (≥ 2 data rows = `fit_sim_wall_affine`'s own
  stated precondition), with the expected branch recorded per cell so a
  surprise is a loud finding; and the contradiction between
  `cells.yaml`'s `CAL-seam: carla: 0.10-fork` (which makes `run.sh`
  start the clock watchdog and use the fit-strict renderer) and
  `scripts/cal_report.py`'s assertion that CAL-seam has no `/clock` is
  recorded as Task 14's to settle. Completeness: the branch had been
  keyed off the `carla:` field and justified by citing `cal_report.py`,
  which is the **CAL-seam** tool specifically, not a generic calibration
  one — so the rule was keyed on an attribute that does not determine
  fittability, against evidence scoped to a different cell than the one
  it was applied to. Testing the data instead of the attribute makes the
  rule correct whichever way Task 14 resolves the contradiction.
- **2026-07-28** — `config/cells.yaml`: `tick_hz` set to `null` on the
  tier4 cells (`B`, `D`, `B-hf`, `B45`) and on `CAL-seam`, naming
  Tasks 13 and 14. Completeness: those values were transcribed from an
  out-of-repo demo script's literal while `lidar_expected_hz` on the
  same cells was left `null` for being un-sourced — the same evidence
  held to two standards. The bar is now stated once in `cells.yaml` and
  applied uniformly: committed evidence in this repo, or `null`.
- **2026-07-28** — `ndt_expected_hz: 20.0` on `A`/`C` re-grounded on
  `docs/e2e-report.md`'s live re-run (NDT ~20 Hz over 400 samples,
  `kinematic_state` 19.97 Hz) instead of on the mechanism ("one pose per
  input cloud, rate-preserving chain"). Completeness: the mechanism is
  an assertion about Autoware, which does not clear the evidence bar
  this amendment set one entry earlier — and in-repo evidence that does
  clear it already existed and had simply not been cited.
- **2026-07-28** — `A-hf`'s `tick_hz: 100.0` labelled explicitly as a
  registered TARGET, with the wiring it still needs named (no committed
  launcher passes `--fixed-delta 0.01`) and a requirement that the
  applied value be recorded per run so the target is checked rather than
  trusted. Completeness: it cleared the evidence bar in letter (the
  `--fixed-delta` mechanism is committed) but not in spirit, and an
  unapplied target that reads like a setting is the silent-wrong-number
  class this campaign guards against. It is kept rather than nulled
  because the mechanism exists here, unlike `B-hf`'s, where no launcher
  exists at all.
- **2026-07-28** (supersedes the entry above, same amendment window) —
  `A-hf`'s `tick_hz` set to `null`, naming the task that wires this
  cell's launch arguments. Completeness: the "registered target" above
  left a number nothing was obliged to apply and nothing could check —
  `RunManifest` has no field to record an applied fixed-delta and the
  requirement named no owning task, so the target's own verification
  was itself unregistered. The justification is `B-hf`'s exactly (the
  wiring to apply it is not written); a committed mechanism nobody
  invokes is not a setting, so the same justification now gets the same
  answer. `cells.yaml`'s `arms: [closed-loop] # fixed_delta 0.01` still
  records the cell's intent; `tick_hz` records what a run will actually
  tick at.
- **2026-07-28** — the clock-domain taxonomy for `control_staleness_ms`
  gained its **fourth** combination (source WALL, published SIM) as an
  explicit fail-loud with no formula. Completeness: the text asserted
  three combinations were "reachable" while the discriminator is applied
  per column, so the fourth was unregistered rather than excluded — and
  computing it as a reversed branch (b) would yield a large negative
  staleness that reads like a real result.
- **2026-07-28** — the aggregation rule's exclusion list gained "runs of
  another arm never contribute". Completeness: the arm rule was
  registered under "Arm scoping" but not restated where a tool author
  writing the aggregation step would look, next to the exclusion and
  no-pooling clauses it belongs with.
- **2026-07-28** — `one_hop_wall_ms`'s `cal_report.py` paragraph
  narrowed from "CAL cells" to **`CAL-rmw`**, citing
  `observer/src/bench_pub.cpp`'s own CAL-rmw-scoped first line for the
  wall-`now()` stamp and `cells/calibration.sh` for the absence of a
  `/clock` publisher, and stating that `CAL-seam` is not covered.
  Completeness: that sentence still asserted unconditionally the exact
  fact — CAL-seam's `/clock` status — that the scoring-window section
  had just registered as an OPEN contradiction owed to Task 14. One
  document answering one question two ways, with the metric entry being
  the likelier landing spot of the two.
- **2026-07-28** — the expected-branch rule gained a named owner and a
  required behaviour: Task 22 implements the branch-mismatch check in
  `scripts/duel_verdict.py`'s window resolution and Task 23 mirrors it
  in `scripts/sweep_verdict.py`, surfacing a mismatched run in the
  rendered table's notes. Completeness: "a loud finding, not a silent
  fallback" is the half of the discriminator rule that makes it safe
  rather than merely correct, and it was prose with no owner and no
  code — unlike every other obligation registered here.
- **2026-07-28** — the high-frequency cells' unregistered bindings now
  name **Task 26** ("Optional cells — E-opt, A-hf/B-hf", owner-strikable)
  by number, where they previously named their owner only by
  description. Completeness: every comparable obligation here names a
  task number, and the tools' pending-task mappings are keyed off these
  names — a cell whose owner exists only in prose yields a generic error
  instead of one naming the task an operator is waiting on. Recorded
  with it: Task 26 is strikable, so `null` is a legitimate permanent end
  state for these cells, not a gap awaiting closure.
- **2026-07-28** (EXTENDS the `tick_hz` correction above to that cell's
  two sibling bindings — it supersedes neither entry: both of those are
  about `tick_hz` alone, while these two fields shipped at 20.0 with the
  `metrics:` block and never had an amendment entry of their own) —
  `A-hf`'s `lidar_expected_hz` and `ndt_expected_hz`
  also set to `null`, and `B-hf`'s `ndt_expected_hz` re-pointed at
  Task 26. Completeness: both were registered at 20.0 on the reasoning
  that `--fixed-delta` moves only the world tick, so `A-hf` inherits
  cell `A`'s `sensor_tick` and `min(1 / sensor_tick, tick_hz)` stays 20.
  Reading Task 26 to name it as owner falsified that: its Step 2 sets
  `A-hf`'s LiDAR `sensor_tick` **explicitly**, to neither cell `A`'s
  value nor the tick period, so the sensor rate is neither inherited nor
  derivable from the tick — and it does the same for `B-hf`. A wrong
  `lidar_expected_hz` is the denominator of `achieved_rate_ratio` and,
  through `ndt_expected_hz`, of the M5 gate's rate criterion.
- **2026-07-28** — `achieved_rate_ratio` gained the M2 three-way
  reconciliation's **window/scope rule** (same resolved window as the
  metric itself, reported per cell and per arm, "not measurable" vs. a
  file-backed real zero kept distinct) and its **cross-run reduction
  rule — owner ruling: median AND max, both reported**, for
  `publisher_drop_rate` and `observer_loss_rate`. Completeness: the
  reconciliation was registered as existing (2026-07-28, above) but its
  own scope and cross-run reduction were not — a gap Task S4's
  implementation surfaced rather than resolved unilaterally. The
  reviewer objected that this output is an instrument-artefact detector
  the five duel metrics' median-only convention would under-report at
  the registered n = 3 minimum; the owner ruled median stays (continuity
  with that convention) with max added beside it (so a lone high-loss
  run is not buried). Margins are unchanged; this is a diagnostic, not a
  duel metric, and carries no margin of its own.
- **2026-07-28 — owner ruling** — the M2 reconciliation's **published
  count is windowed too**, and `publisher_counts.json` gained the schema
  (`publisher_counts/2`) that makes windowing it possible: one sim stamp
  per published message instead of a single whole-run total, registered
  in the data contract at the top of this file. A file in the old shape
  is refused by name rather than reinterpreted.
  Completeness: the window rule registered one entry above said "the
  SAME resolved scoring window" while only two of the three counts were
  in fact windowed — the published one was a cumulative `sensor.listen`
  counter with no window at all. On a healthy 60 s static run against
  the registered [t0 + 20 s, end] window that combination reports
  `publisher_drop_rate` 0.000 (clamped, structurally blind to any real
  drop below ~33%) and `observer_loss_rate` ~0.333 (fabricated by the
  interval mismatch), on exactly the two cells this diagnostic exists to
  arbitrate between. The alternatives were rejected on the record:
  reconciling whole-run everywhere would readmit the warm-up this
  section's own window rule removes, and emitting nothing would leave
  `achieved_rate_ratio`'s publisher/observer split undecidable. This
  lands before any P3 run, so no measurement is scored under the old
  shape. Margins are unchanged.
- **2026-07-28** — the reconciliation's **four output states** (null
  binding, invalid `lidar_expected_hz <= 0`, all-runs-zero-published
  `NaN`, per-run failure) registered explicitly. Completeness: all four
  are implemented and all four are mechanically discriminable from data,
  so the campaign's standing rule — pre-register both branches of any
  discriminable state — applied to them; the invalid-binding row in
  particular existed only in code. No behaviour changes with this entry.
- **2026-07-28** — the reconciliation table reports **both sample
  sizes** (`n measurable` for the publisher pair, `n observer` for the
  observer pair). Completeness: the reduction population registered
  above is "each cell's measurable runs", but the observer pair
  additionally excludes the NaN (zero-published) runs, so its true n was
  never printed and a reader pairing the one printed n with an observer
  statistic would overstate that statistic's sample size — by all of it
  when every measurable run published nothing.
- **2026-07-28** — the expected message count's **time domain is named
  as SIM**, and the M4 sweep's `publisher_rate_ratio` now takes its span
  from `clock.csv`'s `clock_ns` extent instead of the wall arrivals of
  the same rows (`scripts/sweep_verdict.py`). This changes M4's
  registered semantics and lands before Task 16, with no sweep run
  collected. Completeness: `max(1, round(window_s * lidar_expected_hz))`
  was registered with `window_s` "the window's own span in seconds" and
  no domain named, while the two callers of the one shared
  implementation passed spans from different domains — sim in
  `duel_verdict.py`, wall in `sweep_verdict.py`. `lidar_expected_hz` is
  sim-domain by its own registered relation (`min(1 / sensor_tick,
tick_hz)`, both simulation-time periods), so a wall span inflates the
  expectation by `1 / RTF`, depresses `publisher_rate_ratio` by the same
  factor and can fire the ceiling's publisher disjunct on a publisher
  that dropped nothing — on exactly the sub-real-time arms where the
  ceiling verdict is the point, and duplicating a signal
  `evaluate_ceiling` already scores with its `rtf` and `tick_rate_ratio`
  disjuncts. Margins are unchanged; the ceiling thresholds are unchanged.
- **2026-07-28** — the M5 gate's **G1 ladder branch condition** is keyed
  on the map bundle the cell localized against, not on whether Task 11's
  pcd registration fix landed; the two thresholds are unchanged, and no
  cell script changes with this entry. Completeness: the condition was
  phrased as a campaign-level event, while the plan's D3 companion
  ruling scopes the shift to cells A/B (the UE5 world) and makes E's
  bundle choice a MEASURED question (E's static NDT bias, Task 10). With
  the fix landed, branch (a) read as satisfied campaign-wide and would
  have gated cell E at max pose_error < 0.5 m against the deliberately
  unshifted bundle `cells/python-bridge.sh` pins — failing E by ~0.475 m
  of map registration, under a reason that would be attributed to the
  bridge.
- **2026-07-29 — owner ruling** — `scripts/sweep_verdict.py`'s
  `_publisher_rate_ratio` gained a registered **third publisher-counts
  outcome: refused, and the whole invocation aborts**. A present
  `publisher_counts.json` that is malformed or carries an unrecognised
  schema tag (`analysis/publisher_counts.py`'s `read_publisher_counts`
  raises `PublisherCountsFormatError`), or one that does not carry the
  cell's registered `lidar_topic` key (`PublisherCounts.whole_run_count`
  raises the same `PublisherCountsFormatError`), is not caught anywhere
  in this module: the exception propagates out of `verdict_for_run` and
  out of `main`'s per-run loop, aborting the entire `sweep_verdict`
  invocation for that cell/class — no point of that sweep is scored,
  not only the offending run. The file-absent (`NOT_MEASURABLE`) and
  file-backed zero-published (`NaN`) outcomes were already registered
  above; this third one was not. Completeness: consistent with
  `evaluate_ceiling`'s own refusal of `None` inputs — a silent skip
  here would misreport the point as "ceiling not reached", i.e. claim
  headroom that was never tested; degrading a refused file to a
  per-point annotation instead would make it a fifth output state next
  to the four already registered above, and an unmeasurable point must
  never read as a clean measured pass; and it matches the repo's
  fail-loudly convention, where precise failure localization is the
  deliverable. No behaviour changes with this entry.
- **2026-07-29** — `## Known confounds` gained the DDS middleware and
  transport entry (the B family must run `rmw_fastrtps_cpp` with shared
  memory off — `observer/config/udp_only.xml` — in **both** the observer
  and the Autoware container, while A/C run CycloneDDS-on-`lo` and the E
  family runs Fast-DDS with SHM on). No margin, threshold or cell
  definition changes with this entry. Completeness: Task 9 measured that
  the tier4 fork announces SHM-only user-data locators that ROS 2
  Humble's Fast-DDS 2.6.11 cannot read, in **both** directions — sensing
  out of the fork and control into it — and that the fork cannot be
  reconfigured from its own side, so the fix has to be applied to the
  DUT's own middleware for the B family only. That makes Autoware's
  transport differ between the two arms of the headline duel (A vs. B),
  which is inside the measured system for M3 and for the intra-stack
  part of M2, and `CAL-rmw` cannot bound it because `CAL-rmw` runs no
  Autoware at all (`cells/calibration.sh:7-12`). Recorded only in a task
  report before this entry, and the earlier task report framed it as an
  `observer_env` difference alone, which understates it.
- **2026-07-29** — `config/cells.yaml`: cells **E** and **E-opt** got
  `metrics.lidar_topic: /sensing/lidar/top/pointcloud_raw_ex`, replacing
  `/pointcloud_before_sync`; `config/observer_topics/{E,E-opt}.yaml`
  follow. Cell **E0 is unchanged** and keeps `/pointcloud_before_sync`.
  Completeness, not accommodation: Task 10's
  `patches/python-bridge/0002-sensor-config-harmonized.patch` sets the
  bridge's `topic_suffix` to `/pointcloud_raw_ex` — the spec's stated
  injection topic in _every_ cell — so that is where the patched bridge
  now emits, and a binding naming the old topic would make E's M1/M2
  metrics read a topic with no publisher. E0 runs the unpatched image and
  therefore genuinely still emits the old name; the three E-family topic
  lists are deliberately no longer identical. Recorded here because
  `observer_topics/E.yaml`'s own comment delegated exactly this
  re-grounding to Task 10.
- **2026-07-29** — `## Known confounds` gained the E-family sensing-graph
  entry (cell E keeps `carla_sensor_kit`, whose preprocessing chain is two
  crop-box filters and a relay, against the natives'
  `awsim_labs_sensor_kit`) plus the idle camera-republish nodes the
  harmonized bridge kit leaves in its launch tree. No margin, threshold or
  cell definition changes with this entry. Completeness: the spec
  pre-registered the kit difference as a fallback with a confound row
  owed, Task 10 took that fallback, and nothing in this file recorded it.
- **2026-07-29** — the patch policy above gained a **second** named
  exception, for a `carla_ros.py` change that would publish
  `/sensing/gnss/pose_with_covariance` at `base_link` instead of at the
  CARLA actor origin. Granted by the owner, owner-strikable, and
  **registered only — no patch file is written and none is applied.** It
  is registered now so the grant sits inside the pre-registration window,
  and deferred to cell E's re-gate because the hypothesis it was requested
  on was refuted (that topic is not an `ekf_localizer` pose input in this
  launch tree, and NDT regularization is off), so applying it now would
  spend the exception on a contested cause. No margin, threshold or cell
  definition changes with this entry.
- **2026-07-29** — `## Known confounds` gained the ground-truth frame
  entry: `collect_gt.py` records the CARLA actor origin (car centre) while
  every Autoware pose it is compared against is `base_link` (rear axle),
  so a constant longitudinal offset — measured at −1.4045 m on
  `results/E/run-006` — sits in every cell's M5 `pose_error`. ~~Task 16 owes
  either the correction or the offset stated beside every number.~~
  **CLOSED 2026-07-30 — superseded by the per-approach GT-anchor amendment
  below, which landed the correction in Task 13. Task 16 no longer owes it.**
  The remedy chosen was the transform, not the stated offset: the term is
  body-frame longitudinal, so in the map frame it rotates with yaw, and a stated
  constant would be wrong by up to 2.77 m over the committed route's 169.4°
  turn.
  Completeness, not accommodation: the M5 definitions pre-register
  `pose_error` against `gt.csv` and never said which frame `gt.csv` is in,
  and the first live measurement of it made the gap visible. The entry also
  records the E-family-only 0.03 m sensor-placement inconsistency between
  the bridge's `DEFAULT_WHEELBASE` 2.850 and `sample_vehicle`'s 2.79. No
  margin, threshold or cell definition changes with this entry.
- **2026-07-29** — the data contract above gained `pose.csv`, with a typed
  `pose` observer kind (`geometry_msgs/msg/PoseWithCovarianceStamped`) in
  `observer/src/bench_observer.cpp` and `analysis/bench_io.py`
  `read_pose_csv` to read it; every `config/observer_topics/*.yaml` entry for
  the NDT topic moved from kind `generic` to kind `pose`. Completeness, not
  accommodation: M5's `pose_error_m` was pre-registered as "NDT pose minus
  CARLA ground truth" while the NDT topic was recorded by a GENERIC
  subscription, which writes only stamp and serialized size — so no NDT x/y
  existed anywhere in the campaign, `evaluate_quality`'s `ndt_xy` argument had
  no data source, and the mandatory M5 metric was not computable. The one
  file that did carry an x/y pose, `odometry.csv`, is the EKF-fused
  `/localization/kinematic_state`: redefining `pose_error` onto it would have
  masked NDT error behind IMU/odometry fusion, so it is deliberately a second
  file rather than a second topic in the first.
- **2026-07-29** — the data contract above gained `tf.csv`, with a typed `tf`
  observer kind (`tf2_msgs/msg/TFMessage`) that records only the transforms
  matching a configured `child_frame_id` — the topic spec's new optional
  fourth field — plus `read_tf_csv`; `config/observer_topics/E.yaml` now
  registers `/tf` filtered to `base_link`, superseding (and citing) that
  file's own prior instruction not to add the topic. Completeness: cell E's
  re-gate needs the map→base_link TF rate as its H1 discriminator, and the
  `generic` kind cannot record it in two independent ways — `stamp_from_cdr`
  reads `stamp.sec` at CDR byte 4 while `TFMessage` is a `TransformStamped[]`,
  so byte 4 is the sequence LENGTH and every row would carry a valid arrival
  stamp beside a silently nonsense header stamp; and with no frame filter the
  recorded rate is the aggregate across every broadcaster, which stays healthy
  while the one pair under test is dead. The parent `frame_id` is recorded
  rather than filtered on, so map→base_link is verified instead of assumed.
- **2026-07-29** — `pose_error_m`'s definition above now names the file it is
  computed from (`pose.csv`, the cell's registered `ndt_topic`) and states
  explicitly that `odometry.csv`'s `/localization/kinematic_state` is not a
  permitted substitute. Completeness: the definition named the quantity and
  the join rule but no source column, which is exactly the gap that let the
  metric be registered as mandatory with nothing recording its input.
- **2026-07-29** — `config/cells.yaml`'s `metrics:` block gained
  `ladder_branch` and `abs_pose_gate_m`, both `null` on every cell and naming
  their filler, and `scripts/cell_info.py` `METRIC_KEYS` gained both.
  Completeness: `abs_pose_gate_m` existed only as an `evaluate_quality`
  parameter, so no config could select the G1 ladder branch and the M5 gate
  had no way to know which localization criterion applied to a cell. Plan
  Task 11's live G1 re-gate on the shifted Town10 bundle selects it. They are
  TWO keys rather than one because `evaluate_quality(abs_pose_gate_m=None)` is
  itself the relative branch: with one nullable threshold, "the relative
  branch was selected" and "no branch is selected yet" would be the same
  registered value, and the gate would silently report an UNGATED cell as
  gated. No threshold is registered here; both branches' thresholds stay as
  the M5 definitions above already fixed them.
- **2026-07-29** — the "M5 gate result" section above gained its writer
  (`scripts/write_quality.py`, `run.sh` step 13), the registered set of
  conditions under which that step REFUSES rather than writing a verdict, and
  the three-state table for the ladder binding. Completeness: the section
  registered the file's schema and said outright that no writer existed, so
  the M5 gate — a mandatory per-cell validation gate — was pre-registered and
  unexecutable, and its only consumer (`sweep_verdict`) was reading a file
  nothing produced.
- **2026-07-29** — `run.sh` gained the M5 gate as step 13, between
  `finalize_rtf` (12) and the exclusion step, renumbering exclusions to 14 and
  the render smoke to 15; `--dry-run` lists it. It is deliberately NON-FATAL:
  a refusal is a warning, because the run's data is already on disk and the
  exclusion step still owes the directory a pre-registered label. Completeness:
  without a numbered step nothing produced `quality.json`, and a hard failure
  here would make every legitimately un-gateable cell (a null
  `ndt_expected_hz`, an unselected ladder branch, no localization stack at all)
  unfileable.
- **2026-07-29** — `bench_observer` now writes `odometry.csv`'s and
  `pose.csv`'s `x_m`/`y_m` in FIXED notation at 4 decimals, matching
  `collect_gt.py`'s own `f"{x:.4f}"`, instead of `std::ostream`'s default of 6
  SIGNIFICANT digits. Completeness: 6 significant digits is ~1 mm on Town10's
  ±150 m coordinates but only ~0.1 m on Nishi-Shinjuku's
  (`config/routes/NishishinjukuMap.yaml`'s polyline starts at 81371.133,
  49912.721) — half the ladder's 0.2 m no-drift threshold and a third of its
  0.3 m spread threshold, on the cells (C/D) whose map has the large
  coordinates. A metric may not be quantized by its own recorder, and the two
  sides of `pose_error` must carry the same resolution.
- **2026-07-29** — `bench_observer`'s topic-spec format gained an OPTIONAL
  fourth field (`"<topic>|<type>|<kind>|<arg>"`), used by the `tf` kind for
  its `child_frame_id`; a fifth field and a present-but-empty fourth are both
  refused at startup. Completeness: the three-field parser already accepted
  and silently DISCARDED any tail, so a typo'd or misplaced filter would have
  produced an unfiltered recording that looks like a filtered one — the same
  silent-wrong-number class the strict three-field check was added for.
- **2026-07-29 — owner ruling** — the two goal metrics
  (`goal_closest_approach_m`, `goal_terminal_distance_m`) are computed over a
  **goal window** — the full armed span after the 20 s warm-up discard,
  warm-up-trimmed and NOT station-trimmed — instead of over the run's scoring
  window; `pose_error_m`, `lateral_deviation_m` and the NDT rate are
  unchanged and stay on the scoring window. `quality.json` gained
  `goal_window_sim_ns` as a fifth provenance key so the two numbers are
  interpretable. Completeness, not accommodation: both committed routes set
  `stations.end_m` at (route length − 20 m) while their goal sits at the
  route's END, so the station window's last possible sample is 19.772 m
  (Town10) / 20.039 m (Nishi-Shinjuku) from the goal — and the gate's own
  registered criterion is `goal_closest_approach < 1.0 m`. As previously
  registered the two could not both hold on either map, so EVERY honest
  closed-loop run would have failed the gate for a reason that is an artifact
  of the window rather than a property of the approach. The station window's
  registered purpose (`analysis/window.py`'s docstring) is that "every run
  scores the same stretch of road regardless of small speed differences", i.e.
  comparability of the rate/latency/resource metrics; the goal criterion's is
  continuity with P0/P1's G2, which measured closest approach over the whole
  run (0.064 m). Applying the first to the second was the defect.
  `stations.end_m` was NOT extended instead: the "Scoring window" paragraph
  registers that same window for all five margin-carrying duel metrics, so
  moving it would have moved the campaign's headline equivalence measurement.
  No margin, threshold or route changes with this entry.
- **2026-07-29 — owner ruling** — the per-cell validation gate is **arm-scoped**:
  on the `static` arm the two goal criteria DO NOT APPLY, so that arm's gate is
  the NDT-rate criterion plus the G1 ladder criterion, and both goal fields are
  recorded as `null`. Every other arm — the sweep arms included, since `run.sh`
  drives them under either a static or a closed-loop `window_arm` and only the
  manifest's own `static` states that the ego was parked — is unchanged.
  Completeness: the gate was registered as an unscoped conjunction including
  `goal_closest_approach < 1.0 m`, which a parked ego can never satisfy, so the
  static arm's gate was structurally unpassable and its `quality.json` would
  have recorded `gate_pass: false` plus a meaningless distance on every run.
  Recorded here, in the pre-registration document, rather than only in a commit
  body and a test — this file is where the contradiction and its resolution
  belong, following the precedent of the CAL-seam "open contradiction recorded"
  block above.
- **2026-07-29** — the **G1 ladder branch is SELECTED for the two extension
  Town10 cells: `absolute`, `abs_pose_gate_m: 0.5`** (`cells.yaml` on `A` and
  `A-hf`). Registered here because branch selection is a pre-registration item,
  and legitimate now only because no P3 measurement run has happened. **No
  threshold changed**: both branches' criteria are exactly as the M5
  definitions above fix them, and nothing was relaxed — the absolute gate was
  met on its own terms. Cells `B`/`B-hf`/`B45` deliberately keep a `null`
  binding; see the last bullet of this entry. Rung by rung, on Task 11's live
  re-gate:
  - **Step 3 (the pinned `dy = -0.475` rigid shift): FAIL.** Max NDT error
    **0.824 m** over 400 static samples, and 0.749 m on a second window. The
    registered shift did work — the cross-track constant fell from the
    pre-shift +0.477 m to +0.005 m across an 8-seed sweep — but a residual
    `(dx, dy) = (-0.32, +0.12)` m and within-lock jitter remained. The two
    window maxima and that residual are recomputable from
    `benchmarks/evidence/g1-ladder-rigid/`; **the 8-seed sweep's own output is
    NOT retained** (it printed to a session transcript, and
    `scripts/e2e/seed_sweep.py` writes no file), so every per-seed figure in
    this entry — the +0.005 m mean, the +0.132 m converged-subset residual and
    the 1.898 m across-seed x scatter — is reported without a recomputable
    artifact. Re-running the script on the same bundle would reproduce the
    method, not the numbers.
  - **Rung 1 (Refit): FIRED, FAILED.** The sweep's cleanly-converged seeds
    still showed a clean +0.132 m cross-track residual (std 0.012 — from the
    unretained sweep, as above), so the precondition was met; re-shifting from
    source by that mean (`dy = -0.607`, `pins.yaml` `town10_pcd_refit`) drove
    the bias to `(-0.075, -0.029)` m and still measured max **0.570 m**
    (`benchmarks/evidence/g1-ladder-rigid/refit/`).
  - **Rung 2 (Regenerate): FIRED, and PASSED at max 0.089 m** — 411 mm inside
    the gate, bias `(+0.021, -0.038)` m, per-axis jitter std 0.019 / 0.013 m.
    `benchmarks/scripts/build_pcd_from_gt.py` rebuilt the pointcloud from
    1996 ground-truth-registered 128-channel sweeps (0.2 m voxel,
    `pins.yaml` `town10_pcd_regen`), recorded over a 100 s `--window` while
    the ego drove. Rung 3 was therefore NOT reached and the relative branch
    was NOT taken.
    Why rung 2 succeeded where re-registration could not: it fixes point
    DENSITY, not merely a frame offset. Two corrections to an earlier revision of
    this entry, kept rather than quietly dropped: a 0.635 m "floor" derived by
    subtracting the CENTROID was an **upper** bound, not a lower one (a centroid
    minimises RMS, not the max), and the refit's own 0.570 m came in under it;
    and the residual was attributed to along-track jitter, which the data does
    not support — the dominant jitter axis SWAPPED between windows (dx 0.097 /
    dy 0.171 on the `dy = -0.475` window against dx 0.229 / dy 0.094 on the
    refit). Stated as only what is verified: on the refit window the
    **Chebyshev-optimal** rigid offset (the minimum-enclosing-circle centre, the
    offset that genuinely minimises the max) leaves max **0.5041 m** — over the
    gate by 4 mm, on a statistic whose same-bundle window-to-window spread was
    0.075 m. Rigid registration came MARGINALLY short and was never decisively
    excluded; and since rung 2 is non-rigid, a rigid bound said nothing about it
    in any case.
    Because the branch now differs between two bundles of the SAME map —
    regenerated takes (a), every rigid variant takes (b) — cells
    `B`/`B-hf`/`B45` cannot be registered until Task 13 wires a bundle, and
    their binding stays `null` so the M5 gate refuses them rather than gating on
    whichever bundle Task 11 happened to drive.
- **2026-07-29** — `pins.yaml` gained **`town10_pcd_refit`** (`dy_m: -0.607`)
  and **`town10_pcd_regen`** beside the existing `town10_pcd_shifted`, rather
  than either being edited into it, and `scripts/e2e/map_defaults.sh` now
  points `Town10HD_Opt` at `/autoware_map/town10-regen`. All three describe
  candidate contents of the ONE path `map_defaults.sh` resolves, and exactly
  one is installed at a time, so the registered invariant is: **the file at
  that path hashes to the `sha256` of exactly one block, and that block is the
  bundle the run used** — never "whichever block is listed last", and never the
  directory name. Completeness: the refit was written in place, so editing the
  original block would have destroyed the only record of the bundle the
  recorded Step-3 and G2 measurements were taken against, while leaving it
  alone would have left the pin describing bytes that no longer exist.
  `town10_pcd_regen` is deliberately NOT reproducible from its pin (its input
  is a live drive); the pin fixes which file a run used plus the parameters
  that shaped it, the same standard `bench_observer_images.local_digest`
  already documents. The invariant now has consumers rather than being prose:
  `benchmarks/scripts/bundle_pin.py`, called by `preflight.sh` (which reports
  `map_bundle_pin` into the manifest and refuses a bundle matching zero or
  several blocks), plus `tests/benchmarks/test_bundle_pin.py`.
- **2026-07-29 — DEVIATION, disclosed** — the committed **Town10 route was
  re-picked**: the goal moved from `(-101.021, 55.014)` at station 438.9 m to
  **`(74.869, 66.891)` at station 258.9 m** of the same polyline
  (`config/routes/Town10HD_Opt.yaml`, and `map_defaults.sh`'s
  `MAP_DEFAULT_GOAL` with it). The reason is infeasibility established
  **before** measurement, not re-tuning of a result: on the rigid bundles the
  ego halted ~292 m along the route at the SAME place on both registrations,
  and on the regenerated bundle it drove the full route but closed only to
  **1.929 m** against the 1.0 m criterion, stopped before Autoware ever
  reported ARRIVED — the final stretch being the one the regenerated bundle
  covers most thinly, its collection drive having ended at ~292 m. On the
  re-picked route G2 measures **0.244 m — PASS**. Both figures are recomputable
  from retained distance series (`benchmarks/evidence/g2-regen-committed-route/`
  and `benchmarks/evidence/g2-regen-repicked-route/`); an earlier revision of
  this entry also cited an NDT-score breach distribution over that drive, which
  was observed live but whose source log lived inside a since-removed container,
  so it is NOT retained and is no longer offered in support. The route was
  produced by `benchmarks/scripts/pick_route.py` and its four gate-honesty
  properties were verified independently: length 258.9 m, accumulated turn
  **169.4°** (≥ 60), straight-line separation **209.0 m** (≥ 100), closest
  prior approach **33.2 m** (≥ 10, computed with the tool's own
  `APPROACH_SKIP_NODES = 15`). The new goal
  sits 1.750 m from the nearest lanelet2 boundary way, matching the old goal's
  1.819 m and the spawn's 1.750 m, i.e. on a centreline. Two knock-on effects
  are recorded rather than absorbed: the station-to-goal gap moves from
  19.772 m to 19.850 m, so the 2026-07-29 goal-window ruling was re-checked
  and **survives unchanged** (the gap is still ~20 m, so a station-trimmed
  goal metric still could not clear 1.0 m); and the confound table's Town10 row
  is updated below. **Known circularity, disclosed:** the re-picked route lies
  inside the corridor the regenerated bundle was built from, so that bundle is
  densest exactly where the route now runs.
- **2026-07-29** — campaign-level finding, recorded here and not only in a task
  report: **G2 completes on NEITHER rigid Town10 registration.** On both
  `town10_pcd_shifted` (142.599 m closest approach) and `town10_pcd_refit`
  (142.398 m) the ego halts ~292 m into the 438.9 m route at the same place —
  two different registrations stopping within 0.2 m of each other.
  **Neither figure is recomputable from this tree, and the evidence status of
  the two differs:** 142.599 m is retained as the gate's own verbatim output
  (`benchmarks/evidence/g2-rigid-committed-route/g2_gate_output.log`, carrying
  the verdict line and `dist_rows=1198` but not the 1198-sample series behind
  it), while **142.398 m is not retained at all** — it came from an ad-hoc
  monitoring loop whose output went only to a session transcript. Both runs
  predate the gate's per-run retention, when a fixed `/tmp/g2_dist.txt` was
  overwritten by the next invocation. An earlier revision of this entry cited
  "the two distance series under `benchmarks/evidence/`" in support; those two
  series are both `town10_pcd_regen` runs and do not evidence the rigid
  bundles at all. The mechanism observed live was `ndt_scan_matcher` scoring
  below its 2.3 acceptance threshold, the EKF then rejecting the pose and MRM
  stopping the vehicle; that chain came from container logs which were not
  retained either, so it too is the observed explanation and not evidence.
  Only the regenerated bundle drives a closed-loop route at all, and THAT is
  fully recomputable (`g2-regen-committed-route/`, 1.929 m;
  `g2-regen-repicked-route/`, 0.244 m). This is why the
  Town10 closed-loop arm depends on `town10_pcd_regen` specifically, and why a
  future full-route Town10 bundle needs a second collection pass over the
  stretch beyond station ~292 m.
- **2026-07-29** — gate evidence for **decision runs** now has a TRACKED home,
  `benchmarks/evidence/<gate>-<slug>/`, written by pointing the gates' existing
  `G1_RUN_DIR` / `G2_RUN_DIR` at it. Unset, both still default to the
  `.gitignore`d `reports/`, so routine runs are unaffected and only deliberate
  promotions are tracked. Completeness: durability was fixed earlier in the day
  (per-run directories instead of overwritten `/tmp` paths) but the _home_ was
  not — `g1_summary.txt`, carrying the `max_err = 0.089 m … PASS` that selects
  `abs_pose_gate_m: 0.5` for every Town10 cell plus the bundle digest it is
  attributable to, existed on one workstation in a path `git clean -fdx` removes
  and no fresh clone has. Promoted: the rung-2 G1 run and both G2 runs (the
  1.929 m committed-route FAIL that justified the route re-pick, and the 0.244 m
  re-picked-route PASS), ~92 KB. `reports/` plus a `.gitignore` negation was
  rejected because that tree is bind-mounted into a root-running container, and
  `benchmarks/results/<cell>/run-<NNN>/` was rejected because those carry
  manifests and are enumerated by `duel_verdict.py`/`sweep_verdict.py` while
  ladder runs have no cell id.
- **2026-07-29** — the map-bundle provenance check (`preflight.sh` check 6) is
  **scoped per bundle directory**, and an unregistered directory SKIPS instead of
  failing. `benchmarks/pins.yaml` gains `nishishinjuku_bundle` so cells C/D have
  registered provenance, and the bundle a cell is checked against is resolved
  from **that cell's own launcher**. Completeness — this fixes two defects in the
  check as first added, one of them blocking:
  - It compared one flat candidate list (the three `town10_pcd_*` blocks)
    against every cell with a map, so cells C/D's `nishishinjuku` bundle matched
    **zero** blocks and preflight FAILED, which would have blocked Task 15 and
    the entire C/D half of the campaign. A provenance check must not stop
    measurement: absence of a registration is a gap in the record, not a
    corrupted bundle. The four outcomes are now distinct — matched (reported),
    unregistered (skip, named), matches-none (FAIL: changed without re-pinning),
    matches-several (FAIL: duplicated registration).
  - It resolved every cell through `scripts/e2e/map_defaults.sh`, which is the
    **extension** path's table, and so recorded `town10_pcd_regen` as cell E's
    bundle while `cells/python-bridge.sh` actually mounts the unshifted
    `~/autoware_map/town10` — a wrong provenance record written into the
    manifest as authoritative, which the B family would have inherited.
    `APPROACH_BUNDLE_DIR` now carries the non-extension mappings, kept in step
    with the launcher by a test that reads its literal.
    No threshold or margin changes; the tier4 cells resolve to nothing and skip,
    because Task 13 owns what they mount.
- **2026-07-29** — registered as a standing rule for this document, after it was
  broken three times in one day: **every quantitative claim in the committed
  record either cites tracked, recomputable evidence, or is explicitly labelled
  as not recomputable — there is no third state.** Tracked evidence lives in
  `benchmarks/evidence/`, whose README carries the rule, a runnable
  recomputation snippet per directory, and a table of the figures that are
  deliberately NOT recomputable. Completeness: the first fix removed one
  unbacked number and the same commit introduced two more — one citing
  `.gitignore`d `reports/`, and one citing two distance series that belong to a
  different bundle and therefore refute the claim they were attached to. Fixing
  instances left the class intact. Promoted in consequence: the ladder's two
  FAIL rungs (0.824 / 0.749 / 0.570 m), the pre-re-pick route (so the confound
  table's superseded row stays checkable), the rigid-bundle G2 gate output, and
  the step-11.6 engage captures. Labelled instead of promoted, because the
  artifacts did not survive: the rigid halt distances, the 8-seed sweep's
  per-seed figures, the withdrawn NDT-score breach distribution, and parts of
  step 11.6. No threshold, margin or route bound changes with this entry.
- **2026-07-30** — `pose_initializer`'s **`stop_check_enabled` is `false` for
  every cell**, via a committed verbatim copy of the pinned image's own
  `pose_initializer.param.yaml` (source sha256
  `a7ed49a2fabad3e46d023969f16b63d3d1ab3d66a555d88f5914f3ef48baeee2`, one line
  changed) bind-mounted read-only in all three cell families. Reason: cell B's
  localization could not initialize at all — `autoware_pose_initializer` refused
  every request with 'The vehicle is not stopped.' because the fork's parked ego
  reports 2.17–2.41 mm/s of lateral velocity and the checker compares the whole
  linear norm. Not a relaxation: Autoware itself ships this value for
  simulation (`simulator.launch.xml:193`/`:211`;
  `pose_twist_estimator.launch.xml:5-6` derives it `false` for
  `logging_simulation`), and the `e2e_simulator` path simply never forwards
  `system_run_mode`. Uniform across cells so it configures the shared
  environment rather than one approach; the 0.0-vs-2.17 mm/s per-approach
  difference it works around STAYS recorded. Verified effective: 221 refusals in
  `results/B/run-004` against **0** in runs 005/008/012. No margin, threshold or
  cell definition changes.
- **2026-07-30** — **`pose_error`'s GT anchor is per-approach**, which is a
  metric-definition amendment and the reason this landed in Task 13 rather than
  its originally-assigned Task 16: it became a blocker on half the primary duel.
  `benchmarks/analysis/gt_anchor.py` registers a body-frame longitudinal offset
  from the CARLA actor origin to where each approach puts `base_link` —
  `extension` **0.0**, `tier4-native` **−1.39706787**, `python-bridge`
  **−1.425**, `calibration` 0.0 — applied rotated by ego yaw at both consuming
  sites (`collect_gt.py`'s `map_pose`, and the tier4 launcher's localization
  seed). Reason: there is no campaign-wide actor-origin→`base_link` transform,
  because each approach DEFINES where `base_link` sits by where it attaches
  sensors; a uniform correction would have broken the approach that is already
  correct (measured: cell A's own G1 series goes 0.089 m → **1.415 m** under the
  tier4 anchor). Not derived from the vehicle model, deliberately — neither
  non-zero offset equals `sample_vehicle`'s 2.79/2. **Strict no-op for cell A,
  proven not asserted:** exact identity over all 399 retained G1 samples, and
  both promoted gates re-derive unchanged (G1 `max_err=0.089 m`, G2
  `closest_approach=0.244 m`). This entry **supersedes and closes the 2026-07-29
  ground-truth frame entry above** — Task 16 no longer owes that correction. The
  E-family 0.03 m `DEFAULT_WHEELBASE` inconsistency it recorded is unchanged and
  still open as a confound. No margin or threshold changes.
- **2026-07-30** — the shared arm sets **`use_emergency_handling=false` on
  `/control/vehicle_cmd_gate`** before engaging, for every cell (`run.sh` step 9
  runs `arm_and_goal.py` on all of them, so it is uniform by construction).
  Reason: with `perception:=false` the diagnostics graph holds
  `/autoware/modes/autonomous` in ERROR and `mrm_handler` operates an
  EMERGENCY_STOP, so the gate MRM-overrides the drive command and nothing arms
  (`results/B/run-008`: 231 × "no mrm operation available", 35 ×
  `modes/autonomous ERROR`). Not a new relaxation: **every promoted gate number
  in this repo already came from MRM off** — `CLAUDE.md`'s "reseed → dummy
  perception → route → MRM off", and `arm_closed_loop.sh` step 5 sets this exact
  parameter — so this makes every bench cell's arm identical to the
  configuration cell A's evidence came from, and the alternative would put an
  asymmetry between the two duel arms. It is also a false positive of the
  already-registered `perception:=false`. The more faithful alternative
  (supplying the availability input perception would have supplied) is recorded
  as rejected-with-reason, to be reconsidered if cell A is ever re-gated. The
  MRM configuration is now recorded per run in `<run>/arm.log`. No margin or
  threshold changes.
- **2026-07-30** — the campaign's **CPU governor is registered as an explicit
  environment parameter**: driver `intel_pstate`, governor **`powersave`**,
  range **0.8–5.4 GHz**, idle sample **2.39 GHz**. Every filed manifest already
  recorded `placement.cpu_governor` (12/12 cell-B runs, 8/8 cell-E) and this
  document never named it. **Owner ruling: keep `powersave` and measure its
  effect rather than argue about it** — it is the distribution default, so it is
  representative of a real deployment, and it is common to all three
  approaches, so it **cannot bias the duel**; it bites only absolute claims such
  as M4's ceiling. Stated precisely because the opposite error is easy:
  `intel_pstate` + `powersave` is a **dynamic** governor, **not** a pin to
  minimum, so the 91% / 18.3-core attribution is **not** measured on
  frequency-crippled cores. The residual concern is narrower and real —
  `powersave` ramps more slowly than `performance` on bursty latency-sensitive
  paths, which is exactly where the AD-API spin timeouts sit — so the M4 ceiling
  claim gains a **third falsifier** (one paired baseline run, `powersave` vs
  `performance`). That run is registered, **not performed**; the owner schedules
  live measurements. No margin, threshold or cell definition changes.
- **2026-07-30 — owner scope decision: the CORE-DUEL SCOPE CUT.** The owner cut
  the campaign to the core duel. `config/cells.yaml` gains a `dropped:` key on
  six cells — `CAL-seam`, `B45`, `D`, `E-opt`, `A-hf`, `B-hf` — and its header
  registers what that key means. **This is a pre-registration amendment and not
  a note, because `CAL-seam` and `B45` were `mandatory: true`.** Both keep
  `mandatory: true`: it is the only thing in the tree that still records that a
  MANDATORY cell was given up, and flipping it to `false` would have made the
  file read as if the two had always been optional — which is false, and is the
  misstatement this entry exists to prevent. (`D` / `E-opt` / `A-hf` / `B-hf`
  were already `mandatory: false`, pre-registered as owner-strikable, so for
  those four the strike genuinely is a note.) **The reason is an owner
  TIME-BUDGET decision, taken on two measurements this record already carries:**
  (1) the DUT stack consumes **91% of 24 cores, ~18.3 for Autoware alone with
  `perception:=false`** ("Host load during a run is unbounded" above), which
  makes the M4 sweep's premise — the harmonized 16-channel baseline sitting
  BELOW the ceiling, heavier classes probing upward — likely **false at its
  starting point**, so the 81-run sweep would largely re-confirm saturation
  while the claim itself is established by cell A's control run; and (2) Task
  16's margin formula consumes **only the duel size**, so the 32-channel and
  128-channel sizes were sweep context and go with the sweep. **What this is
  NOT:** none of the six cells was technically infeasible, blocked, or
  unmeasurable, and none was measured and found wanting. No result about any of
  them may be inferred from the absence of a result. `B45` in particular was
  expected to surface a hard-fork-maintenance result — the campaign is choosing
  not to look, which is a different statement from "it failed". Kept in scope:
  the A-vs-B duel at **n ≥ 10** (deliberately NOT reduced: cutting n widens the
  equivalence CI and risks an inconclusive verdict on the one thing the campaign
  exists for), cells `C` / `E0` / `E`, `CAL-rmw` at the duel size, and a reduced
  M4 ceiling confirmation. The struck entries stay REGISTERED, not deleted, so
  the record of what was given up survives and `analysis/manifest.py` still
  accepts every id on the already-filed runs. **No margin, threshold, tolerance
  or metric definition changes with this entry** — verified, not asserted:
  `config/margins.yaml` is byte-identical (sha256
  `8ef5fdb87b6620ed92a210439ae2ed871f98d9b231697ef523b2f5b3c042d8b7`, unchanged
  in this commit); no metric definition, threshold, tolerance, aggregation rule
  or scoring window is edited — the ONLY change inside `## Metrics` is a status
  note on the recorded Task-14 contradiction, which alters no rule and restates
  the existing one; and the `control_staleness_ms` per-Autoware-image recording
  rule above is deliberately left exactly as written even though `B45` was its
  second image, because narrowing a metric definition to match a scope cut is
  precisely the kind of edit the amendment rule forbids. The losses this cut
  accepts are registered as their own items below rather than folded into this
  one.
- **2026-07-30 — registered loss: `C1(a)` seam overhead is UNMEASURED.** Not
  weakly measured, not partly measured — there is **no evidence at all**. Cell
  `CAL-seam`'s paired seam-vs-in-core one-hop delta was, in
  `scripts/cal_report.py`'s own words, "the only measurement the seam-overhead
  claim rests on", so striking the cell removes the claim's entire evidence
  base. **Every `C1(a)` wording anywhere in the record is downgraded to match**:
  the "Expected branch per cell" block's Task-14 contradiction is now recorded
  as permanently unsettled rather than owed; the `## Known confounds` CAL-seam
  entry withdraws its instruction that "Task 22's confound table must state this
  alongside the CAL-seam numbers", since there will be no CAL-seam numbers, and
  what Task 22 owes instead is the plain statement that C1(a) has no evidence;
  and `cells/calibration.sh`'s refusal, `config/observer_topics/CAL-seam.yaml`'s
  empty list and `config/processes/CAL-seam.yaml`'s missing publisher entry are
  all re-marked as final states rather than pending ones. No margin or threshold
  changes.
- **2026-07-30 — registered loss: the CAL-seam publishers are committed but
  UNEXERCISED, i.e. dead code for this campaign.** Task 14's CODE half landed
  and stays in the tree: `extension/src/publishers/BenchCloudPublisher.{h,cpp}`,
  its `ExtensionInit.cpp` registration and `ext_on_tick` drive,
  `benchmarks/scripts/cal_report.py`, and their tests
  (`extension/test/test_bench_cloud_publisher.cpp`,
  `tests/benchmarks/test_cal_report.py`). **None of it will ever run in a
  measurement**, and its presence must not be read as evidence that the seam was
  measured — so the disclosure is written into the artifacts themselves
  (`BenchCloudPublisher.h`'s header, `cal_report.py`'s docstring, and
  `patches/extension/README.md`'s spec section, whose fork-side twin was never
  written and now will not be) as well as here. **Deliberately NOT deleted**:
  the code is unit-tested and green, it costs a production run nothing (the
  `$CARLA_BENCH_SEAM_CLOUD` gate leaves an unset environment byte-identical to
  today), and a later campaign reviving C1(a) inherits both the instrument and
  the spec. No engine relink and no behaviour change: the edits are comments and
  documentation only.
- **2026-07-30 — registered loss: no hard-fork-maintenance finding (`B45`).**
  This cell existed to measure what it costs to carry the tier4 CARLA fork
  against a **different** Autoware release (`pins.yaml` `autoware_045`,
  `universe-devel-0.45.1`), which is why it was mandatory. It is not measured.
  The pins stay, as the record of which release the finding would have been
  taken against; `pins.yaml`'s `bench-observer:045` note now says that image was
  never built and is not coming, and `config/autoware/pose_initializer.param.yaml`'s
  unverified-for-B45 comparison is re-marked moot rather than owed. **That one
  open prerequisite was a LOGISTICS gap** — the 0.45.1 image is not on this
  workstation — **never a defect of the 0.45 image or of carrying the fork
  across releases**, and nothing in this record may be read as the latter.
- **2026-07-30 — registered loss: no camera-load axis.** The M4 camera-load arm
  is struck **in full**, on every approach: `cells.yaml`'s `camera_classes`
  (cam1/cam3/cam6, 1600×900 @ 20 fps) will not be measured, so there is no
  camera table and no per-approach native-camera-path comparison. The classes
  stay registered, and `runner/spawn.py`'s native camera spawn plus
  `runner/__main__.py`'s `--cameras` / `--camera-*` flags stay committed and
  unexercised by this campaign — the same disclosure as the CAL-seam publishers,
  for the same reason.
- **2026-07-30 — registered loss: no 100 Hz sensitivity cells (`A-hf` /
  `B-hf`).** Both high-frequency cells are struck, as a pair — striking one half
  would have left a one-sided result. This realizes exactly the end state
  `cells.yaml`'s `A-hf` comment already pre-registered ("If the owner strikes
  Task 26 the cell is dropped and these stay null permanently — a legitimate end
  state, not a gap"), so all three rate bindings on both cells are now
  permanently `null`, and the sensor_tick question that comment raised with the
  plan owner (0.1 vs 0.01) is closed as never-to-be-applied rather than
  answered. The `## Metrics` prose explaining why those bindings are `null` is
  left as written, for the metric-definition reason given two entries above.
- **2026-07-30 — registered loss: no cell `D` cross-map tier4 attempt.** Cell
  `D` (tier4-native on Nishi-Shinjuku) is struck, so the tier4 family is
  measured on Town10 only and the cross-map half of the A/B-vs-C/D design is not
  attempted. **Its own open question stays OPEN, not answered:** whether the
  tier4 tree can cook the Nishi-Shinjuku map at all — the condition its
  `arms:` comment makes the cell conditional on — was never tested, so the
  absence of a `D` result says nothing either way. This also means README
  confound C4 (map provenance) keeps only the A/B-vs-C comparison it already
  had.
- **2026-07-30 — the M4 LiDAR-load sweep is reduced to a ceiling confirmation at
  the duel size.** `cells.yaml`'s `sweep_classes` `32ch` and `128ch` are struck
  (comment-marked rather than given a `dropped:` field, because
  `cell_info.merge` copies every non-meta class key into the merged CELL JSON at
  top level, where a class-level `dropped:` would read as if the cell were
  dropped); `vlp16` is the class this campaign measures FIRST, and `CAL-rmw` runs
  at that one size. Reason: ground (1) of the scope cut above — the duel size
  already saturates the host, so the heavier classes would largely re-confirm
  saturation — plus ground (2), that Task 16's margin formula consumes only the
  duel size. Both classes stay registered and `cell_info --class 32ch` still
  resolves, which is what keeps the step-up branch reachable without a config
  change. **BOTH BRANCHES ARE PRE-REGISTERED**, because which applies is decided
  mechanically by the data — the same standing rule that makes `ladder_branch`
  and `abs_pose_gate_m` two keys, and that leaves the `-hf` rate bindings `null`
  rather than guessed. The M4 claim's second registered falsifier is "whether the
  M4 ceiling criterion actually fires at `vlp16`", so: if it **fires**, the
  spec's M4 success criterion (a fired ceiling criterion **or** the 128-ch class)
  is met by its first disjunct, no step-up is needed, and both struck classes stay
  struck — the branch this strike assumes; if it **does not fire**, the claim is
  falsified and the ceiling is unlocated, so **`32ch` is the pre-registered
  step-up** and reinstating it is an **anticipated** amendment rather than a
  novel one, because the branch and its trigger are registered here before any
  P3 run. `128ch` stays struck either way: once the criterion fires at a lower
  class nothing needs it, and if it does not fire at `vlp16` the informative next
  probe is the adjacent class, not the extreme one. **The registered M4 ceiling
  claim above is unchanged**, including its three falsifiers: what is reduced is
  how many runs probe it, not the claim or any threshold. No margin, threshold or
  `sweep_arms` change.
- **2026-07-30** — the `resources.csv` contract above gained **`loadavg_1m`**,
  the host-wide 1-minute load average per M3 sample, with
  `sampler/sample_resources.py` `read_loadavg_1m` writing it and
  `analysis/bench_io.py` `RESOURCE_OPTIONAL_FLOAT_COLS` reading it; its full
  registration, including what it does **not** mean, is the data-contract
  subsection "`loadavg_1m` — in-run host load" above. **Completeness, and the
  gap was named in this document by the entry it closes**: "Host load during a
  run is unbounded, and it changes outcomes" (Task 13) recorded that
  `preflight.sh` gates loadavg only BEFORE a run (abort at ≥ 8) while nothing
  recorded it DURING one, so the confound that plausibly explains cell B's rate
  deficits and its AD-API spin timeouts could not be recorded per run — and it
  stated that adding the series is a sampler-contract change that "would have to
  land before Task 16 to be usable by the P3 analysis". The evidence for
  needing it is measured: `results/B/run-005` peaked at **loadavg 64 on 24
  cores** and lost **three** rclcpp/rmw service responses inside one **0.4 s**
  window, wedging `pose_initializer` for the whole run, while `run-009` stayed
  near 15 and it did not recur; deficits varied between runs of one unchanged
  configuration. **Field 1 (1-minute) is the registered basis**, because
  `preflight.sh` gates on exactly that field — so the in-run series and the
  pre-run gate are directly comparable — and because Task 13's ad hoc sampling
  recorded the same field, so the new series is comparable with the figures
  already in this record. **Backward compatibility is part of the change, not a
  courtesy:** the column is appended LAST so an old header stays a strict
  prefix, `finalize_rtf.py` therefore keeps working on both formats and does not
  "upgrade" a filed run, and absence reads as **NaN** — the campaign's
  convention for undefined, as in `cadence.reconcile_drops`'s
  `observer_loss_rate` and `arm_and_goal.nonzero_longitudinal` — explicitly
  distinguishable from a recorded `0.0` (idle host) and from `-1` (the column
  exists and `/proc/loadavg` was unreadable). Pinned against old-format
  fixtures AND against all ten already-filed `resources.csv` files; **no filed
  run is modified**, so `results/E/` and `results/B/run-007…012` stay
  byte-identical. **This RECORDS the confound; it does not bound it.** Nothing
  here caps load during a run, so the session-discipline rule in that entry
  stands unchanged for every P3 task, and the reflexive hazard is registered
  with it: an agent's own probing contributed to run-005's 64, so observer-side
  work — the sampler that writes this column included — sits inside the
  perturbation it measures. No margin, threshold, metric definition or cell
  definition changes; `config/margins.yaml` is byte-identical.
- **2026-07-30** — `analysis/manifest.py`: `RunManifest` gained
  **`duel_admissible`** (bool, default `false`, type-checked in `validate()`),
  `scripts/duel_verdict.py` now **drops** runs that are not duel-admissible and
  reports the count on its own term, `scripts/write_manifest.py` gained
  `--duel`, `run.sh` gained `--duel`, and `scripts/duel.sh` passes `--duel` on
  **every** run it orders. **Completeness, and the gap is exact:**
  `duel_verdict.py`'s aggregation reduced _every non-excluded run in a cell_ to
  one run-level scalar and fed it to the equivalence test, so a **successful**
  bring-up or gate run filed under `results/A/` would silently have become
  primary duel data. Task 18's design requires **interleaved** A,B,A,B pairs
  precisely to control for within-session drift (`scripts/duel.sh`'s own
  rationale), so a standalone gate run is not part of an interleaved pair and
  cannot legitimately contribute to the verdict — and nothing in the manifest
  let the tool tell the two apart. Task 15b is the first task to file a cell-A
  `run.sh` run at all, which is why the gap surfaces now.
  **Why a manifest field and not an exclusion reason.** An exclusion asserts the
  run's data is _invalid_; a cell-A gate run's data is valid and is the
  campaign's missing control. Filing it as excluded would (a) misstate it,
  (b) make `report.py` tag good evidence `(EXCLUDED)`, (c) require an
  eleventh criterion in `config/exclusions.md`, whose own closing sentence
  freezes that list, and (d) suppress the M5 gate on it — `write_quality`
  refuses an already-excluded manifest, so the very verdict Steps 1–2 of that
  task exist to obtain would not be written. So `config/exclusions.md` is
  **byte-identical**, and `excluded` / `duel_admissible` stay two fields
  answering two questions — the same shape of argument `cells.yaml` already
  makes for `ladder_branch` / `abs_pose_gate_m` and for `mandatory:` /
  `dropped:`. `_walk_cell_runs` tests `excluded` **first**, so a run that is
  both keeps the actionable pre-registered reason.
  **Why the default is `false` (fail-closed).** The two directions fail very
  differently: defaulting `true` makes a forgotten declaration _silently_
  contaminate the headline verdict — the defect being closed — while defaulting
  `false` surfaces as the already-implemented **UNDER-N / insufficient-data**
  row with the drop count in its notes. The duel path cannot forget it, because
  `duel.sh` — the only caller that _knows_ a run is part of an interleaved pair,
  interleaving being its entire job — declares it unconditionally, so **Task 18
  needs no new operator step**. `sweep_verdict.py` is deliberately untouched: it
  filters on `arm ∈ sweep_arms`, so a `static` / `closed-loop` gate run is
  already out of its scope (skipped and counted), and making the M4 sweep
  require duel admissibility would wrongly drop every legitimate sweep run.
  `report.py` is untouched too: it renders per-run descriptions with no
  aggregation and no verdict, so a gate run appearing there is the intended
  evidence, not contamination.
  **Backward compatibility is part of the change.** Every manifest already in
  `benchmarks/results/` predates the field, loads via the dataclass default, and
  reads as **not** duel data — which is both true of them and the safe
  direction — so **no filed run is modified** and `results/E/` and
  `results/B/run-001…012` stay byte-identical. The bool is type-checked because
  the string `"false"` is truthy, so a hand-edited manifest must not be able to
  declare itself duel data by accident. Pinned by tests that fail when the
  filter, the type check, or `duel.sh`'s `--duel` is neutralised — each of the
  three neutralised in turn against the whole suite, failing only its own pins.
  No margin, threshold, tolerance, metric definition or cell definition
  changes; `config/margins.yaml` and `config/exclusions.md` are byte-identical.
- **2026-07-30** — the **M4 registered claim's falsifiers 1 and 2 are recorded as
  ANSWERED, and the claim itself as FALSIFIED**, in "Registered claim (Task 13)"
  above; the `⚠` attribution box beside cell B's gate result is updated with the
  control that now exists; and the three findings cell A's control produced are
  registered in "Cell A's bench-harness control (Task 15b)". **Completeness, and
  this is the gap that mattered most:** `results/A/run-001` and `run-002` answer
  **both** registered falsifiers, but the tracked record still read "Cell A has
  never run through this harness … the question is open" and "the ceiling test has
  never been evaluated", while the falsification existed only in a **git-excluded**
  `.superpowers/` report. That inverts two of this campaign's core conventions at
  once — refuted hypotheses stay in the record _with the diagnostics that refuted
  them_, and a claim that cannot be re-derived from tracked evidence is a defect —
  so the strongest thing the control measured was the least visible thing in the
  repo. Per item: **falsifier 1** is answered by cell A's Autoware averaging
  ~2.09 cores against cell B's ~18.33 with `carla-server` matched to within 6.7%,
  which refutes the "this environment is saturated" branch and leaves Task 13's
  load figure standing as a finding about **cell B**; the **image** confound
  (`universe-devel` vs `universe-devel-cuda`) is stated as the part still
  unseparated, with Task 18's n ≥ 10 M3 measurement named as where it gets error
  bars. **Falsifier 2** is answered by `evaluate_ceiling` returning
  `reached=False, reasons=[]` on both arms with all four disjuncts' inputs
  tabulated, recorded as a **falsification** rather than dropped, together with
  the measured fact that the rig was ~639 000 pts/s (~2.2× `vlp16`) rather than
  the registered baseline class — which makes the result more robust under load
  monotonicity, stated as an assumption — and with the `32ch` step-up flagged as
  needing a **decision** on an already-anticipated amendment, not a new one.
  **The three findings** are the static-arm teardown-ordering gap that fabricates
  a ~2% `publisher_drop_rate` (which Task 18 inherits on all ten static pairs),
  the A-side instrument-asymmetry bound (`observer_loss_rate` 0.0000 against cell
  B's 0.2564 / 0.1715, against a 0.02 margin on `achieved_rate_ratio`), and a
  **refuted** 0.95 s stamp-domain hypothesis kept with the three diagnostics that
  killed it. One correction rides along: the "extra concat-relay node" was never a
  cell-B-only difference and must not be listed as an A-vs-B asymmetry. No margin,
  threshold, tolerance, metric definition or cell definition changes; no filed run
  is modified; `config/margins.yaml` and `config/exclusions.md` are byte-identical.
- **2026-07-30** — `run.sh` gained **`--check-args`** (resolve the invocation,
  print it as KEY=VALUE, exit before preflight — no host state touched, nothing
  booted, nothing written under `results/`). **Completeness, against a campaign
  rule the owner made binding on this date: a substring or text-scan assertion is
  NOT a pin.** The fail-closed `duel_admissible` default was pinned only by tests
  scanning `run.sh`'s and `duel.sh`'s source text, and inserting `DUEL=1` after
  `run.sh`'s parse loop flips the default **on** with the whole suite green — the
  **sixth** instance of that defect class in this campaign, this time in the guard
  protecting the primary duel from contamination. `--dry-run` cannot serve as the
  test vehicle because it deliberately runs preflight (host load, engine BuildId)
  and so cannot execute without the CARLA trees. The behavioural pins now drive
  the real parser, and one drives the whole `duel.sh` → `run.sh` chain end to end;
  the text scans are kept, relabelled as secondary signals with their limitation
  stated. Verified by re-running the post-parse insertion: the behavioural pin
  fails, the text scans still pass. No measurement, metric, margin or cell
  definition changes.

### Cell A's bench-harness control (Task 15b): three findings the duel inherits

**Added 2026-07-30 (Task 15b), before any P3 run.** All three come from
`results/A/run-001` / `run-002` and are re-derivable from those committed series.
The falsifier answers themselves are in "Registered claim (Task 13)" above.

#### 1. The static arm's windowed M2 reconciliation charges a teardown-ordering gap to the publisher

`duel_verdict._reconcile_run` reports **`publisher_drop_rate = 0.0213` on a
publisher that dropped nothing** (`results/A/run-001`, static). The mechanism is
exact and is a harness property, not an approach property:

- `window.static_window` sets the window's upper bound to `clock_wall.max()` —
  the run's **last** `/clock` sample.
- `scripts/teardown.sh` stops the GT collector (which writes
  `publisher_counts.json`) **before** it SIGINTs the observer (which writes
  `clock.csv` and `observer.csv`). So the publisher series ends first.

| run     | window top | publisher series end | gap          | scans at 20 Hz | in-window deficit  |
| ------- | ---------- | -------------------- | ------------ | -------------- | ------------------ |
| run-001 | 86.442 s   | 85.391 s             | **+1.051 s** | **21**         | 984 − 963 = **21** |
| run-002 | 93.099 s   | 172.999 s            | −79.900 s    | 0              | 0                  |

The predicted 21 equals the observed 21. **The closed-loop arm is immune**
(`spatial_window` closes where the ego leaves the station band, ~80 s before the
run ends: `run-002` reports 0.0000). `sweep_verdict._publisher_rate_ratio` is
immune on both arms because it uses whole-run counts (0.9993 / 1.0000).

**Task 18 inherits this on all ten static pairs, for cell A and cell B alike.**
It is a fabricated non-zero publisher drop in the M2 reconciliation table, not a
duel-margin metric, and being common to both cells it should barely move the
A-vs-B delta. **Not fixed here** — it is a change to a pre-registered metric's
companion output and the owner schedules it. Two candidate fixes, recorded with
their costs: end the static window at `min(clock_wall.max(), publisher_end)`, or
reverse the two teardown stops — the latter is smaller but moves flush ordering,
which `run.sh` step 6's `exec` comment says was already paid for once.

#### 2. The A-side instrument-asymmetry bound: cell A loses NOTHING where cell B loses 17–26%

`cadence.reconcile_drops` over each run's own registered scoring window, on
`/sensing/lidar/top/pointcloud_raw_ex` at the registered `lidar_expected_hz`:

| run                     | expected | published | observed | `publisher_drop_rate` | `observer_loss_rate` |
| ----------------------- | -------- | --------- | -------- | --------------------- | -------------------- |
| A `run-001` static      | 984      | 963       | 983      | 0.0213 (finding 1)    | **0.0000**           |
| A `run-002` closed-loop | 1041     | 1041      | 1042     | 0.0000                | **0.0000**           |
| B (Task 13)             | —        | —         | —        | 0.0000                | **0.2564 / 0.1715**  |

In-window observed rate on both cell-A runs: **20.0000 Hz** against a 20.0 Hz
target. **So every observer-derived wire metric is biased downward for cell B and
not at all for cell A, inside the primary duel.** Three of the five duel margin
metrics are observer-derived (`one_hop_wall_ms`, `lidar_to_ndt_sim_ms`,
`achieved_rate_ratio`), and `achieved_rate_ratio`'s margin is **0.02** — an order
of magnitude below cell B's 0.17–0.26 loss.

This is the confound Task 9 registered in exactly this spot, now bounded from the
A side, and it adds a third independent leg to the existing two: the loss is not
observer miscounting (Autoware's own PublishedTime saw 8.47 Hz against the
observer's 8.53) and not observer-caused (Task 9's matrix measured
10.006/10.071/10.070 Hz on the same transport). Cell A's **0.0000** on a
_different_ transport shows the instrument is capable of losing nothing, so the
loss is a property of cell B's SHM-off Fast-DDS transport. The per-process CPU
agrees: cell A's `observer` averages **2.8%** against cell B's **22.7%**.

#### 3. REFUTED: the apparent 0.95 s stamp-domain offset between the publisher and observer clocks

Kept with the diagnostics that refuted it, per this file's own convention.
`run-001`'s 0.0213 first looked like a stamp-domain defect: comparing the two
series **sorted-elementwise** gave a constant **−0.9500 s** (19 ticks at 20 Hz)
between `publisher_counts.json`'s `sim_stamps_ns` and `observer.csv`'s
`header_stamp_ns`, and the same 0.95 s appeared against `gt.csv`'s `sim_ns` — the
column `analysis/quality.py` joins to the NDT pose within a **25 ms** tolerance.
That would have been serious, and it is the one check
`collect_gt.lidar_stamp_recorder`'s docstring says only a live run can make:
"On the first real counting run they must match to within one message period".

**It is not a stamp-domain offset, and that check PASSES.** The elementwise
comparison was invalid — it pairs `sorted[i]` with `sorted[i]` across two series
whose _coverage intervals_ differ by 19 samples (finding 1), which manufactures a
constant offset out of a pure index shift. Three diagnostics refute it:

- The two series **overlap on one clock**: publisher `[16.341, 85.391]`, observer
  `[17.291, 86.391]`, and **681 of 1382** stamps are bit-identical, the rest
  differing by sub-tick jitter — not a rigid 0.95 s shift.
- `run-002` reports `publisher_drop_rate = 0.0000` with in-window counts matching
  to one message. A stamp-domain offset would be systematic across arms.
- `run-002`'s M5 join succeeded on a **moving** ego at `pose_err_max = 0.264 m`. A
  real 0.95 s label error would have injected ~0.95 s × speed, i.e. metres, and
  the absolute gate would have failed.

## How to run

`benchmarks/run.sh` is the single measurement entry point. One invocation
produces one `benchmarks/results/<cell>/run-<NNN>/`:

```bash
bash benchmarks/run.sh A --arm closed-loop            # one run of cell A
bash benchmarks/run.sh A --arm closed-loop --dry-run  # print the 15 steps
bash benchmarks/scripts/duel.sh A B --arm closed-loop --pairs 10
```

`--dry-run` resolves the cell, runs preflight read-only (`--no-clean`),
writes and validates the manifest into a scratch directory, runs the cell
launcher's `plan` (prerequisite checks only), and prints every command it
would run — without touching `benchmarks/results/` or booting anything.

Flags: `--class <sweep-or-camera-class>`, `--unpaced`, `--runs N`,
`--no-observer` (records `/clock` only), `--rpc-port N`, `--rmw`, `--shm`,
`--dds-profile`, `--duel`, `--check-args`.

`--check-args` resolves the invocation (cell, approach, arm, transport triple,
duel declaration, next run directory), prints it as `KEY=VALUE` and exits
**before** preflight — so unlike `--dry-run` it touches no host state at all and
runs anywhere. It is what lets a test pin the fail-closed `duel_admissible`
default by running the real parser instead of scanning this script's text.

`--duel` declares the run **primary-duel data** (`manifest.json`'s
`duel_admissible`). `duel.sh` passes it on every run it orders, so the duel
needs no extra flag; a bring-up or gate run made with a bare `run.sh` is
**not** duel data and `duel_verdict.py` drops it and says so — see the
`duel_admissible` amendment above for why the default points that way.

The analysis modules live in `benchmarks/analysis/` (manifest schema,
clock fit, CSV loading, cadence, latency, stats/margins, ceiling
evaluation, spatial window, M5 quality). The entry point for rendering a
per-cell report is `python3 -m benchmarks.report <results_dir>`; `run.sh`
runs it as its own last step, so a run directory that does not render is a
loud failure rather than a silent one.
