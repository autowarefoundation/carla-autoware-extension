# P3 Phase 0 — harness re-verification: what is retained and what is not

Decision supported: **the Phase 0 branch ruling — FINAL: branch (c)**, reached
in three stages (count-based ruling → BLOCKED on an instrument correction →
owner ruling to resume → final ruling on P3/P4), the decision gate of the P3
completion plan
(`specs/2026-07-31-p3-completion-design.md`, "Phase 0 — Harness
re-verification (live, decision gate)"). Every later P3 task keys off it.

Sessions, branch `bench/p3-baseline`:

- **2026-07-31**, HEAD `d7460abadd2aa116587dcb9c5925057c6c79984b` — the original
  Phase 0 session (`A/run-013`, `B/run-023`).
- **2026-08-01**, HEAD `f0f8b4b` — fix round 1, the cell-A emission measurement
  (`A/run-014`).
- **2026-08-01**, HEAD `6c4bbe8` — fix round 2, P3/P4 on cell B
  (`B/run-024…027`).
- **2026-08-01**, HEAD `860e077` — fix round 3, record corrections only; **no
  live run**, every figure re-read from already-filed `observer.csv`.

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

That first ruling was therefore procedurally correct on the pre-declared
criterion and NOT substantively established, and the task returned BLOCKED
rather than re-adjudicating.

## What fix round 2 settled (2026-08-01) — the FINAL ruling

The owner ruled **resume Phase 0 at P3/P4** rather than honour the literal count
criterion or re-run from P2: both probes are pre-declared with pre-declared
thresholds, so running them shapes no outcome. Four cell-B runs
(`B/run-024…027`) then produced the measurement Phase 0 never had:

- **The differential is real.** Cell B: out/in ratio **1.818**, **72 duplicate
  stamps** of 88 unique, loss symmetry **0/0** ⇒ **2 emitters**. Cell A:
  ratio 0.995, 0 duplicates ⇒ **1 emitter**.
- **P3 PASSES on cloud structure**: `frame_id` `base_link`, `width` 6202,
  `point_step` 16, `is_dense` true, x/y/z/intensity/return_type/channel, topic
  steady at 7.612 Hz. Branch (b)'s trigger ("empty/malformed clouds") is not met.
- **P4 finds NO recovery**: **0.000 Hz** post-kill on three independent runs
  against the pre-declared **≥ 9.0 Hz**; pre-kill with both emitters 4.830 Hz
  (ratio ≈ 0.48). Branch (c)'s trigger is met.

**FINAL: branch (c).** The differential is real but is **not the cause**: no run
demonstrated recovery to the pre-declared ≥ 9.0 Hz. Fix mechanism: **none**; no
harness change.

**Corrected in fix round 3** (the "it stops NDT altogether" wording used here
before): P4 selects (c) by **failing to demonstrate recovery**, not by showing
that killing the relay stops NDT. `results/B/run-027`'s own filed `observer.csv`
records NDT **resuming** ≈ 29 s after the kill with `concatenate_data` as sole
publisher; the probe reported 0.000 Hz because its window closed 4.2 s too
early. No run pairs a live pre-kill baseline with a post-kill measurement on the
same stack, so the post-kill zeros are **unattributed**. The ruling is
unaffected — the best post-kill reading on any run is ≈ 0.07 Hz against a 9.0 Hz
bar — but the causal claim is withdrawn. See `probe-transcripts.md` §12 and
`results/PROVENANCE.md` §6.8. All three stages are
kept here in order, because the final branch is the same letter as the first but
not the same ruling: the first rested on a criterion measuring the wrong
quantity, the final rests on the spec's own P3 and P4.

## Retention status, per figure

| Figure                                                                                                                                  | Status                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1: cell A `RELAY_OUT` publisher count = **2** (`/sensing/lidar/concatenate_data`, `//relay`)                                           | **RETAINED** — full `ros2 topic info -v` output, plus the `--no-daemon` corroboration, in `probe-transcripts.md` §3                                                                                                                                                                                                                                                                                                                                 |
| P2: cell B `RELAY_OUT` publisher count = **2** (`/relay`, `/sensing/lidar/concatenate_data`)                                            | **RETAINED** — `probe-transcripts.md` §4, including the three under-discovering `--no-daemon` attempts that preceded it                                                                                                                                                                                                                                                                                                                             |
| Cell B graph-discovery under-reporting under `--no-daemon` (relay alive at pid 437, discovered by neither `topic info` nor `node list`) | **RETAINED** — `probe-transcripts.md` §4                                                                                                                                                                                                                                                                                                                                                                                                            |
| P3: concat cloud structure with the relay dead — `base_link`, `width` 6202, `point_step` 16, `row_step` 99232, `is_dense`, 6 fields     | **RETAINED, measured in fix round 2** — `probe-transcripts.md` §11.4, from `results/B/run-027` via `probe_relay_kill_transition.py`                                                                                                                                                                                                                                                                                                                 |
| P4: NDT rate **4.830 Hz** pre-kill and **0.000 Hz** post-kill against the pre-declared ≥ 9.0 Hz                                         | **RETAINED, BUT THE PAIR IS NOT WITHIN-STACK** — the pre-kill figure is `results/B/run-024`'s and the post-kill figures are `run-025`/`run-026`/`run-027`'s; **no run pairs a live pre-kill baseline with a post-kill measurement on the same stack**, so the post-kill zeros are **unattributed**. `probe-transcripts.md` §11.3 for the raw output, §12.2 for the per-run gap analysis                                                             |
| That NDT **resumed** ≈ 29 s after the kill on `run-027`, with `concatenate_data` as sole publisher (14:04:23.537, 14:04:24.292)         | **RETAINED** — read directly from `results/B/run-027/observer.csv`; the probe's 0.000 Hz was a **window artifact** (its window closed 14:04:19Z, 4.2 s early). `probe-transcripts.md` §12.1 carries the recomputation snippet                                                                                                                                                                                                                       |
| That killing the relay **causes** NDT to stop (the "relay is load-bearing" claim)                                                       | **WITHDRAWN, not established** — see `probe-transcripts.md` §12.3 and `results/PROVENANCE.md` §6.8. Branch (c) is selected by **elimination** (best post-kill reading ≈ 0.07 Hz against the ≥ 9.0 Hz recovery bar), not by a demonstrated mechanism                                                                                                                                                                                                 |
| Cell B emitter count = **2** (out/in 1.818, 72 duplicate stamps, loss symmetry 0/0)                                                     | **RETAINED** — `probe-transcripts.md` §11.2, from `results/B/run-024`                                                                                                                                                                                                                                                                                                                                                                               |
| That the relay pid surviving SIGKILL on `run-027` was a **zombie**                                                                      | **NOT CONFIRMED** — `/proc/<pid>/stat` was not read before the container was removed. What is measured instead, and is what P4 needs, is the DDS-level census on `run-024`/`run-025` showing the relay gone from the graph and the publisher count down to 1                                                                                                                                                                                        |
| Whether `concatenate_data`'s duplicate header stamps are what stops NDT                                                                 | **NOT TESTED** — recorded in `probe-transcripts.md` §11.4/§12.4 and `results/PROVENANCE.md` §6.7/§6.8 explicitly as an unproven hypothesis, not a finding. It also has **less to explain** than first thought: `run-027` shows NDT resuming on that very stream                                                                                                                                                                                     |
| Whether cell A's `concatenate_data` is _emitting_ or merely _advertising_                                                               | **RETAINED, measured in fix round 1** — it **only advertises**: out/in 398/400, 0 unmatched stamps, 0 duplicate stamps, aggregate 19.957 Hz vs `RELAY_IN` 19.960 Hz. Raw output in `probe-transcripts.md` §10, probe committed as `probe_concat_emission.py`, run filed as `results/A/run-014`. This is what BLOCKED the count-based ruling and sent the task back for the owner decision that reopened P3/P4; the ruling is now final (branch (c)) |
| The two ~310-entry `widths` histograms in the `probe_concat_emission.py` output                                                         | **TRUNCATED, not retained in full** — labelled in place in `probe-transcripts.md` §10. Per-frame point counts; they carry no attribution information and every attribution figure is retained                                                                                                                                                                                                                                                       |
| Individual wall-clock times of probes P1 and P2                                                                                         | **NOT RETAINED** — not captured inline. `probe-transcripts.md` §8 gives the bounds each probe necessarily falls inside, derived from the filed runs' own `manifest.json`/`quality.json` mtimes, and reconstructs nothing beyond them                                                                                                                                                                                                                |
| The per-run gate lines for `A/run-013` and `B/run-023`                                                                                  | **RETAINED** — in `probe-transcripts.md` §7, and recomputable from each run's own `quality.json`, which is filed under `benchmarks/results/`                                                                                                                                                                                                                                                                                                        |
| Host preamble (loadavg, GPU, governor, no CARLA consumer)                                                                               | **RETAINED** — `probe-transcripts.md` §2, with the `pgrep` self-match line truncated for width and labelled as truncated                                                                                                                                                                                                                                                                                                                            |

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

No relay was ever killed on **cell A**, so this bundle contains no cell-A
post-kill figure and asserts none; the kill probes are a cell-B protocol step and
only cell B was subjected to them. Cell B's raw cloud payloads are not retained
either — the structural metadata is (`frame_id`, `height`, `width`,
`point_step`, `row_step`, `is_dense`, field layout), which is what P3 asks for,
but the 99232 bytes of points behind each cloud are not.

The bundle asserts **no A-vs-B comparison of scores**. The seven runs it
references (`A/run-013`, `A/run-014`, `B/run-023`, `B/run-024…027`) are all
`duel_admissible: false` bring-up-class runs; the equivalence verdict is
computed once, later, by `duel_verdict.py`. The cell-A-vs-cell-B **emitter
count** comparison is not a score comparison — it is the differential the
pre-declared hypothesis itself names, measured by one instrument on both cells.
