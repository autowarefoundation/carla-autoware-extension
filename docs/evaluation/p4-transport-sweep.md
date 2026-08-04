# P4 transport sweep: the A-vs-B-cyc duels, the C1(a) seam measurement, and the amended M4 ceiling search

**Written 2026-08-04 by the P4 wrap (Task 16 of the P4 transport-sweep plan).**
This is the campaign's second published record. Everything after
`docs/evaluation/p3-baseline.md` was collection; this document computes the P4
verdicts — **once** — and states what P4 does and does not support.

Three companion documents are load-bearing and are not restated here:

- `docs/evaluation/p3-baseline.md` — the P3 record whose open items P4 was
  registered to answer. Quoted, never re-derived.
- `benchmarks/results/PROVENANCE.md` — the per-run provenance of every filed
  run, the live findings, and the corrections this document summarises. P4's
  own sections are §11–§27.
- `benchmarks/README.md` — the pre-registration: metric definitions, margins,
  scope, and the `## Known confounds` section this document's confound table
  indexes.

The registration this document discharges is
`2026-08-03-p4-transport-sweep-design.md` in `claude-superpowers`, authored with
the owner **before any P4 measurement run**.

**All three of the following sentences are scoped to Task 16 — this wrap's own
task — and none of them is a branch-level claim.** Nothing under
`benchmarks/results/*/run-*/` was read-modify-written by Task 16. Task 16
deleted, reclassified, re-scored and hand-edited no filed run.
`benchmarks/config/exclusions.md`, `benchmarks/config/margins.yaml`,
`benchmarks/analysis/**`, `scripts/expected_topics.yaml` and
`scripts/spike_stack.json` are untouched **by Task 16**.

**At branch level two of those three are false, deliberately and on the
record**, and a reader arriving here as the P4 evidence inventory must not
carry away the opposite: `benchmarks/analysis/manifest.py` was amended twice
under the pre-registration's own amendment rule (`duel_id` in Task 2, `class_id`
in Task C2), and six B-cyc `32ch` manifests were reclassified to
`excluded: true` under a frozen exclusion criterion and re-collected. Both are
in §8.2 below, both are in `benchmarks/README.md`'s `### Amendment rule` ledger,
and 6.2 describes the re-collection.

## 0. How to read this document

### 0.1 Every number carries the command that reproduces it

Every figure below is produced by one of the twelve commands indexed in section
10, each also given verbatim at the head of the section that uses it. All were
run from the repository root on 2026-08-04 at commit
`fcb83334637b6c7be6e7fda88da2ce2dd0f77c46`, on an idle host. All are pure
analysis over committed files, and the duel is **deterministic**:
`benchmarks/analysis/stats.py:14` pins the bootstrap at `iters=10000,
seed=20260727, alpha=0.05`, so the verdict reproduces across runs of the tool
rather than merely being recomputed. Host load cannot move any output in this
document.

### 0.2 The verdicts were computed exactly once

The campaign's no-peeking rule forbade every P4 task from reading a duel
verdict, a delta, or a cross-cell median. Task 16 is the registered one-shot
where that reading happens, and the one-shot discipline replaces the no-peeking
rule:

- `benchmarks/scripts/duel_verdict.py A B-cyc` was invoked **one time**, with no
  filtering flags. Both arms' rows come from that single run, exactly as P3's
  did. Its complete output is reproduced verbatim in 2.1 — every row, including
  the ones that decline to decide. It was not re-run with adjusted flags after
  the first result, and it is not re-run anywhere else.
- The cell order is `A B-cyc` and is not reversible.
  `duel_verdict.py:1232` builds `expected_duel_id` by plain concatenation with
  no order normalisation, and the legacy clause at `:1233` is gated on
  `("A","B")`. `duel.sh` stamped `duel_id = "A+B-cyc"` on all forty duel runs
  for the same reason.
- `sweep_verdict.py` and `cal_report.py` are not under the one-shot rule — both
  were already read per cell as registered gate facts during collection
  (PROVENANCE §22.7, §26.7, §27.4, §12) — but the figures below are regenerated
  here rather than quoted, and they reproduce.

### 0.3 The per-cell regeneration, and its exit status

```bash
PYTHONPATH=. python3 -m benchmarks.report benchmarks/results > /tmp/p4-report-tables.md
```

`benchmarks/report.py`'s `main` takes the results **ROOT** and treats each child
as a cell; handing it a single cell directory makes it print an empty table that
passes on any input, which is why the root form is the documented one and is
what was run.

**The command exits 1, and the exit is fully explained by cell CAL-rmw**, in
exactly the way `p3-baseline.md` §3 explains it. Of 31 `RENDER FAILED` rows, 15
are CAL-rmw's — untagged by `(EXCLUDED)`, which is what drives the non-zero
exit — reading `ValueError: need >= 2 paired (sim, wall) samples`. CAL-rmw is a
`carla: none`, container-only cell with no simulator, so nothing ever publishes
`/clock`; its registered renderer is `benchmarks/scripts/cal_report.py`. The
other 16 failures are all `(EXCLUDED)`-tagged and are the expected shape of an
excluded run whose data was never written. **No P4-collected run failed to
render**: cells A (`run-015`…`run-053`, 39 runs — see §9.1 on why the P4
boundary falls at `run-015` and not `run-016`), B-cyc (all 45) and CAL-seam
(all 5) render in full, with B-cyc's six criterion-3 exclusions rendering as
ordinary `(EXCLUDED)` rows carrying data. That is **89** runs, with zero
`RENDER FAILED` rows among them.

**DEVIATION from P3's style, recorded rather than done silently.** P3 §3
embedded the whole 320-line rendering and documented the formatter's whitespace
transformation. This document does not embed it, for one reason: **no number in
this document comes from `report.py`.** Every figure below comes from
`duel_verdict.py`, `cal_report.py`, `sweep_verdict.py`, or a named manifest
walk, and each of those is embedded verbatim. Embedding 627 further lines that
feed nothing would add bulk, not checkability. The one `report.py` output this
document does need — the registered CAL-seam trap — is embedded in 5.5.

### 0.4 Three counts get confused, so each is named separately

For each duel arm, the pool the verdict is computed from, and what the tool
dropped to get there:

| count                                      | A static               | B-cyc static           | A closed-loop          | B-cyc closed-loop      |
| ------------------------------------------ | ---------------------- | ---------------------- | ---------------------- | ---------------------- |
| **duel-admissible pool** (what is scored)  | **10** `run-016`…`025` | **10** `run-002`…`011` | **10** `run-026`…`035` | **10** `run-012`…`021` |
| dropped: `duel_admissible: false`          | 4                      | 0                      | 1                      | 1                      |
| dropped: `duel_id` belongs to another duel | 10                     | 0                      | 0                      | 0                      |
| excluded                                   | 0                      | 0                      | 0                      | 0                      |

The pool is the first row and nothing else, and it is the Task 12/13 pairs **by
construction**, not by filtering: no flag was passed. `duel_verdict.py` drops
excluded runs on one counter and everything outside this duel's design on
another, and the `duel_id` partition registered in the spec's 1d is what keeps
P3's own ten cell-A static runs (`A/run-003`…`run-012`, `duel_id: ""`) out of a
P4 verdict.

**The tool prints 14, not 4 + 10.** `_walk_cell_runs`' own docstring registers
that a run dropped by the `duel_id` filter is counted on the **same**
`n_inadmissible` counter as a `duel_admissible: false` run, because both are
"valid data outside this duel's design". The split above is therefore not
readable from the notes column, and is reproduced by the census in section 10,
command 3:

```text
A static: {'not-admissible': 4, 'wrong-duel_id': 10, 'pooled': 10}
  pooled: run-016..run-025 (n=10)
   drop ('run-001', 'duel_admissible=false', '')
   drop ('run-003'..'run-012', 'duel_id', '')      <- P3's own A static pool
   drop ('run-013'..'run-015', 'duel_admissible=false', '')
A closed-loop: {'not-admissible': 1, 'pooled': 10}    drop run-002 (bring-up)
B-cyc static: {'pooled': 10}
B-cyc closed-loop: {'not-admissible': 1, 'pooled': 10} drop run-001 (Task 11 smoke)
```

That is the positive evidence that the pool partition worked on live data: the
ten P3 runs were held out, and no filed manifest was rewritten to achieve it.

## 1. The headline

**Under a shared RMW, three of P3's four static separations disappear into
`parity`, and the fourth reverses direction.**

- On the **static** arm, `one_hop_wall_ms`, `lidar_to_ndt_sim_ms` and
  `achieved_rate_ratio` all return **`parity`** against A-vs-B-cyc, where
  A-vs-B returned a separation outside the margin on every one of them. Per the
  spec's pre-registered per-metric rule, the P3 separation on those three
  metrics is **attributed to the as-shipped Fast-DDS configuration**, not to the
  approach.
- The fourth, `carla_process_cpu_pct`, separates beyond its margin — so by the
  same rule it is **approach-bound under a shared transport family** — but it
  now separates **in cell B-cyc's favour** (Δ = A − B-cyc = **+52.0 pp**, CI
  [49.6, 52.9], margin 10), where P3's A-vs-B row was **−12.9 pp** in cell A's
  favour. The rule attributes the P4 separation; it does not license
  retro-attributing P3's, which did not reproduce under a shared RMW at all.
  **The cause of the reversal is NOT established and no decomposition is
  attempted.**

**The campaign now has a closed-loop equivalence verdict, and it is the first
one it has ever had.** All five pre-registered metrics compute at n = 10/10:
four return `parity` and `carla_process_cpu_pct` returns `b_better` at Δ = +58.3
pp. P3 filed no closed-loop verdict because cell B armed on 0 of 15 runs; the
pre-declared failure branch for B-cyc **did not fire**, and the defect's own
instrument reports the map-delivery blocker absent under CycloneDDS.

**`control_staleness_ms` — the fifth metric, UNAVAILABLE for the whole of P3 —
is measured for the first time**, and only on the closed-loop arm: Δ = −0.789
ms, CI [−1.443, −0.288], margin 10, **`parity`**. On the static arm it is
`insufficient-data` at n = 0/8 for a cell-A-specific, arm-specific reason set
out in 2.4.

**Branch (c) closes on its first disjunct.** B-cyc's static `ndt_rate_ratio` is
≥ 0.9989 on all ten runs, so cell B's P3 depressed NDT rate is **bound to the
Fast-DDS configuration**.

**C1(a) is measured for the first time**, and is reported as an **upper bound**
under the rule pre-registered before the runs existed: the paired seam − in-core
one-hop p50 delta is **+0.278 ms** (median of five runs, range +0.239 … +0.299
ms, 5/5 positive).

**The M4 ceiling was not located.** No disjunct fired at `vlp16` on either cell,
so both stepped up mechanically to `32ch`, where again no disjunct fired on
either cell. The registered wording is **"ceiling not located up to the 32ch
class"** — a statement about where the search stopped, not a new step-up.
`128ch` stays struck on either branch.

Every one of these statements carries its confounds, and section 7 is not
optional reading. The single most important one, stated here so it cannot be
missed: **cell B-cyc runs the same `universe-devel-cuda` image as cell B by
deliberate design, and cell A runs `universe-devel`. The image confound sits
under every B-side number in this document.**

## 2. The attribution bracket

The spec's claim table registered this reading before any P4 run
(`2026-08-03-p4-transport-sweep-design.md`, "What P4 answers"), verbatim:

> Per metric, with the **frozen** margins: `parity` under the existing
> equivalence rule ⇒ the P3 separation on that metric is attributed to the
> as-shipped Fast-DDS configuration; separation beyond the margin ⇒
> approach-bound under a shared transport family. Reported per metric; **no
> composite**.

The bracket is P3's A-vs-B verdict (cell B on `rmw_fastrtps_cpp` + `udp_only.xml`,
SHM off) beside P4's A-vs-B-cyc verdict (both cells on `rmw_cyclonedds_cpp`, SHM
off). It is rmw-matched. It is **not** profile-matched — see 7.1 row P4-2.

### 2.1 The single invocation, and its complete output

```bash
PYTHONPATH=. python3 benchmarks/scripts/duel_verdict.py A B-cyc > /tmp/p4-duel-verdict.md
```

Exit status 0. No flags: `--results` defaults to `benchmarks/results`,
`--margins` to `benchmarks/config/margins.yaml`, `--min-n` to the pre-registered 10. **No filtering flag is needed or was passed** — the pool falls out of the
tool's own contract (0.4).

