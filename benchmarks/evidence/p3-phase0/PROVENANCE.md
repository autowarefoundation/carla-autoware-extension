# P3 Phase 0 — harness re-verification: what is retained and what is not

Decision supported: **the Phase 0 branch ruling — branch (c)**, the decision
gate of the P3 completion plan
(`specs/2026-07-31-p3-completion-design.md`, "Phase 0 — Harness
re-verification (live, decision gate)"). Every later P3 task keys off it.

Session: 2026-07-31, HEAD `d7460abadd2aa116587dcb9c5925057c6c79984b`, branch
`bench/p3-baseline`.

## The claim this bundle backs

The pre-declared hypothesis — _"B's NDT-rate depression is caused by double
publication on `/sensing/lidar/concatenated/pointcloud` (harness relay + tier4
`concatenate_data`), absent on A (relay only)"_ — is **REFUTED**, because probe
P1 measured the same double publication on cell A.

## Retention status, per figure

| Figure                                                                                                                                  | Status                                                                                                                                                                                                                                                                                                     |
| --------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1: cell A `RELAY_OUT` publisher count = **2** (`/sensing/lidar/concatenate_data`, `//relay`)                                           | **RETAINED** — full `ros2 topic info -v` output, plus the `--no-daemon` corroboration, in `probe-transcripts.md` §3                                                                                                                                                                                        |
| P2: cell B `RELAY_OUT` publisher count = **2** (`/relay`, `/sensing/lidar/concatenate_data`)                                            | **RETAINED** — `probe-transcripts.md` §4, including the three under-discovering `--no-daemon` attempts that preceded it                                                                                                                                                                                    |
| Cell B graph-discovery under-reporting under `--no-daemon` (relay alive at pid 437, discovered by neither `topic info` nor `node list`) | **RETAINED** — `probe-transcripts.md` §4                                                                                                                                                                                                                                                                   |
| P3 (concat output usability) and P4 (NDT rate, relay killed)                                                                            | **NOT MEASURED, deliberately** — the pre-declaration removed their decisional role once P1 returned 2; no value is asserted for either, and the 9.0 Hz recovery threshold is not evaluated                                                                                                                 |
| Whether cell A's `concatenate_data` is _emitting_ or merely _advertising_                                                               | **NOT MEASURED** — the supplementary rate probe failed on a bad flag (`ros2 topic hz` has no `--no-daemon`) and the harness window closed before a retry. Open question, stated in `probe-transcripts.md` §3; it is **not** adjudication input, because the pre-declared P1 criterion is a publisher count |
| The per-run gate lines for `A/run-013` and `B/run-023`                                                                                  | **RETAINED** — in `probe-transcripts.md` §7, and recomputable from each run's own `quality.json`, which is filed under `benchmarks/results/`                                                                                                                                                               |
| Host preamble (loadavg, GPU, governor, no CARLA consumer)                                                                               | **RETAINED** — `probe-transcripts.md` §2, with the `pgrep` self-match line truncated for width and labelled as truncated                                                                                                                                                                                   |

## Recomputing the probes

Both censuses are single commands against a live stack; there is no offline
series to re-analyse. To re-take either, bring the cell up and probe it:

```bash
# cell A (or B; both name their Autoware container `autoware`)
bash benchmarks/run.sh A --arm static      # no --duel: duel_admissible=false
docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && \
  source /opt/autoware/setup.bash && \
  ros2 topic info -v /sensing/lidar/concatenated/pointcloud'
```

**On cell B, give the `ros2cli` daemon time to finish discovery before reading
the count.** Measured this session: on B's `rmw_fastrtps_cpp` / SHM-off
transport a `--no-daemon` census returned nothing, then 1 publisher with
`_NODE_NAME_UNKNOWN_`, while the settled daemon returned the correct 2 out of a
162-node graph. That is the **opposite** polarity of the stale-daemon trap
`benchmarks/run.sh:789` documents, and it will silently produce a wrong count.
Cell A (`rmw_cyclonedds_cpp`) showed no such split.

## What is deliberately NOT here

No relay was killed and no NDT rate was measured with a single publisher, so
this bundle contains **no** post-kill rate, no concat-output cloud dump, and no
recovery/non-recovery figure. Reconstructing one now would be fabrication: the
pre-declaration says what those probes mean only while double publication is a
differential between the cells, and P1 measured that it is not.

The bundle also asserts **no A-vs-B comparison**. The two runs it references
are `duel_admissible: false` bring-up-class runs; the equivalence verdict is
computed once, later, by `duel_verdict.py`.
