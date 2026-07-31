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

**INTERLEAVED BUT NOT COUNTERBALANCED — the limitation of that order,
disclosed 2026-07-31.** Every block runs the three transports in the same
sequence, so each transport holds a fixed POSITION within its block:
cyclonedds always first, fastdds-shm always second, fastdds-udp always third.
Interleaving removes drift that is a function of WALL TIME; it does not remove
an effect that is a function of position within a block — a cache, thermal or
DDS-segment state that depends on "first / second / third run since the
previous block" rather than on the hour. Any such effect is therefore
confounded with transport here, and it bears on the frozen quantity directly,
because the delta is taken between position 1 and position 3. Only alternating
the order across blocks would remove it. **Nothing here measures such an effect
and none is asserted** — the design simply cannot exclude one, which is why it
is disclosed. Like the load mismatch recorded below, it does not move the
frozen value: the 2.0 floor binds for any `|Δ| ≤ 1.0 ms` and the measured
`|Δ|` is 0.4152 ms.

**And this cell is the exception, not the campaign's practice.** The primary
duel's driver DOES counterbalance: `benchmarks/scripts/duel.sh:87-96` runs
odd-numbered pairs as A,B and even-numbered pairs as B,A, on its own stated
rationale that "interleaving alone still gives one cell every odd slot and the
other every even slot, so a per-pair effect … lands entirely on one cell"
(`benchmarks/scripts/duel.sh:14-18`). So the limitation above is LOCAL to
CAL-rmw and must not be read across to the duel. (`benchmarks/README.md:3469`
describes the duel as "interleaved A,B,A,B pairs", whose literal reading is the
UNcounterbalanced order; the committed driver is the authority and it
alternates.)

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
> **The `fastdds-udp` p50 rests on a small and wildly variable fraction of the
> offered messages, under load not comparable with the cyclonedds arm's, and it
> is therefore a WEAK loopback-parity number.** DERIVED 2026-07-31 from the
> committed `observer.csv` files, on the same window construction the p50 uses
> (`analysis/window.py:65` `static_window`, 20 s warm-up over
> `arrival_system_ns` for `/bench/cloud`): the rows surviving the warm-up are
> **4** (`run-003`), **51** (`run-006`), **130** (`run-009`), **7** (`run-012`)
> and **37** (`run-015`) — a median of 37, i.e. **5.9% of the 624 offered**,
> across a range of **0.6% to 20.8%**. On whole-run delivery the same arm is
> 6 / 80 / 177 / 9 / 53 of 624, median 53 = **8.5%**. The denominator 624 is the
> cyclonedds arm's own delivered count, used as the offered proxy because that
> arm holds the 10 Hz target to within 0.01% on all five of its runs.
>
> **This supersedes a "roughly 1%" figure that stood here until 2026-07-31.**
> That number describes `run-003` alone — 4/624 = 0.6% in-window, 6/624 = 1.0%
> whole-run — the worst of the five runs, not the arm. **The ~1% end is
> nonetheless where the frozen number comes from, which is the sharper
> statement**: the median-of-5 the formula consumes is `run-012`'s p50 of
> 1.0992 ms, and `run-012`'s window holds **7 rows**, 1.1% of the 624 offered.
>
> The cyclonedds arm carried ~10 msg/s and the fastdds-udp arm ~0.85 msg/s, so
> the two p50s were not measured under comparable queueing pressure, and a
> nearly idle transport can look faster per delivered message. Anyone reaching
> for "the loopback-parity transport term" should treat this as a bound on
> evidential weight, not as a characterisation of Fast DDS at this size.
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
- AGAINST it, and this document previously filed it as unknown: **a second,
  unrelated subscriber loses the same clouds.** `benchmarks/README.md:634-639`
  reports that on `results/B/run-010`, measured from inside the Autoware
  container, Autoware's own subscription receives
  `/sensing/lidar/top/pointcloud_raw_ex` at **8.47 Hz** (339 samples over a
  40.05 s window after a 20 s discovery settle —
  `benchmarks/README.md:2086-2092`), and that passage reads two unrelated
  subscribers losing alike as the loss being **real on the wire** rather than
  an instrument artifact. That defeats the hypothesis's PAYLOAD — "the
  asymmetry is a property of the INSTRUMENT rather than of the approach" —
  because cell B's transport is forced by the fork rather than chosen for the
  recorder (`benchmarks/README.md:1336-1346`) and Autoware's own subscription
  runs it too (`benchmarks/README.md:1334`). It does not by itself settle the
  MECHANISM; the next bullet is about that.
  **Two qualifications, derived here rather than taken on trust.** (i) The
  8.53 Hz the README pairs with the 8.47 is `results/B/run-009`'s WHOLE-RUN
  observer rate, not `run-010`'s — `benchmarks/README.md:636` says "on the
  comparable run" and this is what that means. Derived from `run-009`'s
  `observer.csv`: 662 LiDAR rows spanning 77.45 s of `arrival_system_ns` =
  8.534 Hz. (ii) On `run-010` ITSELF the bench observer read **8.84–9.04 Hz**
  over every 40.05 s window (361 rows = 9.01 Hz over the window opening 20 s
  in; 659 rows over 74.03 s = 8.888 Hz whole-run), so the same-run gap between
  the two subscribers is ~4–6%, not the ~0.7% the cross-run pairing suggests —
  and it points the other way: on `run-010` AUTOWARE saw fewer clouds than the
  recorder did. Both qualifications strengthen this objection rather than
  weaken it, since the recorder is not the lossiest subscriber on that run.