**DEVIATION from the brief's literal text, recorded:** `>` redirection instead
of `| tee`, to the brief's own path. An `rtk` proxy compresses piped output on
this host and the verdict is filed as byte-exact evidence. This is the same
capture-level deviation PROVENANCE §20.2 records for `duel.sh`, taken for the
same reason; it cannot affect what the tool computed. `md5sum` of the captured
file: `f59d33f279b30e5374408b84322c7e25`, 4351 bytes.

Reproduced below in a fenced block rather than as a re-typed markdown table, so
that no formatter transformation stands between the tool's output and the
record. (P3 §4.1 embedded its output as a markdown table and had to document and
check the padding the repository's `prettier` hook applied. A code fence removes
the need for that check entirely.)

Metric definitions: `benchmarks/README.md`, "Primary-duel metric definitions".

```text
Metric definitions: benchmarks/README.md, "Primary-duel metric definitions".

| metric | arm | n (a/b) | delta_median | 95% ci | margin | verdict | notes |
|---|---|---|---|---|---|---|---|
| one_hop_wall_ms | static | 10/10 | 1.687 | [1.441, 1.849] | 2 | parity | 14 run(s) not duel-admissible in A; fit_residual_ns median: a=1766839 b=3765121 |
| lidar_to_ndt_sim_ms | static | 10/10 | 1.356 | [1.287, 1.553] | 5 | parity | 14 run(s) not duel-admissible in A |
| control_staleness_ms | static | 0/8 | - | - | 10 | insufficient-data | 14 run(s) not duel-admissible in A; UNDER-N: a has 0 run(s) (< 10); UNDER-N: b has 8 run(s) (< 10); insufficient data for a bootstrap CI (need >= 3 per side; got a=0, b=8); run-016: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/A/run-016/published_time.csv; run-017: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/A/run-017/published_time.csv; run-018: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/A/run-018/published_time.csv; run-019: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/A/run-019/published_time.csv; run-020: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/A/run-020/published_time.csv; run-021: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/A/run-021/published_time.csv; run-022: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/A/run-022/published_time.csv; run-023: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/A/run-023/published_time.csv; run-024: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/A/run-024/published_time.csv; run-025: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/A/run-025/published_time.csv; run-002: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/B-cyc/run-002/published_time.csv; run-003: FAILED MetricUnavailableError: /control/command/control_cmd/debug/published_time not in benchmarks/results/B-cyc/run-003/published_time.csv |
| carla_process_cpu_pct | static | 10/10 | 52.005 | [49.617, 52.871] | 10 | b_better | 14 run(s) not duel-admissible in A |
| achieved_rate_ratio | static | 10/10 | 0.001 | [0.001, 0.001] | 0.02 | parity | 14 run(s) not duel-admissible in A |
| one_hop_wall_ms | closed-loop | 10/10 | 1.345 | [0.886, 1.942] | 2 | parity | 1 run(s) not duel-admissible in A; 1 run(s) not duel-admissible in B; fit_residual_ns median: a=3580255 b=54602283 |
| lidar_to_ndt_sim_ms | closed-loop | 10/10 | 2.167 | [1.882, 2.553] | 5 | parity | 1 run(s) not duel-admissible in A; 1 run(s) not duel-admissible in B |
| control_staleness_ms | closed-loop | 10/10 | -0.789 | [-1.443, -0.288] | 10 | parity | 1 run(s) not duel-admissible in A; 1 run(s) not duel-admissible in B |
| carla_process_cpu_pct | closed-loop | 10/10 | 58.250 | [57.662, 59.161] | 10 | b_better | 1 run(s) not duel-admissible in A; 1 run(s) not duel-admissible in B |
| achieved_rate_ratio | closed-loop | 10/10 | 0.000 | [-0.000, 0.000] | 0.02 | parity | 1 run(s) not duel-admissible in A; 1 run(s) not duel-admissible in B |

M2 three-way reconciliation (cadence.reconcile_drops over publisher_counts.json), per cell alongside the achieved_rate_ratio duel row above (README.md, "achieved_rate_ratio"):

| cell | arm | n measurable | n not measurable | n zero-published | n observer | publisher_drop_rate (median) | publisher_drop_rate (max) | observer_loss_rate (median) | observer_loss_rate (max) | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| A | static | 10 | 0 | 0 | 10 | 0.001 | 0.001 | 0.000 | 0.000 | 14 run(s) not duel-admissible |
| B-cyc | static | 10 | 0 | 0 | 10 | 0.000 | 0.002 | 0.000 | 0.000 |  |
| A | closed-loop | 10 | 0 | 0 | 10 | 0.000 | 0.000 | 0.000 | 0.000 | 1 run(s) not duel-admissible |
| B-cyc | closed-loop | 10 | 0 | 0 | 10 | 0.000 | 0.000 | 0.000 | 0.000 | 1 run(s) not duel-admissible |
```

### 2.2 Direction convention, restated because one metric's label inverts

