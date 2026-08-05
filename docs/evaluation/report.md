# Evaluation report: three CARLA↔Autoware integration approaches

**Assembled 2026-08-05 (P6 Task 6).** This document argues claims **C1–C3** of
`2026-07-27-three-approach-evaluation-design.md` from evidence that already
exists in this repository. It **computes nothing**. Every figure below is quoted
from a document that computed it once, with the section that owns it named
beside the number.

Sources, and the only ones:

| source                                                                     | what it owns                                                |
| -------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `docs/evaluation/p3-baseline.md`                                           | the P3 record: cells, A-vs-B verdict, E-family data         |
| `docs/evaluation/p4-transport-sweep.md`                                    | the P4 record: A-vs-B-cyc verdicts, C1(a), M4               |
| `docs/evaluation/gap-catalog.md`                                           | C3 — the 53-entry capability catalog                        |
| `docs/evaluation/rubric.md`                                                | the community-acceptance snapshot                           |
| `benchmarks/` (README, config, results)                                    | the pre-registration, patches, and raw runs                 |
| `benchmarks/results/PROVENANCE.md`                                         | every bare "PROVENANCE §N" citation below resolves **here** |
| `2026-07-27-three-approach-evaluation-design.md` (⚠ **out of repository**) | C1–C3's registered wording and §8's honesty constraints     |

**⚠ The design spec is not in this repository and a reader cloning this branch
cannot check it.** It is a superpowers spec document kept outside the target
repo by convention (`~/src/claude-superpowers/autowarefoundation/carla-autoware-extension/specs/2026-07-27-three-approach-evaluation-design.md`
on the author's machine; the campaign's own operator notes record the
convention). Everything the spec is the sole authority for — C1(a)/(b)/(c) and
C2/C3's registered wording (§3, §4, §5), the E-opt measurement-control framing
(§4.1), the byte-layout lower-bound argument (§4.4), the static-only downgrade
(§1.3, §4.3), and the **entire left column of §8's checklist** — is therefore
**not independently checkable from this repository**, and §8's checklist should
be read as self-certifying until the spec is published. Where the spec's own
words are load-bearing they are quoted verbatim below rather than paraphrased,
which is the most this document can do about it. (§8's left column previously
cited a "Global Constraints" heading the spec does not have; its actual heading
is "**Honesty constraints (what the report must NOT claim)**", and the label is
corrected in §8.)

## 0. How to read this document

**Six rules are applied mechanically, not case by case.**

1. **Every number carries its cell and run range.** A figure without a pool is
   not reportable here.
2. **Every C1 sentence names its arm** — `A-vs-B` (P3, **NOT rmw-matched**:
   cell A on `rmw_cyclonedds_cpp` with `docker/cyclonedds.xml`, cell B on
   `rmw_fastrtps_cpp` + `observer/config/udp_only.xml`, so every P3 duel row is
   a **cross-vendor** comparison — `benchmarks/README.md`, "DDS middleware and
   transport (Task 9)") or `A-vs-B-cyc` (P4, both cells on CycloneDDS,
   rmw-matched but **not** profile-matched), and `static` or `closed-loop`.
   **Every C2 sentence names its arm** — `E0` (as-shipped), `E`
   (harmonized/patched), `E-opt` (packer-optimized). E-opt was **struck**;
   see 4.1.
3. **Caveats travel with their numbers, inline**, not in a footnote section.
   **Five** are mandatory and appear at every quotation of the figures they
   bound: the static bracket's **four-of-five** metric coverage; the closed-loop
   verdict being **A-vs-B-cyc, not A-vs-B**; C1(a) being an **upper bound, not
   a point estimate**; cell E0's pool being **optimistically biased**; and — as
   of this revision — the **Autoware image confound**, which
   `p4-transport-sweep.md` §1 calls "**the single most important one**": cell
   B-cyc runs the same `universe-devel-cuda` image (by digest) as cell B by
   deliberate design and cell A runs `universe-devel` (by tag), so **every
   A-vs-B-cyc row in this document also spans an Autoware image difference, and
   no row is corrected for it** (P4 §7.1 P4-1; §7 row 12). It was previously
   carried only as a confound-table row, which is not adequate for a caveat its
   own source flags as the most important one.
4. **Wording downgrades the data forced are applied as written and are not
   re-litigated** anywhere in this document: equivalence is **inconclusive**
   where a metric did not compute, cell E is **static-only**, and the E family
   is gated on the **relative** G1 ladder branch. Each is marked ⬇ where it
   applies.
5. **A P3 figure and a P4 figure never share a sentence without the P4↔P3
   identity caveat inline** (`p4-transport-sweep.md` §9): the engine BuildId and
   the harness sha both moved between phases. The attribution bracket therefore
   sets **verdicts computed entirely within one phase** against each other, and
   **no per-cell margin-metric absolute is compared across phases.** One
   cross-phase per-cell comparison does appear — the M2 `observer_loss_rate`
   bullet in §3.2 — because `p4-transport-sweep.md` §2.3 draws it itself; it is
   not a margin metric, and it restates the identity caveat in its own
   sentence. The rule is stated this way rather than absolutely, because a rule
   the document does not follow is worse than a narrower one it does.
6. **No composite score, and no ranking table.** Per-criterion and per-metric
   evidence only.

