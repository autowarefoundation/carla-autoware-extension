# P4 Task 13 — the A-vs-B-cyc CLOSED-LOOP duel console and integrity pass

Captured 2026-08-04 (duel wall window 2026-08-04T06:01Z … 08:01Z, host local
2026-08-03T23:01 … 2026-08-04T01:01 −07:00). Supports `benchmarks/results/PROVENANCE.md` §20.

**This directory contains no verdict and no cross-cell reading.** The duel
verdict is Task 16's single `duel_verdict.py` invocation; `duel_verdict.py` was
not run by this task. What is here is per-run integrity and gate facts, filed so
§20's claims are checkable.

## What the runs are

Ten interleaved pairs, one `duel.sh` invocation, no resume:

- `benchmarks/results/A/run-026` … `run-035` (10 runs)
- `benchmarks/results/B-cyc/run-012` … `run-021` (10 runs)

All twenty carry `arm: "closed-loop"`, `duel_id: "A+B-cyc"`,
`duel_admissible: true`, `excluded: false`. **Zero exclusions**, so no exclusion
reason needed quoting.

## Files

| File                          | What it is                                                                                                                                                                                                                  |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `duel-closedloop-console.log` | The duel driver's complete console, 2501 lines, byte-exact. Captured with `>` redirection, **not** `\| tee` — the repo's standing note is that an `rtk` proxy compresses piped output, and this file is quoted as evidence. |
| `integrity-pass.log`          | Output of `integrity_pass.py`, the brief's Step 2 pass.                                                                                                                                                                     |
| `integrity_pass.py`           | The exact script that produced it. Read-only over `benchmarks/results/`.                                                                                                                                                    |
| `q2-mrm-signatures.log`       | Output of `q2_mrm_signatures.py`, the Q2 observation.                                                                                                                                                                       |
| `q2_mrm_signatures.py`        | The exact script that produced it. Read-only over `benchmarks/results/`.                                                                                                                                                    |

## Capture method, and the one supervision deviation

The invocation is the brief's command verbatim in its arguments:

```bash
bash benchmarks/scripts/duel.sh A B-cyc --arm closed-loop --pairs 10
```

Two capture-level deviations from the brief's literal text, neither of which can
affect what `duel.sh` did:

- **`>` redirection instead of `| tee`**, to the brief's own path
  (`/tmp/duel-closedloop-p4.log`), for the byte-exactness reason above.
- **Launched under `setsid`**, in its own session, with the driver PID written to
  `/tmp/duel-closedloop.pid` and managed from there — never `pgrep -f` /
  `pkill -f`. This is the Task 12 lesson applied from the start: that task's
  first invocation was killed mid-duel by the agent orchestration layer. It
  changes how the driver is **supervised**, never how runs are produced:
  `duel.sh` still owned interleaving, pacing, `--duel` and the `--duel-id` stamp
  throughout, and the cells were passed in the order `A B-cyc` so the stamp is
  `"A+B-cyc"`.

**The supervision earned its keep, and the evidence is in this session.** At
2026-08-04T00:21 local a passive background watcher — a bare `until grep …;
sleep 30` loop touching nothing in the benchmark — was reported killed by the
orchestration layer. At that instant the duel driver was checked and was alive
with `PID = PGID = SID = 1204301`, state `Ss` (its own session leader), 1 h 39 m
elapsed, and it went on to complete all ten pairs. A supervisor reaping tracked
background tasks explains both observations; no CARLA / Autoware / DDS / host
fault explains the watcher's death. This independently corroborates §19.1's
classification of the Task 12 kill.

That observation is an **operator observation with no byte-exact artifact of its
own** — the orchestration-layer notification is not a file, and the watcher's
own output file is empty. It is recorded as such rather than dressed up, per
§19.1's precedent. The `ps` reading behind it is quoted above verbatim.

## Reproducing

From the worktree root:

```bash
PYTHONPATH=. python3 benchmarks/evidence/p4-task13-closed-loop-duel/integrity_pass.py
PYTHONPATH=. python3 benchmarks/evidence/p4-task13-closed-loop-duel/q2_mrm_signatures.py
```