`benchmarks/config/margins.yaml`'s own header registers `delta = extension -
tier4-native; lower is better`, and `analysis/stats.py`'s `equivalence_decision`
encodes exactly that: `a_better` when the whole CI sits below zero, `b_better`
when it sits above.

On `achieved_rate_ratio` that uniform convention **inverts**, exactly as P3 §4.2
records: the metric is each cell's achieved rate normalised against **its own**
registered `lidar_expected_hz` (20.0 on A, 10.0 on B-cyc), and
`benchmarks/README.md:575-594` registers it as a **shortfall detector**, so
higher is better on that metric and that metric alone. It matters less here than
in P3 — the P4 row is `parity`, not a separation — but the sign is still read
under the inverted rule: Δ = +0.001 means cell A falls 0.001 of its own target
_less_ short than B-cyc does, which is 1/20 of the margin.

### 2.3 The bracket, per metric

| metric                  | P3: A-vs-B (Fast-DDS + `udp_only.xml`)           | P4: A-vs-B-cyc (both CycloneDDS)                 | pre-registered reading, applied                                                                                         |
| ----------------------- | ------------------------------------------------ | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `one_hop_wall_ms`       | −6.281 ms, [−6.542, −5.828], `a_better`          | **+1.687 ms**, [1.441, 1.849], **`parity`**      | **parity ⇒ the P3 separation is attributed to the as-shipped Fast-DDS configuration.**                                  |
| `lidar_to_ndt_sim_ms`   | −5.817 ms, [−8.106, −4.976], `a_better`          | **+1.356 ms**, [1.287, 1.553], **`parity`**      | **parity ⇒ attributed to the as-shipped Fast-DDS configuration.**                                                       |
| `control_staleness_ms`  | UNAVAILABLE (binding never registered)           | `insufficient-data`, n = 0/8                     | no bracket on this arm; see 2.4. The metric IS bracketed closed-loop — see 3.4.                                         |
| `carla_process_cpu_pct` | −12.873 pp, [−16.698, −11.129], `a_better`       | **+52.005 pp**, [49.617, 52.871], **`b_better`** | **separation beyond margin ⇒ approach-bound under a shared transport family — but in the OPPOSITE direction.** See 2.5. |
| `achieved_rate_ratio`   | +0.104, [+0.090, +0.114], `b_better` (favours A) | **+0.001**, [0.001, 0.001], **`parity`**         | **parity ⇒ attributed to the as-shipped Fast-DDS configuration.**                                                       |

**Three of the four computable P3 separations were transport-bound.** That is
the phase's principal result, and it is precisely the question P3 §4.2 declined
to answer and PROVENANCE §10.1 registered as open: "this campaign does not hold
the measurement that would separate 'the extension is faster' from 'cell B's
transport is losing samples, and every message-derived metric sees it'." P4 holds
it. The answer, on three of the four rows, is the second reading.

**The M2 reconciliation corroborates it on a different quantity, and this is the
cleanest single line of evidence in the phase.** P3's cell B lost frames
observer-side — `observer_loss_rate` median **0.085**, max **0.108** — against
cell A's 0.000/0.000. Cell B-cyc, the same image and the same launcher with only
the middleware changed, reads **0.000 / 0.000** on both arms. The loss that
three of P3's four rows were three views of is gone with the transport.

**One row of the M2 table must NOT be read as a transport result.**
`publisher_drop_rate` fell from P3's ~0.020–0.021 medians to 0.000–0.001 here,
**on both cells**. That is the spec's 1f instrument fix (`3b9212e`, "stop the
observer before the GT collector on teardown", pinned by `fd2c125`), which
removed the teardown-ordering artefact P3 §7.3 and PROVENANCE §1 disclosed and
declined to fix mid-campaign. It is a harness change applied symmetrically to
both cells and it says nothing about either transport. P3's pools were
deliberately not re-scored.

### 2.4 `control_staleness_ms` on the static arm: what the row actually says

**It is not "UNAVAILABLE: not registered".** That was P3's row and it is the
wrong description of P4's. The mechanism is traced end-to-end in PROVENANCE
§16.2 and was reproduced offline before this wrap ran:

1. `_bind_control_staleness_ms` (`duel_verdict.py:769-772`) binds on
   **registration**, never on measured rows. The spec's 1c registered
   `control_published_time_topic` for cell A, so the bind **succeeds for both
   cells**.
2. `build_verdict_table`'s unbound early-out (`:1268`,
   `if extractor_a is None or extractor_b is None:`) is therefore **not
   taken** — the row does **not** drop.
3. Execution reaches the per-run extractor, which raises
   `MetricUnavailableError` on each cell-A static run because
   `published_time.csv` is header-only. `_apply_extractor` catches and records
   it: no exception escapes, no NaN is fabricated, no run is silently skipped.
4. The row is **emitted** as `n (a/b) = 0/8`, no delta, no CI, verdict
   `insufficient-data`, carrying **twelve** `MetricUnavailableError` lines in
   its notes — ten for cell A, two for B-cyc.

**The asymmetry is cell-A-specific and arm-specific.** Cell A's control
publisher advertises and stays silent while unengaged: 24/24 across every filed
cell-A **static** run (PROVENANCE §18.5, §20.7). The tier4 gate emits at ~1–2 Hz
on the same arm. **The cause is not established.** An
image/stack-configuration hypothesis exists and is untested.

**What IS established is why any `control_cmd` exists on a static arm at all**,
and it matters for reading the two B-cyc zeros: in the static arm `control_cmd`
is not produced by a control loop. It is emitted only while `vehicle_cmd_gate`
is in its emergency-publishing state, driven by `mrm_handler` cycling
EMERGENCY_STOP operate/cancel (PROVENANCE §19.4, established from the filed
logs). `B-cyc/run-002` and `run-003` recorded zero rows because that cycle ran
exactly once each, **before the scoring window opened** (−7.40 s and −7.30 s) —
not because a rate was low. Neither is excludable and neither was excluded;
`exclusions.md` criterion 2's `gate:control_cmd-silent` is engage-predicated and
structurally unreachable in the static arm.

### 2.5 The `carla_process_cpu_pct` reversal, stated rather than explained away

The pre-registered rule is applied as written: the separation exceeds the
margin, so the row is **approach-bound under a shared transport family**. Three
things must be said with it, and none of them is optional.

**(a) It is the same measurand on both cells, and that was checked.**
`extract_carla_process_cpu_pct` takes the median `cpu_pct` from `resources.csv`
for the cell's registered `cpu_process_label`, over the scoring window in wall
time. Both cells register `cpu_process_label: carla-server`, and both
`config/processes/A.yaml` and `config/processes/B-cyc.yaml` resolve that label
to their own fork tree's `UnrealEditor -game` process by uproject path. It is
the simulator process's own CPU on each side, sampled from `resources.csv` and
not derived from the message stream — which is why P3 §4.2 called it the least
entangled of its four rows.

**(b) The direction reverses, so P3's row cannot be re-read as an approach
property.** P3 measured A **12.9 pp below** B. P4 measures A **52.0 pp above**
B-cyc on the static arm and **58.3 pp above** on the closed-loop arm — a swing
of roughly 65 pp with only the middleware changed on the tier4 side. The rule
says the P4 separation is approach-bound under a shared RMW. It does **not** say
P3's was, and the two cannot both be an approach difference. What the bracket
establishes is that the P3 CPU row's **direction did not survive the transport
control**; what it does not establish is why.

**(c) A registered confound runs against cell A on this metric, and it did in P3
too.** Cell A's `lidar_expected_hz` is **20.0**; B-cyc's is **10.0**
(`cells.yaml`, reproduced by command 7 in section 10). Cell A's simulator
raycasts and publishes its top LiDAR at twice the rate, and `README:3986-4008`
separately registers that cell A ships **2.118×** the bytes for the same point
count. Both push cell A's simulator CPU up for reasons that are registered cell
properties rather than approach efficiency. This confound was present in P3
unchanged — where cell A won the row anyway — so it does not explain the
reversal on its own. It is recorded because the registration requires it either
way, and because it bounds how the P4 row may be read: **the +52 pp is not a
like-for-like sensor load.**

**No decomposition is attempted and none may be read in.** The instrument that
would settle this is a rate-matched CPU comparison, which this campaign does not
hold and which is out of P4's registered scope. It is named in 11.2 as a
standing question.

### 2.6 What the bracket does NOT say

- **It is not a claim that the approaches are equivalent.** Three static rows
  and four closed-loop rows return `parity` under the **frozen** margins; one
  row on each arm does not. `parity` is a TOST decision against a
  pre-registered margin, not a proof of identity: it says the whole 95% CI falls
  inside (−margin, +margin), and on `one_hop_wall_ms` the CI is [1.441, 1.849]
  against a 2.0 ms margin — inside, but not far inside.
- **It is not corrected for the byte-layout asymmetry, and that asymmetry runs
  against cell A on the two latency metrics.** `README:3986-4008` registers
  `one_hop_wall_ms` and `lidar_to_ndt_sim_ms` as byte-sensitive with cell A
  carrying 2.118× the payload. In P3 that made an A-favourable latency result
  conservative. Here the rows are `parity` with Δ slightly positive (cell A
  slower by 1.7 ms and 1.4 ms), so the asymmetry works the other way: correcting
  for it could only move those deltas toward or past zero. **Scoped to what that
  supports: the correction cannot overturn parity toward a B-cyc-favouring
  separation.** It is not an unbounded safety claim, and it must not be read as
  one: Δ = +1.687 ms sits 3.687 ms above the −2.0 ms boundary, so a byte
  correction larger than that would produce `a_better` — parity overturned in
  the _other_ direction. **No bound on the correction's magnitude is offered
  anywhere in this document, and none is measured here**; `README:3986-4008`
  registers the byte ratio, not a latency coefficient, and deriving one from a
  ratio would be exactly the kind of claim outrunning its measurement this
  record keeps catching. What the asymmetry rules out is a B-cyc-favouring
  reading of these two rows; what it does not rule out is an A-favouring one.
- **It does not replace a P4↔P3 identity caveat.** The harness sha and the
  engine BuildId both moved between P3 and P4 (section 9). The bracket compares
  two verdicts each computed within its own phase, which is the design; it does
  not compare a P3 per-cell absolute against a P4 one, and nothing here licenses
  that.
- **It is not a per-approach ranking of the three approaches.** The E family and
  cell C are not in this duel. No cross-approach equivalence statistic was
  computed and none may be inferred.
- **`one_hop_wall_ms` must be read next to its clock-fit residual**, which
  `benchmarks/README.md:624` registers as a required companion reading. Both
  rows print it, and it is asymmetric:

  | pool              | max-abs sim→wall fit residual, per run (ms)             | median    |
  | ----------------- | ------------------------------------------------------- | --------- |
  | A static          | 2.0 1.7 2.5 2.1 1.5 1.7 2.0 1.6 1.8 1.7                 | **1.77**  |
  | B-cyc static      | 1.3 5.8 **65.4 58.9** 1.3 1.1 **70.4** 24.9 1.0 1.7     | **3.77**  |
  | A closed-loop     | 3.1 2.3 3.0 4.4 2.8 2.4 4.1 4.1 4.8 5.2                 | **3.58**  |
  | B-cyc closed-loop | **78.5 79.2 71.8 77.4** 23.7 **64.4** 44.8 1.7 44.8 1.8 | **54.60** |

  `one_hop_wall_ms` is computed through this fit, and the margin is 2.0 ms.
  These are **maxima over a run**, not typical errors — the metric takes a p50
  over ~1400 samples, so a localised excursion moves few of them — but the
  B-cyc closed-loop pool's median max-residual is 54.6 ms, 27× the margin, and
  **eight of its ten runs exceed 20 ms** (seven exceed 40 ms). **The
  `one_hop_wall_ms` parity rows are the weakest of the parity rows in this
  document**, the closed-loop one more so than the static one, and a reader who
  needs that row to bear weight should treat it as such. Cell A's fit is tighter
  on both arms, but by very different factors: **2.1× on the static arm** (1.77
  against 3.77) and **15× on the closed-loop arm** (3.58 against 54.60). Only
  the closed-loop gap is an order of magnitude; the static one is not, and the
  static `one_hop_wall_ms` row is correspondingly better supported than the
  closed-loop one. Reproduce with command 6.

## 3. The closed-loop verdict — the campaign's first

### 3.1 Why it exists: the pre-declared failure branch did not fire

The spec pre-registered, before any data:

> if B-cyc fails to arm, the latched-delivery defect is not Fast-DDS-specific —
> collection STOPS, the finding is recorded (it answers the attribution question
> in the other direction), the transport phase downgrades to static-only, and
> the sweep's B-cyc column downgrades to A-only.

**B-cyc armed and drove.** The branch did not fire, so what follows is the
closed-loop verdict, not the failure-branch record. Collection took **one**
`duel.sh` invocation — no abort, no resume, no make-up pairs, zero exclusions,
and both closed-loop integrity checks 20/20 (engage recorded in `arm.log`,
`goal_closest_approach_m` non-null) (PROVENANCE §20.2, §20.3).

### 3.2 The decisive evidence is the instrument, not the drive

The arm outcome is n-limited and weak on its own. The defect's **own probe** is
the strong evidence, because it is the same probe on both sides of the
transport, on a byte-identical payload. Every run that carries
`vector-map-delivery.json` (command 4 in section 10):

| cell / run            | transport                           | `data_bytes` | `pre_republish_delivered` | attempts | `verify_wait_s`          | `exit_code`                 |
| --------------------- | ----------------------------------- | ------------ | ------------------------- | -------- | ------------------------ | --------------------------- |
| `B/run-031`           | `rmw_fastrtps_cpp` + `udp_only.xml` | 1 305 281    | **false**                 | **3**    | 60.048 / 60.022 / 60.027 | **5** (`EXIT_NOT_VERIFIED`) |
| `B/run-032`           | `rmw_fastrtps_cpp` + `udp_only.xml` | 1 305 281    | **true**                  | 1        | **0.007**                | 0                           |
| `B/run-033`           | `rmw_cyclonedds_cpp`, no profile    | 1 305 281    | true                      | 1        | 0.025                    | 0                           |
| `B-cyc/run-001`       | `rmw_cyclonedds_cpp`, no profile    | 1 305 281    | true                      | 1        | 0.027                    | 0                           |
| `B-cyc/run-012`…`021` | `rmw_cyclonedds_cpp`, no profile    | 1 305 281    | **true**, 10/10           | 1 each   | 0.006 … 0.008            | 0                           |

Under CycloneDDS the latched map was **already delivered before any re-publish
was attempted, on 11 of 11 runs**, and verification closed in **6–27 ms**. Under
Fast-DDS on `run-031` the endpoint never received it across **three minutes** of
re-publishing. The per-topic re-publish workaround PROVENANCE §9.2 records as
not scaling was not needed once.

**A CORRECTION to how PROVENANCE §14.4's two-row table has been read.** That
table set `B/run-031` (false) against `B-cyc/run-001` (true) and is accurate as
far as it goes, but the census above shows a third Fast-DDS run with the probe:
**`B/run-032` reads `pre_republish_delivered: true`** on the same transport, and
**still failed to arm** (`excluded: true`, `gate:arm-failed`). Two consequences,
recorded rather than smoothed over:

- The map leg's delivery is **nondeterministic under Fast-DDS**, 1 false of 2 —
  which is exactly what P3 §5.1 says the defect is ("per-topic and
  nondeterministic"), and it means the Fast-DDS side of this comparison is n = 2,
  not a rate.
- **The map leg is not the whole blocker.** `run-032` got its map — in **7 ms**,
  which is exactly the median of the eleven Cyclone `verify_wait_s` readings
  (0.006 … 0.027, median 0.007) — and still did not arm. That 7 ms is the
  sharpest form of this correction: on the one Fast-DDS run that delivered, the
  map leg was not merely adequate but indistinguishable from the transport this
  comparison prefers, and the run failed anyway. §14.4 already scoped its claim
  to the map leg only ("the route and
  `operation_mode` legs have no equivalent artefact"); this is the positive
  evidence for that scoping, and it is why the closed-loop result rests on the
  twenty filed runs rather than on this probe alone.

**So: the P3 §5.1 latched-delivery defect is transport-dependent on the map
leg**, with the Fast-DDS side measured at n = 2 and the Cyclone side at n = 11.
Nothing here shows _why_, and nothing here shows Fast-DDS is at fault rather
than the interaction of the fork's SHM-only locators, the `udp_only.xml`
workaround they force, and this host's loopback. §14.4's attribution boundary
applies unchanged.

### 3.3 The verdict

Read off 2.1's closed-loop rows. **All five metrics compute at n = 10/10** —
which P3 could not do for any of them.

| metric                  | Δ median (A − B-cyc) | 95% CI           | margin | verdict    | reading                                                         |
| ----------------------- | -------------------- | ---------------- | ------ | ---------- | --------------------------------------------------------------- |
| `one_hop_wall_ms`       | +1.345 ms            | [0.886, 1.942]   | 2.0    | **parity** | inside the margin; read next to the fit residual (2.6)          |
| `lidar_to_ndt_sim_ms`   | +2.167 ms            | [1.882, 2.553]   | 5.0    | **parity** | inside the margin                                               |
| `control_staleness_ms`  | −0.789 ms            | [−1.443, −0.288] | 10.0   | **parity** | **the metric P3 never had** — see 3.4                           |
| `carla_process_cpu_pct` | +58.250 pp           | [57.662, 59.161] | 10.0   | `b_better` | separation; same reversal and same confounds as 2.5             |
| `achieved_rate_ratio`   | +0.000               | [−0.000, 0.000]  | 0.02   | **parity** | higher-is-better polarity (2.2); the delta is 0 to three places |

M2 on this arm: `publisher_drop_rate` and `observer_loss_rate` are **0.000
median and 0.000 max on both cells**, 10/10 measurable each.

**This is explicitly an A-vs-B-cyc verdict.** The A-vs-**B** closed-loop verdict
under cell B's own registered transport remains **non-computable** and is
reported as such: cell B armed on 0 of 15 closed-loop runs, all 15 excluded (P3
§5.1). P4 does not manufacture one, and B's P3 record is untouched.

### 3.4 `control_staleness_ms`: a metric P3 never had

P3 §1 reports the fifth margin metric as "UNAVAILABLE for the whole duel". P4
measures it. The open item Q1 was settled by the collection itself (PROVENANCE
§20.5): cell A's closed-loop arm populates `published_time.csv` on **10 of 10**
runs (2963–2969 rows), every row keyed to
`/control/command/control_cmd/debug/published_time`, at a ratio of **1.000**
against each run's own `control_cmd` count in `observer.csv` (six exact, four
short by a single row). The registration did not need re-scoping: the asymmetry
identified in §15.1 is an **arm** property of cell A, not a cell property.

So the row is a real measurement on both sides at n = 10/10, and it returns
`parity` at Δ = −0.789 ms against a 10.0 ms margin — the tightest parity margin
ratio in the table.

### 3.5 One confound this arm does NOT retire

PROVENANCE §21.1 falsified §20.6's claim that the static-arm control-silence
precondition "cannot arise" closed-loop. It arises: every closed-loop run has a
+6.02 … +6.11 s pre-arm window in which nothing is engaged, so `control_cmd` can
only come from `mrm_handler`'s emergency cycling — §19.4's exact mechanism. In
**1 of 10** B-cyc closed-loop runs (`run-013`) that stream was silent for the
entire pre-arm window, against **2 of 10** on the static arm. **The condition
recurred at a comparable rate; the controller merely masks it within ~2 s once
it starts publishing.** Therefore:

- On the **closed-loop** arm it costs no sample and there is no measured
  arm-cost to report.
- On the **static** arm nothing masks it, and it **remains a live confound for
  the static pool** — it is one of the two candidate readings of B-cyc's 2-of-10
  zero-control-traffic runs (2.4).

What would settle it is capturing `/system/operation_mode/availability` and the
diagnostic-graph output across the pre-arm window; both are outside the frozen
five-topic observer set, and `B-cyc/run-013` is the filed precedent that
re-targets that experiment to the pre-arm interval rather than the scored
window.

## 4. Branch (c): B-cyc's `ndt_rate_ratio` pool

P3 §5.2 left cell B's depressed NDT rate **UNEXPLAINED**: Phase 0 eliminated
double publication as the cause by pre-declared elimination and identified none,
and the M5 rate gate failed on eight of the ten cell-B duel runs (0.2569–0.8505).

The spec's claim table pre-registered both readings, verbatim:

> Ratio ≥ 0.9 across the pool ⇒ the depression is bound to the Fast-DDS
> configuration; still depressed ⇒ transport-independent, cause stays open (and
> is itself a finding). n = 1 `B/run-033` is superseded either way.

**The first disjunct fires.** B-cyc's ten static duel runs (PROVENANCE §18.4,
reproduce with command 5):

| run             | `ndt_rate_ratio`   | `gate_pass` | `reasons` |
| --------------- | ------------------ | ----------- | --------- |
| `B-cyc/run-002` | 0.9989550530354242 | true        | `[]`      |
| `B-cyc/run-003` | 0.9989594023880347 | true        | `[]`      |
| `B-cyc/run-004` | 0.9989679933693522 | true        | `[]`      |
| `B-cyc/run-005` | 0.9999999850840338 | true        | `[]`      |
| `B-cyc/run-006` | 0.9989679933693522 | true        | `[]`      |
| `B-cyc/run-007` | 0.9989506671719838 | true        | `[]`      |
| `B-cyc/run-008` | 0.9989550530354242 | true        | `[]`      |
| `B-cyc/run-009` | 0.9989701190060682 | true        | `[]`      |
| `B-cyc/run-010` | 0.9989679933693522 | true        | `[]`      |
| `B-cyc/run-011` | 0.9989506671719838 | true        | `[]`      |

n = 10, minimum 0.998951, maximum 1.000000 — **all ten ≥ 0.9, the smallest by a
margin of 0.0989.** The M5 gate's 0.9 threshold was never touched, on any cell,
at any point in P3 or P4.

**BRANCH-(c) DISPOSITION: cell B's P3 depressed NDT rate is bound to the
as-shipped Fast-DDS configuration.** The n = 1 `B/run-033` probe is superseded
by this n = 10 pool, as the claim table says it is either way.

**Scope it exactly.** This is a fact about **cell B-cyc's own** rate under the
row-11 Cyclone transport, plus the pre-registered mapping from that fact to a
disposition. It is not a mechanism: nothing here identifies _what_ about the
Fast-DDS configuration depresses the rate, and P3's Phase 0 finding that the
double-publication differential is real but not the cause stands unchanged
(PROVENANCE §6.7, §6.8, and the §6.8 limitation that (c) was reached by
elimination). "Bound to the configuration" names where the cause lives, not what
it is.

## 5. C1(a): the CAL-seam seam-vs-in-core measurement

C1(a) — the cost of the extension's C-ABI seam — had **zero evidence** for the
whole of P3: cell CAL-seam was struck by the owner's 2026-07-30 scope cut, and
`benchmarks/README.md`'s confound entry recorded seam overhead as UNMEASURED.
The owner's 2026-08-03 D8 lift revived the cell for one registered relink round.
It has now been measured, on five static runs, none excluded.

```bash
for r in 001 002 003 004 005; do
  PYTHONPATH=. python3 -m benchmarks.scripts.cal_report benchmarks/results/CAL-seam/run-$r