**What this document is not.** It is not a "which approach wins" study; the
spec says so in terms. **No equivalence statistic was computed between the
python-bridge family and either native approach**, in either phase, and none
may be inferred: the E family and cell C are **not duel sides**
(`p3-baseline.md` §4.3, `p4-transport-sweep.md` §2.6 — "The E family and cell C
are not in this duel"). That is the scope of the prohibition, stated precisely
rather than absolutely, because §2.2 and §§3.2–3.3 **do** report ten TOST
equivalence decisions between the `extension` and `tier4-native` approaches and
a rule this document does not follow would be worse than a narrower one it
does. It is not a re-scoring: no filed run was
re-scored, reclassified or read-modify-written by this task. Its only read of
`benchmarks/results/` is the read-only per-cell census behind §1.2 and §2.4,
which opens each run's `manifest.json` and nothing else (appendix command 10).

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

**191 manifests are filed across eight cells; 37 are excluded.** Every count in
this section and in §2.4 is reproduced by **appendix command 10**, a read-only
`manifest.json` walk that prints filed and excluded totals per cell with each
cell's exclusion reasons.

| cell       | approach      | CARLA      | map           | filed | excluded | role                                                       |
| ---------- | ------------- | ---------- | ------------- | ----- | -------- | ---------------------------------------------------------- |
| `A`        | extension     | 0.10-fork  | Town10HD_Opt  | 53    | 0        | duel side A, P3 **and** P4 — **CycloneDDS in both phases** |
| `B`        | tier4-native  | 0.10-tier4 | Town10HD_Opt  | 33    | 15       | duel side B, P3 (Fast-DDS + `udp_only.xml`)                |
| `B-cyc`    | tier4-native  | 0.10-tier4 | Town10HD_Opt  | 45    | 6        | duel side B, P4 (CycloneDDS)                               |
| `C`        | extension     | 0.10-fork  | Nishishinjuku | 14    | 2        | confirmatory, never duel data                              |
| `E0`       | python-bridge | 0.9.15     | Town10HD_Opt  | 10    | 4        | bridge as shipped — context only                           |
| `E`        | python-bridge | 0.9.15     | Town10HD_Opt  | 16    | 10       | bridge harmonized, **static only** ⬇                       |
| `CAL-rmw`  | none          | —          | —             | 15    | 0        | transport calibration, no simulator                        |
| `CAL-seam` | extension     | 0.10-fork  | Town10HD_Opt  | 5     | 0        | C1(a) seam-vs-in-core isolation                            |

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

**⚠ The P3 duel is CROSS-VENDOR, and the label above says only which RMW cell B
ran.** `benchmarks/README.md`'s "DDS middleware and transport (Task 9)" section
registers three distinct configurations: cells **A and C run
`rmw_cyclonedds_cpp` with `docker/cyclonedds.xml` (`lo` only)**; the E family
runs `rmw_fastrtps_cpp` at the image default; and **only the B family runs
`rmw_fastrtps_cpp` + `observer/config/udp_only.xml`**. So every number in the
P3 `A-vs-B` column of §3.2 compares the extension on the transport it was
tuned for against tier4-native on one it cannot select, and that is the single
largest caveat on the P3 side of the bracket — it is the reason P4 exists. It
is stated here, in §0 rule 2, in §3.2's column header and in §7 row 4 rather
than once, because "(Fast-DDS)" alone reads as if both cells were on Fast-DDS.

**The two P3 duel-pool conditions that are not homogeneous, stated at the pool
rather than left to a deviations list.** `duel.sh` gained inter-run pacing (a
120 s floor plus a bounded load-triggered top-up) **mid-campaign**, i.e. inside
this ten-pair pool: **pair 1 (`A/run-003`, `B/run-013`) predates it and sits on
harness sha `177256e`, pairs 2–10 on `5a28339`**, and pair 1's ~31.5 s inter-run
gap is **reconstructed from committed byte content, not recorded**
(`p3-baseline.md` §8.4 #1, #4). Inter-run host-idle time is a registered
measurement condition, so this is a dated amendment, not a transparent bugfix.
Pair 1 was neither excluded nor re-run, and **no leave-pair-1-out sensitivity
check on the four computable P3 verdicts was performed** — its absence is
recorded here as a limitation rather than implied by silence (§8).

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

**On the E family's CARLA generation, stated once here so the confound rows
below are not read as a staleness charge.** **CARLA 0.9.15 is the bridge's own
supported platform** — its README's "Supported Environment" table pins
`carla: 0.9.15` (rubric criterion 5) — and the spec registered measuring the
bridge **there** rather than porting it: "measured E2E on **CARLA 0.9.15 (its
supported platform)**. No port to 0.10." The repeated "different simulator
generation" caveat below is a comparability statement, not a maturity one, and
it cuts both ways: **no approach in this campaign ran a stock 0.10 binary
either** — the two natives ran _forks_ of 0.10.

`CAL-seam` is the one reversal: struck in P3 with `C1(a)` recorded as
UNMEASURED, revived for one registered relink round, and measured in P4 on five
runs (§3.1).

**The M4 ceiling search is the other thing this campaign did not establish, and
the campaign's registered wording for it is used verbatim: "ceiling not located
up to the 32ch class"** — a statement about where the search stopped, _not_ a
new step-up and not a licence for one (`p4-transport-sweep.md` §6.3). No
disjunct fired at `vlp16` on cell A or cell B-cyc, so `cells.yaml`'s
`sweep_classes` pre-registration stepped **both** cells up to `32ch` with no
owner consultation; no disjunct fired there either. All 18 scored rows per
class read `reached False` with empty reasons, and "did not fire" is a real
evaluation rather than an unevaluable disjunct — `analysis/ceiling.py:84` raises
when both `rtf` and `tick_rate_ratio` are `None`, so an unscoreable row cannot
render as a passing one (`p4-transport-sweep.md` §6.1). **No `n = 5` extension was executed
on either class** — that is pre-registered for a cell whose disjunct fired, and
neither did — so both cells stand at n = 3 per arm at both classes. The `128ch`
class stays struck on either branch and the strike is enforced in code: both
launchers refuse the class by name. **Cell E is out of the sweep entirely**, by
its registered static-only downgrade, and the spec required that recorded in
wording rather than left as silence (`p4-transport-sweep.md` §6.3).

**⚠ `ceiling.py:84` establishes EVALUABILITY, not SENSITIVITY.** That an
unscoreable row cannot render as a passing one says nothing about whether
**n = 3 per arm** could have detected a ceiling sitting just below a disjunct's
threshold. The registered disjuncts are sustain-based (`rtf < 0.9` held for
≥ 10 s), so their detection probability is a function of run count **and** run
length, and **neither was quantified anywhere in this campaign**. "Ceiling not
located up to the 32ch class" therefore bounds **where the search stopped** and
carries no statement about how close the ceiling may be — an
absence-of-evidence result, with an evaluability argument standing in for a
power argument that was never made.

## 2. Methodology

### 2.1 Pre-registration, by commit hash

The metric definitions, the equivalence rule, the margins, the ceiling
evaluator and the exclusion criteria were committed **before any measurement
run existed**. The first commit touching `benchmarks/results/` is `ccd456e`,
**2026-07-29 16:11:54 −0700**; every hash below precedes it. **Every date in
the table below is a COMMITTER date (`%cd`), not an author date** — the two
differ on two of the eight hashes (`ccd456e` `%ad` 15:28:28 against `%cd`
16:11:54; `75f0fc1c` `%ad` 11:00:39 against `%cd` 11:03:39), so a reader
reaching for `%ad` gets a mismatch and no way to know which field was meant.
For those eight the ordering argument holds under either field.

**⚠ The two rubric commits quoted at the end of this section are the exception:
they are quoted by AUTHOR date.** A later rebase of `docs/evaluation-report`
rewrote them and gave both the **same** committer date (2026-08-04 21:53:10
−0700), so `%cd` no longer orders them at all; their 18:56 and 19:22 timestamps
are `%ad`. **What warrants the ordering there is DAG ancestry, not either
timestamp**: `git merge-base --is-ancestor febb895 4e8eff0` exits 0, i.e. the
pre-registration commit is a literal ancestor of the snapshot commit. Ancestry
is the stronger warrant precisely because it survived the rebase that flattened
the committer dates, and because it **cannot be forged backward** — a commit
cannot be inserted as an ancestor of one that already exists without rewriting
the successor's hash, whereas both date fields are freely writable metadata.
The author dates only **corroborate** the ancestry; on their own they prove
nothing. Both commands are in §9.

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

  **⚠ Three qualifications from the same header and the same P3 record,
  reported here because the exculpatory sentence above was previously quoted
  without them, and this margin decides two knife-edge `parity` verdicts
  (§3.2, §3.3).** (1) **12 of the 15 CAL-rmw calibration runs carry `-dirty`
  shas** — `CAL-rmw/run-004`…`run-015`, i.e. "the calibration cell the
  `one_hop_wall_ms` margin is frozen from" — so the calibration cannot be tied
  back to an exact commit (`p3-baseline.md` §8.6's PROVENANCE caveat).
  (2) `margins.yaml`'s header **concedes its own amendment rule is not
  literally satisfiable**: the rule allows a change "only BEFORE the first P3
  measurement run" while naming "the CAL-rmw measured transport term" as a
  legitimate reason, "**which cannot both hold literally**"; the narrow reading
  (no `duel_admissible: true` run exists yet) is the operative one, and it is a
  reading, not a satisfied condition. (3) The header records the calibration as
  **a weak estimate of the quantity it measures**: "the two arms carried very
  different DELIVERED load, ~10 msg/s against ~0.85 msg/s … so the delta is a
  **weaker loopback-parity estimate than the formula's framing suggests**."
  **What bounds the exposure:** the floor keeps binding for any |Δ| ≤ 1.0 ms
  and the measured |Δ| is 0.4152 ms, 2.41× inside it — so all three
  qualifications would have to be wrong by a large factor before the frozen 2.0
  moved at all.

- **The rubric's criterion list and directions were committed before its
  snapshot**: `febb89513b1309e0084591ecf491c1b418e840af` (author date
  2026-08-04 18:56) is a **DAG ancestor** of `4e8eff0` (19:22), which filled the
  value cells. **A branch rebase renamed both commits**: this report previously
  cited them as `dd37379` and `324dc36`, hashes that are no longer reachable
  from the pushed branch. Only the hashes moved — **the pre-registration record
  is unchanged in content**, and the ancestry relation the claim rests on
  survived the rewrite intact. **What that ordering shows, stated exactly:** the
  criteria and directions were **committed** before the value-filling commit. It
  does **not** establish that the author was blinded to the data — one author, a
  26-minute gap, and a git DAG cannot show when a number was first seen — so it
  is a provenance fact, not a blinding one. **And the absolute reading ("no criterion could be re-directioned") has a
  recorded counterexample**: `rubric.md`'s own note under Criterion 7 records
  that the **value-filling commit edited a pre-registered Direction paragraph**,
  inserting "(16-day-old at this snapshot)" — a slip against the rubric's own
  rule, left in place with a note because it cannot be unmade without rewriting
  history. The edit is additive-only, updates a day count, and affected no value
  cell; it is named here rather than left as §6's vague "one process slip".

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

**Three properties of that rule the campaign never stated, added here because a
methods reviewer is entitled to all three before weighing any `parity` cell.**

- **⚠ `parity` means "the pre-registered rule returned parity", not "a
  calibrated 95 % equivalence statement".** The estimator
  (`benchmarks/analysis/stats.py:14-25`) is a **percentile bootstrap of a
  difference of medians**, resampling **n = 10 run-level values per side**. At
  that sample size a percentile CI for a median is lattice-supported — the
  resample median only takes values near a couple of order statistics — and is
  well known to under-cover and behave erratically. **Its interval coverage was
  never validated**, no BCa/studentised alternative was computed, and no
  sensitivity to the choice of statistic (median vs mean vs trimmed mean) was
  run. Under-coverage means **too-narrow** intervals, and TOST declares `parity`
  exactly when the interval is narrow enough to fit inside the margin, so **the
  expected failure mode runs in the direction of this report's headline
  reading.** Pinning `seed=20260727` makes the same interval reproduce; it is a
  reproducibility warrant, not a statistical one.
- **⚠ The directional labels are MARGIN-BLIND, and the report describes only
  the TOST half.** `equivalence_decision` (`stats.py:28-36`) tests `parity`
  first, then returns `a_better` on `hi < 0` alone and `b_better` on `lo > 0`
  alone — **with no requirement that the interval clear the margin.** So
  `a_better` is a statement about **zero**, not about practical equivalence, and
  a row can print `a_better` while its own CI still overlaps the equivalence
  region. One does: P3's `lidar_to_ndt_sim_ms` (§3.2).
- **⚠ No multiplicity or selection-effect argument exists anywhere in this
  campaign.** The two duel invocations adjudicate **5 P3 rows + 10 P4 rows =
  15 verdicts** at a per-comparison `alpha = 0.05`, plus four sweep-class
  booleans over 18 rows each; **no correction was pre-registered or applied**,
  no family-wise or intersection-union framing exists, and **no comparison was
  designated primary in advance**. The bracket's headline (§3.2) is a **pattern
  read across those fifteen per-metric verdicts** — which flipped, which
  reversed, which declined to decide — not a single pre-specified test, and the
  `carla_process_cpu_pct` "reversal" narrative (§3.2, §8) rests on directional
  labels that are one-sided in effect. A reviewer should discount the pattern
  accordingly; this document offers no corrected alpha because none was
  registered and inventing one now would be adjusting the rule after seeing the
  verdicts.

### 2.3 Patch inventory, and the named exception

The patch policy (`benchmarks/README.md`, "Patch policy") forbids changes to
any approach's data-path, conversion or transport code; sensor- and
launch-parameter edits are permitted and are committed as reviewable diffs.
Applied inventory, complete:

| approach        | patches                                                                 | nature                                                                                                  |
| --------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `extension`     | **none** — `patches/extension/` is README only                          | see the footnote: the zero is structural, not a cleanliness result                                      |
| `tier4-native`  | `0001-toolchain-libm`, `0002-glibc-compat`, `0003-autoware-demo-params` | `0001`/`0002` **build-environment adaptation**; `0003` launch/sensor parameters                         |
| `python-bridge` | `0001-lidar-is-dense`, `0002-sensor-config-harmonized`                  | `0001` the named pre-registered exception; `0002` harmonized kit **plus one Autoware-side launch hunk** |

**The 0-vs-3 contrast is not a cleanliness finding, and the nature column is
why.** `0001-toolchain-libm` adds `-lm` to `CMAKE_CXX_STANDARD_LIBRARIES` in
`CMake/Toolchain.cmake`; `0002-glibc-compat` adds a glibc-2.38+
`__isoc23_strtol` shim compiled as C11. **Both are artefacts of building on a
newer host toolchain than the tier4 branch targets, and say nothing about the
integration.** The extension's zero is likewise structural: its equivalent
build adaptations live **inside the CARLA fork it requires**, upstream of the
patch set this table inventories — the fork is the artifact (§3.5).

**`0001-lidar-is-dense.patch` is the policy's one named, pre-registered
exception** (`benchmarks/README.md`, "Named exception (pre-registered
2026-07-28, before any P3 run)"). It is a one-line change on the bridge's
publish path — `is_dense=False` → `is_dense=True` in `create_cloud` — and it is
also _correct_ on the pre-registration's own premise: "the bridge's cloud
contains no invalid points, so the flag was a mislabel". **Two scoping facts
belong in the same sentence, because as written this reads as a one-sided
finding against the bridge.** First, `is_dense=False` is a **valid,
conservative, spec-compliant** PointCloud2 value; it becomes fatal only because
**Autoware's `crop_box_filter_self` rejects every cloud carrying it**
(`benchmarks/config/cells.yaml`, cell-E0 block; `benchmarks/results/PROVENANCE.md`
§9.3) — so the failure is a **two-sided interop contract mismatch** at the
seam, and the Autoware half is as much a finding as the bridge half. Patch 0002
edits `carla_sensor_kit_launch`'s `crop_box_filter_self` input remap directly,
so the harness knows exactly where that node lives. Second, the **"no invalid
points" premise is the pre-registration's** (`benchmarks/README.md`, named
exception; `patches/python-bridge/README.md`), **not a measurement this
campaign filed** — no per-point validity measurement of any E-family cell
exists in `benchmarks/`. Without the patch every E-family closed-loop cell is
unmeasurable and C2 degrades to structural analysis. **The as-shipped behaviour is preserved as
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
(`benchmarks/config/exclusions.md`) and **may not be edited after it**. The
frozen document also carries a **consequence clause**, and it fired once:
"**Any exclusion not matching 1-10 invalidates the campaign for that cell and
requires a fresh cell**" (`exclusions.md:51-52`). See the cell-E0 bullet below
for the disclosed deviation. What the criteria actually excluded, per the census
of appendix command 10 (its full output is printed there, so each row below is
checkable against it):

| cell    | n   | reasons                                                          |
| ------- | --- | ---------------------------------------------------------------- |
| `B`     | 15  | `crash:cell-launch` 7, `crash:collect_gt` 1, `gate:arm-failed` 7 |
| `E`     | 10  | `crash:cell-launch` 4, `harness:<sha>` 4, `gate:arm-failed` 2    |
| `B-cyc` | 6   | `harness:65fbe09` (criterion 3) — the 32ch mislabel, see below   |
| `E0`    | 4   | `harness:e7ba92a` 2, `gate:arm-failed` 1, `crash:cell-launch` 1  |
| `C`     | 2   | `warmup:nishi` — a pre-registered discard, not a failure         |
| `A`     | 0   | —                                                                |

Five properties of this log are the ones a reviewer should check:

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
  (`p4-transport-sweep.md` §6.2). **The same substance test the E0 bullet below
  applies must be applied here, and this document had tested only the
  relabelling alternative.** Criterion 3's text is "Harness defect discovered
  and fixed (**the run was measured with a broken observer/injector**)"; a
  missing `BENCH_TIER4_SWEEP_ARGS` export in the operator's invocation is a
  defect in the _invocation_, not a broken observer or injector, so
  `harness:65fbe09` stretches criterion 3's substance in the same direction as
  `harness:e7ba92a` does — less far, because a real harness-side defect was
  found and the export requirement was fixed, but not exactly. And **B-cyc's
  32ch measured arm is entirely a re-collection following a discarded first
  attempt** (six runs discarded, six re-collected), which is a selection risk on
  that arm worth naming even though the discard was driven by a measured
  quantity and not by a result.
- **Cell E0's two `harness:e7ba92a` exclusions are a substance mismatch, and
  `exclusions.md`'s invalidation clause was OVERRIDDEN BY OWNER RULING rather
  than satisfied.** The reason _string_ is verbatim from criterion 3, but
  nothing was broken and nothing was fixed: NDT published exactly one pose, and
  the cadence function raises on a single sample. The label was applied
  **mechanically by committed code** (`run.sh:1028-1029`) to a rule written
  before E0's data existed. **Stated so a reader of this report alone can see
  it: on a strict reading of `exclusions.md:51-52` — "any exclusion not matching
  1-10 invalidates the campaign for that cell and requires a fresh cell" — cell
  E0 would have to be re-collected. The P3 record says so in terms and then
  declines: "CONTROLLER RULING: do NOT re-collect cell E0"**
  (`p3-baseline.md` §8.3). **This is a disclosed deviation from the frozen
  exclusion protocol, not an application of it**, and it is the single most
  consequential exclusion-log fact in the campaign. The four grounds the ruling
  gives are (1) a fresh cell reproduces the identical filing, the
  `harness:<commit>` ⇄ criterion-3 mapping being pre-registered in committed
  code and E0's NDT starvation being its registered expected outcome; (2) the
  criteria may not be edited after the first P3 run, so widening the vocabulary
  to fit is equally unavailable; (3) an owner "record-only, freeze held" ruling
  covering this whole class; and (4) cell E0 is a bridge cell outside the duel,
  so no verdict, delta or margin rests on it. Those grounds are reasons for the
  override; they are not the protocol's stated consequence. The consequence for
  C2 is carried inline at every E0 figure in §4.
- **Eight of cell E's ten exclusions are pre-registration history, not
  behaviour.** Cell E is filed 16 / excluded 10 in §1.2 — a bare 63 % that reads
  as bridge flakiness beside cell A's 0 %, and it was the one cell in this table
  with no explanatory note. The manifests say otherwise: `E/run-001`…`run-004`
  carry `patches_git_sha ec998b4b` (a pre-campaign patch set) and
  `E/run-005`…`run-008` carry superseded harness shas — the "stale pre-P3 runs
  retained as history" that `p3-baseline.md` §7.1 P3-5 and §8.4 #4 already
  document. **At the campaign's registered configuration (`patches_git_sha
ccff4f94`) cell E stands at 2 exclusions of 8 runs** — `E/run-009`
  (`gate:arm-failed`, the closed-loop attempt of §4.3) and `E/run-010`
  (`crash:cell-launch`).
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
(`CAL-seam/run-001`…`run-005`). No interval is computed for the paired delta;
at n = 5 the 5-of-5 sign pattern is what the table supports and no more.

**⚠ C1(a)'s measured delta is an UPPER BOUND ON THE SEAM MECHANISM'S SHARE, not
a point estimate of it. The seam's median cost is +0.278 ms per 921 908-byte
publish on this instrument, with all five runs inside +0.239…+0.299 ms**, and
that qualifier travels with the number wherever it is quoted. **The bound is a
statement about the mechanism, not about the observations** — the registered
residuals could only make the seam measure _cheap_, so the measured delta caps
the seam's share from above. Where a numeric ceiling is wanted, quote the
observed **maximum (+0.2988 ms)**; the earlier wording "the seam costs _at most_
≈ 0.28 ms" quoted the **median** as a bound, which 2 of the 5 filed runs in the
table directly above exceed — a self-contradiction fixed here without changing
any number or the verdict. It is not a hedge added after the fact:
PROVENANCE §11.9 (`benchmarks/results/PROVENANCE.md`) registered the
upper-bound rule on 2026-08-03,
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
downgrade**: an overhead _was_ measured, on 5 of 5 runs, with a median of
+0.278 ms and an observed maximum of **+0.299 ms** per publish at this payload,
which is the number to quote as a ceiling. What the measurement supports is
that the seam's cost is small and bounded — not that it is zero.

### 3.2 C1(b), static arm — the attribution bracket

**Read this table with the P4↔P3 identity caveat inline** (rule 5): it sets two
_verdicts_ side by side, each computed entirely within its own phase against
the same frozen margins, which is the only cross-phase reading the spec
licenses. It does **not** compare a P3 per-cell absolute against a P4 one, and
nothing here licenses that — the engine BuildId (`4210e602` → `bc08ce19`) and
the harness sha both moved between the phases (`p4-transport-sweep.md` §9.1).

| metric                  | P3 `A-vs-B` (**A on CycloneDDS/lo-profile, B on Fast-DDS + `udp_only.xml` — NOT rmw-matched**) | P4 `A-vs-B-cyc` (both Cyclone, **not profile-matched**) | pre-registered reading                      |
| ----------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------- |
| `one_hop_wall_ms`       | −6.281, [−6.542, −5.828]                                                                       | **+1.687**, [1.441, 1.849]                              | `a_better` → **`parity`** ⇒ transport-bound |
| `lidar_to_ndt_sim_ms`   | −5.817, [−8.106, −4.976]                                                                       | **+1.356**, [1.287, 1.553]                              | `a_better` → **`parity`** ⇒ transport-bound |
| `control_staleness_ms`  | UNAVAILABLE                                                                                    | `insufficient-data`, n = 0/8                            | **no bracket on this arm** ⬇                |
| `carla_process_cpu_pct` | −12.873, [−16.698, −11.129]                                                                    | **+52.005**, [49.617, 52.871]                           | `a_better` → **`b_better`** — reversed      |
| `achieved_rate_ratio`   | +0.104, [+0.090, +0.114]                                                                       | **+0.001**, [0.001, 0.001]                              | favoured A → **`parity`** ⇒ transport-bound |

Pools: P3 `A/run-003`…`012` vs `B/run-013`…`022`, n = 10/10
(`p3-baseline.md` §4.1); P4 `A/run-016`…`025` vs `B-cyc/run-002`…`011`,
n = 10/10 (`p4-transport-sweep.md` §2.1, §2.3). Units follow the metric: ms
on the two latency rows, percentage points on `carla_process_cpu_pct`, and a
dimensionless fraction on `achieved_rate_ratio`.

**⚠ MANDATORY INLINE, per §0 rule 3 — the image confound.** Every P4 row above
also spans an **Autoware image difference**: cell B-cyc runs
`ghcr.io/autowarefoundation/autoware@sha256:5c22369a…e8ee`
(`universe-devel-cuda`, by digest, the same image as cell B by deliberate
design) and cell A runs `ghcr.io/autowarefoundation/autoware:universe-devel`
**by tag**. In `p4-transport-sweep.md` §1's own words this is "**the single most
important**" confound in that document — "**the image confound sits under every
B-side number**" — and P4-1 adds that "**every A-vs-B-cyc row in this document
also spans an image difference, and no row in section 2 or 3 is corrected for
it.**" It is not corrected for here either, and C1(b)'s registered "the same
workload envelope … on the same map and **kit**" wording must be read against
it (§7 row 12).

**⚠ MANDATORY INLINE — the collection provenance of THIS arm.** The **static**
duel, which is the arm the attribution bracket rests on, **took TWO `duel.sh`
invocations**: a resume after the driver was killed mid-duel, with **two
disclosed residues**, both artefacts of the resume — one of which is the 6/4
first-slot alternation instead of 5/5, because every invocation starts its own
pair 1 with cell A (`p4-transport-sweep.md` §8.2, §18.2–§18.3;
`p3-baseline.md` §8.4 #2). The abort was refuted as a two-consecutive-failure
abort and as systematic row-11 uncollectability, and the resume then collected
six further runs with zero failures. This is stated here because §3.3 quotes
the closed-loop arm's clean single invocation inline, and quoting one arm's
favourable collection fact inline while leaving the other arm's behind a
section pointer is the asymmetry §0 rule 3 exists to prevent.

**⚠ MANDATORY INLINE — the clock-fit residual, on BOTH arms and in BOTH
phases.** `benchmarks/README.md`'s duel-metric section registers that a duel
row "must be read next to that run's `fit_residual_ns`" (P4 §7.1 P4-9), and
`one_hop_wall_ms` is computed **through** a sim→wall affine fit. The four
computable medians, against a **2.0 ms** margin:

| pool               | max-abs sim→wall fit-residual median | source                          |
| ------------------ | ------------------------------------ | ------------------------------- |
| P3 cell A (static) | **1.85 ms**                          | `p3-baseline.md` §4.1, tool row |
| P3 cell B (static) | **22.48 ms**                         | `p3-baseline.md` §4.1, tool row |
| P4 cell A (static) | **1.77 ms**                          | `p4-transport-sweep.md` §2.1    |
| P4 B-cyc (static)  | **3.77 ms**                          | `p4-transport-sweep.md` §2.6    |

Two consequences, neither previously stated in this report:

- **The P3 anchor of the flagship flip is itself instrument-limited by more
  than the effect it reports.** Cell B's 22.48 ms residual median is **11× the
  2.0 ms margin and 3.6× the |−6.281 ms| delta the `a_better` verdict is built
  on.** So the `one_hop_wall_ms` flip from `a_better` to `parity` is **not
  attributable to transport alone** — part of it is a flip in the instrument,
  and this document cannot say how much.
- **The static P4 row is also above its margin on the B side.** 3.77 ms exceeds
  the 2.0 ms margin and the entire reported CI [1.441, 1.849], with **4 of 10
  B-cyc static runs above 20 ms** (65.4, 58.9, 70.4, 24.9). The source's own
  phrasing is plural and covers both arms — "**The `one_hop_wall_ms` parity
  rows are the weakest of the parity rows in this document**, the closed-loop
  one more so than the static one" — and cell A's fit is tighter by only
  **2.1×** on the static arm against 15× on the closed-loop one. These are
  **maxima over a run**, not typical errors, and the metric takes a p50 over
  ~1400 samples; but the static row is the **first row of this bracket** and the
  lead evidence for "transport-bound", so it carries the caveat here rather than
  only at §3.3's closed-loop table.

**⚠ How close each `parity` sits to its own margin**, because the tables let a
knife-edge verdict and a comfortable one read identically. As a fraction of
margin, |CI bound nearest the margin| ÷ margin: static `one_hop_wall_ms`
**92.5 %** (1.849/2.0); closed-loop `one_hop_wall_ms` **97.1 %** (1.942/2.0,
§3.3); closed-loop `lidar_to_ndt_sim_ms` **51 %**; static `lidar_to_ndt_sim_ms`
**31 %**. **Under a narrower margin neither `one_hop_wall_ms` row becomes
`inconclusive` — the rule DECLARES tier4-native better on it.** Both CIs lie
wholly above zero, so once the interval no longer fits inside the margin the
`lo > 0` branch fires: `equivalence_decision` returns **`b_better`**, not
`inconclusive` (`inconclusive` requires a CI that straddles the margin **and**
contains zero — see the margin-blind-label bullet in §2.2). The two rows also
have **different** thresholds, because each flips at its own CI's upper bound:
the **closed-loop** row (CI [0.886, 1.942]) returns `b_better` at any margin
**≤ ≈ 1.94 ms**, and the **static** row (CI [1.441, 1.849]) survives further,
returning `b_better` only at a margin **≤ ≈ 1.85 ms**. So the closed-loop row
turns on a **3 % change** in a threshold whose own derivation shows the
_measured_ term never determined it (the pre-registered 2.0 floor bound
instead; §2.1) — and it turns **against** C1(b), not into a decline-to-decide.
No margin-sensitivity analysis was pre-registered and none is computed here;
the thresholds are arithmetic on the printed CIs read against
`stats.py:28-36`.

**⚠ `achieved_rate_ratio`'s intervals are DEGENERATE at the reported
resolution.** The P4 static row's CI is [0.001, 0.001] — zero width to three
decimals — and the closed-loop row's (§3.3) is [−0.000, 0.000], a point mass
printed with a signed zero that advertises a precision the quantity does not
have. A CI that collapses to a point at ≪ 1/20 of its 0.02 margin carries **no
discriminating power**: its `parity` is arithmetically guaranteed rather than
earned. It is therefore **uninformative, not corroborating**. The two counts
this document quotes from the tool's own output — the "three of four" static
flips below and §3.3's "four of five metrics" — are printed **as the verdict
tool produced them**, and this report does not silently renumber a filed
result; but **neither count may be quoted without this caveat attached**,
because on both the `achieved_rate_ratio` member contributes no evidence. Each
site carries the pointer back here.

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

- **Three of the four computable P3 separations were transport-bound — but they
  are THREE VIEWS OF ONE CONDITION, not three findings** (the count is quoted as
  the verdict tool printed it; one of the three, `achieved_rate_ratio`, has a
  degenerate P4 interval and contributes no evidence — see the degenerate-CI
  caveat above). Under a shared RMW
  (`A-vs-B-cyc`, static), `one_hop_wall_ms`, `lidar_to_ndt_sim_ms` and
  `achieved_rate_ratio` all return `parity`, where `A-vs-B` returned a
  separation outside the margin on every one. Per the rule pre-registered
  before any P4 run, the P3 separation on those three metrics is **attributed
  to the as-shipped Fast-DDS configuration, not to the approach.**

  **⚠ The count is not evidentiary weight, and the P3 record says so in
  advance.** `p3-baseline.md` §4.2: "**They are NOT four independent findings,
  and this is stated here rather than left for a reader to infer independence
  from a table.**" `achieved_rate_ratio` **is** cell B's frame deficit measured
  directly; `lidar_to_ndt_sim_ms` is the latency of the same chain over the same
  window; `one_hop_wall_ms` is the transport hop those samples traverse. §4.3
  names the failure mode exactly: "a reader could accept 'the cause is unknown'
  and still wrongly count four corroborating results." **So the bracket flips
  ONE unexplained condition, not three**, and the three-fold appearance is a
  measurement artefact of looking at one deficit through three instruments.
  Discount two of the three accordingly — and note that the M2 bullet below is
  offered as corroboration "on a different quantity" while `observer_loss_rate`
  is a _fourth_ view of that same loss, so it is a **consistency check, not an
  independent confirmation**. (`achieved_rate_ratio` is separately uninformative
  on the P4 side; see the degenerate-CI caveat above.)

- **⚠ The three flips are not equally strong, and one of them flips from a
  verdict that was already compatible with practical equivalence.** Per §2.2,
  `a_better` is declared on the CI excluding **zero**, with no requirement that
  it clear the margin. P3's `lidar_to_ndt_sim_ms` row prints `a_better` on
  [−8.106, **−4.976**] against a **5.0 ms** margin — **its upper bound lies
  INSIDE the equivalence region**, so that row was never a statement of
  practical separation, and calling its move to `parity` a "separation
  disappearing" overstates what changed. `one_hop_wall_ms`'s P3 CI
  ([−6.542, −5.828] against 2.0 ms) does clear its margin, but is the row whose
  P3 instrument residual is 22.48 ms (above). `achieved_rate_ratio`'s P4 side is
  degenerate. **On this arm no flip is unqualified**, and the bracket should be
  read as one condition, weakly instrumented, rather than as three clean
  reversals.
- **The M2 reconciliation corroborates it on a different quantity, and this one
  bullet does set a P3 per-cell figure against a P4 one — carrying the identity
  caveat here, in its own sentence, because §0 rule 5 requires it and this
  section's preamble scopes its copy to the bracket table above.** The engine
  BuildId and the harness sha moved between the phases; `observer_loss_rate` is
  **not** a margin metric, and the comparison is `p4-transport-sweep.md` §2.3's
  own, not one this report constructs. P3's cell B lost frames observer-side
  (`observer_loss_rate` median 0.085, max 0.108, against cell A's 0.000/0.000);
  cell B-cyc — same image, same launcher, only the middleware changed — reads
  0.000/0.000 on both arms. **One row of that same table is not a
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
  like-for-like sensor load.** **And the source's own closing clause, restored
  here because dropping it quoted a discount without its refutation:** that
  confound "was present in P3 unchanged — **where cell A won the row anyway** —
  so **it does not explain the reversal on its own**"
  (`p4-transport-sweep.md` §2.5(c)). This is the one metric on which
  tier4-native separates in its own favour, so the confound rider on it must be
  quoted at exactly the strength its source states and no more.

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

**Four limits on this table, none optional.**

First, **the `one_hop_wall_ms` parity ROWS are the weakest of the parity rows in
this document — on BOTH arms**, which is the wrap doc's own plural phrasing
(`p4-transport-sweep.md` §2.6): the metric is computed through a sim→wall affine
fit, and the max-abs residual medians against a 2.0 ms margin are **54.60 ms
(B-cyc closed-loop) vs 3.58 ms (A closed-loop)** and **3.77 ms (B-cyc static) vs
1.77 ms (A static)** — eight of ten B-cyc closed-loop runs exceed 20 ms, and
four of ten B-cyc **static** runs do too. Cell A's fit is tighter by **15× on
this arm but only 2.1× on the static arm**; only the closed-loop gap is an order
of magnitude. These are maxima over a run, not typical errors, but a reader who
needs either row to bear weight should treat both as weak, the closed-loop one
more so (§7.1 P4-9; §3.2 carries the same table for the static arm and for P3).

Second, **`one_hop_wall_ms`'s parity here is a knife-edge**: the CI upper bound
1.942 sits at **97.1 % of its 2.0 ms margin**, and at any margin **≤ ≈ 1.94 ms**
the rule returns **`b_better` — tier4-native better on this row**, not
`inconclusive`: the CI lies wholly above zero, so the `lo > 0` branch fires as
soon as the interval stops fitting inside the margin (§2.2's margin-blind-label
bullet; `stats.py:28-36`). That is a **3 % change** in a threshold the
_measured_ calibration never determined (§2.1, §3.2), and it moves this row
**against** C1(b) rather than into a decline-to-decide. The static row is less
exposed — its own CI upper bound is 1.849, so it stays `parity` down to
≈ 1.85 ms (§3.2). `lidar_to_ndt_sim_ms` at 51 % of margin and
`control_staleness_ms` at 14 % are not comparable in strength to either, and the
flat table does not show that.

Third, **`achieved_rate_ratio`'s CI is degenerate** — [−0.000, 0.000] is a point
mass printed with a signed zero, ≪ 1/20 of its margin — so its `parity` is
arithmetically guaranteed rather than earned, and it is uninformative rather
than corroborating (§3.2).

Fourth, the `carla_process_cpu_pct` row carries the same reversal and the same
unresolved cause as §3.2 — **and every row above also spans the Autoware image
difference** (`universe-devel-cuda` by digest on B-cyc against `universe-devel`
by tag on A), which P4 §1 calls its single most important confound and which no
row here is corrected for (§0 rule 3; §7 row 12).

**⬇ The wording that survives all of this:** on the closed-loop arm under a
shared transport family — **and across an uncorrected Autoware image
difference** — the extension and tier4-native stacks are **within the
pre-registered margins on four of five metrics and separated beyond margin on
the fifth, in tier4-native's favour, for reasons this campaign did not
establish** (the count is quoted as the verdict tool printed it, and carries the
degenerate-CI caveat of §3.2: one of the four contributes no evidence). Of those four, **one is a knife-edge at 97 % of its margin on a
metric whose instrument residual is 27× that margin, and one is degenerate**, so
the effective evidentiary weight is closer to **two well-supported parity rows
than four**. That is a bracketed workload-envelope statement — it is **not** a
claim that the approaches are equivalent, `parity` is a decision against a
frozen margin rather than a proof of identity
(`p4-transport-sweep.md` §2.6), and per §2.2 it is not a calibrated 95 %
statement either.

### 3.4 Two findings that bound every C1 sentence

**The latched-delivery defect, and its attribution boundary.** Latched
(`TRANSIENT_LOCAL`) messages published once reached `topic_state_monitor_*`
promptly and **not** `behavior_path_planner`. Across the seven cell-B runs that
reached the arm and failed it, the planner named three different missing
inputs: map (2 runs), route (4), operation_mode (1). The map half was
reproduced standalone with no CARLA and no harness at all
(`p3-baseline.md` §5.1). **The defect is a property of the Fast-DDS transport
configuration this cell runs on this host. It is NOT established as an
intrinsic property of the tier4-native approach**, and no sentence in this
report may be read as though it were: Fast-DDS version, kernel and loopback
behaviour are uncontrolled, and the CycloneDDS configuration that works is
itself registered as not measurement-grade.

**⚠ Two of the three things in that configuration are not tier4's, and the
earlier phrasing ("the as-shipped **tier4** transport configuration") attached
tier4's name to both.** (1) `benchmarks/observer/config/udp_only.xml` is
**harness-authored** — it lives in this repository and was added by it, not
shipped by tier4 (`benchmarks/README.md`, "DDS middleware and transport (Task
9)", lists it as part of the cell's transport). (2) The behaviour that forces
it — participants constructed with `efd::PARTICIPANT_QOS_DEFAULT`, so that
`FASTRTPS_DEFAULT_PROFILES_FILE` is inert and only SHM user-data locators are
announced — is **upstream CARLA's code pattern, inherited unchanged by the
tier4 fork**. Verified against this campaign's own pinned branch point:
`git grep PARTICIPANT_QOS_DEFAULT tier4/ue5-dev -- LibCarla/source/carla/ros2`
returns the same line in `BasicPublisher.cpp`, `CarlaClockPublisher.cpp`,
`CarlaGNSSPublisher.cpp`, `CarlaIMUPublisher.cpp`, `CarlaLidarPublisher.cpp` and
the rest of the publisher family — and `gap-catalog.md` §5.0.1 independently
certifies `tier4/ue5-dev` as "a genuine `ue5-dev` baseline rather than a tier4
patch". **The extension's own CARLA fork inherits the same pattern; it simply
never ran on Fast-DDS in this campaign** (§0 rule 2). What is tier4's here is
the _choice_ to ship the branch on Fast-DDS; the code pattern and the profile
that works around it are not.

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

**Two of Phase 0's own rulings were refuted, and both stay in the record with
the diagnostic that refuted them** — the branch ruling is unaffected by either;
only the reasoning is (`p3-baseline.md` §5.2's closing paragraph):

- **The first ruling rested on a publisher COUNT**, which cannot distinguish
  advertising from emitting, and so measured a quantity the hypothesis does not
  name (PROVENANCE §6.5). What replaced it is a stamp-identity measurement:
  cell A has 2 advertised publishers and **1 emitter** (0 duplicate stamps);
  cell B has 2 advertised publishers and **2 emitters** (72 duplicate stamps of
  88 unique).
- **The second ruling's causal wording — "killing the relay stops NDT" — is
  refuted by the repository's own `results/B/run-027/observer.csv`**, which
  records NDT **resuming ≈ 29 s after the kill** with `concatenate_data` as
  sole publisher (PROVENANCE §6.8).

A third correction of the same class sits inside the figure quoted above: an
earlier revision of the P3 record said **nine** of the ten duel-pool runs fail
the M5 gate, which contradicted its own 0.257–0.989 range and overstated the
pervasiveness of the campaign's central unexplained confound. **Eight** is the
corrected count, it is the count used here, and PROVENANCE §4.1's identical
off-by-one is deliberately left as written with a pointer to the diagnostic
that corrected it (`p3-baseline.md` §5.2).

### 3.5 C1(c) — the structural half

This half is argued from `docs/evaluation/rubric.md`, not from the measurement
harness, and it is where the extension's own weaknesses live. Every figure
below is summarised; the rubric carries the command or URL behind each.

**What supports C1(c):**

**⚠ Every figure in this subsection is a DATED SNAPSHOT, not a regenerable
number** (§9): it comes from an authenticated `gh` against a moving GitHub plus
two git clones that are not in this repository, inside sliding 90-day/365-day
windows. The two clone-derived counts are pinned to resolved SHAs below so they
are at least checkable after the fact.

- **Unmerged footprint.** Extension: **219** fork commits ahead of
  `upstream/ue5-dev` + **25** in this repo. tier4-native: **305**. Bridge:
  **0** — it is in-tree (rubric criterion 3). The spec quoted 216 at
  spec-writing time; the fresh count is 219, +3, and both are reported.
  **Endpoints, resolved and pinned** so the counts are reproducible rather than
  "whatever those branches say today": `upstream/ue5-dev`
  `0a5ce0d5b4952bd8294a163c12d49f197bdb2aba`;
  `feat/autoware-seminative-phase-b`
  `62ca380f92efff57cabab4da67ab5abdd9fc94cc`; `tier4/autoware-support`
  `6315b856f8faf2118578322eb20a2b902a45a384` (rubric criteria 3 and 6, which
  also quote the 121-commit extension-only range between the last two).
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
  **⚠ The two figures are computed over DIFFERENT POPULATIONS and are not a
  like-for-like ratio.** The 67.3 % is **every PR the fork's two dominant
  authors ever opened against `carla-simulator/carla`, over their whole
  careers**, explicitly including PRs the rubric itself labels unrelated-topic
  (`#9744`, `#9749`), and 43 of the 66 merges belong to `JArmandoAnaya`, a
  CARLA-side contributor whose upstream record largely predates and is
  independent of this extension. The **0** is PRs by **four named
  Robotec/tier4-specific delta authors**, scoped precisely to _exclude_ the
  shared-ancestor CARLA-community delta authors whose large upstream histories
  the rubric found (`glopezdiest` 82, `Blyron` 145) — the same people who also
  appear in the extension's own fork delta (rubric criterion 6). No ordering
  between the two cells is supported.
- **Maintenance signal — and WHICH ref is stalled.** **The
  `autoware-support` integration branch** is stalled: its tip is
  `6315b856f`, dated **2026-04-08**, with **0** commits in the 90 days before
  the snapshot, its CI has fired **once ever** on that branch (a dependency-bump
  automation event, 2025-09-15), and it is **frozen** at the ruleset level
  (rubric criteria 7, 9, and the corrected criteria 1–2). **tier4's development
  did not stop.** Measured in the same clone at the same moment,
  `tier4/main` — the repository's actual default branch — is tipped
  `5642dfdd2`, **2026-07-07**, with **205** commits inside that same 90-day
  window and **26** distinct author emails in 12 months, and **nine of the
  branches this report's §5 catalogs as side branches are already merged into
  it** (`gap-catalog.md` §1.3, §6.0.2). `autoware-support` is 349 commits behind
  `main` and is not its ancestor. **Scoping the CAPABILITY comparison to
  `autoware-support` is correct — it is the branch cell B builds — but no
  sentence in this report is a maintenance verdict on tier4-native the
  approach**; the finding is that _this integration branch_ is frozen and
  un-synced while the work moved to the `ue5-dev`/`main` lineage. The rubric's
  snapshot script never queries `main` at all, which is why that half was
  previously absent.
- **CI silence is partly CI REACHABILITY, not only CI practice.** Rubric
  criterion 8 records what building tier4's artifact costs — **~300 GB free
  disk, 3–4 hours** to build Unreal Engine from source plus up to another hour
  for the first editor build — and **no GitHub-hosted runner can do that**. The
  extension is credited with a `cpp-tests` job in the same row because, per the
  same criterion, "the extension `.so` itself builds in well under a minute
  (plain C++, no UE toolchain)"; the two cells are therefore partly comparing
  what is _possible_ to CI. tier4's build workflows also target the `ue5-dev`
  lineage where the work landed, not `autoware-support`.

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
upstreaming** where **the comparator's `autoware-support` integration branch is
frozen and un-upstreamed — while tier4's own development continued on the
`ue5-dev`/`main` lineage** (above) — but the extension is **not** fork-free
today, and it is **solo-maintained with no external review**, which is a
governance risk the comparator's numbers do not offset. The upstreaming
comparison is also **not a like-for-like ratio** (above), and every figure in
this half is a dated, non-regenerable snapshot (§9).

## 4. C2 — python-bridge limits

C2's registered text, quoted verbatim from the design spec before any figure
below, exactly as §3 does for C1 and §5 does for C3 — it was previously the one
registered claim in this document that was never stated and never adjudicated,
which left the section heading above doing the work of a finding:

> **C2 (python-bridge limits)** — the bridge's architecture (separate Python
> process, per-sample Python conversion, CARLA-RPC + DDS double hop,
> bridge-as-clock-master) imposes **measurable costs** and a **lower
> sustainable-load ceiling**. Every C2 sentence cites which arm backs it: E0
> (as-shipped = "today's user experience"), E (harmonized = controlled
> comparison), E-opt (packer-optimized = separates architecture from
> implementation defect). The bridge's 16 B/point layout vs the natives'
> 32 B/point means its ceiling is reached at roughly half the byte rate —
> reported explicitly, making the measured gap a lower bound on the
> architectural gap.

