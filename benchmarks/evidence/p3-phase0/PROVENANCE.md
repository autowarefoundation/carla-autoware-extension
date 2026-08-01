# P3 Phase 0 — harness re-verification: what is retained and what is not

Decision supported: **the Phase 0 branch ruling — branch (c), now BLOCKED
pending an owner decision** (see "What fix round 1 changed" below), the decision
gate of the P3 completion plan
(`specs/2026-07-31-p3-completion-design.md`, "Phase 0 — Harness
re-verification (live, decision gate)"). Every later P3 task keys off it.

Session: 2026-07-31, HEAD `d7460abadd2aa116587dcb9c5925057c6c79984b`, branch
`bench/p3-baseline`.

## The claim this bundle backs

The pre-declared hypothesis — _"B's NDT-rate depression is caused by double
publication on `/sensing/lidar/concatenated/pointcloud` (harness relay + tier4
`concatenate_data`), absent on A (relay only)"_ — was ruled **REFUTED** on
2026-07-31, because probe P1 measured **2 publishers** on cell A.

## What fix round 1 changed (2026-08-01) — read this before citing the ruling

P1's pre-declared criterion is a publisher **count**, and a count cannot tell an
_advertised_ publisher from an _emitting_ one. Fix round 1 measured the
difference on a third cell-A stack (`results/A/run-014`): cell A's
`concatenate_data` **advertises a publisher and emits nothing**. The spec's
hypothesis names double _publication_, so P1 did not measure the phenomenon its
own hypothesis names, and the differential the hypothesis rests on is **not**
refuted by it.

The branch-(c) ruling is therefore **procedurally correct on the pre-declared
criterion and NOT substantively established**. It is left in the record exactly
as it was made, with what undermined it attached — this bundle is the evidence
for both. **Nothing may be built on the ruling until the owner rules** on
whether the count criterion stands as written or is superseded by a
publication-based one. Re-adjudicating to (a)/(b) here would mean reshaping the
spec's branch table after seeing data, which is what the pre-declaration exists
to prevent.

## Retention status, per figure

| Figure                                                                                                                                  | Status                                                                                                                                                                                                                                                                                                                         |
| --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| P1: cell A `RELAY_OUT` publisher count = **2** (`/sensing/lidar/concatenate_data`, `//relay`)                                           | **RETAINED** — full `ros2 topic info -v` output, plus the `--no-daemon` corroboration, in `probe-transcripts.md` §3                                                                                                                                                                                                            |
| P2: cell B `RELAY_OUT` publisher count = **2** (`/relay`, `/sensing/lidar/concatenate_data`)                                            | **RETAINED** — `probe-transcripts.md` §4, including the three under-discovering `--no-daemon` attempts that preceded it                                                                                                                                                                                                        |
| Cell B graph-discovery under-reporting under `--no-daemon` (relay alive at pid 437, discovered by neither `topic info` nor `node list`) | **RETAINED** — `probe-transcripts.md` §4                                                                                                                                                                                                                                                                                       |
| P3 (concat output usability) and P4 (NDT rate, relay killed)                                                                            | **NOT MEASURED, deliberately** — the pre-declaration removed their decisional role once P1 returned 2; no value is asserted for either, and the 9.0 Hz recovery threshold is not evaluated                                                                                                                                     |
| Whether cell A's `concatenate_data` is _emitting_ or merely _advertising_                                                               | **RETAINED, measured in fix round 1** — it **only advertises**: out/in 398/400, 0 unmatched stamps, 0 duplicate stamps, aggregate 19.957 Hz vs `RELAY_IN` 19.960 Hz. Raw output in `probe-transcripts.md` §10, probe committed as `probe_concat_emission.py`, run filed as `results/A/run-014`. This is what BLOCKS the ruling |
| The two ~310-entry `widths` histograms in the `probe_concat_emission.py` output                                                         | **TRUNCATED, not retained in full** — labelled in place in `probe-transcripts.md` §10. Per-frame point counts; they carry no attribution information and every attribution figure is retained                                                                                                                                  |
| Individual wall-clock times of probes P1 and P2                                                                                         | **NOT RETAINED** — not captured inline. `probe-transcripts.md` §8 gives the bounds each probe necessarily falls inside, derived from the filed runs' own `manifest.json`/`quality.json` mtimes, and reconstructs nothing beyond them                                                                                           |
| The per-run gate lines for `A/run-013` and `B/run-023`                                                                                  | **RETAINED** — in `probe-transcripts.md` §7, and recomputable from each run's own `quality.json`, which is filed under `benchmarks/results/`                                                                                                                                                                                   |
| Host preamble (loadavg, GPU, governor, no CARLA consumer)                                                                               | **RETAINED** — `probe-transcripts.md` §2, with the `pgrep` self-match line truncated for width and labelled as truncated                                                                                                                                                                                                       |

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

No relay was killed on either cell and no NDT rate was measured with a single
publisher, so this bundle contains **no** post-kill rate, no concat-output cloud
dump, and no recovery/non-recovery figure. Those probes were skipped on the
strength of P1, and P1 is now known not to have measured what it was taken to
measure — so if the owner supersedes the count criterion, they are what Phase 0
must go back and run. Nothing was destroyed by that: no run was excluded or
reclassified, no `duel_admissible` flag was flipped, and no harness file was
edited, so a re-run from P2 costs two live runs and no recollection.

The bundle also asserts **no A-vs-B comparison**. The three runs it references
(`A/run-013`, `B/run-023`, `A/run-014`) are all `duel_admissible: false`
bring-up-class runs; the equivalence verdict is computed once, later, by
`duel_verdict.py`.
