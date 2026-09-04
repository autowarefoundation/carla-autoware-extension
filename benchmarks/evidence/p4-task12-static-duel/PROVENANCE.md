# P4 Task 12 static-duel console logs (filed 2026-08-03)

Console capture for the A-vs-B-cyc **static** duel — `benchmarks/results/A/run-016`
… `run-025` and `benchmarks/results/B-cyc/run-002` … `run-011`, twenty runs in
ten interleaved pairs, all `duel_admissible: true` / `duel_id: "A+B-cyc"`.

Filed here because `benchmarks/results/PROVENANCE.md` §18 quotes strings that
exist **only** on the console: `duel.sh`'s pair banners and pacing lines, the
per-run step banners, and — the reason this directory exists at all — the exact
point at which the first `duel.sh` invocation was killed by the orchestration
layer. That kill is a measurement-condition event, not a run failure, and §18's
classification of it rests on what these two logs do and do not contain.

Nothing here is a gate output. Every **measurement** lives in the twenty run
directories, which are unchanged. `integrity-pass.log` is a derived re-read of
those directories, not a new measurement.

## What is here

| File                                   | What it is                                                                                                                                                                                                                              |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `duel-static-console-part1.log`        | Full console of invocation 1, `bash benchmarks/scripts/duel.sh A B-cyc --arm static --pairs 10`. Covers pairs 1-7 complete (14 runs). Ends mid-`sleep`, inside the 120 s pacing floor before pair 8, with no further output — the kill. |
| `duel-static-console-part2-resume.log` | Full console of invocation 2, `bash benchmarks/scripts/duel.sh A B-cyc --arm static --pairs 3`, the shortfall make-up. Runs to `duel complete: A 3 ok / 0 failed, B-cyc 3 ok / 0 failed`.                                               |
| `integrity-pass.log`                   | Output of `integrity_pass.py` over all twenty runs (brief Step 2 + Step 3).                                                                                                                                                             |
| `integrity_pass.py`                    | The exact script that produced `integrity-pass.log`. Read-only over `benchmarks/results/`.                                                                                                                                              |

## Capture method, and why not `tee`

Both duel logs were captured with plain `>` redirection rather than the brief's
`… | tee <path>`, to the same path the brief names for invocation 1
(`/tmp/duel-static-p4.log`), then copied here. The repo's standing note is that
an `rtk` proxy compresses piped output; `>` keeps the bytes exact. The
destination, the command, and the arguments are otherwise the brief's verbatim.
This is a capture-method deviation only — it cannot affect what `duel.sh` did,
since the redirection is applied to its stdout after the fact.

`benchmarks/evidence/**` is excluded from the text-mutating pre-commit hooks
(`benchmarks/results/PROVENANCE.md` §17), so these files are byte-exact as
captured. Recorded sha256 at filing time:

```text
2c0da80a5ce10b3a4c2f0462808b7c520f6e219726b84bc464994c6eed814ee9  duel-static-console-part1.log
a10c6c265e05fca16eb460c77e9ab42f934fae130db9a39575fb6974a8b21b27  duel-static-console-part2-resume.log
5dadd106d44e85b3d2d7edda1e1300b9a54d6851e5f5bf5cb9f166d888c094d0  integrity-pass.log
5876b3490d0de0d606eb251f57bddfa7be3f520af51196e5314dd8f114b275a8  integrity_pass.py
```

## What `part1.log` proves about the kill, specifically

Three properties of this file are what let §18 classify the kill as an
orchestration-layer event rather than a duel abort or a stack defect:

1. It contains **no** `DUEL FAIL` line. That string is written by `duel.sh`'s
   only self-abort path (`die()`), including the two-consecutive-failure abort.
   Its absence means `duel.sh` did not stop itself.
2. It contains **no** `duel: <cell> run in pair N FAILED` line, so no run in it
   was recorded as failed by the driver.
3. Its final line is the pair-8 pacing-floor announcement, with the run-8
   teardown (`teardown: done`) and step 15 completed above it. The process was
   inside `sleep 120`, between runs, when it died — no run was in flight.

`integrity_pass.py` is deliberately silent about cell A's `ndt_rate_ratio`
(brief Step 3 is a within-B-cyc reading only); it prints cell A rows for the
integrity columns alone.

## Correction appended 2026-08-04 (review fix round 1)

This directory's "What `part1.log` proves about the kill, specifically" section
above lists **three** properties, and that count was and is correct. The
campaign record's `benchmarks/results/PROVENANCE.md` §18.2 disagreed with it,
claiming **four** checkable facts "all in" these files — the fourth being the
simultaneous death of an unrelated passive watcher process. That fourth item is
**not in these files and not in any filed artifact**: it was an agent-harness
notification observed by the operator at the time.

`PROVENANCE.md` §19.1 corrects the campaign record to "three checkable facts,
plus one operator observation not captured in the filed logs", so the two
records now agree, with this directory's count being the one that was right.

No transcript of the watcher-process death is filed, because none exists in
byte-exact form and manufacturing one after the fact would defeat the purpose of
this directory. The three properties listed above are jointly sufficient to
classify the interruption: the first two exclude a `duel.sh` self-abort, and the
third excludes a run-in-flight failure.

The four captured files are unchanged by this correction and still hash to the
digests recorded above.