- AGAINST it, on mechanism: `benchmarks/README.md:2076-2078` already
  attributes this deficit to **host CPU starvation, not UDP fragmentation**,
  and records that as a change of reading forced by Task 9's transport matrix —
  `benchmarks/patches/tier4-native/README.md:342,344,349` measure
  10.006 / 10.071 / 10.070 Hz on this exact `fastrtps` + `udp_only.xml`
  transport, rows 8–11 of that matrix running in the same pinned Autoware image
  cell B launches from.
  **One caveat, measured here and not previously recorded anywhere:** the
  corroborating stock-`bench_observer` acceptance check in that same file
  (`benchmarks/patches/tier4-native/README.md:473-478` — 243 rows in 24 s =
  10.1 Hz) records its `size_bytes` as **64–76 KB**, roughly 3.4× below the
  ~242 KB the committed `run-008`/`run-009` observer CSVs carry, and the matrix
  rows record no cloud size at all. That corroboration is therefore not at cell
  B's measured message size, and on its own it cannot close a SIZE-dependent
  mechanism.
- FOR it: the loss is on the observer's subscription while the publisher's own
  count is complete, the two cells' observers differ exactly in the transport
  this cell just showed to be size-sensitive, and 242 KB is still far above any
  single-datagram threshold — roughly 170 UDP fragments per sample against
  ~640 here.
- STILL OPEN, and narrower than this document previously claimed. This bullet
  used to read: "NOT KNOWN, and not to be assumed: whether Autoware's own
  subscription in cell B lost the same clouds. If it did not, the loss is
  instrument-only; if it did, it is not. Nothing in the committed data was
  checked for this." **It had been checked** — by the `run-010` in-container
  measurement above, which sits eight lines below a block this document already
  cites. What genuinely remains open is the PER-MESSAGE question on the two
  runs the loss rates come from: `run-010` is a different run and a RATE
  comparison, so it constrains the hypothesis without closing it. Closing it
  means the registered reconciliation (`analysis/publisher_counts.py` +
  `cadence.reconcile_drops`) run on `run-008`/`run-009` themselves, per topic.
  Their own `published_time.csv` cannot substitute: each holds only
  `/control/command/control_cmd/debug/published_time` rows (980 on `run-008`,
  18 on `run-009`) and no LiDAR-stage PublishedTime, so nothing in those two
  run directories records what Autoware's LiDAR subscription received.

**Weighed, not inverted: DISFAVOURED WITH REASON.** Two independent lines — a
second subscriber losing alike on `run-010`, and the CPU-starvation attribution
the transport matrix forced — point away from the instrument-only reading, and
neither is a per-message test on `run-008`/`run-009`. The hypothesis stays in
the record, marked disfavoured: not deleted, and not asserted refuted.

