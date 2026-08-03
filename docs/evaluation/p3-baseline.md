# P3 baseline: the three-approach evaluation, its cells, and the A-vs-B equivalence verdict

**Written 2026-08-01 by the P3 wrap (Task 9 of the P3 completion plan).** This is
the campaign's published record. Everything before it was collection; this
document computes the verdict — **once** — and states what the campaign does and
does not support.

Two companion documents are load-bearing and are not restated here:

- `benchmarks/results/PROVENANCE.md` — the per-run provenance of every filed
  run, the live findings, and the deviations log this document summarises.
- `benchmarks/README.md` — the pre-registration: metric definitions, margins,
  scope, and the `## Known confounds` section this document's confound table
  indexes.

Nothing under `benchmarks/results/*/run-*/` was read-modify-written by this
task. No filed run was deleted, reclassified, re-scored or hand-edited.

## 0. How to read this document

**Every number carries the command that reproduces it.** Two commands produce
every figure in sections 3 and 4; they are given verbatim at the head of each
section and collected again in section 10. Both were run from the repository
root on 2026-08-01, at commit `269b931`. Both are pure analysis over committed
files and are **deterministic** — `duel_verdict.py` pins its bootstrap at
`iters=10000, seed=20260727, alpha=0.05`, the campaign's own defaults, which is
what makes a verdict reproducible across runs of the tool rather than merely
recomputed. Host load cannot move either output.

**The verdict was computed exactly once.** No verdict, delta, or cross-cell
median existed in this repository before this task, and none is recomputed
after it. `benchmarks/scripts/duel_verdict.py` was invoked one time, with no
filtering flags; its complete output is reproduced in section 4 — every row,
including the ones that decline to decide, with no cell content altered (see
section 3 on the one whitespace-only transformation the repository's formatter
applies, and the check that verifies it).

**Three counts get confused, so each is named separately wherever it appears.**
For the primary duel's static arm:

| count                                                               | cell A                       | cell B                       |
| ------------------------------------------------------------------- | ---------------------------- | ---------------------------- |
| **duel-admissible static pool** (what the verdict is computed from) | **10** — `run-003`…`run-012` | **10** — `run-013`…`run-022` |
| non-excluded static runs (the whole static tree, duel and non-duel) | 13                           | 17                           |
| excluded static runs                                                | 0                            | 0                            |

The verdict's pool is the first row and nothing else. It is the 10 pairs _by
construction_, not by filtering: `duel_verdict.py` drops excluded runs and
drops runs that are not `duel_admissible` — on two separate counters, because
"the data is invalid" and "valid data outside the duel's interleaved design"
are different facts — so the pool falls out of the tool's own contract with no
flag passed. The counts of what it dropped are printed in the table's `notes`
column, which is how a reader checks the pool rather than taking it on trust.

An earlier draft of this record said "fifteen" for this pool. That matches none
of the three counts above and is corrected here rather than silently dropped.

## 1. The headline

**On the static arm, at the pre-registered n = 10 per side, the extension and
tier4-native approaches are NOT equivalent on any metric the campaign can
compute — and every computable metric separates them in the extension's
favour.**

- Four of the five pre-registered margin metrics are computable. **None returns
  `parity`.** Every one of the four falls entirely outside its pre-registered
  margin, with a 95% bootstrap CI that does not cross zero.
- The fifth, `control_staleness_ms`, is **UNAVAILABLE for the whole duel** —
  cell A's `control_published_time_topic` binding was never registered
  (`benchmarks/config/cells.yaml:132`, owed to Tasks 13/20, neither of which
  ran). It is reported as unavailable, never as zero and never as parity.

**And the closed-loop half of the duel is NOT COMPUTABLE.** Cell B filed **15**
closed-loop runs under its registered transport and **armed on none of them**;
all 15 are excluded, which is why the verdict tool's own closed-loop rows print
`15 run(s) excluded from B`. It armed exactly once in the whole campaign, on
`B/run-033` — a deliberate, non-duel run that changed **only the middleware**
and is therefore not a cell-B measurement. There is no A-vs-B closed-loop
equivalence verdict, and this document does not manufacture one. The mechanism
is a first-class campaign finding and is stated as such in section 5.1, which
also carries the exact breakdown of the 15.

**Read the direction of `achieved_rate_ratio`'s verdict label with care.** The
row prints `b_better`. That label is a polarity artifact, not a result in cell
B's favour, and it is explained in full in section 4.2. Cell A is ahead on that
metric too.

## 2. Cell readiness: what was collected, and what was struck

`benchmarks/config/cells.yaml` registers **twelve** cells. Six were struck by
the owner's core-duel scope cut of 2026-07-30 — machine-readable as
`dropped: owner-time-budget-2026-07-30` on each — and six were collected.

### 2.1 The six in-scope cells, as filed

Reproduce the per-run classification with:

```bash
python3 - <<'PY'
import json, pathlib
root = pathlib.Path("benchmarks/results")
for cell in sorted(p for p in root.iterdir() if p.is_dir()):
    for run in sorted(cell.glob("run-*")):
        mp = run / "manifest.json"
        if not mp.is_file():
            print(f"{cell.name}/{run.name}: NO MANIFEST")
            continue
        m = json.loads(mp.read_text())
        # `.get`, not `m["duel_admissible"]`: the field was introduced by the
        # 2026-07-30 amendment (Task 15b) and is ABSENT from every manifest
        # filed before it -- B/run-001..012 and E/run-001..008. Indexing raises
        # KeyError on those 20, which is how the first revision of this command
        # shipped broken. "absent" is itself provenance and is printed as such,
        # never defaulted to false.
        duel = m.get("duel_admissible", "absent(pre-2026-07-30)")
        print(f"{cell.name}/{run.name}: arm={m['arm']} excluded={m['excluded']} "
              f"reason={m['exclusion_reason']!r} duel_admissible={duel} "
              f"quality_json={(run / 'quality.json').is_file()}")
PY
```

| cell        | approach        | map              | arms registered     | filed | what it contributes to P3                                                                                                                                                                                                                                                                                                           |
| ----------- | --------------- | ---------------- | ------------------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A**       | `extension`     | Town10HD_Opt     | static, closed-loop | 14    | **primary duel, side A.** 10 duel-admissible static (`run-003`…`run-012`). Closed-loop: `run-002` only, bring-up class. `run-001`, `run-013`, `run-014` are bring-up/Phase-0 diagnostics.                                                                                                                                           |
| **B**       | `tier4-native`  | Town10HD_Opt     | static, closed-loop | 33    | **primary duel, side B.** 10 duel-admissible static (`run-013`…`run-022`). Closed-loop: **0 valid** — see 5.1.                                                                                                                                                                                                                      |
| **C**       | `extension`     | NishishinjukuMap | static, closed-loop | 14    | **confirmatory, never duel data.** 5 valid static (`run-004`…`run-008`) + 5 valid closed-loop (`run-010`…`run-014`). **`run-009` is `excluded: false` with NO `quality.json` — read 5.3 before iterating this cell.** `run-002` is a valid bring-up-class closed-loop run, not counted in the five.                                 |
| **E0**      | `python-bridge` | Town10HD_Opt     | static              | 10    | **bridge context, as-shipped image.** 5 valid static — read section 6 before quoting any central tendency.                                                                                                                                                                                                                          |
| **E**       | `python-bridge` | Town10HD_Opt     | static, closed-loop | 16    | **bridge context, patched image.** 6 valid static. Closed loop **not collected**, per the pre-registered static-only downgrade.                                                                                                                                                                                                     |
| **CAL-rmw** | `calibration`   | none             | static              | 15    | **calibration.** The `one_hop_wall_ms` margin was **frozen** from these 15 interleaved runs (`p50_cyclonedds` 0.6840 ms, `p50_fastdds-udp` 1.0993 ms) — and the measurement put 2 × abs(Δ) at 0.83 ms, so the pre-registered **floor of 2.0 is what binds**. That is a result, not an agreement. No simulator, no `/clock`, no map. |

Cell C's warm-ups (`run-001`, `run-003`) are excluded `warmup:nishi`, a
pre-registered discard under criterion 5, not a failure — both armed and scored
cleanly regardless.

### 2.2 The six struck cells, with their registered reason

None of these was technically infeasible, blocked, or measured and found
wanting. **No result about any of them may be inferred from its absence.** The
strike is an owner time-budget decision; the entries stay registered rather than
deleted, so the record of what was given up survives.

| cell       | what it would have measured                                                                                    | registered loss                                                                                                                                                                                                                                                                 |
| ---------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CAL-seam` | the paired seam-vs-in-core one-hop delta on one CARLA fork process                                             | **`C1(a)` seam overhead is UNMEASURED — not weakly measured, not partly measured. There is no evidence at all.** The extension-side publishers (`extension/src/publishers/BenchCloudPublisher.{h,cpp}`) and `scripts/cal_report.py`'s seam half stay committed and unexercised. |
| `B45`      | what it costs to carry the tier4 CARLA fork against a **different** Autoware release (`universe-devel-0.45.1`) | no hard-fork-maintenance finding. The one open prerequisite was a **logistics** gap — the 0.45.1 image is not on this workstation — **never** a defect of that image or of carrying the fork across releases.                                                                   |
| `D`        | tier4-native on Nishi-Shinjuku — the cross-map half of the A/B-vs-C/D design                                   | no cross-map tier4 attempt. **Its own open question stays OPEN, not answered:** whether the tier4 tree can cook the Nishi-Shinjuku map at all was never tested. Confound C4 keeps only its A/B-vs-C comparison.                                                                 |
| `E-opt`    | the optimised python-bridge closed loop                                                                        | no optimised-bridge result.                                                                                                                                                                                                                                                     |
| `A-hf`     | 100 Hz sensitivity, extension                                                                                  | no 100 Hz sensitivity cells. Struck **as a pair** with `B-hf` — striking one half would have left a one-sided result. All three rate bindings on both cells are now permanently `null`.                                                                                         |
| `B-hf`     | 100 Hz sensitivity, tier4-native                                                                               | as above.                                                                                                                                                                                                                                                                       |

Struck with them: the M4 **camera-load arm in full** (`camera_classes`
cam1/cam3/cam6 — no camera table, no per-approach native-camera-path
comparison), and the M4 LiDAR sweep's `32ch` and `128ch` classes, reducing M4 to
a ceiling confirmation at the duel size. `32ch` is the **pre-registered
step-up** on a branch the data decides; both branches were registered before any
P3 run.

## 3. Per-cell tables

Produced by, verbatim:

```bash
PYTHONPATH=. python3 -m benchmarks.report benchmarks/results > /tmp/p3-report-tables.md
```

`benchmarks/report.py`'s `main` takes the results **ROOT** and treats each child
as a cell. Handing it a single cell directory instead makes it walk that cell's
`run-NNN` directories as if _they_ were cells, find no `run-*` inside them, and
print an empty table — a smoke test that passes on any input, which is worse
than none. That warning is `benchmarks/run.sh:927-935`'s alone.
`benchmarks/README.md:4058-4061` is cited only for the invocation form it does
state — "the entry point for rendering a per-cell report is `python3 -m
benchmarks.report <results_dir>`" — and NOT for the trap, which it does not
mention. The root form above is the documented one and is what was run.

**The command exits 1, and the exit is fully explained by cell CAL-rmw.** All
15 of its rows read `RENDER FAILED: ValueError: need >= 2 paired (sim, wall)
samples`, untagged by `(EXCLUDED)`, which is what drives the non-zero exit.
That is correct behaviour on both sides: CAL-rmw is a `carla: none`,
container-only cell with **no simulator**, so nothing ever publishes `/clock`
and `clock.csv` holds a header row and nothing else. `benchmarks/run.sh:996-997`
takes the `BENCH_HAS_SIM_CLOCK != 1` branch for exactly this cell and
deliberately does **not** call `report.py`'s renderer — it asserts only that
rows were recorded, and writes a one-line stub into each run's `report.md`. The
registered renderer for the cell is `benchmarks/scripts/cal_report.py`.
Nothing was fixed, silenced or worked around here: the tool is reporting,
loudly and by name, that it was pointed at a cell it does not render.

**And a citation correction, because the first revision of this paragraph got
it backwards.** It said `benchmarks/results/CAL-rmw/PROVENANCE.md:433-448`
"records that all fifteen runs were rendered through `cal_report.py`". That
passage says close to the opposite: `cal_report.py` "was run to produce the
unwindowed column of that table, but **its output is not committed as a file
anywhere**, so nothing under `results/CAL-rmw/` is `cal_report.py` output."
What each CAL-rmw `report.md` holds is the `run.sh:996-997` stub
(`# run-001: 624 observer rows, 130 resource samples (no sim clock; CAL
rendering is Task 16's cal_report.py)`), and **the cell's scored numbers live in
exactly two places**: that file's own p50 table, and the frozen derivation in
`benchmarks/config/margins.yaml`'s `one_hop_wall_ms` block. Cite those, not a
rendering that was never filed.

Every other untagged row rendered. The `(EXCLUDED)`-tagged failures are the
expected shape of an excluded run whose data was never written — a
`crash:cell-launch` run has no `clock.csv` because the cell never came up — and
two of them are cell E0's registered result in its sharpest form
(`run-005`/`run-006`: `need >= 2 arrivals`; see section 6).

**One column must not be cross-read against section 4.** `report.py`'s `hz` is
computed by `inter_arrival_stats(arrival_system_ns)` — an **arrival**-domain
rate, in wall time — whereas the duel's `achieved_rate_ratio` is computed on
`header_stamp_ns`, the **sim** domain, deliberately, so that the simulator's
real-time factor cannot land inside a 0.02 margin (`benchmarks/README.md:588-594`).
The two are different quantities on the same topic. Read each in its own
section; do not divide one by the other.

Below is that command's output with **no cell content altered and no row
omitted**. Two mechanical transformations were applied and nothing else: the
tool's own `## Cell <id>` headings are demoted one level to `###` so they nest
under this section, and the repository's `prettier` pre-commit hook padded every
table cell to its column width and widened the `---` separator rows — whitespace
only. Checkable: strip the padding and every data row of the raw output is
present here, byte for byte.

```bash
PYTHONPATH=. python3 -m benchmarks.report benchmarks/results > /tmp/p3-report-tables.md
python3 - <<'PY'
import pathlib
def norm(line):
    if not line.startswith("|"):
        return line.strip()
    return "|".join(c.strip() for c in line.strip().strip("|").split("|"))
doc = {norm(l) for l in pathlib.Path("docs/evaluation/p3-baseline.md").read_text().splitlines()}
src = [l for l in pathlib.Path("/tmp/p3-report-tables.md").read_text().splitlines() if l.strip()]
src = [l.replace("## Cell ", "### Cell ", 1) if l.startswith("## Cell ") else l for l in src]
missing = [l for l in src if norm(l) not in doc]
print(len(src), "source lines;", len(missing), "not found")
for m in missing:
    print("  ", m)
PY
```

It reports **320 source lines, 6 not found** — the six table **separator** rows,
one per cell, which prettier widened. Every data row and every heading matches.
The same check over section 4.1's verdict output reports 20 and 2, the two
separator rows there.

### Cell A

