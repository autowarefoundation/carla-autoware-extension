# Evaluation report: three CARLA↔Autoware integration approaches

**Assembled 2026-08-05 (P6 Task 6).** This document argues claims **C1–C3** of
`2026-07-27-three-approach-evaluation-design.md` from evidence that already
exists in this repository. It **computes nothing**. Every figure below is quoted
from a document that computed it once, with the section that owns it named
beside the number.

Sources, and the only ones:

| source                                  | what it owns                                        |
| --------------------------------------- | --------------------------------------------------- |
| `docs/evaluation/p3-baseline.md`        | the P3 record: cells, A-vs-B verdict, E-family data |
| `docs/evaluation/p4-transport-sweep.md` | the P4 record: A-vs-B-cyc verdicts, C1(a), M4       |
| `docs/evaluation/gap-catalog.md`        | C3 — the 53-entry capability catalog                |
| `docs/evaluation/rubric.md`             | the community-acceptance snapshot                   |
| `benchmarks/` (README, config, results) | the pre-registration, patches, and raw runs         |

## 0. How to read this document

**Six rules are applied mechanically, not case by case.**

1. **Every number carries its cell and run range.** A figure without a pool is
   not reportable here.
2. **Every C1 sentence names its arm** — `A-vs-B` (P3, cell B on Fast-DDS +
   `udp_only.xml`) or `A-vs-B-cyc` (P4, both cells on CycloneDDS), and `static`
   or `closed-loop`. **Every C2 sentence names its arm** — `E0` (as-shipped),
   `E` (harmonized/patched), `E-opt` (packer-optimized). E-opt was **struck**;
   see 4.1.
3. **Caveats travel with their numbers, inline**, not in a footnote section.
   Four are mandatory and appear at every quotation of the figures they bound:
   the static bracket's **four-of-five** metric coverage; the closed-loop
   verdict being **A-vs-B-cyc, not A-vs-B**; C1(a) being an **upper bound, not
   a point estimate**; and cell E0's pool being **optimistically biased**.
4. **Wording downgrades the data forced are applied as written and are not
   re-litigated** anywhere in this document: equivalence is **inconclusive**
   where a metric did not compute, cell E is **static-only**, and the E family
   is gated on the **relative** G1 ladder branch. Each is marked ⬇ where it
   applies.
5. **A P3 figure and a P4 figure never share a sentence without the P4↔P3
   identity caveat inline** (`p4-transport-sweep.md` §9): the engine BuildId and
   the harness sha both moved between phases, so only **verdicts computed
   entirely within one phase** are set against each other — never a per-cell
   absolute against another phase's.
6. **No composite score, and no ranking table.** Per-criterion and per-metric
   evidence only.

**What this document is not.** It is not a "which approach wins" study; the
spec says so in terms. It is not a cross-approach equivalence statistic — none
was computed in either phase, and none may be inferred (`p3-baseline.md` §4.3,
`p4-transport-sweep.md` §2.6). It is not a re-scoring: no filed run was read,
re-read, re-scored or reclassified by this task.

## 1. The approaches and the workload matrix

### 1.1 The three approaches

| label             | what it is                                              | repo                                               |
| ----------------- | ------------------------------------------------------- | -------------------------------------------------- |
| **extension**     | out-of-tree `.so` behind a frozen C ABI + Python runner | `autowarefoundation/carla-autoware-extension`      |
| **tier4-native**  | in-fork native ROS 2/DDS, built into a CARLA UE5 fork   | `tier4/carla-autoware-native` @ `autoware-support` |
| **python-bridge** | `autoware_carla_interface`, in-tree Python bridge node  | `autowarefoundation/autoware_universe`             |

Full ownership, licensing and maintenance detail: `docs/evaluation/rubric.md`,
"The three approaches" (§6 below).

### 1.2 The cells as filed

**191 manifests are filed across eight cells; 37 are excluded.** Counts are the
per-cell census reproduced by command 3 of the appendix.

| cell       | approach      | CARLA      | map           | filed | excluded | role                                 |
| ---------- | ------------- | ---------- | ------------- | ----- | -------- | ------------------------------------ |
| `A`        | extension     | 0.10-fork  | Town10HD_Opt  | 53    | 0        | duel side A, P3 **and** P4           |
| `B`        | tier4-native  | 0.10-tier4 | Town10HD_Opt  | 33    | 15       | duel side B, P3 (Fast-DDS)           |
| `B-cyc`    | tier4-native  | 0.10-tier4 | Town10HD_Opt  | 45    | 6        | duel side B, P4 (CycloneDDS)         |
| `C`        | extension     | 0.10-fork  | Nishishinjuku | 14    | 2        | confirmatory, never duel data        |
| `E0`       | python-bridge | 0.9.15     | Town10HD_Opt  | 10    | 4        | bridge as shipped — context only     |
| `E`        | python-bridge | 0.9.15     | Town10HD_Opt  | 16    | 10       | bridge harmonized, **static only** ⬇ |
| `CAL-rmw`  | none          | —          | —             | 15    | 0        | transport calibration, no simulator  |
| `CAL-seam` | extension     | 0.10-fork  | Town10HD_Opt  | 5     | 0        | C1(a) seam-vs-in-core isolation      |

The duel pools inside those cells, which are what every verdict is computed
from (`p3-baseline.md` §0, `p4-transport-sweep.md` §0.4):

| duel         | arm         | pool A        | pool B/B-cyc      | n                          |
| ------------ | ----------- | ------------- | ----------------- | -------------------------- |
| P3 `A+B`     | static      | `A/003`…`012` | `B/013`…`022`     | 10/10                      |
| P3 `A+B`     | closed-loop | —             | —                 | **0/0** — not computable ⬇ |
| P4 `A+B-cyc` | static      | `A/016`…`025` | `B-cyc/002`…`011` | 10/10                      |
| P4 `A+B-cyc` | closed-loop | `A/026`…`035` | `B-cyc/012`…`021` | 10/10                      |

Both pools fall out of `duel_verdict.py`'s own contract with **no filtering
flag passed**; the P4 pool is partitioned from P3's by the `duel_id` key so
that P3's ten cell-A static runs (`duel_id: ""`) cannot enter a P4 verdict
(`p4-transport-sweep.md` §0.4).

### 1.3 What is NOT measured, and why it is stated here

Six cells were struck by the owner's 2026-07-30 core-duel scope cut
(`p3-baseline.md` §2.2). **None was infeasible, blocked, or measured and found
wanting; no result about any of them may be inferred from its absence.**

| struck                  | consequence for this report                             |
| ----------------------- | ------------------------------------------------------- |
| `D` (tier4 on Nishi)    | no cross-map tier4 attempt; the question stays **open** |
| `B45` (Autoware 0.45.1) | no hard-fork-maintenance finding; the gap was logistics |
| `E-opt`                 | **no optimised-bridge result** — see 4.1                |
| `A-hf` / `B-hf`         | no 100 Hz sensitivity; struck as a pair                 |
| M4 camera arm           | no camera table, no native-camera-path comparison       |
| `CAL-seam`              | **revived** for P4 by the owner's 2026-08-03 D8 lift    |

`CAL-seam` is the one reversal: struck in P3 with `C1(a)` recorded as
UNMEASURED, revived for one registered relink round, and measured in P4 on five
runs (§3.1). The M4 `128ch` class stays struck on either branch and is enforced
in code — both launchers refuse the class by name
(`p4-transport-sweep.md` §6.3).

## 2. Methodology

### 2.1 Pre-registration, by commit hash

