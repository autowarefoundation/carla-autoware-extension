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
| `manifest.json`      | the `RunManifest` schema implemented in `benchmarks/analysis/manifest.py`                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `quality.json`       | `dataclasses.asdict(analysis.quality.QualityStats)` plus `arm`, `window_sim_ns`, `ladder_branch`, `expected_ndt_hz` | The M5 gate's recorded verdict for the run; `gate_pass` is the single field a consumer may treat as that verdict. See "M5 gate result (`quality.json`)" below. NO WRITER EXISTS YET — the task that lands the M5 gate step writes it.                                                                                                                                                                                                   |

Results are laid out on disk as:

```text
benchmarks/results/<cell>/run-<NNN>/{manifest.json,observer.csv,clock.csv,published_time.csv,resources.csv,odometry.csv,gt.csv,quality.json}
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

**Per-cell bindings.** No tool may hardcode a topic, a process label or a
rate. Each cell's entry in `benchmarks/config/cells.yaml` carries a `metrics:`
block (`lidar_topic`, `ndt_topic`, `control_topic`,
`control_published_time_topic`, `cpu_process_label`, `tick_hz`,
`lidar_expected_hz`), read with
`benchmarks.scripts.cell_info.metrics_for(load_cells_doc(), <cell>)`. A `null`
binding is not a default to fill in at analysis time: the value is not
pre-registered yet, so the metric is UNAVAILABLE for that cell and the tool
must report it as such. `cells.yaml` names the task that owes each `null`.

`tick_hz` (paced world tick, `1 / fixed_delta_seconds`) and
`lidar_expected_hz` (sensor publish target) are different numbers. They
coincide at 20.0 on most cells and diverge on the high-frequency cells
(`A-hf`/`B-hf`: `tick_hz: 100.0`, `lidar_expected_hz: 20.0`, because
`--fixed-delta` moves the world tick and not the rig's `sensor_tick`). An
expected message COUNT must be derived from `lidar_expected_hz`; only the M4
ceiling's unpaced `tick_rate_ratio` disjunct divides by `tick_hz`.

**Scoring window.** All five are computed over the run's registered scoring
window (see "Scoring windows" above), resolved once per run:

- closed-loop arm: `analysis/window.py` `spatial_window` over `odometry.csv`'s
  `/localization/kinematic_state` rows against the polyline and
  `stations.start_m`/`end_m` of `config/routes/<map>.yaml`, warm-up
  `20e9` ns — bounds are SIM ns.
- every other arm (`static`, `paced`, `unpaced`, `ablation`):
  `static_window(t0, end, 20e9)` over `clock.csv`'s `arrival_system_ns` —
  bounds are WALL ns.
- The other domain's bounds come from the run's own affine clock fit
  (`analysis/clockfit.py` `fit_sim_wall_affine` over `clock.csv`): sim → wall
  by `sim_to_wall`, wall → sim by its exact inverse
  `(wall_ns - fit.intercept_ns) / fit.slope`.
- Rows are filtered on the column native to their file: `observer.csv` on
  `header_stamp_ns` (sim), `published_time.csv` on `source_header_ns` (sim),
  `resources.csv` on `sample_system_ns` (wall).

Windowing is not optional for these five. The 20 s warm-up covers map load,
NDT convergence and stack settling, which A and B do differently; against a
2.0 ms margin on `one_hop_wall_ms` a whole-run median is dominated by it.

**Aggregation (all five).** Per run: the MEDIAN of the in-window per-message
(or per-sample) series — one run-level scalar per run. Across runs:
`analysis/stats.py` `bootstrap_ci_median_diff` + `equivalence_decision` on the
two cells' run-level scalars, `delta = median(A) - median(B)`, lower better.
Messages are never pooled across runs. Excluded runs never contribute.

#### `one_hop_wall_ms` — transport (margin 2.0)

`analysis/latency.py` `one_hop_wall_ms(header_stamp_ns, arrival_system_ns,
fit)` over `observer.csv` rows for the cell's `lidar_topic`: observer arrival
wall time minus the wall time the run's clock fit maps that message's own sim
header stamp to. Single topic, so no join. This is the same quantity
`report.py` `summarize_run` already reports per topic as `one_hop_p50_ms`,
reduced to the one topic the margin is registered against.

Relation to `scripts/cal_report.py`: the SAME measurand, a DIFFERENT code
path, deliberately. CAL cells publish wall-`now()` header stamps and have no
`/clock` at all, so `cal_report._one_hop_ms` takes the direct
`arrival_system_ns - header_stamp_ns` and no fit is possible; a simulated
cell's stamps are sim-domain, so the fit is required. The duel term therefore
carries the fit's error on top of the transport it measures, and a duel row
must be read next to that run's `fit_residual_ns` (`report.summarize_run`).
Task 16 freezes this margin from CAL-rmw, i.e. from the `cal_report` path:
that transfer is legitimate because the measurand is identical, not because
the arithmetic is.

#### `lidar_to_ndt_sim_ms` — pipeline (margin 5.0)

LiDAR emission to NDT pose output, in SIMULATED milliseconds.

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
in ms — but only when both stamps are in the same clock domain. Which they are
is an empirical property of the pinned Autoware image (`published_stamp` may
be taken from the node's sim clock or from a default system clock) and must be
RECORDED by Tasks 13/20 alongside the topic name, not assumed. Both branches
are pre-registered here so the choice cannot be made after seeing the number:

- (a) `published_stamp` in the SIM domain →
  `staleness_ms(source_header_ns, published_ns)`.
- (b) `published_stamp` in the WALL domain →
  `one_hop_wall_ms(source_header_ns, published_ns, fit)`, the publisher-side
  analogue of the transport term.

The discriminator is mechanical and unambiguous: a wall stamp is a Unix epoch
(> 1e18 ns); a sim stamp is a run-length offset (< 1e13 ns for any window this
harness records).

Known limitation, recorded rather than worked around: under branch (a) both
stamps come from the sim clock, whose resolution is the `/clock` period
(50 ms at `tick_hz: 20.0`), so the metric can only resolve whole-tick
staleness against a 10.0 ms margin. Whether to keep the margin, re-scope the
metric, or drop it from the duel is an owner decision that this amendment
deliberately does not make; the margin is left at its pre-registered value.

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
lidar_expected_hz`.

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
  rate, and none of the three was machine-readable anywhere — so tools
  hardcoded them (a `"carla"` process label that matches no row, a
  `/lidar` topic that exists on no cell, a tick target used as a message
  -count target on the high-frequency cells).
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