| run     | topic                                             | hz    | p95 ms | 1-hop p50 ms | 1-hop p99 ms | MB/s  |
| ------- | ------------------------------------------------- | ----- | ------ | ------------ | ------------ | ----- |
| run-001 | /localization/kinematic_state                     | 19.96 | 51.43  | 1.96         | 4.27         | 0.00  |
| run-001 | /localization/pose_estimator/pose_with_covariance | 19.96 | 52.97  | 13.56        | 17.50        | 0.00  |
| run-001 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.37  | 8.39         | 11.28        | 10.25 |
| run-002 | /control/command/control_cmd                      | 19.96 | 51.06  | 1.70         | 3.86         | 0.00  |
| run-002 | /localization/kinematic_state                     | 19.96 | 51.13  | 1.87         | 4.39         | 0.00  |
| run-002 | /localization/pose_estimator/pose_with_covariance | 19.96 | 52.96  | 13.94        | 18.25        | 0.00  |
| run-002 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.22  | 8.51         | 11.42        | 10.21 |
| run-003 | /localization/kinematic_state                     | 19.96 | 51.37  | 1.93         | 4.30         | 0.00  |
| run-003 | /localization/pose_estimator/pose_with_covariance | 19.96 | 52.91  | 13.12        | 16.58        | 0.00  |
| run-003 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.23  | 8.05         | 10.71        | 10.25 |
| run-004 | /localization/kinematic_state                     | 19.96 | 51.53  | 1.99         | 4.38         | 0.00  |
| run-004 | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.09  | 13.43        | 17.33        | 0.00  |
| run-004 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.59  | 8.20         | 11.02        | 10.26 |
| run-005 | /localization/kinematic_state                     | 19.96 | 51.55  | 2.05         | 4.64         | 0.00  |
| run-005 | /localization/pose_estimator/pose_with_covariance | 19.96 | 52.81  | 12.73        | 16.89        | 0.00  |
| run-005 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.37  | 8.28         | 11.34        | 10.25 |
| run-006 | /localization/kinematic_state                     | 19.96 | 51.35  | 1.93         | 4.15         | 0.00  |
| run-006 | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.11  | 13.16        | 16.96        | 0.00  |
| run-006 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.46  | 8.31         | 11.14        | 10.26 |
| run-007 | /localization/kinematic_state                     | 19.96 | 51.43  | 1.98         | 4.49         | 0.00  |
| run-007 | /localization/pose_estimator/pose_with_covariance | 19.96 | 52.92  | 12.59        | 16.17        | 0.00  |
| run-007 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.27  | 8.26         | 11.21        | 10.26 |
| run-008 | /localization/kinematic_state                     | 19.96 | 51.68  | 2.00         | 4.48         | 0.00  |
| run-008 | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.30  | 12.87        | 16.83        | 0.00  |
| run-008 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.54  | 8.39         | 11.58        | 10.26 |
| run-009 | /localization/kinematic_state                     | 19.96 | 51.17  | 1.80         | 4.18         | 0.00  |
| run-009 | /localization/pose_estimator/pose_with_covariance | 19.96 | 52.54  | 12.79        | 16.23        | 0.00  |
| run-009 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 51.84  | 8.05         | 10.38        | 10.25 |
| run-010 | /localization/kinematic_state                     | 19.96 | 51.59  | 2.10         | 4.80         | 0.00  |
| run-010 | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.11  | 12.83        | 16.44        | 0.00  |
| run-010 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.56  | 8.38         | 11.17        | 10.25 |
| run-011 | /localization/kinematic_state                     | 19.96 | 51.47  | 1.94         | 4.50         | 0.00  |
| run-011 | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.26  | 12.63        | 16.43        | 0.00  |
| run-011 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.61  | 8.30         | 11.14        | 10.25 |
| run-012 | /localization/kinematic_state                     | 19.96 | 51.42  | 1.98         | 5.32         | 0.00  |
| run-012 | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.28  | 12.93        | 17.60        | 0.00  |
| run-012 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.78  | 8.41         | 12.36        | 10.25 |
| run-013 | /localization/kinematic_state                     | 19.96 | 51.51  | 2.00         | 4.49         | 0.00  |
| run-013 | /localization/pose_estimator/pose_with_covariance | 19.95 | 53.10  | 13.33        | 16.90        | 0.00  |
| run-013 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.34  | 8.17         | 11.01        | 10.25 |
| run-014 | /localization/kinematic_state                     | 19.96 | 51.50  | 1.93         | 4.68         | 0.00  |
| run-014 | /localization/pose_estimator/pose_with_covariance | 19.96 | 52.99  | 12.95        | 16.75        | 0.00  |
| run-014 | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.36  | 8.20         | 11.21        | 10.25 |

### Cell B

| run                | topic                                                                                                           | hz    | p95 ms   | 1-hop p50 ms | 1-hop p99 ms | MB/s |
| ------------------ | --------------------------------------------------------------------------------------------------------------- | ----- | -------- | ------------ | ------------ | ---- |
| run-001 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/B/run-001/clock.csv' | -     | -        | -            | -            | -    |
| run-002 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/B/run-002/clock.csv' | -     | -        | -            | -            | -    |
| run-003 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/B/run-003/clock.csv' | -     | -        | -            | -            | -    |
| run-004 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/B/run-004/clock.csv' | -     | -        | -            | -            | -    |
| run-005 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/B/run-005/clock.csv' | -     | -        | -            | -            | -    |
| run-006 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/B/run-006/clock.csv' | -     | -        | -            | -            | -    |
| run-007 (EXCLUDED) | /control/command/control_cmd                                                                                    | 10.29 | 216.38   | 4.00         | 15.83        | 0.00 |
| run-007 (EXCLUDED) | /localization/kinematic_state                                                                                   | 19.29 | 56.81    | 2.63         | 12.17        | 0.00 |
| run-007 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 3.10  | 573.38   | 122.62       | 207.93       | 0.00 |
| run-007 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 10.20 | 101.30   | 13.55        | 17.39        | 3.69 |
| run-008 (EXCLUDED) | /control/command/control_cmd                                                                                    | 10.77 | 240.24   | 6.47         | 36.80        | 0.00 |
| run-008 (EXCLUDED) | /localization/kinematic_state                                                                                   | 18.13 | 64.97    | 2.62         | 16.13        | 0.00 |
| run-008 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 2.02  | 1623.92  | 205.02       | 261.77       | 0.00 |
| run-008 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 7.62  | 296.22   | 15.19        | 31.32        | 1.84 |
| run-009 (EXCLUDED) | /control/command/control_cmd                                                                                    | 1.26  | 2740.50  | 17.51        | 2628.74      | 0.00 |
| run-009 (EXCLUDED) | /localization/kinematic_state                                                                                   | 19.12 | 67.32    | 2.50         | 19.07        | 0.00 |
| run-009 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 3.42  | 865.51   | 203.79       | 215.89       | 0.00 |
| run-009 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.53  | 201.35   | 15.30        | 33.15        | 2.07 |
| run-010 (EXCLUDED) | /control/command/control_cmd                                                                                    | 1.99  | 1819.41  | 16.27        | 1487.77      | 0.00 |
| run-010 (EXCLUDED) | /localization/kinematic_state                                                                                   | 18.94 | 92.74    | 2.49         | 19.15        | 0.00 |
| run-010 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 3.72  | 886.98   | 204.76       | 271.59       | 0.00 |
| run-010 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.89  | 200.86   | 15.97        | 36.75        | 2.15 |
| run-011 (EXCLUDED) | /control/command/control_cmd                                                                                    | 1.11  | 3861.38  | 9.19         | 910.48       | 0.00 |
| run-011 (EXCLUDED) | /localization/kinematic_state                                                                                   | 19.25 | 60.48    | 2.06         | 13.39        | 0.00 |
| run-011 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 2.21  | 1646.24  | 204.77       | 316.45       | 0.00 |
| run-011 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.94  | 201.54   | 13.65        | 28.23        | 2.16 |
| run-012 (EXCLUDED) | /control/command/control_cmd                                                                                    | 3.71  | 1441.44  | 11.15        | 666.63       | 0.00 |
| run-012 (EXCLUDED) | /localization/kinematic_state                                                                                   | 18.45 | 99.67    | 2.22         | 14.28        | 0.00 |
| run-012 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 5.71  | 402.96   | 156.88       | 270.16       | 0.00 |
| run-012 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.99  | 200.16   | 14.84        | 30.02        | 2.18 |
| run-013            | /control/command/control_cmd                                                                                    | 1.51  | 2301.08  | 7.11         | 1908.20      | 0.00 |
| run-013            | /localization/kinematic_state                                                                                   | 19.82 | 56.01    | 1.80         | 11.93        | 0.00 |
| run-013            | /localization/pose_estimator/pose_with_covariance                                                               | 9.77  | 188.07   | 21.50        | 215.10       | 0.00 |
| run-013            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 9.30  | 198.29   | 12.61        | 27.40        | 2.25 |
| run-014            | /control/command/control_cmd                                                                                    | 0.24  | 14386.42 | 9.48         | 51.89        | 0.00 |
| run-014            | /localization/kinematic_state                                                                                   | 19.59 | 58.41    | 2.41         | 17.16        | 0.00 |
| run-014            | /localization/pose_estimator/pose_with_covariance                                                               | 7.07  | 313.23   | 32.01        | 223.06       | 0.00 |
| run-014            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 9.10  | 200.00   | 14.72        | 32.52        | 2.20 |
| run-015            | /control/command/control_cmd                                                                                    | 2.36  | 2535.02  | 8.56         | 1690.96      | 0.00 |
| run-015            | /localization/kinematic_state                                                                                   | 18.02 | 100.22   | 2.26         | 14.04        | 0.00 |
| run-015            | /localization/pose_estimator/pose_with_covariance                                                               | 3.50  | 732.73   | 40.48        | 223.75       | 0.00 |
| run-015            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.66  | 201.90   | 14.77        | 30.12        | 2.10 |
| run-016            | /control/command/control_cmd                                                                                    | 8.85  | 246.11   | 4.75         | 146.38       | 0.00 |
| run-016            | /localization/kinematic_state                                                                                   | 19.36 | 60.65    | 2.05         | 15.93        | 0.00 |
| run-016            | /localization/pose_estimator/pose_with_covariance                                                               | 2.12  | 1235.09  | 204.61       | 268.29       | 0.00 |
| run-016            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.94  | 201.47   | 14.42        | 33.47        | 2.17 |
| run-017            | /control/command/control_cmd                                                                                    | 0.91  | 4888.47  | 8.75         | 2288.53      | 0.00 |
| run-017            | /localization/kinematic_state                                                                                   | 18.25 | 99.86    | 1.74         | 33.59        | 0.00 |
| run-017            | /localization/pose_estimator/pose_with_covariance                                                               | 4.98  | 612.35   | 34.37        | 317.63       | 0.00 |
| run-017            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 9.05  | 200.73   | 14.10        | 26.85        | 2.19 |
| run-018            | /control/command/control_cmd                                                                                    | 1.05  | 2884.71  | 10.92        | 2237.24      | 0.00 |
| run-018            | /localization/kinematic_state                                                                                   | 19.51 | 58.76    | 2.42         | 14.21        | 0.00 |
| run-018            | /localization/pose_estimator/pose_with_covariance                                                               | 7.97  | 212.28   | 25.79        | 216.90       | 0.00 |
| run-018            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 9.12  | 200.49   | 13.75        | 30.15        | 2.21 |
| run-019            | /control/command/control_cmd                                                                                    | 1.13  | 4006.98  | 16.65        | 920.09       | 0.00 |
| run-019            | /localization/kinematic_state                                                                                   | 19.32 | 61.27    | 2.22         | 18.27        | 0.00 |
| run-019            | /localization/pose_estimator/pose_with_covariance                                                               | 4.38  | 721.88   | 36.07        | 259.44       | 0.00 |
| run-019            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.94  | 201.40   | 15.07        | 34.26        | 2.16 |
| run-020            | /control/command/control_cmd                                                                                    | 1.32  | 2292.19  | 4.96         | 1913.12      | 0.00 |
| run-020            | /localization/kinematic_state                                                                                   | 19.19 | 63.73    | 2.44         | 15.99        | 0.00 |
| run-020            | /localization/pose_estimator/pose_with_covariance                                                               | 3.77  | 910.40   | 33.89        | 226.46       | 0.00 |
| run-020            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.96  | 200.91   | 14.61        | 28.73        | 2.17 |
| run-021            | /control/command/control_cmd                                                                                    | 0.52  | 5322.47  | 9.76         | 2139.54      | 0.00 |
| run-021            | /localization/kinematic_state                                                                                   | 19.27 | 61.57    | 2.21         | 16.65        | 0.00 |
| run-021            | /localization/pose_estimator/pose_with_covariance                                                               | 3.50  | 820.03   | 180.88       | 289.70       | 0.00 |
| run-021            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.78  | 201.70   | 14.68        | 27.53        | 2.13 |
| run-022            | /control/command/control_cmd                                                                                    | 1.07  | 3981.06  | 11.39        | 2195.68      | 0.00 |
| run-022            | /localization/kinematic_state                                                                                   | 18.68 | 98.72    | 2.52         | 14.50        | 0.00 |
| run-022            | /localization/pose_estimator/pose_with_covariance                                                               | 7.70  | 282.59   | 29.55        | 244.55       | 0.00 |
| run-022            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.91  | 201.74   | 14.82        | 30.67        | 2.16 |
| run-023            | /control/command/control_cmd                                                                                    | 3.63  | 1550.64  | 10.95        | 908.22       | 0.00 |
| run-023            | /localization/kinematic_state                                                                                   | 19.29 | 63.10    | 2.52         | 18.28        | 0.00 |
| run-023            | /localization/pose_estimator/pose_with_covariance                                                               | 3.90  | 788.97   | 48.19        | 229.58       | 0.00 |
| run-023            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.57  | 204.04   | 14.80        | 38.03        | 2.07 |
| run-024            | /control/command/control_cmd                                                                                    | 1.41  | 3022.32  | 8.21         | 1851.15      | 0.00 |
| run-024            | /localization/kinematic_state                                                                                   | 17.90 | 100.28   | 2.41         | 17.42        | 0.00 |
| run-024            | /localization/pose_estimator/pose_with_covariance                                                               | 4.67  | 599.94   | 36.09        | 255.78       | 0.00 |
| run-024            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.59  | 203.66   | 14.25        | 30.53        | 2.08 |
| run-025            | /control/command/control_cmd                                                                                    | 1.02  | 2651.12  | 7.30         | 1288.71      | 0.00 |
| run-025            | /localization/kinematic_state                                                                                   | 17.59 | 101.88   | 2.71         | 19.46        | 0.00 |
| run-025            | /localization/pose_estimator/pose_with_covariance                                                               | 1.94  | 1780.76  | 206.84       | 307.83       | 0.00 |
| run-025            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.23  | 205.94   | 14.71        | 34.35        | 1.99 |
| run-026            | /control/command/control_cmd                                                                                    | 3.90  | 1303.00  | 10.32        | 141.75       | 0.00 |
| run-026            | /localization/kinematic_state                                                                                   | 17.64 | 100.99   | 2.43         | 17.45        | 0.00 |
| run-026            | /localization/pose_estimator/pose_with_covariance                                                               | 1.46  | 2124.49  | 205.66       | 238.49       | 0.00 |
| run-026            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.32  | 204.72   | 15.56        | 33.78        | 2.02 |
| run-027            | /control/command/control_cmd                                                                                    | 1.09  | 3567.21  | 7.78         | 1452.89      | 0.00 |
| run-027            | /localization/kinematic_state                                                                                   | 19.10 | 66.28    | 2.25         | 16.61        | 0.00 |
| run-027            | /localization/pose_estimator/pose_with_covariance                                                               | 0.81  | 1906.26  | 202.85       | 255.54       | 0.00 |
| run-027            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.30  | 206.00   | 15.05        | 38.25        | 2.01 |
| run-028 (EXCLUDED) | /control/command/control_cmd                                                                                    | 11.10 | 215.79   | 5.60         | 73.01        | 0.00 |
| run-028 (EXCLUDED) | /localization/kinematic_state                                                                                   | 18.08 | 99.77    | 2.43         | 14.63        | 0.00 |
| run-028 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 4.82  | 620.03   | 37.40        | 220.61       | 0.00 |
| run-028 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.90  | 201.18   | 14.69        | 26.01        | 2.15 |
| run-029            | /control/command/control_cmd                                                                                    | 3.95  | 1646.42  | 7.97         | 902.26       | 0.00 |
| run-029            | /localization/kinematic_state                                                                                   | 19.02 | 72.74    | 2.54         | 14.67        | 0.00 |
| run-029            | /localization/pose_estimator/pose_with_covariance                                                               | 2.23  | 1481.36  | 160.63       | 260.09       | 0.00 |
| run-029            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.17  | 205.69   | 14.87        | 34.32        | 1.98 |
| run-030            | /control/command/control_cmd                                                                                    | 7.07  | 251.52   | 6.07         | 76.26        | 0.00 |
| run-030            | /localization/kinematic_state                                                                                   | 17.13 | 102.92   | 2.59         | 21.47        | 0.00 |
| run-030            | /localization/pose_estimator/pose_with_covariance                                                               | 2.98  | 1078.80  | 68.08        | 274.45       | 0.00 |
| run-030            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 8.42  | 203.88   | 14.72        | 37.68        | 2.04 |
| run-031 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/B/run-031/clock.csv' | -     | -        | -            | -            | -    |
| run-032 (EXCLUDED) | /control/command/control_cmd                                                                                    | 0.93  | 2953.60  | 4.47         | 13.95        | 0.00 |
| run-032 (EXCLUDED) | /localization/kinematic_state                                                                                   | 19.51 | 58.09    | 1.93         | 12.47        | 0.00 |
| run-032 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 3.01  | 520.34   | 28.13        | 219.87       | 0.00 |
| run-032 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 9.03  | 199.87   | 13.99        | 27.03        | 2.19 |
| run-033            | /control/command/control_cmd                                                                                    | 20.00 | 51.14    | 1.83         | 3.80         | 0.00 |
| run-033            | /localization/kinematic_state                                                                                   | 20.00 | 51.18    | 1.50         | 3.07         | 0.00 |
| run-033            | /localization/pose_estimator/pose_with_covariance                                                               | 10.00 | 101.99   | 9.81         | 12.56        | 0.00 |
| run-033            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 10.00 | 101.74   | 6.69         | 9.20         | 2.39 |