**⬇ C2 AS REGISTERED IS NOT ESTABLISHED BY THIS CAMPAIGN, and the downgrade is
stated here rather than left implicit in the section heading.** Taking its three
components in turn, on this campaign's own record:

- **"Measurable costs" — no cross-approach statistic exists.** None was
  computed in either phase and none may be inferred; the E family is context,
  not a duel side (§4.5, `p3-baseline.md` §4.3, `p4-transport-sweep.md` §2.6).
  What §4 reports is **per-arm context on cells E0 and E**, every row of it
  bounded by the CARLA-generation, container, rig, throttle and topic
  differences of §7 rows 1–3.
- **"A lower sustainable-load ceiling" — NO measurement at all.** **Cell E is
  out of the M4 sweep entirely** by its registered static-only downgrade
  (`p4-transport-sweep.md` §6.3, §8.1: "**Cell E in the sweep — OUT**";
  restated in §1.3), so no ceiling search was ever run on the bridge. There is
  no bridge ceiling number in this campaign, high or low, and none may be
  inferred from the natives' "ceiling not located up to the 32ch class".
- **The 16 B/point lower-bound argument — RETRACTED by this report.** §4.4
  records the spec's own premise as **unmeasured** and derives no multiplier
  from it; no per-point layout measurement of any E-family cell exists in
  `benchmarks/`.