The metric definitions, the equivalence rule, the margins, the ceiling
evaluator and the exclusion criteria were committed **before any measurement
run existed**. The first commit touching `benchmarks/results/` is `ccd456e`,
**2026-07-29 16:11:54 −0700**; every hash below precedes it.

| commit                                     | date (−0700)     | what it registered                          |
| ------------------------------------------ | ---------------- | ------------------------------------------- |
| `b791ee9881ddf7c4e09df84af87c98a739168f53` | 2026-07-27 11:51 | analysis package skeleton                   |
| `941c80507289eeaad1d53ff075a929bc1d5535dd` | 2026-07-27 12:32 | bootstrap CI, equivalence rule, **margins** |
| `884368dcd85cbc4e6b2a5840ee2e44b41691d00d` | 2026-07-27 12:37 | the M4 ceiling evaluator                    |
| `a3ca131466f07e8af8d140697d8ed3815422dff6` | 2026-07-27 12:47 | cell matrix, **exclusion criteria**, method |
| `bdb5c4251c55b8266a5f0071c5549de2d119dc65` | 2026-07-27 13:27 | final whole-branch review fixes to P0       |
| `96af345a5632640c9fede353e2677d29da1eef8f` | 2026-07-27 22:52 | amendment: three spec gaps closed           |
| `75f0fc1c60a30430ae7e7da6909379abc5298fb2` | 2026-07-28 11:03 | amendments for the P2–P4 campaign           |

Two later registrations are load-bearing and are named with the same rigour:

- **`one_hop_wall_ms`'s margin was FROZEN 2026-07-30** from cell CAL-rmw's 15
  interleaved runs, under a formula written before the runs
  (`benchmarks/config/margins.yaml`). The measurement put 2 × |Δ| at 0.83 ms,
  so the **pre-registered floor of 2.0 binds** — a result, not an agreement.
  The file's own header records why this edit was still inside the amendment
  window: no run in the tree was `duel_admissible: true` at that commit.
- **The rubric's criterion list and directions were committed before its
  snapshot**: `dd3737971955b6f5df637c18b4d3de37352a754f` (2026-08-04 18:56)
  precedes `324dc36` (19:22), which filled the value cells. **That ordering is
  itself the methodology fact** — no criterion could be added, dropped or
  re-directioned after a number was seen.

### 2.2 The five margin metrics and the decision rule

| metric                  | margin  | what it measures                      |
| ----------------------- | ------- | ------------------------------------- |
| `one_hop_wall_ms`       | 2.0 ms  | sensor emission → observer arrival    |
| `lidar_to_ndt_sim_ms`   | 5.0 ms  | LiDAR stamp → NDT pose, sim domain    |
| `control_staleness_ms`  | 10.0 ms | control command publish staleness     |
| `carla_process_cpu_pct` | 10.0 pp | the simulator process's own CPU       |
| `achieved_rate_ratio`   | 0.02    | achieved rate ÷ the cell's own target |

