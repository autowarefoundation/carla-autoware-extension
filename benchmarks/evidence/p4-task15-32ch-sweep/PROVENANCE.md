# P4 Task 15 — the 32ch step-up sweep console, driver and integrity passes

Captured 2026-08-04 (sweep wall window 2026-08-04T06:21:54−07:00 …
2026-08-04T07:58:47−07:00). Supports `benchmarks/results/PROVENANCE.md` §26.

> **CORRECTED 2026-08-04 by review fix round 1 — read §27 of
> `benchmarks/results/PROVENANCE.md` alongside everything below.** Nothing in
> this file is deleted or rewritten; the corrections are appended as "What fix
> round 1 changed" at the end. In short: `BENCH_TIER4_SWEEP_ARGS` was derived
> UNEXPORTED in `cells/tier4-native.sh`, so it never crossed into the spawned
> tier4 demo, and cell B-cyc's six MEASURED runs booted the demo's default
> vlp16 rig under a `class_id: "32ch"` label. `results/B-cyc/run-031 …
run-036` are now **excluded** `harness:65fbe09`, and `run-040 … run-045` are
> their re-collected replacements. Every sentence below — including
> "**Zero exclusions**" and the eighteen-run table — describes the collection
> AS IT WAS FILED, and is kept for that reason. Cell A and B-cyc's three
> ablation runs are unaffected and stand.

**This directory contains no ceiling verdict, no `sweep_verdict.py` output, and
no cross-cell reading of a performance magnitude.** The ceiling gate is a
per-cell boolean, read once per cell under the registered no-peeking exception
and recorded in §26; its tables were written to `/tmp` and are deliberately not
filed here, because they carry per-run magnitudes nothing in this campaign is
licensed to compare across cells before Task 16.

Unlike Task 14's directory, that claim needs **no scope admission for the
integrity pass**. §23.2 recorded that Task 14's `integrity-pass.log` carried
both cells' measured `observer rows` counts — `observed_count`, a term
`cadence.reconcile_drops` consumes — in one committed artifact, and instructed
Task 15 to "either split this output per cell or reduce measured-arm rows to
booleans". **Both were done** (see `integrity_pass.py`'s docstring): the row
columns are booleans, and the pass renders one cell per invocation into its own
log. No file here holds two cells' per-run instrument facts, and none holds a
row count at all.

One cross-cell statement is admitted, on exactly the ground §23.1 admitted its
predecessor: each cell's ablation client self-reports `channels 32` and
`points_per_second 1200000`. That is the **registered class definition**
(`cells.yaml` `sweep_classes`) read back off the rig, identical by construction
on both cells, and it is the check that the 4× step-up actually reached the
sensor. It is not a performance measurement and no Δ is computed from it.

## What the runs are

One driver invocation, no resume, no make-up runs. Eighteen `run.sh`
invocations, three per cell per arm:

| cell  | arm        | runs                              |
| ----- | ---------- | --------------------------------- |
| A     | `paced`    | `results/A/run-045 … run-047`     |
| A     | `unpaced`  | `results/A/run-048 … run-050`     |
| A     | `ablation` | `results/A/run-051 … run-053`     |
| B-cyc | `paced`    | `results/B-cyc/run-031 … run-033` |
| B-cyc | `unpaced`  | `results/B-cyc/run-034 … run-036` |
| B-cyc | `ablation` | `results/B-cyc/run-037 … run-039` |

All eighteen carry `class_id: "32ch"`, `excluded: false`,
`duel_admissible: false` and an empty `duel_id` — sweep data is never duel
data. **Zero exclusions**, so no exclusion reason needed quoting. All eighteen
`run.sh` invocations exited 0.

## Files

