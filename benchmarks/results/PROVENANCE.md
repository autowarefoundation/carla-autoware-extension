# Primary duel (Task 18) — provenance of the committed A/B run data

**Written 2026-07-31 by Task 18**, the primary duel, at the moment its runs were
filed. Read this before citing any number out of the duel's runs.

Nothing under `benchmarks/results/*/run-*/` is modified by this document. Every
filed run's data is byte-identical to what was collected.

Scope. This file covers the runs Task 18 filed. Two neighbouring provenance
boundaries are stated elsewhere and are **not** restated here:

- `benchmarks/results/B/PROVENANCE.md` — cell B's binary-vs-pinned-source
  boundary (Task 17b), which governs `benchmarks/results/B/run-001…012`.
- `benchmarks/results/CAL-rmw/PROVENANCE.md` — the calibration cell.

---

## 1. The static arm reports a fabricated non-zero `publisher_drop_rate`

**This is a harness property, not an approach property, and it is disclosed
here rather than fixed.** The controller ruled it *carried* on 2026-07-31.

### What a reader must not conclude

Every static-arm run this task filed — **cell A and cell B alike** — will report
a **non-zero `publisher_drop_rate`** in the M2 reconciliation table for a
publisher that **dropped nothing**. Do not read that figure as a real
publisher-side loss. It is an artefact of when two teardown steps run relative
to each other.

### The mechanism, exactly

The finding was measured and documented before this task collected anything, on
Task 15b's cell-A control runs: see **`benchmarks/README.md:3793-3822`**, which
carries the arithmetic (`results/A/run-001`: window top 86.442 s, publisher
series end 85.391 s, gap +1.051 s, 21 scans at 20 Hz, in-window deficit
984 − 963 = 21, reported `publisher_drop_rate` 0.0213 — predicted 21 equals
observed 21).

The two code paths that produce it, cited at their **call sites**:

- **Where the window's upper bound is set.** For every arm that is not
  `closed-loop`, `_resolve_window` takes the static branch and calls
  `static_window(int(clock_wall.min()), int(clock_wall.max()), WARMUP_NS)` —
  `benchmarks/scripts/duel_verdict.py:324-326`. The upper bound is therefore
  the run's **last `/clock` sample**.
- **Where the publisher series is cut short of it.** `teardown.sh` stops the GT
  collector at **`benchmarks/scripts/teardown.sh:209`**
  (`stop_pid "${GT_PID:-}" "gt collector"`) and only afterwards SIGINTs the
  observer container at **`benchmarks/scripts/teardown.sh:222`**
  (`stop_container "$OBSERVER_CONTAINER"`). The GT collector is what writes
  `publisher_counts.json` (`benchmarks/scripts/collect_gt.py:412`); the observer
  is what writes `clock.csv`. So the publisher series ends **first**, and the
  in-window deficit is exactly the scans that fall in the gap.
- **Where the deficit becomes a rate.** `_reconcile_run`
  (`benchmarks/scripts/duel_verdict.py:787`) reconciles over that same resolved
  window and reads `publisher_counts.json` at
  `benchmarks/scripts/duel_verdict.py:845`; the field itself is
  `DropStats.publisher_drop_rate`, `benchmarks/analysis/cadence.py:20-21`.

The comment at `benchmarks/scripts/teardown.sh:192-207` states why the GT
collector is stopped early — it is the other process writing into the run
directory, and stopping the observer first would let a slow CSV flush trip the
clock watchdog and get a complete, healthy run excluded as `stall:clock`. The
ordering is deliberate and load-bearing for a different failure; that is why
reversing it is not a free fix.

### Its four bounding properties

1. **Symmetric across A and B.** Both cells run the same `teardown.sh` and the
   same `_resolve_window` static branch, so it should barely move the A-vs-B
   delta.
2. **Not a duel-margin metric.** It is a companion output of the M2
   reconciliation table, not one of the five pre-registered margin metrics.
3. **The closed-loop arm is immune.** That arm takes `_resolve_window`'s
   `spatial_window` branch (`benchmarks/scripts/duel_verdict.py:317-319`), which
   closes where the ego leaves the station band — ~80 s before the run ends.
   `results/A/run-002` reports 0.0000.
4. **Magnitude not recomputed here.** Quantifying it per run means running
   `duel_verdict.py`'s reconciliation, which the pre-registration reserves for
   the single verdict computation in Task 22. Task 18 discloses the mechanism
   and leaves the arithmetic to the run that is allowed to do it. The one
   worked example above (`results/A/run-001`) predates this task and is quoted
   from the README, not recomputed.

### Why it was not fixed

The correct fix — ending the static window at
`min(clock_wall.max(), publisher_end)` — is a formula change inside the frozen
`benchmarks/analysis/` tree, applied to a pre-registered metric's companion
output, mid-campaign. The smaller-looking alternative, reversing the two
teardown stops, trades a **quantified** defect for an **unquantified** one: it
moves flush ordering, which is what the comment at `teardown.sh:192-207` says
that ordering is protecting against. Task 18's obligation was disclosure, and
neither fix was attempted.

---

## 2. What the runs are, and why there are only two of them

Filed by `bash benchmarks/scripts/duel.sh A B --arm static --pairs 10`, which
passes `--duel` on every `run.sh` invocation it makes (`duel.sh:74`) so the runs
carry `duel_admissible=true`. Runs filed by this task are exactly:

| run         | arm    | `excluded` | `duel_admissible` | M5 `gate_pass` |
| ----------- | ------ | ---------- | ----------------- | -------------- |
| `A/run-003` | static | false      | true              | true           |
| `B/run-013` | static | false      | true              | true           |

Everything numbered below those belongs to earlier tasks and is untouched.
`B/run-013` is the **first non-excluded cell-B run in the campaign** and the
first cell-B **static** arm ever attempted (`B/run-001…012` are all
closed-loop and all excluded — see `benchmarks/results/B/PROVENANCE.md`).

**The duel stopped after pair 1**, at `duel.sh`'s 2-consecutive-failure abort
(`duel.sh:81-83`). Neither failure was a cell failure: both were
`preflight.sh` refusals on **`hostload:`** (26.52, then 24.55) because
`duel.sh` starts the next `run.sh` immediately and the 1-min loadavg left by
the previous run has not decayed below the gate's 8 (`preflight.sh:28,67-69`).
Both refusals happened at `run.sh` **step 3** (`run.sh:430`), before step 4
writes the manifest (`run.sh:445`), and `run.sh:12-14` states that "an abort
before step 4 leaves no run directory at all". Criterion 6 itself says the run
"is not started" (`benchmarks/config/exclusions.md:27-29`). So **no run
directory was created and no exclusion criterion was consumed**; verified
directly — `A/run-004` and `B/run-014` do not exist, and the next runs filed
will take those indices.

This is a harness-pacing defect, not a property of either approach, and it is
**unresolved** as of this commit. `n` is therefore **1 per cell on the static
arm and 0 on the closed-loop arm**, far below the pre-registered `n >= 10`.
**Any equivalence verdict computed over this data would be computed at n = 1.**

See `task-18-report.md` (outside this repo, with the campaign's other task
records) for the session preamble, the per-run integrity pass, the live
recorded-tree teardown verification, and the full localization of the abort.
