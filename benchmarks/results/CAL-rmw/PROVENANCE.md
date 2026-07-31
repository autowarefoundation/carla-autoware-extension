# CAL-rmw calibration matrix — provenance (Task 16, 2026-07-30)

What the fifteen `run-*` directories beside this file are, how they were
produced, and what they do and do not establish. The runs themselves are
committed **as produced**; nothing here was regenerated, re-run or edited.

## What was run

Three transport configurations × the **duel message size only** × n = 5,
`--arm static` (60 s window), all on one host, back to back, 19:06–19:26
local time on 2026-07-30.

| transport     | invocation                                              | resolved transport                                             |
| ------------- | ------------------------------------------------------- | -------------------------------------------------------------- |
| `cyclonedds`  | `run.sh CAL-rmw --arm static --rmw rmw_cyclonedds_cpp`  | `rmw_cyclonedds_cpp`, shm off, `docker/cyclonedds.xml`         |
| `fastdds-shm` | `… --rmw rmw_fastrtps_cpp --shm on`                     | `rmw_fastrtps_cpp`, shm on, no profile (Fast DDS defaults)     |
| `fastdds-udp` | `… --rmw rmw_fastrtps_cpp --shm off`                    | `rmw_fastrtps_cpp`, shm off, `observer/config/udp_only.xml`    |