**OPEN INCONSISTENCY IN THE RECORD, named rather than reconciled: ~460 KB
against ~242 KB.** `benchmarks/README.md:639` (and `:2104`, `:2121`) describes
cell B's clouds as **~460 KB**. Measured here from the committed evidence, the
same topic in the same runs is **~242 KB**: mean `size_bytes` over
`/sensing/lidar/top/pointcloud_raw_ex` rows is 241 754 B (`run-008`, 699 rows),
241 918 B (`run-009`, 662), 241 861 B (`run-010`, 659), 241 782 B (`run-011`,
626) and 241 859 B (`run-012`, 699). Those two cannot both be measurements of
the same thing. The ratio is ~1.9 — the order of a `point_step` 16-vs-32
difference, i.e. a doubled per-point payload against unchanged message overhead
— which is the SHAPE of the gap and not a diagnosis of it.
`benchmarks/README.md` is frozen and its figure is recorded as a
measured/derived value, so it is NOT changed here and NEITHER figure is
asserted correct. **Task 17b** (cell B binary-vs-pinned-source provenance) is
where this gets settled. A third figure sits beside them and is noted so a
reader does not treat it as a tie-breaker: the wire-visibility acceptance check
at `benchmarks/patches/tier4-native/README.md:476` records 64–76 KB on the same
topic; whether that is a different sensor configuration or a third reading of
this one is not stated there.

**What would settle it, cheapest first. NOT RUN — scheduling is the owner's.**
Revised 2026-07-31: the list used to open at item 2 below, and it had missed
that the record ALREADY holds a cheaper discriminator than either of them.

1. **Already paid — zero runs and zero analysis.** The `run-010` in-container
   measurement (`benchmarks/README.md:2086-2092`, and the reading drawn from it
   at `:634-639`) is exactly the discriminator this section was asking for:
   Autoware's own subscription, on cell B's own transport, in its own
   container. It answers the question by RATE on ONE run, which is why the
   items below are still worth running — but it is already in the record and
   costs nothing to consult, so nothing should be scheduled without reading it
   first.
2. **Zero new runs.** Cell B's committed `observer.csv` files already contain
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
3. **One CAL-rmw round at cell B's size**, 2 runs, ~3 minutes:
   `BENCH_PUB_POINTS=7558` (7558 × 32 B = 241 856 B, 0.008% above cell B's
   measured mean of 241 836 B across `run-008`/`run-009`) on `cyclonedds` and
   on `fastdds-udp`. This measures the transport directly at the size in
   question. It is the most nearly redundant of the three: Task 9's matrix rows
   already measure ~10 Hz on this transport
   (`benchmarks/patches/tier4-native/README.md:342,344,349`), and what a
   CAL-rmw round adds over them is a RECORDED cloud size at cell B's value,
   which those rows do not carry. It must be filed as a labelled probe, never
   as duel-feeding data, and it does NOT invalidate `cells.yaml:525`'s
   `lidar_expected_hz: 10.0` binding, whose own comment scopes that hazard to
   `BENCH_PUB_RATE_HZ` — which such a run must leave alone.

Neither of the two runnable items was run, and nothing in cell B's data,
`config/observer_topics/` or any cell's transport configuration was touched by
this task.

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

## Each run's `report.md` is a SMOKE RECEIPT, not scorer output

Recorded 2026-07-31 because a reader opening a run directory and finding a
`report.md` will reasonably assume it holds that run's scored result. It does
not. All fifteen are one line of this shape:

```text
# run-001: 624 observer rows, 130 resource samples (no sim clock; CAL rendering is Task 16's cal_report.py)
```

It is printed by `benchmarks/run.sh:996-997` — the `BENCH_HAS_SIM_CLOCK != 1`
branch of step 15's smoke — whose stdout `benchmarks/run.sh:940-943` redirects
into `<run>/report.md`. On a cell that publishes no `/clock` that branch
deliberately does NOT call `report.py`'s renderer; it asserts only that rows
were recorded, and exits non-zero if none were.

**Where the scored numbers actually live**, and it is two places only: the p50
table in the next section of this file, and the frozen value with its full
derivation in `benchmarks/config/margins.yaml`'s `one_hop_wall_ms` block.
`benchmarks/scripts/cal_report.py` — the CAL renderer that stub names — was run
to produce the unwindowed column of that table, but **its output is not
committed as a file anywhere**, so nothing under `results/CAL-rmw/` is
`cal_report.py` output.

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