Direction convention, from `margins.yaml`'s own header: `delta = extension −
tier4-native; lower is better`. **On `achieved_rate_ratio` that uniform
convention inverts** — the metric is a shortfall detector normalised against
each cell's own registered `lidar_expected_hz`, so higher is better and the
printed `b_better` label on P3's row is a polarity artifact, not a
tier4-favouring result (`p3-baseline.md` §4.2, `p4-transport-sweep.md` §2.2).
That reading is stated wherever the row appears below.

`parity` is a TOST decision: the whole 95% bootstrap CI falls inside
(−margin, +margin). It is **not a proof of identity**
(`p4-transport-sweep.md` §2.6). The bootstrap is pinned at `iters=10000,
seed=20260727, alpha=0.05`, so both verdicts reproduce rather than merely
recompute.

### 2.3 Patch inventory, and the named exception

The patch policy (`benchmarks/README.md`, "Patch policy") forbids changes to
any approach's data-path, conversion or transport code; sensor- and
launch-parameter edits are permitted and are committed as reviewable diffs.
Applied inventory, complete:

| approach        | patches                                                                 |
| --------------- | ----------------------------------------------------------------------- |
| `extension`     | **none** — `patches/extension/` is README only                          |
| `tier4-native`  | `0001-toolchain-libm`, `0002-glibc-compat`, `0003-autoware-demo-params` |
| `python-bridge` | `0001-lidar-is-dense`, `0002-sensor-config-harmonized`                  |

**`0001-lidar-is-dense.patch` is the policy's one named, pre-registered
exception** (`benchmarks/README.md`, "Named exception (pre-registered
2026-07-28, before any P3 run)"). It is a one-line change on the bridge's
publish path — `is_dense=False` → `is_dense=True` in `create_cloud` — and it is
also _correct_: the bridge's cloud contains no invalid points, so the flag was
a mislabel. Without it every E-family closed-loop cell is unmeasurable and C2
degrades to structural analysis. **The as-shipped behaviour is preserved as
cell E0's measured result**, and `cells/python-bridge.sh plan` greps the
resolved image for `is_dense=True` and refuses in **both** directions, so
"measured the unpatched bridge and filed it as E" and "measured the patched
bridge and filed it as E0" are both inexpressible.

A **second** named exception was registered 2026-07-29 (the bridge's `pose()`
publishing the CARLA actor origin where Autoware's contract is `base_link`) and
is **registered, never written, never applied** — the hypothesis it was granted
for was refuted before it was spent. It is listed here because an unexercised
grant is part of the patch record.

`patches_git_sha` is `ccff4f9` on every non-excluded P3 run and `7000c785` on
every P4 run; the move is a git-derived key, and **no `.patch` file changed
between the phases** — the diff is one README line
(`p4-transport-sweep.md` §9.3).

### 2.4 Exclusion log

Ten criteria were frozen before the first measurement run
(`benchmarks/config/exclusions.md`) and **may not be edited after it**. What
they actually excluded:

| cell    | n   | reasons                                                          |
| ------- | --- | ---------------------------------------------------------------- |
| `B`     | 15  | `crash:cell-launch` 7, `crash:collect_gt` 1, `gate:arm-failed` 7 |
| `E`     | 10  | `crash:cell-launch` 4, `harness:<sha>` 4, `gate:arm-failed` 2    |
| `B-cyc` | 6   | `harness:65fbe09` (criterion 3) — the 32ch mislabel, see below   |
| `E0`    | 4   | `harness:e7ba92a` 2, `gate:arm-failed` 1, `crash:cell-launch` 1  |
| `C`     | 2   | `warmup:nishi` — a pre-registered discard, not a failure         |
| `A`     | 0   | —                                                                |

Four properties of this log are the ones a reviewer should check:

- **All 15 of cell B's exclusions are closed-loop**, and they are why the
  A-vs-B closed-loop verdict does not exist (§3.3). Cell B's static pool has
  **zero** exclusions.
- **`B-cyc/run-031`…`run-036` were excluded and re-collected**, not relabelled.
  A missing `BENCH_TIER4_SWEEP_ARGS` export filed a vlp16 rig under a 32ch
  label; the defect was caught by a **measured** quantity (observer median
  `size_bytes` ×0.9987…×1.0005 against the cell's own vlp16 baseline where the
  registered class ratio is 4.1667), not by a label. Relabelling them to
  `vlp16` would have retroactively moved an already-filed verdict's pool, which
  is a worse violation than the one being corrected
  (`p4-transport-sweep.md` §6.2).
- **Cell E0's two `harness:e7ba92a` exclusions are a substance mismatch, named
  rather than softened.** The reason _string_ is verbatim from criterion 3, but
  nothing was broken and nothing was fixed: NDT published exactly one pose, and
  the cadence function raises on a single sample. The label was applied
  **mechanically by committed code** (`run.sh:1028-1029`) to a rule written
  before E0's data existed. E0 is **not** re-collected, on four stated grounds
  (`p3-baseline.md` §8.3). The consequence for C2 is carried inline at every E0
  figure in §4.
- **Three runs are unexcludable and unscoreable** — `C/run-009`, `B/run-025`,
  `B/run-026`. Each ran to completion, matches none of the ten criteria, and
  could not be scored, so each is filed unexcluded with **no `quality.json`**.
  The vocabulary has no category for this and deliberately cannot gain one
  mid-campaign (`p3-baseline.md` §8.2). Any consumer iterating cell C's
  unexcluded runs must special-case `C/run-009` or it will fault.

### 2.5 One-shot verdict discipline

`duel_verdict.py` was invoked **once per phase**, with no filtering flags, and
its complete output — including the rows that decline to decide — is reproduced
verbatim in `p3-baseline.md` §4.1 and `p4-transport-sweep.md` §2.1. Neither was
re-run with adjusted flags after a first result. The P4 capture's md5 is
recorded (`f59d33f279b30e5374408b84322c7e25`, 4351 bytes) precisely so the
claim is checkable.

## 3. C1 — extension versus tier4-native

C1 has three sub-claims, registered in the design spec before any measurement:

- **C1(a)** — routing Autoware vocabulary through the frozen C ABI seam costs
  no measurable overhead versus compiling it into CARLA core.
- **C1(b)** — at system level the extension stack sustains the same workload
  envelope as tier4-native on the same map and kit.
- **C1(c)** — the structural half: it achieves this without a permanent hard
  fork.

### 3.1 C1(a) — the CAL-seam seam-vs-in-core measurement

Five static runs, none excluded, one CARLA fork process, both twins publishing
an identical 921 908-byte cloud on the same RMW; the delta is a **within-run
paired** difference (`p4-transport-sweep.md` §5.1):

| run       | seam p50 ms | in-core p50 ms | Δ p50 ms    | n seam / in-core |
| --------- | ----------- | -------------- | ----------- | ---------------- |
| `run-001` | 0.7242      | 0.4458         | **+0.2784** | 508 / 506        |
| `run-002` | 0.7464      | 0.4593         | **+0.2871** | 502 / 499        |
| `run-003` | 0.7447      | 0.4460         | **+0.2988** | 507 / 506        |
| `run-004` | 0.7316      | 0.4924         | **+0.2392** | 501 / 496        |
| `run-005` | 0.7634      | 0.4987         | **+0.2647** | 505 / 497        |

**Median +0.2784 ms, range +0.2392…+0.2988 ms, positive in 5 of 5 runs**
(`CAL-seam/run-001`…`run-005`).

**⚠ C1(a) IS AN UPPER BOUND, NOT A POINT ESTIMATE — the seam costs _at most_
≈ 0.28 ms per 921 908-byte publish on this instrument**, and that qualifier
travels with the number wherever it is quoted. It is not a hedge added after
the fact: PROVENANCE §11.9 registered the upper-bound rule on 2026-08-03,
**before Task 10 collected a single run**, and `p4-transport-sweep.md` §5.2
applies it on two independent grounds — the rule's antecedent is a judgement
about scale that may not be resolved after seeing the number, and the residual
in-core-only sample loss independently requires it.

Three further statements the table does not support, each recorded rather than
left for a reader to infer:

- **The tails do not separate.** Δ p95 median +0.118 ms, Δ p99 median
  **−0.045 ms**, with the p99 delta negative in 3 of 5 runs. The seam cost is a
  consistent shift in the **median** only; no tail claim is made at n = 5.
- **The CPU half cannot decompose.** `cal_report.py` reports `carla-server` at
  249.70–252.67 % mean across the five runs, but **both twins run inside that
  one process**, so the figure is run-condition context and not a seam cost
  (`p4-transport-sweep.md` §5.4).
- **The publish-order residual's sign is NOT established.** §11.9's original
  "seam-first pays the cold-cache cost, so the bias is conservative" argument
  was corrected on 2026-08-03 and does not survive — the seam is a late writer
  on an already-warm path. The paired delta survives (the burst is
  common-mode); the conservatism claim does not
  (`p4-transport-sweep.md` §5.2, §5.3).

**⬇ Against C1(a) as stated ("no measurable overhead"), the honest reading is a
downgrade**: an overhead _was_ measured, on 5 of 5 runs, and it is bounded
above at ≈ 0.28 ms per publish at this payload. What the measurement supports
is that the seam's cost is small and bounded — not that it is zero.

### 3.2 C1(b), static arm — the attribution bracket

**Read this table with the P4↔P3 identity caveat inline** (rule 5): it sets two
_verdicts_ side by side, each computed entirely within its own phase against
the same frozen margins, which is the only cross-phase reading the spec
licenses. It does **not** compare a P3 per-cell absolute against a P4 one, and
nothing here licenses that — the engine BuildId (`4210e602` → `bc08ce19`) and
the harness sha both moved between the phases (`p4-transport-sweep.md` §9.1).

| metric                  | P3 `A-vs-B` (Fast-DDS)      | P4 `A-vs-B-cyc` (both Cyclone) | pre-registered reading                      |
| ----------------------- | --------------------------- | ------------------------------ | ------------------------------------------- |
| `one_hop_wall_ms`       | −6.281, [−6.542, −5.828]    | **+1.687**, [1.441, 1.849]     | `a_better` → **`parity`** ⇒ transport-bound |
| `lidar_to_ndt_sim_ms`   | −5.817, [−8.106, −4.976]    | **+1.356**, [1.287, 1.553]     | `a_better` → **`parity`** ⇒ transport-bound |
| `control_staleness_ms`  | UNAVAILABLE                 | `insufficient-data`, n = 0/8   | **no bracket on this arm** ⬇                |
| `carla_process_cpu_pct` | −12.873, [−16.698, −11.129] | **+52.005**, [49.617, 52.871]  | `a_better` → **`b_better`** — reversed      |
| `achieved_rate_ratio`   | +0.104, [+0.090, +0.114]    | **+0.001**, [0.001, 0.001]     | favoured A → **`parity`** ⇒ transport-bound |

Pools: P3 `A/run-003`…`012` vs `B/run-013`…`022`, n = 10/10
(`p3-baseline.md` §4.1); P4 `A/run-016`…`025` vs `B-cyc/run-002`…`011`,
n = 10/10 (`p4-transport-sweep.md` §2.1, §2.3). Units follow the metric: ms
on the two latency rows, percentage points on `carla_process_cpu_pct`, and a
dimensionless fraction on `achieved_rate_ratio`.

**⚠ THE STATIC BRACKET CLOSES ON FOUR OF THE FIVE PRE-REGISTERED MARGIN
METRICS, NOT FIVE.** `control_staleness_ms` is `insufficient-data` at n = 0/8
on the P4 static arm and was UNAVAILABLE for the whole of P3, so **C1 static
must not be worded as if the fifth metric is available statically.** It is
bracketed only on the closed-loop arm (§3.3). The P4 row's mechanism is traced
end-to-end and is not a tool failure: the bind succeeds, the row is emitted,
and the per-run extractor raises `MetricUnavailableError` on each cell-A static
run because `published_time.csv` is header-only — cell A's control publisher
advertises and stays silent while unengaged, 24/24 across every filed cell-A
static run. **The cause is not established**; an image/stack-configuration
hypothesis exists and is untested (`p4-transport-sweep.md` §2.4).

**What the bracket establishes, stated at the strength the data carries:**

- **Three of the four computable P3 separations were transport-bound.** Under a
  shared RMW (`A-vs-B-cyc`, static), `one_hop_wall_ms`, `lidar_to_ndt_sim_ms`
  and `achieved_rate_ratio` all return `parity`, where `A-vs-B` returned a
  separation outside the margin on every one. Per the rule pre-registered
  before any P4 run, the P3 separation on those three metrics is **attributed
  to the as-shipped Fast-DDS configuration, not to the approach.**
- **The M2 reconciliation corroborates it on a different quantity.** P3's cell B
  lost frames observer-side (`observer_loss_rate` median 0.085, max 0.108,
  against cell A's 0.000/0.000); cell B-cyc — same image, same launcher, only
  the middleware changed — reads 0.000/0.000 on both arms
  (`p4-transport-sweep.md` §2.3). **One row of that same table is not a
  transport result**: `publisher_drop_rate` fell on _both_ cells because of the
  spec's 1f instrument fix, applied symmetrically.
- **⬇ Equivalence is inconclusive on `carla_process_cpu_pct`, and the wording
  downgrades to the measured statement.** The row separates beyond its margin
  on the P4 static arm — so it is approach-bound under a shared transport
  family — but **in cell B-cyc's favour** (Δ = +52.0 pp), where P3's `A-vs-B`
  row was −12.9 pp in cell A's favour. The rule attributes the P4 separation;
  it does **not** license retro-attributing P3's, and **the two cannot both be
  an approach difference**. The cause of the reversal is **NOT established and
  no decomposition is attempted** (`p4-transport-sweep.md` §2.5). A registered
  confound runs against cell A on exactly this metric and was present unchanged
  in P3: cell A's `lidar_expected_hz` is 20.0 against B-cyc's 10.0, and cell A
  ships 2.118× the bytes for the same point count — **the +52 pp is not a
  like-for-like sensor load.**

### 3.3 C1(b), closed-loop arm — the campaign's first closed-loop verdict

**⚠ THIS IS AN `A-vs-B-cyc` VERDICT.** The `A-vs-B` closed-loop verdict, under
cell B's own registered transport, remains **non-computable** and is not
manufactured here: cell B armed on **0 of 15** closed-loop runs, all 15
excluded (`p3-baseline.md` §5.1). The two must not be conflated.

It exists because a **pre-declared failure branch did not fire**. The P4 spec
registered, before any data, that if B-cyc failed to arm the phase would
downgrade to static-only and record the finding. B-cyc armed and drove on the
first try; collection took one `duel.sh` invocation, zero exclusions, both
integrity checks 20/20 (`p4-transport-sweep.md` §3.1).

`A/run-026`…`035` vs `B-cyc/run-012`…`021`, n = 10/10 on **all five** metrics —
which P3 could not do for any of them:

| metric                  | Δ (A − B-cyc) | 95% CI           | margin | verdict    |
| ----------------------- | ------------- | ---------------- | ------ | ---------- |
| `one_hop_wall_ms`       | +1.345 ms     | [0.886, 1.942]   | 2.0    | **parity** |
| `lidar_to_ndt_sim_ms`   | +2.167 ms     | [1.882, 2.553]   | 5.0    | **parity** |
| `control_staleness_ms`  | −0.789 ms     | [−1.443, −0.288] | 10.0   | **parity** |
| `carla_process_cpu_pct` | +58.250 pp    | [57.662, 59.161] | 10.0   | `b_better` |
| `achieved_rate_ratio`   | +0.000        | [−0.000, 0.000]  | 0.02   | **parity** |

`control_staleness_ms` is **the metric P3 never had**: cell A's closed-loop arm
populates `published_time.csv` on 10 of 10 runs at a ratio of 1.000 against
each run's own `control_cmd` count, so the asymmetry in §3.2 is an **arm**
property of cell A, not a cell property (`p4-transport-sweep.md` §3.4).

**Two limits on this table, both from the wrap doc and neither optional.**
First, `one_hop_wall_ms`'s parity is the **weakest row in the phase**: the
metric is computed through a sim→wall affine fit whose max-abs residual median
is **54.60 ms** on the B-cyc closed-loop pool against **3.58 ms** on cell A's,
on a metric with a 2.0 ms margin — eight of ten B-cyc runs exceed 20 ms. These
are maxima over a run, not typical errors, but a reader who needs that row to
bear weight should treat it as weak (`p4-transport-sweep.md` §2.6, §7.1 P4-9).
Second, the `carla_process_cpu_pct` row carries the same reversal and the same
unresolved cause as §3.2.

**⬇ The wording that survives all of this:** on the closed-loop arm under a
shared transport family, the extension and tier4-native stacks are **within the
pre-registered margins on four of five metrics and separated beyond margin on
the fifth, in tier4-native's favour, for reasons this campaign did not
establish.** That is a bracketed workload-envelope statement — it is **not** a
claim that the approaches are equivalent, and `parity` is a decision against a
frozen margin, not a proof of identity (`p4-transport-sweep.md` §2.6).

### 3.4 Two findings that bound every C1 sentence

**The latched-delivery defect, and its attribution boundary.** Latched
(`TRANSIENT_LOCAL`) messages published once reached `topic_state_monitor_*`
promptly and **not** `behavior_path_planner`. Across the seven cell-B runs that
reached the arm and failed it, the planner named three different missing
inputs: map (2 runs), route (4), operation_mode (1). The map half was
reproduced standalone with no CARLA and no harness at all
(`p3-baseline.md` §5.1). **The defect is a property of the as-shipped tier4
transport configuration on this host. It is NOT established as an intrinsic
property of the tier4-native approach**, and no sentence in this report may be
read as though it were: Fast-DDS version, kernel and loopback behaviour are
uncontrolled, and the CycloneDDS configuration that works is itself registered
as not measurement-grade.

P4 sharpened it in both directions on the same probe, on a byte-identical
payload (`p4-transport-sweep.md` §3.2): under CycloneDDS the latched map was
already delivered **before any re-publish, on 12 of 12 runs**, verified in
6–27 ms; under Fast-DDS `B/run-031` never received it across three minutes.
**And the map leg is not the whole blocker** — `B/run-032` _did_ get its map
under Fast-DDS, in 7 ms, and **still failed to arm**. So the Fast-DDS side of
that comparison is **n = 2, not a rate**, and the closed-loop result rests on
the twenty filed runs rather than on the probe.

**Branch (c) — cell B's depressed NDT rate.** P3 left it **UNEXPLAINED**: Phase
0 eliminated double publication as the cause by pre-declared elimination and
identified none, and the M5 rate gate failed on **eight** of the ten cell-B
duel-pool runs (0.2569–0.8505; `B/run-013` passes at 0.9892, `B/run-019` is
unscoreable). The gate's 0.9 threshold was never touched, in either phase.
P4 closed it on its first pre-registered disjunct: B-cyc's ten static duel runs
read `ndt_rate_ratio` ≥ **0.9989** (min 0.998951, max 1.000000), so **the
depression is bound to the as-shipped Fast-DDS configuration**
(`p4-transport-sweep.md` §4). **Scope it exactly: that names where the cause
lives, not what it is.** Phase 0's finding that the double-publication
differential is real but not the cause stands unchanged.

### 3.5 C1(c) — the structural half

This half is argued from `docs/evaluation/rubric.md`, not from the measurement
harness, and it is where the extension's own weaknesses live. Every figure
below is summarised; the rubric carries the command or URL behind each.

**What supports C1(c):**

- **Unmerged footprint.** Extension: **219** fork commits ahead of
  `upstream/ue5-dev` + **25** in this repo. tier4-native: **305**. Bridge:
  **0** — it is in-tree (rubric criterion 3). The spec quoted 216 at
  spec-writing time; the fresh count is 219, +3, and both are reported.
- **Direction of travel.** The extension fork's two dominant authors have
  **66 merged of 98 opened PRs (≈ 67.3 %)** to `carla-simulator/carla` — a
  PR-count proxy the rubric labels as such, not a SHA-exact map onto the
  219-commit delta — and the
  spec's named mitigation chain `#9743`–`#9758` is confirmed merged on a
  number-by-number recheck. tier4-native's four Robotec/tier4-specific delta
  authors have **zero** PRs to `carla-simulator/carla` — a claim the rubric
  explicitly **rescoped** in fix round 1, because several other delta authors
  are shared-ancestor CARLA-community contributors with large upstream
  histories (rubric criterion 4).