### Cell C

| run                | topic                                             | hz    | p95 ms | 1-hop p50 ms | 1-hop p99 ms | MB/s  |
| ------------------ | ------------------------------------------------- | ----- | ------ | ------------ | ------------ | ----- |
| run-001 (EXCLUDED) | /control/command/control_cmd                      | 19.96 | 51.16  | 1.05         | 5.30         | 0.00  |
| run-001 (EXCLUDED) | /localization/kinematic_state                     | 19.96 | 51.22  | 1.41         | 6.16         | 0.00  |
| run-001 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.45  | 14.65        | 19.88        | 0.00  |
| run-001 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.40  | 9.36         | 14.04        | 9.80  |
| run-002            | /control/command/control_cmd                      | 19.96 | 51.27  | 1.71         | 5.02         | 0.00  |
| run-002            | /localization/kinematic_state                     | 19.96 | 51.23  | 2.06         | 6.31         | 0.00  |
| run-002            | /localization/pose_estimator/pose_with_covariance | 19.96 | 52.98  | 14.56        | 18.98        | 0.00  |
| run-002            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.28  | 9.70         | 13.58        | 9.80  |
| run-003 (EXCLUDED) | /localization/kinematic_state                     | 19.96 | 51.35  | 1.94         | 4.01         | 0.00  |
| run-003 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.66  | 13.18        | 16.99        | 0.00  |
| run-003 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.59  | 8.33         | 11.22        | 10.06 |
| run-004            | /localization/kinematic_state                     | 19.96 | 51.30  | 1.91         | 4.15         | 0.00  |
| run-004            | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.23  | 12.64        | 16.54        | 0.00  |
| run-004            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.19  | 8.14         | 10.97        | 10.07 |
| run-005            | /localization/kinematic_state                     | 19.96 | 51.15  | 1.85         | 3.64         | 0.00  |
| run-005            | /localization/pose_estimator/pose_with_covariance | 19.96 | 52.66  | 12.71        | 15.99        | 0.00  |
| run-005            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 51.92  | 8.20         | 10.92        | 10.07 |
| run-006            | /localization/kinematic_state                     | 19.96 | 51.35  | 1.89         | 3.94         | 0.00  |
| run-006            | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.68  | 12.98        | 16.96        | 0.00  |
| run-006            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.33  | 8.27         | 10.82        | 10.06 |
| run-007            | /localization/kinematic_state                     | 19.96 | 51.30  | 1.92         | 3.77         | 0.00  |
| run-007            | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.22  | 13.00        | 17.05        | 0.00  |
| run-007            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.24  | 8.41         | 10.94        | 10.07 |
| run-008            | /localization/kinematic_state                     | 19.96 | 51.35  | 1.92         | 3.93         | 0.00  |
| run-008            | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.29  | 13.17        | 16.93        | 0.00  |
| run-008            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.12  | 8.50         | 11.15        | 10.07 |
| run-009            | /control/command/control_cmd                      | 19.95 | 51.18  | 1.48         | 3.50         | 0.00  |
| run-009            | /localization/kinematic_state                     | 19.95 | 51.21  | 1.38         | 3.57         | 0.00  |
| run-009            | /localization/pose_estimator/pose_with_covariance | 8.35  | 298.60 | 13.75        | 18.41        | 0.00  |
| run-009            | /sensing/lidar/top/pointcloud_raw_ex              | 19.95 | 52.11  | 8.70         | 11.40        | 10.06 |
| run-010            | /control/command/control_cmd                      | 19.96 | 51.31  | 1.43         | 5.23         | 0.00  |
| run-010            | /localization/kinematic_state                     | 19.96 | 51.25  | 1.80         | 6.28         | 0.00  |
| run-010            | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.01  | 14.31        | 18.45        | 0.00  |
| run-010            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.43  | 9.78         | 13.34        | 9.80  |
| run-011            | /control/command/control_cmd                      | 19.96 | 51.13  | 1.57         | 4.81         | 0.00  |
| run-011            | /localization/kinematic_state                     | 19.96 | 51.13  | 1.93         | 5.98         | 0.00  |
| run-011            | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.22  | 14.76        | 19.00        | 0.00  |
| run-011            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.23  | 9.71         | 13.37        | 9.80  |
| run-012            | /control/command/control_cmd                      | 19.96 | 51.14  | 1.72         | 5.09         | 0.00  |
| run-012            | /localization/kinematic_state                     | 19.96 | 51.12  | 2.10         | 5.82         | 0.00  |
| run-012            | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.26  | 15.05        | 19.42        | 0.00  |
| run-012            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.22  | 9.80         | 13.23        | 9.80  |
| run-013            | /control/command/control_cmd                      | 19.96 | 51.28  | 1.44         | 4.93         | 0.00  |
| run-013            | /localization/kinematic_state                     | 19.96 | 51.23  | 1.66         | 5.34         | 0.00  |
| run-013            | /localization/pose_estimator/pose_with_covariance | 19.96 | 53.63  | 14.73        | 19.90        | 0.00  |
| run-013            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.45  | 9.60         | 13.66        | 9.80  |
| run-014            | /control/command/control_cmd                      | 19.96 | 51.05  | 1.36         | 4.32         | 0.00  |
| run-014            | /localization/kinematic_state                     | 19.96 | 51.06  | 1.76         | 5.11         | 0.00  |
| run-014            | /localization/pose_estimator/pose_with_covariance | 19.96 | 52.63  | 13.90        | 18.05        | 0.00  |
| run-014            | /sensing/lidar/top/pointcloud_raw_ex              | 19.96 | 52.01  | 9.50         | 12.73        | 9.80  |

### Cell CAL-rmw

| run     | topic                                                           | hz  | p95 ms | 1-hop p50 ms | 1-hop p99 ms | MB/s |
| ------- | --------------------------------------------------------------- | --- | ------ | ------------ | ------------ | ---- |
| run-001 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-002 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-003 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-004 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-005 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-006 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-007 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-008 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-009 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-010 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-011 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-012 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-013 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-014 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |
| run-015 | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples | -   | -      | -            | -            | -    |

### Cell E

| run                | topic                                                                                                           | hz    | p95 ms  | 1-hop p50 ms | 1-hop p99 ms | MB/s |
| ------------------ | --------------------------------------------------------------------------------------------------------------- | ----- | ------- | ------------ | ------------ | ---- |
| run-001 (EXCLUDED) | RENDER FAILED: ValueError: need >= 2 paired (sim, wall) samples                                                 | -     | -       | -            | -            | -    |
| run-002 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/E/run-002/clock.csv' | -     | -       | -            | -            | -    |
| run-003 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/E/run-003/clock.csv' | -     | -       | -            | -            | -    |
| run-004 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/E/run-004/clock.csv' | -     | -       | -            | -            | -    |
| run-005 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/E/run-005/clock.csv' | -     | -       | -            | -            | -    |
| run-006 (EXCLUDED) | /control/command/control_cmd                                                                                    | 1.42  | 2774.51 | 24.69        | 2111.53      | 0.00 |
| run-006 (EXCLUDED) | /localization/kinematic_state                                                                                   | 19.94 | 58.00   | 4.80         | 17.19        | 0.00 |
| run-006 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 10.03 | 256.48  | 46.02        | 80.81        | 0.00 |
| run-006 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 19.85 | 53.98   | 14.27        | 22.61        | 2.20 |
| run-007 (EXCLUDED) | /control/command/control_cmd                                                                                    | 1.30  | 2812.52 | 20.50        | 1902.64      | 0.00 |
| run-007 (EXCLUDED) | /localization/kinematic_state                                                                                   | 19.94 | 57.11   | 5.19         | 17.73        | 0.00 |
| run-007 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 9.79  | 259.46  | 43.59        | 78.26        | 0.00 |
| run-007 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 19.86 | 53.64   | 14.53        | 23.85        | 2.20 |
| run-008 (EXCLUDED) | /control/command/control_cmd                                                                                    | 8.52  | 904.72  | 10.54        | 907.73       | 0.00 |
| run-008 (EXCLUDED) | /localization/kinematic_state                                                                                   | 19.88 | 55.40   | 5.43         | 20.23        | 0.00 |
| run-008 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 12.87 | 164.82  | 38.54        | 71.05        | 0.00 |
| run-008 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 19.87 | 54.30   | 15.83        | 29.18        | 2.20 |
| run-009 (EXCLUDED) | /control/command/control_cmd                                                                                    | 1.17  | 3267.05 | 7.38         | 111.01       | 0.00 |
| run-009 (EXCLUDED) | /localization/kinematic_state                                                                                   | 19.91 | 57.92   | 6.17         | 20.30        | 0.00 |
| run-009 (EXCLUDED) | /localization/pose_estimator/pose_with_covariance                                                               | 8.91  | 297.65  | 50.44        | 90.14        | 0.00 |
| run-009 (EXCLUDED) | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 19.91 | 54.19   | 14.68        | 24.44        | 2.20 |
| run-009 (EXCLUDED) | /tf                                                                                                             | 19.91 | 58.57   | 6.81         | 20.57        | 0.00 |
| run-010 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/E/run-010/clock.csv' | -     | -       | -            | -            | -    |
| run-011            | /control/command/control_cmd                                                                                    | 1.10  | 3620.92 | 22.09        | 2824.63      | 0.00 |
| run-011            | /localization/kinematic_state                                                                                   | 19.94 | 58.78   | 4.22         | 22.41        | 0.00 |
| run-011            | /localization/pose_estimator/pose_with_covariance                                                               | 5.01  | 595.98  | 62.48        | 117.47       | 0.00 |
| run-011            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 19.91 | 53.43   | 14.08        | 30.20        | 2.20 |
| run-011            | /tf                                                                                                             | 19.93 | 59.48   | 5.17         | 24.47        | 0.00 |
| run-012            | /control/command/control_cmd                                                                                    | 1.52  | 2830.65 | 7.53         | 2961.40      | 0.00 |
| run-012            | /localization/kinematic_state                                                                                   | 19.93 | 56.61   | 4.48         | 15.72        | 0.00 |
| run-012            | /localization/pose_estimator/pose_with_covariance                                                               | 7.52  | 324.84  | 51.45        | 102.38       | 0.00 |
| run-012            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 19.89 | 53.87   | 14.11        | 21.50        | 2.20 |
| run-012            | /tf                                                                                                             | 19.93 | 57.78   | 5.33         | 16.68        | 0.00 |
| run-013            | /control/command/control_cmd                                                                                    | 1.83  | 2623.41 | 27.81        | 922.45       | 0.00 |
| run-013            | /localization/kinematic_state                                                                                   | 19.32 | 65.90   | 6.57         | 25.83        | 0.00 |
| run-013            | /localization/pose_estimator/pose_with_covariance                                                               | 1.91  | 1576.09 | 112.47       | 192.82       | 0.00 |
| run-013            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 19.83 | 54.32   | 14.06        | 27.38        | 2.19 |
| run-013            | /tf                                                                                                             | 19.31 | 65.79   | 7.71         | 26.70        | 0.00 |
| run-014            | /control/command/control_cmd                                                                                    | 1.18  | 3712.71 | 7.17         | 1451.95      | 0.00 |
| run-014            | /localization/kinematic_state                                                                                   | 19.93 | 57.51   | 4.56         | 16.03        | 0.00 |
| run-014            | /localization/pose_estimator/pose_with_covariance                                                               | 6.91  | 371.28  | 50.07        | 92.86        | 0.00 |
| run-014            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 19.90 | 54.02   | 13.94        | 22.33        | 2.20 |
| run-014            | /tf                                                                                                             | 19.93 | 58.09   | 5.45         | 17.18        | 0.00 |
| run-015            | /control/command/control_cmd                                                                                    | 1.65  | 2819.23 | 17.39        | 2861.72      | 0.00 |
| run-015            | /localization/kinematic_state                                                                                   | 19.90 | 58.52   | 5.54         | 19.44        | 0.00 |
| run-015            | /localization/pose_estimator/pose_with_covariance                                                               | 4.97  | 517.72  | 67.51        | 136.52       | 0.00 |
| run-015            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 19.87 | 54.00   | 14.48        | 25.23        | 2.20 |
| run-015            | /tf                                                                                                             | 19.90 | 59.54   | 6.11         | 21.73        | 0.00 |
| run-016            | /control/command/control_cmd                                                                                    | 4.21  | 961.44  | 32.75        | 435.07       | 0.00 |
| run-016            | /localization/kinematic_state                                                                                   | 19.85 | 60.33   | 5.64         | 21.35        | 0.00 |
| run-016            | /localization/pose_estimator/pose_with_covariance                                                               | 3.44  | 710.21  | 85.38        | 184.07       | 0.00 |
| run-016            | /sensing/lidar/top/pointcloud_raw_ex                                                                            | 19.91 | 54.14   | 14.88        | 23.18        | 2.20 |
| run-016            | /tf                                                                                                             | 19.85 | 61.36   | 6.59         | 22.44        | 0.00 |

### Cell E0

| run                | topic                                                                                                            | hz    | p95 ms   | 1-hop p50 ms | 1-hop p99 ms | MB/s |
| ------------------ | ---------------------------------------------------------------------------------------------------------------- | ----- | -------- | ------------ | ------------ | ---- |
| run-001            | /control/command/control_cmd                                                                                     | 5.14  | 1125.27  | 30.42        | 970.97       | 0.00 |
| run-001            | /localization/kinematic_state                                                                                    | 14.84 | 121.22   | 15.07        | 130.28       | 0.00 |
| run-001            | /localization/pose_estimator/pose_with_covariance                                                                | 0.14  | 17151.50 | 74.21        | 123.77       | 0.00 |
| run-001            | /sensing/lidar/top/pointcloud_before_sync                                                                        | 8.42  | 137.22   | 30.75        | 148.52       | 1.05 |
| run-002            | /control/command/control_cmd                                                                                     | 3.79  | 1065.31  | 39.00        | 321.73       | 0.00 |
| run-002            | /localization/kinematic_state                                                                                    | 14.19 | 125.23   | 10.69        | 103.99       | 0.00 |
| run-002            | /localization/pose_estimator/pose_with_covariance                                                                | 0.11  | 24306.07 | 74.14        | 116.44       | 0.00 |
| run-002            | /sensing/lidar/top/pointcloud_before_sync                                                                        | 8.43  | 135.14   | 22.82        | 117.07       | 1.05 |
| run-003            | /control/command/control_cmd                                                                                     | 2.11  | 3184.08  | 41.24        | 2610.16      | 0.00 |
| run-003            | /localization/kinematic_state                                                                                    | 13.84 | 128.30   | 6.19         | 132.21       | 0.00 |
| run-003            | /localization/pose_estimator/pose_with_covariance                                                                | 0.27  | 12456.53 | 65.48        | 106.13       | 0.00 |
| run-003            | /sensing/lidar/top/pointcloud_before_sync                                                                        | 8.38  | 137.15   | 25.80        | 145.52       | 1.04 |
| run-004            | /control/command/control_cmd                                                                                     | 3.97  | 1179.17  | 27.19        | 354.75       | 0.00 |
| run-004            | /localization/kinematic_state                                                                                    | 13.39 | 132.25   | -2.40        | 117.01       | 0.00 |
| run-004            | /localization/pose_estimator/pose_with_covariance                                                                | 0.17  | 10398.18 | 72.28        | 165.89       | 0.00 |
| run-004            | /sensing/lidar/top/pointcloud_before_sync                                                                        | 8.41  | 135.64   | 10.71        | 129.71       | 1.05 |
| run-005 (EXCLUDED) | RENDER FAILED: ValueError: need >= 2 arrivals                                                                    | -     | -        | -            | -            | -    |
| run-006 (EXCLUDED) | RENDER FAILED: ValueError: need >= 2 arrivals                                                                    | -     | -        | -            | -            | -    |
| run-007            | /control/command/control_cmd                                                                                     | 4.13  | 1086.64  | -4.11        | 161.74       | 0.00 |
| run-007            | /localization/kinematic_state                                                                                    | 13.37 | 131.17   | 8.86         | 140.39       | 0.00 |
| run-007            | /localization/pose_estimator/pose_with_covariance                                                                | 0.10  | 17906.81 | 22.44        | 117.71       | 0.00 |
| run-007            | /sensing/lidar/top/pointcloud_before_sync                                                                        | 8.36  | 141.18   | 28.90        | 160.61       | 1.04 |
| run-008            | /control/command/control_cmd                                                                                     | 2.33  | 1688.18  | 37.42        | 259.36       | 0.00 |
| run-008            | /localization/kinematic_state                                                                                    | 13.96 | 122.93   | 9.52         | 78.92        | 0.00 |
| run-008            | /localization/pose_estimator/pose_with_covariance                                                                | 0.08  | 16856.00 | 50.05        | 121.25       | 0.00 |
| run-008            | /sensing/lidar/top/pointcloud_before_sync                                                                        | 8.41  | 139.28   | 24.75        | 95.44        | 1.05 |
| run-009 (EXCLUDED) | /control/command/control_cmd                                                                                     | 1.62  | 1983.82  | -3605.10     | -507.16      | 0.00 |
| run-009 (EXCLUDED) | /localization/kinematic_state                                                                                    | 0.98  | 4674.55  | 626.73       | 22757.40     | 0.00 |
| run-009 (EXCLUDED) | /sensing/lidar/top/pointcloud_before_sync                                                                        | 1.78  | 3838.02  | -599.59      | 16979.72     | 0.22 |
| run-010 (EXCLUDED) | RENDER FAILED: FileNotFoundError: [Errno 2] No such file or directory: 'benchmarks/results/E0/run-010/clock.csv' | -     | -        | -            | -            | -    |

