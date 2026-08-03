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

> **COUNT CORRECTED — it is EIGHT, not nine. See §10.3, "COUNT CORRECTION".**
> This heading and the paragraph below say "nine"; recomputed from every
> `quality.json` on 2026-08-01, the ten duel-admissible cell-B static runs split
> **1 pass (`run-013`, 0.9892) / 8 fail (0.2569–0.8505) / 1 unscoreable
> (`run-019`)**. The table two paragraphs above already recorded
> `M5 gate_pass = true: 1 (run-013)`, so the two never agreed. Both are left as
> written, per the convention that a claim stays in the record with the
> diagnostic that corrected it — this pointer is how a reader reaches that
> diagnostic without having to find it 2 400 lines away. Reproduction command:
> `docs/evaluation/p3-baseline.md` §5.2.

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
> | **§6.7 (fix round 2)** | **FINAL: branch (c), ruled on P3 + P4 as pre-declared** | **ACT ON THIS** — its causal wording corrected by §6.8 |
> | §6.8 (fix round 3) | P4 selects (c) by **elimination**; the post-kill zeros are unattributed and NDT resumed on `run-027` | current — read with §6.7 |
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

**CLOSED 2026-08-01 by the P3 wrap (§10.3).** All live collection completed, so
the annotation landed: `scripts/e2e/launch_autoware.sh:48-71` now carries the
refutation of both claims, comment-only, with no executable change. The original
claim at `:44-47` is kept exactly as written, per the convention that a claim
stays in the record with the diagnostic that corrected it. The insertion shifted
the file's later line numbers by 24, and every in-repo citation that shifts
with it was corrected in the same commit and each re-verified against its new
target: `benchmarks/scripts/teardown.sh:100` (`:89-94` → `:113-118`,
`compose_exec_script`), `benchmarks/cells/tier4_autoware.sh:438` and
`scripts/e2e/stop_launch_tree.sh:90` (`:185-233` → `:209-257`, the pid-file
write plus its Task-18b settle loop) and
`tests/e2e/test_stop_launch_tree.py:148,362` (`:219-233` → `:243-257`, read at
`:221` → `:245`). Every edited file took a **comment-only** change; no
measured configuration moved. `benchmarks/evidence/p3-phase0/probe-transcripts.md`'s
`:46` and this section's own `:44-47` sit above the insertion and are unaffected.

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

> **THE TWO CAUSAL SENTENCES BELOW ARE OVERSTATED AND ARE CORRECTED IN §6.8.**
> They are kept unedited because the campaign's convention is that a claim stays
> in the record with the diagnostic that corrected it. In short: P4 selects (c)
> by **failing to demonstrate recovery**, not by demonstrating that killing the
> relay stops NDT — the repo's own `results/B/run-027/observer.csv` shows NDT
> **resuming** with `concatenate_data` as sole publisher. **The branch ruling is
> unaffected**; only the causal wording is.

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

*(Corrected reading of the same two points, per §6.8: (a) is not selected because
**no run demonstrated recovery to ≥ 9.0 Hz** — the best post-kill reading on any
of the four runs is ≈ 0.07 Hz, two orders of magnitude short; the further claim
that the relay is load-bearing is **not established** by these runs. (b) is not
selected because its trigger is genuinely unmet — P3 passed. The fix mechanism —
**NONE** — is unchanged, and so is every consequence below.)*

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

### 6.8 LIMITATION (registered 2026-08-01): P4 selects (c) by ELIMINATION, not by a demonstrated mechanism

This is the **same class of error as the count-vs-emission correction in §6.5**,
in a new place, and the record says so rather than treating it as a wording
nit: §6.7 claimed more than its measurement carries. There it was a probe
measuring a different quantity from the one the hypothesis names; here it is a
causal claim resting on readings that cannot support it.

#### The measured fact that refutes the causal claim

`benchmarks/results/B/run-027/observer.csv` — the run's own filed observer
stream, not a re-derivation — records NDT **resuming after the kill**, with
`concatenate_data` as the **sole** publisher on `RELAY_OUT`:

| arrival (UTC) | event |
| --- | --- |
| 14:03:39.632 | last NDT pose **before** the kill |
| ≈ 14:03:54 | relay kill completes (SIGTERM → SIGKILL escalation) |
| **14:04:23.537** | **NDT pose — ≈ 29 s AFTER the kill, relay gone** |
| **14:04:24.292** | **NDT pose** |
| 14:04:24.537 | observer stream ends (teardown) |

Recomputable:

```bash
python3 - <<'PY'
import csv, datetime
rows = [r for r in csv.DictReader(open("benchmarks/results/B/run-027/observer.csv"))
        if "pose_estimator/pose_with_covariance" in r["topic"]]
for r in rows[-4:]:
    ns = int(r["arrival_system_ns"])
    print(datetime.datetime.fromtimestamp(ns / 1e9, datetime.UTC).strftime("%H:%M:%S.%f")[:-3])
PY
```

**Why the probe read 0.000 Hz anyway:** `probe_relay_kill_transition.py`'s
observation window closed at **14:04:19Z** — **4.2 s before** the first
resumption sample. The zero is a **window artifact**, not an absence. That is
evidence against the reading this task itself published, and it belongs in the
record with the diagnostic that produced it.

#### The structural gap: no run pairs a pre-kill baseline with a post-kill measurement

Checked against each run's own filed `observer.csv`:

| run | pre-kill NDT baseline | post-kill NDT measurement | why it cannot carry the causal claim |
| --- | --- | --- | --- |
| `B/run-024` | **yes** — 331 poses, clean 4.830 Hz | **none** | its observer stream ends 13:46:46.346, **7 s before** the kill at 13:46:53 |
| `B/run-025` | none of its own | zero over ≈ 50 s | the kill instant was never timestamped, and the last NDT pose (13:51:41.320) is ≈ 3.7 s **before** the post-kill census — NDT silence already preceded the kill |
| `B/run-026` | none of its own | zero over ≈ 43 s | the relay was confirmed **still alive** 3 s after `kill`; NDT was already down and the run is M5-**unscoreable** |
| `B/run-027` | 1.600 Hz then 0 from t≈10 s, **12 s before** the kill | 2 poses, then the window closed | NDT had stopped **before** the kill, and it **resumed** after it |

So **no run pairs a live pre-kill NDT baseline with a post-kill measurement on
the same stack.** The post-kill zeros are **unattributed**: nothing in the filed
data establishes that the kill caused them, and `run-027` positively shows NDT
returning without the relay.

#### Why the ruling is nevertheless unaffected

**Branch (c) stands, by elimination on the pre-declared table, and no re-run is
needed:**

- **(a) Recovery** requires **≥ 9.0 Hz sustained** post-kill. The best post-kill
  reading on any of the four runs is `run-027`'s 2 poses over ≈ 30 s ≈ **0.07
  Hz** — two orders of magnitude short. No plausible correction for any of the
  confounds above reaches 9.0 Hz.
- **(b) Concat output unusable** is genuinely unmet: P3 passed and concat's
  output is a well-formed, non-empty `base_link` cloud stream.
- **(c)** is what remains.

The correct statement of P4's role: it selects (c) because **no run
demonstrated recovery**, not because killing the relay was shown to stop NDT.
The threshold, the branch table and the fix mechanism (**NONE**) are untouched.

#### The P3-vs-P4 tension, confronted