| file                          | what it is                                                                                                                                                                                   |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `step1-form-verification.log` | The twelve Step-1 invocations, verbatim: `--check-args` then `--dry-run` for {A, B-cyc} × {paced, unpaced, ablation}, all at `--class 32ch`. Each block is followed by its own `exit=` line. |
| `sweep_driver.sh`             | The exact driver that produced the eighteen runs — ordering, inter-run hygiene and the settle wait. It makes no measurement decision; `run.sh` owns all of those.                            |
| `sweep-console.log`           | The driver's whole console, unedited, including each run's fifteen numbered steps, the hygiene blocks and the bootstrap refusals.                                                            |
| `integrity_pass.py`           | The read-only pass that produced the two logs below. Computes no verdict, prints no row count, and refuses to render two cells into one artifact — see its docstring and §23.2.              |
| `integrity-pass-A.log`        | Cell A's output: per-run arm, class label, exclusion label, transport, duel flags, engine BuildId, governor, loadavg, instrument presence, and the ablation client's recorded rig.           |
| `integrity-pass-B-cyc.log`    | The same for cell B-cyc, in its own file.                                                                                                                                                    |

`sweep-console.log`, `step1-form-verification.log` and the two
`integrity-pass-*.log` files are **verbatim captures** and are covered by the
`benchmarks/evidence/**` exclude on the text-mutating pre-commit hooks
(`.pre-commit-config.yaml`); their sha256 digests were taken before and after
`pre-commit run --all-files` and are unchanged. `sweep_driver.sh` and
`integrity_pass.py` are the certified producers of those logs and are excluded
from the ruff hooks for the same reason every other evidence script is: a
reformat would make the file in the tree no longer the file that produced the
recorded figure.

## The `--mount` value is now a launcher constant, and it took

Task 14 wired the Task 11 measurement into `cells/tier4-native.sh` as
`TIER4_ABLATION_MOUNT` (with a `BENCH_ABLATION_MOUNT` override). This
collection is the first to rely on it with **no operator action at all**, and
the check is taken from the run directories rather than from the launcher that
wrote them — each ablation run's own `raycast_baseline.json`, written by the
client:

- cell B-cyc, all three runs: `mount_location_m [-0.497071, 2e-06, 2.0]`,
  `mount_rotation_deg [0.85967, -0.053676, -88.156119]` — the Task 11
  measurement (§14.5), **3/3**, with `mount_source: --mount`.
- cell A, all three runs: `[0.9, 0.0, 2.0]` with the same rotation and
  `mount_source: default_mount()` — the committed kit, which is **exact** for
  the extension rig and therefore correctly carries no `--mount`.

The two poses differ by **1.397071 m in x**, which is the whole point: that is
the tier4 rig's `base_link` anchor, and it is the estimate the constant
replaced. `mount_source` is the key §23.5 added; Task 14's six filed ablation
summaries predate it, which is why `integrity_pass.py` reads it with `.get()`.

## Two rig facts the ablation summaries record

- Every ablation run on both cells reports `channels 32` /
  `points_per_second 1200000` — the registered `32ch` class, read back off the
  rig the client actually spawned. The step-up reached the sensor; a run that
  had silently kept the vlp16 or the default 128-channel rig would say so here.
- `clock_header_reasserts` is **1** on all six ablation runs, with
  `clock_toctou_repairs` 0 and `clock_stood_down` false. One re-assert is the
  documented NORMAL case (`bench_observer` truncating `clock.csv` when it opens
  it at run.sh step 6, after the client started at step 5), and
  `stood_down: false` is the positive evidence that nothing else was extending
  the file — i.e. the ablation client was `clock.csv`'s sole writer on every
  run, which is what the arm's name has to mean.

## The bootstrap refusal, stated correctly this time

`bootstrap_carla_msgs.sh` refused on **all eighteen** hygiene blocks
(`PREFLIGHT FAIL: container 'autoware' is not running`, exit 1), measured runs
included — because the hygiene rule pairs a `docker compose down` with a
bootstrap requiring the container that `down` just removed. This is the
established behaviour (§22.6, §23.4), not a new observation, and **this
directory's `sweep_driver.sh` says so in its own comment** rather than
inheriting Task 14's refuted arm/cell framing. Task 14's driver is a certified
verbatim producer and stays as it ran; this one was written knowing the
outcome.