## 4. The duel verdict

### 4.1 The single invocation, and its complete output

```bash
PYTHONPATH=. python3 benchmarks/scripts/duel_verdict.py A B | tee /tmp/p3-duel-verdict.md
```

Exit status 0. No flags: `--results` defaults to `benchmarks/results`,
`--margins` to `benchmarks/config/margins.yaml`, `--min-n` to the pre-registered 10. **No filtering flag is needed or was passed** — `duel_verdict.py` drops
excluded and non-duel-admissible runs itself, on separate counters, so the pool
is the 10 static pairs by construction (see section 0).

Metric definitions: benchmarks/README.md, "Primary-duel metric definitions".

| metric                | arm         | n (a/b) | delta_median | 95% ci             | margin | verdict           | notes                                                                                                                                                                                                                                    |
| --------------------- | ----------- | ------- | ------------ | ------------------ | ------ | ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| one_hop_wall_ms       | static      | 10/10   | -6.281       | [-6.542, -5.828]   | 2      | a_better          | 3 run(s) not duel-admissible in A; 7 run(s) not duel-admissible in B; fit_residual_ns median: a=1848316 b=22475834                                                                                                                       |
| lidar_to_ndt_sim_ms   | static      | 10/10   | -5.817       | [-8.106, -4.976]   | 5      | a_better          | 3 run(s) not duel-admissible in A; 7 run(s) not duel-admissible in B                                                                                                                                                                     |
| control_staleness_ms  | static      | 0/0     | -            | -                  | 10     | insufficient-data | UNAVAILABLE: cell A: control_published_time_topic not registered for this cell (Tasks 13/20)                                                                                                                                             |
| carla_process_cpu_pct | static      | 10/10   | -12.873      | [-16.698, -11.129] | 10     | a_better          | 3 run(s) not duel-admissible in A; 7 run(s) not duel-admissible in B                                                                                                                                                                     |
| achieved_rate_ratio   | static      | 10/10   | 0.104        | [0.090, 0.114]     | 0.02   | b_better          | 3 run(s) not duel-admissible in A; 7 run(s) not duel-admissible in B                                                                                                                                                                     |
| one_hop_wall_ms       | closed-loop | 0/0     | -            | -                  | 2      | insufficient-data | 15 run(s) excluded from B; 1 run(s) not duel-admissible in A; 1 run(s) not duel-admissible in B; UNDER-N: a has 0 run(s) (< 10); UNDER-N: b has 0 run(s) (< 10); insufficient data for a bootstrap CI (need >= 3 per side; got a=0, b=0) |
| lidar_to_ndt_sim_ms   | closed-loop | 0/0     | -            | -                  | 5      | insufficient-data | 15 run(s) excluded from B; 1 run(s) not duel-admissible in A; 1 run(s) not duel-admissible in B; UNDER-N: a has 0 run(s) (< 10); UNDER-N: b has 0 run(s) (< 10); insufficient data for a bootstrap CI (need >= 3 per side; got a=0, b=0) |
| control_staleness_ms  | closed-loop | 0/0     | -            | -                  | 10     | insufficient-data | UNAVAILABLE: cell A: control_published_time_topic not registered for this cell (Tasks 13/20)                                                                                                                                             |
| carla_process_cpu_pct | closed-loop | 0/0     | -            | -                  | 10     | insufficient-data | 15 run(s) excluded from B; 1 run(s) not duel-admissible in A; 1 run(s) not duel-admissible in B; UNDER-N: a has 0 run(s) (< 10); UNDER-N: b has 0 run(s) (< 10); insufficient data for a bootstrap CI (need >= 3 per side; got a=0, b=0) |
| achieved_rate_ratio   | closed-loop | 0/0     | -            | -                  | 0.02   | insufficient-data | 15 run(s) excluded from B; 1 run(s) not duel-admissible in A; 1 run(s) not duel-admissible in B; UNDER-N: a has 0 run(s) (< 10); UNDER-N: b has 0 run(s) (< 10); insufficient data for a bootstrap CI (need >= 3 per side; got a=0, b=0) |

M2 three-way reconciliation (cadence.reconcile_drops over publisher_counts.json), per cell alongside the achieved_rate_ratio duel row above (README.md, "achieved_rate_ratio"):

| cell | arm         | n measurable | n not measurable | n zero-published | n observer | publisher_drop_rate (median) | publisher_drop_rate (max) | observer_loss_rate (median) | observer_loss_rate (max) | notes                                                    |
| ---- | ----------- | ------------ | ---------------- | ---------------- | ---------- | ---------------------------- | ------------------------- | --------------------------- | ------------------------ | -------------------------------------------------------- |
| A    | static      | 10           | 0                | 0                | 10         | 0.021                        | 0.385                     | 0.000                       | 0.000                    | 3 run(s) not duel-admissible                             |
| B    | static      | 10           | 0                | 0                | 10         | 0.020                        | 0.022                     | 0.085                       | 0.108                    | 7 run(s) not duel-admissible                             |
| A    | closed-loop | 0            | 0                | 0                | 0          | -                            | -                         | -                           | -                        | no runs found for this arm; 1 run(s) not duel-admissible |
| B    | closed-loop | 0            | 0                | 0                | 0          | -                            | -                         | -                           | -                        | no runs found for this arm; 1 run(s) not duel-admissible |

### 4.2 Reading the table

**Direction convention.** `benchmarks/config/margins.yaml`'s own header
registers `delta = extension - tier4-native; lower is better`, and
`benchmarks/analysis/stats.py`'s `equivalence_decision` encodes exactly that: it
returns `a_better` when the whole CI sits below zero and `b_better` when the
whole CI sits above it. The convention is applied uniformly to all five metrics.

**On `achieved_rate_ratio` that uniform convention inverts the label, and the
row must not be read as a tier4-native win.** The metric is
`inter_arrival_stats(header_stamp_ns).hz / lidar_expected_hz` — each cell
normalised against **its own** registered sensor target (`lidar_expected_hz`
20.0 on cell A, 10.0 on cell B), and `benchmarks/README.md:575-594` registers
what that fraction is _for_: "Taken in the sim domain, the ratio measures
dropped or skipped frames instead, which is what M2 is for." It is a **shortfall
detector**. A larger value is a smaller shortfall against the cell's own target,
so on this metric — and on this metric alone among the five — **higher is
better**, and the uniform lower-is-better label inverts.

`equivalence_decision` prints `b_better` exactly when the whole CI sits above
zero, i.e. when median(A) > median(B). So Δ = +0.104 with CI [+0.090, +0.114]
says **cell B falls 0.104 of its own registered target further short than cell A
does** — five times the 0.02 margin, in cell A's favour. No new statistic is
needed to read the direction; it follows from the printed sign.

The M2 reconciliation table produced by the **same** invocation corroborates it
independently and on a different quantity: `observer_loss_rate` median **0.000**
/ max **0.000** on cell A against **0.085** / **0.108** on cell B. Cell A loses
no frames observer-side; cell B does.

So, on the metrics' own senses:

| metric                  | arm         | Δ median (A − B) | 95% CI             | margin | printed verdict     | which approach the row favours                             |
| ----------------------- | ----------- | ---------------- | ------------------ | ------ | ------------------- | ---------------------------------------------------------- |
| `one_hop_wall_ms`       | static      | −6.281 ms        | [−6.542, −5.828]   | 2.0    | `a_better`          | **extension** (lower wall latency)                         |
| `lidar_to_ndt_sim_ms`   | static      | −5.817 ms        | [−8.106, −4.976]   | 5.0    | `a_better`          | **extension** (shorter sensor→NDT pipeline)                |
| `control_staleness_ms`  | static      | —                | —                  | 10.0   | `insufficient-data` | **neither — UNAVAILABLE**, cell A binding never registered |
| `carla_process_cpu_pct` | static      | −12.873 pp       | [−16.698, −11.129] | 10.0   | `a_better`          | **extension** (lower simulator CPU)                        |
| `achieved_rate_ratio`   | static      | +0.104           | [+0.090, +0.114]   | 0.02   | `b_better`          | **extension** — label polarity artifact, see above         |
| all five                | closed-loop | —                | —                  | —      | `insufficient-data` | **not computable**, see 5.1                                |

**Four computable rows, zero `parity` rows, four separations in the same
direction.** That is the verdict.

**They are NOT four independent findings, and this is stated here rather than
left for a reader to infer independence from a table.** Three of the four are
plausibly downstream of **one** condition — cell B's depressed NDT/transport
behaviour, for which Phase 0 eliminated a candidate cause and identified
**none** (see 5.2):

- `achieved_rate_ratio` **is** that deficit, measured directly. Its 0.104 gap is
  the shortfall itself, not a second, separate result.
- `lidar_to_ndt_sim_ms` is the sensor→NDT pipeline on the same chain, in the
  same cell, over the same scoring window. A chain delivering a third of its
  expected poses is not independent of the latency of the poses it does deliver.
- `one_hop_wall_ms` is the transport hop those samples traverse — and the
  campaign's registered account of cell B's loss is precisely a transport
  property (`rmw_fastrtps_cpp` with SHM off; `benchmarks/README.md`'s A-side
  instrument-asymmetry bound and `benchmarks/results/CAL-rmw/PROVENANCE.md`).

`carla_process_cpu_pct` is the one row with a **different measurand** — the
simulator process's own CPU, sampled from `resources.csv` rather than derived
from the message stream — so it is the least entangled of the four.

**No decomposition is attempted and none may be read in.** This campaign does
not hold the measurement that would separate "the extension is faster" from
"cell B's transport is losing samples, and every message-derived metric sees
it". Assigning a share to each would be exactly the class of claim outrunning
its measurement that this record keeps catching. What the four rows jointly
support is the **direction**. What they do not support is a count of four
independent effects, or any single row's effect size read as an approach
difference in isolation. The instrument that would settle it is a controlled
transport comparison — see 9.4.

### 4.3 What the verdict does NOT say

- **It is not a closed-loop result.** Every closed-loop row is
  `insufficient-data` with `n = 0/0`. The extension side has one valid
  closed-loop run in cell A (`run-002`, bring-up class, `duel_admissible:
false`) and five more in cell C — none of which is duel data — and the
  tier4-native side has none at all under its registered transport.
- **It is not corrected for the byte-layout asymmetry, and that asymmetry runs
  AGAINST the winner.** `benchmarks/README.md:3986-4008` registers that
  `one_hop_wall_ms` and `lidar_to_ndt_sim_ms` are byte-sensitive and that **cell
  A ships 2.118× the bytes for the same point count** (512 184 B/msg against
  241 813 B/msg, `bench_observer` medians). An A-favourable latency result on
  those two metrics is therefore **conservative** — cell A won while carrying
  2.1× the payload. The same registration says the converse: a B-favourable
  result on them would have been confounded. Neither of the two A-favourable
  latency rows needs that caveat to survive; it is recorded because the
  registration requires it either way.
- **The CPU row's direction is likewise conservative.** `README:4010-4018`
  records that cell B's running binary emitted a 16 B/point cloud where its own
  pinned source specifies 32 B/point — less data per point, i.e. less work than
  its registration implies — so correcting that could only push cell B's cost
  **up**, never down.
- **It says nothing about cell B's NDT rate being explained.** The rate deficit
  is a registered confound whose cause Phase 0 did **not** identify. See 5.2.
  That is about the **cause**. The separate point in 4.2 — that three of the
  four rows are not independent **of each other**, because they are three views
  of that same unexplained deficit — is about **non-independence**, and both
  caveats are needed. Neither substitutes for the other: a reader could accept
  "the cause is unknown" and still wrongly count four corroborating results.
- **It is not a per-approach ranking of the three approaches.** The E family is
  context, not a duel side; cell C is confirmatory. No cross-approach
  equivalence statistic was computed and none may be inferred from these rows.

## 5. Findings that bound the verdict

### 5.1 FINDING: latched-topic delivery to `behavior_path_planner`, and why the closed-loop verdict does not exist

Full evidence, probe scripts and raw captures:
`benchmarks/evidence/b-vector-map-delivery/`. Full narrative:
`benchmarks/results/PROVENANCE.md` §7.7–§7.11.

**The defect.** Latched (`TRANSIENT_LOCAL`) messages, published once, are
received promptly by `topic_state_monitor_*` and **not** by
`behavior_path_planner`. The two behave as **independent draws**, not as
proxies for one another, and the divergence is visible in single runs in both
directions. Across the **seven** cell-B runs that reached the arm and failed it,
the planner's own last readiness line names three different missing inputs:
**map 2** (`run-008`, `run-028`), **route 4** (`run-009`, `run-010`, `run-011`,
`run-032`), **operation_mode 1** (`run-012`). The map half was **reproduced
standalone** — same image digest, same bundle, same launch line, **no CARLA and
no harness at all** — where two consecutive runs of one script, two minutes
apart, gave "never in 113 s" and "0.97 s".

**The exact tally, and every figure in it is reproducible.** Cell B filed 15
closed-loop runs under `rmw_fastrtps_cpp`, plus `B/run-033` under the cyclonedds
deviation:

| class                                     | n      | runs                                                         | reached the arm?                 |
| ----------------------------------------- | ------ | ------------------------------------------------------------ | -------------------------------- |
| `crash:cell-launch`                       | **7**  | `run-001`…`run-006`; **`run-031` — see the carve-out below** | no — except `run-031`, which did |
| `crash:collect_gt`                        | **1**  | `run-007`                                                    | no                               |
| `gate:arm-failed`                         | **7**  | `run-008`…`run-012`, `run-028`, `run-032`                    | **yes**, and failed it           |
| **total under the registered transport**  | **15** | all excluded                                                 | **0 armed**                      |
| deviation probe, not a cell-B measurement | 1      | `run-033` (cyclonedds)                                       | **yes — ARMED**                  |

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

Two counts are therefore in play and neither may stand in for the other: **15**
is how many closed-loop runs cell B filed and lost under its registered
transport, and **7** is how many of those got far enough to attempt the arm.