done
```

`cal_report.py` is the correct tool here and `report.py` is not: `cal_report`
takes the **direct wall difference** `arrival_system_ns - header_stamp_ns`,
which is right because both bench publishers stamp `header.stamp` with wall
`now()` on the same host as the observer. `report.py` applies
`fit_sim_wall_affine` to those same wall stamps, which is the registered trap
(5.5).

### 5.1 The C1(a) table

Rendered values are `cal_report`'s own output; the delta column is computed from
the same function's unrounded return (command 9).

| run     | seam p50 (ms) | in-core p50 (ms) | **Δ p50 (seam − in-core)** | Δ p95   | Δ p99   | n seam / in-core | `carla-server` cpu_pct mean |
| ------- | ------------- | ---------------- | -------------------------- | ------- | ------- | ---------------- | --------------------------- |
| run-001 | 0.7242        | 0.4458           | **+0.2784**                | +0.1184 | −0.0447 | 508 / 506        | 249.70                      |
| run-002 | 0.7464        | 0.4593           | **+0.2871**                | +0.2268 | +0.1420 | 502 / 499        | 250.62                      |
| run-003 | 0.7447        | 0.4460           | **+0.2988**                | +0.2558 | +0.2234 | 507 / 506        | 252.09                      |
| run-004 | 0.7316        | 0.4924           | **+0.2392**                | −0.0634 | −0.1297 | 501 / 496        | 252.67                      |
| run-005 | 0.7634        | 0.4987           | **+0.2647**                | −0.0509 | −0.1824 | 505 / 497        | 252.17                      |

**Δ p50: median +0.2784 ms, range +0.2392 … +0.2988 ms, positive in 5 of 5
runs.** Mean +0.2736 ms.

**The tails do not separate and that is stated, not hidden.** Δ p95 median
+0.118 ms and Δ p99 median **−0.045 ms**, with the p99 delta **negative in 3 of
5 runs** — i.e. the seam's own tail is sometimes shorter than the in-core twin's.
The seam cost is a consistent shift in the **median**; it is not resolvable in
the tails at n = 5, and no tail claim is made.

### 5.2 The pre-registered upper-bound rule, honoured

PROVENANCE §11.9, filed 2026-08-03 **before Task 10 collected a single run**:

> **If the measured seam cost lands on the order of a cache-warming effect,
> `C1(a)` is reported as an UPPER BOUND, not a point estimate.**
>
> It binds whatever the data says. It is not conditional on the result being
> inconvenient, and it may not be revisited after the runs are in — that would
> convert it back into the post-hoc judgement it exists to replace.

**C1(a) IS REPORTED AS AN UPPER BOUND: the seam costs at most ≈ 0.28 ms per
921 908-byte publish on this instrument.** Two independent grounds, either of
which is sufficient:

1. **The rule's own antecedent is a judgement about scale, and it may not be
   resolved after the data exists in the direction that weakens the rule.**
   0.278 ms is arguably above cache-warming scale. Deciding that _now_, having
   seen the number, is exactly the post-hoc move the rule exists to prevent, so
   the rule is applied rather than argued out of.
2. **PROVENANCE §13.2 independently requires it**, in terms addressed to this
   task: the residual in-core-only sample loss "is a **second reason** `C1(a)`
   must be read as an upper bound, and Task 16 should state it alongside the
   publish-order and serializer residuals rather than treat the pair as
   perfectly matched."

**A correction §11.9 itself carries, which makes the rule do MORE work, not
less.** §11.9's original direction argument — "seam-first means the seam pays
the cold-cache cost, so the bias is conservative" — was **corrected on
2026-08-03** and does not survive: CAL-seam boots through `run_e2e.sh`, so
roughly 921 KB of ego LiDAR crosses the same seam at 20 Hz in
`SensorManager.PostPhysTick` **before** `OnPostTick` drives either twin. The
seam is a late writer on a freshly-walked warm path, not the frame's first
writer. The paired delta **survives** (the burst is common-mode, landing ahead
of both publishes alike), but the **conservatism claim does not**: the residual
order effect between the two adjacent publishes is smaller than assumed and its
**sign is not established**. The pre-registered rule is unchanged and now stands
on its own rather than on that argument. Authoritative derivation:
`benchmarks/README.md:1563-1589`.

### 5.3 The residual set, complete

Everything the instrument controls is symmetric by construction. What is not:

| residual                         | status                                                                                                                                                                                                                                                                                                                                                                        | direction                                                                                                                                                                         |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **publish order**                | Unremovable: two publishes on one thread, seam first (`FCarlaEngine::OnPostTick` drives `ROS2ExtensionLoader->Tick()` before `BenchIncoreCloudOnTick()`). §11.9's largest residual.                                                                                                                                                                                           | **sign NOT established** (corrected 2026-08-03)                                                                                                                                   |
| **in-core-only sample loss**     | Real and one-directional: the in-core twin has anomalous publish gaps in **4 of 5** runs (200/250/300 ms), the seam twin in **0 of 5**; `seam Hz > in-core Hz` in **5 of 5**. Same-tick pairing 95.0–99.0 %.                                                                                                                                                                  | **against the seam measuring cheap** — a lost in-core sample removes that publish from the population, so the surviving in-core population is the one that kept up. Conservative. |
| **serializer implementation**    | Different code emits each side (`rosidl/fastrtps` vs the fork's `serialize_to_cdr`), but §11.8 closed the payload question: both emit **921 905** CDR bytes, 305 B overhead, the same `dds_type_name` and the same RIHS01 hash; on the wire all five runs read **921 908 B** on both topics with no other value appearing.                                                    | code difference only, not payload                                                                                                                                                 |
| **pair rate spread**             | **0.20 – 1.59 %** per run (§13.1 — the earlier "0.6 %" understated the worst case by 2.6×).                                                                                                                                                                                                                                                                                   | bounds how well the decimation cancels                                                                                                                                            |
| **drops vs skips not separable** | The in-core twin's two skip paths log to the editor's stderr, which on the `run_e2e.sh` launch path goes to a fixed `/tmp` file copied into no run directory. **These five runs cannot distinguish "the transport dropped it" from "the publisher skipped it."** Fixed for later cells (`EDITOR_LOG` + `teardown.sh`, pinned by three tests), not retrofitted onto this pool. | open, disclosed                                                                                                                                                                   |

**The registered `lidar_expected_hz: 10.0` is unachievable on this cell by
construction**, and both twins publish at ~8.0 Hz in all five runs (§12.5): the
seam publisher's 100 ms `steady_clock` gate is tested once per `ext_on_tick`
against a 20 Hz world whose two-tick span is 100.24 ms, so each publish lands on
the 2nd or 3rd tick and the achievable rate is quantised to 9.98 / 6.65 Hz, a
≈52/48 mixture. It is **common-mode** — both twins share `ext_on_tick`,
`kPeriod` and the phase-reset rule — so it costs sample count (~500 pairs per
topic per run, ample), not the delta. It is not an exclusion under any of
`exclusions.md`'s ten criteria, walked criterion by criterion in §12.5, and
`lidar_expected_hz` reaches no analysis for this cell because all three of its
binders guard jointly on `lidar_topic`, which is `null` for CAL-seam.

**A refutation that was itself refuted, kept in the record.** §12.5 argued the
~8 Hz was not observer-side loss because mean `header_stamp` Δ equals mean
`arrival_system` Δ to five significant figures. **§13.3 retracts that argument:
it has no discriminating power** — both means telescope over the same surviving
rows, so the identity holds whether or not anything was lost (verified: deleting
20 % of run-003's rows at random leaves the equality just as tight while the
mean interval moves 124 → 156 ms). What actually carries the seam-side
conclusion is the quantisation evidence: the seam twin's gaps are _only_ 100 or
150 ms across ~2 500 publishes, and transport loss would necessarily have
produced 200/250/300 ms gaps. For the **in-core** twin the loss hypothesis is
**not** refuted.

### 5.4 The CPU half of C1(a) cannot decompose, and must not be read as if it can

`cal_report.py`'s per-process table reports `carla-server` at a mean of
**249.70 – 252.67 %** across the five runs (median 252.09). **Both twins run
inside that one process.** The table therefore measures the cost of the pair
together and cannot attribute any share of it to the seam. It is filed as the
C1(a) table's registered second half and as run-condition context; it is **not**
a seam-cost measurement, and the ≈0.28 ms latency delta is the only quantity
C1(a) rests on.

### 5.5 The registered `report.py` trap, reproduced exactly as pre-registered

`cell_info` reports `has_sim_clock: true` for CAL-seam (`carla: 0.10-fork`), so
`run.sh` step 15 routes its runs to `report.summarize_run`, which applies
`analysis/clockfit.fit_sim_wall_affine` to the two bench publishers' **wall**
header stamps. The result is in every filed run's `report.md` and in the Step-1
regeneration:

```text
| run-001 | /bench/incore_cloud | 8.02 | 151.09 | -1790250414630.00 | -1790250414553.68 | 7.40 |
| run-001 | /bench/seam_cloud   | 8.05 | 151.11 | -1790250414630.24 | -1790250414553.39 | 7.43 |
```

Those one-hop columns are a sim epoch subtracted from a wall epoch. This is the
**registered** trap, written down before collection with its remedy
(`report.py:30-51`, `cal_report.py:59-85`, PROVENANCE §12.4): the measurement is
read from `cal_report.py`. The `hz`, `p95 ms` and `MB/s` columns above are
unaffected and correct. Nothing was special-cased to suppress the rendering —
both tools are used, for different purposes, exactly as registered.

**Neither topic's absolute `one_hop_p50_ms` from `report.py` may be quoted as a
latency, and neither may be compared against a sim-stamped cell's number.** The
C1(a) delta survives the fit because it is common-mode and cancels; the absolute
values do not.

**One number was published early, and it is not an anchor.** §12.4 stated
run-001's 0.72 / 0.45 ms pair, which §12's own preamble forbade, and §13.5
corrects the framing without deleting the number. That pair is **n = 1 of 5** and
carries no privileged status; C1(a) is the five-run pool above.

## 6. Amended M4: the sweep, and where the ceiling search stopped

M4's registered residue at the end of P3 was a ceiling confirmation at `vlp16`
plus the ablation decomposition. The spec registered the success criterion as:
**a fired ceiling disjunct at `vlp16`, OR the 32ch step-up executed with its own
verdict**, with a per-cell trigger ("a cell steps up iff none of its own vlp16
points fires") and `128ch` struck on either branch.

```bash
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py A     --class vlp16
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py A     --class 32ch
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py B-cyc --class vlp16
PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py B-cyc --class 32ch
```

### 6.1 The four ceiling tables

| cell  | class   | rows in table | scored | excluded | `reached: True` | reasons | skipped: out of arm | skipped: out of class | **disjunct fired** |
| ----- | ------- | ------------- | ------ | -------- | --------------- | ------- | ------------------- | --------------------- | ------------------ |
| A     | `vlp16` | 9             | 9      | 0        | **0**           | none    | 35                  | 9                     | **NO**             |
| A     | `32ch`  | 9             | 9      | 0        | **0**           | none    | 35                  | 9                     | **NO**             |
| B-cyc | `vlp16` | 9             | 9      | 0        | **0**           | none    | 21                  | 15                    | **NO**             |
| B-cyc | `32ch`  | 15            | 9      | **6**    | **0**           | none    | 21                  | 9                     | **NO**             |

Every scored row reads `reached False` with an empty `reasons` column and
`publisher_rate 1.000`. On the twelve measured rows per class nothing is
defaulted (`quality_ok True`, empty notes); on the ablation rows the notes carry
the two designed absences — "publisher rate not measurable (no
`publisher_counts.json`)" and "quality not applicable (ablation arm, no closed
loop)" — neither of which becomes a disjunct. No row carries a
`window_branch_note`.

**"Did not fire" is a real evaluation, not an unevaluable disjunct.**
`benchmarks/analysis/ceiling.py:84` raises when both `rtf` and `tick_rate_ratio`
are `None`, so an unscoreable row cannot render as a passing one. All rows
rendered, so all were scored against a real per-sample throughput series. The
booleans are also read from the **rendered table**, not from `rc`: PROVENANCE
§25.3 records that `sweep_verdict.main` returns 0 when every run is
class-dropped, so exit status alone cannot tell "passed" from "nothing scored".

### 6.2 The 32ch step-up executed mechanically, and one collection was excluded

Neither cell's `vlp16` disjunct fired, so `cells.yaml`'s `sweep_classes`
pre-registration triggered `32ch` on **both** cells with no owner consultation
(PROVENANCE §22.7, §22.8).

**`B-cyc/run-031`…`run-036` are EXCLUDED under `exclusions.md` criterion 3,
reason `harness:65fbe09`** (applied only through `write_manifest.py --exclude`,
commit `4e195f6`; two fields per manifest and nothing else; the runs stay in
`benchmarks/results/` with all their data). `BENCH_TIER4_SWEEP_ARGS` was not
exported, so the spawned demo ran its defaults and a **vlp16 rig was filed under
a 32ch label**. The defect was caught by a **measured** quantity, not a label:
the observer's median serialized `size_bytes` on the registered lidar topic read
**×0.9987 … ×1.0005** against the cell's own vlp16 baseline where the registered
class ratio is **4.1667**.

**They were deliberately NOT relabelled to `vlp16`.** They did measure a vlp16
rig, so relabelling would look like salvage — but it would retroactively move
Task 14's already-filed vlp16 booleans by adding six runs to a pool whose
verdict is recorded, which is a worse violation than the one being corrected.
They are excluded and stay out of every pool.

Six replacements were collected after the fix (`run-040`…`run-045`, all
`×4.1679 … ×4.1730`, six `run.sh` invocations, all exit 0, zero exclusions).
B-cyc's `--class 32ch` pool is therefore **15 rows: 6 excluded, 9 scored** — the
three standing ablation runs (`run-037`…`run-039`, which genuinely ran 32ch and
whose own `raycast_baseline.json` records `channels 32` / `points_per_second
1200000`) plus the six new measured runs. Cell A's nine stand in full and were
not re-run.

**Task 14's vlp16 data was correct BY COINCIDENCE, and that is recorded rather
than glossed.** The same defect was present for Task 14's collection: cell
B-cyc's six measured vlp16 runs also received no sweep arguments and also fell
back to `--lidar-channels 16 --lidar-pps 288000` — which for that class was the
**right** rig, because the fallback happens to equal `vlp16` exactly. The data
stands and is not re-run (its payload is self-consistent across all six at
238 808 … 239 160 B, and is the baseline every ratio above is taken against).
**What did not exist was the guarantee.** Had Task 14 been the 32ch collection,
the same silence would have produced the same mislabelling. The durable form of
a class claim is a per-run **measured** quantity, not a derivation from how a
launcher resolves its arguments (§27.6).

### 6.3 The wording: "ceiling not located up to the 32ch class"

Nothing fired at `vlp16` and nothing fired at `32ch`, on either cell. Per the
`cells.yaml` registration, **`128ch` stays struck on either branch** — "once the
criterion fires at a lower class nothing needs it, and if it does not fire at
`vlp16` the informative next probe is the adjacent class, not the extreme one."
No 128ch data was collected and none is proposed; both launchers still refuse
the class by name for want of a sensor-argument mapping, so the strike is
enforced in code, not merely documented.

**No `n = 5` extension was executed on either class.** The parent spec's "≥ 5 at
the ceiling class" is pre-registered for a cell whose disjunct **fired**;
neither did, at either class. Both cells stand at n = 3 per arm at both classes.

**Amended M4 is therefore MET on its second disjunct**: the 32ch step-up
executed and was adjudicated. The campaign's wording for the outcome is
**"ceiling not located up to the 32ch class"** — a statement about where the
search stopped, _not_ a new step-up and not a licence for one. Each boolean was
read from its own cell's table and decides its own cell; nothing here follows
from comparing the cells.

**Cell E is out of the sweep**, by its registered static-only downgrade
(PROVENANCE §7.4, §9.1). No E sweep points and no E raycast baseline were
collected, and the spec required this to be recorded in wording rather than left
as silence. It is recorded here.

### 6.4 The ablation decomposition, and why it is a lower bound

The ablation arm is a plain CARLA client with an identical sensor rig per class
and `listen(lambda d: None)` — no ROS, no publishing. Subtracting it from a
measured arm gives the publish-and-transport share of the simulator's CPU.
Median-of-run-means `carla-server` `cpu_pct` (command 8):

| cell  | class   | paced  | unpaced | ablation | paced − ablation | unpaced − ablation |
| ----- | ------- | ------ | ------- | -------- | ---------------- | ------------------ |
| A     | `vlp16` | 208.35 | 208.35  | 200.33   | **+8.02**        | **+8.02**          |
| A     | `32ch`  | 315.67 | 320.70  | 310.23   | **+5.44**        | **+10.47**         |
| B-cyc | `vlp16` | 210.24 | 210.50  | 209.55   | **+0.69**        | **+0.94**          |
| B-cyc | `32ch`  | 260.33 | 258.37  | 271.90   | **−11.57**       | **−13.53**         |

**THE RPC-HOP CAVEAT, disclosed verbatim from the registration (spec 1e):** the
baseline includes the client stream, so **transport cost = total − baseline is a
LOWER BOUND for the natives.** The ablation client receives every point cloud
over CARLA's RPC/streaming protocol to a separate host process; the native
publishers do not pay that hop. The B-cyc `32ch` row is that caveat made
concrete: the difference goes **negative**, which under the caveat means the
native publish path costs less than the RPC-stream baseline and **no positive
lower bound is recoverable there** — it is not evidence that publishing is free.

**This table is within-cell and within-class only.** The two cells' ablation
rigs differ by construction, mirroring each cell's own registered sensor
(`raycast_baseline.json`): cell A's is `rig: extension`, `sensor_tick 0.05`,
`range 120.0`; cell B-cyc's is `rig: tier4`, `sensor_tick 0.1`, `range 100.0`,
`lower_fov -20.0 / upper_fov 10.0`. Cell A's ablation client therefore raycasts
at twice B-cyc's rate over a longer range. **No cross-cell reading of this table
is licensed**, and the numbers are reported per cell for that reason. This is
the same registered per-cell sensor-rate difference that bounds 2.5(c).

## 7. Confounds

`benchmarks/README.md`'s `## Known confounds` section is the pre-registered
source; this table indexes it, carries forward P3 §7's rows that still apply,
and adds the P4-era rows. Nothing here is a correction to a measurement.

