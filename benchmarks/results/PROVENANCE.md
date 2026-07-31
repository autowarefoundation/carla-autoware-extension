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
passes `--duel` on every `run.sh` invocation it makes (`duel.sh:213`) so the runs
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
(`duel.sh:220-222`). Neither failure was a cell failure: both were
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

This is a harness-pacing defect, not a property of either approach, and it was
**unresolved** as of this commit. `n` was therefore **1 per cell on the static
arm and 0 on the closed-loop arm**, far below the pre-registered `n >= 10`.
**Any equivalence verdict computed over this data would be computed at n = 1.**
**Amended 2026-07-31 (Task 18a): fixed** — see §3 below for the pacing that
Task 18a added to `duel.sh` so the duel can chain runs at all, and for pair
1's own inter-run gap, reconstructed after the fact since it predates the fix.

See `task-18-report.md` (outside this repo, with the campaign's other task
records) for the session preamble, the per-run integrity pass, the live
recorded-tree teardown verification, and the full localization of the abort.

---

## 3. Inter-run pacing amendment (Task 18a, dated 2026-07-31)

**Dated amendment, not a silent fix.** Inter-run host-idle time is a
measurement condition (duel.sh's own top comment, `duel.sh:7-22`: the
interleaving and per-pair order alternation exist to spread host drift evenly
across both cells), so introducing pacing between chained runs mid-campaign
changes that condition and must read as an amendment rather than a
transparent bugfix.

**Why.** §2 above records the mechanism: a completed run leaves the host well
above `preflight.sh`'s loadavg gate (`preflight.sh:28,67-69`, `MAX_LOADAVG=8`,
exclusions.md criterion 6), `duel.sh` chained runs with zero cooldown, and the
next run was refused before pair 2 could be filed. `MAX_LOADAVG` and criterion
6 are **not** changed by this amendment — relaxing the gate would tune a
measurement-validity condition to fit the measurement, and would silently
admit runs whose localization the load degrades. `duel.sh` gained pacing
instead.

**The measured basis.**

- Mean/peak loadavg left by a whole cell-B run, nothing else running on the
  box: mean **25.80**, peak **50.05**, on 24 cores (`benchmarks/README.md:
  1789-1797`).
- The live abort this task's predecessor hit: `hostload:26.52`, then
  `hostload:24.55`, two consecutive preflight refusals (§2 above,
  `duel.sh:220-222` for the abort itself).
- The post-run decay Task 18 measured by hand from that same host: 24.55 →
  13.74 after 38 s → 1.92 after 162 s, i.e. roughly 70–95 s of idle clears the
  gate from a freshly-completed run. This series is **not committed to this
  repo** — it is recorded in this task's own brief/report outside the repo
  (see the campaign's other task records), not here, so it is cited as such
  rather than given a false in-repo line number.

**The 120 s floor.** Fixed above the measured 95 s upper end of the decay
band, plus margin, so the common case never even reaches preflight before the
host has cleared the gate. A floor alone would still leave a run refused
outright on a worse-than-typical host (the measured peak, 50.05, is roughly
double the mean the 70–95 s figure came from), so `duel.sh` polls loadavg down
to a target under the gate (with its own margin, since the 1-min average can
still tick up between this script's read and preflight's own re-read moments
later) for up to a further bounded ceiling, and — this is the part that must
never regress — **proceeds regardless of whether the ceiling is reached**.
This campaign has six recorded cases of a correctness check refusing a
legitimate measurement; a pacing script that itself refuses, fails, or aborts
a run would be a seventh, self-inflicted this time. `preflight.sh` alone
judges whether a run may start. Full derivation and every knob:
`benchmarks/scripts/duel.sh:42-126`.

**Pair 1 predates this amendment.** `A/run-003` and `B/run-013` were filed by
a `duel.sh` with no pacing at all — the version at commit `289196e`. Their
inter-run gap is therefore not *recorded* the way every pair after this
amendment will be (`benchmarks/results/duel-pacing.log`, one line per paced
run). It is **reconstructed** instead, from the committed run artifacts, and
that distinction is deliberate: a reconstruction rests on a proxy and carries
resolution/coverage caveats a live recording does not, so it must not read as
the same kind of evidence.

Reconstruction, from committed byte content only (filesystem mtimes were
considered and rejected — see the note below):

- `A/run-003/resources.csv`'s **last row**'s `sample_system_ns` column (the
  host-resource sampler's own wall-clock stamp, `SAMPLE_INTERVAL_S=1.0` in
  `benchmarks/run.sh`) is `1785523733790041990`.
- `B/run-013/manifest.json`'s `started_at_ns` (written by
  `benchmarks/scripts/write_manifest.py:180`, at `run.sh` step 4, shortly
  after that run's own preflight completed) is `1785523765327599468`.
- The difference is **31.537557478 s ≈ 31.5 s**.

This is an **upper-bound proxy**, not the exact idle gap: `resources.csv`'s
last sample is when cell A's host-resource sampler was still running, some
time before `run-003`'s teardown actually finished, and `B/run-013`'s
`started_at_ns` lands after `run-013`'s own arg-resolution and preflight
steps, some time after `duel.sh` actually invoked it. The true unpaced idle
gap is therefore somewhat **smaller** than 31.5 s. Both endpoints are
plain-text fields inside git-tracked files (a CSV row, a JSON field), not
filesystem metadata — mtimes were rejected as a source because git does not
preserve them through a clone or archive, so a reconstruction resting on them
would not survive being reproduced from the committed history, which is what
"from the committed artifacts" is understood to require here.

For scale: 31.5 s is well under the 120 s floor this amendment now applies,
and under the 70–95 s decay band §"why" above cites. This is not a
contradiction — `A/run-003` is a **cell-A** (`extension`) run, and the
25.80/50.05 loadavg figures describe what **cell B**'s own, heavier stack
(~163 Autoware nodes, the tier4-native stack) leaves behind; the blocker this
amendment fixes was measured chaining a run **after a completed cell-B run**
(§2's pair-2 abort followed `B/run-013`, filed here, finishing), not after
`A/run-003`. `B/run-013`'s own preflight recorded `loadavg=4.46`
(`B/run-013/manifest.json`, `placement.loadavg`) — comfortably under the
gate — consistent with a 31.5 s natural gap being enough after a lighter
cell-A run, and consistent with the same gap being nowhere near enough after
a cell-B run, which is exactly what pair 2 hit.

Also for the record: `A/run-003`'s own `placement.loadavg` is `0.27` — this
duel started from an already-quiescent host, the "operator starts a duel from
a host they already know is quiescent" case `duel.sh`'s pacing-block comment
gives as the reason the floor is not applied before a duel's first run either.