- **Maintenance signal.** `tier4/autoware-support`'s tip is dated
  **2026-04-08** with **0** commits in the 90 days before the snapshot, its CI
  has fired **once ever** on that branch (a dependency-bump automation event,
  2025-09-15), and the branch is **frozen** at the ruleset level (rubric
  criteria 7, 9, and the corrected criteria 1–2).

**What does not, and is stated at the same volume:**

- **C1(c) does not mean "no fork today."** The extension requires building the
  CARLA fork's UE5.5 source tree from scratch — **the fork is the artifact** —
  exactly as tier4-native does. On rubric criterion 5 ("runs against an
  official upstream CARLA release binary"), extension **No**, tier4-native
  **No**, bridge **Yes**. That is the single largest real-world adoption
  differentiator in the rubric, and it does not favour either native approach.
- **Bus factor is the extension's weakest row.** This repo: **1** maintainer,
  25/25 commits by one author, **0** external reviewers across 30 PRs, the only
  recorded reviews being two self-reviews; no CODEOWNERS, and `main`'s ruleset
  requires passing checks, not a human approval. tier4-native's own branch is
  no better governed but is at least two-contributor dominated; the bridge has
  4 named maintainers and 9 human authors in 12 months (rubric criteria 1, 6).
- **No approach runs a live CARLA+Autoware loop in CI**, this one included; its
  G0–G3 gates are run manually (rubric criterion 9).

**⬇ So C1(c) downgrades to what the snapshot supports:** the extension carries
a **smaller** unmerged delta than tier4-native, on a branch that is **actively
upstreaming** where the comparator's is frozen and un-upstreamed — but it is
**not** fork-free today, and it is **solo-maintained with no external review**,
which is a governance risk the comparator's numbers do not offset.

## 4. C2 — python-bridge limits

### 4.1 The arms, and the one that does not exist

| arm       | image                  | what it is                               | status                |
| --------- | ---------------------- | ---------------------------------------- | --------------------- |
| **E0**    | `bridge-bench`         | as shipped (`frequency_hz: 11`)          | 5-run static pool     |
| **E**     | `bridge-bench-patched` | harmonized kit, both patches applied     | 6 valid static runs ⬇ |
| **E-opt** | `bridge-bench-patched` | `create_cloud` → `tobytes()` sensitivity | **STRUCK — no data**  |

**⚠ E-opt was struck by the owner's 2026-07-30 scope cut
(`p3-baseline.md` §2.2), and this removes a capability C2 was designed to
have.** The spec registered E-opt as a _measurement control_ whose explicit
purpose was to separate the architecture's cost from a known ~20-line
implementation defect in the per-point packer — without it, C2's headline
number is not decomposable and a maintainer could in principle neutralise part
of it with one PR. **This report therefore makes no claim that separates
architecture from implementation on the bridge's publish path.** Every C2
sentence below is scoped to E0 or E as measured, and the separation the spec
wanted is recorded as **not measured**, not as an inference.

### 4.2 E0 — the bridge as its authors ship it

**⚠ EVERY E0 CENTRAL-TENDENCY STATEMENT IS OPTIMISTICALLY BIASED, BY A
MECHANISM CORRELATED WITH E0's OWN REGISTERED FAILURE, AND THE BIAS CANNOT BE
ESTIMATED FROM THE SURVIVING POOL.** `E0/run-005` and `run-006` were excluded
because NDT published **exactly one** pose each, which makes the cadence
function raise and the run fail its smoke step; the five pooled runs carry
8 / 17 / 8 / 6 / 6 NDT poses against the two dropped runs' 1 / 1. The pool is
therefore E0's behaviour **conditioned on NDT having emitted at least two
poses** — the campaign registered "deliberately no quality-based criterion",
and this is a quality-based exclusion arriving through a registered criterion's
back door (`p3-baseline.md` §6, quoting PROVENANCE §9.9). **The excluded runs'
data is retained in full and is the stronger evidence for E0's registered
failure, not weaker.** `E0/run-001` is deliberately **not** pooled as a sixth
run: it carries 10 NDT poses, more than four of the five pooled runs, so
pooling it would push an already-upward-biased pool further up
(`p3-baseline.md` §6.1).

With that caveat attached, the as-shipped arm's own numbers
(`p3-baseline.md` §3, cell E0; pool `E0/run-002`, `003`, `004`, `007`, `008`;
all rates are **arrival-domain**, see 4.5):

| topic on cell E0                      | rate across the pool | context                   |
| ------------------------------------- | -------------------- | ------------------------- |
| `pose_estimator/pose_with_covariance` | **0.08 – 0.27 Hz**   | NDT, structurally starved |
| `localization/kinematic_state`        | 13.37 – 14.19 Hz     | EKF output                |
| `lidar/top/pointcloud_before_sync`    | 8.36 – 8.43 Hz       | at 1.04–1.05 MB/s         |
| `control/command/control_cmd`         | 2.11 – 4.13 Hz       | not a control loop        |

The one E0 run the M5 gate ever scored, `E0/run-003`, reads `ndt_rate_ratio`
**0.038** (`p3-baseline.md` §6). **This is E0's registered expected outcome,
written down in advance** — PROVENANCE §9.3: "Cell E0 is expected to be
UNSCOREABLE, and that is its registered result." It is not a surprise finding
and is not presented as one.

### 4.3 E — the harmonized arm, and its static-only downgrade

Cell E applies both patches: `is_dense=True` and the harmonized kit (16 ch /
288 000 pts/s / range 100 / FOV ±15, `frequency_hz` 11 → 20, cameras dropped
from the enabled list, `multi_camera_combiner` disabled, GNSS covariance
diagonal harmonized to the extension's values). Its six valid static runs are
`E/run-011`…`run-016` (`p3-baseline.md` §3, cell E):

| topic on cell E                       | rate across the six runs | context           |
| ------------------------------------- | ------------------------ | ----------------- |
| `pose_estimator/pose_with_covariance` | **1.91 – 7.52 Hz**       | NDT               |
| `localization/kinematic_state`        | 19.32 – 19.94 Hz         | EKF output        |
| `lidar/top/pointcloud_raw_ex`         | 19.83 – 19.91 Hz         | at 2.19–2.20 MB/s |

**⬇ CELL E'S CLOSED-LOOP ARM PRODUCED NO DATA, AND THE DOWNGRADE WAS
PRE-REGISTERED.** `E/run-009` reached `mode=2 autonomous=True
is_autoware_control_enabled=True` and then failed on the gated control command
(`control_cmd_hz~0.00 n=0`), excluded `gate:arm-failed`; its failing link is
**the route** (`behavior_path_planner: waiting for route` persists 63.98 s past
`set_waypoint_route`, and `waiting for map` never appears) — a _different_
failing link from cell B's, so one diagnosis does not unblock both. The
static-only downgrade was registered precisely so this case would not need a
decision taken after seeing a failure, and it fired (`p3-baseline.md` §6.2).

**The consequence, stated so it cannot be misread: the python-bridge approach's
closed-loop evidence is STRUCTURAL, not measured.** Nothing in this record may
be read as the bridge having been measured closed-loop and found wanting. **It
was never measured closed-loop at all, because it could not be armed.**

### 4.4 The byte-rate lower-bound argument — as registered, and as measured

The spec registered a specific lower-bound argument for C2: that the bridge's
16 B/point layout against the natives' 32 B/point means its ceiling is reached
at roughly half the byte rate, which would make any measured gap a **lower
bound** on the architectural gap.

**That argument is NOT backed by a filed measurement in this campaign, and this
report does not assert it.** What the tree actually registers about point
layout is a different fact about a different cell: `benchmarks/README.md`
`:3986-4018` records that **cell A** ships **2.118×** the bytes for the same
point count (512 184 B/msg against 241 813 B/msg, `bench_observer` medians),
and that **cell B's running binary emitted a 16 B/point cloud where its own
pinned source specifies 32 B/point** — a contradiction registered as
**UNRESOLVED**, with a stale build artifact as the leading hypothesis. No
per-point layout measurement of the E-family cells exists anywhere in
`benchmarks/`. The spec's premise about the bridge's layout is therefore
recorded here as **unmeasured**, and no lower-bound multiplier is derived from
it.

What the campaign does hold is an **observed byte rate per cell, on each cell's
own registered LiDAR topic**, over the frozen per-cell observer topic list.
Because the observer records only that list and not the whole graph, an
observed rate is a **lower bound on the cell's total published byte rate** —
which is the only lower-bound property this report claims.

| pool                 | LiDAR topic observed         | observed MB/s | **generation caveat (inline)**                                                                            |
| -------------------- | ---------------------------- | ------------- | --------------------------------------------------------------------------------------------------------- |
| `A/run-003`…`012`    | `.../pointcloud_raw_ex`      | 10.25 – 10.26 | CARLA 0.10 fork, UE5.5 source build, `editor-game`                                                        |
| `B/run-013`…`022`    | `.../pointcloud_raw_ex`      | 2.10 – 2.25   | CARLA 0.10 tier4 fork, UE5.5 source build, `editor-game`                                                  |
| `E/run-011`…`016`    | `.../pointcloud_raw_ex`      | 2.19 – 2.20   | **stock CARLA 0.9.15 — different simulator generation, different container; not comparable as a ranking** |
| `E0/run-002`…`008`\* | `.../pointcloud_before_sync` | 1.04 – 1.05   | **as above, plus a different topic and the shipped 11 Hz throttle**                                       |

\* the five pooled E0 runs, i.e. `run-002`, `003`, `004`, `007`, `008` — read
with §4.2's bias caveat, which applies to this row as to every other E0 figure.

**This is not a ranking table and no ordering claim is drawn from it.** The
generation caveat is carried in-row per the spec's honesty constraint; the
cells differ in simulator generation, container, sensor rig, publish throttle
and observed topic simultaneously, and no statistic was computed across them in
either phase. All four rows are read off the per-cell tables in
`p3-baseline.md` §3.

### 4.5 What C2 does NOT say

- **It is not an equivalence or ranking statistic.** No cross-approach
  equivalence statistic was computed in either phase and none may be inferred
  (`p3-baseline.md` §4.3, `p4-transport-sweep.md` §2.6). The E family is
  context, not a duel side.
- **The `hz` figures above are arrival-domain and must not be cross-read
  against §3's `achieved_rate_ratio`**, which is computed on `header_stamp_ns`
  in the sim domain, deliberately, so the simulator's real-time factor cannot
  land inside a 0.02 margin. They are different quantities on the same topic
  (`p3-baseline.md` §3).
- **No renderer or engine difference is attributed to the bridge.** The E-vs-E0
  contrast is the load-bearing one and is **within** the approach: same CARLA
  0.9.15, same container family, differing by the patch set alone — which is
  that pair's whole purpose (`p3-baseline.md` §7.1 P3-5).
- **⬇ The E family is gated on the G1 ladder's RELATIVE branch**
  (`ladder_branch: relative`, `abs_pose_gate_m: null`), because E/E0 run the
  deliberately unshifted `autoware_contents` Town10 pcd carrying a +0.475 m
  cross-track offset. **Four of cell E's six scored runs have
  `pose_err_max_m` > 0.5 m and would have failed an absolute gate by map
  registration** — under a heading a reader would wrongly attribute to the
  bridge (`p3-baseline.md` §7.1 P3-3). **No absolute localization-accuracy
  claim is made about the bridge anywhere in this report.**
- **Cell E0's exclusion mechanism is not a harness defect and is not repaired.**
  E0 is not re-collected; the four grounds are in `p3-baseline.md` §8.3.

## 5. C3 — the gap roadmap

**C3 is not sourced from either measurement document.** It is
`docs/evaluation/gap-catalog.md`, argued from **code reading of both local
trees** at pinned SHAs — no live `ros2 topic echo`, no running stack and no
runtime measurement backs any verdict in it, and six entries carry a **scoped**
`needs prototype` marker where that method reaches its edge
(gap-catalog §5.0, §7.4).

**53 capability entries. Every one has a reproduction path on the extension
architecture; none is unreachable.**

| class                              | main (§5) | side branches (§6) | total  |
| ---------------------------------- | --------- | ------------------ | ------ |
| already-exists                     | 11        | 3                  | 14     |
| extension-side work                | 4         | 4                  | 8      |
| CARLA-core seam work — sensor-side | 6         | 15                 | 21     |
| CARLA-core seam work — ROS-side    | 7         | 3                  | 10     |
| **entries**                        | **28**    | **25**             | **53** |

Effort classes: main **25 × S, 3 × M**; side branches **13 × S, 8 × M, 4 × L**
(gap-catalog §5.0.4, §6.0.3). A class is the **remaining delta from this
repository's side**, not the size of tier4's original change, and classes are
**per-entry, not cumulative**.

**The single most decision-relevant fact in the catalog, in its own words:**
the side-branch half skews far harder toward CARLA-core seam work — **18 of 25,
against 13 of 28 on main** — i.e. main's capabilities are largely ROS-layer and
the side branches' largely are not (gap-catalog §6.0.3).

Three limits the catalog states about itself and this report carries forward:

- **"Unmerged" is relative to the instructed baseline.** Nine of the branches
  cataloged as side branches are already merged into `tier4/main`, whose tip is
  byte-identical to `feature/vehicle-sim-package`'s. Calling them experimental
  would be wrong (gap-catalog §6.0.2).
- **A shallow shared clone broke `git merge-base` for 15 of 65 branches**;
  their "commits ahead" figures are the best available signal, not verified
  merged-ancestor status (gap-catalog §1.2).
- **The `already-exists` verdicts were adversarially re-argued** against the
  _extension_ files they cite — the side carrying the overclaim risk. **None
  was overturned**; four gained a missing fact, one was retitled, one gained a
  maturity qualifier (gap-catalog §7.2).

## 6. Community-acceptance rubric

`docs/evaluation/rubric.md` carries 11 criteria across the three approaches,
each with a pre-registered direction and a value cell traceable to a command or
a linked observation. **It computes no total and this report adds none.**

Summarised, without re-deriving any cell:

| criterion                    | what the snapshot found                               |
| ---------------------------- | ----------------------------------------------------- |
| 1–2 governance / who accepts | AWF org but sole author; tier4 branch frozen, no gate |
| 3 unmerged artifact set      | 219 + 25 vs 305 vs 0                                  |
| 4 upstreamed ratio           | ≈ 67.3 % merged (proxy) vs 0 (scoped) vs N/A          |
| 5 runs on a release binary   | No / No / **Yes**                                     |
| 6 bus factor                 | 1 / 2 contractors / 4 named + 9 human authors         |
| 7 activity                   | young repo (annotated) / 0 in 90 d / 8 in 90 d        |
| 8 install complexity         | UE5.5 source build / UE5.5 + ~300 GB, 3–4 h / binary  |
| 9 CI on the integration path | none live in any of the three                         |
| 10 license                   | Apache-2.0 / MIT / Apache-2.0 — all compatible        |
| 11 documentation             | 8 docs / 1 branch README / 1 README                   |

Read the rubric itself for the cells; each carries its own corrections from an
adversarial re-verification round that overturned four cells and recorded one
process slip in place rather than rewriting it.

## 7. Confound table

Every row cites the measurement or the pin that establishes it.
`p4-transport-sweep.md` §7.2 is the authority on which P3-era rows still bind
for P4 and which two are **retired** — this table takes its carry-forward from
there, not from `p3-baseline.md` §7 alone. "README" means `benchmarks/README.md`.

| #   | confound                                                                                | binds             | where registered                        |
| --- | --------------------------------------------------------------------------------------- | ----------------- | --------------------------------------- |
| 1   | CARLA generation: stock 0.9.15 `shipping-headless` vs 0.10 fork `editor-game`           | E/E0 vs all       | P3 §7.1 P3-4; per-run `manifest.json`   |
| 2   | Map assets: E/E0 on the unshifted Town10 pcd (+0.475 m); A/B/B-cyc on rung-2 regen      | all               | P3 §7.1 P3-3; P4 §7.2                   |
| 3   | GNSS: GT anchor per-approach (extension +0.000 m, bridge −1.425 m); covariance patched  | E/E0 vs A/B       | README `:1097`, `:1132`; patches README |
| 4   | RMW pairing: B on Fast-DDS + `udp_only.xml`; P4 rmw-matched but NOT profile-matched     | B, B-cyc          | README `:1323`; P4 §7.1 P4-2            |
| 5   | Row-11 inherited caveats: Cyclone-no-profile binds a routable NIC, graph is flaky       | B-cyc             | P4 §7.1 P4-3                            |
| 6   | Point layout bytes: A ships 2.118× bytes/msg; B's wire `point_step` 16 vs pinned 32     | A vs B            | README `:3986-4018`                     |
| 7   | Publisher QoS and endpoint config differ per approach; observer RMW follows the cell    | all               | P3 §7.1 P3-2; gap-catalog §5.16         |
| 8   | Sensing graph: `carla_sensor_kit` vs `awsim_labs_sensor_kit`; relay on the concat topic | E vs A/B/C        | README `:1059`; P3 §5.2                 |
| 9   | Container / process placement and images; observer is `network_mode: host`              | all               | P3 §7.1 P3-4; P4 §7.1 P4-4              |
| 10  | Pacing: `duel.sh` gained inter-run pacing mid-campaign; sweep paced/unpaced arms        | all               | P3 §8.4 #1; P4 §6.4                     |
| 11  | Physics substepping: the B family disables it at 20 Hz, A leaves the default on         | A vs B/B-cyc      | README `:1249`; P4 §7.2                 |
| 12  | Autoware version skew: B/B-cyc `universe-devel-cuda` by digest vs A by tag; B45 struck  | A vs B/B-cyc      | P4 §7.1 P4-1; P3 §2.2                   |
| 13  | Perception off: clear-road dummy stand-in vs the bridge family's real CUDA perception   | A/B/C vs E family | README `:1025`                          |
| 14  | Fork delta magnitudes: 219 (+25) vs 305 vs 0                                            | structural        | rubric criterion 3                      |
| 15  | Sensor-rate asymmetry: `lidar_expected_hz` 20.0 (A) vs 10.0 (B/B-cyc), against A        | A vs B/B-cyc      | P4 §7.1 P4-5                            |
| 16  | Clock-fit residual asymmetry: B-cyc closed-loop 54.60 ms vs A 3.58 ms, margin 2.0       | A vs B-cyc        | P4 §7.1 P4-9                            |
| 17  | CAL-seam residuals: publish order (sign NOT established), in-core-only sample loss      | CAL-seam          | P4 §7.1 P4-8                            |
| 18  | Static pre-arm control silence: 2 of 10 B-cyc static runs, unmasked on that arm         | B-cyc             | P4 §7.1 P4-7                            |
| 19  | `control_mode`: A reports MANUAL parked, tier4 reports AUTONOMOUS unconditionally       | A vs B            | P3 §7.1 P3-6                            |
| 20  | Observer + G1 ladder rung 2: not reproducible from its pin, coverage ~292 m of 438.9 m  | all               | P3 §7.1 P3-2                            |
| 21  | Route difficulty: Town10 vs Nishi-Shinjuku (cell C is confirmatory only)                | A/B vs C          | README `:902`                           |
| 22  | Localization initialization: the stop check blocks every path on cell B                 | B, B-cyc          | README `:1400`                          |

Rows 1–3 are why bridge and native figures never share a ranking table here
without the caveat in-row (§4.4), and row 19 is deliberately **unpatched**:
whether an approach reports its own control mode correctly is part of the
interop completeness being compared.

**Two P3 rows are retired and are not carried forward**
(`p4-transport-sweep.md` §7.2): CAL-seam's "`C1(a)` is UNMEASURED" (it is
measured — §3.1), and the fabricated non-zero `publisher_drop_rate` — retired
**for P4 pools only**, by a harness fix applied symmetrically to both cells.
**P3's pools were not re-scored and the artefact remains in the P3 record**, so
it still bounds every P3 figure in §3.2.

**Deviations, complete and not summarised away:** `p3-baseline.md` §8.1–§8.6
and `p4-transport-sweep.md` §8.1–§8.4. They include a teardown defect that left
the Autoware stack up on 5 of 10 cell-B static runs (invalidating none), the
duel's 6/4 first-slot alternation, `-dirty` harness shas on both sweep pools,
and — recorded at branch level rather than task level — that
`benchmarks/analysis/manifest.py`, a frozen path, was **amended twice** under
the pre-registration's own amendment rule, with both entries in the README's
amendment ledger.

## 8. Honesty-constraints checklist

Each constraint is ticked with **the mechanism that enforced it**, not with an
assertion that it holds.

| #   | constraint (spec, Global Constraints)                                                          | mechanism in this document                                                                                                                                                                                                                                                                                                                                                                   |
| --- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **No composite acceptance score**                                                              | `rubric.md` carries a "No composite score" banner as its own section; this report contains **no ranking table, no weighting and no total**. §6 summarises per criterion and links out; §3–§5 report per metric and per entry.                                                                                                                                                                |
| 2   | **Bridge and native numbers never share a ranking table without the generation caveat inline** | Exactly one table places an E-family figure beside a native one (§4.4). It carries a **generation-caveat column filled per row**, and the sentence under it states it is not a ranking and draws no ordering. All other E/E0 figures live in §4's own arm-scoped tables.                                                                                                                     |
| 3   | **No attribution of UE4-vs-UE5 renderer/engine differences to the bridge**                     | C2's load-bearing contrast is **E vs E0**, within one approach, one CARLA version and one container family, differing only by the patch set (§4.1–§4.3). No cross-generation delta is computed anywhere. The publish-disabled ablation arm exists only inside cells A and B-cyc and is registered **within-cell only** (§7 row 15; P4 §6.4).                                                 |
| 4   | **E2E latency under a 20 Hz sim clock is context, never C1 evidence**                          | C1 rests **only** on the five pre-registered margin metrics (§3.2, §3.3) and the C1(a) paired delta (§3.1). The ~51–53 ms arrival-domain figures on cell A are one sim tick and appear nowhere in §3; the arrival-domain rates quoted in §4 are labelled as such, and §4.5 restates the prohibition on cross-reading them against `achieved_rate_ratio`.                                     |
| 5   | **Every number carries its cell/run reference**                                                | Every figure names its pool (`A/run-016`…`025`, `CAL-seam/run-001`…`005`, `E0/run-002`…`008`, …) or the census that produced it, plus the wrap-doc section that owns it.                                                                                                                                                                                                                     |
| 6   | **Every C1/C2 sentence names its arm**                                                         | C1 sentences name `A-vs-B` or `A-vs-B-cyc` **and** static or closed-loop; C2 sentences name E0, E, or the struck E-opt. §0 rule 2 states the discipline; §3.2/§3.3 headings carry the arm; §4.1 fixes the three C2 arms before any C2 number is quoted.                                                                                                                                      |
| 7   | **Wording downgrades the data forced are applied mechanically**                                | Marked ⬇ at each site: equivalence **inconclusive** on static `control_staleness_ms` and on `carla_process_cpu_pct` (§3.2, §3.3); A-vs-B closed-loop **not computable** (§1.2, §3.3); C1(a) an **upper bound** (§3.1); C1(c) rescoped (§3.5); cell E **static-only** (§4.3); the E family on the **relative** G1 branch (§4.5); the spec's bridge byte-layout premise **unmeasured** (§4.4). |
| 8   | **Mandatory caveats travel inline**                                                            | The four-of-five static bracket, A-vs-B-cyc-not-A-vs-B, C1(a)-upper-bound and E0-optimistic-bias caveats each appear **in the paragraph that quotes their figures** (§3.2, §3.3, §3.1, §4.2), not in a trailing caveats section.                                                                                                                                                             |
| 9   | **Nothing is recomputed, no verdict is manufactured**                                          | This task ran no verdict tool and read no filed run. Both wrap docs computed their verdict **once**, with no filtering flags, and reproduce their full output verbatim; §9 gives the commands and the SHAs so a reader regenerates rather than trusts.                                                                                                                                       |
| 10  | **Refuted hypotheses stay in the record with the diagnostic that refuted them**                | Carried, not dropped: Phase 0's publisher-count-vs-emission error and its causal-wording refutation (§3.4), the `B/run-032` correction to the delivery-probe reading (§3.4), C1(a)'s retracted conservatism argument (§3.1), and the spec's own bridge byte-layout premise (§4.4).                                                                                                           |

**Known residual weaknesses of this report, stated rather than left to the
reviewer:** the C1(a) publish-order residual's sign is unestablished; the
`carla_process_cpu_pct` reversal is unexplained and is the largest thing P4
discovered and did not resolve; the A-vs-B closed-loop verdict is permanently
non-computable from this data; E-opt's absence blocks the
architecture-versus-implementation split C2 was designed to make; and the
extension's own governance row (solo author, zero external review) is its
weakest structural evidence.

## 9. Regeneration appendix

**No number in this report requires re-collection.** Every figure regenerates
from committed raw data plus committed scripts. The two phases pin the commits
they were generated at, and **those pins are reused here rather than
re-derived**:

| phase                        | pinned at                                                                                           | source             |
| ---------------------------- | --------------------------------------------------------------------------------------------------- | ------------------ |
| P3 (`p3-baseline.md`)        | `269b931`                                                                                           | its §0 and §10     |
| P4 (`p4-transport-sweep.md`) | `fcb83334637b6c7be6e7fda88da2ce2dd0f77c46`                                                          | its §0.1 and §10   |
| rubric snapshot              | `dd37379` → `324dc36` → `16e6757`, retrieved 2026-08-05T02:13 UTC                                   | `rubric.md` header |
| gap catalog                  | `tier4/autoware-support` @ `6315b856f8faf2118578322eb20a2b902a45a384`, fetched 2026-08-04 23:15 UTC | gap-catalog §1.1   |

All commands run from the repository root.

```bash
# 1. Per-cell tables (both phases). Exits 1, and the exit is fully explained
#    by cell CAL-rmw, which has no simulator and therefore no /clock.
PYTHONPATH=. python3 -m benchmarks.report benchmarks/results > /tmp/report-tables.md

# 2. The P3 duel verdict -- the campaign's single P3 invocation.
PYTHONPATH=. python3 benchmarks/scripts/duel_verdict.py A B | tee /tmp/p3-duel-verdict.md

# 3. The P4 duel verdict -- P4's single invocation. Both arms come from this
#    one run. Use `>` not `| tee`: an rtk proxy compresses piped output here.
PYTHONPATH=. python3 benchmarks/scripts/duel_verdict.py A B-cyc > /tmp/p4-duel-verdict.md

# 4. C1(a): the CAL-seam paired delta (section 3.1).
for r in 001 002 003 004 005; do
  PYTHONPATH=. python3 -m benchmarks.scripts.cal_report benchmarks/results/CAL-seam/run-$r
done

# 5. M4 ceiling tables (section 1.3's "not located up to the 32ch class").
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py A     --class vlp16
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py A     --class 32ch
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py B-cyc --class vlp16
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py B-cyc --class 32ch

# 6. Per-cell metric bindings quoted throughout.
PYTHONPATH=. python3 -c "from benchmarks.scripts.cell_info import load_cells_doc, metrics_for; \
  d=load_cells_doc(None); print(metrics_for(d,'A')); print(metrics_for(d,'B-cyc'))"

# 7. Identity / provenance census -- all of P4's section 9.
PYTHONPATH=. python3 benchmarks/evidence/p4-task16-wrap/identity_walk.py

# 8. The rubric snapshot (section 6).
bash scripts/evaluation/rubric_snapshot.sh

# 9. The test-suite baseline.
python3 -m pytest tests/ -q
```

Four walks are given verbatim in the wrap docs rather than repeated here,
because repeating a script is how two copies drift: the per-run manifest
classification (`p3-baseline.md` §2.1), the duel-pool census
(`p4-transport-sweep.md` §10 command 3, which also produces §2.4's exclusion
counts), the `ndt_rate_ratio` walk (command 5) and the clock-fit residual walk
(command 6).

**Collection is a different operation and is not needed to check anything
above.** A cell is collected with `bash benchmarks/run.sh <cell> [--arm ...]`,
and interleaved duel pairs with `benchmarks/scripts/duel.sh`; re-running either
would produce **new** runs, not the filed ones. Every figure in this report is
pure analysis over `benchmarks/results/`, which is committed.