### 7.1 The P4-era confound rows

| id   | confound                                              | what it is                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | cells      | where registered                                             |
| ---- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------ |
| P4-1 | **The image confound, on every B-side number**        | Cell B-cyc runs the **same Autoware image as cell B**, pinned by digest `ghcr.io/autowarefoundation/autoware@sha256:5c22369a…e8ee` (`universe-devel-cuda`); cell A runs `ghcr.io/autowarefoundation/autoware:universe-devel` **by tag**. This is deliberate — transport is the only variable P4 changes on the tier4 side, so B-vs-B-cyc is clean, and separating the two images is explicitly out of scope. The cost is that **every A-vs-B-cyc row in this document also spans an image difference**, and no row in section 2 or 3 is corrected for it.                                                                                                                                                                                                     | A vs B-cyc | spec 1c; `cells.yaml` B-cyc entry; verified by command 11    |
| P4-2 | **rmw-matched, NOT profile-matched**                  | Both cells run `rmw_cyclonedds_cpp` with SHM off. Cell A runs the **lo-pinned** profile (`transport.dds_profile_sha256 = 1eeef31e…f2865`); cell B-cyc runs **no profile** (`""`). This is a **measured necessity**, not a preference: the Task 9 wire-visibility matrix (`benchmarks/patches/tier4-native/README.md:349-355`) shows rows 5 and 10 (cyclone + `cyclonedds.xml`) see **nothing** from the tier4 fork's Fast-DDS publishers — `LIST no, ECHO no` — and **row 11 (cyclone, no profile) is the only cyclone configuration in which the fork is readable at all** (`ECHO yes`, `RATE 9.930`). The A(lo-profile) ↔ B-cyc(no-profile) interface difference is therefore structural to the comparison and cannot be removed without losing it.         | A vs B-cyc | spec 1c; matrix rows 5 / 10 / 11                             |
| P4-3 | **Row-11's own registered caveats, inherited**        | Quoted from the matrix rather than tidied away: "Rows 6 and 11 work only because Cyclone with no profile binds a routable interface (`wlp130s0f0`) — they make the measurement depend on the host's wireless NIC and on Cyclone's graph being flaky for bare-DDS publishers (row 11 receives data while `topic list` denies the topic exists). **Do not use them.**" B-cyc uses row 11 knowingly, because it is the only workable option. **Neither caveat surfaced as a run failure**: 20/20 static and 20/20 closed-loop runs completed, zero exclusions, `duel.sh`'s two-consecutive-failure abort never armed, and the artefact digests were identical across all runs. The caveats stand as confounds on the _result_, not as costs to the _collection_. | B-cyc      | matrix caveat paragraph; PROVENANCE §18.6, §20.6, §20.8      |
| P4-4 | **Observer / NIC placement**                          | Every cell is observed by the same `bench-observer:universe-devel` image (local digest `sha256:b78ec01a…a5385`) with SHM off, and the observer's RMW **follows the cell** — in P4 that means **both** cells are observed over CycloneDDS, which is a tighter instrument match than P3 had (where the observer followed cell B onto Fast-DDS). What is **not** matched is the interface: cell A's traffic rides the lo-pinned profile while B-cyc's rides the host's routable NIC (P4-2/P4-3). The observer container is `network_mode: host` in both cases.                                                                                                                                                                                                   | A vs B-cyc | `benchmarks/pins.yaml`; `config/observer_topics/<cell>.yaml` |
| P4-5 | **Registered sensor-rate asymmetry**                  | Cell A's `lidar_expected_hz` is **20.0**; B-cyc's is **10.0**. `achieved_rate_ratio` normalises each cell against its own target and is unaffected. **`carla_process_cpu_pct` does not normalise at all**, so cell A's simulator carries twice the sensor cadence, and `README:3986-4008` separately registers cell A shipping **2.118×** the bytes for the same point count. Both run **against** cell A on the CPU row and on the two latency rows. Present unchanged in P3.                                                                                                                                                                                                                                                                                | A vs B-cyc | `cells.yaml` (command 7); `README:3986-4008`                 |
| P4-6 | **The ablation baseline's RPC hop**                   | The publish-disabled arm streams every cloud to a separate client process over CARLA's RPC/streaming protocol, which the natives do not pay. **transport cost = total − baseline is a LOWER BOUND**, and on B-cyc `32ch` it is negative, i.e. no positive bound is recoverable. The two cells' ablation rigs also differ by construction (`sensor_tick` 0.05 vs 0.1, `range` 120 vs 100, fov limits), so the decomposition is **within-cell only**.                                                                                                                                                                                                                                                                                                           | A, B-cyc   | spec 1e; `raycast_baseline.py` docstring; 6.4                |
| P4-7 | **The static pre-arm control-silence condition**      | The §19.4 mechanism recurred at **1 of 10** closed-loop B-cyc runs against **2 of 10** static — a comparable rate. Closed-loop it costs nothing because the controller masks it within ~2 s; **on the static arm nothing masks it**, and it remains a live confound for the static pool and for the two B-cyc zero-control-traffic runs behind the `control_staleness_ms` row's `0/8`.                                                                                                                                                                                                                                                                                                                                                                        | B-cyc      | PROVENANCE §19.4, §20.6, §21.1                               |
| P4-8 | **CAL-seam's three residuals**                        | Publish order (sign **not** established), in-core-only sample loss (runs **against** the seam measuring cheap), and serializer implementation (code only — payload identity closed at 921 905 CDR bytes / 921 908 wire bytes). Plus: the five filed runs cannot separate transport drops from publisher skips on the in-core twin.                                                                                                                                                                                                                                                                                                                                                                                                                            | CAL-seam   | PROVENANCE §11.9, §13.2, §13.4, §11.8; 5.3                   |
| P4-9 | **Clock-fit residual asymmetry on `one_hop_wall_ms`** | `README:624` registers that a duel row must be read next to its `fit_residual_ns`. B-cyc's max-abs sim→wall fit residual medians are **3.77 ms** (static) and **54.60 ms** (closed-loop) against cell A's **1.77 / 3.58 ms**, on a metric with a **2.0 ms** margin. Maxima, not typical errors — but the closed-loop `one_hop_wall_ms` parity row is the weakest in this document.                                                                                                                                                                                                                                                                                                                                                                            | A vs B-cyc | `README:624`; 2.6                                            |