- **The architecture-versus-implementation split C2 was designed to make —
  UNAVAILABLE.** E-opt was struck (§4.1), so nothing here separates the
  architecture's cost from the implementation's.

**What survives, and it is the whole of C2's evidentiary content:** two
per-arm descriptions of the bridge under this harness (E0 as its authors ship
it, E harmonized), the E-vs-E0 within-approach contrast, and one **closed-loop
non-result on a single attempted run at the registered configuration** (§4.3).
Nothing in §4 may be quoted as establishing either half of C2 as registered.

### 4.1 The arms, and the one that does not exist

| arm       | image                  | what it is                               | status                |
| --------- | ---------------------- | ---------------------------------------- | --------------------- |
| **E0**    | `bridge-bench`         | as shipped (`frequency_hz: 11`)          | 5-run static pool     |
| **E**     | `bridge-bench-patched` | harmonized kit, both patches applied     | 6 valid static runs ⬇ |
| **E-opt** | `bridge-bench-patched` | `create_cloud` → `tobytes()` sensitivity | **STRUCK — no data**  |

**⚠ E-opt was struck by the owner's 2026-07-30 scope cut
(`p3-baseline.md` §2.2), and this removes a capability C2 was designed to
have.** The spec registered E-opt as a _measurement control_ separating the
architecture's cost from an implementation defect, and its registered wording is
restored here **verbatim**, because an earlier revision of this paragraph
softened its two most bridge-protective phrases — "dominated by" to "not
decomposable", and "the whole section" to "part of it" — which is exactly the
re-litigation §0 rule 4 forbids:

> an **optional local-only sensitivity arm** (cell E-opt) with the known
> `create_cloud` per-point packer replaced by `tobytes()` is included as a
> _measurement control_ — **without it, C2's headline number is dominated by a
> 20-line implementation bug and a maintainer can neutralise the whole section
> with one PR.**

**Two scoping facts about that registered wording, since it is a claim about
someone else's code that this campaign never measured.** The "20-line
implementation bug" is a **code-reading claim from the pre-registration**, with
no file, no SHA and no line range filed anywhere in `benchmarks/`, and by
construction no measurement — the arm that would have measured it was struck
before it ran. And the named target, `create_cloud`, is the packing entry point
the bridge **calls**; this report files no evidence about how much of the cost
sits in bridge-authored code versus in the helper, and none may be inferred from
the phrase "the per-point packer".

**This report therefore makes no claim that separates architecture from
implementation on the bridge's publish path**, and the pre-registration's own
position — that one PR could neutralise the section — stands unmeasured in
**both** directions: neither confirmed nor refuted. Every C2 sentence below is
scoped to E0 or E as measured, and the separation the spec wanted is recorded as
**not measured**, not as an inference.

### 4.2 E0 — the bridge as its authors ship it

**⚠ EVERY E0 CENTRAL-TENDENCY STATEMENT IS OPTIMISTICALLY BIASED, BY A
MECHANISM CORRELATED WITH E0's OWN REGISTERED FAILURE, AND THE BIAS CANNOT BE
ESTIMATED FROM THE SURVIVING POOL.** `E0/run-005` and `run-006` were excluded
because NDT published **exactly one** pose each, which makes the cadence
function raise and the run fail its smoke step; the five pooled runs carry
8 / 17 / 8 / 6 / 6 NDT poses against **the three dropped runs' 1 / 1 / 0** —
`E0/run-009` recorded **zero** NDT poses and is excluded `gate:arm-failed`
(`p3-baseline.md` §6's per-run table; `run-010` has no `observer.csv` at all).
So **three of the four excluded E0 runs are the three worst-performing runs in
the cell**, and the conditioning is stronger than "at least two poses" alone
conveys. The pool is
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

| topic on cell E0                      | rate across the pool | context                                                                                 |
| ------------------------------------- | -------------------- | --------------------------------------------------------------------------------------- |
| `pose_estimator/pose_with_covariance` | **0.08 – 0.27 Hz**   | NDT starved by the `is_dense` ⇄ `crop_box_filter_self` contract mismatch — see below    |
| `localization/kinematic_state`        | 13.37 – 14.19 Hz     | EKF output                                                                              |
| `lidar/top/pointcloud_before_sync`    | 8.36 – 8.43 Hz       | at 1.04–1.05 MB/s                                                                       |
| `control/command/control_cmd`         | 2.11 – 4.13 Hz       | static/unengaged arm, downstream of the starved localization chain — see the note below |

**The NDT row's mechanism, named rather than left as an adjective.** The
registered cause is a **two-sided interop contract mismatch, not an
architectural property of the bridge**: "the as-shipped bridge publishes
`is_dense=False` and **Autoware's `crop_box_filter_self` rejects every cloud**
… so NDT is structurally starved" (`benchmarks/config/cells.yaml`, cell-E0
block; identically at `benchmarks/results/PROVENANCE.md` §9.3). It is a
**one-flag defect at the seam**, and this campaign's own data shows it is not
architectural: with that single flag flipped (`0001-lidar-is-dense.patch`, one
line), the **same architecture, same CARLA, same container** yields
**1.91 – 7.52 Hz** on cell E (§4.3). Stated as a statistic the pools support
rather than as a multiplier they do not: the **pooled medians differ by ≈ 45×**
(E0 **0.11 Hz** over `E0/run-002`, `003`, `004`, `007`, `008`; E **4.99 Hz** over
`E/run-011`…`016`), and **the two ranges do not overlap — every cell-E run
exceeds every cell-E0 run** (E min 1.91 Hz against E0 max 0.27 Hz). No paired
design exists between the two arms, so no per-run recovery factor is computable;
the earlier "20–70×" was derivable from neither pool (the extreme ratios span
7.1× to 94×). The word
"structurally" previously stood alone in that cell while this document uses
"STRUCTURAL" 40 lines below to mean _argued from architecture rather than
measured_; the two senses are different and the collision is removed here.

**The `control_cmd` row is not a bridge control-loop measurement**, and it is
printed on both E arms (§4.3) so the row that reads worst does not appear only
on the arm labelled "the bridge as its authors ship it". These are **static,
parked, unengaged** runs; a control-command rate on them measures the downstream
Autoware stack fed by a starved localization chain, not a bridge control loop —
the same reading this report applies to cell A, whose "control publisher
advertises and stays silent while unengaged, 24/24" (§3.2) and draws no
conclusion about cell A's control loop from it. The corresponding cell-E figures
are **1.10 – 4.21 Hz** across `E/run-011`…`016` (`p3-baseline.md` §3, cell E),
i.e. within the same band on the _patched_ configuration, which is itself the
reason no property of the bridge may be read off either row.

The one E0 run the M5 gate ever scored, `E0/run-003`, reads `ndt_rate_ratio`
**0.038** (`p3-baseline.md` §6). **This is E0's registered expected outcome,
written down in advance** — PROVENANCE §9.3: "Cell E0 is expected to be
UNSCOREABLE, and that is its registered result." It is not a surprise finding
and is not presented as one.

### 4.3 E — the harmonized arm, and its static-only downgrade

Cell E applies both patches. **The harmonization list, complete against
`benchmarks/patches/python-bridge/0002-sensor-config-harmonized.patch` rather
than summarised** — the earlier list read as exhaustive and omitted three
changes, one of which is on Autoware's side of the seam:

| change                                               | as shipped (E0)                         | harmonized (E)                                                                                                                                                                                             |
| ---------------------------------------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LiDAR channels / points-per-second                   | **64 ch / 300 000 pts/s**               | 16 ch / 288 000 pts/s                                                                                                                                                                                      |
| FOV (upper / lower)                                  | **+10.0 / −30.0**                       | +15.0 / −15.0                                                                                                                                                                                              |
| range                                                | 100                                     | 100 (unchanged)                                                                                                                                                                                            |
| `frequency_hz` (publish throttle)                    | 11                                      | **20**                                                                                                                                                                                                     |
| **`rotation_frequency`**                             | **20**                                  | **10**                                                                                                                                                                                                     |
| **observed LiDAR topic (`topic_suffix`)**            | **`/pointcloud_before_sync`** (shipped) | **`/pointcloud_raw_ex`** (renamed by the patch)                                                                                                                                                            |
| cameras in the enabled list; `multi_camera_combiner` | 6 cameras enabled; combiner running     | cameras dropped; combiner disabled                                                                                                                                                                         |
| GNSS covariance diagonal                             | 0.01 / 1.0                              | 0.1 / 0.05 (extension's values)                                                                                                                                                                            |
| **Autoware `crop_box_filter_self` input remap**      | `/pointcloud_before_sync`               | **`/pointcloud_raw_ex`** — a hunk in `carla_sensor_kit_launch/pointcloud_preprocessor.launch.py`, i.e. **the patch edits Autoware, not only the bridge**, while being filed under `patches/python-bridge/` |

So harmonization moved the bridge's rig **in both directions** (down on
channels, up on publish rate, down on rotation rate), and the topic difference
between the two arms is the **harness's rename**, not a bridge property.

**⚠ The 20 Hz denominator is the campaign's choice, not the bridge's default,
and `cells.yaml` registers it as such** — carried here because the table below
puts NDT beside a ~19.9 Hz LiDAR rate and invites a reader to divide: "20.0 is
also the **HARMONIZED target**: 0002 sets this rig to 16 channels at 288000
pts/s, the `vlp16` sweep class, so **the rate is the campaign's own
comparability choice and not the bridge's default**" (`benchmarks/config/cells.yaml`,
cell-E block). The bridge's authors ship **11**.

Cell E's six valid static runs are `E/run-011`…`run-016`
(`p3-baseline.md` §3, cell E):

