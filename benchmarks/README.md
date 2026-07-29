# benchmarks

## Purpose

This directory holds the reproducible measurement harness for the
three-approach CARLA↔Autoware integration evaluation described in the
project's design spec, "Three-Approach CARLA↔Autoware Integration
Evaluation Design". It exists to turn that spec's claims (C1–C3) into
pre-registered, regenerable evidence rather than one-off numbers.

## Data contract

A future `bench_observer` must emit the following files for every run:

| File                 | Columns / schema                                                                                                    | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `observer.csv`       | `topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes`                                     | `clock_ns` is the latest `/clock` value seen at arrival; `-1` before the first clock is received.                                                                                                                                                                                                                                                                                                                                       |
| `clock.csv`          | `clock_ns,arrival_system_ns`                                                                                        | One row per `/clock` receipt.                                                                                                                                                                                                                                                                                                                                                                                                           |
| `published_time.csv` | `topic,source_header_ns,published_ns`                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `resources.csv`      | `sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf`                                            | One row per process per sample. `gpu_util_pct`/`vram_bytes` are `-1` for a process with no GPU context. `rtf` is the sim/wall rate at that instant (`-1` before the first `/clock`) and repeats across the processes sharing a `sample_system_ns`; it is the per-sample series `evaluate_ceiling` consumes.                                                                                                                             |
| `odometry.csv`       | `topic,header_stamp_ns,x_m,y_m`                                                                                     | One row per `/localization/kinematic_state` receipt, written by bench_observer's typed subscription. That same receipt also emits a row to `observer.csv` with `size_bytes = 0` — a typed (deserialized) subscription has no serialized-size handle, unlike the generic subscriptions used for pointcloud/camera topics. M2/M4 byte metrics only ever read those generic-kind topics, so the sentinel is never consumed as a real size. |
| `gt.csv`             | `arrival_system_ns,sim_ns,x_m,y_m,z_m,yaw_rad`                                                                      | One row per CARLA world tick, written by `benchmarks/scripts/collect_gt.py`, the M5 ground-truth source.                                                                                                                                                                                                                                                                                                                                |
| `publisher_counts.json` | `{"schema": "publisher_counts/2", "topics": {<topic>: {"count": n, "sim_stamps_ns": [...]}}}`                     | The M2 reconciliation's publisher-side term, written by `collect_gt.py --count-lidar` and read through `analysis/publisher_counts.py`. One SIM stamp per published message (`gt.csv`'s `sim_ns` domain and rounding), so the count can be windowed to the run's scoring window exactly as the expected and observed counts are. ABSENT by design on the python-bridge cells, where the bridge's own `sensor.listen` callback is the publish path — see "Reconciliation window and scope" below.                                                                                                     |
| `manifest.json`      | the `RunManifest` schema implemented in `benchmarks/analysis/manifest.py`                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `quality.json`       | `dataclasses.asdict(analysis.quality.QualityStats)` plus `arm`, `window_sim_ns`, `ladder_branch`, `expected_ndt_hz` | The M5 gate's recorded verdict for the run; `gate_pass` is the single field a consumer may treat as that verdict. See "M5 gate result (`quality.json`)" below. NO WRITER EXISTS YET — the task that lands the M5 gate step writes it.                                                                                                                                                                                                   |

Results are laid out on disk as:

```text
benchmarks/results/<cell>/run-<NNN>/{manifest.json,observer.csv,clock.csv,published_time.csv,resources.csv,odometry.csv,gt.csv,publisher_counts.json,quality.json}
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
`lidar_expected_hz`, `ndt_expected_hz`), read with
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
> path (step 10), and routes step 14 to `report.py`'s fit-strict renderer. But
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
tick_hz)`. It is registered only where committed code fixes it today (the
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
`ndt_rate_ratio`, `gate_pass` (bool), `reasons` (list of str) — plus four
provenance keys the gate definition above requires to be interpretable:
`arm`, `window_sim_ns` (`[lo, hi]`), `ladder_branch` (`"absolute"` |
`"relative"`, the G1 branch that applied) and `expected_ndt_hz`.

`expected_ndt_hz` is written from the cell's `metrics.ndt_expected_hz` binding
and nothing else — it is `evaluate_quality`'s divisor for the "NDT rate ≥ 90%
of expected" criterion, and taking it from `tick_hz` would fail every A-hf run
by a factor of five while looking like a localization result. A cell whose
`ndt_expected_hz` is `null` cannot be gated: the M5 gate must refuse to write
a verdict for it rather than assume a rate.

`gate_pass` is the single field a consumer may treat as the verdict.

No writer exists yet: `run.sh`'s `gate:arm-failed` is the bring-up arm check
(`injector/arm_and_goal.py`), not this gate. The task that lands the M5 gate
step writes exactly this file. Until then a consumer must fail loudly on its
absence for any arm that closes the loop, rather than defaulting it to a pass.

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