**CARVE-OUT — `B/run-031` is a delivery loss wearing a launch-crash label, and
the row above must not be read as covering it.** Of the 8 crash-class runs, 7
genuinely never came up and therefore say nothing about the latched-delivery
defect. `run-031` is the exception: its cell came up far enough to produce a
**551 KB `tier4-autoware.log`** and a filed `vector-map-delivery.json`
recording `captured: true`, `data_bytes: 1305281`, `subscriber_count: 16`,
`matching_settled: true`, **three** re-publish attempts and
`verified: false, exit_code: 5` (`EXIT_NOT_VERIFIED`). What failed was the
delivery gate, which was **fatal at the time**; `cells/tier4-native.sh up`
failed as a consequence and the run was filed criterion 1. PROVENANCE §7.9
already recorded the labelling ambiguity as housekeeping
("`gate:<detail>` under criterion 2 arguably fits a readiness-check abort
better … criterion 1 is the safer reading. Left as filed"), and §7.8 records
the finding that matters more than the verdict: that run's own log shows the
re-published map **being delivered** to `lanelet2_map_visualization` and
`vector_map_tf_generator` on all three attempts while the endpoint the gate
read received none of them. So `run-031` belongs to the defect's evidence, not
outside it. **NOT TESTED: whether `run-031` would have armed** — the gate
aborted before any route was set. The direction of the original gloss was
conservative (it under-counts the defect's reach), but it was false for 1 of 8,
and it is corrected rather than left standing. An earlier revision of this
document said "14 times" and "the six runs that reached the arm"; both are
corrected here, and `run-032` — a seventh `gate:arm-failed`, blocked on the
route per PROVENANCE §7.10 — is the run both omitted.

**The bounding probe.** `B/run-033`, one deliberate non-duel deviation run
(owner ruling), changed **only the middleware**:

```text
BENCH_TIER4_TRANSPORT_DEVIATION="task5 cyclonedds bounding probe: is the latched-delivery defect Fast-DDS-specific?" \
  bash benchmarks/run.sh B --arm closed-loop --rmw rmw_cyclonedds_cpp --dds-profile none
```

It **armed on the first try**, drove to within `goal_closest_approach_m`
**0.103 m**, and passed its quality gate (`gate_pass: true`, `reasons: []`) —
against 0-for-15 on the registered transport (the tally above).

**THE ATTRIBUTION BOUNDARY — read this before quoting the finding.** The defect
is a property of **the as-shipped tier4 transport configuration on this host**.
It is **NOT established as an intrinsic property of the tier4-native approach**,
and nothing in this document may be read as though it were:

- **n = 1** on the cyclonedds side. One arming run is not a rate, exactly as two
  failing bring-ups were not one.
- **Fast-DDS version, kernel and loopback behaviour are uncontrolled.** The
  Autoware image ships Fast-DDS 2.6.11 and the fork builds against 2.11.2; no
  other version pair was tried.
- **The cyclonedds configuration is itself not measurement-grade.**
  `benchmarks/README.md`'s Task 9 transport matrix says in terms not to use rows
  6/11 for measurement. `run-033` is a bounding probe, **not** a proposal to
  re-register cell B's transport, and nothing in it licenses swapping the
  middleware for collection.
- The probe shows the defect **does not occur** under a different middleware on
  this host. It does not show _why_, and it does not show that Fast-DDS is at
  fault rather than the interaction between the fork's SHM-only locators, the
  `udp_only.xml` workaround they force, and this host's loopback.

This campaign has already caught three separate claims outrunning their
measurements (the Phase 0 count-vs-emission criterion, the P4 causal wording,
and the criterion-3 substance mismatch). This finding must not become the
fourth.

**One observation that touches a standing ruling, recorded and NOT acted on.**
`B/run-033`'s `ndt_rate_ratio` is **1.000**, against **0.257–0.989** across every
filed Fast-DDS cell-B run. Cell B's failing M5 rate gate is the registered
branch-(c) confound, and this document **neither reopens nor amends** that
ruling — but a reader deciding branch (c)'s future should know that the confound
is absent on the one bring-up that changed only the middleware. **n = 1.**

**The consequence.** Cell B's closed-loop arm is not collectable under its
registered transport, so **the A-vs-B closed-loop equivalence verdict is NOT
COMPUTABLE**. What is unaffected: the static-arm verdict (the delivery
workaround is closed-loop only, pinned by a test that asserts the static
bring-up reaches no container command at all), and cell C's closed-loop
confirmatory data on the extension path.

### 5.2 Phase 0 ruled branch (c) — and cell B's depressed NDT rate remains UNEXPLAINED

Phase 0's hypothesis, its four probes with pre-declared outcomes, and three
adjudication branches were registered in the P3 completion design **before any
measurement existed**. The full transcript, pre-declaration copied verbatim
above the measurements, is committed at
`benchmarks/evidence/p3-phase0/probe-transcripts.md`.

**Hypothesis under test:** cell B's depressed NDT rate is caused by double
publication on `/sensing/lidar/concatenated/pointcloud` (the harness relay plus
tier4 `concatenate_data`), absent on cell A.

**The differential is REAL.** Measured with the same stamp-identity instrument
on both cells: cell A has 2 advertised publishers and **1 emitter** (`RELAY_OUT`/
`RELAY_IN` ratio 0.995, **0** duplicate stamps); cell B has 2 advertised
publishers and **2 emitters** (ratio 1.818, **72** duplicate stamps of 88
unique, 0/0 loss symmetry).

**But the differential is not the cause, and branch (c) was selected by
ELIMINATION on the pre-declared table:**

| branch                     | pre-declared trigger                        | measured                                                                                 | selected |
| -------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------- | -------- |
| (a) recovery               | P4 NDT rate ≥ 9.0 Hz with the relay stopped | best post-kill reading on any of four runs ≈ **0.07 Hz** — two orders of magnitude short | no       |
| (b) concat output unusable | P3 fails: empty/malformed clouds            | clouds are well-formed, non-empty, `base_link`, steady at 7.612 Hz                       | no       |
| (c) no recovery            | P4 stays < 0.9 with a single publisher      | 0.48 of expectation pre-kill; no run demonstrated recovery                               | **YES**  |

**Branch (c) prescribes no harness change, and none was made.** Consequences,
all as pre-declared: no `harness:<commit>` reclassification of B `run-013`…
`run-022`; no 10-fresh-pair static recollection; and **no `duel_admissible` flip
on A `run-003`…`run-012`** — the spec conditions that on branches (a)/(b), which
did not fire, so the A static pair-halves keep `duel_admissible: true`. No gate
was tuned, no threshold moved, no run excluded, no harness file edited.

**What Phase 0 did NOT establish, stated plainly because the verdict carries
it:** it eliminated double publication as the cause; **it did not identify a
cause.** The M5 rate gate keeps failing on cell B. The gate was never tuned and
its 0.9 threshold was never touched. The verdict carries that fact rather than
resolving it.

**The duel pool's exact split, because two different counts are in circulation
and one of them is wrong.** Over `B/run-013`…`run-022`:

| outcome                                             | n     | runs                                     | `ndt_rate_ratio` |
| --------------------------------------------------- | ----- | ---------------------------------------- | ---------------- |
| `gate_pass: true`                                   | **1** | `run-013`                                | 0.9892           |
| `gate_pass: false`, all on `ndt rate ratio X < 0.9` | **8** | `run-014`…`run-018`, `run-020`…`run-022` | 0.2569–0.8505    |
| unscoreable — no `quality.json`                     | **1** | `run-019`                                | —                |

**Eight of the ten fail, not nine.** Reproduce:

```bash
python3 - <<'PY'
import json, pathlib
for run in sorted(pathlib.Path("benchmarks/results/B").glob("run-*")):
    m = json.loads((run / "manifest.json").read_text())
    if m["arm"] != "static" or not m["duel_admissible"]:
        continue
    q = run / "quality.json"
    if not q.is_file():
        print(run.name, "UNSCOREABLE (no quality.json)")
        continue
    d = json.loads(q.read_text())
    print(run.name, "gate_pass=", d["gate_pass"], "ndt_rate_ratio=", round(d["ndt_rate_ratio"], 4))
PY
```

An earlier revision of this document said "nine of the ten … fail", which
contradicted its own §5.1 range of 0.257–**0.989** (that range spans **all**
filed cell-B runs, and its upper end IS `run-013`'s passing 0.989) and
**overstated the pervasiveness of the campaign's central unexplained
confound**. Corrected here. **`benchmarks/results/PROVENANCE.md` §4.1 carries
the same "Nine cell-B static runs fail the M5 gate" wording and is likewise
wrong by one**; it is left as written, per the convention that a claim stays in
the record with the diagnostic that corrected it — this is that diagnostic, and
§10.3 of that file points back here.

**And the ranges, stated correctly — the first repair of this passage got the
population label wrong.** It said `0.257–0.989` was "every filed Fast-DDS
cell-B run". It is not; it is the **duel pool's own** min–max over its nine
scoreable runs. The three figures, all recomputed from `quality.json`:

| range             | population                                                                                                                               | n   |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | --- |
| **0.2569–0.8505** | the **failing** duel-pool runs                                                                                                           | 8   |
| **0.2569–0.9892** | **all scoreable duel-pool runs** — the same population plus `run-013`'s pass                                                             | 9   |
| **0.0386–0.9892** | all scoreable filed cell-B **static** runs (adds `run-023`, `run-024`, `run-027`, `run-029`, `run-030`; `run-027`'s 0.0386 is the floor) | 14  |

So the first two are **one population** differing only by whether the passing
run is included — not, as that revision claimed, "two different populations
that must not be swapped". The count fix (eight, not nine) is unaffected and
stands. `0.257–0.989` as §5.1 and PROVENANCE §7.11 use it — the range
`B/run-033`'s 1.000 is contrasted against — is the **duel pool's** scoreable
range, and both places label it "every filed Fast-DDS B run", which is the same
mislabelling; the contrast itself is unharmed, since 1.000 sits above every one
of the 14.

Two corrections stay in the record with the diagnostics that produced them,
per the campaign's convention: Phase 0's first ruling rested on a publisher
**count**, which cannot distinguish advertising from emitting and so measured a
quantity the hypothesis does not name (PROVENANCE §6.5); and the second ruling's
causal wording — "killing the relay stops NDT" — is refuted by the repository's
own `results/B/run-027/observer.csv`, which records NDT **resuming** ≈ 29 s after
the kill with `concatenate_data` as sole publisher (PROVENANCE §6.8). The branch
ruling is unaffected by either; only the reasoning is.

### 5.3 `C/run-009` — armed, engaged, never drove, unscored, and NOT excludable

`C/run-009` reached `ARMED: localized, route set to (81571.616, 50019.827),
autonomous engaged` and the harness's own gate printed `OK:
/control/command/control_cmd is flowing`. It then recorded **0.000 m** of
ground-truth displacement from spawn, against ~231 m on all five sibling runs.
The M5 gate refused to score it, verbatim:

```text
QUALITY GATE FAIL: cannot resolve the closed-loop spatial window: no odometry sample inside the spatial window
WARN: the M5 gate did not score .../benchmarks/results/C/run-009 (named reason above);
      no quality.json is written, so its consumers fail loudly
```

**FOR ANY CONSUMER OF THIS CELL:** `C/run-009` is the one run in cell C that is
`excluded: false` **and** has **no `quality.json`**. Iterating cell C's
unexcluded runs and assuming a `quality.json` exists **will fault on it**. That
is the harness's intended fail-loud behaviour and it must be **special-cased
explicitly** — filtering on `excluded` is not sufficient for this cell. This
document's own per-cell reporting special-cases it rather than filtering.

It is filed unexcluded because **no `exclusions.md` criterion 1–10 matches and
none was stretched to fit**: criterion 2 covers the gated control command never
flowing, and here it _did_ flow (7.67 Hz over 23 samples, all-zero longitudinal
— all-zero is not silence); criterion 1 does not apply (nothing crashed);
and there is deliberately **no quality-based criterion**. A run that fails to
drive is a _failing_ run, not an excludable one. `run.sh` step 14 declined to
fire an exclusion on its own.

**Root-cause LEAD, NOT TESTED.** `C/run-009`'s
`/localization/pose_estimator/pose_with_covariance` ran at **8.35 Hz, p95
298.60 ms**, against 19.96 Hz / ≈53 ms on every other cell C run ever filed
(visible in the section 3 table). The collapse is **specific to the pose
estimator**: LiDAR, `kinematic_state` and `control_cmd` were all ~19.95 Hz on
the same run. It is a plausible source of the `is_autonomous_mode_available=
False` that made `change_to_autonomous` refuse five times, and of a control path
that then commanded zero — but nothing tested the link, the direction of
causation is unestablished, and the run has no `quality.json` so its
`ndt_rate_ratio` was never computed. **Recorded as a lead. It is not a finding.**

`C/run-014` was collected as the make-up run, so cell C's closed-loop arm
reaches n = 5 valid.

## 6. Cell E0 — published as CONTEXT, never as a verdict

**Cell E0's five valid static runs are `run-002`, `run-003`, `run-004`,
`run-007` and `run-008`.** Their measurements are in section 3.

> **QUOTED INLINE, NOT MERELY CITED — `benchmarks/results/PROVENANCE.md` §9.9,
> the finding that governs this row:**
>
> **"FINDING: cell E0's exclusion is CORRELATED WITH ITS OWN RESULT."**
>
> "`E0/run-005` and `run-006` were excluded `harness:e7ba92a`. The mechanism,
> diagnosed exactly: on each, NDT published **exactly one** pose for the whole
> run. `benchmarks/report.py`'s `summarize_run` computes per-topic cadence
> through `analysis/cadence.py`'s `inter_arrival_stats`, which raises
> `need >= 2 arrivals` on a single sample; run.sh's step-15 smoke therefore
> fails, and its handler files the run under criterion 3's catch-all."
>
> §9.9 states in terms that a reader quoting it "must carry **both**" of its
> claims — the sampling bias (iii) **and** the criterion-substance mismatch
> (i)–(ii) that produces it. All three items are therefore quoted here, not
> just the one that bites hardest:
>
> "**(i) The reason STRING is verbatim; the criterion's SUBSTANCE does not fit,
> and this has to be named rather than softened.** `harness:e7ba92a` matches
> criterion 3's registered form exactly. But criterion 3 reads, in full,
> 'Harness defect discovered **and fixed** (the run was measured with a broken
> observer/injector)', and on these two runs: **nothing was broken** … the
> run's data is intact. **nothing was fixed.** No harness defect was discovered
> or repaired in response … One message is not a malfunction on this cell; it
> is **cell E0's registered result in its sharpest form**."
>
> "**(ii) What makes it defensible, stated so it cannot be mistaken for
> manipulation.** The `harness:<commit>` ⇄ criterion-3 mapping is
> **pre-registered in the harness itself**, at `run.sh:1028-1029` … So the
> label was applied **mechanically by committed code**, to a rule written
> before cell E0's data existed, and not chosen after seeing which runs it
> would drop. The substance mismatch is a property of the pre-registration, not
> an exercise of discretion inside this task."
>
> "**(iii) The exclusion is NOT independent of the measurement.** The runs the
> filing path drops are precisely the runs where the as-shipped bridge performed
> **worst**. The six other E0 runs are not a random sample of E0's behaviour:
> they are E0's behaviour _conditioned on NDT having emitted at least two
> poses_. The campaign registered 'deliberately **no quality-based criterion**',
> and this is a quality-based exclusion arriving through a registered
> criterion's back door."
>
> "**Any statement about cell E0's central tendency must carry this caveat.**
> The excluded runs' data is retained in full and is the stronger evidence for
> E0's registered failure, not weaker."
>
> **What §9.9 explicitly does NOT decide, and what does:** it records that
> whether `exclusions.md:51-52` bites — and cell E0 therefore needs
> re-collecting under a widened criterion — "is **NOT this task's call**". That
> question is ruled on in **8.3** of this document: **cell E0 is not
> re-collected**, on four stated grounds. Read 8.3 with this quote; neither is
> complete alone.

The size of the effect, measured — reproduce with:

```bash
python3 - <<'PY'
import csv, pathlib
for run in sorted(pathlib.Path("benchmarks/results/E0").glob("run-*")):
    p = run / "observer.csv"
    if not p.is_file():
        print(run.name, "NO observer.csv")
        continue
    n = sum(1 for r in csv.DictReader(open(p))
            if "pose_estimator/pose_with_covariance" in r["topic"])
    print(run.name, "NDT rows =", n)
PY
```

| run       | NDT poses recorded | state                                                                   |
| --------- | ------------------ | ----------------------------------------------------------------------- |
| `run-001` | 10                 | valid, **bring-up class — NOT pooled**, see 6.1                         |
| `run-002` | 8                  | valid, pooled                                                           |
| `run-003` | 17                 | valid, pooled — the only E0 run ever M5-scored (`ndt_rate_ratio` 0.038) |
| `run-004` | 8                  | valid, pooled                                                           |
| `run-005` | **1**              | **excluded `harness:e7ba92a`** — the §9.9 mechanism                     |
| `run-006` | **1**              | **excluded `harness:e7ba92a`** — the §9.9 mechanism                     |
| `run-007` | 6                  | valid, pooled                                                           |
| `run-008` | 6                  | valid, pooled                                                           |
| `run-009` | 0                  | excluded `gate:arm-failed`                                              |
| `run-010` | —                  | excluded `crash:cell-launch` (no observer.csv)                          |

The five pooled runs carry **8 / 17 / 8 / 6 / 6** NDT poses against the two
dropped runs' **1 / 1**. The pool is biased toward E0's better runs by a
mechanism correlated with E0's own registered failure — a structurally starved
NDT, which is exactly what cell E0 exists to expose. Every central-tendency
statement about cell E0 in this document or downstream of it is **optimistically
biased**, and the bias cannot be estimated from the surviving pool.

### 6.1 The pooling decision: `E0/run-001` is NOT pooled as a sixth run

PROVENANCE §9.5 flags this as an open choice and requires the wrap to state
which it took. **This document does not pool `E0/run-001`.** Cell E0's published
static pool is **five** runs. Four reasons, in decreasing weight:

1. **It was collected under a different registration.** `run-001` carries
   `harness_git_sha: 1f43914`; the five pooled runs carry `e7ba92a`, the §9.2
   grounding commit that first registered E0's `lidar_expected_hz`,
   `ndt_expected_hz`, `ladder_branch` and `abs_pose_gate_m`. When `run-001` ran,
   those were all `null` and the M5 gate could not score the cell at all. Pooling
   it would mix two registration states inside one row.
2. **Pooling it would make the §9.9 bias WORSE, not better — measured, not
   argued.** `run-001` carries **10** NDT poses, more than four of the five
   pooled runs. Adding it pushes an already-upward-biased pool further up.
   Excluding it is the conservative direction with respect to E0's own
   registered failure.
3. **It is bring-up class** (`duel_admissible: false`), filed by the Task 4
   smoke pass whose stated purpose was to prove a path, not to measure it.
4. **The campaign already resolved this exact shape the same way.** PROVENANCE
   §8.5: "Task 4's `C/run-002` remains a valid, unexcluded closed-loop run in
   the same pool but is bring-up class and is not counted toward this task's
   five."

`E0/run-001`'s own measurements stay in section 3's table and are reported
**beside** the pool, never inside it.

### 6.2 Cell E's closed loop was not collected, and why that is a spec outcome

Cell E's `closed-loop` arm produces **no P3 data**. `E/run-009` reached
`mode=2 autonomous=True is_autoware_control_enabled=True` and then failed on the
gated control command (`control_cmd_hz~0.00 n=0`), excluded `gate:arm-failed`.
Its failing link is **the route** — `behavior_path_planner: waiting for route`
persists 63.98 s past `set_waypoint_route`, and `waiting for map` never appears
at all. That is a _different_ failing link from cell B's, so one diagnosis does
not unblock both.

Cell E's **static-only downgrade was pre-registered**, precisely so this case
would not need a decision taken after seeing a failure. It fired.

**Consequence for the matrix, stated so it cannot be misread: the
python-bridge approach's closed-loop evidence is STRUCTURAL, not measured.**
Nothing in this record may be read as the bridge having been measured
closed-loop and found wanting. It was never measured closed-loop at all,
because it could not be armed.

## 7. Confounds

`benchmarks/README.md`'s `## Known confounds` section (`:894` onward) is the
pre-registered source; this table indexes it and adds the P3-era rows. Nothing
here is a correction to a measurement — these are differences between cells that
bear on how their results are read together.

### 7.1 The P3-era confound rows

| id   | confound                                                                      | what it is                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | cells                   | where registered                                                                      |
| ---- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------- |
| P3-1 | **Phase 0 outcome: branch (c)**                                               | Double publication on `/sensing/lidar/concatenated/pointcloud` is **real and differential** — cell B has 2 emitters, cell A has 1 — but it is **not the cause** of cell B's depressed NDT rate: branch (c) was selected by elimination and prescribes no harness change. **The cause is UNEXPLAINED.** Cell B's M5 rate gate keeps failing on **eight** of the ten duel-pool runs (0.2569–0.8505; `run-013` passes at 0.9892, `run-019` is unscoreable — see 5.2 for the full split) and the gate was never tuned.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | B (effect), A (control) | PROVENANCE §6, §6.7, §6.8; evidence `p3-phase0/`                                      |
| P3-2 | **Observer instrument, and the G1 ladder rung**                               | Every cell in the campaign is observed by the **same** `bench-observer:universe-devel` image (local digest `sha256:b78ec01a…a5385`), with **SHM off**, and a per-cell topic list (`config/observer_topics/<cell>.yaml`). The observer RMW **follows the cell** (`rmw_cyclonedds_cpp` on A/C/E/E0/CAL-rmw, `rmw_fastrtps_cpp` on B), so the instrument is shared-mode in A − B on everything except the transport it is measuring. Separately, the Town10 UE5 cells localize against the **G1 ladder's rung 2** bundle (`town10_pcd_regen`): rung 1's rigid refit measured max NDT error 0.570 m against the 0.5 m absolute gate, rung 2 measures **0.089 m**, and rung 3 was never reached. Rung 2 is **not reproducible from its pin alone** — its input is a live 100 s drive — and its **coverage is bounded by where the ego drove** (~292 m of a 438.9 m route), so it is dense along that corridor and thins beyond it.                                                                                                                                                                                                                                                                                                                                 | all                     | `benchmarks/pins.yaml` `bench_observer_images` / `town10_pcd_regen`; README G1 ladder |
| P3-3 | **pcd variant per cell**                                                      | Read off each manifest's `placement.map_bundle_pin`. **A, B: `town10_pcd_regen`** (the rung-2 rebuild). **C: `nishishinjuku_bundle.pcd_sha256`** (sourced, AWSIM v2.0.0 `Shinjuku-Map.zip`). **E, E0: `autoware_contents.town10_pcd_sha256`** — the **deliberately unshifted** bundle, verified live at `7ed7890e…ee95b`, which carries the +0.475 m cross-track offset the ladder exists to correct. **CAL-rmw: `skipped:no-map:-`.** This is why E/E0 are registered on the **relative** ladder branch with a null `abs_pose_gate_m`: gating them at 0.5 m against that bundle would fail them by map registration under a heading a reader would attribute to the bridge. Four of cell E's six scored runs have `pose_err_max_m` > 0.5 m and would have failed exactly that way.                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | all                     | README confound C4 (`:955`); PROVENANCE §9.2                                          |
| P3-4 | **Container placement and run mode**                                          | `placement.run_mode` and `placement.container_image` differ by family and are recorded per run. **A, B, C: `editor-game`** — the CARLA fork under the Unreal editor, engine BuildId `4210e602-78ec-46e1-8f2f-03fadbe036a3`, with A/C on `carla-autoware-integration` (`carla_version: 0.10-fork`, Autoware `universe-devel` by tag) and B on `carla-autoware-native` (`0.10-tier4`, Autoware pinned by digest `sha256:5c22369a…e8ee`, plus a full `tier4_*` build-identity block). **E, E0: `shipping-headless`**, CARLA **0.9.15**, images `bridge-bench-patched:latest` / `bridge-bench:latest` — a different simulator version and a different container entirely. **CAL-rmw: `container-only`**, no simulator at all. Cross-family comparisons cross a CARLA major version; the A-vs-B duel does not.                                                                                                                                                                                                                                                                                                                                                                                                                                                     | all                     | each run's `manifest.json`; `benchmarks/pins.yaml`                                    |
| P3-5 | **Patch inventory**                                                           | `patches_git_sha` is `ccff4f9` on **every non-excluded run in the campaign**, and on every run any P3 conclusion rests on. It is NOT uniform over the whole tree: 20 of the 102 filed manifests carry one of five earlier shas (`B/run-001`…`run-004` `8aeed44`, `B/run-005`…`run-012` `31aac85`, `E/run-001`…`run-004` `ec998b4`, `E/run-005`…`run-007` `b81200d`, `E/run-008` `4557e5c`) and **every one of those 20 is `excluded: true`** — the stale pre-P3 runs retained as history. Reproduce with the census in 9.1. Applied patch sets: **`patches/extension/`** — none, README only (the extension carries no patches). **`patches/tier4-native/`** — `0001-toolchain-libm.patch`, `0002-glibc-compat.patch`, `0003-autoware-demo-params.patch`: two build fixes this host needs plus a params change, all on cell B/D's path. **`patches/python-bridge/`** — `0001-lidar-is-dense.patch` and `0002-sensor-config-harmonized.patch`, which is what separates cell **E** (patched, `frequency_hz: 20`) from cell **E0** (as-shipped, `frequency_hz: 11`). `cells/python-bridge.sh` refuses to run either cell against the other's image, in both directions. **So the E-vs-E0 difference IS the patch inventory** — that is the pair's whole purpose. | B/D, E/E0               | `benchmarks/patches/**`; `benchmarks/pins.yaml` `patches_sha256`; PROVENANCE §9.2     |
| P3-6 | **`control_mode: MANUAL` — a per-approach interop gap, recorded not patched** | The two duel approaches differ on exactly the flag: while parked, cell **A** publishes `/vehicle/status/control_mode` = **`4` (MANUAL)** — the extension reporting the ego's live state — and cell **B** publishes **`1` (AUTONOMOUS)** **unconditionally**, from the tier4 fork's `ROS2.cpp:1117` `SetControlMode(ControlMode::AUTONOMOUS)`, with the fork's own `TODO: Add logic to use the input of control mode` beside it. One under-reports its mode; the other reports AUTONOMOUS whether or not it is. **Neither is patched**, deliberately: whether an approach reports its own control mode correctly _is part of the interop completeness being compared_. The `control_mode = MANUAL` → arm-refusal link is **NOT established** — README's own follow-up records that the transition was refused in exactly that state and that `control_mode_request` is the alternative candidate. No python-bridge reading is registered.                                                                                                                                                                                                                                                                                                                      | A, B                    | README `:2159-2413`, table at `:2324`                                                 |

### 7.2 The pre-registered confounds that still apply

Indexed, not restated. Read them at the cited line in `benchmarks/README.md`.

| confound                                                                                                                                                                        | cells               | line             |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- | ---------------- |
| Route difficulty: Town10 vs Nishi-Shinjuku                                                                                                                                      | A/B vs C/D          | `:902`           |
| Map provenance: self-built Town10 pcd vs sourced Nishi pcd (C4) — keeps only its A/B-vs-C comparison now that `D` is struck                                                     | A/A-hf vs C         | `:955`           |
| Perception load: clear-road stand-in vs real CUDA perception                                                                                                                    | A/B/C/D vs E family | `:1025`          |
| Sensing graph: `carla_sensor_kit` vs `awsim_labs_sensor_kit`                                                                                                                    | E family vs A/B/C/D | `:1059`          |
| Ground truth is the CARLA actor origin; localization is `base_link` — and the GT anchor is **per-approach**, not campaign-wide (`extension` +0.000 m, `python-bridge` −1.425 m) | all                 | `:1097`, `:1132` |
| Physics substepping: B disables it at 20 Hz, A leaves CARLA's default on                                                                                                        | A vs B              | `:1249`          |
| CAL-seam: a per-publish allocation the fork side alone carries — **and `C1(a)` seam overhead is now UNMEASURED**, the cell having been struck                                   | —                   | `:1281`, `:3330` |
| DDS middleware and transport: the B family runs a different one (`rmw_fastrtps_cpp` + `observer/config/udp_only.xml`, SHM off)                                                  | B vs all            | `:1323`          |
| Localization initialization: the stop check blocks every path on cell B                                                                                                         | B                   | `:1400`          |
| Byte-layout asymmetry: cell A ships **2.118×** the bytes for the same point count, biasing the two latency metrics **against** cell A                                           | A vs B              | `:3986`          |

### 7.3 One instrument artefact that appears in the verdict output itself

The M2 reconciliation table in section 4.1 reports a **non-zero
`publisher_drop_rate` on the static arm of both cells for a publisher that
dropped nothing** — cell A median 0.021 / max 0.385, cell B median 0.020 / max
0.022. **This is a harness property, not an approach property**, disclosed
rather than fixed (owner ruling 2026-07-31). The mechanism: the static branch of
`_resolve_window` sets the window's upper bound to the run's **last `/clock`
sample** (`duel_verdict.py:324-326`), while `teardown.sh` stops the GT collector
— which writes `publisher_counts.json` — at `:209`, _before_ it SIGINTs the
observer container, which writes `clock.csv`, at `:222`. The publisher series
therefore ends first and the in-window deficit is exactly the scans in the gap.
Its four bounding properties: **symmetric across A and B** (same `teardown.sh`,
same window branch, so it barely moves the A − B delta); **not a duel-margin
metric**; the **closed-loop arm is immune** (it takes the `spatial_window`
branch, which closes ~80 s before the run ends); and the correct fix is a
formula change inside the **frozen** `benchmarks/analysis/` tree, applied to a
pre-registered metric mid-campaign. Full derivation: PROVENANCE §1.

## 8. Deviations log

Every deviation from the plan as written, with the ruling that produced it.
Nothing in this list was decided by this task except where it says so.

### 8.1 Branches not taken, and the tasks that did not run

| item                                                                                                    | outcome                      | why                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Phase 0 branch (a)** — relay removal                                                                  | **not selected**             | Requires P4 NDT ≥ 9.0 Hz post-kill. Best post-kill reading on any of four runs ≈ 0.07 Hz.                                                                                                                                                           |
| **Phase 0 branch (b)** — concat suppression                                                             | **not selected**             | Trigger is "P3 fails: empty/malformed clouds". P3 passed: well-formed, non-empty `base_link` clouds at 7.612 Hz.                                                                                                                                    |
| **Phase 0 branch (c)**                                                                                  | **SELECTED**, by elimination | See 5.2. Prescribes **no** harness change. The root cause of cell B's depressed NDT rate is **UNEXPLAINED**.                                                                                                                                        |
| **Task 2** — the branch-(a)/(b) fix                                                                     | **SKIPPED**                  | Conditional on branch (a)/(b). Branch (c) fired, and its registered fix mechanism is **NONE**.                                                                                                                                                      |
| **Task 3** — criterion-3 reclassification of B `run-013`…`run-022` + `--revoke-duel` on A's pair-halves | **SKIPPED**                  | Same condition. The A static pair-halves therefore keep `duel_admissible: true`, and B's ten stay filed and unexcluded. Recorded explicitly so no later task applies the spec's "Consequence of (a)/(b) for the A pair-halves" paragraph by reflex. |
| **Task 5** — 10-fresh-pair static recollection                                                          | **SKIPPED**                  | Same condition. The pools stand exactly as filed.                                                                                                                                                                                                   |
| **M5 gate threshold**                                                                                   | **never touched**            | 0.9 throughout. No threshold moved, on any cell, at any point in P3.                                                                                                                                                                                |

### 8.2 The exclusion vocabulary has no category for "ran, was not excludable, could not be scored"

**Three runs are in this state: `C/run-009`, `B/run-025`, `B/run-026`.** Each
ran to completion, matches **none** of `exclusions.md`'s ten criteria, and could
not be scored by the M5 gate, so each is filed **unexcluded with no
`quality.json`**.

`exclusions.md` has no criterion that fits, and deliberately so — there is no
quality-based criterion at all, by design. The criteria **may not be edited
after the first P3 measurement run** (`exclusions.md:52-53`), so the vocabulary
cannot be widened now either.

**Owner ruling: record only, freeze held.** No retroactive reclassification, no
criterion added or edited, no run's manifest touched. Any amendment is left to a
future campaign, which is where a pre-registration change belongs. The three
runs are named here so a later reader does not have to re-derive the gap.

`B/run-025` and `B/run-026` are the Phase 0 diagnostic runs with a deliberate
mid-run relay kill; `B/run-029`, a clean un-intervened cell B run, filed a
`quality.json` normally, which supports reading their absence as an artifact of
the intervention rather than baseline cell B behaviour. `C/run-009` had **no**
diagnostic intervention in it, which is why it is the load-bearing instance.

### 8.3 Cell E0 and criterion 3: the substance does not fit, and E0 is NOT re-collected

`E0/run-005` and `run-006` are filed `harness:e7ba92a`. The reason **string** is
verbatim from criterion 3. The criterion's **substance** does not fit: criterion
3 reads "Harness defect discovered **and fixed** (the run was measured with a
broken observer/injector)", and on these two runs **nothing was broken** (the
observer recorded its full topic set; `gt.csv` holds 1148 and 1167 rows; the sim
clock never stalled) and **nothing was fixed** (neither `report.py` nor
`cadence.py` was changed in response — and `analysis/**` is frozen, so
`inter_arrival_stats` could not have been).

**A strict reading of `exclusions.md:51-52`** — "any exclusion not matching 1-10
invalidates the campaign for that cell and requires a fresh cell" — would
therefore require re-collecting cell E0.

**CONTROLLER RULING: do NOT re-collect cell E0.** Four grounds:

1. **A fresh cell reproduces the identical filing.** The `harness:<commit>` ⇄
   criterion-3 mapping is pre-registered **in committed code**, at
   `benchmarks/run.sh:1028-1029`: "`crash:` while the world is being built
   (criterion 1), `harness:<commit>` once the data exists and only finalization
   can still fail (criterion 3)." That mapping predates cell E0's data and was
   not touched by any task that filed it — checkable: across `9c0f8dd..a52bb6b`,
   outside `benchmarks/results/`, `run.sh`, `report.py` and all of `analysis/`
   are **byte-identical**. And E0's NDT starvation is its **registered expected
   outcome**, written down in advance (PROVENANCE §9.3: "Cell E0 is expected to
   be UNSCOREABLE, and that is its registered result"). A fresh cell would starve
   the same way, fail the same step-15 smoke, and be filed under the same
   catch-all. Re-collection buys a second identical filing, not a cleaner one.
2. **The criteria may not be edited after the first P3 run**, so widening the
   vocabulary to fit is not available either. Both doors are closed by the same
   pre-registration, which is what it is for.
3. **Owner ruling: record-only, freeze held** for this whole class — the same
   ruling 8.2 applies to the three unscoreable runs.
4. **Cell E0 is a bridge cell outside the duel.** It is context. No verdict,
   delta or margin decision rests on it, so the cost of the mismatch is bounded
   to a row that must be read with section 6's caveat attached — which is
   exactly how this document presents it.

The label was applied **mechanically by committed code**, to a rule written
before cell E0's data existed, and not chosen after seeing which runs it would
drop. The substance mismatch is a property of the pre-registration, not an
exercise of discretion. It is named here rather than softened.

### 8.4 Measurement-condition deviations, disclosed

| #   | deviation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | status                                                                            |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| 1   | **`duel.sh` gained inter-run pacing mid-campaign** (120 s floor + a bounded, load-triggered top-up). Inter-run host-idle time is a measurement condition, so this is a **dated amendment**, not a transparent bugfix. `MAX_LOADAVG` and criterion 6 were **not** changed — relaxing the gate would tune a validity condition to fit the measurement. Pair 1 (`A/run-003`, `B/run-013`) predates it; its ~31.5 s gap is **reconstructed** from committed byte content, not recorded. Recorded behaviour over the 17 paced gaps: top-up fired on **5 of 17** (5/10/15/15/20 s), the 300 s ceiling was **never** reached, total pacing wait 2105 s.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | disclosed, PROVENANCE §3, §4.2                                                    |
| 2   | **The duel's first-slot alternation realised 6/4, not 5/5.** `duel.sh` alternates which cell takes a pair's first slot so neither always pays the cold-cache cost. Because the duel was filed as `--pairs 10` (aborted after pair 1) plus `--pairs 9`, and every invocation starts its own pair 1 with cell A, cell A went first in **6** of the ten static pairs. A one-slot imbalance introduced by an abort, not by a design change; not correctable without re-running filed pairs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | disclosed, PROVENANCE §4.3                                                        |
| 3   | **A live teardown defect left the Autoware stack up on 5 of the 10 cell-B static runs.** A racy sidecar write (reading `/proc/$pid/cmdline` on the line after `nohup ros2 launch …`, racing `ros2`'s own exec) makes `stop_launch_tree.sh`'s pid-reuse guard misfire. **It did NOT invalidate any run**: teardown runs after the scoring window closes, `teardown.sh`'s `docker rm -f` killed all 56 processes immediately after, every subsequent preflight passed, and no run was refused or excluded. What was lost is the graceful SIGINT ladder on those five. **Not fixed** — changing how a run is launched mid-measurement changes the measured configuration.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | disclosed, PROVENANCE §5                                                          |
| 4   | **`harness_git_sha` is not uniform, within cells or across them.** Even the duel pool spans two shas: pair 1 on `177256e`, pairs 2–10 on `5a28339` (the pacing amendment). Cell C spans `1f43914` and `4f7aa68`. **Cell E/E0's collection is uniform on `e7ba92a` only for the runs that count** — all 11 valid static runs and both cells' Task-8 exclusions carry it, while `E0/run-001` is on `1f43914` and `E/run-001`…`run-009` carry five other shas; every one of those is excluded or bring-up class. Verified rather than assumed — see 9.3 for the blast radius, which is the fact a P4 comparison actually needs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | disclosed, PROVENANCE §8.6; 9.3 below                                             |
| 5   | **Two 0-byte `gt.log` classes**, both with populated `gt.csv`. The python-bridge family's is root-caused (python block-buffering over a non-TTY `docker exec`, whose client — not the in-container interpreter — receives run.sh's SIGTERM) and **fixed** by `-e PYTHONUNBUFFERED=1`, so E-family runs from `e7ba92a` forward file the applied GT anchor. `C/run-005`'s single 0-byte `gt.log` is a **different, unexplained one-off**: its `gt.csv` is complete at 1383 rows, `publisher_counts.json` is well-formed, and the run scored `gate_pass: true`. No criterion 1–10 applies to either — in particular not criterion 9, which covers a recorder that exits "before it has recorded anything usable".                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | disclosed, PROVENANCE §7.5, §8.6, §9.4                                            |
| 6   | **Per-run preflight loadavg spread inside chained cell-C batches** (1.47–5.38 across the eleven runs). `run.sh --runs N` has no inter-run pacing, unlike `duel.sh`. Every value is under `preflight.sh`'s registered gate of 8 **and** under `duel.sh`'s registered target of 6, so all were collected inside the campaign's own registered host-load conditions. Recorded rather than corrected: correcting it afterwards would mean choosing which runs to keep on a condition that is not a pre-registered exclusion.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | disclosed, PROVENANCE §8.4                                                        |
| 7   | **`benchmarks/config/observer_topics/B.yaml` does not carry `/map/vector_map`**, so **no filed run in this campaign can answer the latched-delivery question from data already on disk.** It needed the live probes of PROVENANCE §7.7–§7.11, which is why that finding rests on evidence under `benchmarks/evidence/` rather than on run artifacts.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | disclosed, PROVENANCE §7.1                                                        |
| 8   | **The load-sensitive test flake is REPRODUCIBLE ON DEMAND, and this task characterised it further.** `test_teardown.py::test_tier4_autoware_sh_aw_sidecar_settles_on_the_post_exec_cmdline` executes the real sidecar polling loop and reads a real short-lived process's `/proc/<pid>/cmdline`; under load the process is gone before the read and it fails `assert 'os.execv' in ''`. This task hit it **twice**, both times while the host was shedding a `pre-commit run --all-files` — once at 1-min loadavg **42.68**, once at 1-min **1.71** but 5-min **14.25**, which shows the **1-min average alone is not a sufficient quiet signal for this test**. Gated on 1-min < 1.0 **and** 5-min < 3.0 instead, with nothing else changed: `tests/benchmarks/test_teardown.py` **16 passed** in isolation, and the full suite **1075 passed, 1 skipped** — the baseline as it stood then. (The review wave since added 9 tests, so the current baseline is **1084 passed, 1 skipped**; the 1075 figure is retained here because it is what this observation was made against.) Not a regression and not silenced; the launcher's own comment already warns the poll cap is "a FLOOR, not a ceiling -- load stretches it further". | disclosed, PROVENANCE §7.10, §7.11; the 5-min-average characterisation added here |
| 9   | **`benchmarks/report.py` exits 1 over the full results root**, driven entirely by cell CAL-rmw, which has no simulator and therefore no `/clock`. Its registered renderer is `scripts/cal_report.py`. Not fixed, not suppressed — see section 3.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | disclosed here                                                                    |

### 8.5 One deferred annotation, closed by this task

PROVENANCE §6.6 recorded a **refuted premise left in place in a live launcher**,
with its in-file annotation "deliberately deferred to the P3 wrap task" on the
owner's ruling, because cell A was about to carry hours of live duel collection
and line-shifting that file risked live runs for no gain.

`scripts/e2e/launch_autoware.sh` asserted that the awsim_labs concatenate node
"HARD-REQUIRES >= 2 input topics … and never loads", and that "it stays silent
with a single publisher, so the relay is the sole publisher on the concatenated
topic — verified live after bring-up". **Phase 0 measured both claims false on
cell A**: `concatenate_data` _does_ load and _does_ advertise a publisher on
`/sensing/lidar/concatenated/pointcloud`, so the relay is **not** the sole
publisher; what the comment gets right in substance though not in mechanism is
that the node is indeed **silent** — it emits nothing (`RELAY_OUT`/`RELAY_IN`
ratio 0.995, zero duplicate stamps) — but silent _while holding a publisher_,
not by failing to load.

All live collection is complete, so the annotation is landed here at
`scripts/e2e/launch_autoware.sh:48-71`, as a **comment-only** change with no
executable effect. The original claim at `:44-47` is kept exactly as written,
per the convention that a claim stays in the record with the diagnostic that
corrected it.

The insertion shifts that file's later line numbers by 24, which is the
citation-drift class PROVENANCE §6.6 named as a reason to defer. **Every in-repo
citation that shifts was corrected in the same commit and each was re-verified
against its new target** — all four are comment or docstring text, none is
executable:

| citing file                                  | citation                                         | before → after                           |
| -------------------------------------------- | ------------------------------------------------ | ---------------------------------------- |
| `benchmarks/scripts/teardown.sh:100`         | `compose_exec_script`                            | `:89-94` → `:113-118`                    |
| `benchmarks/cells/tier4_autoware.sh:438`     | the pid-file write plus its Task-18b settle loop | `:185-233` → `:209-257`                  |
| `scripts/e2e/stop_launch_tree.sh:90`         | the same block                                   | `:185-233` → `:209-257`                  |
| `tests/e2e/test_stop_launch_tree.py:148,362` | the settle loop, and the read inside it          | `:219-233` → `:243-257`; `:221` → `:245` |

`benchmarks/evidence/p3-phase0/probe-transcripts.md`'s `:46` and PROVENANCE
§6.6's own `:44-47` sit **above** the insertion and are unaffected. The
cell-B-side counterpart comment in `benchmarks/cells/tier4_autoware.sh` ("THAT
PREMISE IS REFUTED") already carries its own refutation in place and its **text
is unchanged** — that file's only edit in this commit is the citation row above.

### 8.6 The two standing owner questions, answered

Both were already ruled on and are recorded here rather than posed:

- **PR #29 stays in DRAFT.** The branch is pushed; the PR is not flipped to
  ready-for-review.
- **P4 is DEFERRED to a later session**, and it **will** be run. This document
  therefore hands off to P4 rather than closing the campaign — see section 9.

## 9. Handoff to P4

**P4 will be run, in a later session.** Everything **P3 owes P4** is in this document
and in `benchmarks/results/PROVENANCE.md` §10. Neither depends on any
out-of-repo workspace: the plan's SDD scratch directory is git-ignored and is
deleted when the plan finishes, so nothing **P3 owes P4** lives only there.

**One thing is NOT here and cannot be: P4's own scope.** It is registered
nowhere in this repository, and this document does not invent it — see 9.4,
which states the gap plainly rather than leaving a promise the repo cannot
keep.

### 9.1 The environment identity P4 must match — and it is verifiable

Every filed run records the identity of what produced it, so P4 does not have to
take the environment on trust. The keys, all in `manifest.json`:

| key                            | what it pins                      | P3 value on the duel pool                                                                                                     |
| ------------------------------ | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `carla_version`                | which fork/build of the simulator | `0.10-fork` (A/C), `0.10-tier4` (B), `0.9.15` (E/E0)                                                                          |
| `autoware_image`               | the Autoware container            | `ghcr.io/autowarefoundation/autoware:universe-devel` (A/C), the same by **digest** `sha256:5c22369a…e8ee` (B)                 |
| `patches_git_sha`              | the applied patch inventory       | `ccff4f9` on every non-excluded run; 20 excluded stale runs carry five earlier shas (see 7.1, row P3-5, and the census below) |
| `harness_git_sha`              | the measurement code              | see 9.3 — **it moved during P3**                                                                                              |
| `transport.dds_profile_sha256` | the DDS profile actually in force | `1eeef31e…f2865` (cyclone cells), `9886f744…65098` (cell B), `""` (E/E0, no profile)                                          |
| `placement.engine_build_id`    | the shared Unreal engine          | `4210e602-78ec-46e1-8f2f-03fadbe036a3`                                                                                        |

**P4 must re-verify all six at its start**, before collecting anything.
Cross-session drift in the fork build, the Autoware image, or the DDS profile
would make P4 **incomparable to P3** — and it would do so silently, because
every one of these can move without any run failing.

The census that prints all six for every filed run, and the source of the
per-key figures above:

```bash
python3 - <<'PY'
import collections, json, pathlib
seen = collections.defaultdict(list)
for m in sorted(pathlib.Path("benchmarks/results").glob("*/run-*/manifest.json")):
    d = json.loads(m.read_text())
    # Abbreviate, but NEVER by slicing: `sha[:7]` drops the "-dirty" suffix
    # `write_manifest.py:19-22` appends when the working tree differed from
    # HEAD, so a truncating census structurally cannot surface the one thing
    # about these two keys most worth surfacing.
    def short(sha):
        head, _, tail = sha.partition("-")
        return head[:7] + ("-" + tail if tail else "")

    key = (
        d["carla_version"], d["autoware_image"], short(d["patches_git_sha"]),
        short(d["harness_git_sha"]), d["transport"]["dds_profile_sha256"][:8],
        d["placement"].get("engine_build_id", "-"), d["excluded"],
    )
    seen[key].append(f"{m.parent.parent.name}/{m.parent.name}")
for key, runs in sorted(seen.items(), key=lambda kv: kv[1][0]):
    print(f"{len(runs):3d}  excluded={key[6]!s:5s} carla={key[0]:11s} patches={key[2]:14s} "
          f"harness={key[3]:14s} dds={key[4]:8s} buildid={key[5][:8]}  {runs[0]}..{runs[-1]}")
PY
```

#### PROVENANCE CAVEAT: 20 manifests carry `-dirty` shas, and 12 of them sit behind the frozen margin

**Disclosed, not repaired.** `benchmarks/scripts/write_manifest.py:19-22`
appends `-dirty` to `harness_git_sha` (and `patches_git_sha`) when the working
tree differed from HEAD, and says why the suffix exists: without it the field
**asserts** a tie-back — README's "any result can be tied back to the exact
analysis code that scored it" — "which a dirty tree makes false". Twenty of the
102 filed manifests carry it, on **both** keys:

| runs                        | n      | `excluded` | what they are                                                    |
| --------------------------- | ------ | ---------- | ---------------------------------------------------------------- |
| `CAL-rmw/run-004`…`run-015` | **12** | **false**  | the calibration cell the `one_hop_wall_ms` margin is frozen from |
| `B/run-024`…`run-027`       | 4      | false      | Phase 0 diagnostics, `duel_admissible: false`                    |
| `B/run-001`…`run-004`       | 4      | true       | stale pre-P3 runs, retained as history                           |

```bash
python3 - <<'PY'
import collections, json, pathlib
dirty = collections.defaultdict(list)
for m in sorted(pathlib.Path("benchmarks/results").glob("*/run-*/manifest.json")):
    d = json.loads(m.read_text())
    if "-dirty" in d["harness_git_sha"] or "-dirty" in d["patches_git_sha"]:
        dirty[(m.parent.parent.name, d["excluded"])].append(m.parent.name)
for (cell, excluded), runs in sorted(dirty.items()):
    print(f"{cell:8s} excluded={excluded!s:5s} n={len(runs):2d}  {runs[0]}..{runs[-1]}")
PY
```

**What this touches and what it does not, stated precisely because the
distinction is the whole point.**

- **The verdict's INPUTS are clean.** Both duel pools — `A/run-003`…`run-012`
  and `B/run-013`…`run-022` — are clean on **both** keys, verified run by run.
  No run the A-vs-B verdict is computed from carries a dirty sha.
- **What is not fully pinned is the code state behind the MARGIN the verdict is
  compared against.** 12 of the 15 CAL-rmw runs from which
  `benchmarks/config/margins.yaml`'s `one_hop_wall_ms` margin was frozen carry
  dirty shas, so those runs cannot be tied back to an exact commit. The
  measurement stands as filed; its code provenance does not.
- **Bounded by the margin's own arithmetic.** That derivation put 2 × abs(Δ) at
  **0.83 ms** against a pre-registered **floor of 2.0**, and the floor is what
  binds — the frozen value would be 2.0 for any measured delta up to 1.0 ms. The
  dirty provenance would have to move the calibration by more than a factor of
  two before it could move the margin at all. That bounds the exposure; it does
  not remove it.

**NOT REPAIRED, deliberately, and the reasoning is the campaign's own.**
`margins.yaml` is **frozen** and its own header forbids re-derivation once
collection has started, so re-collecting CAL-rmw could not be allowed to change
the margin — which makes re-collection the same self-defeating remedy as the
cell E0 criterion-3 case in 8.3: it would cost live runs and could not alter the
artifact it was run to justify. Nothing under `benchmarks/results/` was touched
and `margins.yaml` was not opened. **This is an item P4 should be aware of**: a
margin with fully pinned provenance means a fresh calibration under a clean
tree, registered as such in advance — not a retroactive repair of this one.

**Engine BuildId `4210e602-78ec-46e1-8f2f-03fadbe036a3` stays pinned, and
RELINK REMAINS FORBIDDEN.** `benchmarks/pins.yaml:247-259`: a `carla-unreal-editor` rebuild
in **any** tree relinks the shared engine and invalidates every tree that shares
it; "no further engine relink is permitted from here on (D8)". `exclusions.md`
criterion 8 excludes any run whose BuildId is found to mismatch after start.

> **SUPERSEDED 2026-08-03 — the statement above is left standing as the P3-era
> fact it was.** The owner registered a D8 lift for exactly one relink round (P4
> spec decision 6, CAL-seam revival). It was executed once: the engine BuildId
> moved to `bc08ce19-f19c-46fe-808f-dbb2b0ddf41a`, all three trees re-converged
> on it, `benchmarks/pins.yaml` was re-pinned, and **D8 was re-instated
> immediately afterwards** — no further engine relink is permitted for the
> remainder of the campaign. `exclusions.md` criterion 8 is unaffected; it still
> excludes any run whose BuildId mismatches the pin, which is now the new value.
> Full record: `benchmarks/results/PROVENANCE.md` §11.

### 9.2 Cell B's closed-loop blocker will affect any P4 arm that tries to arm B

This is not a P3-only condition. Under cell B's registered transport
(`rmw_fastrtps_cpp` + `benchmarks/observer/config/udp_only.xml`, SHM off), the
latched-topic delivery defect of section 5.1 blocks the arm nondeterministically
and per-topic. **Cell B is 0-for-15 on the closed-loop arm under that
transport** — 7 of the 15 reached the arm and failed it, and 8 never got that
far (see 5.1's tally and its reproduction command). A P4 design that assumes
cell B can be armed will lose the runs it budgets for that. **Attribute the
loss carefully**: of P3's 15, the 7 `gate:arm-failed` runs are the ones the
latched-delivery defect accounts for; the other 8 are crash-class
(`crash:cell-launch` ×7, `crash:collect_gt` ×1) and were lost to bring-up —
**with one carve-out: `B/run-031` came up, ran the delivery step, and was
filed criterion 1 only because that step was fatal at the time. It belongs to
this defect's evidence.** See 5.1.

The per-topic re-publish workaround (`injector/republish_vector_map.py`, made
advisory in `2dbec06`) fixes the **map** and **does not scale**: the route is
published _after_ the planner starts by construction, so it can never use the
late-joiner path the map fix relies on, and `operation_mode` would need a third.
Its value on a bring-up that genuinely needed it is **UNTESTED**.

### 9.3 `harness_git_sha` moved during P3 — what it means for P4↔P3 comparisons

Three harness changes landed after the duel pool was collected:

1. **`1f43914`** — the python-bridge `set -u` fix: `cells/python-bridge.sh`'s
   base_link anchor guard was 65 lines above the `IMAGE=` resolution it reads, so
   every python-bridge cell aborted `plan` with `IMAGE: unbound variable`. Moved
   **verbatim** below the resolution; nothing about what it checks changed.
2. **`a3ba158` → `2dbec06`** — the `/map/vector_map` re-publish step, added to
   `cells/tier4_autoware.sh` **on the closed-loop arm only**, then made
   **advisory** (it records and continues; it no longer aborts).
   `transport.dds_profile_sha256` is byte-identical, so cell B's filed runs stay
   transport-comparable.
3. **`0c869ef`** — the registered opt-in for a deliberate tier4 transport
   deviation (`BENCH_TIER4_TRANSPORT_DEVIATION`), which is what let `B/run-033`
   run at all.

**Comparisons _within_ P4 are unaffected** — P4 will collect on one harness sha
per cell and record it. **P4↔P3 comparisons must account for the move.**

**The blast radius, verified rather than asserted.** Across
`5a28339..269b931` — from the commit that filed the duel pool's pairs 2–10 to
this document's parent — outside `benchmarks/results/` and
`benchmarks/evidence/`, the changed files are:

```text
benchmarks/cells/python-bridge.sh
benchmarks/cells/tier4_autoware.sh
benchmarks/config/cells.yaml
benchmarks/injector/republish_vector_map.py
benchmarks/scripts/teardown.sh
scripts/e2e/launch_autoware.sh
scripts/e2e/stop_launch_tree.sh
tests/benchmarks/test_cell_info.py
tests/benchmarks/test_sweep_verdict.py
tests/benchmarks/test_teardown.py
tests/benchmarks/test_vector_map_gate.py
tests/benchmarks/test_write_quality.py
tests/e2e/test_stop_launch_tree.py
```

Reproduce with:

```bash
git diff --name-only 5a28339 269b931 -- . \
  ':(exclude)benchmarks/results' ':(exclude)benchmarks/evidence'
```

**FOUR of those are on cells A and C's path, and two of the four are
EXECUTABLE changes.** Cells A and C are `approach: extension`, and
`benchmarks/cells/extension.sh:192` launches `scripts/e2e/run_e2e.sh`, which
runs `scripts/e2e/launch_autoware.sh`, which in turn drives
`scripts/e2e/stop_launch_tree.sh` on its `--stop` path (`launch_autoware.sh:155`).
Both of those `scripts/e2e/` files changed **executably** in this range:

| file on A/C's path                | change                                                                                                  | comment-stripped md5, `5a28339` → `269b931` |
| --------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| `scripts/e2e/launch_autoware.sh`  | **executable** — +87/−2; the Task-18b fork/exec settle loop, which polls for up to ~5 s during bring-up | `07436b102c07` → `4797c56ecd45`             |
| `scripts/e2e/stop_launch_tree.sh` | **executable** — +54/−6; the teardown-summary and pid-reuse-guard work                                  | `f4912c09ee75` → `917ec5a3d1ba`             |
| `benchmarks/scripts/teardown.sh`  | comment only — a one-line citation fix (`:311-316` → `:361`)                                            | unchanged                                   |
| `benchmarks/config/cells.yaml`    | registry — semantic change confined to cells **E** and **E0**                                           | A/C parse-identical                         |

Reproduce the hashes with:

```bash
for f in scripts/e2e/launch_autoware.sh scripts/e2e/stop_launch_tree.sh \
         benchmarks/cells/extension.sh benchmarks/run.sh scripts/e2e/run_e2e.sh; do
  for r in 5a28339 269b931; do
    printf '%-34s %s %s\n' "$f" "$r" \
      "$(git show "$r:$f" | sed 's/[[:space:]]*#.*$//' | grep -v '^[[:space:]]*$' | md5sum | cut -c1-12)"
  done
done
```

**CONSEQUENCE, AND IT IS P4-FACING: cell A and cell C DID NOT RUN THE SAME
LAUNCHER.** The `scripts/e2e/` changes landed in six commits on the evening of
2026-07-31 (`3cf06ef`, `6d06608`, `2742dbf`, `161cf75`, `cdb22aa`, `7056a6e`),
which sits **between** the two cells' collections:

| runs                                                 | `harness_git_sha`     | relative to the `scripts/e2e/` change |
| ---------------------------------------------------- | --------------------- | ------------------------------------- |
| **cell A duel pool** `run-003` / `run-004`…`run-012` | `177256e` / `5a28339` | **before** — the whole pool           |
| cell A Phase-0 diagnostics `run-013`, `run-014`      | `d7460ab` / `f0f8b4b` | after                                 |
| **cell C** `run-001`…`run-002` / `run-003`…`run-014` | `1f43914` / `4f7aa68` | **after** — every run                 |

**The A-vs-B static verdict is unaffected**: cell A's pool is entirely
pre-change and internally consistent on this axis, and cell B is
`approach: tier4-native`, which does not reach `scripts/e2e/` at all. **But any
A-vs-C comparison must account for it** — the two cells ran different bring-up
and teardown code, and this document draws no A-vs-C statistic for that reason
among others (cell C is confirmatory and `duel_admissible: false` throughout).

An earlier revision of this section said "cell A's and cell C's measurement
paths byte-identical" and counted two files rather than four. That was **false**
and is corrected here rather than quietly dropped; it is exactly the class of
claim this campaign keeps catching, and it was labelled "verified rather than
asserted", which made it worse.

Verify the `cells.yaml` half with:

```bash
python3 - <<'PY'
import subprocess, yaml, json
def load(rev):
    txt = subprocess.run(["git", "show", f"{rev}:benchmarks/config/cells.yaml"],
                         capture_output=True, text=True, check=True).stdout
    return {c["id"]: c for c in yaml.safe_load(txt)["cells"]}
old, new = load("5a28339"), load("269b931")
for cid in sorted(set(old) | set(new)):
    same = json.dumps(old.get(cid), sort_keys=True) == json.dumps(new.get(cid), sort_keys=True)
    print(f"{cid:9s} identical={same}")
PY
```

Output: `identical=True` for A, A-hf, B, B-hf, B45, C, CAL-rmw, CAL-seam, D
and E-opt — all ten other registered cells; `identical=False` for **E** and
**E0** only.

**So the reviewed blast radius is: cells B and D** (the `tier4_autoware.sh`
vector-map work), **cells E/E0** (the bridge grounding and the `set -u` fix),
**and the shared `scripts/e2e/` bring-up + teardown code that cells A and C
run** — which moved between their two collections, as above.

What IS byte-identical across the whole span, and this list is enumerated
rather than generalised because the generalisation is what went wrong above —
each verified by `git show <rev>:<path> | md5sum` at both endpoints:
`benchmarks/cells/extension.sh`, `benchmarks/run.sh`,
`scripts/e2e/run_e2e.sh`, `benchmarks/scripts/preflight.sh`,
`benchmarks/scripts/write_quality.py`, `benchmarks/report.py`,
`benchmarks/scripts/duel_verdict.py`, `benchmarks/config/exclusions.md`,
`benchmarks/config/margins.yaml`, and every file under
`benchmarks/analysis/`. **No analysis or scoring CODE moved** — which is the
part the verdict actually rests on.

One qualification, because the sentence above would otherwise overreach the way
this section already had to be corrected once: `benchmarks/config/cells.yaml`
is a **scoring input**, not just a registry — `duel_verdict.py` resolves every
per-cell binding through `cell_info.metrics_for` against it — and it did move,
+206/−19, inside this same span. What makes that harmless here is proved 24
lines above rather than asserted: **every cell except E and E0 is
parsed-identical across the range**, so cells A, B, C and CAL-rmw were scored
against byte-identical bindings. The claim is "no scoring code moved, and no
binding the verdict reads moved", not "nothing under `benchmarks/config/`
moved".

### 9.4 The transport question, and an OPEN ITEM the handoff cannot close

> **"P4" means three different things in this campaign's vocabulary. Fix the
> referent before reading anything below.**
>
> | usage                     | what it is                                                                                                | where                               |
> | ------------------------- | --------------------------------------------------------------------------------------------------------- | ----------------------------------- |
> | **P4, the phase**         | the next phase of the evaluation campaign, deferred to a later session                                    | this section, section 9 generally   |
> | **P4, the Phase-0 probe** | the pre-declared probe "NDT rate with the relay stopped, vs ≥ 9.0 Hz", whose failure selected branch (c)  | 5.2's branch table; PROVENANCE §6.7 |
> | ~~P4, a confound row~~    | **removed** — this document's confound rows were relabelled `P3-1`…`P3-6` precisely to end this collision | 7.1                                 |
>
> Every bare "P4" outside 5.2 means the phase.

**OPEN ITEM, and it falsifies part of this section's first revision: P4's scope
is registered NOWHERE in this repository.** That revision asserted "P4 already
has transport as a registered axis". It does not. Checkable:
`grep -c P4 benchmarks/README.md` returns **0**, and `benchmarks/config/cells.yaml`
registers no transport axis — its `sweep_arms` are `paced` / `unpaced` /
`ablation`, and `transport` appears only as a per-run recorded block, never as a
dimension to sweep. The claim is withdrawn.

This matters because section 9 opens by promising that everything P4 needs lives
in this document and in PROVENANCE §10, and **the SDD workspace that held P4's
plan is git-ignored scratch that is deleted when this plan finishes.** The
honest statement of what survives:

- **What P3 owes P4 IS committed and complete**: the environment identity to
  re-verify (9.1), the `harness_git_sha` move and its blast radius (9.3), cell
  B's closed-loop blocker (9.2), the verdict and every caveat on it, and the
  full deviations log (section 8).
- **What P4's own scope is, is NOT committed anywhere.** Whoever runs P4 must
  re-derive or re-register it. This document does not invent it, because a
  scope written here by the wrap would be a pre-registration authored after
  seeing P3's results — precisely what the campaign's no-tuning rule forbids.

**What the repository DOES hold for the transport question, stated as fact
rather than as a promise about P4.** Section 5.1's finding is bounded to "the
as-shipped tier4 transport configuration on this host" and is explicitly **not**
attributed to the tier4-native approach; settling it needs a controlled
transport comparison. The campaign already built one instrument for that and it
is committed and frozen: **cell `CAL-rmw`**, 15 interleaved runs at the duel
size across three DDS configurations (5 each, visible as three distinct
`dds_profile_sha256` values in the 9.1 census), from which
`benchmarks/config/margins.yaml`'s `one_hop_wall_ms` margin was frozen
(`p50_cyclonedds` 0.6840 ms, `p50_fastdds-udp` 1.0993 ms; the registered formula
put 2 × abs(Δ) at 0.83 ms, so the pre-registered floor of 2.0 binds). A
transport phase that reuses that cell and that margin inherits a
measurement-grade baseline rather than starting cold. `B/run-033` is a single
non-duel bounding probe and is **not** a substitute for it.

Two things any later phase must **not** do with `run-033`: treat it as a cell-B
measurement (its manifest says on its face that its transport does not match
`cells.yaml` — `transport.rmw = rmw_cyclonedds_cpp`, `dds_profile_sha256 = ""`,
`duel_admissible: false`), and read its `ndt_rate_ratio` of 1.000 as reopening
branch (c). Both are observations at n = 1.

## 10. Reproduction index

Every command in this document, in one place. All were run from the repository
root at commit `269b931` on an idle host.

| #   | produces                                                     | command                                                                                                                                                                        |
| --- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | section 3's per-cell tables (exit 1, explained in section 3) | `PYTHONPATH=. python3 -m benchmarks.report benchmarks/results > /tmp/p3-report-tables.md`                                                                                      |
| 2   | section 4's verdict — **the campaign's single invocation**   | `PYTHONPATH=. python3 benchmarks/scripts/duel_verdict.py A B \| tee /tmp/p3-duel-verdict.md`                                                                                   |
| 3   | section 2.1's per-run classification                         | the `manifest.json` walk in 2.1                                                                                                                                                |
| 4   | section 6's NDT-pose counts                                  | the `observer.csv` walk in 6                                                                                                                                                   |
| 5   | section 9.3's blast radius                                   | `git diff --name-only 5a28339 269b931 -- . ':(exclude)benchmarks/results' ':(exclude)benchmarks/evidence'`                                                                     |
| 6   | section 9.3's per-cell registration diff                     | the `cells.yaml` comparison in 9.3                                                                                                                                             |
| 7   | the per-cell metric bindings quoted throughout               | `PYTHONPATH=. python3 -c "from benchmarks.scripts.cell_info import load_cells_doc, metrics_for; d=load_cells_doc(None); print(metrics_for(d,'A')); print(metrics_for(d,'B'))"` |
| 8   | the M5 quality figures quoted in sections 2, 5 and 6         | `python3 -c "import json,pathlib;[print(p.parent.name, json.loads(p.read_text())) for p in sorted(pathlib.Path('benchmarks/results').glob('*/run-*/quality.json'))]"`          |
| 9   | the test-suite baseline                                      | `python3 -m pytest tests/ -q` → **1084 passed, 1 skipped** (1075 before the review wave added 9 tests)                                                                         |
