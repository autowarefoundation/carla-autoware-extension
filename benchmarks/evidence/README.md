# Gate evidence for decision runs (tracked)

Raw artifacts for the live gate runs whose numbers a **pre-registered decision**
rests on, kept under version control so those numbers stay recomputable.

## Why this directory exists rather than `reports/`

`reports/` is the default home for gate artifacts and is **`.gitignore`d**
(`.gitignore:3`), which is right for routine runs — they are numerous and
disposable. It is wrong for a run that selects a campaign-wide parameter: the
`max_err=0.089 m … PASS` in `g1-rung2-regen/g1_summary.txt` is what selects
`abs_pose_gate_m: 0.5` for every Town10 cell, and while it lived only in
`reports/` it existed on exactly one workstation, in a path that `git clean
-fdx` removes and that no fresh clone ever has. A number nobody else can
re-derive is weak evidence, whatever it says.

Two alternatives were considered and rejected:

- **`reports/` plus a `.gitignore` negation** — `reports/` is bind-mounted into
  the `autoware` container, which runs as root and creates paths there
  root-owned; tracking a subtree of it invites permission churn in the working
  tree.
- **`benchmarks/results/<cell>/run-<NNN>/`** — those directories carry a
  `manifest.json` and are enumerated by `duel_verdict.py` and
  `sweep_verdict.py`. Ladder runs have no cell id and no manifest, so filing
  them there would either fabricate provenance or feed malformed runs to tools
  that must refuse them.

## How to write here

Both gates take an output directory, so a decision run simply points at one:

```bash
G1_RUN_DIR=benchmarks/evidence/g1-<slug> bash scripts/e2e/gate_g1_localization.sh
G2_RUN_DIR=benchmarks/evidence/g2-<slug> bash scripts/e2e/gate_g2_closed_loop.sh <x> <y>
```

Unset, both default to `reports/g{1,2}-<UTC stamp>`, so **routine runs keep
going to the ignored path** and only deliberate promotions land here. Use a slug
that names the decision, not the date — the artifacts carry their own timestamp.

## What is here

| Directory                   | Decision it supports                                                                                                                                                                                                                                                           |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `g1-rung2-regen/`           | Selects the G1 ladder's **absolute** branch, `abs_pose_gate_m: 0.5`, for cells A/A-hf: max NDT error **0.089 m** against the 0.5 m gate on `pins.yaml` `town10_pcd_regen`. Contains the raw NDT and ground-truth series plus the bundle digest the verdict is attributable to. |
| `g2-regen-committed-route/` | The **1.929 m** FAIL on the original 438.9 m Town10 route — the measurement that justified re-picking the route.                                                                                                                                                               |
| `g2-regen-repicked-route/`  | The **0.244 m** PASS on the re-picked 258.9 m route.                                                                                                                                                                                                                           |

Each `*_summary.txt` records the map, the bundle's own pcd `sha256`, the window
and the verdict, so a reader can confirm which bytes produced which number
without trusting a transcript.

## Recomputing a verdict

The series are plain text (`<wall-clock seconds> <x_m> <y_m>` for G1; one
ego-to-goal distance per line for G2), and the gates' own analysis scripts take
them directly:

```bash
python3 scripts/e2e/measure_ndt.py \
  --ndt benchmarks/evidence/g1-rung2-regen/g1_ndt.txt \
  --gt  benchmarks/evidence/g1-rung2-regen/g1_gt.txt --max-err-m 0.5

python3 scripts/e2e/measure_route.py \
  --distances benchmarks/evidence/g2-regen-repicked-route/g2_dist.txt \
  --goal-tol-m 1.0
```

## What is deliberately NOT here

Evidence that was not retained is not reconstructed. The NDT-score breach
distribution once cited for the route re-pick came from a container-side launch
log that no longer exists; the claim has been restated in terms of the retained
distance series instead. An invalid run is likewise kept out of this directory
and left under `reports/` with an `INVALID.txt` explaining what was discarded.