### 7.2 P3-era confound rows that still apply, unchanged

Indexed, not restated. Read them in `docs/evaluation/p3-baseline.md` §7.

| row  | applies to P4 because                                                                                                                                                                                                                                |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P3-2 | The observer image and the **G1 ladder rung-2** map bundle are unchanged: all P4 UE cells carry `placement.map_bundle_pin: town10_pcd_regen`, which is not reproducible from its pin alone and whose coverage is bounded by where the ego drove.     |
| P3-3 | pcd variant per cell — A and B-cyc both on `town10_pcd_regen`, so this row is **neutral within the P4 duel** and is carried only for cross-phase reading.                                                                                            |
| P3-4 | Container placement: both P4 duel cells are `editor-game` on the **same** engine BuildId, so the row is neutral within P4 — but the BuildId itself moved from P3 (section 9).                                                                        |
| P3-5 | Patch inventory: `patches/tier4-native/` still carries `0001-toolchain-libm`, `0002-glibc-compat`, `0003-autoware-demo-params` on B-cyc's path; the extension carries none. The applied `.patch` files are **byte-identical** to P3's (section 9.3). |
| P3-6 | `control_mode: MANUAL` on cell A vs unconditional `AUTONOMOUS` on the tier4 fork — unpatched deliberately, since whether an approach reports its own control mode is part of the interop completeness being compared.                                |
| §7.2 | Physics substepping (B family disables it at 20 Hz, A leaves CARLA's default on) and localization initialization (the stop check) apply to B-cyc exactly as to B, since B-cyc changes only the transport.                                            |

**Two P3 rows are RETIRED by P4 and must not be carried forward blindly:**

- P3 §7.2's "CAL-seam: **`C1(a)` seam overhead is now UNMEASURED**, the cell
  having been struck" — retired. It is measured; see section 5.
- P3 §7.3's fabricated non-zero `publisher_drop_rate` — retired for **P4 pools
  only**, by the spec's 1f fix (`3b9212e`, pinned by `fd2c125`). P3's pools were
  not re-scored and the artefact remains in the P3 record.

## 8. Deviations log

Every deviation from the plan as written, with the ruling that produced it.

### 8.1 Branches, and which way each went

| item                                          | outcome                           | why                                                                                                                  |
| --------------------------------------------- | --------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **B-cyc closed-loop smoke failure branch**    | **DID NOT FIRE**                  | B-cyc armed and drove first try (PROVENANCE §14.4). Transport phase kept both arms; the sweep kept its B-cyc column. |
| **Branch (c) — B-cyc `ndt_rate_ratio` ≥ 0.9** | **FIRST DISJUNCT FIRED**          | All ten static runs ≥ 0.9989 (section 4). Depression bound to the Fast-DDS configuration.                            |
| **`vlp16` ceiling disjunct, per cell**        | **DID NOT FIRE** on A or B-cyc    | 18/18 rows `reached False`, empty reasons (§22.7).                                                                   |
| **32ch step-up, per cell**                    | **EXECUTED mechanically on both** | Pre-registered auto-execution; no owner consultation, as registered.                                                 |
| **`32ch` ceiling disjunct, per cell**         | **DID NOT FIRE** on A or B-cyc    | 18/18 scored rows `reached False` (§26.7, §27.4).                                                                    |
| **n = 5 extension at the ceiling class**      | **NOT EXECUTED**                  | Pre-registered for a cell whose disjunct fired. Neither did, at either class.                                        |
| **`128ch`**                                   | **STAYS STRUCK**                  | Registered on either branch; enforced in code — both launchers refuse the class by name.                             |
| **Cell E in the sweep**                       | **OUT**                           | Its registered static-only downgrade. No E sweep points, no E raycast baseline. Recorded in wording (6.3).           |

### 8.2 Measurement-condition and procedural deviations, all disclosed

| deviation                                                                                                                                       | disposition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **The static duel took TWO `duel.sh` invocations** (a resume after the driver was killed mid-duel)                                              | Recorded in §18.2 with two disclosed residues (§18.3), both artefacts of the resume. Refuted: it was not the two-consecutive-failure abort (that path prints a `DUEL FAIL` line, absent from the console) and not systematic row-11 uncollectability (the resume collected 6 further runs with zero failures). The **closed-loop** duel took one invocation with neither residue (§20.4).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **`bootstrap_carla_msgs.sh` REFUSED on every hygiene block** across Tasks 10, 14 and 15                                                         | A property of the hygiene rule's **ordering**, not of any task: the rule pairs `docker compose down` with a bootstrap whose first act requires a _running_ `autoware` container, which the `down` just removed. **Unreachable for every cell on this ordering.** Cost nothing (`carla_msgs` is sourced optionally, `launch_autoware.sh:202`, and every measured run armed and produced full data). Not fixed mid-collection — that would be revising a registered procedure after data exists.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **Sweep `vlp16` manifests carry `-dirty` shas on BOTH keys** (`51d27f23…-dirty`, `7000c785…-dirty`)                                             | Disclosed. The **duel** pools are clean and sha-matched within each arm (section 9.2), and no number in sections 2–4 comes from a `-dirty` manifest. The `-dirty` suffix reflects a working tree differing from HEAD at run time; the P3 caveat class (§9.1) recurs here for the sweep pools only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **B-cyc's `32ch` pool spans two harness shas** (`55df5c1` on the three standing ablation runs, `4e195f6` on the six re-collected measured runs) | A direct consequence of the criterion-3 exclusion and re-collection (6.2). Disclosed rather than normalised; the ablation runs were deliberately not re-run because that arm genuinely ran 32ch.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **PROVENANCE §26 claimed `pre-commit run --all-files` clean and it was not**, at `b6fbc80`                                                      | Recorded in §27.8 and fixed in `da1f6df` (shellcheck excluded from `benchmarks/evidence/` on the same grounds the ruff hooks already exclude it — a lint-driven edit to a certified verbatim producer would make it no longer the file that produced the recorded figure). No measurement affected.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **`sweep_verdict.py --class` did not filter the rows it scored** (Task C2, §24)                                                                 | Found and fixed **offline, before Task 15 collected anything** (`512adbc`, `55df5c1`). Task 14's filed booleans reproduce byte-exactly once the new class-drop counter line is stripped (§26.3, §27.4). No filed manifest was rewritten; the legacy `""`-admits-to-vlp16 clause is what makes that possible.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| **Task 16's Step 2 used `>` instead of `\| tee`**                                                                                               | Capture-level only, same as §20.2's. An `rtk` proxy compresses piped output on this host. Cannot affect what the tool computed; the file's md5 is recorded in 2.1.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **Task 16 did not embed `report.py`'s full per-cell tables** (P3 §3 did)                                                                        | Deliberate; reason in 0.3. No number in this document comes from `report.py`, and the one output that is needed (the registered CAL-seam trap) is embedded in 5.5.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **`benchmarks/evidence/**` was not excluded from the text-mutating pre-commit hooks, and one filed byte moved**                                 | Found and closed during Task 11 (§16.3, §17, `37aac09`, `d57df9d`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **CAL-seam manifests carry no `placement.engine_build_id`**                                                                                     | §12.2: `preflight.sh`'s BuildId check is gated on `APPROACH = extension \| tier4-native`, and CAL-seam registers `calibration`, so no BuildId reaches its manifest even though it boots the extension fork's editor. Recorded as a finding, not repaired retroactively. The live identity gate covered it (§12.1: `bc08ce19` on 11 of 11 `UnrealEditor.modules`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **`benchmarks/analysis/manifest.py` — a frozen path — was AMENDED TWICE during P4, and six filed manifests were RECLASSIFIED**                  | Disclosed here because section 0's freeze statement is scoped to Task 16 and this row is the branch-level truth. (1) **Task 2** added `duel_id: str = ""` to `RunManifest` so a duel pool could be partitioned by which duel a run was collected for; the `""`-admits-to-`("A","B")` legacy clause exists precisely so no already-filed P3 run had to be rewritten. (2) **Task C2** added `class_id: str = ""` the same way, for the same reason, after the `sweep_verdict.py --class` filter defect (row above) — the fix required the second amendment, which that row does not say. Both are entered in `benchmarks/README.md`'s `### Amendment rule` ledger with their completeness argument. Separately, **six B-cyc `32ch` manifests (`run-031`…`run-036`) were reclassified to `excluded: true`** under frozen criterion 3 via `write_manifest.py --exclude` (`4e195f6`), two fields per manifest and nothing else — see 6.2. No filed number was re-scored by either amendment: Task 14's booleans reproduce byte-exactly (§26.3, §27.4). |

### 8.3 Two runs that established more about a cause without becoming excludable

`B-cyc/run-002` and `run-003` recorded zero control traffic on the static arm.
§19.4 establishes the mechanism (the emergency cycle ran once, before the
scoring window opened) and §20.6/§21.1 narrow what the signature means.
**Neither is excluded, and the non-exclusion was re-walked rather than assumed**
against every frozen criterion: criterion 2's `gate:control_cmd-silent` is
engage-predicated and unreachable in a static arm; criterion 5 is map-scoped to
Nishi-Shinjuku and these are `Town10HD_Opt`; criteria 4 and 10 need a stall or a
capped window and both runs carry the standard ~68.5 s window with no
`clock_stall.marker`. **Establishing a cause does not make a run excludable.**

### 8.4 Deferred, and named rather than silently dropped

**Forty** findings from the P4 review rounds — 39 minors and one out-of-scope
observation — are parked in the branch's own ledger for the final whole-branch
review's triage (`.superpowers/sdd/2026-08-03-p4-transport-sweep-plan/deferred-minors.md`;
one entry per line-leading `Task N:`). They are not enumerated here: none of
them affects a filed measurement or a number in this document. The final
whole-branch review has since triaged them — what it elected to fix is in this
branch's final fix commits, and the remainder carry to P5. The two named in §27.8 (the
`QUALITY GATE FAIL: … pose.csv` console-string documentation, and
`sweep_driver.sh`'s hardcoded `REPO=`) are representative of the class.