The `--shm`/profile pairing is resolved by `benchmarks/run.sh:128-155`, and
each run's `manifest.json` `transport` block records the resolved triple with
the profile's sha256 — `1eeef31e…2865` for `docker/cyclonedds.xml`, `9886f744…
5098` for `benchmarks/observer/config/udp_only.xml`, and an empty digest for
the profile-less SHM arm.

**Message size and rate are the launcher defaults and nothing overrode them.**
28 800 points × 32 B = **921 600 B/msg at 10 Hz** —
`benchmarks/cells/calibration.sh:76-79`, whose values are in turn
`bench_pub.cpp:15-17`'s own declared defaults. `BENCH_PUB_RATE_HZ`,
`BENCH_PUB_POINTS` and `BENCH_PUB_POINT_STEP` were **never set**, so
`config/cells.yaml:525`'s `lidar_expected_hz: 10.0` binding — which that file's
own comment says a rate override would invalidate — remains valid, and the
`rate` column below is a real `achieved_rate_ratio`.

### Run order: INTERLEAVED, five rounds of three

| round | cyclonedds | fastdds-shm | fastdds-udp |
| ----- | ---------- | ----------- | ----------- |
| 1     | `run-001`  | `run-002`   | `run-003`   |
| 2     | `run-004`  | `run-005`   | `run-006`   |
| 3     | `run-007`  | `run-008`   | `run-009`   |
| 4     | `run-010`  | `run-011`   | `run-012`   |
| 5     | `run-013`  | `run-014`   | `run-015`   |

**This is a deliberate deviation from Task 16's brief, and it changes nothing
the brief pre-registers.** The brief specifies the matrix (3 × n = 5 at the
duel size), the metric, the aggregation and the margin formula; it does not
specify run ORDER. The frozen quantity is a DIFFERENCE between two transports,
so running each transport as a contiguous block would have put ~20 minutes of
possible host drift between the cyclonedds and fastdds-udp arms and charged it
to the delta. Interleaving is also the campaign's own established practice for
a between-arm comparison (the primary duel is pre-registered as interleaved for
exactly this reason). The transport of every run is recorded in its own
manifest, so attribution is exact regardless of order.

## Host quiescence — this cell's dominant validity risk

Transport latency is load-sensitive in a way pose accuracy is not, so the
1-min loadavg is recorded per run twice over: `placement.loadavg` in each
manifest (preflight, at run start; `scripts/preflight.sh:64,295`) and the
`loadavg_1m` column of each `resources.csv` (one sample per second across the
whole run). Preflight's own refusal threshold is 8 (exclusions.md criterion 6).

Measured: **start loadavg 0.37–1.13, per-run mean 0.32–1.02, per-run max
0.41–1.23** across all fifteen runs. No CARLA, no Autoware container and no
other measurement ran concurrently. The host was materially quiet, not merely
admissible.

## Delivery, and a loud finding

| run       | transport   | msgs | achieved Hz | rate ratio |
| --------- | ----------- | ---: | ----------: | ---------: |
| `run-001` | cyclonedds  |  624 |      10.000 |      1.000 |
| `run-004` | cyclonedds  |  624 |      10.000 |      1.000 |
| `run-007` | cyclonedds  |  624 |      10.001 |      1.000 |
| `run-010` | cyclonedds  |  624 |      10.001 |      1.000 |
| `run-013` | cyclonedds  |  624 |      10.001 |      1.000 |
| `run-002` | fastdds-shm |   40 |       0.639 |      0.064 |
| `run-005` | fastdds-shm |   46 |       0.724 |      0.072 |
| `run-008` | fastdds-shm |   45 |       0.759 |      0.076 |
| `run-011` | fastdds-shm |   16 |       0.246 |      0.025 |
| `run-014` | fastdds-shm |   73 |       1.182 |      0.118 |
| `run-003` | fastdds-udp |    6 |       0.097 |      0.010 |
| `run-006` | fastdds-udp |   80 |       1.386 |      0.139 |
| `run-009` | fastdds-udp |  177 |       2.830 |      0.283 |
| `run-012` | fastdds-udp |    9 |       0.142 |      0.014 |
| `run-015` | fastdds-udp |   53 |       0.852 |      0.085 |

**MEASURED: at 921 600 B/msg, Cyclone DDS delivers every message and Fast DDS
delivers ~1–14% of them.** Cyclone is at the 10 Hz target to within 0.01% in
all five runs (**624 messages, 10.000–10.001 Hz**); both Fast DDS arms lose
**86–99%** of samples (**6–177 messages**), with run-to-run swings of ~30×
(`run-003`'s 6 against `run-009`'s 177).

> ### Read this before using the fastdds-udp p50
>
> **The `fastdds-udp` p50 rests on roughly 1% of the offered messages, under
> load not comparable with the cyclonedds arm's, and it is therefore a WEAK
> loopback-parity number.** Median delivery on that arm is 53 messages against
> 624 offered; per run only 4–130 rows survive the 20 s warm-up. The cyclonedds
> arm carried ~10 msg/s and the fastdds-udp arm ~0.85 msg/s, so the two p50s
> were not measured under comparable queueing pressure, and a nearly idle
> transport can look faster per delivered message. Anyone reaching for "the
> loopback-parity transport term" should treat this as a bound on evidential
> weight, not as a characterisation of Fast DDS at this size.
>
> **No registered exclusion criterion covers this condition**, and that absence
> is part of the record rather than something to paper over.
> `config/exclusions.md`'s ten criteria cover crashes, bring-up gates, harness
> defects, clock stalls, warm-up, host load, port collisions, BuildId
> mismatches, recorder crashes and a capped unpaced window — none is "the
> transport under test delivered almost nothing". Had a Fast DDS run recorded
> ZERO observer rows (`run-003` came within 6), `run.sh` step 15's smoke would
> have failed and the run would have been filed under criterion 3,
> `harness:<commit>` — a harness-defect label for a run in which the harness
> worked perfectly. **A criterion is deliberately NOT being added**: writing an
> exclusion rule after seeing the data it would exclude is textbook post-hoc
> exclusion, and those criteria may not be edited after the first P3
> measurement run either way. Owner ruling 2026-07-31: retain all fifteen runs
> as produced, with no exclusions, and disclose.
>
> **Why the frozen margin nonetheless stands.** The margin is
> `max(2.0, ceil_to_0.5(2 × |delta|))`, and `ceil_to_0.5(x)` exceeds the 2.0
> floor only once `x` does — so the floor binds for any `|delta| ≤ 1.0 ms`. The
> measured `|delta|` is **0.4152 ms**. For the weak arm to move the frozen
> value the true delta would have to exceed 1.0 ms, i.e. the measurement would
> have to be wrong by a factor of **~2.4**; equivalently, with `p50_cyclonedds`
> at 0.684 ms the true `p50_fastdds-udp` would have to exceed ~1.68 ms against
> the measured 1.099 ms. The conclusion is insensitive to the weak arm rather
> than resting on it.

Independently corroborated at bring-up: `cells/calibration.sh:160-165`'s
readiness probe is a separate `ros2 topic hz` subscriber (rclpy, in the
publisher's own container, on the same RMW), and it reported 10.008–10.010 Hz
on every cyclonedds run against 0.333–6.156 Hz on the Fast DDS runs. Two
independent subscribers, one C++ and one Python, in two containers, agree. The
probe's figures are console output of the driver loop and are **NOT retained in
this repository** — the per-run message counts above are the tracked evidence,
and the probe is offered only as corroboration.

`bench_pub` publishes on `KeepLast(5)` **BEST_EFFORT** VOLATILE
(`bench_pub.cpp:19`), which is ROS 2 sensor-data QoS: lost fragments of a
fragmented sample are never repaired, and one missing fragment discards the
whole sample. A plausible mechanism is that a 921 600 B sample fragments into
~640 UDP datagrams and overruns the receiver's socket buffer — this host's
`net.core.rmem_default` is 212 992 B. That mechanism is **NOT measured here**
and is offered as a hypothesis only; the delivery collapse itself is measured.

### What this does NOT say about the duel cells

It says nothing about cell B, and the reason is size, not transport. Cell B
also runs `rmw_fastrtps_cpp` + `udp_only.xml`, and it delivers: its LiDAR
messages are **~242 KB**, not 921 KB — mean `size_bytes` 241 782 B over its
626 `…/pointcloud_raw_ex` rows in `results/B/run-011/observer.csv` and
241 859 B over 699 such rows in `results/B/run-012/observer.csv`, arriving at
8.94 and 8.99 Hz. Cell A's are ~513 KB (513 245 B mean over its 1383 LiDAR
rows, `results/A/run-001/observer.csv`, at 19.96 Hz) on Cyclone. So the collapse sits somewhere between ~242 KB and ~922 KB per
sample on this Fast DDS configuration; **this task did not bisect it**, and
`benchmarks/patches/tier4-native/README.md:342`'s 10.006 Hz for
fastrtps + `udp_only.xml` is consistent with the smaller size rather than in
conflict with the measurement above.

### BOUNDED HYPOTHESIS — NOT ESTABLISHED: does this explain cell B's `observer_loss_rate`?

The campaign has already measured an instrument asymmetry it has not explained,
and this result is a candidate mechanism for it. Recorded here as a
**hypothesis**, explicitly **not established**, because if it were true the
asymmetry would be a property of the INSTRUMENT rather than of the approach —
and that distinction bears directly on the primary duel.

What is already measured (`benchmarks/README.md:619-631`): cell A's
`observer_loss_rate` is **0.0000** on both arms, against cell B's **0.2564**
(`results/B/run-008`: 930 expected, 940 published, 699 observed) and **0.1715**
(`results/B/run-009`: 798 expected, 799 published, 662 observed), with
`publisher_drop_rate` **0.0000** in both — i.e. the fork published and the
OBSERVER did not see it. And the observers differ by transport, not by
approach: cell A's observer runs `rmw_cyclonedds_cpp` on
`docker/cyclonedds.xml`, cell B's runs `rmw_fastrtps_cpp` +
`observer/config/udp_only.xml` (`benchmarks/README.md:1332-1334`).

The hypothesis: the same Fast DDS large-sample fragmentation loss measured
above is what cell B's observer suffers, so its `observer_loss_rate` is a fact
about the recorder's transport rather than about the tier4-native approach.

**Bounded in both directions, because it does not transfer directly.**

- AGAINST it, and this is the strong objection: cell B's LiDAR messages are
  ~242 KB (241 754 B mean over `run-008`'s 699 rows, 241 918 B over
  `run-009`'s 662) against this cell's 921 600 B — a **~3.8× gap**. This
  document says elsewhere that cell B "delivers" at its own size, and that
  remains the honest reading: nothing measured here shows Fast DDS losing
  anything at ~242 KB. A ~25% loss and a ~99% loss are also different
  phenomena, not the same one scaled.
- FOR it: the loss is on the observer's subscription while the publisher's own
  count is complete, the two cells' observers differ exactly in the transport
  this cell just showed to be size-sensitive, and 242 KB is still far above any
  single-datagram threshold — roughly 170 UDP fragments per sample against
  ~640 here.
- NOT KNOWN, and not to be assumed: whether Autoware's own subscription in
  cell B lost the same clouds. If it did not, the loss is instrument-only; if
  it did, it is not. Nothing in the committed data was checked for this.

**What would settle it, cheapest first. NOT RUN — scheduling is the owner's.**

1. **Zero new runs.** Cell B's committed `observer.csv` files already contain
   SMALL topics recorded over the same transport in the same runs —
   `run-008` holds 1704 `/localization/kinematic_state` rows, 110
   `/localization/pose_estimator/pose_with_covariance` and 1011
   `/control/command/control_cmd` beside its 699 LiDAR rows (`run-009`: 1529 /
   111 / 20 / 662). Those are raw row counts, NOT loss rates: turning them into
   loss rates needs the registered reconciliation
   (`analysis/publisher_counts.py` + `cadence.reconcile_drops`), which was not
   run here. If the small topics reconcile to ~0 loss while only the 242 KB
   PointCloud2 loses, size-dependent fragmentation is implicated; if every
   topic loses alike, it is refuted and the cause is elsewhere.
2. **One CAL-rmw round at cell B's size**, 2 runs, ~3 minutes:
   `BENCH_PUB_POINTS=7558` (7558 × 32 B = 241 856 B, 0.008% above cell B's
   measured mean of 241 836 B across `run-008`/`run-009`) on `cyclonedds` and
   on `fastdds-udp`. This measures the
   transport directly at the size in question. It must be filed as a labelled
   probe, never as duel-feeding data, and it does NOT invalidate
   `cells.yaml:525`'s `lidar_expected_hz: 10.0` binding, whose own comment
   scopes that hazard to `BENCH_PUB_RATE_HZ` — which such a run must leave
   alone.

Neither was run, and nothing in cell B's data, `config/observer_topics/` or any
cell's transport configuration was touched by this task.

### Consequence for the pre-registered synthetic size

The registered duel size matches cell A in BYTES PER SECOND
(921 600 × 10 = 9.2 MB/s against 512 184 × 20 = 10.2 MB/s, ~10% below) but
not per MESSAGE: it is 1.8× cell A's message and 3.8× cell B's. Fast DDS
fragmentation loss is a per-message effect, so the bandwidth match is what put
the two Fast DDS arms into a loss regime that neither duel cell is in. The
size is pre-registered and was NOT changed — changing it after the
measurement that revealed the gap is exactly the post-hoc tuning the
pre-registration freeze exists to prevent.

## Exclusions

**None.** All fifteen runs are `excluded: false`, all fifteen exited 0, and
all fifteen rendered through `run.sh` step 15. No pre-registered exclusion
criterion was met.

Worth recording for the record: none of `config/exclusions.md`'s ten criteria
covers "the transport under test delivered almost nothing". Had a Fast DDS run
recorded ZERO observer rows (`run-003` came within 6), step 15's smoke would
have failed and the run would have been filed under criterion 3,
`harness:<commit>` — a harness-defect label for a run in which the harness
worked perfectly. That did not happen, and the criteria may not be edited
after the first P3 measurement run, so it is noted rather than fixed.

## Derived: one-hop wall latency and the frozen margin

Percentiles are **derived**, not recorded by the harness. Two bases, both
computed from committed helpers only:

- **windowed** (the registered basis): `analysis/window.py:65`
  `static_window(t0, end, 20_000_000_000)` over `observer.csv`'s
  `arrival_system_ns` for `/bench/cloud`, first and last row — README's
  "Unfittable branch" (`benchmarks/README.md:337`), rows filtered on the same
  column the bounds come from — then the median of
  `analysis/latency.py` `segment_sim_ms(header_stamp_ns, arrival_system_ns)`.
- **unwindowed** (what the committed CAL tool prints):
  `scripts/cal_report.py` `summarize_run`'s `one_hop_p50_ms`, whole run.

| transport     | p50 windowed, median of 5 runs | run range        | p50 unwindowed |
| ------------- | -----------------------------: | ---------------- | -------------: |
| `cyclonedds`  |                     0.684 ms |  0.659 – 0.712 ms |       0.676 ms |
| `fastdds-shm` |                     1.050 ms |  0.907 – 1.200 ms |       1.066 ms |
| `fastdds-udp` |                     1.099 ms |  1.057 – 1.262 ms |       1.130 ms |

The pre-registered formula, applied mechanically on the windowed basis
(`fastdds-udp` is the loopback-parity arm; `fastdds-shm` is context):

```text
|0.6840 - 1.0993|          = 0.4152 ms
2 x 0.4152                 = 0.8305 ms
ceil_to_0.5(0.8305)        = 1.0 ms
max(2.0, 1.0)              = 2.0 ms      <- the 2.0 FLOOR BINDS
```

The unwindowed basis gives |Δ| = 0.4549 ms and the same 2.0. The floor keeps
binding for any |Δ| ≤ 1.0 ms, so the measured 0.4152 ms sits 2.41× inside it.
**2.0 is the floor binding, not the measurement agreeing with the provisional
value it replaces.** The frozen value and its full derivation are in the
`config/margins.yaml` commit.

## Limits of the transfer, stated rather than implied

- **Same measurand, different window basis and no fit.** This margin is frozen
  from an observer-windowed, UNFITTED wall term (no `/clock` exists in this
  cell, so `clockfit.fit_sim_wall_affine` cannot apply) and is applied to a
  duel term that is `/clock`-windowed and fit-converted. The arithmetic and the
  window basis are not the same; only the measurand is. Already registered in
  `benchmarks/README.md`'s "Recorded consequence for Task 16".
- **The size mismatch largely cancels — but the LOAD mismatch does not.** The
  margin is a difference between two transports at the SAME nominal size, so
  the ~10% gap to cell A's live volume affects both arms alike and mostly
  cancels. What does not cancel is delivered load: the cyclonedds arm carried
  ~10 msg/s and the fastdds-udp arm ~0.85 msg/s, so the two p50s are not
  measured under comparable queueing pressure, and a nearly idle transport can
  look faster per delivered message. The delta is therefore a weaker
  "loopback parity" estimate than the formula's framing suggests. It does not
  change the frozen value, because the floor binds with 2.41× headroom.
- **Container vs host placement.** Both `bench_pub` and the observer run in
  containers from the same image, `--net=host --ipc=host`
  (`cells/calibration.sh:136-142` and `run.sh:605-607`), and each manifest
  records it as `placement.run_mode: container-only`. The natives' publisher
  is a host process, so the calibration's publisher placement is not the
  duel's (`run_mode: editor-game` there). It bounds the observer-side
  difference between two RMW configurations — placement is identical in both
  CAL arms, so it cancels out of the delta the margin is frozen from — and it
  does NOT bound any native cell's absolute one-hop latency.

  **Now disclosed in the README as well, and the history is kept because this
  is the error class the campaign records rather than smooths.** Task 16's
  dispatch asserted this was "a disclosed approximation already recorded in
  the README" and it was NOT: the word "approximation" did not occur anywhere
  in that file, and its only placement statement was the narrower "both inside
  the one observer image" in the CAL-rmw bounds list. The owner confirmed the
  dispatch statement was wrong and inherited unchecked, and ruled the
  disclosure in; it is now `benchmarks/README.md`'s **"DISCLOSED
  APPROXIMATION: publisher PLACEMENT is not the duel's"** bullet, in that same
  bounds list beside "What `CAL-rmw` bounds" and "What `CAL-rmw` does not
  bound".
- **32-ch / 128-ch sizes were NOT run.** The campaign was cut to the core duel
  on 2026-07-30 and the margin formula consumes only the duel size, so the
  3 840 000 B and 14 720 000 B points were not measured. If the `32ch` class is
  ever reinstated — it is pre-registered as an anticipated amendment — **its
  CAL-rmw transport calibration does not exist and would have to be measured
  then.** Given the delivery collapse above, a 3 840 000 B Fast DDS arm should
  be expected to deliver nothing at all.
