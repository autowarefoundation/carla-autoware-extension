# P4 Task 14 — the vlp16 sweep console, driver and integrity pass

Captured 2026-08-04 (sweep wall window 2026-08-04T02:12:14−07:00 …
2026-08-04T03:49:16−07:00). Supports `benchmarks/results/PROVENANCE.md` §22.

**This directory contains no ceiling verdict, no cross-cell reading, and no
`sweep_verdict.py` output.** The ceiling gate is a per-cell boolean, read once
per cell under the registered no-peeking exception and recorded in §22; its
tables were written to `/tmp` and are deliberately not filed here, because they
carry per-run magnitudes that nothing in this campaign is licensed to compare
across cells before Task 16.

## What the runs are

One driver invocation, no resume, no make-up runs. Eighteen `run.sh`
invocations, three per cell per arm:

| cell  | arm        | runs                                |
| ----- | ---------- | ----------------------------------- |
| A     | `paced`    | `results/A/run-036 … run-038`       |
| A     | `unpaced`  | `results/A/run-039 … run-041`       |
| A     | `ablation` | `results/A/run-042 … run-044`       |
| B-cyc | `paced`    | `results/B-cyc/run-022 … run-024`   |
| B-cyc | `unpaced`  | `results/B-cyc/run-025 … run-027`   |
| B-cyc | `ablation` | `results/B-cyc/run-028 … run-030`   |

All eighteen carry `excluded: false`, `duel_admissible: false` and an empty
`duel_id` — sweep data is never duel data. **Zero exclusions**, so no exclusion
reason needed quoting.

## Files

| file                            | what it is                                                                                                                                                             |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `step1-form-verification.log`   | The twelve Step-1 invocations, verbatim: `--check-args` then `--dry-run` for {A, B-cyc} × {paced, unpaced, ablation}. Each block is followed by its own `exit=` line.     |
| `sweep_driver.sh`               | The exact driver that produced the eighteen runs — ordering, inter-run hygiene and the settle wait. It makes no measurement decision; `run.sh` owns all of those.         |
| `sweep-console.log`             | The driver's whole console, unedited, including each run's fifteen numbered steps, the hygiene blocks and the bootstrap refusals.                                        |
| `integrity_pass.py`             | The read-only pass that produced `integrity-pass.log`. Reads only pass/fail-shaped and provenance-shaped fields; computes no verdict.                                    |
| `integrity-pass.log`            | Its output: per-run arm, exclusion label, transport, duel flags, engine BuildId, governor, loadavg, file presence, row counts, and the ablation client's recorded rig.    |

`sweep-console.log`, `step1-form-verification.log` and `integrity-pass.log` are
**verbatim captures** and are covered by the `benchmarks/evidence/**` exclude on
the text-mutating pre-commit hooks (`.pre-commit-config.yaml`); their sha256
digests were taken before and after `pre-commit run --all-files` and are
unchanged. `sweep_driver.sh` and `integrity_pass.py` are the certified
producers of the two logs and are excluded from the ruff hooks for the same
reason every other evidence script is: a reformat would make the file in the
tree no longer the file that produced the recorded figure.

## The `--mount` wiring, checked from the run directories rather than the launcher

`integrity-pass.log`'s last two blocks read each ablation run's own
`raycast_baseline.json` — written by the client, not by the launcher — so the
check is independent of the code that passes the flag:

- cell B-cyc, all three runs: `mount_location_m [-0.497071, 2e-06, 2.0]`,
  `mount_rotation_deg [0.85967, -0.053676, -88.156119]` — the Task 11
  measurement (§14.5), 3/3.
- cell A, all three runs: `[0.9, 0.0, 2.0]` with the same rotation — the
  committed kit composed by `default_mount()`, which is **exact** for the
  extension rig and therefore correctly carries no `--mount`.

## Two rig facts the ablation summaries record

- `sensor_callbacks` ≈ `ticks` on cell A (2914 / 2912) and ≈ half on cell B-cyc
  (1456 / 2909). That is the two rigs' own `sensor_tick` — 0.05 s in
  `runner.spawn.top_lidar_attributes`, 0.1 s in `TIER4_LIDAR_ATTRIBUTES` — not a
  dropped-callback signal. Neither is a sweep-class knob; a class pins
  `channels` and `points_per_second` only.
- `clock_header_reasserts` is **1** on all six ablation runs, with
  `clock_toctou_repairs` 0 and `clock_stood_down` false. One re-assert is the
  documented NORMAL case (`bench_observer` truncating `clock.csv` when it opens
  it at run.sh step 6, after the client started at step 5), and
  `stood_down: false` is the positive evidence that nothing else was extending
  the file — i.e. the ablation client was `clock.csv`'s sole writer on every
  run, which is what the arm's name has to mean.