## 9. P4 ↔ P3 identity caveats

P3 §9.1 registered six keys P4 had to match and required them re-verified before
anything was collected. Task 10 took that gate **live** — against the live
environment, not against filed history, because a census over filed manifests
cannot answer a question about the live environment — and recorded **zero
`4210e602` readings live, no STOP** (§12.1).

### 9.1 Two keys moved between P3 and P4, deliberately

| key                         | P3 value                               | P4 value                                   | why it moved                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| --------------------------- | -------------------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `placement.engine_build_id` | `4210e602-78ec-46e1-8f2f-03fadbe036a3` | **`bc08ce19-f19c-46fe-808f-dbb2b0ddf41a`** | The owner's **D8 lift** for one registered relink round (spec 1a), taken to build the fork-side in-core publisher C1(a) needs. Converged in three rounds. D8 was re-instated immediately after: **no further relink for the remainder of the campaign**, and every P4 run from Task 10 onward **that carries the key** carries `bc08ce19`. (Task 10 _is_ the CAL-seam collection, and its five runs carry no `placement.engine_build_id` at all — structurally, not by drift. See the bullet below.) |
| `harness_git_sha`           | moved **during** P3 (§9.3)             | moves **within** P4 too, by task           | The harness is under active TDD across a campaign. See 9.2 for what it does and does not cost.                                                                                                                                                                                                                                                                                                                                                                                                       |

**What each caveat touches:**

