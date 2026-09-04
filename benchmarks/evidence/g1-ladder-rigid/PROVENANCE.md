# G1 ladder — the two RIGID Town10 registrations (the FAIL rungs)

Raw series for the ladder rungs that MISSED the 0.5 m absolute gate. Promoted so
the numbers the ladder record rests on are recomputable, not merely asserted:
they are cited in `benchmarks/config/cells.yaml`, `benchmarks/README.md`'s
2026-07-29 ladder amendment, and the Task 11 report.

**Written by hand, not by the gate.** These three runs predate
`gate_g1_localization.sh`'s per-run retention, so no `g1_summary.txt` exists for
them and none is fabricated here — this file is the substitute, and it is named
so nobody mistakes it for gate output. The series themselves ARE the gate's own
(the ego-pose and ground-truth files it fed to `measure_ndt.py`); only the
summary is reconstructed.

| Directory       | Bundle        | `pins.yaml` block    | max NDT error | Verdict |
| --------------- | ------------- | -------------------- | ------------- | ------- |
| `shifted-run1/` | `dy = -0.475` | `town10_pcd_shifted` | **0.824 m**   | FAIL    |
| `shifted-run2/` | `dy = -0.475` | `town10_pcd_shifted` | **0.749 m**   | FAIL    |
| `refit/`        | `dy = -0.607` | `town10_pcd_refit`   | **0.570 m**   | FAIL    |

`shifted-run1` is the Step-3 protocol run — the pristine GNSS-initialised lock,
no reseed — and is therefore the number that drove the ladder forward.
`shifted-run2` is the same bundle measured again after a ground-truth reseed;
having two windows on one bundle is what bounds the max statistic's own spread
at 0.075 m. `refit/` is rung 1's single permitted repeat.

All three: static ego, `Town10HD_Opt`, 20 s window, 399–400 NDT samples.

## Recomputing

```bash
for d in shifted-run1 shifted-run2 refit; do
  python3 scripts/e2e/measure_ndt.py \
    --ndt benchmarks/evidence/g1-ladder-rigid/$d/g1_ndt.txt \
    --gt  benchmarks/evidence/g1-ladder-rigid/$d/g1_gt.txt --max-err-m 0.5
done
```

Verified to reproduce 0.824 / 0.749 / 0.570 exactly before promotion.

The per-axis decompositions quoted in the record (dx/dy means and standard
deviations, the drift and spread figures for the relative branch, and the
Chebyshev-optimal residual of 0.503989 m on the refit window) are all derived
from these same two-column series, so they are recomputable from this directory
too.

## Bundle digests these runs were measured against

The gate did not yet record the bundle digest in 2026-07-29's earlier runs, so
attribution here is by `pins.yaml` block name rather than by a digest the run
itself captured — a weaker link than `g1-rung2-regen/`, whose `g1_summary.txt`
carries the digest. Stated rather than glossed: the mapping above comes from the
run order in the Task 11 report, not from metadata inside these files.