| topic on cell E                       | rate across the six runs | context                                                                                             |
| ------------------------------------- | ------------------------ | --------------------------------------------------------------------------------------------------- |
| `pose_estimator/pose_with_covariance` | **1.91 – 7.52 Hz**       | NDT — against a **20 Hz target the campaign chose**, not the bridge's shipped 11                    |
| `localization/kinematic_state`        | 19.32 – 19.94 Hz         | EKF output                                                                                          |
| `lidar/top/pointcloud_raw_ex`         | 19.83 – 19.91 Hz         | at 2.19–2.20 MB/s                                                                                   |
| `control/command/control_cmd`         | 1.10 – 4.21 Hz           | static/unengaged arm, downstream of localization — **not** a bridge control-loop measurement (§4.2) |

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
was never measured closed-loop at all: ONE closed-loop run was attempted at the
campaign's registered configuration** — `E/run-009` at `patches_git_sha
ccff4f94`; `E/run-007` and `E/run-008` are the cell's only other closed-loop
manifests and both are **superseded-harness exclusions** (`harness:092dc9a`) at
a pre-registration patch set, never an arm result (§2.4) — **it failed at the
route link, and THE CAUSE IS NOT ESTABLISHED.**

**⚠ The attribution boundary §3.4 grants tier4-native applies here in exactly
the same terms, and is stated rather than left asymmetric.** Cell E's failing
link — `behavior_path_planner: waiting for route` for 63.98 s — is the **same
component on the same host** that failed cell B's arms, and is equally
un-root-caused. **Nothing here establishes an intrinsic property of the
python-bridge approach**, and no sentence in this report may be read as though
it did. The denominator is **1**, against the 0-of-15 this report prints for
cell B (§3.3): a single attempted run supports no rate, no comparison and no
inference about how the bridge would behave on a second attempt.

### 4.4 The byte-rate lower-bound argument — as registered, and as measured

The spec registered a specific lower-bound argument for C2: that the bridge's
16 B/point layout against the natives' 32 B/point means its ceiling is reached
at roughly half the byte rate, which would make any measured gap a **lower
bound** on the architectural gap.

**That argument is NOT backed by a filed measurement in this campaign, and this
report does not assert it.** What the tree actually registers about point
layout is a different fact about a different cell: `benchmarks/README.md`'s
2026-07-30 amendment-ledger entry and the "Cell A's bench-harness control (Task
15b)" section's per-message-size derivation (headings cited rather than line
numbers, which drift — see §7) record that **cell A** ships **2.118×** the bytes
for the same point count (512 184 B/msg against 241 813 B/msg, `bench_observer`
medians), and that **cell B's running binary emitted a 16 B/point cloud where its own
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

| pool                 | LiDAR topic observed         | observed MB/s | **per-row caveat (inline, and symmetric)**                                                                                                                                                                                                                             |
| -------------------- | ---------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `A/run-003`…`012`    | `.../pointcloud_raw_ex`      | 10.25 – 10.26 | CARLA 0.10 fork, UE5.5 source build, `editor-game`; **32 B/point layout — ships 2.118× the bytes for the same point count, which is most of why this row tops the column** (README, Task 15b §4; §7 row 6)                                                             |
| `B/run-013`…`022`    | `.../pointcloud_raw_ex`      | 2.10 – 2.25   | CARLA 0.10 tier4 fork, UE5.5 source build, `editor-game`; **wire `point_step` 16 against a pinned source specifying 32 — registered UNRESOLVED** (§7 row 6)                                                                                                            |
| `E/run-011`…`016`    | `.../pointcloud_raw_ex`      | 2.19 – 2.20   | **stock CARLA 0.9.15 — different simulator generation, different container; not comparable as a ranking**; 0.9.15 is the bridge's **supported** platform (§1.3), and this rig is the harmonized 16 ch one                                                              |
| `E0/run-002`…`008`\* | `.../pointcloud_before_sync` | 1.04 – 1.05   | **as above, plus the shipped 11 Hz throttle and the shipped 64 ch rig**, observed on `/pointcloud_before_sync` — **the topic this package ships**; patch 0002 renames it to `/pointcloud_raw_ex` on cell E, so the topic difference is the harness's, not the bridge's |

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

**53 capability entries. Every one has an ARGUED reproduction path on the
extension architecture — but three depend on artifacts that exist in neither
tree, so their cost is a lower bound, not a reachability class.** The earlier
wording ("none is unreachable") is contradicted by the catalog's own text and is
corrected here: §6.7's raw-UDP packet **encoder is not in either tree** — it
lives in the **private** `RobotecAI/RGL-extension-udp`, and "whether that
extension is obtainable, and under what licence, could not be established …
**the reproduction cost of this capability is unbounded from this repository's
side**"; §6.3's Agnocast capability also needs the `carla_agnocast_bridge` node,
an Agnocast-enabled Autoware launch and the Agnocast **kernel module**, "none of
which exist in either tree"; and §6.12's 35 JP signal `.uasset` files are of
**unestablished redistributability**. (§6.4, the fourth L entry, needs the
third-party RGL SDK and toolchain — obtainable, but likewise outside both
trees.) See `gap-catalog.md` §7.1.

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
**per-entry, not cumulative**. **Why so many main-branch entries land at S, in
the catalog's own words, because carrying the definition without the reason
invites "89 % of tier4's merged integration work is a small lift":** "a class is
the remaining delta from this repository's side (**which is why §5.14, §5.15,
§5.16, §5.21 and §5.22 are S — the sibling fork already carries the equivalent
core change**)" (gap-catalog §7.3), and a sixth, §6.11, is S "because the defect
is in a code path this architecture does not use". Five of the main-branch S
entries are S **only because the extension's own required CARLA fork
independently re-implemented the same core change** — the class measures what is
left to do here, not how large tier4's original change was. Two more (§5.9,
§5.10) are S on **code volume** while their remaining work is a **C ABI version
bump**, a compatibility cost the class does not price (gap-catalog §5.0.4).

**The single most decision-relevant fact in the catalog, in its own words:**
the side-branch half skews far harder toward CARLA-core seam work — **18 of 25,
against 13 of 28 on main** — i.e. main's capabilities are largely ROS-layer and
the side branches' largely are not (gap-catalog §6.0.3). **⚠ That statistic
received no second pass.** It is computed entirely from the **39** seam- and
extension-side classifications; the adversarial re-argument below covered the
**14 `already-exists` entries only** (26 % of 53) — precisely the entries
_excluded_ from this statistic, because they carry the overclaim risk. So "none
was overturned" is a statement about the 14 and is **not** support for
18/25-vs-13/28, which rests on a single-analyst code-reading judgement with no
inter-rater or second-pass check (gap-catalog §7.2).

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
  maturity qualifier (gap-catalog §7.2). **The scope of that pass is 14 of 53
  entries**; the other 39 received one classification pass each (above).

## 6. Community-acceptance rubric

`docs/evaluation/rubric.md` carries 11 criteria across the three approaches,
each with a pre-registered direction and a value cell traceable to a command or
a linked observation. **It computes no total and this report adds none.**

Summarised, without re-deriving any cell:

Every row below carries a value **per approach, in the order
extension / tier4-native / bridge**, and no row is a ranking.

| criterion                    | what the snapshot found                                                                                                                                                                                                                                                                                                                                               |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1–2 governance / who accepts | AWF org but sole author, CI-only gate / **`autoware-support` frozen at the ruleset level, no GitHub-side approval gate configured — internal tier4 review is not visible to this snapshot** / **AWF monorepo under PSC governance, 1 required CODEOWNER approval**                                                                                                    |
| 3 unmerged artifact set      | 219 + 25 vs 305 vs 0 (endpoints pinned in §3.5)                                                                                                                                                                                                                                                                                                                       |
| 4 upstreamed ratio           | 66 merged of 98 opened (all-time PR proxy for the fork's 2 dominant authors) vs **0 PRs opened by the 4 Robotec/tier4-specific delta authors — ratio undefined, not 0 %** vs N/A (in-tree). **Different populations; not a like-for-like ratio, and no ordering is implied** (§3.5)                                                                                   |
| 5 runs on a release binary   | No / No / **Yes**                                                                                                                                                                                                                                                                                                                                                     |
| 6 bus factor                 | 1 (this repo; fork delta 2-author dominated, 52 %) / 2 contributors dominate (160/305 ≈ 52 %) / 4 named maintainers + 9 human authors                                                                                                                                                                                                                                 |
| 7 activity                   | young repo (annotated) / **`autoware-support` 0 in 90 d — while `tier4/main` carries 205 in the same window** (§3.5) / 8 in 90 d                                                                                                                                                                                                                                      |
| 8 install complexity         | UE5.5 source build / UE5.5 + ~300 GB, 3–4 h / binary                                                                                                                                                                                                                                                                                                                  |
| 9 CI on the integration path | none live in any of the three; **the tier4 row also measures CI reachability — a ~300 GB / 3–4 h UE5 build is not runnable on public CI** (§3.5)                                                                                                                                                                                                                      |
| 10 license                   | Apache-2.0 / MIT / Apache-2.0 — all compatible                                                                                                                                                                                                                                                                                                                        |
| 11 documentation             | 8 operator docs (~130 KB) / one 349-line branch README, **scoped to `autoware-support`; the `ue5-dev`/`main` lineage additionally carries `README_RGL.md`, `Docs/rgl/*` and `Docs/ros2_native.md`** / one 301-line package README + `CHANGELOG.rst`. **Rubric criterion 11 is a registered QUALITATIVE judgment, "not a numeric score" — read no ratio off this row** |

Read the rubric itself for the cells; each carries its own corrections from an
adversarial re-verification round that overturned four cells and recorded one
process slip in place rather than rewriting it — **the slip being that the
value-filling commit edited a pre-registered Direction paragraph in Criterion 7
(§2.1 names it)** — plus a second, 2026-08-05 round recorded there under "Fix
round 2".

## 7. Confound table

Every row cites the measurement or the pin that establishes it.
`p4-transport-sweep.md` §7.2 is the authority on which P3-era rows still bind
for P4 and which two are **retired** — this table takes its carry-forward from
there, not from `p3-baseline.md` §7 alone. "README" means `benchmarks/README.md`.

**README citations are by SECTION HEADING, not by line number.** The previous
revision carried P3-era line numbers that had drifted: seven of the nine
resolved only at the P3 pin `269b931` and landed on unrelated text at HEAD and
at the P4 pin `fcb8333` — four off by exactly +201 lines, the rest by
+236…+300, and one (`:1323`) on a blank line — while a ninth was a P4-era
citation, so the table silently mixed two pins' numbering. Headings do not
drift, and every heading named below was verified to resolve at HEAD.

| #   | confound                                                                                                                                                                                                                                                                                                          | binds              | where registered                                                                                                                                                              |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | CARLA generation: stock 0.9.15 `shipping-headless` vs 0.10 fork `editor-game`                                                                                                                                                                                                                                     | E/E0 vs all        | P3 §7.1 P3-4; per-run `manifest.json`                                                                                                                                         |
| 2   | Map assets: E/E0 on the unshifted Town10 pcd (+0.475 m); A/B/B-cyc on rung-2 regen                                                                                                                                                                                                                                | all                | P3 §7.1 P3-3; P4 §7.2                                                                                                                                                         |
| 3   | GNSS: GT anchor per-approach (extension +0.000 m, bridge −1.425 m); covariance patched                                                                                                                                                                                                                            | E/E0 vs A/B        | README "Ground truth is the CARLA actor origin; localization is `base_link`" + its "Amendment: the GT anchor is per-approach, not campaign-wide (2026-07-30)"; patches README |
| 4   | **RMW pairing is CROSS-VENDOR in P3**: A on CycloneDDS + `docker/cyclonedds.xml` (lo only), B on Fast-DDS + `udp_only.xml` — **NOT rmw-matched**; P4 rmw-matched but NOT profile-matched                                                                                                                          | B, B-cyc           | README "DDS middleware and transport (Task 9): the B family runs a different one"; P4 §7.1 P4-2                                                                               |
| 5   | Row-11 inherited caveats: Cyclone-no-profile binds a routable NIC, graph is flaky                                                                                                                                                                                                                                 | B-cyc              | P4 §7.1 P4-3                                                                                                                                                                  |
| 6   | Point layout bytes: A ships 2.118× bytes/msg; B's wire `point_step` 16 vs pinned 32                                                                                                                                                                                                                               | A vs B             | README amendment-ledger entry dated 2026-07-30 + "Cell A's bench-harness control (Task 15b)" §4                                                                               |
| 7   | Publisher QoS and endpoint config differ per approach; observer RMW follows the cell                                                                                                                                                                                                                              | all                | P3 §7.1 P3-2; gap-catalog §5.16                                                                                                                                               |
| 8   | Sensing graph: `carla_sensor_kit` vs `awsim_labs_sensor_kit`; relay on the concat topic                                                                                                                                                                                                                           | E vs A/B/C         | README "Sensing graph: `carla_sensor_kit` (E family) vs. `awsim_labs_sensor_kit` (A/B/C/D)"; P3 §5.2                                                                          |
| 9   | Container / process placement and images; observer is `network_mode: host`                                                                                                                                                                                                                                        | all                | P3 §7.1 P3-4; P4 §7.1 P4-4                                                                                                                                                    |
| 10  | Pacing: `duel.sh` gained inter-run pacing mid-campaign; sweep paced/unpaced arms                                                                                                                                                                                                                                  | all                | P3 §8.4 #1; P4 §6.4                                                                                                                                                           |
| 11  | Physics substepping: the B family disables it at 20 Hz, A leaves the default on                                                                                                                                                                                                                                   | A vs B/B-cyc       | README "Physics substepping (Task 13): B disables it at 20 Hz, A leaves CARLA's default on"; P4 §7.2                                                                          |
| 12  | **THE IMAGE CONFOUND — P4's "single most important one", now MANDATORY-INLINE (§0 rule 3):** B/B-cyc run `universe-devel-cuda` by digest, A runs `universe-devel` by tag; **it sits under every B-side number and no row in §3.2 or §3.3 is corrected for it**; B45 struck                                        | A vs B/B-cyc       | P4 §1, §7.1 P4-1; P3 §2.2                                                                                                                                                     |
| 13  | Perception off: clear-road dummy stand-in vs the bridge family's real CUDA perception                                                                                                                                                                                                                             | A/B/C vs E family  | README "Perception load: clear-road stand-in (A/B/C/D) vs. real CUDA perception (E family)"                                                                                   |
| 14  | Fork delta magnitudes: 219 (+25) vs 305 vs 0 — **a dated snapshot over moving refs, not a regenerable figure; endpoints pinned in §3.5**                                                                                                                                                                          | structural         | rubric criterion 3                                                                                                                                                            |
| 15  | Sensor-rate asymmetry: `lidar_expected_hz` 20.0 (A) vs 10.0 (B/B-cyc), against A                                                                                                                                                                                                                                  | A vs B/B-cyc       | P4 §7.1 P4-5                                                                                                                                                                  |
| 16  | **Clock-fit residual asymmetry on BOTH arms and in BOTH phases**, margin 2.0 ms: B-cyc closed-loop **54.60** vs A **3.58**; B-cyc static **3.77** vs A **1.77**; **P3 cell B static 22.48 vs cell A 1.85**. The `one_hop_wall_ms` parity **rows** are the weakest of the parity rows, the closed-loop one more so | A vs B, A vs B-cyc | P4 §2.6, §7.1 P4-9; P3 §4.1 tool row; README duel-metric section                                                                                                              |
| 17  | CAL-seam residuals: publish order (sign NOT established), in-core-only sample loss                                                                                                                                                                                                                                | CAL-seam           | P4 §7.1 P4-8                                                                                                                                                                  |
| 18  | Static pre-arm control silence: 2 of 10 B-cyc static runs, unmasked on that arm                                                                                                                                                                                                                                   | B-cyc              | P4 §7.1 P4-7                                                                                                                                                                  |
| 19  | `control_mode`: A reports MANUAL parked, tier4 reports AUTONOMOUS unconditionally                                                                                                                                                                                                                                 | A vs B             | P3 §7.1 P3-6                                                                                                                                                                  |
| 20  | Observer + G1 ladder rung 2: not reproducible from its pin, coverage ~292 m of 438.9 m                                                                                                                                                                                                                            | all                | P3 §7.1 P3-2                                                                                                                                                                  |
| 21  | Route difficulty: Town10 vs Nishi-Shinjuku (cell C is confirmatory only)                                                                                                                                                                                                                                          | A/B vs C           | README "Route difficulty: Town10 (cells A/B) vs. Nishi-Shinjuku (cells C/D)"                                                                                                  |
| 22  | Localization initialization: the stop check blocks every path on cell B                                                                                                                                                                                                                                           | B, B-cyc           | README "Localization initialization (Task 13): the stop check blocks every path on cell B"                                                                                    |

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

**⚠ This checklist is SELF-CERTIFYING from this repository.** Its left column is
the design spec's "**Honesty constraints (what the report must NOT claim)**"
section — "Global Constraints" was not the spec's heading, and is corrected
here — and **the spec is not in this repository** (§0). A reader cloning this
branch therefore cannot check a single one of the eleven rows against the
constraint it claims to satisfy: the right column is checkable in-tree, the
left is not.

| #   | constraint (spec, "Honesty constraints")                                                       | mechanism in this document                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| --- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **No composite acceptance score**                                                              | `rubric.md` carries a "No composite score" banner as its own section; this report contains **no ranking table, no weighting and no total**. §6 summarises per criterion and links out; §3–§5 report per metric and per entry.                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 2   | **Bridge and native numbers never share a ranking table without the generation caveat inline** | Exactly one table places an E-family figure beside a native one (§4.4). It carries a **per-row caveat column, filled on every row and SYMMETRIC** — the 2026-08-05 round added the native rows' own registered caveats (cell A's 2.118× byte layout, cell B's unresolved wire `point_step`), which previously sat two paragraphs above the table while only the bridge rows carried a limitation in-row. The sentence under it states it is not a ranking and draws no ordering. All other E/E0 figures live in §4's own arm-scoped tables.                                                                                                       |
| 3   | **No attribution of UE4-vs-UE5 renderer/engine differences to the bridge**                     | C2's load-bearing contrast is **E vs E0**, within one approach, one CARLA version and one container family, differing only by the patch set (§4.1–§4.3). No cross-generation delta is computed anywhere. The publish-disabled ablation arm exists only inside cells A and B-cyc and is registered **within-cell only** (P4 §6.4 — §7 carries no row for it).                                                                                                                                                                                                                                                                                      |
| 4   | **E2E latency under a 20 Hz sim clock is context, never C1 evidence**                          | C1 rests **only** on the five pre-registered margin metrics (§3.2, §3.3) and the C1(a) paired delta (§3.1). The ~51–53 ms arrival-domain figures on cell A are one sim tick and appear nowhere in §3; the arrival-domain rates quoted in §4 are labelled as such, and §4.5 restates the prohibition on cross-reading them against `achieved_rate_ratio`.                                                                                                                                                                                                                                                                                          |
| 5   | **Every number carries its cell/run reference**                                                | Every figure names its pool (`A/run-016`…`025`, `CAL-seam/run-001`…`005`, `E0/run-002`…`008`, …) or the census that produced it — appendix command 10, whose script and output are both printed — plus the wrap-doc section that owns it.                                                                                                                                                                                                                                                                                                                                                                                                         |
| 6   | **Every C1/C2 sentence names its arm**                                                         | C1 sentences name `A-vs-B` or `A-vs-B-cyc` **and** static or closed-loop; C2 sentences name E0, E, or the struck E-opt. §0 rule 2 states the discipline; §3.2/§3.3 headings carry the arm; §4.1 fixes the three C2 arms before any C2 number is quoted.                                                                                                                                                                                                                                                                                                                                                                                           |
| 7   | **Wording downgrades the data forced are applied mechanically**                                | Marked ⬇ at each site: equivalence **inconclusive** on static `control_staleness_ms` and on `carla_process_cpu_pct` (§3.2, §3.3); A-vs-B closed-loop **not computable** (§1.2, §3.3); C1(a) an **upper bound** (§3.1); C1(c) rescoped (§3.5); cell E **static-only** (§4.3); the E family on the **relative** G1 branch (§4.5); the spec's bridge byte-layout premise **unmeasured** (§4.4).                                                                                                                                                                                                                                                      |
| 8   | **Mandatory caveats travel inline**                                                            | **Five** caveats each appear **in the paragraph that quotes their figures**, not in a trailing caveats section: the four-of-five static bracket (§3.2), A-vs-B-cyc-not-A-vs-B (§3.3), C1(a)-upper-bound (§3.1), E0-optimistic-bias (§4.2), and — promoted in the 2026-08-05 adversarial round — the **Autoware image confound** (§0 rule 3; §3.2, §3.3, §7 row 12), which its own source calls the single most important one and which this report had carried only as a table row. The clock-fit residual, the static arm's two-invocation collection and the P3 cross-vendor RMW pairing are likewise carried inline in §3.2 in the same round. |
| 9   | **Nothing is recomputed, no verdict is manufactured**                                          | This task ran no verdict tool and **re-scored, reclassified or rewrote no filed run**; its only read of `benchmarks/results/` is appendix command 10's read-only `manifest.json` census, which is why §0 states the narrower claim rather than "read no filed run". Both wrap docs computed their verdict **once**, with no filtering flags, and reproduce their full output verbatim; §9 gives the commands and the SHAs so a reader regenerates rather than trusts.                                                                                                                                                                             |
| 10  | **Refuted hypotheses stay in the record with the diagnostic that refuted them**                | Carried, not dropped, each with the diagnostic that refuted it: Phase 0's publisher-count-vs-emission error and its "killing the relay stops NDT" causal wording, plus the nine-vs-eight count correction (§3.4's closing three paragraphs, quoting `p3-baseline.md` §5.2 and PROVENANCE §6.5/§6.8); the `B/run-032` correction to the delivery-probe reading (§3.4); C1(a)'s retracted conservatism argument (§3.1); and the spec's own bridge byte-layout premise (§4.4).                                                                                                                                                                       |

**Known residual weaknesses of this report, stated rather than left to the
reviewer:** the C1(a) publish-order residual's sign is unestablished; the
`carla_process_cpu_pct` reversal is unexplained and is the largest thing P4
discovered and did not resolve; the A-vs-B closed-loop verdict is permanently
non-computable from this data; E-opt's absence blocks the
architecture-versus-implementation split C2 was designed to make; **cell E's
closed-loop non-result rests on ONE attempted run at the registered
configuration with no established cause, and C2's registered "lower
sustainable-load ceiling" half has no measurement on this campaign at all, cell
E being out of the M4 sweep** (§4, §4.3); and the extension's own governance row
(solo author, zero external review) is its weakest structural evidence.

### 8.1 Stated limitations from the 2026-08-05 adversarial re-review

The round that produced the disclosures marked throughout this document also
found defects this branch **cannot** repair, because they are owned by documents
outside its scope or would require re-measurement. They are recorded here rather
than fixed:

1. **The `parity` verdicts' interval coverage was never validated**, and the
   percentile bootstrap of a median at n = 10 is expected to be
   **anticonservative in the direction of `parity`** (§2.2). Fixing this needs a
   coverage study or a different estimator, i.e. a re-analysis under a rule that
   was not pre-registered; neither is available on this branch.
2. **No multiplicity correction exists** for the fifteen verdicts adjudicated at
   `alpha = 0.05`, and none may be invented now without adjusting the decision
   rule after seeing the verdicts (§2.2).
3. **No leave-pair-1-out sensitivity check** exists for the P3 duel pool, whose
   pair 1 predates the mid-campaign pacing amendment and sits on a different
   harness sha (§1.2). Running one now would be a second analysis of an
   already-filed verdict, which §2.5's one-shot discipline forbids.
4. **The M4 ceiling search's sensitivity at n = 3 per arm was never quantified**
   (§1.3). "Ceiling not located" bounds where the search stopped and nothing
   more.
5. **`p3-baseline.md` §6 uses "a structurally starved NDT" as a bare noun phrase
   with no mechanism.** That wrap doc is not editable from this branch; the
   propagation is stopped here — §4.2 resolves the phrase to the registered
   `is_dense=False` ⇄ Autoware `crop_box_filter_self` contract mismatch, and this
   report does not inherit the bare phrase.
6. **The `one_hop_wall_ms` margin's calibration is not reproducible from a
   committed tree** on 12 of its 15 CAL-rmw runs (`-dirty` shas), its amendment
   rule is recorded by `margins.yaml` itself as not literally satisfiable, and
   the calibration's delivered-load asymmetry makes it a weak loopback-parity
   estimate (§2.1). The frozen 2.0 floor binds for any |Δ| ≤ 1.0 ms and the
   measured |Δ| is 0.4152 ms, which bounds — but does not remove — the exposure.
   Repairing the provenance would require re-collecting CAL-rmw.
7. **§3.5's, §6's and §7 row 14's numbers are a dated snapshot, not a
   regenerable figure** (§9): authenticated `gh` against a moving GitHub, two
   clones absent from this repository, sliding date windows, and no committed
   console transcript of the 2026-08-05T02:13 UTC run. The endpoint SHAs are now
   pinned (§3.5) and `rubric.md`'s "Snapshot audit trail" appendix carries what
   could be re-derived read-only, but the `gh`-derived half remains unauditable
   from this repository alone.
8. **The design spec is out of repository**, so §8's entire left column and
   every registered-wording quotation in §3–§5 are self-certifying from here
   (§0). Publishing the spec is the only fix.
9. **The 18/25-vs-13/28 seam-skew statistic received no second pass** (§5); an
   inter-rater check would be new analysis, not a re-reading.
10. **`cal_report.py` renders p50 at two decimal places**, so §3.1's four-decimal
    table and its Δ column are not obtainable from §9 command 4 alone; §9 now
    carries the unrounded walk instead of pointing only at the rounded renderer.
11. **The E-family per-point layout is unmeasured** (§4.4), so the spec's
    16-vs-32 B/point lower-bound argument stays retracted rather than resolved.

## 9. Regeneration appendix

**No MEASUREMENT number in this report requires re-collection.** Every figure
computed over `benchmarks/results/` regenerates from committed raw data plus
committed scripts.

**⚠ The STRUCTURAL half does not, and the earlier unqualified claim was wrong
about it.** §3.5, §6 and §7 row 14 — 219, +25, 305, 121, 66/98 ≈ 67.3 %, the
2026-04-08 tip, 0-in-90-days, one-CI-run-ever — come from **command 8**, which
needs an authenticated `gh` against a **moving** GitHub, **two git clones that
are not in this repository**, at branch tips that were previously **not pinned**,
inside **sliding** 90-day/365-day windows; and when a clone is absent the script
prints `SKIP` and still **exits 0**, so criteria 3, 6 and 7's fork halves vanish
with no failure signal. **No console transcript of the 2026-08-05T02:13 UTC run
was committed anywhere** — in pointed contrast to
`benchmarks/evidence/p4-task16-wrap/identity-walk.log`, which is filed beside its
script exactly so command 7 is checkable without re-running it. Three partial
remedies are in place and none of them makes that half regenerable: the two
clone endpoints are now **pinned by SHA** in §3.5 and in `rubric.md` criteria 3
and 6; `rubric.md` carries a **"Snapshot audit trail"** appendix recording what
was re-derived read-only and what was not; and the script now prints
`git rev-parse` beside every `rev-list --count` and no longer fetches by default
(§9 command 8). **Read §3.5, §6 and §7 row 14 as a dated snapshot** (§8.1
item 7).

The two phases pin the commits they were generated at, and **those pins are
reused here rather than re-derived**:

| phase                        | pinned at                                                                                                                                                                                                                                                                                                                                                                         | source                    |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| P3 (`p3-baseline.md`)        | `269b931`                                                                                                                                                                                                                                                                                                                                                                         | its §0 and §10            |
| P4 (`p4-transport-sweep.md`) | `fcb83334637b6c7be6e7fda88da2ce2dd0f77c46`                                                                                                                                                                                                                                                                                                                                        | its §0.1 and §10          |
| rubric snapshot              | `febb895` → `4e8eff0` → `2671130` (a branch rebase renamed these three; the pre-registration record is unchanged in content, and the earlier hashes `dd37379` → `324dc36` → `16e6757` are no longer reachable), retrieved 2026-08-05T02:13 UTC; clone endpoints `upstream/ue5-dev` `0a5ce0d5`, `feat/autoware-seminative-phase-b` `62ca380f`, `tier4/autoware-support` `6315b856` | `rubric.md` header + §3.5 |
| gap catalog                  | `tier4/autoware-support` @ `6315b856f8faf2118578322eb20a2b902a45a384`, fetched 2026-08-04 23:15 UTC                                                                                                                                                                                                                                                                               | gap-catalog §1.1          |

All commands run from the repository root. **Environment the filed digests were
produced on**, recorded because §2.2's `seed=20260727` reproducibility claim is
undiagnosable without it: **Python 3.12.3, numpy 1.26.4, PyYAML 6.0.1**;
`stats.py` uses `np.random.default_rng` (PCG64, stream-stable under NEP 19), so
the md5 in §2.5 reproduces across numpy versions that keep that guarantee. The
tree carries no dependency manifest for the analysis package and CI installs
`pytest pyyaml numpy` unpinned.

```bash
# 1. Per-cell tables (both phases). Exits 1, and the exit is fully explained
#    by cell CAL-rmw, which has no simulator and therefore no /clock.
PYTHONPATH=. python3 -m benchmarks.report benchmarks/results > /tmp/report-tables.md

# 2. The P3 duel verdict -- the campaign's single P3 invocation.
#    MUST be run at the P3 pin. At HEAD the tool no longer reproduces
#    p3-baseline.md section 4.1: cells.yaml has since gained cell A's
#    control_published_time_topic binding and 29 more cell-A runs were filed,
#    so control_staleness_ms prints `0/10` with ten MetricUnavailableError
#    notes instead of the filed `0/0` + UNAVAILABLE that section 3.2's table
#    quotes, and the inadmissible counts read 14/11 instead of 3/1. The five
#    margin numbers and every verdict string are unaffected.
git stash list && git checkout 269b931   # restore your branch afterwards
PYTHONPATH=. python3 benchmarks/scripts/duel_verdict.py A B | tee /tmp/p3-duel-verdict.md
git checkout -   # back to docs/evaluation-report

# 3. The P4 duel verdict -- P4's single invocation. Both arms come from this
#    one run. Use `>` not `| tee`: an rtk proxy compresses piped output here.
PYTHONPATH=. python3 benchmarks/scripts/duel_verdict.py A B-cyc > /tmp/p4-duel-verdict.md

# 4. C1(a): the CAL-seam run tables (section 3.1's `n` column and the
#    carla-server 249.70-252.67 % CPU means). NOTE: cal_report renders p50 at
#    TWO decimals, so section 3.1's 0.7242 / 0.4458 / +0.2784 and the whole
#    delta column are NOT obtainable from this command -- use command 4b.
for r in 001 002 003 004 005; do
  PYTHONPATH=. python3 -m benchmarks.scripts.cal_report benchmarks/results/CAL-seam/run-$r
done

# 4b. Section 3.1's UNROUNDED p50/p95/p99 deltas -- the source of the
#     +0.2784 column, the median/min/max line, and the tails bullet
#     (`Delta p95 median +0.118`, `Delta p99 median -0.045`, negative in 3 of 5).
#     This is p4-transport-sweep.md section 10 command 9, extended by two lines
#     for the tails, which had no command in either document.
PYTHONPATH=. python3 - <<'PY'
import statistics
from benchmarks.scripts.cal_report import summarize_run
d50, d95, d99 = [], [], []
for r in ("001", "002", "003", "004", "005"):
    s = summarize_run(f"benchmarks/results/CAL-seam/run-{r}")
    seam, core = s["topics"]["/bench/seam_cloud"], s["topics"]["/bench/incore_cloud"]
    d50.append(seam["one_hop_p50_ms"] - core["one_hop_p50_ms"])
    d95.append(seam["one_hop_p95_ms"] - core["one_hop_p95_ms"])
    d99.append(seam["one_hop_p99_ms"] - core["one_hop_p99_ms"])
    print(r, round(seam["one_hop_p50_ms"], 4), round(core["one_hop_p50_ms"], 4),
          round(d50[-1], 4), round(s["processes"]["carla-server"]["cpu_pct_mean"], 2))
print("p50 median", round(statistics.median(d50), 4),
      "min", round(min(d50), 4), "max", round(max(d50), 4))
print("p95 median", round(statistics.median(d95), 4))
print("p99 median", round(statistics.median(d99), 4),
      "negative in", sum(1 for x in d99 if x < 0), "of 5")
PY

# 5. M4 ceiling tables (section 1.3's "ceiling not located up to the 32ch
#    class").
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py A     --class vlp16
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py A     --class 32ch
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py B-cyc --class vlp16
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py B-cyc --class 32ch

# 6. Per-cell metric bindings quoted throughout.
PYTHONPATH=. python3 -c "from benchmarks.scripts.cell_info import load_cells_doc, metrics_for; \
  d=load_cells_doc(None); print(metrics_for(d,'A')); print(metrics_for(d,'B-cyc'))"

# 7. Identity / provenance census -- all of P4's section 9.
PYTHONPATH=. python3 benchmarks/evidence/p4-task16-wrap/identity_walk.py

# 8. The rubric snapshot (sections 3.5 and 6). READ THE WARNING ABOVE: this is
#    the one command that does NOT regenerate a filed figure. It needs an
#    authenticated `gh`, two sibling clones outside this repository, and a run
#    date; absent clones print SKIP and the script still exits 0. It now prints
#    `git rev-parse` for every endpoint it counts and does not fetch unless you
#    pass --fetch, so a re-run is comparable to the pinned SHAs in section 3.5.
#    Redirect it: the transcript is the only auditable artifact it produces.
bash scripts/evaluation/rubric_snapshot.sh > /tmp/rubric-snapshot.log 2>&1

# 9. The test-suite baseline. -> 1336 passed, 3 skipped (P4's was 1317/1,
#    P3's 1084/1). Carry forward P4 section 10's disclosure: one registered
#    load-sensitive flake,
#    test_teardown.py::test_tier4_autoware_sh_aw_sidecar_settles_on_the_post_exec_cmdline,
#    reproduces on demand under host load and is gated on 1-min < 1.0 AND
#    5-min < 3.0 rather than silenced.
python3 -m pytest tests/ -q

# 11. Section 2.1's pre-registration ordering. The TABLE's dates are COMMITTER
#     dates (%cd); %ad differs on ccd456e and 75f0fc1c. The two rubric commits
#     (febb895, 4e8eff0) are the exception and are quoted by AUTHOR date: a
#     rebase of this branch gave both the same %cd (2026-08-04 21:53:10), so
#     %cd cannot order them. Those two hashes were renamed by that rebase --
#     the report used to cite dd37379 and 324dc36, which no longer resolve on
#     a fresh clone; the pre-registration record itself is unchanged.
git log --reverse --format='%h %cd' --date=iso -- benchmarks/results | head -1
for h in b791ee9 941c805 884368d a3ca131 bdb5c42 96af345 75f0fc1 febb895 4e8eff0; do
  git show -s --format='%h | ad=%ad | cd=%cd | %s' --date=iso "$h"
done
# The rubric pair's ordering warrant is ancestry, not either timestamp: it
# survives rebases and cannot be forged backward. Exits 0 and prints OK.
git merge-base --is-ancestor febb895 4e8eff0 && echo "OK: febb895 is an ancestor of 4e8eff0"

# 12. Section 5's C3 counts, recountable in-tree without the external clone.
#     -> 54 and 54; one of each is the section-3 Entry template line, giving
#     53 entries and 38 S / 11 M / 4 L. The VERDICTS behind them are not
#     regenerable here: they rest on reading tier4/carla-autoware-native @
#     6315b856f8faf2118578322eb20a2b902a45a384 in an external clone
#     (gap-catalog.md section 1), which this repository does not contain.
grep -c '^- Reproduction path:' docs/evaluation/gap-catalog.md
grep -c '^- Effort class:'       docs/evaluation/gap-catalog.md
grep    '^- Effort class:'       docs/evaluation/gap-catalog.md | sort | uniq -c
```

Command 10 — the per-cell filed/excluded census behind §1.2 and §2.4. It is
given in full rather than cited, because no walk in either wrap doc produces
it: `p4-transport-sweep.md` §10 command 3 iterates cells `A` and `B-cyc` only,
so it cannot produce the counts for `B`, `E`, `E0` or `C`. This walk opens each
run's `manifest.json` and reads nothing else.

```bash
PYTHONPATH=. python3 - <<'PYTHON'
import collections, json, pathlib
root = pathlib.Path("benchmarks/results")
filed = excluded = 0
for cell in sorted(p for p in root.iterdir() if p.is_dir()):
    reasons = collections.Counter()
    n = 0
    for run in sorted(cell.glob("run-*")):
        m = json.loads((run / "manifest.json").read_text())
        n += 1
        if m["excluded"]:
            reasons[m["exclusion_reason"]] += 1
    filed += n
    excluded += sum(reasons.values())
    print(f"{cell.name:9s} filed={n:3d} excluded={sum(reasons.values()):3d} {dict(reasons)}")
print(f"TOTAL filed={filed} excluded={excluded}")
PYTHON
```

Its output, which is where §1.2's and §2.4's tables come from:

```text
A         filed= 53 excluded=  0 {}
B         filed= 33 excluded= 15 {'crash:cell-launch': 7, 'crash:collect_gt': 1, 'gate:arm-failed': 7}
B-cyc     filed= 45 excluded=  6 {'harness:65fbe09': 6}
C         filed= 14 excluded=  2 {'warmup:nishi': 2}
CAL-rmw   filed= 15 excluded=  0 {}
CAL-seam  filed=  5 excluded=  0 {}
E         filed= 16 excluded= 10 {'gate:arm-failed': 2, 'crash:cell-launch': 4, 'harness:fac5cb7': 1, 'harness:7425084': 1, 'harness:092dc9a': 2}
E0        filed= 10 excluded=  4 {'harness:e7ba92a': 2, 'gate:arm-failed': 1, 'crash:cell-launch': 1}
TOTAL filed=191 excluded=37
```

Four further walks are given verbatim in the wrap docs rather than repeated
here, because repeating a script is how two copies drift: the per-run manifest
classification (`p3-baseline.md` §2.1), the **duel-pool** census
(`p4-transport-sweep.md` §10 command 3 — cells `A` and `B-cyc` only, which is
why §2.4's exclusion counts need command 10 above instead), the
`ndt_rate_ratio` walk (P4 §10 command 5) and the clock-fit residual walk (P4
§10 command 6 — the source of §3.2's and §3.3's fit-residual tables). **P4 §10
command 9 is NOT in that list any more**: it is the only source of §3.1's
unrounded delta column, so it is reproduced above as command 4b (extended by
two lines for the p95/p99 deltas, which had no command in either document)
rather than left behind a pointer.

**Numbering note:** the fenced block above runs 1–9 plus 4b, 11 and 12; the
census below is **command 10** and every "appendix command 10" reference
elsewhere in this document means it.

**Collection is a different operation and is not needed to check anything
above.** A cell is collected with `bash benchmarks/run.sh <cell> [--arm ...]`,
and interleaved duel pairs with `benchmarks/scripts/duel.sh`; re-running either
would produce **new** runs, not the filed ones. Every figure in this report is
pure analysis over `benchmarks/results/`, which is committed.
