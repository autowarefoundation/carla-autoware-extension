# P4 Task 11 bring-up console logs (filed 2026-08-03, fix round 1)

Console capture for the two runs of P4 Task 11 — `benchmarks/results/A/run-015`
(cell A, static, non-duel) and `benchmarks/results/B-cyc/run-001` (cell B-cyc,
closed-loop, non-duel). Filed here because `PROVENANCE.md` §14 quotes several
strings that exist **only** on the console: `run.sh`'s per-step banners, the
step-9 flow gate, the teardown summary, and two `ros2 topic` transcripts taken
by hand while the cell-A stack was up.

Nothing here is a gate output — neither run is scored, and no verdict rests on
these files. They exist so §14's quoted strings are checkable rather than
transcribed. The **measurements** all live in the two run directories, which are
unchanged.

## What is here

| File                               | What it is                                                                                                                       |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `a-bringup-console.log`            | Full `bash benchmarks/run.sh A --arm static` console, all 15 steps including preflight readings and the teardown summary.         |
| `a-published-time-topiclist.log`   | The §14.2 check verbatim: `ros2 topic list \| grep published_time` inside the `autoware` container while the cell-A stack was up. |
| `a-published-time-topicinfo.log`   | The transcript that makes §14.2's argument: `ros2 topic info -v` on the registered PublishedTime topic (**Publisher count: 0**, sole endpoint `bench_observer`) and `ros2 topic info` on `/control/command/control_cmd` (**Publisher count: 1**). |
| `b-cyc-smoke-console.log`          | Full `bash benchmarks/run.sh B-cyc --arm closed-loop` console: the tier4 artifact gate, the arm sequence, `OK: /control/command/control_cmd is flowing`, the `OK: base_link anchor -1.39706787 m` check, and the teardown summary. |
| `b-cyc-lidar-mount.log`            | The §14.5 LiDAR mount capture: attach chain, blueprint attributes, and the six `--mount` numbers with the decomposition residual. |
| `b-cyc-actor-list-after-tick.log`  | The §14.6 CARLA finding: `actors before tick: 0` → `actors after tick: 31` on a freshly-connected client.                         |
| `capture_tier4_mount.py`           | The read-only probe that produced `b-cyc-lidar-mount.log`. Never ticks, never calls `apply_settings`.                             |

## Retention status, per figure

- **RETAINED, and byte-exact here**: every string §14 quotes from the console —
  the topic listing, both `ros2 topic info` transcripts, `OK: /control/command/control_cmd is flowing`,
  `OK: base_link anchor -1.39706787 m matches ...`, the teardown summaries
  (`0 survivor(s)` / `teardown: done`), and the six `--mount` numbers.
- **RETAINED in the run directories, not here**: every number in `quality.json`,
  `manifest.json`, `observer.csv`, `published_time.csv` and `arm.log`. §14 and
  §15 cite those from `benchmarks/results/`, which is the authority; these
  console files are a transcript of the same session, not a second source.
- **NOT RETAINED**: the container's own stdout for the Autoware stack on the
  cell-A run beyond what `run.sh` echoed. Cell A's editor stdout **is** filed,
  as `benchmarks/results/A/run-015/carla-editor.log` (added by `876b500`); the
  tier4 side's equivalents are `tier4-autoware.log`, `tier4-demo.log` and
  `tier4-concat-relay.log` in the B-cyc run directory.
- **NOT A SOURCE OF ANY VERDICT**: these logs were captured by shell redirection
  during the session and are filed after the fact. Where a console string and a
  filed artifact could disagree, **the filed artifact wins** — §15's I2
  correction is exactly such a case, and it was resolved against
  `benchmarks/results/B-cyc/run-001/arm.log`, not against
  `b-cyc-smoke-console.log`.
