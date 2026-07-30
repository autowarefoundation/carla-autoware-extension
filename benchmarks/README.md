# benchmarks

## Purpose

This directory holds the reproducible measurement harness for the
three-approach CARLA↔Autoware integration evaluation described in the
project's design spec, "Three-Approach CARLA↔Autoware Integration
Evaluation Design". It exists to turn that spec's claims (C1–C3) into
pre-registered, regenerable evidence rather than one-off numbers.

## Data contract

A future `bench_observer` must emit the following files for every run:

| File                    | Columns / schema                                                                                                                          | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `observer.csv`          | `topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes`                                                           | `clock_ns` is the latest `/clock` value seen at arrival; `-1` before the first clock is received.                                                                                                                                                                                                                                                                                                                                                                                               |
| `clock.csv`             | `clock_ns,arrival_system_ns`                                                                                                              | One row per `/clock` receipt.                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `published_time.csv`    | `topic,source_header_ns,published_ns`                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `resources.csv`         | `sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf`                                                                  | One row per process per sample. `gpu_util_pct`/`vram_bytes` are `-1` for a process with no GPU context. `rtf` is the sim/wall rate at that instant (`-1` before the first `/clock`) and repeats across the processes sharing a `sample_system_ns`; it is the per-sample series `evaluate_ceiling` consumes.                                                                                                                                                                                     |
| `odometry.csv`          | `topic,header_stamp_ns,x_m,y_m`                                                                                                           | One row per `/localization/kinematic_state` receipt, written by bench_observer's typed subscription. That same receipt also emits a row to `observer.csv` with `size_bytes = 0` — a typed (deserialized) subscription has no serialized-size handle, unlike the generic subscriptions used for pointcloud/camera topics. M2/M4 byte metrics only ever read those generic-kind topics, so the sentinel is never consumed as a real size.                                                         |
| `pose.csv`              | `topic,header_stamp_ns,x_m,y_m`                                                                                                           | One row per NDT pose receipt (the cell's registered `ndt_topic`), written by bench_observer's typed `pose` subscription, with the same `size_bytes = 0` sentinel row in `observer.csv` as `odometry.csv`. A SEPARATE file from `odometry.csv` even though the schema is identical: that one carries the EKF-fused `/localization/kinematic_state`, a different quantity, and M5's `pose_error_m` is defined on the NDT pose alone. Read with `analysis/bench_io.py` `read_pose_csv`.            |
| `tf.csv`                | `topic,frame_id,child_frame_id,header_stamp_ns`                                                                                           | One row per `/tf` transform whose `child_frame_id` matches the one registered in that cell's topic list (kind `tf`, whose fourth spec field is that frame), written by bench_observer's typed `tf` subscription with the same `size_bytes = 0` sentinel row in `observer.csv`. The parent `frame_id` is recorded but NOT filtered on, so a map→base_link claim is verified rather than assumed. Read with `read_tf_csv`.                                                                        |
| `gt.csv`                | `arrival_system_ns,sim_ns,x_m,y_m,z_m,yaw_rad`                                                                                            | One row per CARLA world tick, written by `benchmarks/scripts/collect_gt.py`, the M5 ground-truth source.                                                                                                                                                                                                                                                                                                                                                                                        |
| `publisher_counts.json` | `{"schema": "publisher_counts/2", "topics": {<topic>: {"count": n, "sim_stamps_ns": [...]}}}`                                             | The M2 reconciliation's publisher-side term, written by `collect_gt.py --count-lidar` and read through `analysis/publisher_counts.py`. One SIM stamp per published message (`gt.csv`'s `sim_ns` domain and rounding), so the count can be windowed to the run's scoring window exactly as the expected and observed counts are. ABSENT by design on the python-bridge cells, where the bridge's own `sensor.listen` callback is the publish path — see "Reconciliation window and scope" below. |
| `manifest.json`         | the `RunManifest` schema implemented in `benchmarks/analysis/manifest.py`                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `quality.json`          | `dataclasses.asdict(analysis.quality.QualityStats)` plus `arm`, `window_sim_ns`, `goal_window_sim_ns`, `ladder_branch`, `expected_ndt_hz` | The M5 gate's recorded verdict for the run; `gate_pass` is the single field a consumer may treat as that verdict. See "M5 gate result (`quality.json`)" below. Written by `benchmarks/scripts/write_quality.py`, run as `run.sh` step 13. ABSENT when the gate REFUSED to score the run (an unselected G1 ladder branch, a null `ndt_expected_hz`, a missing input): absence means not scored, never a pass.                                                                                    |

Results are laid out on disk as:

```text
benchmarks/results/<cell>/run-<NNN>/{manifest.json,observer.csv,clock.csv,published_time.csv,resources.csv,odometry.csv,pose.csv,tf.csv,gt.csv,publisher_counts.json,quality.json}
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
bindings on both cells are `null` until Task 26 registers what it applied.
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

> **Open contradiction in committed code, owed to Task 14 before any CAL-seam
> run.** `cells.yaml` gives `CAL-seam` `carla: 0.10-fork`, so
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
Task 16 owes one of the two: offset `gt.csv` to `base_link` before computing
`pose_error`, or state this offset beside every `pose_error` number. What it must
NOT do is read ~1.4 m of constant offset as approach-dependent accuracy, which is
exactly what the raw comparison invites.

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
   this workstation — so Task 21 owes the same comparison before it files a B45
   run.
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
B45, D and the E family unmeasured.** Task 13 (cell B's closed-loop gate) and
Task 15 (cell C's re-gate) must record their own `change_to_autonomous` outcome
here, in this same form: which cell, refused or succeeded. `arm_and_goal.py` logs
`change_to_autonomous: SUCCEEDED` or `did not succeed` to its own stdout/stderr
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
  `results/E/run-006` — sits in every cell's M5 `pose_error`. Task 16 owes
  either the correction or the offset stated beside every number.
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
`--dds-profile`.

The analysis modules live in `benchmarks/analysis/` (manifest schema,
clock fit, CSV loading, cadence, latency, stats/margins, ceiling
evaluation, spatial window, M5 quality). The entry point for rendering a
per-cell report is `python3 -m benchmarks.report <results_dir>`; `run.sh`
runs it as its own last step, so a run directory that does not render is a
loud failure rather than a silent one.