It cost the collection nothing, and that stays checkable: `carla_msgs` is
sourced optionally at `scripts/e2e/launch_autoware.sh:202`, nothing under
`benchmarks/` consumes it, and all twelve measured runs armed, drove and
produced `quality_ok: true` with full observer and publisher-count data. The
`down` half — what the rule exists for — succeeded on all eighteen.

## What fix round 1 changed (2026-08-04)

Appended, not merged into the text above. The full record is
`benchmarks/results/PROVENANCE.md` §27; this section says only what is in
THIS directory.

**The defect.** `cells/tier4-native.sh` derived `BENCH_TIER4_SWEEP_ARGS` as a
plain, unexported shell assignment. The ablation arm expands it in the same
process and was correct; the measured arms spawn `bash "$TIER4_DEMO"` through
a prefix-assignment whitelist that did not carry it, so
`cells/tier4_autoware.sh` expanded it to empty in the child and the patched
demo fell back to `--lidar-channels 16 --lidar-pps 288000` — the vlp16 class.
Six B-cyc measured runs were filed at `class_id: "32ch"` on a vlp16 rig. Fixed
by `65fbe09` (export at the derivation site), excluded by `4e195f6`
(`harness:65fbe09`), re-collected by `af65a27`.

**This directory's two claims that need reading with that in mind.** The
eighteen-run table and "**Zero exclusions**" were true of the collection as
filed and are now superseded for cell B-cyc's measured arms only. The two "rig
facts the ablation summaries record" are UNAFFECTED and still hold exactly:
that arm's `channels 32` / `points_per_second 1200000` read-back was never
touched by the defect, which is precisely why it corroborated a claim that was
false elsewhere.

**New files.**

| file                               | what it is                                                                                                                                                                                              |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `step1_fix1.sh`                    | Step-1 form verification for the two forms this round re-collects (B-cyc `paced`, `paced --unpaced`), `--check-args` then `--dry-run`.                                                                  |
| `step1-form-verification-fix1.log` | Its verbatim output: four invocations, all `exit=0`, each resolving `class_id=32ch`.                                                                                                                    |
| `sweep_driver_fix1.sh`             | The exact driver for the six replacement runs. Two phases on purpose: `proof` collects ONE run so the fix can be checked at the rig before five more are paid for, then `rest` does the remaining five. |
| `sweep-console-fix1-proof.log`     | The `proof` phase's whole console, unedited — `run-040`.                                                                                                                                                |
| `sweep-console-fix1-rest.log`      | The `rest` phase's whole console, unedited — `run-041 … run-045`.                                                                                                                                       |

`sweep_driver.sh` and `sweep-console.log` are UNCHANGED and were not re-run:
they are the certified verbatim producer and capture of the original eighteen.

**`integrity_pass.py` was fixed and both of its logs regenerated in place.**
As filed it could not have failed on this defect: it read the spawned rig back
only from `raycast_baseline.json`, which only the ablation arm writes, and for
the measured runs it printed `manifest.class_id` — a label — while `main`
returned 0 unconditionally. It now derives a MEASURED rig fact for the
measured arms (median lidar `size_bytes` against the same cell's vlp16
baseline and the registered class ratio), enforces the ablation-side
read-backs instead of printing them, and exits non-zero on any mismatch. Both
logs exit 0 on the current tree. Regenerating them in place follows §21's
precedent, where Task 13's own `integrity-pass.log` was regenerated when its
own `integrity_pass.py` was corrected; the pre-fix output stays recoverable at
`b6fbc80`. The §23.2 split is unchanged — one cell per invocation, one log per
cell — and the new column is a workload property (how many points the sensor
emits), not a performance magnitude.

**The rig proof, which is what licensed the other five runs.** After `run-040`
alone: median `size_bytes` on `/sensing/lidar/top/pointcloud_raw_ex` = 996 728 B
against this cell's own vlp16 measured baseline of 238 984 B — ×4.1707,
against the registered class ratio 1 200 000 / 288 000 = 4.1667. The six
excluded runs read ×0.9987 … ×1.0005 on the same measurement, which is why no
label-level check could ever have separated them.

All five new captures and both regenerated logs were sha256'd before and after
`pre-commit run --all-files` and are unchanged, as the originals were.