Both are read-only over `benchmarks/results/` and take no arguments. Their
`PRE_TASK13` / `PRE_TASK13_BCYC` constants are what restricts them to this
task's twenty runs.

## Digests at capture

Recorded so a reader can confirm the pre-commit hooks did not move a byte —
`benchmarks/evidence/**` is excluded from the text-mutating hooks (§17), and
this directory's own narrative `PROVENANCE.md` is deliberately still linted.

```text
c0f03c04a76685bf6dc471f0cc471fa686055a6ad2e9dcd4ae9155a405b0e65c  duel-closedloop-console.log
72eca26ed68794c7d2f273a95d9f31a3c116eb174f74984b28caacc09bd55844  integrity-pass.log
0648a1ac4f109f714428945ec01dcfd454bf8772dc17fdfe26a9c99722be912e  integrity_pass.py
c5115aa0f77c869ba55b866349e5609ea7cf2838bb32e955500c6f80d7550ca3  q2-mrm-signatures.log
396f6ded439cfc1bd8eae4e85107b0100869e7792e4d298317a31079d8017aac  q2_mrm_signatures.py
```

## What `integrity_pass.py` deliberately does NOT print, and why

It prints the **checks**, not the measured values behind them, because Task 16
owns the only comparison:

- `goal_closest_approach_m` is reported non-null / null — which is the check the
  brief states. The metre value stays in each run's own `quality.json`.
- §15.5's row counts are printed in full for **cell A only**, because they _are_
  Q1's evidence and Q1 is cell-A-specific by construction. Cell B-cyc's
  counterpart is reported as the same three checks in boolean form.

This follows Task 12's convention, which printed cell B-cyc's `ndt_rate_ratio`
because its brief asked for it within-cell and deliberately did not print cell
A's.

## Fix round 1, appended 2026-08-04 — both scripts amended, both logs regenerated

The text above is left as written; this block supersedes its digest table for
four of the five files. Nothing under `benchmarks/results/*/run-*` was touched,
and the duel console is **unchanged** — no run's data moved.

**Why the scripts changed.**

- `integrity_pass.py` (M5): `PROVENANCE.md` §20.3 asserts `gate_pass: true`,
  `reasons: []` and `ladder_branch: "absolute"` on all twenty runs and names this
  script as the reproducer, but the script collected the first two without
  printing them and never read the third. It now prints all three per run plus
  an explicit per-cell check line, which also puts the previously unused
  `duel_id_ok` to work. All three claims were true beforehand; only the evidence
  for them was missing.
- `q2_mrm_signatures.py` (I1, I2): §21.1 and §21.2 correct §20.6's Q2 reading,
  and every figure they state is now produced by this script rather than
  asserted — the pre-arm window table (observer attach vs arm start vs first
  `control_cmd`), the per-run shape table (MRM cycle count, last cycle relative
  to engage, control-traffic span), and the signature band's placement against
  the observer window start.

Both logs were regenerated from the amended scripts, and both scripts were
re-verified **deterministic**: two consecutive runs of each produce byte-identical
output, so a filed log can be reproduced at any time with the commands in the
"Reproducing" section above.

### Digests after fix round 1

```text
c0f03c04a76685bf6dc471f0cc471fa686055a6ad2e9dcd4ae9155a405b0e65c  duel-closedloop-console.log   (UNCHANGED)
9c597d433c0c05eed6742defb7f255eddfa2dacc1dc49b2ea28737809143bfcc  integrity-pass.log
770b80f5301485a060825569395c831ccc317eddc8b9cac5800994b67fe1d420  integrity_pass.py
76e3f73b7a4410b9a87b4c68f8bfe082b98a68d2ea4e43b8f733aca997ef50b6  q2-mrm-signatures.log
299f24f7e1ff9c42ffe0052560cb3bb8249c9a183d1f77b521e0b33907a74a6f  q2_mrm_signatures.py
```