- **Within-P4 comparisons are unaffected by the BuildId.** One engine identity
  across all P4 collection, verified by Task 10's six-key census on all six keys
  and re-verified per run by command 11, which prints the census and the
  partition it counted:

  ```text
  engine_build_id over all 191 filed manifests:
    bc08ce19-f19c-46fe-808f-dbb2b0ddf41a     84
    4210e602-78ec-46e1-8f2f-03fadbe036a3     61
    None                                     46

  P4 runs (patches_git_sha startswith 7000c785): 89
    A          run-015..run-053  n=39  engine_build_id={'bc08ce19': 39}
    B-cyc      run-001..run-045  n=45  engine_build_id={'bc08ce19': 45}
    CAL-seam   run-001..run-005  n=5   engine_build_id={'None': 5}
  ```

  **`bc08ce19` appears in every P4 manifest that carries the key, without
  variation — 84 of them — and the other five P4 runs (CAL-seam) carry no key at
  all.** That absence is §12.2's structural finding, not drift: `preflight.sh`'s
  BuildId check is gated on `APPROACH = extension | tier4-native` and CAL-seam
  registers `calibration`, so no BuildId ever reaches its manifest. Zero P4
  manifests carry `4210e602`.

  **THREE COUNTS ARE IN CIRCULATION HERE AND THE RECORD SHOULD STATE WHY**, since
  an earlier revision of this bullet asserted a fourth (`91`) that no command
  produces and that is simply wrong:

  | count  | what it counts                                                                        |
  | ------ | ------------------------------------------------------------------------------------- |
  | **84** | P4 manifests carrying `engine_build_id` — the only ones the identity claim is _about_ |
  | **89** | **all filed P4 runs**, i.e. 84 + CAL-seam's five key-less ones                        |
  | 88     | the count you get from the partition `A/016-053 + B-cyc/001-045 + CAL-seam/001-005`   |
  | ~~91~~ | **retracted — reconstructible from no partition of the filed data**                   |

  **The P4 boundary in cell A falls at `run-015`, not `run-016`**, and that is
  where the 88/89 discrepancy comes from. `A/run-015` is Task 11's cell-A
  bring-up (`duel_admissible: false`, §14.2), and it is the first cell-A run to
  carry both `patches_git_sha 7000c78` (Task 9's relink commit) and
  `engine_build_id bc08ce19`; `A/run-014` carries `ccff4f9` / `4210e602` and its
  harness sha `f0f8b4b` is a 2026-07-31 P3-era commit. **§0.3's rendering
  statement is corrected to match**: the P4-collected cell-A range is
  `run-015`…`run-053`, 39 runs, and all 39 render (zero `RENDER FAILED` rows in
  that range).

  The boundary is **derived, not asserted**: command 11 defines a P4 run as one
  whose `patches_git_sha` starts with `7000c785`, which is the sha that moved at
  the relink (§9.3), and prints the resulting per-cell ranges so the definition
  is checkable rather than taken on trust.

- **P4 ↔ P3 cross-phase comparisons carry the engine-identity caveat.** Any
  statement that sets a P4 per-cell absolute against a P3 one crosses an engine
  relink. **This document makes no such statement.** The attribution bracket
  (section 2) compares two _verdicts_, each computed entirely within its own
  phase against the same frozen margins — which is what the spec registered and
  the only cross-phase reading it licenses.
- **P3's verdicts are already computed and are not touched.**

### 9.2 The harness sha inside P4, pool by pool

`harness_git_sha` is the measurement code. Within P4 it is **matched across both
cells of each duel arm**, which is the property the duels actually need:

| pool                                            | cell A            | cell B-cyc                                      | matched?                                                                                                           |
| ----------------------------------------------- | ----------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| static duel (`A/016–025`, `B-cyc/002–011`)      | `d57df9d1…`       | `d57df9d1…`                                     | **yes**                                                                                                            |
| closed-loop duel (`A/026–035`, `B-cyc/012–021`) | `3fcd8079…`       | `3fcd8079…`                                     | **yes**                                                                                                            |
| sweep `vlp16`                                   | `51d27f23…-dirty` | `51d27f23…-dirty`                               | **yes**, both `-dirty`                                                                                             |
| sweep `32ch`                                    | `55df5c1c…`       | `55df5c1c…` (ablation) / `4e195f6a…` (measured) | **no** — see 8.2                                                                                                   |
| CAL-seam                                        | —                 | —                                               | `7a3651bd…`, clean; C1(a) is a within-run paired delta, so a cross-pool sha is not a comparability question for it |

**The duel pools are the ones a verdict rests on, and both are sha-matched and
clean (no `-dirty` on either key).** That is a provenance improvement over P3,
which had to disclose 20 `-dirty` manifests with 12 of them behind the frozen
`one_hop_wall_ms` margin.

### 9.3 A third key moved, and it is explained rather than merely observed

`patches_git_sha` moved from P3's `ccff4f9…` to P4's `7000c785…`.
`write_manifest.py:30` defines it as `git log -1 --format=%H --
benchmarks/patches/`, i.e. a **git-derived** key, not an environment fact.
`7000c78` is Task 9's own relink commit, which touched that path. **The applied
patch inventory did not change**, and that is checkable rather than asserted:

```bash
git diff --stat ccff4f946a9b33dc1d5cfacac0c6217656bbe10a \
                7000c7855bea62960f47d18774b2aca02f264777 -- benchmarks/patches/
# benchmarks/patches/tier4-native/README.md | 6 +++++-
# 1 file changed, 5 insertions(+), 1 deletion(-)
```

One README. **No `.patch` file changed between P3 and P4.**

### 9.4 The keys that did NOT move

Verified live at the identity gate and again in every filed manifest:
`extension_carla_fork.sha` `62ca380f…`, `tier4_carla_fork.sha` `6315b856f`,
`dds_profile_sha256` (cyclone) `1eeef31e…f2865` and (udp_only) `9886f744…65098`,
`autoware_universe_devel.digest` `sha256:5c22369a…e8ee`, `bench_observer_images`
local digest `sha256:b78ec01a…a5385`, `map_name` `Town10HD_Opt`,
`placement.map_bundle_pin` `town10_pcd_regen`, `placement.run_mode`
`editor-game`.

## 10. Reproduction index

Every command in this document, in one place. All were run from the repository
root at commit `fcb83334637b6c7be6e7fda88da2ce2dd0f77c46` on an idle host.

| #   | produces                                                                                                                                      | command                                                                                                                                                                            |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | 0.3's per-cell regeneration (exit 1, explained in 0.3)                                                                                        | `PYTHONPATH=. python3 -m benchmarks.report benchmarks/results > /tmp/p4-report-tables.md`                                                                                          |
| 2   | sections 2 and 3's verdict — **P4's single duel invocation**                                                                                  | `PYTHONPATH=. python3 benchmarks/scripts/duel_verdict.py A B-cyc > /tmp/p4-duel-verdict.md`                                                                                        |
| 3   | 0.4's pool census (the 4 + 10 split the tool prints as 14)                                                                                    | the `manifest.json` walk below                                                                                                                                                     |
| 4   | 3.2's `vector-map-delivery.json` census                                                                                                       | the `vector-map-delivery.json` walk below                                                                                                                                          |
| 5   | section 4's `ndt_rate_ratio` table                                                                                                            | the `quality.json` walk below                                                                                                                                                      |
| 6   | 2.6's clock-fit residual table                                                                                                                | the `fit_sim_wall_affine` walk below                                                                                                                                               |
| 7   | the per-cell metric bindings quoted throughout                                                                                                | `PYTHONPATH=. python3 -c "from benchmarks.scripts.cell_info import load_cells_doc, metrics_for; d=load_cells_doc(None); print(metrics_for(d,'A')); print(metrics_for(d,'B-cyc'))"` |
| 8   | 6.4's ablation decomposition                                                                                                                  | the `read_resources_csv` walk below                                                                                                                                                |
| 9   | section 5's C1(a) table                                                                                                                       | `for r in 001 002 003 004 005; do PYTHONPATH=. python3 -m benchmarks.scripts.cal_report benchmarks/results/CAL-seam/run-$r; done` + the delta walk below                           |
| 10  | section 6's ceiling tables                                                                                                                    | `PYTHONPATH=. python3 benchmarks/scripts/sweep_verdict.py {A,B-cyc} --class {vlp16,32ch}` (four invocations)                                                                       |
| 11  | **all of section 9** — the BuildId census and count (9.1), the per-pool `harness_git_sha` / `patches_git_sha` table (9.2), and 9.3's key move | the walk below (plus the six-key census in `p3-baseline.md` §9.1, run verbatim, for the live-vs-filed distinction)                                                                 |
| 12  | the test-suite baseline                                                                                                                       | `python3 -m pytest tests/ -q` → **1317 passed, 1 skipped** (P3's was 1084 passed / 1 skipped). See the note below on the one registered load-sensitive flake.                      |

**The suite figure carries a disclosure, because the wrap's own verification run
did not print it cleanly.** The baseline was measured on an idle host at this
commit before any of this task's edits: **1317 passed, 1 skipped**. The
post-edit verification run, taken while the host was still loaded from
`pre-commit run --all-files` (1-minute loadavg 2.44, 5-minute 14.69), reported
**1 failed, 1316 passed, 1 skipped** — the failure being
`tests/benchmarks/test_teardown.py::test_tier4_autoware_sh_aw_sidecar_settles_on_the_post_exec_cmdline`,
one of the two registered load-sensitive flakes.

**It was not accepted on authority.** Its recorded failure mode (PROVENANCE
§26.1) is a race in the test's own subprocess setup producing an empty
`/proc/<pid>/cmdline` read, and the assertion that fired was
`assert 'os.execv' in ''` under the test's own message "stub setup is broken --
this should be the PRE-exec argv" — an empty string, i.e. exactly that mode.
Re-run in isolation: **1 passed in 5.17 s**, the same figure §26.1 recorded.
**Effective count 1317 passed / 1 skipped, equal to the pre-edit baseline** —
which is what a documentation-only task should produce, since it adds no tests.

Command 3 — the duel pool census:

```bash
PYTHONPATH=. python3 - <<'PY'
import json, pathlib
from collections import Counter
for cell in ("A", "B-cyc"):
    for arm in ("static", "closed-loop"):
        c, pooled, dropped = Counter(), [], []
        for run in sorted((pathlib.Path("benchmarks/results")/cell).glob("run-*")):
            m = json.loads((run/"manifest.json").read_text())
            if m["arm"] != arm: continue
            if m.get("excluded"): c["excluded"] += 1; continue
            if not m.get("duel_admissible"):
                c["not-admissible"] += 1; dropped.append((run.name, "duel_admissible=false")); continue
            if m.get("duel_id", "") != "A+B-cyc":
                c["wrong-duel_id"] += 1; dropped.append((run.name, "duel_id")); continue
            c["pooled"] += 1; pooled.append(run.name)
        print(f"{cell} {arm}: {dict(c)}")
        print(f"  pooled: {pooled[0]}..{pooled[-1]} (n={len(pooled)})" if pooled else "  pooled: none")
        for d in dropped: print("   drop", d)
PY
```

Command 4 — the delivery-probe census:

```bash
PYTHONPATH=. python3 - <<'PY'
import json, pathlib
for p in sorted(pathlib.Path("benchmarks/results").glob("*/run-*/vector-map-delivery.json")):
    d = json.loads(p.read_text())
    print(p.parent.parent.name, p.parent.name, d["data_bytes"], d["pre_republish_delivered"],
          len(d["attempts"]), [a.get("verify_wait_s") for a in d["attempts"]], d["exit_code"])
PY
```

Command 5 — the `ndt_rate_ratio` walk (P3 §5.2's script, retargeted to B-cyc's
static duel pool):

```bash
PYTHONPATH=. python3 - <<'PY'
import json, pathlib
for run in sorted(pathlib.Path("benchmarks/results/B-cyc").glob("run-*")):
    m = json.loads((run/"manifest.json").read_text())
    if m["arm"] != "static" or not m["duel_admissible"] or m["excluded"]: continue
    d = json.loads((run/"quality.json").read_text())
    print(run.name, d["ndt_rate_ratio"], d["gate_pass"], d["reasons"])
PY
```

Command 6 — the clock-fit residuals:

```bash
PYTHONPATH=. python3 - <<'PY'
import pathlib, statistics
from benchmarks.analysis.bench_io import read_clock_csv
from benchmarks.analysis.clockfit import fit_sim_wall_affine
pools = {("A","static"): range(16,26), ("B-cyc","static"): range(2,12),
         ("A","closed-loop"): range(26,36), ("B-cyc","closed-loop"): range(12,22)}
for (cell, arm), rng in pools.items():
    vals = []
    for i in rng:
        d = pathlib.Path("benchmarks/results")/cell/f"run-{i:03d}"
        ns, w = read_clock_csv(d/"clock.csv")
        vals.append(fit_sim_wall_affine(ns, w).max_abs_residual_ns/1e6)
    print(cell, arm, "median", round(statistics.median(vals), 2), [round(v,1) for v in vals])
PY
```

Command 8 — the ablation decomposition:

```bash
PYTHONPATH=. python3 - <<'PY'
import json, pathlib, statistics
import numpy as np
from benchmarks.analysis.bench_io import read_resources_csv
POOL = {("A","vlp16"):    {"paced":range(36,39),"unpaced":range(39,42),"ablation":range(42,45)},
        ("A","32ch"):     {"paced":range(45,48),"unpaced":range(48,51),"ablation":range(51,54)},
        ("B-cyc","vlp16"):{"paced":range(22,25),"unpaced":range(25,28),"ablation":range(28,31)},
        ("B-cyc","32ch"): {"paced":range(40,43),"unpaced":range(43,46),"ablation":range(37,40)}}
for (cell, klass), arms in POOL.items():
    out = {}
    for arm, rng in arms.items():
        vals = []
        for i in rng:
            d = pathlib.Path("benchmarks/results")/cell/f"run-{i:03d}"
            m = json.loads((d/"manifest.json").read_text())
            assert m["arm"] == arm and not m["excluded"], d
            vals.append(float(np.mean(read_resources_csv(d/"resources.csv")["carla-server"]["cpu_pct"])))
        out[arm] = statistics.median(vals)
    print(cell, klass, {k: round(v,2) for k,v in out.items()},
          "paced-abl", round(out["paced"]-out["ablation"],2),
          "unpaced-abl", round(out["unpaced"]-out["ablation"],2))
PY
```

Command 9 — the C1(a) paired delta (unrounded, from `cal_report`'s own
`summarize_run`):

```bash
PYTHONPATH=. python3 - <<'PY'
import statistics
from benchmarks.scripts.cal_report import summarize_run
d50 = []
for r in ("001","002","003","004","005"):
    s = summarize_run(f"benchmarks/results/CAL-seam/run-{r}")
    seam, core = s["topics"]["/bench/seam_cloud"], s["topics"]["/bench/incore_cloud"]
    d = seam["one_hop_p50_ms"] - core["one_hop_p50_ms"]; d50.append(d)
    print(r, round(seam["one_hop_p50_ms"],4), round(core["one_hop_p50_ms"],4), round(d,4),
          round(s["processes"]["carla-server"]["cpu_pct_mean"],2))
print("median", round(statistics.median(d50),4), "min", round(min(d50),4), "max", round(max(d50),4))
PY
```

Command 11 — the identity walk. It produces **all three** of section 9's
subsections: the campaign-wide `engine_build_id` census with its counts and the
derived P4 partition (§9.1), the per-pool `harness_git_sha` / `patches_git_sha`
table (§9.2), and the `patches_git_sha` value §9.3 is about. Filed as
`benchmarks/evidence/p4-task16-wrap/identity_walk.py`; its output is filed
alongside as `identity-walk.log`.

```bash
PYTHONPATH=. python3 benchmarks/evidence/p4-task16-wrap/identity_walk.py
```

```text
engine_build_id over all 191 filed manifests:
  bc08ce19-f19c-46fe-808f-dbb2b0ddf41a     84
  4210e602-78ec-46e1-8f2f-03fadbe036a3     61
  None                                     46

P4 runs (patches_git_sha startswith 7000c785): 89
  A          run-015..run-053  n=39  engine_build_id={'bc08ce19': 39}
  B-cyc      run-001..run-045  n=45  engine_build_id={'bc08ce19': 45}
  CAL-seam   run-001..run-005  n=5   engine_build_id={'None': 5}

  A closed-loop duel           n=10  harness=['3fcd807'] patches=['7000c78'] buildid=['bc08ce19'] image=['autoware:universe-devel'] dds=['1eeef31e']
  A static duel                n=10  harness=['d57df9d'] patches=['7000c78'] buildid=['bc08ce19'] image=['autoware:universe-devel'] dds=['1eeef31e']
  A static non-duel            n=1   harness=['876b500'] patches=['7000c78'] buildid=['bc08ce19'] image=['autoware:universe-devel'] dds=['1eeef31e']
  A sweep 32ch                 n=9   harness=['55df5c1'] patches=['7000c78'] buildid=['bc08ce19'] image=['autoware:universe-devel'] dds=['1eeef31e']
  A sweep vlp16                n=9   harness=['51d27f2-dirty'] patches=['7000c78-dirty'] buildid=['bc08ce19'] image=['autoware:universe-devel'] dds=['1eeef31e']
  B-cyc EXCLUDED               n=6   harness=['55df5c1'] patches=['7000c78'] buildid=['bc08ce19'] image=['autoware@sha256:5c22369a'] dds=['(none)']
  B-cyc closed-loop duel       n=10  harness=['3fcd807'] patches=['7000c78'] buildid=['bc08ce19'] image=['autoware@sha256:5c22369a'] dds=['(none)']
  B-cyc closed-loop non-duel   n=1   harness=['876b500'] patches=['7000c78'] buildid=['bc08ce19'] image=['autoware@sha256:5c22369a'] dds=['(none)']
  B-cyc static duel            n=10  harness=['d57df9d'] patches=['7000c78'] buildid=['bc08ce19'] image=['autoware@sha256:5c22369a'] dds=['(none)']
  B-cyc sweep 32ch             n=9   harness=['4e195f6', '55df5c1'] patches=['7000c78'] buildid=['bc08ce19'] image=['autoware@sha256:5c22369a'] dds=['(none)']
  B-cyc sweep vlp16            n=9   harness=['51d27f2-dirty'] patches=['7000c78-dirty'] buildid=['bc08ce19'] image=['autoware@sha256:5c22369a'] dds=['(none)']
  CAL-seam static non-duel     n=5   harness=['7a3651b'] patches=['7000c78'] buildid=['None'] image=['none'] dds=['1eeef31e']
```

Read §9.2's table off the `harness=` column and §9.1's image confound (row P4-1)
off the `image=` / `dds=` columns. The walk abbreviates shas by `partition("-")`
rather than by slicing, deliberately: `sha[:7]` would silently drop the
`-dirty` suffix that `write_manifest.py:19-22` appends when the working tree
differed from HEAD — which is the one thing about these two keys most worth
surfacing, and which §8.2 and §9.2 both depend on being visible.

## 11. What P4 hands to P5/P6

### 11.1 Success criteria, against the spec's own list

| #   | criterion                                                                                                                          | status                                                                                                                                                                                                                                                               |
| --- | ---------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Registration wave complete and committed before the first measurement run; suite held; `pre-commit` clean                          | **MET.** Suite 1317 passed / 1 skipped at this wrap (effective — see the flake disclosure under section 10), against 1084/1 at the P3 wrap. `pre-commit run --all-files` clean. One historical lapse recorded in 8.2 (§26's claim at `b6fbc80`, fixed in `da1f6df`). |
| 2   | C1(a) measured: 5 valid CAL-seam runs, paired seam-vs-in-core table                                                                | **MET.** Section 5, reported as an upper bound per §11.9.                                                                                                                                                                                                            |
| 3   | A-vs-B-cyc static verdict computed once from ≥ 10 clean interleaved pairs, all five metrics computable, pool selected by `duel_id` | **PARTIALLY MET.** 10 clean pairs, zero exclusions, pool selected by `duel_id` — but `control_staleness_ms` is `insufficient-data` at n = 0/8 on this arm (2.4). Four of five computable.                                                                            |
| 4   | A-vs-B-cyc closed-loop verdict computed once from ≥ 10 valid pairs, or the failure branch recorded                                 | **MET.** 10 pairs, one invocation, zero exclusions, **all five** metrics computable (section 3).                                                                                                                                                                     |
| 5   | Amended M4 met per cell; E's exclusion recorded in wording                                                                         | **MET** on the second disjunct: the 32ch step-up executed and was adjudicated on both cells (6.3). E recorded.                                                                                                                                                       |
| 6   | Every number regenerates from committed raw data + scripts; the wrap carries the transcript                                        | **MET.** Section 10.                                                                                                                                                                                                                                                 |
| 7   | Branch pushed; draft PR opened; owner decides the flip; Plan 3 updated                                                             | **PARTIAL.** Branch pushed. **The PR is not opened** — that decision is the owner's and is asked for in 11.3. Plan 3's update is out of this task's file scope.                                                                                                      |

### 11.2 Open items P4 creates or leaves open

1. **The `carla_process_cpu_pct` direction reversal is unexplained** (2.5). The
   instrument that would address it is a **rate-matched** CPU comparison — cell
   A's registered `lidar_expected_hz` is 20.0 against B-cyc's 10.0 — plus a
   split of the image confound. Neither is in P4's registered scope. This is the
   single largest thing P4 discovered and did not resolve.
2. **The static-arm control-silence mechanism** (§19.4, §21.1). Settling it
   needs `/system/operation_mode/availability` and the diagnostic-graph output
   captured **across the pre-arm window**; both are outside the frozen
   five-topic observer set. `B-cyc/run-013` is the filed precedent showing where
   to look.
3. **C1(a)'s publish-order residual has an unestablished sign** (§11.9's
   correction). Establishing it would convert the upper bound into a point
   estimate. Reordering the two call sites changes the measurement and
   invalidates the pre-registered rule, so it cannot be done on this instrument.
4. **The in-core twin's drops-vs-skips ambiguity** is fixed for later cells but
   not for the CAL-seam pool (§13.4). A re-collection under the fixed launcher
   would close it; none is proposed here.
5. **The ceiling was not located.** The search stopped at `32ch` with `128ch`
   struck. Whether P5/P6 wants a further class is an owner decision, not a
   mechanical step-up.
6. **The A-vs-B closed-loop verdict under cell B's own transport remains
   non-computable**, and nothing in P4 changes that.

### 11.3 Standing questions for the owner

1. **Open the P4 PR, stacked on #29?** The branch is pushed. `gh pr create` was
   deliberately **not** run: the P4 PR's destination and stacking are the
   owner's call, and the campaign's own rule is that a child PR must be
   retargeted to `main` **before** the parent is squash-merged, or GitHub
   auto-closes it.
2. **Does the `carla_process_cpu_pct` reversal (11.2 item 1) warrant a P5
   instrument**, or is it recorded and left?
3. **Is "ceiling not located up to the 32ch class" the end of the M4 search**,
   or does P5/P6 want the `128ch` strike revisited? P4 did not revisit it and
   recommends it stay struck absent a fired disjunct.