§6.7 left "a usable 7.6 Hz cloud stream drives NDT to exactly zero" resting
entirely on an untested duplicate-stamp hypothesis. **The `run-027` resumption
substantially dissolves that tension**: NDT did **not** sit at zero on
`concatenate_data`'s output — it returned ≈ 29 s after the relay died. What the
data actually shows is a slow, intermittent, unreliable NDT on cell B, on both
sides of the kill, consistent with this cell's already-registered instability
(`B/run-025` and `B/run-026` were M5-**unscoreable**; `run-027` scored
`ndt_rate_ratio=0.039`; §4.1's filed range is 0.257–0.989).

The duplicate-stamp mechanism therefore has **less** to explain than §6.7
implied, and it remains **NOT TESTED** — a hypothesis for whoever picks it up,
never a finding, wherever it appears in this record.

## 7. Task 4 smoke pass over the unproven closed-loop paths (live, 2026-08-01)

One run per unproven path before any batch collection commits to it, all
**without `--duel`** (`duel_admissible: false` on every manifest). Purpose: stop
this campaign repeating the 20 runs it already lost batch-collecting on unproven
paths (B run-001…012, E run-001…008).

Preamble held for every launch: `ROS_DOMAIN_ID=0`, 1-min loadavg < 2 at start
(1.66 / 1.26 / 1.63 / 1.65 / 1.72), no non-desktop GPU consumer, no pre-existing
`UnrealEditor`/`CarlaUE4`, governor `powersave` (recorded, unchanged).
`docker compose … down` between runs; `bootstrap_carla_msgs.sh` re-run after each
container recreate ahead of the extension-family runs.

| cell | run | arm | outcome | filed as |
| --- | --- | --- | --- | --- |
| B | `B/run-028` | closed-loop | **FAIL** — arm gate | excluded `gate:arm-failed` |
| B | `B/run-029` | static | **PASS** — filed, M5 rate gate fails as registered | not excluded |
| C | `C/run-001` | closed-loop | warm-up (pre-registered discard) | excluded `warmup:nishi` |
| C | `C/run-002` | closed-loop | **PASS** — all four criteria | not excluded |
| E | `E/run-009` | closed-loop | **FAIL** — arm gate | excluded `gate:arm-failed` |
| E0 | `E0/run-001` | static | **PASS** — files, observer records the as-emitted set | not excluded |

**Fix round 1 (2026-08-01, documentation only — no live runs).** Three
corrections are folded into the sections below and flagged in place rather than
silently rewritten. Every verdict, exclusion and go/no-go above is
**unchanged**; what changed is the diagnosis behind two of them, and one
citation:

1. **§7.1 / §7.4 — the "B and E fail at the same link" framing was WRONG**, and
   it hid cell B's actual blocker. They share a symptom (no trajectory) and stall
   on **different missing inputs**: B on the **map**, E on the **route**. B's
   `waiting for map` × 11 went unrecorded entirely in the first version; it is
   the single most actionable lead in the run.
2. **§7.4 — a 4.5× numeric error.** E's last `control_cmd` row is **12.077 s**
   before engage, not "~55 s".
3. **§7.6 — evidence cited that does not exist.** No filed artifact contains the
   `OK: base_link anchor` line; it was in the operator's terminal capture.

Commit `68116ac`'s message carries the superseded "SAME named link" framing.
Git history is immutable, so this note is the correction of record: **read §7.1
and §7.4 below, not that commit message,** for what the two cells actually did.

### 7.1 Cell B closed-loop: NO-GO, and it has never once armed

`B/run-028` reached `mode=2 autonomous=True is_autoware_control_enabled=True` via
the proven `/autoware/engage` publish (the AD API `change_to_autonomous` refused
first — "The target mode is not available", then "no response (spin timed out)" —
and the harness took its documented fallback). It failed on the control command:
post-engage `control_cmd_hz~0.00 n=0`.

**Failing link, named: `behavior_path_planner` is blocked WAITING FOR THE MAP, so
planning never produced a trajectory.** The route was set (`Route set via
set_waypoint_route`, `lanelet_sequence = [ids: 324 5650 719 6660 776 31 2463]`,
t=1785596518.797) and it **reached the planner** — `behavior_path_planner`'s own
`waiting for route` **stops** at `tier4-autoware.log:1347`, t=1785596529.903.
From that point the planner logs a *different* missing input, and logs nothing
else, for the rest of the run:

| `tier4-autoware.log` | t | line |
| --- | --- | --- |
| first `behavior_path_planner: waiting for map` | 1785596537.705 | `:1522` |
| last `behavior_path_planner: waiting for map` | 1785596590.955 | `:2453` (teardown) |

`waiting for map` × **11** spanning **53.3 s**, against `waiting for route` × 7
that all cease once the route lands. Downstream of that, and explained by it,
`control.trajectory_follower.controller_node_exe` logged `Waiting for trajectory
data` / `Control is skipped since input data is not ready` — last at
**1785596591.014**, i.e. right up to teardown — and
`control.autoware_operation_mode_transition_manager: Subscribed control_cmd is
timed out` × 25, last at 1785596592.905.

**`waiting for map` is the actionable lead on cell B**, and it is the *only*
input `behavior_path_planner` still reports missing at teardown. It is recorded
here rather than left in the raw log because it names a specific next probe:
whether `map_loader` publishes the lanelet map at all, and whether its
`transient_local` sample reaches a subscriber that joins late.

The run's own `observer.csv` shows `/control/command/control_cmd` spanning
**08:01:46.417 → 08:01:56.863 only** — it died **12.996 s BEFORE** the engage
publish (1785596529.859), so engage did not stop it. The only control traffic the run ever carried
was the pre-route emergency-stop stream of a `vehicle_cmd_gate` already in
`Emergency!` (`system_emergency heartbeat is timeout` at 1785596516.515, 0.35 s
before the stream ended). `system.mrm_handler` oscillated `NORMAL ↔ MRM_OPERATING`
at ~1 Hz throughout.

Upstream, from the same log: `sensing.lidar.concatenate_data:
transformed_raw_points[/sensing/lidar/{left,right}/pointcloud_before_sync] is
nullptr, skipping pointcloud publish` × **630**, plus
`crop_box_filter_measurement_range: Invalid PointCloud: row_step mismatch.
Expected: 99968 … Got: 0`. Measured on this run: LiDAR 8.90 Hz and NDT 4.82 Hz.
That is the **already-registered** cell-B sensing/NDT confound (§4.1, §6), which
the Task 1 ruling settled as not-to-be-fixed — recorded here as context, not as a
new defect.

**Not a one-off.** Across every cell B manifest: run-001…006 `crash:cell-launch`,
run-007 `crash:collect_gt`, run-008…012 `gate:arm-failed`, run-028
`gate:arm-failed`. Cell B has attempted closed-loop **13 times across two
independent sessions and has never armed**; run-028 is the **sixth**
`gate:arm-failed`. Deterministic within the run (53.3 s of continuous `waiting
for map`, and 73 s of the `Waiting for trajectory data` it causes) and across
sessions, so it was **not** re-run: this is a smoke failure with a named link,
and cell B closed-loop collection stops here.

**Hand-off to the cell-B diagnostic.** A separate static B run is dispatched to
settle the `waiting for map` lead before the primary duel. Starting point, from
this run's filed evidence: `behavior_path_planner` received the route
(`waiting for route` ceased at 1785596529.903) and then reported **only**
`waiting for map`, 11 times over 53.3 s, up to teardown. The open questions that
follow directly are whether `map_loader` publishes the lanelet map at all, and
whether its `transient_local` sample reaches a subscriber that joins late — the
latter being the case a late-starting planner would hit while the topic still
looks correctly advertised. Note that `/map/vector_map` is **not** in cell B's
observer topic set (`observer_topics/B.yaml` records LiDAR, NDT pose,
kinematic_state, control_cmd and published_time only), so no filed run in this
campaign can answer it from data already on disk — it needs the live probe.

### 7.2 Cell B static: GO, and the `quality.json` question is answered

`B/run-029` is the first clean, un-intervened cell B run since Phase 0. It
**filed a `quality.json`**: `ndt_rate_ratio = 0.281`, `pose_err_max_m = 0.050`,
`gate_pass = false`, `reasons = ["ndt rate ratio 0.28 < 0.9"]`.

So the `B/run-025` / `B/run-026` "no `quality.json`, and no matching exclusion
criterion" state did **not** recur on a clean run. That supports the mitigating
reading already on record: those four were the intervened-upon Phase 0 diagnostic
runs with a deliberate mid-run relay kill, and the missing `quality.json` is an
artifact of that intervention rather than baseline cell B behaviour. `0.281` sits
inside §4.1's filed 0.257–0.989 range. The failing M5 rate gate is the
**registered measured confound** — expected on B, neither a smoke failure nor
excludable.

`B/run-028` also has no `quality.json`, but that is a different and benign state:
it aborted at step 9 (`ARM FAIL`) and so never reached step 13 `write_quality`,
and it carries a registered exclusion. Nothing was hand-written into it.

### 7.3 Cell C: GO

`C/run-001` was the mandatory criterion-5 Nishi warm-up and is excluded
`warmup:nishi` — a pre-registered discard, not a failure (it armed and scored
cleanly regardless). `C/run-002` is the smoke, and passes all four criteria:

- engage on the `/autoware/engage` path — `published engage=true x5`, then
  `ARMED: localized, route set to (81571.616, 50019.827), autonomous engaged`;
- `/control/command/control_cmd` flows — post-engage `control_cmd_hz~20.00 n=68
  nonzero_longitudinal=63/68 frac=0.926`, and the harness's own gate printed
  `OK: /control/command/control_cmd is flowing`;
- manifest validates — `excluded: false`, `duel_admissible: false`;
- teardown — `teardown: done`, no survivors/skips heading.

`quality.json`: `gate_pass=True branch=absolute ndt_rate_ratio=1.000
pose_err_max_m=0.187`.

### 7.4 Cell E closed-loop: NO-GO — the recorded static-only downgrade applies

`E/run-009` reached `mode=2 autonomous=True is_autoware_control_enabled=True` and
then failed on the control command with the same *symptom* as B: post-engage
`control_cmd_hz~0.00 n=0`, excluded `gate:arm-failed`.

**Failing link, named — the same SYMPTOM as B, a DIFFERENT CAUSE.** Corrected in
fix round 1; the first version of this section called it "the same link as B's",
which the logs do not support and which hid B's real blocker (§7.1). The two
cells stall on **different missing inputs**:

| | `B/run-028` | `E/run-009` |
| --- | --- | --- |
| `Route set via set_waypoint_route` | 1785596518.797 | 1785597940.366 (`bridge-stage2.log:1459`) |
| `behavior_path_planner: waiting for route` | **stops** at 1785596529.903 | **persists** to 1785598004.347 (`:1976`) — **63.98 s AFTER** route-set |
| `behavior_path_planner: waiting for map` | **× 11**, to teardown | **× 0** |
| blocked on | **the map** | **the route** |

So on E the route is published by `mission_planner` but **never reaches
`behavior_path_planner`**, and the map is not implicated at all; on B the route
does arrive and the map never does. **One diagnosis will not unblock both.**

Downstream of E's missing route, and explained by it:
`control.trajectory_follower.controller_node_exe: Waiting for trajectory data` ×
15 and `Control is skipped since input data is not ready` × 23, with `Subscribed
control_cmd is timed out` × 24. The run's `observer.csv` carries just **6**
`/control/command/control_cmd` rows, the last at 1785597942.392 — **12.077 s
before** the engage publish at 1785597954.469.

That offset is worth recording rather than rounding away: **12.077 s on E against
12.996 s on B**, i.e. both cells' control streams die ~12–13 s ahead of engage,
despite the two failing on different inputs. Whether that near-coincidence is
mechanism or arithmetic of the fixed arm sequence is **NOT established here** — it
is an observation for whoever picks the question up, not a finding.

**Ruled out on E, so it is not mistaken for the blocker later:**
`planning.scenario_planning.parking.costmap_generator: Could not find a
connection between 'map' and 'base_link' … Tf has two or more unconnected trees`
is a **bring-up transient**. Its last occurrence is `bridge-stage2.log:1284`,
t=1785597929.809 — **10.557 s BEFORE** route-set — and it never recurs.

This cell's sensing and localization were healthy on this run — LiDAR
`/sensing/lidar/top/pointcloud_raw_ex` 19.91 Hz (the patched image's topic),
`/localization/kinematic_state` 19.91 Hz, NDT 8.91 Hz — so the failure is in the
planning→control chain, not in bring-up. This is the outcome the plan
anticipated: cell E's recorded **static-only downgrade** applies and its later
collection is static-only. That is a spec outcome, not a blocker.

### 7.5 Cell E0: GO for what it measures, with a scoring caveat

`E0/run-001` passes its two criteria: the run files (`run 1/1 complete`,
`excluded: false`) and the observer records the **as-emitted** topic set of
`benchmarks/config/observer_topics/E0.yaml` — all four topics present, including
the unpatched image's own `/sensing/lidar/top/pointcloud_before_sync` (8.42 Hz),
`/localization/kinematic_state` (14.84 Hz),
`/localization/pose_estimator/pose_with_covariance` (0.14 Hz) and
`/control/command/control_cmd` (5.14 Hz).

**Caveat, registered here because E-family collection depends on it:** no
`quality.json` was written, and the refusal is deliberate and by design —

```
QUALITY GATE FAIL: metrics.ladder_branch is null for cell 'E0': no G1 ladder
branch is selected for the map bundle this cell localizes against, so the M5
gate has no localization criterion to apply.
```

`cells.yaml` leaves `ladder_branch`, `abs_pose_gate_m`, `lidar_expected_hz` and
`ndt_expected_hz` null for E and E0, pending the live re-gate those entries name.
Consequence, checked against every filed manifest: **no E-family run has ever
produced a `quality.json`** — `E/run-001…009` are all excluded, and `E0/run-001`
is valid-but-unscored. An E-family collection can therefore gather transport and
process-cost data (which is what E0 exists to measure) but cannot be M5-scored
until that re-gate selects the branch. This is distinct from the `B/run-025` /
`B/run-026` state: E0/run-001's missing `quality.json` has a named,
pre-registered cause and the run is not excluded.

**Corrected in fix round 1 — the gap is NOT E-only**, and saying "both E and E0"
understated it. `cells.yaml` leaves `ladder_branch` null for **D** (`:410-411`)
and **E-opt** (`:495-500`) on the same pending-measurement grounds, so the same
refusal awaits them. **CAL-rmw** (`:527-528`) and the other CAL cells are also
null but belong in a different category: their nulls are *deliberate and
terminal*, carrying their own stated reason (`# no localization stack in this
cell`), not a pending measurement. Any cell in the first group needs its branch
selected before it can be M5-scored; the CAL cells never will be.

**Also registered (pre-existing, not caused by this task):** both new E-family
runs file a **0-byte `gt.log`** while their `gt.csv` is fully populated
(`E/run-009` 1349 rows, `E0/run-001` 1169), where the UE5-family runs file a
~250-byte `gt.log` (`B/run-029` 253 B, `C/run-002` 251 B). So the python-bridge
family leaves **no filed record of which ground-truth anchor was applied** — the
exact fact `1f43914`'s guard exists to establish. That absence is what made the
F2 citation error below possible, and it is worth closing before E-family
`pose_error` numbers are relied on.

### 7.6 Pre-flight harness defect: every python-bridge cell could not `plan`

Found by a `--dry-run` pass before any live boot, and fixed before cells E / E0
could run at all. `ad56308` ("fix round 1 … No live run") inserted the base_link
anchor guard into `cells/python-bridge.sh` **65 lines above** the `IMAGE=`
resolution it reads, so under `set -u` every python-bridge cell (E, E0, E-opt)
aborted `plan` with `IMAGE: unbound variable`. The empty pipe that followed made
the guard mis-report itself as anchor drift ("no DEFAULT_WHEELBASE assignment
found in the bridge source") rather than as the statement-ordering defect it was.

Fixed by moving the guard **verbatim** below the resolution and its
`docker image inspect` (commit `1f43914`); nothing about what it checks changed,
it merely became reachable. It then passed on both E-family images
(`-1.42500000 m`). No exclusion applies: the defect aborts before step 4, so no
run directory is created, and no filed run was measured through it
(`E/run-001…008` predate `ad56308`).

**Where that observation actually comes from — corrected in fix round 1.** This
section previously said `E0/run-001`'s launch log "carries the first `OK:
base_link anchor` line this campaign has ever produced". **It does not, and no
filed artifact does.** Checked:

```
$ grep -ril anchor benchmarks/results/E0/run-001/ benchmarks/results/E/run-009/
(no matches)
```

The guard runs in the cell launcher's `plan` phase, whose stdout goes to the
**runner's terminal**, not into the run directory; the two `OK: -1.42500000 m`
lines this task observed were in the operator-side capture (`/tmp/smoke-E.log`,
`/tmp/smoke-E0.log`), which is **not** filed evidence. The observation is real
and was independently reproduced by running the guard directly against both
images — but the record must not point at a filed artifact that does not exist,
so the claim is withdrawn and replaced by its actual provenance.

This compounds the 0-byte `gt.log` noted in §7.5: the python-bridge family files
**no** record of the applied GT anchor anywhere in its run directory, which is
precisely the fact this guard exists to prove. Making the guard's result reach
the run directory is the obvious follow-up; it is **not** done here (fix round 1
is documentation only).

### 7.7 Cell B's `waiting for map` blocker, settled live (2026-08-01)

The diagnostic §7.1 handed off ran, as one non-duel cell-B `--arm static` run —
**`B/run-030`**, `excluded: false`, `duel_admissible: false`. Full evidence,
every command and every raw capture: **`benchmarks/evidence/b-vector-map-delivery/`**.
Preamble held: `ROS_DOMAIN_ID=0`, preflight loadavg 0.36, governor `powersave`
(recorded, unchanged), no pre-existing `UnrealEditor`/`CarlaUE4`, engine BuildId
`4210e602-78ec-46e1-8f2f-03fadbe036a3`. The run's `quality.json` fails only on
`ndt_rate_ratio = 0.303` — the **registered** M5 confound (§4.1, §6),
`pose_err_max_m = 0.054`.

**Answer to §7.1's two open questions: `map_loader` DOES publish the lanelet
map, and its `transient_local` sample DOES reach a subscriber that joins late.**
Measured on `B/run-030`'s own live stack: a late-joining
`RELIABLE / KEEP_LAST(1) / TRANSIENT_LOCAL` subscriber received **1 305 281
bytes in 0.173 s**, and `ros2 topic echo --once` returned the message. Across
this task's nine probe subscriptions the sample arrived **9 times out of 9**.

**So the failing link moves one step, and the map hypothesis survives in a
narrower form.** `/map/lanelet2_map_loader` publishes exactly one retained
sample from its constructor; **every** subscriber in the stack —
`behavior_path_planner` included, read off the live graph — requests the
publisher's exact QoS, so **there is no durability mismatch**. What is
unreliable is delivery to the subscribers that are **already running when that
one publication happens**. On the in-stack `topic_state_monitor_vector_map`,
same QoS, over six Fast-DDS `udp_only` bring-ups:

| bring-up | first receipt, relative to `Map is published.` |
| --- | --- |
| `B/run-028` | +20.2 … +23.2 s |
| `B/run-029` | **NEVER** (not-OK at +98.2 s, last block of the run) |
| `B/run-030` | +11.5 … +14.6 s |
| replica V1 | **NEVER** (`NotReceived` at +113.35 s) |
| replica V1b | +0.97 s |
| replica pass 2 | +0.05 s |

**Two of six never delivered it.** V1 and V1b are consecutive runs of the same
script, two minutes apart. The failure was **reproduced standalone** — same
image, same bundle, same launch line, no CARLA, no harness — which localises it
to the `rmw_fastrtps_cpp` + `observer/config/udp_only.xml` transport that **cell
B alone runs**; cells A/C/E run `rmw_cyclonedds_cpp`. A cyclonedds control
bring-up delivered at +0.24 s, but n = 1 and that is **not** a claim that
cyclonedds is immune.

**Why B's static runs file cleanly and every closed-loop attempt dies.**
`behavior_path_planner` checks its inputs in a fixed order, visible in the filed
logs: scenario → route → map. A static arm sets no route, so no scenario is
selected, so the planner stops at the *first* check and never evaluates the map
(`waiting for scenario_topic` × 16-17, `waiting for map` × 0, on `run-029` and
`run-030` alike). `run-028` is the only run that got far enough to report the
map missing.

**NOT TESTED, stated so it is not read as more than it is:**
`behavior_path_planner`'s own receipt of the map was never observed directly —
the static arm cannot reach its map check, and under cell B's transport the ros2
CLI could not enumerate the node. Its failure in `run-028` is attributed to the
mechanism above by inference from an endpoint with identical QoS in the same
already-running class. Also not tested: whether any fix makes cell B arm, and
whether a 16 MiB socket-buffer profile helps (one passing run against a 2-in-6
failure has no power).

**Nothing was fixed.** `benchmarks/cells/tier4_autoware.sh` is untouched; the
proposed minimal fix — a re-publish-and-verify bring-up step that leaves
`dds_profile_sha256` byte-identical, with a zero-perturbation gate-only
alternative — is written up in the evidence document for the operator's
decision.

### 7.8 The delivery workaround applied, and validation STOPPED at run 1 (2026-08-01)

Owner ruling after §7.7: apply the fix, validate with three consecutive cell-B
closed-loop runs, then proceed to the duel. **Validation stopped at run 1, which
failed.** Per the ruling the fix was not iterated on, no fourth run was taken,
and no criterion was adjusted.

**What landed** (commit `a3ba158`, `fix(bench)`): `injector/republish_vector_map.py`
(capture the retained sample -> wait for its own publisher to match a settled
reader set -> re-publish -> gate on delivery), called from
`cells/tier4_autoware.sh` section 5 **on the closed-loop arm only**, pinned by
`tests/benchmarks/test_vector_map_gate.py` (which executes the real gating block
for both arms and asserts the static one reaches no container command at all),
recording `<run>/vector-map-delivery.json`. It is a **harness-injected
workaround for a measured transport defect** — not a gate adjustment, not a
threshold change. `transport.dds_profile_sha256` is byte-identical, so cell B's
filed runs stay transport-comparable, and the static path acquires no step.

**§7.7's 6-of-6 arithmetic, reconciled from filed data — there IS a second
blocker.** `behavior_path_planner` reports the FIRST input it finds missing, so
its last readiness line names the blocker
(`evidence/b-vector-map-delivery/planner_readiness.py`). Across the six
`gate:arm-failed` runs — the only 6 of 13 closed-loop attempts that reached the
arm:

| run | planner blocked on |
| --- | --- |
| `run-008` | **map**, to teardown |
| `run-009` | route |
| `run-010` | route |
| `run-011` | route (its `arm.log` also has `set_route_points: no response`) |
| `run-012` | **operation_mode** — it got PAST the map |
| `run-028` | **map**, to teardown |

**The map is the blocker in 2 of 6, not 6 of 6.** Three fail on the route and
one on `operation_mode`. All six end with `/planning/trajectory` not-OK and no
trajectory ever formed; they simply stall in different places. So this fix was
known to be **necessary and not sufficient before validation started**.

**Validation run 1: `B/run-031`, FAILED, excluded `crash:cell-launch`** (a
registered criterion-1 exclusion: `cells/<approach>.sh up` itself failed). The
gate refused the bring-up with exit 5 — published, never verified:

```text
capture_wait_s 6.0   captured true   data_bytes 1305281
subscriber_count 16  matching_settled true   pre_republish_delivered false
attempt 1 verified false (60.048 s) | 2 false (60.022 s) | 3 false (60.027 s)
```

**And the run carries a finding that matters more than its verdict: the
re-published map WAS delivered — to some in-stack subscribers and not to the
one the gate verifies.** From `run-031/tier4-autoware.log`:

| line | t | event |
| --- | --- | --- |
| `:347` | 1785605088.396 | `lanelet2_map_loader: Succeeded to load lanelet2_map. Map is published.` |
| `:398` / `:419` | 1785605088.641 / .790 | `lanelet2_map_visualization: Map is loaded` / `vector_map_tf_generator: broadcast static tf` — the ORIGINAL publication |
| `:1123` / `:1128` | 1785605117.126 / .143 | both again — **re-publish attempt 1 DELIVERED** |
| `:2149` / `:2155` | 1785605177.156 / .176 | both again — **attempt 2 DELIVERED** |
| `:3147` / `:3152` | 1785605237.147 / .159 | both again — **attempt 3 DELIVERED** |
| `:545` … `:4343` | — | `/autoware/map/topic_rate_check/vector_map ERROR` in **71 of 72** diag blocks |

The helper is a separate process, so those three deliveries are inter-process
and they landed every time. `topic_state_monitor_vector_map`, in a different
container, received **none** of them (`NotReceived`, `last_message_time 0.00`,
throughout ~220 s). So the re-publish mechanism works as a publication; what
failed is the endpoint the gate reads.

**Consequence, stated plainly: the gate as built is over-strict, and this run's
verdict is NOT evidence that the planner lacked the map.** §7.7 already recorded
that the monitor and the planner fail independently (`run-028`: monitor OK at
+23.2 s, planner still blocked at +95 s); `run-031` is the mirror image, with
the monitor failing while two other in-stack subscribers succeeded. Because the
gate aborts the bring-up **before** any route is set, `behavior_path_planner`
never evaluated its map check at all — its 38 readiness lines all read
`waiting for scenario_topic`. **NOT TESTED: whether `run-031` would have armed.**

Ruled out for this run: no bring-up crash caused it. `component_container_mt-34`
(`mission_planner_container`) and `mt-41` do abort, at 1785605307 (`:4476`,
`:4514`) — that is **7 s after the gate had already failed** and is the teardown
SIGINT storm, not the cause. `pose_instability_detector` died early (`:873-875`,
`std::runtime_error`), which is pre-existing and unrelated to map delivery.

The fix had been exercised on the failing path before this run
(`evidence/b-vector-map-delivery/smoke-republisher.log`): a replica bring-up
that was `NotReceived` at +40 s was rescued, but only on **attempt 3**. So across
the two failing bring-ups now observed, the re-publish flipped the monitor
**1 of 2**. That is the workaround's measured reliability, on n = 2, and it is
not a rate.

Everything §7.7 disclosed still stands: the `/map/pointcloud_map` observation is
unchanged and the branch-(c) NDT ruling is not reopened; the replica bench's
`use_sim_time:=false` deviation and the trailing-whitespace trim on the tracked
captures remain as disclosed.

### 7.9 The gate made advisory, and the map/operation_mode unification REFUTED (2026-08-01)

Owner ruling after §7.8: make the delivery step advisory, add the delivery
oracle that actually worked, then re-validate. Recorded plainly, because this
campaign is strict about it: **making the step advisory changes no measured
quantity.** It removes an *added* precondition that is not one of the
pre-registered pass criteria (the arm succeeding and `control_cmd` flowing). If
the map genuinely never reaches the planner, the run still fails — at the arm,
where `behavior_path_planner` reports on the map itself, instead of at a step
that fires before a route exists.

**Probe: does `topic_rate_check/vector_map` propagate into operation-mode
availability?** Measured off the last `logging_diag_graph` block of each run.

- **Propagation: CONFIRMED.** `/autoware/map/topic_rate_check/vector_map` is
  printed as a direct child of `/autoware/map`, which is a direct child of
  `/autoware/modes/autonomous`. In `run-031` it sits ERROR in **71 of 72**
  blocks and `/autoware/modes/autonomous` is ERROR throughout. So a
  non-received vector map does withhold autonomous-mode availability.
- **The unification is REFUTED.** `run-012` is the only run whose planner
  blocked on `operation_mode`, and in its final block
  `topic_rate_check/vector_map` is **ABSENT** — i.e. delivered (it went OK at
  +17.7 s) — while `/autoware/modes/autonomous` is ERROR anyway, via
  `topic_rate_check/pointcloud_map`. `run-028` is the same shape. So the map
  and `operation_mode` are **not one defect with two faces**, and the three
  blockers stay three.
- **And a stronger fact that makes the propagation moot in practice:**
  `/autoware/modes/autonomous` is ERROR in the final block of **every** cell-B
  run examined (`run-012`, `run-028`, `run-030`, `run-031`), driven by
  `pointcloud_map` and `transform` regardless of the vector map. Autonomous-mode
  availability is therefore withheld on 100% of cell-B bring-ups whatever the
  map does — which is exactly why the harness's documented fallback to the
  legacy `/autoware/engage` path exists. vector_map's contribution to
  availability is real, and never decisive.
- **NOT TESTED, and it is the named next probe:**
  `behavior_path_planner: waiting for operation_mode` is the planner not
  receiving the `/system/operation_mode/state` **topic**, which is a different
  mechanism from the diag-graph availability computation. Nothing here measured
  that topic's delivery. It is another latched `TRANSIENT_LOCAL` topic, so the
  one-defect-class hypothesis of §7.7 survives even though this specific
  unification does not.

**What changed in the harness** (commit `a6c6935`): the step keeps the capture,
the re-publish and `--attempts 3` (both the replica smoke and `run-031` show the
retry is load-bearing), keeps recording `topic_state_monitor_vector_map`, and
**no longer aborts**. It gains the second oracle `run-031` established — a fresh
`lanelet2_map_visualization: Map is loaded` / `vector_map_tf_generator:
broadcast static tf` line after a publication, which is inter-process receipt
because the re-publisher is a different process. Both oracles are recorded per
attempt (`verified`, `verified_relog`), and the refuted one stays in the record:
`topic_state_monitor_vector_map` is a poor oracle — `run-028` has it OK while
the planner stayed blocked 53.3 s longer, `run-031` has it silent while two
other subscribers received every re-publication. Neither oracle observes the
planner; only its own `waiting for map` line does, and only once a route exists.

**Housekeeping, noted rather than changed:** `run-031` is filed
`crash:cell-launch` (criterion 1, "the cell failing to come up at all", which
its `cells/tier4-native.sh up` failure satisfies). `gate:<detail>` under
criterion 2 arguably fits a readiness-check abort better, but criterion 2 says
**pre-registered** readiness check and that step was new, so criterion 1 is the
safer reading. Left as filed; the ambiguity is recorded here.

### 7.10 Validation re-run STOPPED at run 1: the map is fixed, the ROUTE is the blocker (2026-08-01)

`B/run-032`, cell B closed-loop, non-duel, harness `2dbec06`, preflight loadavg
1.05. **ARM FAIL, excluded `gate:arm-failed`.** Per the standing ruling the run
was not retried, the fix was not iterated on, and no criterion was adjusted.

**The advisory step behaved exactly as ruled, and the map fix worked.** The step
recorded and continued (`verdict_code 0`, `pre_republish_delivered true`,
monitor verified on attempt 1 in 0.007 s), the run proceeded to the arm, and
`behavior_path_planner` logged **`waiting for map` × 0** — against × 8 on
`run-008` and × 11 on `run-028`. The planner had the map.

**It blocked on the ROUTE instead — the second blocker §7.8 predicted from
filed data, landing exactly there.** From `run-032/tier4-autoware.log`
(offsets vs teardown at 1785606658.036):

| line | t | event |
| --- | --- | --- |
| `:261` | 1785606537.858 | `mission_planner: waiting lanelet map…` — printed ONCE, so mission_planner had the map promptly |
| `:1317` | 1785606573.594 (−84.4 s) | `route_handler: getMainLanelets: lanelet_sequence` — **the route exists** |
| `:1339` | 1785606574.310 (−83.7 s) | last diag block listing `topic_rate_check/route` not-OK |
| `:1390` | 1785606577.308 (−80.7 s) | first block **without** it — the route monitor received it **≤3.7 s** after the route existed |
| `:1468` | 1785606580.366 (−77.7 s) | the planner's **first** `waiting for route` — 3.1 s AFTER the monitor already had it |
| `:2430` | 1785606629.428 (−28.6 s) | the planner's **last** `waiting for route`; it printed nothing further |

So `behavior_path_planner` lacked the route for **≥55.8 s** after
`mission_planner` produced it and **≥52.1 s** after
`topic_state_monitor_route` had received it. Engage went out at 1785606593.756
via the documented `/autoware/engage` fallback; the post-engage window closed at
1785606642.660 with `mode=2 autonomous=True … control_cmd_hz~0.00 n=0`. No
trajectory ever formed (`Waiting for trajectory data` × 21, last at −4.4 s;
`trajectory` in the final not-OK set alongside `control_command`,
`trajectory_follower`, `transform`, `pointcloud_map`).

**CHARACTERISATION: this is the SAME defect signature as the map, on the route
topic.** A latched (`TRANSIENT_LOCAL`) message, published once, received
promptly by `topic_state_monitor_*` and not by `behavior_path_planner`, with
the two behaving as independent draws:

| | `/map/vector_map` (§7.7) | `/planning/mission_planning/route` (here) |
| --- | --- | --- |
| monitor receipt | +0.05 s … +23.2 s, or never | **+≤3.7 s** |
| planner receipt | never, in `run-008` / `run-028` | **≥55.8 s late** |
| divergence | `run-028`: monitor OK at +23.2 s, planner blocked +95 s | `run-032`: monitor OK at +3.7 s, planner blocked +55.8 s |

That materially strengthens §7.7's one-defect-**class** hypothesis — latched
topic non-delivery to an already-running subscriber under the tier4-native
transport — and it means the route is not a *different* bug so much as the same
bug on another topic. It also means a per-topic re-publish workaround does not
scale: the map needed one, the route would need another, and `operation_mode`
(`run-012`) a third.

**NOT TESTED, and it is what the next probe should measure:** the route topic's
delivery was not probed live. A live `ros2 topic info -v` attempt on
`/planning/mission_planning/route` during this run returned
`Unknown topic` — the same ros2-CLI discovery limitation §7.7 recorded under
this transport, not evidence the topic was absent. Whether the planner
eventually received the route at ~1785606630 (it stopped complaining) or simply
stopped cycling is **not established**: the planner emitted no further line
either way, and no trajectory followed in the remaining 28 s.

**Also NOT established:** whether the map fix is what let the planner get past
its map check, or whether this bring-up would have delivered the map anyway.
`pre_republish_delivered` was already `true` before the re-publish, so on THIS
run the workaround had nothing to repair. Its value remains untested on a
bring-up that needed it.

**Recorded artifact of the second oracle:** `verified_relog` came back `false`
on `run-032` despite delivery, because the re-log check re-reads the launch log
immediately after the monitor's wait returns — 7 ms after publication here,
before the container's log write can land. The two oracles are therefore **not
comparable on runs where the monitor verifies instantly**. Left unchanged
rather than fixed mid-validation, because editing the harness between runs of a
validation series would invalidate the series.

**Test-suite note, recorded rather than left silent.** The commit filing
`run-032` was made from a suite run in which
`tests/benchmarks/test_teardown.py::test_tier4_autoware_sh_aw_sidecar_settles_on_the_post_exec_cmdline`
FAILED once (1 failed / 1021 passed). It is a **load flake, not a regression**:
that test executes the REAL sidecar polling loop, which needs the `/proc`
cmdline to read identically for 2 continuous seconds inside a 50-poll cap, and
it ran while the host was still shedding `run-032`'s teardown (1-min loadavg
~10). Re-run in isolation it passes, `tests/benchmarks/test_teardown.py` passes
16/16 three times consecutively, and the full suite is **1022 passed / 0 failed
/ 1 skipped** on an idle host (loadavg 0.18). The launcher's own comment already
warns that the poll cap is "a FLOOR, not a ceiling -- load stretches it
further"; this is that, observed from the test side.

## 7.11 FINDING: latched-topic delivery to `behavior_path_planner`, bounded to the Fast-DDS transport — and cell B's closed-loop rescope

This is a first-class campaign finding, not a footnote. Full evidence, probe
scripts and raw captures: `benchmarks/evidence/b-vector-map-delivery/`.

### The defect, characterised

**Latched (`TRANSIENT_LOCAL`) messages, published once, are received promptly by
`topic_state_monitor_*` and NOT by `behavior_path_planner`. The two behave as
INDEPENDENT DRAWS, not as proxies for one another.** Measured on two topics, in
runs where the planner's own readiness log names what it was missing:

| topic | monitor receipt | planner receipt |
| --- | --- | --- |
| `/map/vector_map` | +0.05 s … +23.2 s, or **never** (2 of 6 bring-ups) | **never**, in `run-008` and `run-028` |
| `/planning/mission_planning/route` | **+≤3.7 s** (`run-032`) | **≥55.8 s late** (`run-032`) |

The divergence is visible in single runs, in both directions:

- `run-028`: monitor OK at +23.2 s while the planner was still `waiting for map`
  at +95 s, to teardown.
- `run-032`: monitor had the route at +≤3.7 s (`:1339` last not-OK block,
  `:1390` first block without it) while the planner logged its **first**
  `waiting for route` at `:1468` — 3.1 s *after* the monitor already had it —
  and its **last** at `:2430`, ≥55.8 s after `mission_planner` produced the
  route at `:1317`. Engage went out at 1785606593.756; the post-engage window
  closed at 1785606642.660 with `control_cmd_hz~0.00 n=0`.
- `run-031`: the monitor received **none** of three re-publications while
  `lanelet2_map_visualization` (`:1123`, `:2149`, `:3147`) and
  `vector_map_tf_generator` (`:1128`, `:2155`, `:3152`) received every one —
  inter-process, from a different process than the publisher.

Blocker breakdown across every cell-B run that reached the arm and failed it
(the six `gate:arm-failed` runs; the other seven of the 13 closed-loop attempts
are 6 `crash:cell-launch` + 1 `crash:collect_gt` and never reached the arm):
**map 2** (`run-008`, `run-028`), **route 3** (`run-009/010/011`),
**operation_mode 1** (`run-012`).

The map half was **reproduced standalone** — same image digest, bundle and
launch line, no CARLA and no harness at all (`replica-bench.log`): consecutive
runs of one script two minutes apart gave "never in 113 s" and "0.97 s".

### The bounding probe: `B/run-033`, cyclonedds — IT ARMED

One deliberate, non-duel deviation run (owner ruling). **Exact command:**

```text
BENCH_TIER4_TRANSPORT_DEVIATION="task5 cyclonedds bounding probe: is the latched-delivery defect Fast-DDS-specific?" \
  bash benchmarks/run.sh B --arm closed-loop --rmw rmw_cyclonedds_cpp --dds-profile none
```

**Transport actually in force:** the Autoware container ran
`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` with **no `CYCLONEDDS_URI` and no
profile mounted at all**. `observer/config/udp_only.xml` is a **Fast-DDS**
profile: it was **not mounted, not read, and consumed by nothing** in this run.
`--dds-profile none` rather than the harness's cyclone default
(`docker/cyclonedds.xml`) because that profile pins interfaces to `lo`, under
which Task 9's matrix **row 10** measured the fork invisible to this image (no
list, no echo, no rate). **Row 11** — cyclone, no profile — is the only
non-Fast-DDS cell in which the fork is readable, and it works by binding the
host's routable NIC.

**This is a DEVIATION from cell B's registered transport and is not a cell-B run
in the normal sense.** Its `manifest.json` says so on its face —
`transport.rmw = rmw_cyclonedds_cpp`, `dds_profile_sha256 = ""` — which does not
match `cells.yaml`'s registration. `duel_admissible: false`. The launcher prints
a `DEVIATION` banner naming the reason; that banner goes to the runner's
terminal, not into the run directory (the same gap §7.6 recorded), so the
manifest's transport block is what a later reader must key on.

**Result — cell B armed for the first time in 14 closed-loop attempts, and
scored a clean pass:**

| | fastrtps `udp_only` (`run-032`) | **cyclonedds (`run-033`)** |
| --- | --- | --- |
| planner `waiting for map` | 0 | **0** |
| planner `waiting for route` | **10**, last ≥55.8 s late | **0** |
| planner blocked on, at end | route | **only `scenario_topic` ×5, last −161 s (bring-up)** |
| AD API `change_to_autonomous` | refused, fell back | **SUCCEEDED** (fallback still ran) |
| post-engage | `control_cmd_hz~0.00 n=0` | **`~5.00 n=15`, nonzero 11/15, ego 0.153 m/s** |
| arm verdict | ARM FAIL | **ARMED** |
| `control_cmd` rows recorded | — | **2935** |
| final diag not-OK set | `control_command`, `objects`, `pointcloud`, `pointcloud_map`, `trajectory`, `trajectory_follower`, `transform` | **`objects`, `pointcloud` only** (perception, off by design) |
| `quality.json` | not reached | **`gate_pass: true`, `reasons: []`** |
| `pose_err_max_m` | — | 0.138 |
| `goal_closest_approach_m` | — | **0.103** |

So on the same host, same image digest, same map bundle, same fork build, same
launch line and the same harness commit, **changing only the middleware takes
cell B from 0-for-14 to armed, driven to the goal within 0.103 m, and passing
its quality gate.**

### The attribution boundary — read this before quoting the finding

The defect is a property of **the as-shipped tier4 transport configuration on
this host**, and the cyclonedds probe bounds it to the Fast-DDS side of that
configuration. It is **NOT established as an intrinsic property of the
tier4-native approach**, and this record must not be read as though it were:

- **n = 1** on the cyclonedds side. One arming run is not a rate, exactly as two
  failing bring-ups were not one.
- **Fast-DDS version, kernel, and loopback behaviour are uncontrolled.** The
  Autoware image ships Fast-DDS 2.6.11 and the fork builds against 2.11.2; no
  other version pair was tried.
- **The cyclonedds cell is itself not measurement-grade.** Task 9's README says
  in terms not to use rows 6/11 for measurement, because they bind the host's
  routable NIC and Cyclone's graph is flaky for bare-DDS publishers. `run-033`
  is a bounding probe, **not** a proposal to re-register cell B's transport, and
  nothing in it licenses swapping the middleware for collection.
- The probe shows the defect **does not occur** under a different middleware on
  this host. It does not show *why*, and it does not show that Fast-DDS is at
  fault rather than the interaction between the fork's SHM-only locators, the
  `udp_only.xml` workaround they force, and this host's loopback.

**One observation that touches a standing ruling, recorded and NOT acted on.**
`run-033`'s `ndt_rate_ratio` is **1.000**, against 0.257–0.989 across every
filed Fast-DDS B run (0.303 on `run-030`). Cell B's failing M5 rate gate is the
**registered branch-(c) confound**, and this task neither reopens nor amends
that ruling — but a reader deciding branch (c)'s future should know that the
confound is absent on the one bring-up that changed only the middleware. n = 1.

### The consequence — rescope

**Cell B's closed-loop arm is not collectable under its registered transport, so
the A-vs-B closed-loop equivalence verdict is NOT COMPUTABLE.** What is
unaffected:

- the **static-arm** verdict. Three counts get confused here, so each is named,
  all recomputed from every manifest on 2026-08-01: cell B has **17 non-excluded
  static runs** (`run-013`…`run-027`, `run-029`, `run-030`), of which
  **10 — `run-013`…`run-022` — are the DUEL-ADMISSIBLE pool** the A-vs-B static
  verdict is actually computed from, and **0 statics are excluded** (cell A:
  13 non-excluded static, 10 duel-admissible `run-003`…`run-012`, 0 excluded).
  All of them are complete and untouched: the delivery workaround is
  closed-loop only, pinned by a test that asserts the static bring-up reaches no
  container command at all;
- **cell C**, which supplies closed-loop confirmatory data on the extension path.

### What was tried and did not work

- **The per-topic re-publish** (`injector/republish_vector_map.py`, commit
  `a3ba158`, made advisory in `2dbec06`). It works for the map — `run-032` and
  `run-033` both logged `waiting for map` × 0 — but it **does not scale**: the
  route is published *after* the planner starts by construction, so it can never
  use the late-joiner path the map fix relies on, and `operation_mode` would need
  a third. Its value on a bring-up that genuinely needed it is **UNTESTED**:
  `run-032` and `run-033` both had `pre_republish_delivered: true`, so it had
  nothing to repair, and `run-031` — the one bring-up that needed it — is the one
  where it did not take within three attempts.
- **The fatal form of that gate.** It aborted `run-031` on an oracle its own log
  refuted, converting a possibly-armable run into `crash:cell-launch`. Made
  advisory; the refuted oracle is kept in the record with what refuted it.
- **`verified_relog` fast-path artifact:** it reads `false` on `run-032`/`run-033`
  despite delivery, because the re-log check re-reads the launch log immediately
  after the monitor's wait returns — 7 ms after publication. The two oracles are
  **not comparable when the monitor verifies instantly**. Left unchanged rather
  than fixed mid-validation.
- **Still NOT ESTABLISHED:** whether `run-032`'s planner finally received the
  route at ~1785606630 or merely stopped cycling; the route topic's delivery was
  never probed live (a live `ros2 topic info -v` returned `Unknown topic`, the
  known CLI discovery limitation under this transport, **not** evidence of
  absence).

**Second load-flake instance, recorded for the same reason as §7.10's.** A suite
run started while the host was still shedding `run-033`'s teardown failed one
test with `assert 'os.execv' in ''` — an empty `/proc/<pid>/cmdline` read, the
same class as §7.10's sidecar flake and the same root cause (these tests read a
real short-lived process's cmdline, and under load the process is gone before
the read). Re-run on an idle host the suite is **1028 passed / 0 failed /
1 skipped**. Neither flake is a regression, and neither is silenced: both are
timing-sensitive reads that the launcher's own comments already warn about.

---

## 8. Task 7 confirmatory cell C collection (live, 2026-08-01)

Cell C is `approach: extension` on `NishishinjukuMap` — **not** the tier4-native
cell. Its closed-loop path was smoke-proven in Task 4 (`C/run-002`). This section
records the confirmatory collection: **5 valid static + 5 valid closed-loop**,
all `duel_admissible: false` (cell C is confirmatory, never primary-duel data).
No verdict, no delta and no cross-cell figure appears here or was computed — the
only analysis output consulted was each run's own gate and exclusion state.

Preamble held before the first boot: `ROS_DOMAIN_ID=0`, 1-min loadavg **0.17**,
governor `powersave` (recorded, unchanged), no non-desktop GPU consumer
(Xorg / gnome-shell / browser / terminal only on the RTX 5090), no pre-existing
`UnrealEditor`/`CarlaUE4` process. `docker compose … down` + `up -d` +
`bootstrap_carla_msgs.sh` before every `run.sh` invocation, and the host was
drained to 1-min loadavg < 2 before each one.

| run | arm | outcome | filed as |
| --- | --- | --- | --- |
| `C/run-003` | static | warm-up (pre-registered discard) | excluded `warmup:nishi` |
| `C/run-004` | static | scored | not excluded |
| `C/run-005` | static | scored | not excluded |
| `C/run-006` | static | scored | not excluded |
| `C/run-007` | static | scored | not excluded |
| `C/run-008` | static | scored | not excluded |
| `C/run-009` | closed-loop | **armed but never drove — UNSCORED** | not excluded, **not valid** (see §8.2) |
| `C/run-010` | closed-loop | scored | not excluded |
| `C/run-011` | closed-loop | scored | not excluded |
| `C/run-012` | closed-loop | scored | not excluded |
| `C/run-013` | closed-loop | scored | not excluded |
| `C/run-014` | closed-loop | scored (make-up for `run-009`) | not excluded |

### 8.1 The criterion-5 warm-up, and why it is charged once per session

`exclusions.md` criterion 5 reads "Nishi-Shinjuku **first run after a CARLA
boot**". Taken to the letter that would exclude *every* cell C run, because
`teardown.sh` stops the editor and runs `docker compose down` at the end of every
run, so `run.sh --runs N` boots CARLA N times. The campaign's operative reading —
established in Task 4, where `C/run-002` was accepted immediately after the
`C/run-001` warm-up under exactly this per-run boot behaviour — is **one warm-up
per session cold start**, the state the 107 s cold-start lag of P1 Verdict 5
actually lives in (shader/DDC and page-cache warmth, which survives an editor
restart). `C/run-003` is this session's warm-up and is excluded `warmup:nishi`,
verbatim from criterion 5.

The warm-up was run on the **static** arm while the runs it precedes span both
arms. That is sound because criterion 5's requirement is that "the warm-up run
spawns the exact sensor suite", and the sensor suite is arm-independent:
`cells/extension.sh` derives `SPAWN_ARGS` from `BENCH_ROUTE_FILE` alone (:116),
and `BENCH_ARM` reaches only `LAUNCH_ARM` (:139), never the spawn.

### 8.2 `C/run-009`: armed, never drove, unscored — and NOT excludable

`run-009` reached `ARMED: localized, route set to (81571.616, 50019.827),
autonomous engaged`, and the harness's own gate printed `OK:
/control/command/control_cmd is flowing`. It then did not move:

| run | GT rows | max GT displacement from spawn |
| --- | --- | --- |
| `C/run-009` | 3245 | **0.000 m** |
| `C/run-010` | 3172 | 231.242 m |
| `C/run-011` | 3169 | 231.250 m |
| `C/run-012` | 3171 | 231.209 m |
| `C/run-013` | 3170 | 231.180 m |
| `C/run-014` | 3172 | 231.183 m |

#### The M5 gate's refusal, verbatim

The refusal text is **not** in the run directory: `write_quality` declines to
write anything rather than write a partial `quality.json`, and the reason goes to
the harness's stdout, which is not a filed artifact. It is transcribed here so
the record — not a temp file — carries it. Steps 13–14 of `run-009`, verbatim:

```
13. M5 gate: write quality.json (pose_error, goal, NDT rate, G1 ladder)
      $ python3 -m benchmarks.scripts.write_quality --run-dir .../benchmarks/results/C/run-009
QUALITY GATE FAIL: cannot resolve the closed-loop spatial window: no odometry sample inside the spatial window
WARN: the M5 gate did not score .../benchmarks/results/C/run-009 (named reason above);
      no quality.json is written, so its consumers fail loudly

14. exclusions: clock stall, short unpaced window, silent control gate
      $ if .../benchmarks/results/C/run-009/clock_stall.marker exists: write_manifest --exclude 'stall:clock'
      none
```

(Absolute paths abbreviated to `...`; nothing else altered.) Step 14 printing
`none` is the harness declining, on its own, to exclude the run — see the
adjudication below.

**FOR ANY CONSUMER OF THIS CELL:** `C/run-009` is the one run in cell C that is
`excluded: false` **and** has **no `quality.json`**. Iterating cell C's unexcluded
runs and assuming a `quality.json` exists **will fault on it**. That is the
harness's intended fail-loud behaviour and must be special-cased explicitly —
filtering on `excluded` is not sufficient for this cell.

The arm log names the proximate condition: `is_autonomous_mode_available=False`
pre-engage, `change_to_autonomous` refused five times with "The target mode is
not available. Please check the diagnostics.", then the documented
`/autoware/engage` fallback took, and post-engage the gated control output was
present but **commanded nothing** — `control_cmd_hz~7.67 n=23
nonzero_longitudinal=0/23 frac=0.000 peak_abs_velocity=0.000` — at less than half
the rate every other run of this collection reached. Post-engage arm
observations, verbatim from each run's `arm.log`:

| run | post-engage control command |
| --- | --- |
| `C/run-009` | `control_cmd_hz~7.67 n=23 nonzero_longitudinal=0/23 frac=0.000` |
| `C/run-010` | `control_cmd_hz~19.67 n=68 nonzero_longitudinal=62/68 frac=0.912` |
| `C/run-011` | `control_cmd_hz~19.67 n=65 nonzero_longitudinal=61/65 frac=0.938` |
| `C/run-012` | `control_cmd_hz~19.67 n=68 nonzero_longitudinal=62/68 frac=0.912` |
| `C/run-013` | `control_cmd_hz~19.67 n=66 nonzero_longitudinal=61/66 frac=0.924` |
| `C/run-014` | `control_cmd_hz~19.67 n=67 nonzero_longitudinal=62/67 frac=0.925` |

`run-009`'s preflight loadavg was **1.56**, the *lowest* of the five, so host
load is not the explanation. **The root cause is not established here** — this
section records what the run did, not why.

#### Root-cause LEAD — the NDT pose rate collapsed. NOT TESTED.

`C/run-009/report.md:33` records `/localization/pose_estimator/pose_with_covariance`
at **8.35 Hz, p95 298.60 ms**, against 19.96 Hz / ≈53 ms on every other cell C
run ever filed:

| run | NDT pose Hz | p95 ms |
| --- | --- | --- |
| `C/run-009` | **8.35** | **298.60** |
| `C/run-002` | 19.96 | 52.98 |
| `C/run-010` | 19.96 | 53.01 |
| `C/run-011` | 19.96 | 53.22 |
| `C/run-012` | 19.96 | 53.26 |
| `C/run-013` | 19.96 | 53.63 |
| `C/run-014` | 19.96 | 52.63 |

The collapse is **specific to the pose estimator**. In the same run,
`/sensing/lidar/top/pointcloud_raw_ex` ran 19.95 Hz, `/localization/kinematic_state`
19.95 Hz and `/control/command/control_cmd` 19.95 Hz — the sensor input and the
downstream consumers were all nominal, so this is not a general stack slowdown.

**Why it is a lead:** a localization output arriving at 8 Hz with a 299 ms p95
is a plausible source of the `is_autonomous_mode_available=False` that made
`change_to_autonomous` refuse five times, and of a control path that then
commanded zero. **It is NOT asserted as the cause.** Nothing here tests the link:
no diagnostic was run against the run's localization stack, the direction of
causation is unestablished (a degraded NDT rate could equally be a *symptom* of
the same upstream condition), and `run-009` has no `quality.json`, so its
`ndt_rate_ratio` — the registered M5 rate input — was never computed. Recorded so
a later reader starts here instead of at the arm log.

**It is filed unexcluded and it is not counted.** No `exclusions.md` criterion
1–10 matches, and none was stretched to fit:

- Criterion 2 covers `gate:control_cmd-silent`, "the gated control command never
  flowing after a successful engage". Here it *did* flow, at 7.67 Hz over 23
  samples — all-zero longitudinal is not silence, and `run.sh` step 14 correctly
  declined to fire the exclusion.
- Criterion 1 does not apply: nothing crashed, `up` succeeded, teardown reported
  a stopped tree.
- There is deliberately **no quality-based criterion**. A run that fails to drive
  is a *failing run*, not an excludable one.

This is the "neither valid nor excludable" state registered as a carry-forward
risk after Phase 0 (`B/run-025`, `B/run-026`), now observed once on cell C on a
run with **no** diagnostic intervention in it. It is left exactly as the harness
filed it — nothing hand-written, nothing deleted — and `C/run-014` was collected
as the make-up run so the closed-loop arm reaches n = 5 valid.

### 8.3 Batch aborts: `run.sh --runs N` has no inter-run pacing

`scripts/duel.sh` owns the campaign's pacing floor and load top-up; `run.sh`'s
own `--runs N` loop has neither, while `preflight.sh` hard-refuses at 1-min
loadavg ≥ 8 (criterion 6). A closed-loop run leaves the host near loadavg 17, so
the chained batch aborted twice at the next run's preflight:

```
PREFLIGHT FAIL: hostload:17.05 (1-min loadavg >= 8; exclusions.md criterion 6)
PREFLIGHT FAIL: hostload:13.45 (1-min loadavg >= 8; exclusions.md criterion 6)
```

Both aborts landed at step 3, **before** the run directory exists, so each left
no directory and no `hostload:` exclusion — the header contract ("an abort before
step 4 leaves no run directory at all") held, verified against `ls
benchmarks/results/C/`. Collection resumed with the remaining `--runs`, as the
plan's resume rule directs. The static batch chained all five without aborting;
a static run sheds load faster than a closed-loop one.

### 8.4 Measurement condition disclosed: preflight loadavg spread

Because `run.sh` does not pace, the runs inside a chained batch started at higher
residual load than the runs that opened an invocation. Per-run preflight loadavg
as filed in each manifest's `placement.loadavg`:

| run | 004 | 005 | 006 | 007 | 008 | 009 | 010 | 011 | 012 | 013 | 014 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| loadavg | 1.47 | 4.43 | 3.13 | 4.68 | 5.38 | 1.56 | 5.31 | 1.63 | 1.67 | 5.24 | 1.84 |

Every value is under `preflight.sh`'s registered gate of 8 and under `duel.sh`'s
registered pacing target of 6, so all of them were collected inside the
campaign's own registered host-load conditions. The spread is recorded here
rather than corrected, because correcting it after the fact would mean choosing
which runs to keep on a condition that is not a pre-registered exclusion.

### 8.5 Integrity pass

Task 5 Step 2 semantics, over every `benchmarks/results/C/run-*`: manifest
validates through `analysis.manifest.load_manifest`, `quality.json` present,
watchdog marker (`clock_stall.marker`) absent, exclusion reason (where present)
verbatim from the `exclusions.md` vocabulary — plus, for the closed-loop arm,
engage recorded in `arm.log` and `goal_closest_approach_m` non-null.

All fourteen of cell C's runs (`run-001`…`run-014`) pass every check except
`C/run-009`, which fails `quality_json_present` and
`goal_closest_approach_m_non_null` for the reason in §8.2. Both filed exclusions
read `warmup:nishi`, verbatim from criterion 5.

**Valid, excluding warm-ups and exclusions: 5 static (`run-004…008`) and 5
closed-loop (`run-010`, `run-011`, `run-012`, `run-013`, `run-014`).** Task 4's
`C/run-002` remains a valid, unexcluded closed-loop run in the same pool but is
bring-up class and is not counted toward this task's five.

### 8.6 Two artifact discrepancies inside cell C, both disclosed as sound

Neither matches an exclusion criterion and neither was acted on. They are
recorded so a later reader does not have to re-derive them.

**`C/run-005`'s `gt.log` is 0 bytes.** All thirteen sibling runs carry the same
251-byte line (`gt base_link anchor: +0.00000000 m (body frame) for approach
'extension' carla client=0.10.0 server=0.10.0 counting 1 LiDAR…`), which is the
GT collector's own anchor and publisher-count cross-check. On `run-005` the file
is empty. **The run itself is sound**: `gt.csv` is complete at 1383 rows,
`publisher_counts.json` is well-formed, and the run scored (`gate_pass: true`).
So the loss is confined to the collector's log line, not to its data, and no
criterion 1–10 applies — in particular not criterion 9 (`crash:collect_gt`), which
covers a recorder that "exits during start-up, before it has recorded anything
usable", and this collector recorded 1383 usable rows. Note this is the same
*class* of gap already recorded as a Task 4 deferred minor for the E-family
(0-byte `gt.log` with a populated `gt.csv`), now seen once on the extension
family.

**`harness_git_sha` is not uniform across cell C, and that is immaterial.**
`C/run-001` and `C/run-002` (Task 4) record `1f439144d696ba031ec46ecfc08f6795efb8ef76`;
`C/run-003`…`C/run-014` (Task 7) record `4f7aa68dc61870e6267040cefb79778f9607f1aa`.
Every one is clean — no `-dirty` suffix — so no run straddles a mixed tree.
Verified rather than assumed: outside `benchmarks/results/` and
`benchmarks/evidence/`, the entire `1f43914..4f7aa68` range changes exactly three
files — `benchmarks/cells/tier4_autoware.sh`, `benchmarks/injector/republish_vector_map.py`
and `tests/benchmarks/test_vector_map_gate.py` — all of which are the cells B/D
vector-map work. Cell C's own path is **byte-identical** across the two shas:
`benchmarks/cells/extension.sh` (C's launcher), `benchmarks/run.sh`,
`benchmarks/scripts/preflight.sh`, `benchmarks/scripts/write_quality.py`,
`benchmarks/scripts/teardown.sh`, `benchmarks/config/cells.yaml`,
`benchmarks/config/exclusions.md`, `benchmarks/config/margins.yaml` and all of
`benchmarks/analysis/`. `run.sh` dispatches `cells/$approach.sh`, and cell C is
`approach: extension`, so `tier4_autoware.sh` is never on its path. The two shas
are therefore the same measurement code for this cell.

## 9. Task 8 bridge-cell collection: E0 and E (live, 2026-08-01)

The campaign's last collection task. Two sections: **9.1–9.4 are the
PRE-REGISTRATION**, written and committed *before the first scored E-family
boot*; 9.5 onwards is what the collection then produced. The ordering is the
point, and it is checkable from the git history rather than asserted here: the
commit carrying 9.1–9.4 and the `cells.yaml` registration precedes every
`started_at_ns` filed below.

### 9.1 Cell E's closed loop is NOT collected — the recorded downgrade applies

Task 4 settled this and it is not re-litigated or retried here. `E/run-009`
reached `mode=2 autonomous=True is_autoware_control_enabled=True` and then failed
on the gated control command (`control_cmd_hz~0.00 n=0`), excluded
`gate:arm-failed`. Its failing link is named in §7.4 and is **the route**:
`behavior_path_planner: waiting for route` persists 63.98 s past
`set_waypoint_route`, `waiting for map` never appears at all, and the downstream
`Waiting for trajectory data` / `Control is skipped since input data is not
ready` follow from it. That is a *different* failing link from cell B's map, so
one diagnosis does not unblock both.

**The recorded wording, which is the deliverable rather than silence:** cell E's
pre-registered **static-only downgrade** applies. Cell E is collected on the
`static` arm only; its `closed-loop` arm produces no P3 data, and the campaign
records the reason above rather than an absent row. This is a **spec outcome, not
a blocker** — the downgrade was registered in advance precisely so this case
would not need a decision taken after seeing a failure. Cell E0 was already
`arms: [static]` by its own registration, so the two cells collect the same arm
for two different reasons, and the record keeps them apart.

Consequence for the matrix: **C2's closed-loop evidence for the python-bridge
approach is structural, not measured.** Nothing in this record may be read as the
bridge having been measured closed-loop and found wanting; it was never measured
closed-loop at all, because it could not be armed.

### 9.2 The grounding: what was registered, from what, and why it is independent

`cells.yaml` left `lidar_expected_hz`, `ndt_expected_hz`, `ladder_branch` and
`abs_pose_gate_m` null for **both** E and E0, so the M5 gate refused to score
them and **no E-family run had ever produced a `quality.json`** (§7.5). That file
also pre-registered the *procedure* for closing the gap — "re-grounded live …
**before any E-family P3 run**", and "which pcd variant E localizes against is
MEASURED first". A measurement-derived threshold is therefore the design; what
the no-tuning rule forbids is deriving one from a **scored** run. Every input
below is either a committed constant or a **bring-up-class** artifact
(`duel_admissible: false`), and no E-family run had been scored when this was
written, so the two are not in tension.

**Registered values:**

| cell | `lidar_expected_hz` | `ndt_expected_hz` | `ladder_branch` | `abs_pose_gate_m` |
| --- | --- | --- | --- | --- |
| E | 20.0 | 20.0 | `relative` | null |
| E0 | 10.0 | 10.0 | `relative` | null |

**The rate derivation.** A python-bridge cell's as-emitted rate is fixed by two
committed numbers and one mechanism, read out of the pinned images
(`bridge-bench:latest` = `sha256:b734b9af…b4123`, `bridge-bench-patched:latest` =
`sha256:6d65be77…e14220`, both matching `pins.yaml`'s `local_digest` on
2026-08-01):

1. the bridge sets **no `sensor_tick`** on the LiDAR blueprint —
   `modules/carla_wrapper.py`'s `_configure_lidar_attributes` sets only `range`,
   `rotation_frequency`, `channels`, `upper_fov`, `lower_fov`,
   `points_per_second` — so the CARLA sensor fires on **every world tick**, i.e.
   at the already-registered `tick_hz` of 20.0;
2. the bridge throttles **publication** in its own code: `carla_ros.py`'s
   `checkFrequency()` → `sensor_manager.should_publish()` returns
   `time_diff >= (1.0 / sensor.frequency_hz)` on `self.timestamp`, which is
   **sim** time and deliberately so ("Uses simulation time (self.timestamp) for
   all sensors to ensure correct throttling in synchronous mode").

A sim-time threshold evaluable only on tick boundaries fires every
`ceil(tick_hz / frequency_hz)`-th tick, so the as-emitted rate is
`tick_hz / ceil(tick_hz / frequency_hz)` — the divisor-quantized analogue of the
`min(1/sensor_tick, tick_hz)` relation cell A registers.

`frequency_hz` for each cell is a constant **committed in this repo**, not a
transcription: `patches/python-bridge/0002-sensor-config-harmonized.patch` holds
E0's on its `-` side (`frequency_hz: 11`) and E's on its `+` side
(`frequency_hz: 20`), and `cells/python-bridge.sh` refuses to run either cell
against the other's image, in both directions. So E is
`20.0 / ceil(20/20) = 20.0` and E0 is `20.0 / ceil(20/11) = 10.0`.

**The raw `frequency_hz` is deliberately NOT what is registered.** E0's shipped
11 is a rate a 20 Hz tick cannot produce, so registering it would cap
`achieved_rate_ratio` at 0.91 by arithmetic alone — the silent-wrong-number class
`cells.yaml`'s own header exists to prevent. `rotation_frequency` does not enter
either: on this blueprint it governs points per revolution, not frame cadence.

**Corroboration, on bring-up-class data only.** `E/run-009` records
`/sensing/lidar/top/pointcloud_raw_ex` at **19.969 Hz** over a 65.50 s span of
header stamps (n = 1309); `E0/run-001` records
`/sensing/lidar/top/pointcloud_before_sync` at **9.983 Hz** over 57.70 s
(n = 577). Both match the derivation to within 0.16 %. This *corroborates*, it
does not derive: the numbers above come from the patch file and the tick.

**Read the header-stamp rate, not the arrival rate — and this resolves the
apparent 8.59 Hz discrepancy** the old `cells.yaml` note recorded ("P1 measured
8.59 Hz as-emitted on an unpatched run, which is a MEASUREMENT, not a target").
It was an *arrival* rate. The bridge is a Python publisher that does not deliver
in wall-clock step with the sim, so its arrival rate sits below its sim-stamp
rate — `E0/run-001`'s `report.md` says 8.42 Hz for exactly the rows whose header
stamps say 9.983. That gap is a transport **result** this cell family exists to
expose, and it is what `achieved_rate_ratio` and `one_hop_wall_ms` report.
Absorbing it into the denominator would make the shortfall unmeasurable by
construction, so the old note is superseded rather than contradicted.

**The ladder branch.** Selected from **the bundle the cell mounts**, which is the
pre-registered rule (README, "M5 definitions") and which that README already
names for this family: "the unshifted `~/autoware_map/town10` that
`cells/python-bridge.sh` pins for the E family". Four independent confirmations,
all predating any E-family P3 run:

- `cells/python-bridge.sh`'s committed literal
  `MAP_BUNDLE_HOST="$HOME/autoware_map/town10"`;
- `scripts/bundle_pin.py`'s `BUNDLE_REGISTRY`, which maps that directory to
  `autoware_contents.town10_pcd_sha256`, and whose `APPROACH_BUNDLE_DIR` entry
  already records that resolving E through `map_defaults.sh` would report
  `town10_pcd_regen` — "the wrong bundle";
- preflight's per-run `map_bundle_pin` placement key, which reads
  `autoware_contents.town10_pcd_sha256` in every E-family manifest **that
  carries the key at all** — every `E0` run, and `E/run-009` onward. It is
  ABSENT from `E/run-001`…`E/run-008`, which predate the key. (An earlier
  revision of this line claimed "every filed E-family manifest", which is
  false for those eight and is corrected here rather than dropped. The
  correction does not weaken the selection: the key agrees on every manifest
  that has it, none disagrees, and the other three confirmations do not depend
  on it.);
- the bundle's own bytes, verified live 2026-08-01:
  `sha256(~/autoware_map/town10/pointcloud_map.pcd)` =
  `7ed7890ebe983b324758835336264dcc6b7f736e51498101262e91de49eee95b`, the
  unshifted digest — **not** `town10_pcd_regen`.

That bundle is by definition the one carrying the offset the ladder exists to
correct: `pins.yaml`'s `town10_pcd_shifted` describes itself as correcting "the
+0.475 m cross-track offset the P1 seed sweep localized to this file", and the
two rigid re-registrations *of* it measured max 0.824 m and 0.570 m — both over
the 0.5 m gate. So README branch **(b)** applies: no drift (|mean of last 20 % −
mean of first 20 %| < 0.2 m) and p95 − p50 < 0.3 m, with the constant bias
reported. `abs_pose_gate_m` stays null, and `write_quality.resolve_ladder`
*refuses* a relative branch carrying a threshold rather than ignoring one.

This is the outcome `cells.yaml`'s header block predicted in as many words:
"gating cell E at 0.5 m against the deliberately unshifted bundle
`cells/python-bridge.sh` pins would fail it by ~0.475 m of map registration,
under a reason a reader would attribute to the bridge."

Nothing in the branch selection came from a pose series: the bundle is identified
by **content hash**, which is the same route cell B's selection took.

### 9.3 Two consequences stated BEFORE the runs, so neither can read as tuning

`ndt_expected_hz` is registered as the **sensor** rate on cell B's rule and
`cells.yaml`'s header — "one NDT pose per input cloud is the target", and a chain
that decimates must **fail** the M5 NDT-rate criterion "instead of hiding inside
a lower expectation". Applying that rule to this family has two consequences that
are written down here, in advance, rather than discovered afterwards:

1. **Cell E is expected to FAIL the M5 NDT-rate criterion.** `E/run-009` measures
   NDT at 8.943 Hz against its own 19.969 Hz input — a ratio of ~0.45 against the
   gate's 0.90. Registering ~8.9 would gate the cell at its own observed
   throughput, which is the tuning this campaign forbids, and would delete the
   finding. **20.0 records it.** The finding, stated plainly: *the bridge's
   localization chain does not sustain NDT at the cell's own sensor rate.*
2. **Cell E0 is expected to be UNSCOREABLE, and that is its registered result.**
   The as-shipped bridge publishes `is_dense=False` and Autoware's
   `crop_box_filter_self` rejects every cloud (README's named exception, P1
   Verdict 1), so NDT is structurally starved — `E0/run-001` measured 0.168 Hz,
   n = 10. At that rate a 60 s static window holds fewer than
   `quality.MIN_JOIN_PAIRS` NDT↔GT pairs, so the gate is expected to **refuse**
   by name and write no `quality.json`.

**A refusal is not an exclusion.** `exclusions.md` has no criterion for it — and
deliberately so, there being no quality-based criterion at all — so such runs
stay **valid and unexcluded**, and the absent `quality.json` is the registered
carrier of "not scored" (`write_quality`'s module docstring). Cell E0's row is
its transport and process cost plus that structural failure, exactly as its own
`arms: [static]` registration describes.

### 9.4 GT-anchor gap closed: the applied anchor is now filed per run

§7.5 recorded that every python-bridge run filed a **0-byte `gt.log`** beside a
fully-populated `gt.csv`, so the family left "no filed record of which
ground-truth anchor was applied — the exact fact `1f43914`'s guard exists to
establish". Since this task relies on E's `pose_error` (the relative branch is a
criterion *on* `pose_error`), the gap is closed rather than disclosed and left.

**Root-caused by measurement, not by reasoning.** `collect_gt.py` prints its
anchor line and the client/server versions at start-up, but python's stdout is
**block-buffered** over a non-TTY pipe and `docker exec` is not a TTY here.
`run.sh` SIGTERMs `GT_PID`, which for this family is the host-side `docker exec`
**client** and not the in-container interpreter, so the buffer is never flushed
anywhere the redirect can see. Reproduced both directions against this image on
2026-08-01: a buffered exec killed after 4 s left **0 bytes**; the identical exec
with `PYTHONUNBUFFERED=1` left the line. The UE5 families never hit this because
their collector is a **host** process that receives the SIGTERM itself, runs its
handler and exits cleanly — which is why only this family was affected, and why
§8.6's single 0-byte `gt.log` on `C/run-005` is a *different*, unexplained
one-off rather than the same defect.

Fixed by adding `-e PYTHONUNBUFFERED=1` to `cells/python-bridge.sh`'s `GT_CMD`.
It is **observability only**: the collector prints three lines in total, none per
row, and `gt.csv` was already flushed per row.

**The anchor itself, stated independently of that fix.** The registered
`python-bridge` anchor is **−1.425 m** in the ego body frame
(`analysis/gt_anchor.py`: the bridge's `CoordinateTransformer` subtracts
`DEFAULT_WHEELBASE / 2 = 2.850 / 2` when it places sensors), and
`cells/python-bridge.sh`'s plan-phase guard re-reads `sensor_kit_loader.py` **out
of the image the run will use** and aborts the run on any drift. So the anchor
was already *enforced* on every filed E-family run; what was missing was only its
*record*. From this commit forward the value is filed in each run's own
`gt.log`, and §9.5 reports it per run.

### 9.5 What was collected

Every run below was driven one at a time by a pacing wrapper, never two harness
instances at once, and never `run.sh --runs N` — which has no inter-run pacing
against preflight's loadavg gate and aborted two of four invocations during cell
C. The wrapper waits for the host's 1-min loadavg to fall below **2.0** before
each run (preflight's own gate is 8) and settles afterwards. Every filed
manifest records `cpu_governor: powersave`, which was **recorded and never
changed**, and a start loadavg between **0.75 and 1.97**. All runs of this task
carry `harness_git_sha: e7ba92a` — the registration commit — so no run straddles
a mixed tree, and every one of them is **after** the registration, not before it.

All runs are `duel_admissible: false`, matching cell C's convention: `--duel` is
`scripts/duel.sh`'s declaration for the interleaved primary duel, and this is P3
cell collection.

**Cell E0 — `arms: [static]` by registration.** `run-001` is Task 4's; this task
filed `run-002`…`run-010`.

| run | outcome | exclusion | M5 gate |
| --- | --- | --- | --- |
| run-002 | valid | — | refused: 5 NDT↔GT pairs |
| run-003 | valid | — | **scored**, `gate_pass=false` |
| run-004 | valid | — | refused: 5 pairs |
| run-005 | excluded | `harness:e7ba92a` | not scored |
| run-006 | excluded | `harness:e7ba92a` | not scored |
| run-007 | valid | — | refused: 3 pairs |
| run-008 | valid | — | refused: 4 pairs |
| run-009 | excluded | `gate:arm-failed` | not scored |
| run-010 | excluded | `crash:cell-launch` | not scored |

**Valid static from this task: 5 (`run-002`, `run-003`, `run-004`, `run-007`,
`run-008`).** Target met.

> **TWO ITEMS THE WRAP MUST SETTLE FOR THIS ROW — neither is decided here.**
>
> 1. **Whether Task 4's `run-001` is pooled as a sixth E0 run.** It is valid and
>    unexcluded, sits in the same pool, and is a legitimate candidate — but it is
>    **bring-up class** (`duel_admissible: false`, filed before the §9.2
>    registration and on a different harness sha) and is **not** counted toward
>    this task's five. Pooling it is defensible and so is excluding it; this
>    section deliberately does not choose, and the wrap must **state which it
>    did** rather than leave the count ambiguous.
> 2. **§9.9 must be quoted INLINE beside this row, not merely cited.** Cell E0's
>    valid pool is *conditioned on NDT having emitted at least two poses*, so
>    these five runs are not a random sample of E0's behaviour. A reader who
>    meets this table without that caveat attached will read the row as
>    representative, which it is not.

**Cell E — static only, per the §9.1 downgrade.** `run-001`…`run-009` are the
stale Task 10 / Task 4 runs, all excluded, retained as history and not inputs.
This task filed `run-010`…`run-016`.

| run | outcome | exclusion | M5 gate |
| --- | --- | --- | --- |
| run-010 | excluded | `crash:cell-launch` | not scored |
| run-011 | valid | — | scored, `gate_pass=false` |
| run-012 | valid | — | scored, `gate_pass=false` |
| run-013 | valid | — | scored, `gate_pass=false` |
| run-014 | valid | — | scored, `gate_pass=false` |
| run-015 | valid | — | scored, `gate_pass=false` |
| run-016 | valid | — | scored, `gate_pass=false` |

**Valid static from this task: 6 (`run-011`…`run-016`)**, one over target
because the top-up batch was sized before `run-015` landed. **No cell-E
closed-loop run was attempted**, per §9.1.

`E/run-011` is the **first `quality.json` any python-bridge run has ever
produced** in this campaign (§7.5 recorded that none existed), and `E0/run-003`
is the first for the as-shipped bridge.

Both `crash:cell-launch` exclusions (`E0/run-010`, `E/run-010`) are criterion 1
and were filed by the launcher's 420 s readiness gate with its own diagnosis
attached: `/localization/kinematic_state never published within 420s **while the
sim clock kept advancing (so this is NOT the tick stall)**`, with an empty
`/localization/util/` node list — the `load_node` race the launcher documents,
not a bridge defect. That is criterion **1**, and the launcher's probe is what
rules out criterion 4 rather than an assumption.

### 9.6 Integrity pass

Per run: manifest validates through `analysis.manifest.load_manifest`; watchdog
marker (`clock_stall.marker`) absent; exclusion reason (where present) verbatim
from the `exclusions.md` criteria 1–10 vocabulary; `gt.csv` has data rows; and —
new for this task — `gt.log` records the applied `base_link` anchor.

`quality.json` presence is an **observation here, not a gate**, and the
difference is deliberate. It is a hard check on the UE5 families because a
scoreable run that produced no verdict is a defect there. On this family §9.3
pre-registered, before any of these runs booted, that cell E0's gate would refuse
for want of NDT↔GT pairs. So a missing `quality.json` is instead re-derived by
**running the gate again** and its refusal recorded verbatim; a run whose
refusal does not reproduce would fail the pass. None did.

**Every run this task filed passes**, except the two `crash:cell-launch` runs,
which fail `gt_csv_has_rows` and `anchor_recorded` for the same single reason:
the cell never came up, so the GT collector never ran. That is what a criterion-1
exclusion means and it is not a separate defect.

Among the retained stale runs, three fail `watchdog_marker_absent`
(`E0/run-009`, `E/run-001`, `E/run-006`) — see §9.10 — and the rest fail
`gt_csv_has_rows` or the closed-loop engage checks, all of them already-excluded
Task 10 runs whose failures are their filed exclusion reasons.

### 9.7 The grounding held: registered against measured

The §9.2 registration was committed before any of these boots. What the boots
then measured, on **header (sim) stamps**:

| cell | topic | registered | measured across this task's valid runs |
| --- | --- | --- | --- |
| E | `/sensing/lidar/top/pointcloud_raw_ex` | 20.0 Hz | 19.89, 19.95, 19.97, 19.97, 19.97, 19.94 |
| E0 | `/sensing/lidar/top/pointcloud_before_sync` | 10.0 Hz | 9.96, 9.97, 9.97, 9.98, 9.99 |

Eleven independent runs, every one within **0.55 %** of its registered value, and
the two cells separated by exactly the factor their two committed `frequency_hz`
values predict. The derivation in §9.2 — no `sensor_tick`, a sim-time publish
throttle, `tick_hz / ceil(tick_hz / frequency_hz)` — is therefore confirmed
rather than merely argued, and the confirmation is out-of-sample with respect to
the two bring-up runs it was corroborated on.

**The ladder branch is vindicated too, and this is the part that would have gone
wrong.** On the relative branch every one of cell E's six scored runs passes the
localization criteria (no drift, bounded spread); their `pose_err_max_m` runs
0.318–0.645 m, so **four of the six exceed 0.5 m**. Had the branch been
registered `absolute` at 0.5 m — the value cells A/B/C carry — those four would
additionally have failed the localization criterion, and they would have failed
it for the **map registration offset of the unshifted bundle**, under a heading a
reader would have attributed to the bridge. That is verbatim the failure
`cells.yaml`'s header block predicted, and the branch was selected from the
bundle's content hash **before** any of these numbers existed.

### 9.8 The M5 verdicts, and exactly what they do and do not say

| run | `ndt_rate_ratio` | `pose_err_max_m` | `pose_bias_m` | gate reasons |
| --- | --- | --- | --- | --- |
| E/run-011 | 0.253 | 0.376 | 0.083 | ndt rate ratio 0.25 < 0.9 |
| E/run-012 | 0.382 | 0.605 | 0.081 | ndt rate ratio 0.38 < 0.9 |
| E/run-013 | 0.090 | 0.318 | 0.076 | ndt rate ratio 0.09 < 0.9 |
| E/run-014 | 0.341 | 0.645 | 0.085 | ndt rate ratio 0.34 < 0.9 |
| E/run-015 | 0.242 | 0.605 | 0.087 | ndt rate ratio 0.24 < 0.9 |
| E/run-016 | 0.162 | 0.570 | 0.074 | ndt rate ratio 0.16 < 0.9 |
| E0/run-003 | 0.038 | 0.114 | 0.090 | ndt rate ratio 0.04 < 0.9 |

**Every scored run fails, and every one fails on exactly ONE criterion: the NDT
rate.** No run fails the ladder's drift or spread criterion. This is the outcome
§9.3 wrote down in advance, and the advance statement is what makes it evidence
rather than an artifact: the divisor was fixed by cell B's registered rule before
the runs, and it was **not** moved to the observed throughput afterwards.

**What this says:** the python-bridge's localization chain does not sustain NDT
anywhere near the cell's own sensor rate. On cell E the sensor delivers ~20 Hz
and NDT returns roughly a tenth to a third of it, per window.

**What it does NOT say, and must not be read as saying:**

- It is **not** a statement that the bridge localizes inaccurately. The ladder's
  localization criteria — the ones that measure that — **passed on every scored
  run**, and the constant bias sits at 0.074–0.090 m.
- It is **not** a comparison with any other cell. No cross-cell statement is made
  here and none may be inferred from these numbers; the duel wrap owns that.
- `ndt_rate_ratio` here is computed over the **scoring window**, not the whole
  run, so it is lower than a whole-run rate on a bursty series and the two are
  not interchangeable.

### 9.9 FINDING: cell E0's exclusion is CORRELATED WITH ITS OWN RESULT — and criterion 3's substance does not fit it

This is the most important caveat on cell E0's row and it is not a defect
introduced by this task; it is a property of the filing path that only shows up
on a cell this degraded. It carries **two** claims, and a reader quoting this
section must carry both: the sampling bias (item iii) **and** the
criterion-substance mismatch that produces it (items i–ii).

`E0/run-005` and `run-006` were excluded `harness:e7ba92a`. The mechanism,
diagnosed exactly: on each, NDT published **exactly one** pose for the whole run.
`benchmarks/report.py`'s `summarize_run` computes per-topic cadence through
`analysis/cadence.py`'s `inter_arrival_stats`, which raises `need >= 2 arrivals`
on a single sample; run.sh's step-15 smoke therefore fails, and its handler files
the run under criterion 3's catch-all.

Three things follow, and they must be kept apart.

**(i) The reason STRING is verbatim; the criterion's SUBSTANCE does not fit, and
this has to be named rather than softened.** `harness:e7ba92a` matches criterion
3's registered form exactly. But criterion 3 reads, in full, "Harness defect
discovered **and fixed** (the run was measured with a broken observer/injector)",
and on these two runs:

- **nothing was broken.** The observer recorded its full topic set, the sampler
  and GT collector ran to completion (`gt.csv` at 1148 and 1167 rows), and the
  sim clock never stalled. The run's data is intact.
- **nothing was fixed.** No harness defect was discovered or repaired in
  response; this task changed neither `report.py` nor `cadence.py` (see the
  refusal below).

What actually happened is narrower than the criterion describes: the step-15
smoke fails inside `analysis/cadence.py:28`'s `need >= 2 arrivals` — a **frozen**
file — because `report.py`'s `summarize_run` cannot express a topic carrying a
single message, and `run.sh:1014` then files `harness:<sha>` as the handler's
catch-all. One message is not a malfunction on this cell; it is **cell E0's
registered result in its sharpest form**.

This matters because `exclusions.md:51-52` states that "any exclusion not
matching 1-10 invalidates the campaign for that cell and requires a fresh cell."
So the gap between the matching string and the non-matching substance is exactly
the kind of thing a later reader must be able to see, and must not have to
re-derive.

**(ii) What makes it defensible, stated so it cannot be mistaken for
manipulation.** The `harness:<commit>` ⇄ criterion-3 mapping is **pre-registered
in the harness itself**, at `run.sh:1028-1029`: "`crash:` while the world is
being built (criterion 1), `harness:<commit>` once the data exists and only
finalization can still fail (criterion 3)." That mapping predates this task and
**was not touched by it**. Checkable: outside `benchmarks/results/`, the whole
range `9c0f8dd..a52bb6b` changes exactly five files —
`benchmarks/cells/python-bridge.sh`, `benchmarks/config/cells.yaml`,
`tests/benchmarks/test_cell_info.py`, `tests/benchmarks/test_sweep_verdict.py`
and `tests/benchmarks/test_write_quality.py`. `run.sh`, `report.py` and all of
`analysis/` are **byte-identical** across it. So the label was applied
**mechanically by committed code**, to a rule written before cell E0's data
existed, and not chosen after seeing which runs it would drop. The substance
mismatch is a property of the pre-registration, not an exercise of discretion
inside this task.

Whether that is enough to keep the cell, or whether `exclusions.md:51-52` bites
and cell E0 needs re-collecting under a widened criterion, is **NOT this task's
call** — it is a pre-registration question for the owner. It is recorded here so
the decision is taken knowingly.

**(iii) The exclusion is NOT independent of the measurement.** The runs the
filing path drops are precisely the runs where the as-shipped bridge performed
**worst**. The six other E0 runs are not a random sample of E0's behaviour: they
are E0's behaviour *conditioned on NDT having emitted at least two poses*. The
campaign registered "deliberately **no quality-based criterion**", and this is a
quality-based exclusion arriving through a registered criterion's back door.

**Any statement about cell E0's central tendency must carry this caveat.** The
excluded runs' data is retained in full and is the stronger evidence for E0's
registered failure, not weaker.

**Deliberately NOT fixed here, and the reason is the campaign's own rule.**
`analysis/**` is frozen, so `inter_arrival_stats` could not be touched in any
case; `benchmarks/report.py` is not frozen and could have been taught to skip
cadence for a single-sample topic. That was rejected: it would have changed
**which runs count as valid** in the middle of a collection, splitting cell E0
across two behaviours of the filing path, and a harness change that converts
excluded runs into valid ones is exactly the shape of tweak this campaign
forbids. The distortion is disclosed instead, which is where the decision
belongs.

Measured incidence, so the size of the effect is on the record rather than
implied: **2 of the 9 runs this task filed for cell E0**, plus the same
underlying starvation visible as gate refusals on 4 more (3, 4, 5 and 5 NDT↔GT
pairs against the required 10).

### 9.10 An unread clock-stall marker under an arm failure — and why criterion 2 still fits

**This section's claim was overstated in its first revision and is narrowed
here.** It previously argued that `E0/run-009` "should be" criterion 4. It should
not; criterion 2 is the better textual fit, and the filed reason is more
defensible than that revision implied. What survives is the *mechanism*, which is
worth recording on its own.

`E0/run-009` is filed `gate:arm-failed` (criterion 2), and its run directory also
carries a `clock_stall.marker` reading **"newest /clock arrival is 5.4 s old
(limit 5.0 s)"**. Both are true, and the ordering explains why only one is in the
manifest: the clock watchdog wrote the marker, then `arm_and_goal.py` failed at
run.sh **step 9**, whose `exclude_and_die` (`run.sh:762`) files the run
immediately — and **step 14 (`run.sh:910-913`) is the only place the marker is
ever read**. So run.sh's own stated priority there ("stall:clock wins over the
others: a frozen sim clock is the cause a short window or a suppressed control
output would be a symptom of") is not enforced on the earlier exit paths. That
asymmetry is the finding.

**Why criterion 2 nonetheless fits and criterion 4 does not.** Criterion 4 is
conditioned on the stall occurring "while the run was **armed**"
(`exclusions.md:19-20`). This run's arm **failed** — it never armed at all — so
criterion 4's own precondition is not met, whatever the marker says about the
clock. Criterion 2 covers "a pre-registered readiness check that must pass before
the scoring window starts did not", which is precisely what happened. The filing
is therefore correct on the text, not merely tolerable.

The causal reading still holds and is not withdrawn: the sim clock froze, nodes
on sim time stopped with it, `/localization/kinematic_state` could not sustain
5 Hz, and the readiness check failed. The clock stall is plausibly the **cause**
and the arm failure the **symptom** — but "cause" is not what the exclusion
vocabulary indexes, and criterion 4's armed-precondition is what settles it.

**Criterion 10 is excluded outright, and for a stronger reason than either.**
Criterion 10 (`stall:unpaced-window-cap`) is a clock that "advanced throughout
the run" and was merely **slow**, and it applies only to the `--unpaced` arm's
sim-time window. **Every run in this task is `arm: static`; none used the unpaced
arm, so criterion 10 could not apply to any of them**, and none was filed under
it. The criterion-4-vs-10 distinction the brief flagged is therefore applied
exactly: the one frozen-clock event is criterion 4's *phenomenon* (a frozen
clock, not a slow one), even though criterion 4's *precondition* rules it out
here.

**Not rewritten, deliberately** — and now for a better reason than the first
revision gave. The filed reason stays `gate:arm-failed` because it is the
textually correct criterion, not merely because rewriting would be revisionism.
The marker is committed alongside it, so the fuller causal story is recoverable
from the run directory itself — which is what this section makes findable.

**Two stale runs carry the same marker, from two different causes**, and they are
not conflated: `E/run-006` (`harness:7425084`) shows "newest /clock arrival is
5.1 s old", the same frozen-clock phenomenon; `E/run-001` (`gate:arm-failed`)
shows **"no /clock rows at all after 30 s grace"**, which is not a frozen clock
at all but the observer-transport defect the launcher now refuses outright (the
`lo`-pinned Cyclone profile discovering nothing against a Fast-DDS stack, §7.5
and the launcher's own transport matrix). The watchdog's two message forms
distinguish them; the exclusion vocabulary does not.

### 9.11 What the registration COST the test suite, and what replaced it

Recorded here rather than only in a test docstring, because it is a real
coverage loss and a reader auditing the registration should not have to find it
by reading tests.

`tests/benchmarks/test_sweep_verdict.py`'s
`test_main_on_an_unbound_cell_fails_clearly_when_lidar_expected_hz_is_unbound`
pins that `sweep_verdict.main` **refuses** a cell whose `lidar_expected_hz` is
null rather than substituting a plausible number (`tick_hz`, or another cell's
value). It had always been driven against a **real committed null**, and this
task consumed the last one:

- it ran on cell **B** until Task 13 registered B's rate from the launcher
  constant that task landed;
- it ran on cell **E** until this task registered the whole bridge family;
- and there is now **no committed null left that can drive it**. `--class` only
  resolves for the three cells `sweep_classes.applies_to` lists (A, B, E), and
  all three are registered. The four remaining nulls (`A-hf`, `B-hf`, `E-opt`,
  `CAL-seam`) belong to cells no sweep class applies to, so `cell_info.merge`
  rejects them before the binding is ever read.

So the null is now **injected** via `--cells-yaml`. That is **strictly weaker
evidence** than a real committed null: it pins the *refusal path*, not the
*registry*, and it would keep passing even if every cell in `cells.yaml` were
mis-registered.

**What compensates for it**, and why the net position is not worse:
`tests/benchmarks/test_cell_info.py` gained registry-side pins this task, and
they are stronger than what was lost because they check the derivation rather
than restate the value —

- the E/E0 rates are **recomputed** from
  `patches/python-bridge/0002-sensor-config-harmonized.patch`'s own
  `frequency_hz` lines through `tick_hz / ceil(tick_hz / frequency_hz)` and
  compared against `cells.yaml`, so a drifting patch or a hand-edited registry
  fails rather than passing;
- the two cells are asserted **not** to share a rate or a topic, which is the
  copy-one-cell's-rig-onto-the-other mistake `cells.yaml`'s E0 comment names;
- both are asserted onto the **relative** branch with a null threshold;
- and a **registry-wide** check requires every cell's `ladder_branch` /
  `abs_pose_gate_m` pair to be one of the three legal states — catching an
  inconsistent registration in the suite instead of at `write_quality` time,
  i.e. before it costs a live run rather than after.

`tests/benchmarks/test_write_quality.py`'s registry-wide ladder assertion also
gained a `selected_relative` set, so E/E0's branch is pinned from both sides.

---

## 10. The P3 wrap (Task 9, live 2026-08-01): the verdict, the deviations log, and the handoff to P4

**This section is written to be self-contained for a P4 reader.** The campaign's
published record is `docs/evaluation/p3-baseline.md`; the plan's own workspace
(`.superpowers/sdd/**`) is git-ignored scratch and is deleted when the plan
finishes, so **nothing P3 OWES P4 lives only there**. Everything below is in
this repository.

**One thing is NOT here and cannot be: P4's own scope.** It is registered
nowhere in this repository — `grep -c P4 benchmarks/README.md` returns **0**,
and `config/cells.yaml` has no transport axis (its `sweep_arms` are `paced` /
`unpaced` / `ablation`; `transport` appears only as a per-run recorded block).
Whoever runs P4 must re-derive or re-register it. This record deliberately does
not invent one: a scope authored by the wrap, after seeing P3's results, would
be exactly the after-the-fact pre-registration the campaign's no-tuning rule
forbids.

**"P4" means three things in this campaign and the referent must be fixed
before reading.** (1) **P4 the phase** — the next phase, deferred to a later
session; every bare "P4" in this section means this. (2) **P4 the Phase-0
probe** — the pre-declared "NDT rate with the relay stopped, vs >= 9.0 Hz"
whose failure selected branch (c); that is §6.1/§6.7's usage only. (3) A
confound-row label in `docs/evaluation/p3-baseline.md`, now **removed** — those
rows were relabelled `P3-1`..`P3-6` to end the collision.

No filed run was deleted, reclassified, re-scored or hand-edited by this task.
Nothing under `benchmarks/results/*/run-*/` changed.

### 10.1 The verdict, computed exactly ONCE

No verdict, delta or cross-cell median existed in this repository before this
task, and none is recomputed after it. One invocation, no filtering flags:

```bash
PYTHONPATH=. python3 benchmarks/scripts/duel_verdict.py A B | tee /tmp/p3-duel-verdict.md
```

Exit status 0. `--results` defaulted to `benchmarks/results`, `--margins` to
`benchmarks/config/margins.yaml`, `--min-n` to the pre-registered 10. **No
filtering flag is needed**: `duel_verdict.py` drops excluded runs and drops runs
that are not `duel_admissible`, on two separate counters, so the static pool is
the 10 pairs **by construction**. The counts it dropped are printed in the
table's own `notes` column.

Static arm, n = 10 per side (`A/run-003`…`run-012` × `B/run-013`…`run-022`):

| metric | Δ median (A − B) | 95% CI | margin | printed verdict |
| --- | --- | --- | --- | --- |
| `one_hop_wall_ms` | −6.281 ms | [−6.542, −5.828] | 2.0 | `a_better` |
| `lidar_to_ndt_sim_ms` | −5.817 ms | [−8.106, −4.976] | 5.0 | `a_better` |
| `control_staleness_ms` | — | — | 10.0 | `insufficient-data` (UNAVAILABLE) |
| `carla_process_cpu_pct` | −12.873 pp | [−16.698, −11.129] | 10.0 | `a_better` |
| `achieved_rate_ratio` | +0.104 | [+0.090, +0.114] | 0.02 | `b_better` |

M2 three-way reconciliation from the same invocation, static arm: cell A
`publisher_drop_rate` median 0.021 / max 0.385, `observer_loss_rate` median
0.000 / max 0.000; cell B `publisher_drop_rate` median 0.020 / max 0.022,
`observer_loss_rate` median 0.085 / max 0.108. Both cells' non-zero
`publisher_drop_rate` on this arm is the §1 teardown-ordering artefact, not a
real publisher loss.

Every closed-loop row is `insufficient-data` at n = 0/0.

**HEADLINE: on the static arm the two approaches are NOT equivalent on any
computable metric — no row returns `parity`, all four computable rows fall
entirely outside their pre-registered margin, and all four separate in the
extension's favour.**

**THE FOUR ROWS ARE NOT FOUR INDEPENDENT FINDINGS.** Three of them are
plausibly downstream of ONE condition — cell B's depressed NDT/transport
behaviour, for which Phase 0 eliminated a candidate cause and identified none.
`achieved_rate_ratio` **is** that deficit measured directly;
`lidar_to_ndt_sim_ms` is the sensor→NDT pipeline on the same chain, same cell,
same window; `one_hop_wall_ms` is the transport hop those samples traverse, and
the registered account of cell B's loss is a transport property (§4.1 here,
`benchmarks/README.md`'s A-side asymmetry bound, `CAL-rmw/PROVENANCE.md`).
`carla_process_cpu_pct` is the one row with a different measurand — the
simulator process's own CPU out of `resources.csv`, not the message stream — so
it is the least entangled. **No decomposition is attempted and none may be read
in**: this campaign does not hold the measurement that separates "the extension
is faster" from "cell B's transport is losing samples and every message-derived
metric sees it". The four rows jointly support the DIRECTION; they do not
support a count of four independent effects, nor any single row's effect size
read as an approach difference on its own. Full statement:
`docs/evaluation/p3-baseline.md` §4.2.

**Two further readings a later task must not get wrong.**

1. **`achieved_rate_ratio`'s `b_better` label is a polarity artefact, not a
   tier4-native win.** `benchmarks/config/margins.yaml`'s header registers
   `delta = extension - tier4-native; lower is better`, and
   `analysis/stats.py`'s `equivalence_decision` applies that convention
   uniformly. But `benchmarks/README.md:575-594` registers what this particular
   fraction is *for* — "Taken in the sim domain, the ratio measures dropped or
   skipped frames instead, which is what M2 is for" — so it is a **shortfall
   detector** against each cell's own `lidar_expected_hz` (20.0 on A, 10.0 on B),
   and **higher is better** on this metric alone among the five.
   `equivalence_decision` prints `b_better` exactly when the whole CI sits above
   zero, i.e. when median(A) > median(B), so Δ = +0.104 with CI [+0.090, +0.114]
   says **cell B falls 0.104 of its own registered target FURTHER SHORT than cell
   A does** — five times the margin, in cell A's favour. The direction follows
   from the printed sign; no new statistic is needed. The reconciliation row
   corroborates it independently on a different quantity: cell A loses **0.000**
   of its frames observer-side, cell B loses **0.085–0.108**.
   *Do not cross-read `benchmarks/report.py`'s `hz` column against this metric*:
   that column is an **arrival**-domain rate and `achieved_rate_ratio` is
   computed on **sim** header stamps, deliberately, so that RTF cannot land
   inside a 0.02 margin.
2. **`control_staleness_ms` is UNAVAILABLE, never zero and never parity.** Cell
   A's `control_published_time_topic` is `null` (`config/cells.yaml:132`, owed
   to Tasks 13/20, neither of which ran), so the metric is unbound for the whole
   duel and the tool says so without touching a run directory.

### 10.2 There is NO closed-loop equivalence verdict, and that is a result

**Cell B never armed closed-loop under its registered transport: 0 of 15 filed
runs, all excluded** — which is why the verdict tool's own closed-loop rows
print `15 run(s) excluded from B`.

**The two counts, reconciled, because an earlier revision of this section put
"0 of 14" and "fifteen excluded" in adjacent sentences without doing so.**
Recomputed from every manifest, 2026-08-01:

| class | n | runs | reached the arm? |
| --- | --- | --- | --- |
| `crash:cell-launch` | **7** | `run-001`…`run-006`; **`run-031` — carve-out below** | no — except `run-031`, which did |
| `crash:collect_gt` | **1** | `run-007` | no |
| `gate:arm-failed` | **7** | `run-008`…`run-012`, `run-028`, `run-032` | **yes**, and failed it |
| total, registered transport | **15** | all excluded | **0 armed** |
| deviation probe, not a cell-B measurement | 1 | `run-033` (cyclonedds) | **yes — ARMED** |

```bash
python3 - <<'PY'
import collections, json, pathlib
by_reason = collections.defaultdict(list)
for run in sorted(pathlib.Path("benchmarks/results/B").glob("run-*")):
    m = json.loads((run / "manifest.json").read_text())
    if m["arm"] == "closed-loop":
        by_reason[m["exclusion_reason"] or "NOT EXCLUDED"].append(run.name)
for reason, runs in sorted(by_reason.items()):
    print(f"{reason:20s} n={len(runs):2d}  {runs}")
PY
```

**CARVE-OUT: `B/run-031` is a delivery loss wearing a launch-crash label.** Of
the 8 crash-class runs, 7 genuinely never came up. `run-031` did: it produced a
**551 KB `tier4-autoware.log`** and a filed `vector-map-delivery.json` recording
`captured: true`, `data_bytes: 1305281`, `subscriber_count: 16`,
`matching_settled: true`, three re-publish attempts and
`verified: false, exit_code: 5` (`EXIT_NOT_VERIFIED`). The **delivery gate**
failed — fatal at the time — and `cells/tier4-native.sh up` failed as a
consequence, which is why it carries criterion 1. §7.9 already logged that
labelling ambiguity as housekeeping, and §7.8 records that this run's own log
shows the re-published map **being delivered** to `lanelet2_map_visualization`
and `vector_map_tf_generator` on all three attempts while the gate's endpoint
received none. So `run-031` belongs to the defect's evidence, not outside it.
**NOT TESTED: whether it would have armed** — the gate aborted before a route
existed.

**15** is how many closed-loop runs cell B filed and lost under its registered
transport; **7** is how many reached the arm. The other 8 are crash-class and
say nothing about the latched-delivery defect — they never got to where it
bites. §7.11's "0-for-14" and "the six `gate:arm-failed` runs" predate
`run-032` and are superseded by this table; `run-032` is the seventh
`gate:arm-failed`, blocked on the **route** (§7.10), which makes the blocker
tally **map 2 / route 4 / operation_mode 1**.

The mechanism is §7.11's
first-class finding — latched (`TRANSIENT_LOCAL`) messages, published once,
reaching `topic_state_monitor_*` promptly and `behavior_path_planner` not at
all, nondeterministically and per-topic (**map ×2, route ×4, operation_mode ×1**
across the **seven** runs that reached the arm), **reproduced standalone with no
CARLA and no harness**. The cyclonedds bounding probe `B/run-033` armed on the
first try and passed its gate.

**So the A-vs-B closed-loop equivalence verdict is NOT COMPUTABLE**, and this
task did not manufacture one.

**The attribution boundary of §7.11 is restated here because this is where a
P4 reader will meet it:** the defect is a property of **the as-shipped tier4
transport configuration on this host**. It is **NOT established as intrinsic to
the tier4-native approach** — the cyclonedds side is **n = 1**, Fast-DDS
version / kernel / loopback are uncontrolled, and this repository's own README
says in terms that the cyclone rows are not measurement-grade. This campaign has
caught three separate claims outrunning their measurements; this finding must
not become the fourth.

**Recorded, NOT acted on:** `B/run-033`'s `ndt_rate_ratio` is **1.000** against
**0.257–0.989** on every filed Fast-DDS cell-B run — the branch-(c) confound
absent on the one bring-up that changed only the middleware. **Owner ruling: an
n = 1 observation with its attribution boundary attached. Branch (c) is neither
reopened nor amended.**

### 10.3 The deviations log, complete

#### Branches not taken, and the tasks that did not run

| item | outcome | why |
| --- | --- | --- |
| Phase 0 branch **(a)**, relay removal | **not selected** | needs P4 NDT ≥ 9.0 Hz post-kill; best post-kill reading on any of four runs ≈ 0.07 Hz (§6.8) |
| Phase 0 branch **(b)**, concat suppression | **not selected** | trigger is "P3 fails: empty/malformed clouds"; P3 passed — well-formed, non-empty `base_link` clouds at 7.612 Hz |
| Phase 0 branch **(c)** | **SELECTED**, by elimination (§6.7, §6.8) | registered fix mechanism: **NONE** |
| **Task 2** — the branch-(a)/(b) fix | **SKIPPED** | conditional on (a)/(b); (c) fired and prescribes no harness change |
| **Task 3** — criterion-3 reclassification of B `run-013`…`run-022`, plus `--revoke-duel` on cell A's pair-halves | **SKIPPED** | same condition. A's static pair-halves therefore **keep `duel_admissible: true`** and B's ten stay filed and unexcluded — recorded explicitly so no later task applies the spec's "Consequence of (a)/(b) for the A pair-halves" paragraph by reflex |
| **Task 5** — 10-fresh-pair static recollection | **SKIPPED** | same condition; the pools stand exactly as filed |
| M5 gate threshold | **never touched** | 0.9 throughout, on every cell, at every point in P3 |

**And what branch (c) does NOT settle, stated plainly because the verdict
carries it: Phase 0 eliminated double publication as the cause of cell B's
depressed NDT rate; it did NOT identify a cause.** The gate was never tuned.
The root cause is **UNEXPLAINED** and the verdict is published carrying that
fact.

> **COUNT CORRECTION, and it corrects §4.1 of this file as well as an earlier
> revision of this section.** The split over the ten duel-admissible cell-B
> static runs (`run-013`…`run-022`), recomputed from every `quality.json` on
> 2026-08-01, is **1 pass / 8 fail / 1 unscoreable**:
>
> | outcome | n | runs | `ndt_rate_ratio` |
> | --- | --- | --- | --- |
> | `gate_pass: true` | **1** | `run-013` | 0.9892 |
> | `gate_pass: false`, all on `ndt rate ratio X < 0.9` | **8** | `run-014`…`run-018`, `run-020`…`run-022` | 0.2569–0.8505 |
> | unscoreable, no `quality.json` | **1** | `run-019` | — |
>
> So **eight fail, not nine**. §4.1 above says "Nine cell-B static runs fail
> the M5 gate, and all nine fail it on the same named reason", and its own
> table two paragraphs earlier already recorded `M5 gate_pass = true: 1
> (run-013)` — the two never agreed. §4.1 is left as written, per the
> convention that a claim stays in the record with the diagnostic that
> corrected it; **this is that diagnostic.** An overcount here overstates the
> pervasiveness of the campaign's central unexplained confound, which is why it
> is corrected rather than tidied away.
>
> **The ranges, stated correctly — the first version of this note mislabelled
> them.** It called `0.257–0.989` "every filed Fast-DDS cell-B run". It is not;
> it is the **duel pool's own** min–max over its nine scoreable runs, so it and
> `0.2569–0.8505` are ONE population differing only by whether the passing run
> is included. Recomputed from `quality.json`:
>
> | range | population | n |
> | --- | --- | --- |
> | **0.2569–0.8505** | the **failing** duel-pool runs | 8 |
> | **0.2569–0.9892** | all **scoreable** duel-pool runs (adds `run-013`'s pass) | 9 |
> | **0.0386–0.9892** | all scoreable filed cell-B **static** runs (`run-027`'s 0.0386 is the floor) | 14 |
>
> §7.11 uses `0.257–0.989` with the same "every filed Fast-DDS B run" label and
> carries the same mislabelling; the contrast it draws is unharmed, because
> `B/run-033`'s 1.000 sits above all 14. The count fix (eight, not nine) is
> unaffected. Reproduction command: `docs/evaluation/p3-baseline.md` §5.2.

#### The "neither valid nor excludable" gap — three runs, record only

`C/run-009`, `B/run-025`, `B/run-026`. Each ran to completion, matches **none**
of `exclusions.md`'s ten criteria, and could not be scored by the M5 gate, so
each is filed **unexcluded with no `quality.json`**.

**The frozen ten-criterion vocabulary has no category for "ran, was not
excludable, could not be scored."** There is deliberately no quality-based
criterion at all, and `exclusions.md:52-53` forbids editing the criteria after
the first P3 measurement run — so the vocabulary cannot be widened now either.

**Owner ruling: record only, freeze held.** No retroactive reclassification, no
criterion added or edited, no manifest touched. Any amendment is left to a future
campaign, where a pre-registration change belongs.

`C/run-009` is the load-bearing instance because it had **no** diagnostic
intervention in it (§8.2); `B/run-025`/`run-026` are the Phase 0 relay-kill
diagnostics, and `B/run-029` — a clean, un-intervened cell-B run — filed a
`quality.json` normally, which supports reading their absence as an artefact of
that intervention (§7.2).

#### Cell E0, criterion 3, and the ruling NOT to re-collect

`E0/run-005` and `run-006` are filed `harness:e7ba92a`. §9.9 establishes that
the reason **string** is verbatim from criterion 3 while the criterion's
**substance** does not fit: nothing was broken and nothing was fixed.

A strict reading of `exclusions.md:51-52` — "any exclusion not matching 1-10
invalidates the campaign for that cell and requires a fresh cell" — would
therefore require re-collecting cell E0.

**CONTROLLER RULING: cell E0 is NOT re-collected.** Four grounds:

1. **A fresh cell reproduces the identical filing.** The `harness:<commit>` ⇄
   criterion-3 mapping is pre-registered in committed code at
   `benchmarks/run.sh:1028-1029`, predates cell E0's data, and was not touched by
   any task that filed it (§9.9 (ii) carries the byte-identity check). Cell E0's
   NDT starvation is its **registered expected outcome**, written down in advance
   at §9.3. A fresh cell would starve the same way, fail the same step-15 smoke,
   and be filed under the same catch-all.
2. **The criteria may not be edited after the first P3 run**, so widening the
   vocabulary is not available either. Both doors are closed by the same
   pre-registration, which is what it is for.
3. **Owner ruling: record-only, freeze held** for this whole class — the same
   ruling that governs the three unscoreable runs above.
4. **Cell E0 is a bridge cell outside the duel.** No verdict, delta or margin
   decision rests on it.

#### Cell E0's published pool is FIVE runs, and `E0/run-001` is NOT pooled

§9.5 left this open and required the wrap to state which it did. **The wrap does
not pool `E0/run-001` as a sixth run.** Cell E0's published static pool is
`run-002`, `run-003`, `run-004`, `run-007`, `run-008`. Four grounds:

1. **`run-001` was collected under a different registration** —
   `harness_git_sha: 1f43914` against the pool's `e7ba92a`, the §9.2 grounding
   commit. When it ran, E0's `lidar_expected_hz`, `ndt_expected_hz`,
   `ladder_branch` and `abs_pose_gate_m` were all `null` and the M5 gate could
   not score the cell at all.
2. **Pooling it would make §9.9's bias WORSE — measured, not argued.**
   `run-001` carries **10** NDT poses, against the pool's 8 / 17 / 8 / 6 / 6 and
   the two dropped runs' 1 / 1. Adding it pushes an already-upward-biased pool
   further up.
3. It is **bring-up class** (`duel_admissible: false`), filed by the Task 4 smoke
   pass whose purpose was to prove a path, not to measure it.
4. **The campaign already resolved this exact shape the same way** — §8.5, on
   `C/run-002`.

`E0/run-001`'s measurements are reported **beside** the pool, never inside it.
And **§9.9 is quoted inline beside cell E0's row** in
`docs/evaluation/p3-baseline.md`, not merely cited, per §9.5's second item: any
central-tendency statement about cell E0 is optimistically biased by a mechanism
correlated with E0's own registered failure, and the bias cannot be estimated
from the surviving pool.

#### Cell E's closed loop, and what its absence does NOT mean

Not collected, per the pre-registered static-only downgrade (§9.1). **The
python-bridge approach's closed-loop evidence is STRUCTURAL, not measured.**
Nothing in this record may be read as the bridge having been measured
closed-loop and found wanting; it was never measured closed-loop at all, because
it could not be armed.

#### Measurement-condition deviations, all previously disclosed

Indexed here so the log is complete in one place; each is written up at the
section named.

| deviation | section |
| --- | --- |
| Static-arm `publisher_drop_rate` is a teardown-ordering artefact — symmetric across A and B, not a duel-margin metric, closed-loop arm immune, correct fix inside the frozen `analysis/` tree | §1 |
| `duel.sh` gained inter-run pacing mid-campaign — a dated amendment, not a transparent bugfix; `MAX_LOADAVG` and criterion 6 unchanged; pair 1's gap reconstructed, not recorded | §3 |
| The duel's first-slot alternation realised **A first in 6 of 10**, not 5/5, because of the pair-2 abort | §4.3 |
| A racy sidecar write left the Autoware stack up on **5 of 10** cell-B static runs; **no measurement was affected** and no run was invalidated; not fixed | §5 |
| `harness_git_sha` is not uniform, within cells or across them — even the duel pool spans `177256e` (pair 1) and `5a28339` (pairs 2–10) | §8.6, 10.4 |
| Two 0-byte `gt.log` classes: the python-bridge one root-caused and fixed (`PYTHONUNBUFFERED=1`); `C/run-005`'s a different, unexplained one-off with a complete `gt.csv` | §7.5, §8.6, §9.4 |
| Preflight loadavg spread inside chained cell-C batches (1.47–5.38), all under the registered gate of 8 and target of 6; recorded rather than corrected | §8.4 |
| `observer_topics/B.yaml` carries no `/map/vector_map`, so no filed run can answer the latched-delivery question from disk — it needed live probes | §7.1 |
| Load-sensitive test flakes, all `/proc/<pid>/cmdline` reads under host load; all pass idle; none silenced. **This task hit `test_teardown.py::test_tier4_autoware_sh_aw_sidecar_settles_on_the_post_exec_cmdline` TWICE** (`assert 'os.execv' in ''`, §7.11's form), both times while the host was shedding a `pre-commit run --all-files`: once at 1-min loadavg **42.68**, and once at 1-min **1.71** with 5-min **14.25** — so **the 1-min average alone is not a sufficient quiet signal for this test**. Gated on 1-min < 1.0 AND 5-min < 3.0 instead, nothing else changed: `test_teardown.py` **16 passed** in isolation and the full suite **1075 passed, 1 skipped**, the baseline as it stood then (the review wave since added 9 tests: current baseline **1084 passed, 1 skipped**) | §7.10, §7.11 |
| `benchmarks/report.py` exits 1 over the full results root, driven **entirely** by cell CAL-rmw, which has no simulator and therefore no `/clock`; `run.sh:996-997` takes the `BENCH_HAS_SIM_CLOCK != 1` branch for it and writes a one-line stub into each `report.md`. Not fixed, not suppressed. **NB `CAL-rmw/PROVENANCE.md:445-448` says `cal_report.py`'s output "is not committed as a file anywhere", so nothing under `results/CAL-rmw/` is `cal_report.py` output** — the cell's scored numbers live only in that file's p50 table and in `config/margins.yaml`'s `one_hop_wall_ms` block | `docs/evaluation/p3-baseline.md` §3 |

#### One deferred annotation, closed by this task

§6.6 recorded a refuted premise left in place in `scripts/e2e/launch_autoware.sh`
(cell A's relay) with its in-file annotation "deliberately deferred to the P3
wrap task", because cell A was about to carry hours of live duel collection and
line-shifting that file risked live runs for no gain. **All live collection is
complete, so the annotation is landed by this task** as a comment-only change
with no executable effect, with every in-repo line-number citation that shifts
with it corrected in the same commit. The cell-B-side counterpart comment in
`benchmarks/cells/tier4_autoware.sh` ("THAT PREMISE IS REFUTED") already
carries its own refutation and **its text is unchanged**.

**Separately, and recorded here because it touches cell B's launcher: the
review wave corrected two message defects in `tier4_autoware.sh`'s advisory
`/map/vector_map` block, and both are echo/comment text only.** (1) The "OK:"
branch said the step "completed", which reads as success — but under
`--advisory` the node's `_finish` returns `EXIT_OK` for **every** verdict it can
reach, so that branch is taken on `EXIT_NO_CAPTURE` too; it now says the step
RAN AND RECORDED A VERDICT and sends the reader to `verdict_code`. (2) The
`else` branch enumerated verdict codes 3/4/5 as things a reader might meet
there; with `--advisory` none of them can reach it, so it now names what
actually does — a process failure (crash, or the container command never
running). **No control flow changed and no measured configuration moved**; the
step is closed-loop-only and cell B's closed-loop arm is not collectable under
its registered transport (§10.2). `tests/benchmarks/test_vector_map_gate.py`
gained assertions that bite on both branches, verified by deleting the block
and confirming they fail.

#### The two standing owner questions, answered rather than posed

- **PR #29 stays in DRAFT.** The branch is pushed; the PR is not flipped to
  ready-for-review.
- **P4 is DEFERRED to a later session, and it WILL be run.** This record
  therefore hands off rather than closing the campaign — §10.4.

### 10.4 HANDOFF TO P4 — read this before collecting anything

#### The environment identity P4 must match, and it is verifiable

Every filed run records the identity of what produced it, so P4 need not take
the environment on trust. In `manifest.json`: **`carla_version`**,
**`autoware_image`**, **`patches_git_sha`**, **`harness_git_sha`**,
**`transport.dds_profile_sha256`**, and **`placement.engine_build_id`**.

P3's values on the duel pool: `carla_version` `0.10-fork` (cells A/C),
`0.10-tier4` (cell B), `0.9.15` (cells E/E0); `autoware_image`
`ghcr.io/autowarefoundation/autoware:universe-devel` on A/C and the same by
**digest** `sha256:5c22369a…e8ee` on B; `patches_git_sha` `ccff4f9` on **every
non-excluded run in the campaign** (it is NOT uniform over the whole tree: 20 of
the 102 filed manifests carry one of five earlier shas — `B/run-001`..`run-004`
`8aeed44`, `B/run-005`..`run-012` `31aac85`, `E/run-001`..`run-004` `ec998b4`,
`E/run-005`..`run-007` `b81200d`, `E/run-008` `4557e5c` — and **every one of
those 20 is `excluded: true`**, the stale pre-P3 runs retained as history);
`dds_profile_sha256` `1eeef31e…f2865` on the cyclone cells, `9886f744…65098` on
cell B, `""` on E/E0. The census that prints all six keys for every filed run is
in `docs/evaluation/p3-baseline.md` §9.1.

**PROVENANCE CAVEAT ON THE FROZEN MARGIN — disclosed, deliberately NOT
repaired.** `benchmarks/scripts/write_manifest.py:19-22` appends `-dirty` to
`harness_git_sha` and `patches_git_sha` when the working tree differed from
HEAD, and says why: without the suffix the field **asserts** a tie-back to the
exact code that scored the run, "which a dirty tree makes false". **Twenty of
the 102 filed manifests carry it on both keys**: `CAL-rmw/run-004`…`run-015`
(**12**, none excluded), `B/run-024`…`run-027` (4, none excluded, Phase 0
diagnostics) and `B/run-001`…`run-004` (4, excluded, stale pre-P3).

- **The verdict's INPUTS are clean.** Both duel pools — `A/run-003`…`run-012`
  and `B/run-013`…`run-022` — are clean on both keys, verified run by run.
- **What is not fully pinned is the code state behind the MARGIN the verdict is
  compared against**: 12 of the 15 CAL-rmw runs that `config/margins.yaml`'s
  `one_hop_wall_ms` margin was frozen from carry dirty shas. The measurement
  stands as filed; its code provenance does not.
- **Bounded by that margin's own arithmetic**: the derivation put 2 × |Δ| at
  0.83 ms against a pre-registered floor of **2.0**, and the floor binds for any
  |Δ| ≤ 1.0 ms — so the calibration would have to move by more than 2× before
  the margin could move at all. That bounds the exposure; it does not remove it.
- **NOT repaired**, for the campaign's own reason: `margins.yaml` is frozen and
  may not be re-derived after collection began, so re-collecting CAL-rmw could
  not be allowed to change the margin — the same self-defeating remedy as the
  cell E0 criterion-3 case. `margins.yaml` was not opened and no run directory
  was touched. **P4 should be aware of it**: a fully-pinned margin means a fresh
  calibration under a clean tree, registered in advance — not a retroactive
  repair of this one.

The census command in `docs/evaluation/p3-baseline.md` §9.1 abbreviates shas
**without slicing**, because `sha[:7]` structurally cannot surface a `-dirty`
suffix; an earlier revision of it did slice, and could not have shown any of
this.

**P4 MUST RE-VERIFY ALL SIX AT ITS START, before collecting anything.**
Cross-session drift in the fork build, the Autoware image, or the DDS profile
would make P4 **incomparable to P3** — and silently, because every one of these
can move without any run failing.

**Engine BuildId `4210e602-78ec-46e1-8f2f-03fadbe036a3` stays pinned, and
RELINK REMAINS FORBIDDEN.** `pins.yaml:247-259`: a `carla-unreal-editor` rebuild
in **any** tree relinks the shared engine and invalidates every tree that shares
it — "no further engine relink is permitted from here on (D8)".
`exclusions.md` criterion 8 excludes any run whose BuildId is found to mismatch
after start.

#### `harness_git_sha` MOVED during P3 — what that costs a P4↔P3 comparison

Three harness changes landed after the duel pool was collected:

1. **`1f43914`** — the python-bridge `set -u` fix: `cells/python-bridge.sh`'s
   base_link anchor guard sat 65 lines above the `IMAGE=` resolution it reads,
   so every python-bridge cell aborted `plan` with `IMAGE: unbound variable`.
   Moved **verbatim** below the resolution; what it checks did not change (§7.6).
2. **`a3ba158` → `2dbec06`** — the `/map/vector_map` re-publish step, added to
   `cells/tier4_autoware.sh` **on the closed-loop arm only**, then made
   **advisory** (§7.8, §7.9). `transport.dds_profile_sha256` is byte-identical,
   so cell B's filed runs stay transport-comparable, and the static path acquired
   no step.
3. **`0c869ef`** — the registered opt-in for a deliberate tier4 transport
   deviation (`BENCH_TIER4_TRANSPORT_DEVIATION`), which is what let `B/run-033`
   run at all (§7.11).

**Comparisons *within* P4 are unaffected.** **P4↔P3 comparisons must account for
the move.**

**The reviewed blast radius: cells B and D (the `tier4_autoware.sh` vector-map
work), cells E/E0 (the bridge grounding and the `set -u` fix), AND the shared
`scripts/e2e/` bring-up + teardown code that cells A and C run.** Across
`5a28339..269b931`, outside `benchmarks/results/` and `benchmarks/evidence/`,
exactly thirteen files change: `benchmarks/cells/python-bridge.sh`,
`benchmarks/cells/tier4_autoware.sh`, `benchmarks/config/cells.yaml`,
`benchmarks/injector/republish_vector_map.py`, `benchmarks/scripts/teardown.sh`,
`scripts/e2e/launch_autoware.sh`, `scripts/e2e/stop_launch_tree.sh`, and six
files under `tests/`.

> **CORRECTION (this section's first revision was WRONG, and it was P4-facing).**
> It said "cell A's and cell C's measurement paths BYTE-IDENTICAL" and counted
> **two** files on their path. **FOUR are on their path, and two of the four are
> EXECUTABLE changes.** Cells A and C are `approach: extension`, so
> `benchmarks/cells/extension.sh:192` launches `scripts/e2e/run_e2e.sh` →
> `scripts/e2e/launch_autoware.sh` → (on `--stop`, at `launch_autoware.sh:155`)
> `scripts/e2e/stop_launch_tree.sh`. Comment-stripped md5, `5a28339` →
> `269b931`: `launch_autoware.sh` **`07436b102c07` → `4797c56ecd45`** (+87/−2,
> the Task-18b fork/exec settle loop, which polls for up to ~5 s during
> bring-up) and `stop_launch_tree.sh` **`f4912c09ee75` → `917ec5a3d1ba`**
> (+54/−6). The other two on that path are inert: `teardown.sh`'s change is a
> one-line comment citation fix (`:311-316` → `:361`), and `cells.yaml`'s 206
> insertions leave every cell except E and E0 parsed-identical.
>
> **CONSEQUENCE: cell A and cell C DID NOT RUN THE SAME LAUNCHER.** Those
> `scripts/e2e/` commits (`3cf06ef`, `6d06608`, `2742dbf`, `161cf75`, `cdb22aa`,
> `7056a6e`, all 2026-07-31 evening) sit BETWEEN the two collections: cell A's
> duel pool ran `177256e` (`run-003`) and `5a28339` (`run-004`…`run-012`), both
> **before**; cell C ran `1f43914` and `4f7aa68`, both **after**. **The A-vs-B
> static verdict is unaffected** — A's pool is entirely pre-change and
> internally consistent, and cell B is `tier4-native`, which never reaches
> `scripts/e2e/`. **Any A-vs-C comparison must account for it.** Reproduction
> commands: `docs/evaluation/p3-baseline.md` §9.3.

What IS byte-identical across the whole span, enumerated rather than
generalised because the generalisation is what went wrong above — each verified
by `git show <rev>:<path> | md5sum` at both endpoints:
`benchmarks/cells/extension.sh`, `benchmarks/run.sh`, `scripts/e2e/run_e2e.sh`,
`benchmarks/scripts/preflight.sh`, `benchmarks/scripts/write_quality.py`,
`benchmarks/report.py`, `benchmarks/scripts/duel_verdict.py`,
`benchmarks/config/exclusions.md`, `benchmarks/config/margins.yaml`, and every
file under `benchmarks/analysis/`. **The analysis and scoring code did not move
at all**, which is the part the verdict rests on.

#### Cell B's closed-loop blocker will affect any P4 arm that tries to arm B

This is not a P3-only condition. Under cell B's registered transport
(`rmw_fastrtps_cpp` + `benchmarks/observer/config/udp_only.xml`, SHM off), the
§7.11 latched-delivery defect blocks the arm nondeterministically and per-topic.
**Cell B is 0-for-15** (§10.2's table). A P4 design that assumes cell B can be
armed will lose the runs it budgets for that. **Attribute the loss carefully:**
of P3's 15, the **7** `gate:arm-failed` runs are what this defect accounts for;
the other **8** are crash-class (`crash:cell-launch` ×7, `crash:collect_gt` ×1)
and were lost to bring-up — **except `B/run-031`, see §10.2's carve-out: it came
up, ran the delivery step, and is part of this defect's evidence.** The
per-topic
re-publish workaround fixes the **map** and **does not scale** — the route is
published *after* the planner starts by construction, so it can never use the
late-joiner path the map fix relies on, and `operation_mode` would need a third
(§7.11, "What was tried and did not work").

#### The transport question: what the repo HOLDS, and what it does not

§7.11's finding is bounded to the as-shipped tier4 transport configuration **on
this host** and is explicitly not attributed to the tier4-native approach.
Settling it needs a controlled transport comparison.

**An earlier revision of this paragraph said "P4 already carries transport as a
registered axis". IT DOES NOT, and the claim is withdrawn** — see the scope
note at the head of §10. Stated as fact instead: the campaign already built a
transport instrument and it is committed and frozen. Cell **`CAL-rmw`** holds 15
interleaved runs at the duel size across three DDS configurations (5 each,
visible as three distinct `dds_profile_sha256` values in the §9.1 census of
`docs/evaluation/p3-baseline.md`), and `config/margins.yaml`'s
`one_hop_wall_ms` margin was frozen from them (`p50_cyclonedds` 0.6840 ms,
`p50_fastdds-udp` 1.0993 ms; 2 × |Δ| = 0.83 ms, so the pre-registered 2.0 floor
binds — `config/margins.yaml`, `benchmarks/results/CAL-rmw/PROVENANCE.md`). A
later phase that reuses that cell and that margin inherits a measurement-grade
baseline rather than starting cold. `B/run-033` is a single non-duel bounding
probe, not a substitute for it.

Two things any later phase must **not** do with `run-033`: treat it as a cell-B measurement —
its manifest says on its face that its transport does not match `cells.yaml`
(`transport.rmw = rmw_cyclonedds_cpp`, `dds_profile_sha256 = ""`,
`duel_admissible: false`) — and read its `ndt_rate_ratio` of 1.000 as reopening
branch (c). Both are n = 1 observations.

#### One consumer trap P4 will hit if it iterates cell C

**`C/run-009` is `excluded: false` and has NO `quality.json`.** Iterating cell
C's unexcluded runs and assuming a `quality.json` exists **will fault on it**.
Filtering on `excluded` is **not sufficient** for this cell; special-case it
explicitly. Full statement, with the M5 gate's verbatim refusal: §8.2. Its
NDT-rate collapse (8.35 Hz against 19.95–19.96 elsewhere, pose-estimator
specific) is a **lead, NOT TESTED**, and must stay that way until something
tests it.

## 11. The registered relink round (P4 Task 9, 2026-08-03): engine BuildId moved, and why CAL-seam still cannot collect

This section is APPENDED, not a rewrite. §10's statement that "Engine BuildId
`4210e602-78ec-46e1-8f2f-03fadbe036a3` stays pinned, and RELINK REMAINS
FORBIDDEN" was accurate when filed and is left exactly as written; what follows
is the owner-authorized, singly-registered exception to it and its outcome.
Every filed manifest, `launch.log` and evidence document keeps `4210e602` —
those record what produced them.

### 11.1 What was authorized, and what it bought

D8 was lifted **once**, on 2026-08-03, for one reason: reviving cell **CAL-seam**
(P4 spec decision 6). CAL-seam measures the cost of the C-ABI seam by publishing
the same synthetic point cloud twice and pairing the two one-hop latencies —
`/bench/seam_cloud` from the out-of-tree extension `.so` (committed since
2026-07-30, `extension/src/publishers/BenchCloudPublisher.{h,cpp}`) against
`/bench/incore_cloud` from inside the CARLA fork process. The in-core half did
not exist. Creating it means new C++ in the fork, and new C++ in the fork means
one `carla-unreal-editor` rebuild, which by P1 Verdict 3 relinks the shared
engine for every tree that uses it.

The in-core twin is now committed on the extension fork
(`~/src/carla-autoware-integration`, branch `feat/autoware-seminative-phase-b`,
commit `5981f5168a0d87ffacddc4635f73e1373e185ad6`, "feat(ros2): add env-gated
bench in-core cloud publisher (CAL-seam)"). It is gated on
`$CARLA_BENCH_INCORE_CLOUD=1`, so with the variable unset a production run is
byte-identical to a build without it.

**The measurement-validity constraint was honoured and checked, not asserted.**
The twin calls `BlobCreatePublisher` / `BlobPublish` — the very functions the
extension's `host_.publish` vtable slot lands in — rather than the fork's
Fast-DDS `publishers/CarlaLidarPublisher` path. Had it used the latter, the
paired delta would have measured "Fast-DDS versus CycloneDDS, plus the seam" and
would have isolated nothing. Evidence: a `-M` dependency scan of the new
translation unit pulls **0** `fastdds/` or `fastrtps/` headers and **0**
`middleware/` or `publishers/Carla*` headers; the DDS it reaches is reached only
through the pure-C-ABI declarations in `ExtensionBlobEndpoints.h`. The template
message serializes through the fork's own `serialize_to_cdr` to **921 905 bytes**
and round-trips, with the field table taken from the shared
`kLidarFieldsExtended` rather than re-typed.

One residual confound is recorded rather than hidden: the two twins do **not**
share a serializer implementation and cannot — the extension side uses
`rosidl_typesupport_fastrtps_cpp`, which needs ROS 2 packages `carla-server` is
deliberately built without. Both are fastcdr emitting classic CDR v1
little-endian with the 4-byte encapsulation header, so the wire bytes are the
same format, but the emitting code differs and that difference sits inside the
measured delta. Any report quoting this instrument must say so.

### 11.2 The relink itself: converged in three rounds

| round | tree built (`carla-unreal-editor`)    | engine BuildId after |
| ----- | ------------------------------------- | -------------------- |
| —     | (before)                              | `4210e602-78ec-46e1-8f2f-03fadbe036a3` |
| 1     | extension `~/src/carla-autoware-integration` | `bc08ce19-f19c-46fe-808f-dbb2b0ddf41a` (bumped) |
| 2     | extension, post-commit rebuild        | `bc08ce19…` (held steady) |
| 3     | tier4 `~/src/carla-autoware-native`   | `bc08ce19…` (held steady) |

Converged: **5 of 5** manifests — the engine's, and both trees' project *and*
plugin `UnrealEditor.modules` — report `bc08ce19-f19c-46fe-808f-dbb2b0ddf41a`.
This reproduces the P1/Task-4 pattern exactly (an extension rebuild bumps it, a
tier4 rebuild holds it steady). `benchmarks/pins.yaml`'s `engine.build_id` is
re-pinned to the new value and **D8 is re-instated in the same commit: no
further engine relink is permitted for the remainder of the campaign.**

`TIER4_TREE=~/src/carla-autoware-native bash benchmarks/scripts/verify_tier4_artifact.sh`
**PASSES** (exit 0): `tier4_git_sha=6315b856f8faf2118578322eb20a2b902a45a384`,
`tier4_worktree=registered-patches`,
`tier4_plugin_sha256=26f95decb0b18dda86f73f6c1ebd2445a287d8dedde3f1cb1544bfffbd093c4e`,
`tier4_stale_ack=none`.

### 11.3 LIVE DEFECT: the extension tree's editor artifact cannot be rebuilt on this host, so CAL-seam is BLOCKED

`bash scripts/e2e/verify_editor_artifact.sh` **REFUSES** (exit 1):

```text
PREFLIGHT FAIL: /home/youtalk/src/carla-autoware-integration/Unreal/CarlaUnreal/Plugins/Carla/Binaries/Linux/libUnrealEditor-Carla.so (1784854960) is OLDER than HEAD commit (1785781990).
  -> rebuild target carla-unreal-editor before any live run.
```

**The remedy that check names does not work on this host, and that was measured,
not assumed.** `libUnrealEditor-Carla.so` in the extension tree is frozen at
2026-07-23 18:02. Three `carla-unreal-editor` builds were run from
`~/src/carla-autoware-integration` (rounds 1, 2 and 4) with full before/after
mtime snapshots of both trees' `Binaries` directories. All three wrote the same
26 files, split the same way every time:

- **20 files into `carla-autoware-integration`** — the monolithic game binary
  `CarlaUnreal`, the runtime DDS dependencies, and both `UnrealEditor.modules`
  manifests (which is why the BuildId converged);
- **6 files into `carla-autoware-native`** — `libUnrealEditor-Carla.{so,debug,sym}`
  and `libUnrealEditor-CarlaUnreal.{so,debug,sym}`.

That is: the shared engine's `UnrealEditor` editor-module state is bound to the
**tier4** tree. Under
`~/src/UnrealEngine/Engine/Intermediate/Build/Linux/x64/UnrealEditor`, **12**
files reference `carla-autoware-native` and **1** references
`carla-autoware-integration`. Both projects are named `CarlaUnreal.uproject`,
and the tier4 tree was the last one configured against this engine
(2026-07-27/28) — which also explains why the extension artifact's mtime stops
dead at 2026-07-23, the last date on which an extension-tree editor build
actually landed in the extension tree.

**The tier4 artifact is NOT contaminated, and that was checked rather than
assumed.** The `.so` those extension-tree builds write into the tier4 tree
carries **none** of the integration fork's extension-seam symbols
(`carla::ros2::MakeExtensionHost`, `carla::ros2::TeardownExtensionEndpoints`),
which the 2026-07-23 integration artifact does carry, and the tier4 source tree
has no `LibCarla/source/carla/ros2/extension/` directory at all. The file
written there is tier4-sourced.

**Consequence for CAL-seam.** The in-core twin is present in
`libcarla-ros2-native.so` (verified: `carla::ros2::BenchIncoreCloudInit()` and
`BenchIncoreCloudOnTick()` exported `T`) and referenced from `libcarla-server.a`
(verified: both `U`), and the freshly relinked game binary `CarlaUnreal` carries
those undefined references too. But `scripts/e2e/run_e2e.sh` launches the
**engine's `UnrealEditor`** against the integration `.uproject`, so the module a
live cell-A run loads is `libUnrealEditor-Carla.so` — the 2026-07-23 one, whose
`ROS2::Enable` and `ROS2::SetTimestamp` predate the twin. The twin would never be
constructed, and **the in-core side of the CAL-seam pair would be silently
empty** — a publisher that is simply absent, which downstream would read as "the
in-core path has no latency". That is the worst available failure for this
instrument, which is why this is filed as a blocker rather than worked around.

**How far back this reaches: checked, and the answer is "not at all".** The
obvious worry is that a frozen artifact means every extension-fork source change
since the freeze is missing from what cell A actually ran, which would put the
filed P3 cell-A results in doubt. It does not. There is **no fork commit between
the artifact's build time (2026-07-23 18:02:40) and the in-core twin commit**:
`ae166d80d` (the IMU sensor-frame fix) landed at 2026-07-23 17:55:28, about seven
minutes *before* the artifact was built, and nothing else landed on
`feat/autoware-seminative-phase-b` until 2026-08-03. Every filed cell-A result was
therefore produced by an editor artifact that matched its pinned fork revision,
and `extension_carla_fork.sha` = `ae166d80d` remains an accurate description of
that artifact. The only source change the frozen artifact is missing is the
in-core twin added today. No retroactive audit of P3 is required — but the defect
will bite the next change to that fork, which is why it is filed here rather than
left as a Task-9 footnote.

**CAL-seam collection is BLOCKED.** No CAL-seam run may be started until the
extension tree's editor artifact is genuinely rebuilt. Cell A is independently
gated by `verify_editor_artifact.sh` (`run_e2e.sh:126`), which refuses on its
own, so no run can slip past this by accident.

**Why it was not repaired here.** Re-binding the shared engine's editor-module
state to the integration tree — regenerating that project's UE project files, or
clearing `Engine/Intermediate/Build/Linux/x64/UnrealEditor`'s Carla state — is a
**second engine-level intervention** on an engine three trees share, and it would
relink the engine again. The authorization obtained was for exactly **one**
registered relink round, and that round is spent and re-instated. A repair needs
its own registration; it is not something to slip in under a round that was
authorized for a different purpose.

### 11.4 What is pinned, and what deliberately is not

`benchmarks/pins.yaml`:

- `engine.build_id` → `bc08ce19-f19c-46fe-808f-dbb2b0ddf41a`. This is **true and
  verified across all 5 manifests**, and pinning it is what keeps
  `preflight.sh`'s BuildId comparison honest for every tree — cell B included,
  which is otherwise unaffected and whose artifact gate passes.
- `extension_carla_fork.sha` → **deliberately left at
  `ae166d80d022f838b78f4a2daab1ca2880a7c8aa`.** That pin names the fork revision
  the loaded editor artifact was built from, and that artifact is the 2026-07-23
  one, built from `ae166d80d`. Advancing it to the in-core-twin commit while
  `libUnrealEditor-Carla.so` predates that commit would assert a build that does
  not exist on this host.
- `extension_carla_fork.incore_twin_sha` → `5981f5168a0d87ffacddc4635f73e1373e185ad6`,
  with `incore_twin_status: committed-not-built-into-editor-artifact`, so the
  revision is not lost while the blocker stands.

Suite at this commit: **1084 passed, 1 skipped** (the skip is
`test_observer_contract.py:105`, docker end-to-end, `BENCH_E2E=1`) — the
pre-existing baseline, held exactly. `pre-commit run --all-files` clean.
