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
passes `--duel` on every `run.sh` invocation it makes (`duel.sh:283`) so the runs
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
(`duel.sh:290-292`). Neither failure was a cell failure: both were
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
**unresolved** as of this commit. `n` **is** therefore **1 per cell on the
static arm and 0 on the closed-loop arm**, far below the pre-registered
`n >= 10`. **Any equivalence verdict computed over this data would be
computed at n = 1.**
**Amended 2026-07-31 (Task 18a): the pacing defect is fixed** — see §3 below
for the pacing `duel.sh` gained so future duels can chain runs at all, and for
pair 1's own inter-run gap, reconstructed after the fact since it predates the
fix. **This amendment does not change `n`**: Task 18a filed no runs, so `n`
remains exactly as stated above — 1 per cell on the static arm, 0 on the
closed-loop arm — until a future task files more.

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
  `duel.sh:290-292` for the abort itself).
- The post-run decay Task 18 measured by hand from that same host: 24.55 →
  13.74 after 38 s → 1.92 after 162 s, i.e. roughly 70–95 s of idle clears the
  gate from a freshly-completed run. This series is **not committed to this
  repo** — it is recorded in this task's own brief/report outside the repo
  (see the campaign's other task records), not here, so it is cited as such
  rather than given a false in-repo line number.

**The 120 s floor is the uniform component.** Fixed above the **interpolated**
95 s upper end of the decay band (read off the two measured points above;
neither reading lands exactly at the gate value of 8, so 95 s is derived
between them, not itself a measured figure) plus margin, so the common case
never even reaches preflight before the host has cleared the gate. It applies
identically before every run after the first, regardless of which cell just
finished — the load-independent half of this amendment.

**The top-up that follows the floor is NOT uniform, and that is deliberate —
a correction to this section's first cut, which claimed the whole wait was
load-independent.** A floor alone would still leave a run refused outright on
a worse-than-typical host (the measured peak, 50.05, is roughly double the
mean the 70–95 s figure came from), so `duel.sh` polls loadavg — load-
TRIGGERED by construction, so its length can differ with which cell just ran
— down to a target under the gate (with its own margin, since the 1-min
average can still tick up between this script's read and preflight's own
re-read moments later) for up to a further bounded ceiling, and — this is the
part that must never regress — **proceeds regardless of whether the ceiling
is reached**. `duel.sh:7-22`'s own drift argument is about host state
(thermals, page cache, accumulated DDS shared memory), not clock time as
such, and host state at run start is exactly what `preflight.sh`'s gate
measures — equalising that is closer to the design's intent than equalising
idle seconds would be, so the residual is accepted as a bounded, disclosed,
per-run-recorded (`topup_s`) trade rather than removed. On the cited decay it
is expected to be **zero** in the typical case: 24.55·e^(−120/60) ≈ 3.3,
already under the target of 6 — so the wait actually paid in the typical case
is the uniform floor alone, and the top-up is insurance that is not expected
to fire. Because `topup_s` is recorded per run, a later analysis can check
whether it ever fired and whether it correlates with the preceding cell: a
disclosed, bounded, measured residual is a covariate, not a confound.

This campaign has six recorded cases of a correctness check refusing a
legitimate measurement; a pacing script that itself refuses, fails, or aborts
a run would be a seventh, self-inflicted this time. That holds on the ceiling
path by construction (it `break`s a poll loop, it never `die`s), and — after
this amendment's own fix round — on the I/O paths too: an unreadable loadavg
source or an unwritable pacing log are pacing-infrastructure faults, not run
failures, and now warn to stderr and proceed rather than tripping `set -e`
into an abort that would otherwise masquerade as this script's own "some runs
failed" exit-1 status (§2 above). `preflight.sh` alone judges whether a run
may start. Full derivation and every knob: `benchmarks/scripts/duel.sh:42-161`.

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

---

## 4. The static arm completed: n = 10 per cell, and what those runs do and do not support

**Written 2026-07-31 by Task 18**, resuming after Task 18a cleared the pacing
blocker. §2 above described the state at `289196e`, when the abort had left
n = 1; that section is left as written and this one supersedes its `n` figures.

`bash benchmarks/scripts/duel.sh A B --arm static --pairs 9` filed pairs 2–10:
**A 9 ok / 0 failed, B 9 ok / 0 failed**, no preflight refusal, no exclusion, no
abort. With pair 1 the static arm now holds:

| cell | filed | non-excluded | M5 `gate_pass` = true | M5 unscoreable |
| ---- | ----- | ------------ | --------------------- | -------------- |
| A    | 10 (`run-003…012`) | **10** | **10** | 0 |
| B    | 10 (`run-013…022`) | **10** | **1** (`run-013`) | 1 (`run-019`) |

Every one of the twenty is `duel_admissible=true`, has a valid manifest, has no
watchdog stall marker, and renders through `report.py`'s strict path.

### 4.1 Cell B's nine gate-failing runs are retained, unexcluded, and disclosed

Nine cell-B static runs fail the M5 gate, and all nine fail it on the **same
named reason**: `ndt rate ratio <r> < 0.9`, with `r` between **0.257 and 0.850**
against cell B's registered `ndt_expected_hz` of 10.0. The tenth,
`run-019`, could not be scored at all — `write_quality` refused, loudly and by
name, at `run.sh` step 13:

```
QUALITY GATE FAIL: evaluate_quality could not score run-019 over the window
[50207676168, 99905759634] sim ns: fewer than 10 NDT<->GT stamp pairs in the
window (found 2)
WARN: the M5 gate did not score .../B/run-019 (named reason above);
      no quality.json is written, so its consumers fail loudly
```

That is the harness working as designed, not a harness defect: it declined to
write a `quality.json` it could not justify, said why, and let step 15's smoke
still verify the run renders. `run-019` therefore carries **no** `quality.json`,
and any consumer that needs one will fail loudly rather than read a fabricated
score. The named reason is quoted here because it is otherwise only on the duel
driver's console.

**The proximate measurement is observer-side message count, not window length.**
All ten windows span 49.3–51.7 s, i.e. uniform; what differs is how many
`/localization/pose_estimator/pose_with_covariance` rows the observer recorded
inside them — **63 to 695** across the ten runs (`run-016`: 63; `run-013`: 695).
A ~50 s window at 10 Hz offers ~500. So the loss is in delivery, not in
windowing or in the gate's arithmetic.

**This is the condition the campaign has already registered, and its handling is
already ruled on.** Cell B's transport is `rmw_fastrtps_cpp` with
shared memory **off** (`benchmarks/observer/config/udp_only.xml`), and:

- `benchmarks/README.md:3824-3849` registers the A-side instrument-asymmetry
  bound — cell A loses **0.0000** where cell B loses **0.2564 / 0.1715** — and
  concludes "the loss is a property of cell B's SHM-off Fast-DDS transport",
  corroborated three independent ways (Autoware's own `PublishedTime`, Task 9's
  transport matrix, and cell A's zero loss on a different transport).
- `benchmarks/results/CAL-rmw/PROVENANCE.md:151-165` states that **"No
  registered exclusion criterion covers this condition, and that absence is part
  of the record rather than something to paper over"**, that **"A criterion is
  deliberately NOT being added"**, and carries **Owner ruling 2026-07-31: retain
  all fifteen runs as produced, with no exclusions, and disclose.** Its
  independent bring-up corroboration at
  `benchmarks/results/CAL-rmw/PROVENANCE.md:176-181` measures the same transport
  at **0.333–6.156 Hz** against cyclonedds' **10.008–10.010 Hz**, from a second
  rclpy subscriber on the same RMW.

**Task 18 applied that ruling unchanged.** The nine gate-failing runs and the
one unscoreable run are **retained as produced, with no exclusions**. No
exclusion reason was invented, no criterion was added or edited, and the M5
gate's 0.9 threshold was not touched. The losses here (down to a ratio of
0.257) run **worse** than the 0.17–0.26 the README bounds, so the disclosure is
that the registered condition is present in the primary duel's cell-B static
data **at a larger magnitude than the bound anticipated** — not that a new
condition was found.

**What this means for reading the data — stated, not resolved:** three of the
five pre-registered duel margin metrics are observer-derived
(`README.md:3838-3841`), and `achieved_rate_ratio`'s margin is 0.02 against a
loss here of up to 0.74. Whether cell B's static runs can carry an equivalence
verdict on the observer-derived metrics is **not** decided here — Task 22 owns
the verdict, and this section exists so that it decides with the condition in
view. No verdict, delta, median or A-vs-B comparison was computed by Task 18.

### 4.2 Reading `duel-pacing.log`: its pair numbers are per-invocation

`benchmarks/results/duel-pacing.log` holds **17 lines**, one per paced run, and
is committed as evidence. Two cautions, both of which will silently mislead:

- **`before_pair=`/`before_cell=` name the run the wait PRECEDES**, not the run
  that just finished (`duel.sh`'s own note at the log write).
- **The pair numbers are the numbers of the *invocation*, not of the duel.**
  These 17 lines come from a `--pairs 9` invocation that filed the duel's pairs
  **2–10**, so a line reading `before_pair=1` precedes the duel's **pair 2**.
  The duel's pair 1 (`A/run-003`, `B/run-013`) is **absent** from this log
  entirely: it predates the pacing (§3), and its gap is the ~31.5 s
  reconstruction in §3, not a recorded line. Join on `ts` against each
  manifest's `started_at_ns` rather than trusting `before_pair`.

Recorded behaviour, for whoever checks whether the top-up ever fired: floor
120 s on all 17 gaps; **top-up fired on 5 of 17** (5, 10, 15, 15, 20 s);
**the 300 s ceiling was never reached**; `loadavg_end` 0.53–5.72, always under
the target of 6; total pacing wait **2105 s ≈ 35.1 min**. §3 expected the
typical top-up to be zero, and it was zero on 12 of 17 gaps — but it is **not**
uniformly zero, so §3's "insurance that is not expected to fire" is correct as a
central tendency and wrong as an absolute.

### 4.3 One design property the abort cost, disclosed

`duel.sh` alternates which cell takes a pair's first slot so that neither cell
always pays the cold-cache cost (`duel.sh:14-22`). Within a single `--pairs 10`
invocation that splits 5/5. Because the duel was filed as `--pairs 10`
(aborted after pair 1) plus `--pairs 9`, and every invocation starts its own
pair 1 with cell A, the realised split over the ten static pairs is **A first in
6, B first in 4** — not 5/5. It is a one-slot imbalance introduced by the abort,
not by a design change, and it could not be corrected afterwards without
re-running filed pairs. Recorded so it is not mistaken for the balanced design.

---

## 5. LIVE DEFECT FOUND: the cell-B recorded-tree teardown silently skipped the whole Autoware stack on 5 of 10 runs

**Found 2026-07-31 by Task 18** during brief §F1's live verification — the
verification Task 16 and Task 17c both deferred because neither could run
against a real stack. This is what it was for.

### 5.1 What happened

On **5 of the 10** cell-B static runs, `scripts/e2e/stop_launch_tree.sh`
signalled **nothing** for the Autoware launch tree and left **56 processes
running inside the container**, while reporting **`0 survivor(s)`**:

| runs | recorded tree | survivors reported | container after the stop |
| ---- | ------------- | ------------------ | ------------------------ |
| `run-013`, `014`, `015`, `016`, `018` | **55** processes | 0 | **3 running**, 3–4 defunct |
| `run-017`, `019`, `020`, `021`, `022` | **2** processes | 0 | **56 running**, 2 defunct |

`0 survivor(s)` is technically true and materially misleading: survivors are
counted against the *recorded* tree, and on the bad runs the recorded tree was
only the 2-process concat relay. **The `container now:` count is the only thing
that reveals it** — the count Task 17c deliberately put in that message. It
earned its place today.

### 5.2 Root cause: a racy sidecar write makes the pid-reuse guard misfire

The guard is correct; the data it is given is not. From `run-022`'s own
`tier4-stop-launch-tree.log`:

```
stop: SKIPPING /tmp/tier4-autoware.pid -- pid 121 was REUSED. Recorded at launch as
stop:   'nohup ros2 launch autoware_launch e2e_simulator.launch.xml ... '
stop:   but pid 121 is now '/usr/bin/python3 /opt/ros/humble/bin/ros2 launch autoware_launch e2e_simulator.launch.xml ... '
stop:   Nothing was signalled; the process this pid file named is already gone. Pid file kept.
```

Those two cmdlines are the **same process before and after `ros2`'s own exec**,
not a reused pid. `benchmarks/cells/tier4_autoware.sh:402-408` launches
`nohup ros2 launch …`, records `$!`, and then writes the sidecar by reading
`/proc/$pid/cmdline` on the very next line. That read **races the exec**: `ros2`
replaces the `nohup ros2 launch …` image with
`/usr/bin/python3 /opt/ros/humble/bin/ros2 launch …` in place, keeping the pid.

- Sidecar read loses the race → post-exec cmdline recorded → matches at
  teardown → tree stopped (55 processes).
- Sidecar read wins the race → **pre-exec** cmdline recorded → mismatches at
  teardown → `stop_launch_tree.sh:329-341`'s guard declares pid reuse, returns
  0 without signalling, and the stack is left up.

A tight race, which is why it split 5/5. The guard itself
(`stop_launch_tree.sh:323-341`) behaves exactly as its comment says it should
given a mismatching sidecar; the defect is at the write site, not the read site.

### 5.3 Blast radius: real, bounded, and it did NOT invalidate any run

Stated precisely, because §F1 warns that a teardown which does not clear the
tree invalidates later runs in the session, and **here it did not**:

- **No measurement was affected.** Teardown runs after the scoring window
  closes, so a stack left up at teardown cannot touch the run's own data.
- **No leak across runs.** `teardown.sh` removes the Autoware container
  (`docker rm -f`) immediately after, which kills all 56. Verified after
  `run-022` (a bad run): container absent, `ros2 node list` **0 nodes**, no
  CARLA/UE processes, port 2000 free.
- **No downstream refusal.** Every subsequent run's preflight passed; no run in
  the session was refused on `hostload:` or filed with any exclusion.
- **What was actually lost** is the graceful shutdown: on those 5 runs the
  SIGINT ladder never ran and a 56-process Autoware stack was SIGKILLed by
  container removal — precisely the ungraceful shutdown `stop_launch_tree.sh`
  exists to prevent, on the family Task 17c wired it into.

### 5.4 Not fixed here, and independent of §4.1

**No fix was attempted.** The defect is in a launcher (`tier4_autoware.sh`) that
files every cell-B run in the campaign; changing how a run is launched
mid-measurement changes the measured configuration, and this task's remit was to
verify the teardown, not to re-cut it. Reported for the owner to schedule.

**It does not explain §4.1's NDT loss and is not correlated with it.** The
gate-failing runs span both groups (bad-teardown group ratios 0.383–0.818 and
one unscoreable; good-teardown group 0.257–0.989), and the single passing run
(`run-013`, 0.989) is in the good-teardown group alongside the worst failure
(`run-016`, 0.257). Two independent findings, and neither is evidence for the
other.

## 6. Phase 0 harness re-verification: FINAL RULING = branch (c), reached in three stages

> **THE FINAL, ACTIONABLE RULING IS §6.7. READ IT FIRST.**
>
> This section records the whole arc, in order, because two of its stages were
> superseded and the campaign's convention is that superseded rulings stay in
> the record with the diagnostics that superseded them:
>
> | Stage | What it says | Status |
> | --- | --- | --- |
> | §6.1–§6.4 (2026-07-31) | Branch (c), ruled on P1's publisher **count** | **superseded reasoning** — do not act on §6.3's list |
> | §6.5 (fix round 1) | The count did not measure double *publication*; BLOCKED | **superseded by the owner's ruling to resume**, and its measurement stands |
> | §6.6 | A refuted premise in cell A's launcher, annotation deferred | current |
> | **§6.7 (fix round 2)** | **FINAL: branch (c), ruled on P3 + P4 as pre-declared** | **ACT ON THIS** |
>
> The final branch is the same letter the first stage reached, but it is
> **not** the same ruling: the first rested on a criterion that measured the
> wrong quantity, and the final rests on the spec's own P3 and P4 with their
> pre-declared thresholds. That distinction is the point of keeping both.

The P3 completion plan opens with a live decision gate. Its hypothesis, its four
probes with their predicted outcomes, and three adjudication branches were
pre-declared in `specs/2026-07-31-p3-completion-design.md` **before any
measurement existed**. The full transcript — pre-declaration copied verbatim
*above* the measurements — is committed at
`benchmarks/evidence/p3-phase0/probe-transcripts.md`, with per-figure retention
status in that directory's `PROVENANCE.md`.

**Hypothesis under test.** Cell B's depressed NDT rate is caused by double
publication on `/sensing/lidar/concatenated/pointcloud` (the harness relay plus
tier4 `concatenate_data`), **absent on cell A** (relay only).

### 6.1 Probe summary

| Probe | Predicted (pre-declared) | Measured | Outcome |
| --- | --- | --- | --- |
| **P1** — cell A publisher census on `/sensing/lidar/concatenated/pointcloud` | **1**, `//relay` | **2 advertisers** — `/sensing/lidar/concatenate_data` **and** `//relay` — but only **1 emitter** (§6.5) | **failed on advertisement count; MET on emission** (see §6.5: the count is not the quantity the hypothesis names) |
| **P2** — cell B, same census | **2** — `//relay` and `/sensing/lidar/concatenate_data` | **2** — `/relay` and `/sensing/lidar/concatenate_data`, reproducing the `results/B/run-012` record | prediction held |
| **P3** — concat output usable with the relay stopped | — | **not run** | decisional role removed by P1 |
| **P4** — NDT rate with the relay stopped, vs 0.9 × the registered `ndt_expected_hz: 10.0` = 9.0 Hz | recovery, if the hypothesis were true | **not run**; the relay was never killed | same |

Diagnostic runs: `A/run-013` and `B/run-023`, both launched without `--duel`
(`duel_admissible: false`), both completing a full 60 s static window with no
exclusion. They are bring-up-class runs; **no A-vs-B comparison is drawn from
them and none may be.**

**What the refutation rests on, and the gap in it.** P1's pre-declared criterion
is a publisher **count**. A count cannot distinguish a publisher that
*advertises* from one that *emits*, and the spec's hypothesis names double
**publication**. So the refutation below holds only if cell A's second
publisher is actually emitting. That gap was recorded as an open question when
the ruling was made, and it has since been measured: **it does not hold.** See
§6.5.

### 6.2 Ruling: branch (c)

*(Recorded as it stood at ruling time. **Superseded** — its reasoning by §6.5,
its status by §6.7's final ruling. Kept unedited, with what superseded it
attached, rather than rewritten.)*

The hypothesis is explicitly *differential* — it explains cell B's depressed
rate **by** a difference from cell A. P1 measured the same double publication on
cell A, whose filed `ndt_rate_ratio` is ≈ 0.99999998 across 12 runs. The alleged
cause is present where the alleged effect is absent, so it is not the cause. The
spec assigned this outcome its consequence in advance — *"Two publishers here
refutes the hypothesis (the probe can kill it, deliberately)"* — and branches
(a) and (b) are both fix branches predicated on a harness fault that is now
unestablished. **Branch (c) is the ruling.**

No fourth branch was invented, no branch reshaped, and no prediction softened
after the fact.

**Corrected in fix round 2:** describing P1's prediction as simply "FAILED" was
itself imprecise, and the imprecision is the crux of this whole correction. P1
predicted **one publisher** and measured **two advertisers but one emitter**. It
therefore failed on advertisement count and was **met on emission** — and
emission is the quantity the hypothesis names. Reading the failure as a
refutation is what produced the superseded ruling below.

### 6.3 What follows, and what explicitly does not

*(Recorded as it stood at ruling time. **Do not act on this list** — it was
suspended by §6.5 and is superseded by **§6.7**, which reaches the same branch
on the correct probes and restates the consequences. Act on §6.7.)*

Branch (c) prescribes no harness edit and no reclassification. Therefore:

- `benchmarks/cells/tier4_autoware.sh`'s relay is **unchanged**, and its "THAT
  PREMISE IS REFUTED" comment block stays as written, per the convention that
  refuted hypotheses stay in the record with the diagnostics that refuted them.
- **No** `harness:<commit>` reclassification of B `run-013…022` under
  `exclusions.md` criterion 3. Those runs stay filed and unexcluded, exactly as
  §4.1 above rules.
- **No** 10-fresh-pair static recollection — the spec conditions it on branch
  (a)/(b).
- **No `duel_admissible` flip on A `run-003…012`.** The spec's "Consequence of
  (a)/(b) for the A pair-halves" paragraph is conditioned on branches (a)/(b)
  and does not fire. The A static pair-halves keep `duel_admissible: true`.
  Recorded explicitly so no later task applies that paragraph by reflex.

**Nothing here is a gate adjustment.** No threshold moved, no run was excluded,
no harness was tuned. Cell B's M5 failures stand and the verdict will carry
them. The single thing that changed is that one candidate explanation for those
failures is now measured to be false — which is a subtraction from the space of
explanations, not an adjustment to the measurement.

### 6.4 The pre-existing registered confound is unaffected

Branch (c) asks that the depressed rate be registered as a measured confound
with the Phase 0 diagnostics attached. It already is, and this session did not
find a new one. **Phase 0 measured nothing that bears on whether that registered
confound is a complete causal account of cell B's depressed rate, and this
section makes no such claim** — an earlier wording here ("the confound that
*remains*") asserted an exhaustiveness Phase 0 did not measure and is corrected.
What the registered confound is, and what backs it:

- `benchmarks/README.md`'s A-side instrument-asymmetry bound: `observer_loss_rate`
  **0.0000** on cell A against **0.2564 / 0.1715** on cell B, concluding "the
  loss is a property of cell B's SHM-off Fast-DDS transport".
- `benchmarks/results/CAL-rmw/PROVENANCE.md`: the same transport at
  **0.333–6.156 Hz** against cyclonedds' **10.008–10.010 Hz**, under **Owner
  ruling 2026-07-31: retain all fifteen runs as produced, with no exclusions,
  and disclose.**
- §4.1 above, which applied that ruling unchanged to cell B's static runs.

Phase 0 adds an independent fourth observation of the same transport property,
on a different quantity — DDS **graph discovery** rather than sample delivery.
On cell B a `--no-daemon` census returned nothing, then 1 publisher with
`_NODE_NAME_UNKNOWN_`, and `ros2 node list --no-daemon` found neither the relay
nor `concatenate_data` while the relay process was alive at pid 437; the settled
daemon then resolved both out of a 162-node graph. **This is the opposite
polarity of the stale-daemon trap `benchmarks/run.sh:789` documents**, it is
specific to cell B's transport (cell A's cyclonedds censuses agreed with and
without the daemon), and on that transport a CLI graph query must be given time
to discover before its count means anything.

### 6.5 Fix round 1 — P1's count criterion did not measure double PUBLICATION (this stage returned BLOCKED)

Fix round 1 (2026-08-01) closed the open question flagged in §6.1. It is
decision-relevant, and it goes against the ruling.

**Measured on a third diagnostic cell-A stack** (`A/run-014`, `--arm static`,
no `--duel`), with the publisher census and the flow measurement taken against
the **same stack state** so the two cannot be about different moments:

| Quantity | If both publishers emit | Measured |
| --- | --- | --- |
| `RELAY_OUT` / `RELAY_IN` message ratio | ≈ 2.0 | **0.995** (398 / 400) |
| `RELAY_OUT` header stamps absent from `RELAY_IN` | > 0 | **0** |
| `RELAY_OUT` duplicate header stamps | > 0 | **0** |
| Aggregate `ros2 topic hz` on `RELAY_OUT` | ≈ 40 Hz | **19.957 Hz**, vs `RELAY_IN` **19.960 Hz** |
| Publisher count, same stack state | 2 | **2** |

`topic_tools relay` forwards verbatim, so every message it emits carries a
stamp that also appeared on `RELAY_IN`; a second emitting publisher would show
up as unmatched stamps, duplicate stamps, or a doubled rate. None is present.
**Every message on `/sensing/lidar/concatenated/pointcloud` is a relay forward.
Cell A's `concatenate_data` holds an advertised publisher and contributes zero
traffic.** The instrument's own bias (subscriber-side BEST_EFFORT sampling)
points toward this same conclusion, so it cannot have manufactured it; the
independent `ros2 topic hz` reading is what rules the bias out.

**Consequence.** The spec's hypothesis names double **publication**. Cell A has
two publish*ers* and one publish*er emitting*, so P1's count of 2 is a true
measurement of something the hypothesis does not name. The differential the
hypothesis rests on — double publication present on B, absent on A — is
therefore **not refuted by P1**, and branch (a) or (b) may be correct.

**This was escalated as an owner decision rather than re-adjudicated here.**
It has since been taken — see §6.7. Re-adjudicating at this stage
would mean reshaping the spec's branch table against its own pre-declared
criterion after seeing data, which is what the pre-declaration exists to
prevent. The decision needed is whether P1's count criterion stands as written
(branch (c) holds) or is superseded by a publication-based criterion (Phase 0
re-runs from P2, executing the P3/P4 kill probes that were skipped on the
strength of P1).

**Nothing was destroyed by this outcome.** No relay was ever killed on either
cell, no run was excluded or reclassified, no `duel_admissible` flag was
flipped, and no harness file was edited. Re-running Phase 0 from P2 costs two
live runs and no recollection. All three diagnostic runs (`A/run-013`,
`B/run-023`, `A/run-014`) stay filed, unexcluded, `duel_admissible: false`.

### 6.6 A refuted premise in `scripts/e2e/launch_autoware.sh`, annotation deferred

`scripts/e2e/launch_autoware.sh:44-47` (cell A's relay, a different file from
the cell-B relay at `benchmarks/cells/tier4_autoware.sh:538`) asserts:

> (The concat node is left with its stock 3-topic config; it stays silent with
> a single publisher, so the relay is the sole publisher on the concatenated
> topic -- verified live after bring-up.)

and above it, that the node "HARD-REQUIRES >= 2 input topics … and never loads".

**P1 measured both claims false on cell A**: `concatenate_data` *does* load and
*does* advertise a publisher on `/sensing/lidar/concatenated/pointcloud`, so the
relay is **not** the sole publisher there. §6.5 then measured the part the
comment gets right in substance though not in mechanism: the node is indeed
**silent** — it emits nothing — but it is silent *while holding a publisher*,
not by failing to load.

**The in-file annotation is deliberately deferred to the P3 wrap task**, on the
owner's ruling: cell A is about to carry hours of live duel collection, this
branch has a documented citation-drift class that has already fired seven times,
and line-shifting that file now risks live runs while buying nothing, since the
record is what later tasks read. The finding is therefore registered here, and
the annotation is scheduled for after all live collection completes. The
cell-B-side counterpart comment (`tier4_autoware.sh`'s "THAT PREMISE IS
REFUTED") already carries its own refutation in place and needs no change.

### 6.7 FINAL RULING (fix round 2, 2026-08-01): branch (c), on P3 and P4 as pre-declared

**Owner ruling that reopened the protocol**, recorded because it is what makes
this stage legitimate rather than a second bite at the adjudication:

> **RESUME Phase 0 at P3/P4.** Not "honor the literal count criterion", not
> "re-run the whole session from P2". P3 and P4 are pre-declared in the spec
> with pre-declared thresholds and can still land on (c), so running them shapes
> no outcome — it completes a protocol that was short-circuited by an instrument
> measuring the wrong quantity. In publication terms, cell A has exactly the one
> emitter P1 predicted, so the differential is intact and the hypothesis is live
> again.

Four cell-B diagnostic runs, `--arm static`, no `--duel`, all filed and **none
excluded**: `B/run-024` (emission census, P4 pre-kill, the kill, post-kill
census), `B/run-025` and `B/run-026` (P4 post-kill, the second with
`PYTHONUNBUFFERED=1` to rule out a block-buffering artifact), `B/run-027` (P4
across the kill on an already-discovered subscriber, plus the full P3 cloud
characterisation). Raw output for all of it is in
`benchmarks/evidence/p3-phase0/probe-transcripts.md` §11.

#### The differential IS real — cell B has two emitters, cell A has one

Same stamp-identity instrument on both cells, so they are measured by one rule:

| Quantity | Cell A (`run-014`) | Cell B (`run-024`) |
| --- | --- | --- |
| Advertised publishers on `RELAY_OUT` | 2 | 2 |
| `RELAY_OUT`/`RELAY_IN` message ratio | 0.995 | **1.818** |
| `RELAY_OUT` **duplicate** stamps | **0** | **72** of 88 unique |
| `RELAY_IN` stamps absent from `RELAY_OUT` (loss symmetry) | 2 (= count diff) | **0** |
| **Emitters** | **1** | **2** |

The 0/0 loss symmetry rules out the probe's own dropped samples, and the excess
is entirely duplicate stamps — `concatenate_data` republishing the relay's input
clouds under the input's own stamp. So fix round 1's correction stands and the
hypothesis had a real differential to rest on.

#### The probe table, against the spec's thresholds

| Probe | Predicted (pre-declared) | Measured | Outcome |
| --- | --- | --- | --- |
| **P3** — concat output usable, relay stopped | — | `frame_id` **`base_link`**, `width` **6202** (6198 / 6254 on two other runs), `point_step` **16**, `row_step` 99232, `is_dense` true, fields x/y/z/intensity/return_type/channel, topic steady at **7.612 Hz** | clouds **usable** — (b)'s trigger NOT met |
| **P4** — NDT rate, relay stopped, vs **≥ 9.0 Hz** (0.9 × registered 10.0) | recovery, if the hypothesis were true | **0.000 Hz** on three independent runs; pre-kill with both emitters **4.830 Hz** (ratio ≈ 0.48) | **no recovery** — (c)'s trigger MET |

- **(a) Recovery** — needs P4 ≥ 9.0 Hz. Measured 0.000. **Not selected.**
- **(b) Concat output unusable** — trigger is *"P3 fails: empty/malformed
  clouds"*. The clouds are neither. **Not selected.**
- **(c) No recovery** — trigger is *"P4 stays < 0.9 with a single publisher"*.
  Measured 0.000 post-kill, 0.48 pre-kill. **SELECTED.**

#### What is and is not concluded

The differential is real; it is **not the cause**. Removing the second publisher
does not move NDT's rate toward 10 Hz — it stops NDT entirely — and the rate was
already 0.48 of expectation while both publishers ran. The hypothesis names
double publication as the *cause*, P4 is the test of causation, and it fails.

**Fix mechanism for Task 2: NONE.** Branch (c) prescribes no harness change.
Not relay-removal (a) — the relay is load-bearing, and killing it is what takes
NDT to zero. Not concat-suppression (b) — its trigger is not met, and the
measured 0.48 pre-kill rate shows that suppressing the second publisher would
not reach the 0.9 gate either. `benchmarks/cells/tier4_autoware.sh:538` stays
exactly as it is, comment block included.

Consequences, all as pre-declared for (c): no `harness:<commit>`
reclassification of B `run-013…022` under `exclusions.md` criterion 3; no
10-fresh-pair static recollection; **no `duel_admissible` flip on A
`run-003…012`** — the spec conditions that on branches (a)/(b), which did not
fire, so the A static pair-halves keep `duel_admissible: true`. No gate was
tuned, no threshold moved, no run excluded, no harness file edited. Cell B's M5
failures stand and the verdict carries them.

#### Two things a later task must not misread

1. **NDT on cell B stops on its own.** On `run-027` the bucketed rates show NDT
   at 1.600 Hz for 10 s and then 0.000 Hz from t≈10 s — twelve seconds *before*
   the kill completed. `B/run-025` and `B/run-026` were both **unscoreable** by
   the M5 gate (too few NDT↔GT stamp pairs, the same class as the filed
   `B/run-019`), and `run-027` scored `ndt_rate_ratio=0.039`. The post-kill zero
   is carried by `run-025`/`run-026`; `run-027` carries P3.
2. **An unproven mechanism, flagged as unproven.** `concatenate_data` republishes
   under stamps the relay already used (72 duplicates). A chain that
   de-duplicates or time-filters on header stamp would drop such a stream while
   the clouds themselves look sane — consistent with P4, but **not tested and
   not evidence**. It is a hypothesis for whoever picks the question up, not a
   finding.
