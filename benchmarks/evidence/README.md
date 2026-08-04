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

## The rule this directory exists to enforce

**Every quantitative claim in the committed record either cites tracked,
recomputable evidence, or is explicitly labelled as not recomputable. There is
no third state.**

The third state — a number stated with neither a citation nor a caveat — is what
this directory was created in response to, and it recurred twice after the first
fix: a commit that removed one unbacked figure introduced two more, one of them
citing series that belonged to a different bundle entirely and so _refuted_ the
claim they were attached to. Fixing instances does not fix the class. So when
adding a number to `README.md`, `cells.yaml` or `pins.yaml`, do one of exactly
two things:

1. **Point at a tracked artifact** under `benchmarks/evidence/` (or another
   committed file) from which the number can be re-derived, and say how — the
   `PROVENANCE.md` files here carry runnable snippets for that purpose.
2. **Say it is not recomputable, and why.** "Observed live; the source log lived
   in a container that has since been removed" is a complete and acceptable
   provenance statement. An honest gap is evidence about the evidence; a bare
   number is not.

Labelling is not a lesser option to be avoided. Several figures in this campaign
legitimately carry it — the rigid-bundle halt distances, the 8-seed sweep, parts
of step 11.6 — because the artifacts genuinely did not survive the runs that
produced them, and reconstructing them would be fabrication.

### What is deliberately absent, and where it is declared

| Claim                                                                       | Status                                                                               |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Rigid-bundle G2 halt at 142.599 m                                           | gate output retained, series overwritten — `g2-rigid-committed-route/PROVENANCE.md`  |
| Rigid-bundle G2 halt at 142.398 m                                           | **not retained** — same file                                                         |
| 8-seed sweep figures (+0.005, +0.132, 1.898 m)                              | **not retained** — declared in `README.md`'s ladder amendment                        |
| NDT-score breach distribution                                               | **not retained**, claim withdrawn — `g2-rigid-committed-route/PROVENANCE.md`         |
| Pre-engage 19.93 Hz, control_mode = MANUAL, ground-truth speeds             | **not retained** — `step-11_6-adapi-engage/PROVENANCE.md`                            |
| Cell C's AD-API-engaged drive, all but its final 12.827 m                   | **not retained** (the arrival is) — `task-15-adapi-engage-cellc/PROVENANCE.md`       |
| That drive covered the FULL route; that no `/autoware/engage` was published | **attested, not retained** — same file                                               |
| G2's teleport-back reset (the landing pose)                                 | **attested, not retained** — `g2-nishi-cellc/PROVENANCE.md`                          |
| G1's loadavg 1.35, cadence rates, "no reseed"                               | **attested, not retained** — `g1-nishi-bundle/PROVENANCE.md`                         |
| Why cell A refused `change_to_autonomous`                                   | **not diagnosed**, two untested candidates named — same file                         |
| Phase 0's cell-B raw cloud payloads (99232 B per cloud)                     | **not retained**; the structural metadata P3 asks for is — `p3-phase0/PROVENANCE.md` |
| Individual wall-clock times of Phase 0 probes P1 and P2                     | **not retained**, bounds attested from filed run mtimes — same file                  |

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

| Directory                     | Decision it supports                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `g1-rung2-regen/`             | Selects the G1 ladder's **absolute** branch, `abs_pose_gate_m: 0.5`, for cells A/A-hf: max NDT error **0.089 m** against the 0.5 m gate on `pins.yaml` `town10_pcd_regen`. Contains the raw NDT and ground-truth series plus the bundle digest the verdict is attributable to.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `g2-regen-committed-route/`   | The **1.929 m** FAIL on the original 438.9 m Town10 route — the measurement that justified re-picking the route.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `g2-regen-repicked-route/`    | The **0.244 m** PASS on the re-picked 258.9 m route.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `g1-ladder-rigid/`            | The ladder's two FAIL rungs — 0.824 / 0.749 m on the `dy = -0.475` shift and 0.570 m on the `dy = -0.607` refit — so the rungs that drove the ladder forward are checkable, not only the one that closed it. Also the source for the Chebyshev-optimal 0.503989 m residual.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `g2-rigid-committed-route/`   | The rigid-bundle G2 outcome, with retention status stated per figure (142.599 m retained as gate output; 142.398 m not retained).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `route-town10-pre-repick/`    | The Town10 route as it stood before the re-pick, so the confound table's superseded row (438.9 m / 250.9 m / 233.0° / 33.468 m) stays recomputable.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `step-11_6-adapi-engage/`     | The AD-API-vs-legacy engage discriminator: `change_to_autonomous` refusing for 60 s, the legacy publish succeeding in the same state, and the gated output at 20.07 Hz commanding +4.170 m/s on 281/281 samples. Its root-cause attribution (`control_mode == MANUAL`) is REFUTED by `task-15-adapi-engage-cellc/`; both are kept.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `b-closed-loop-stopcheck/`    | Cell B's closed-loop gate **FAIL** (Task 13): localization never initializes because `pose_initializer`'s stop check reads a twist carrying **2.17 mm/s of lateral velocity** from the fork's parked ego, so every initialization request is refused 'The vehicle is not stopped.' Contains the run console log, the refusal lines, the stop-check input measurement and the probe scripts, with retention status stated per figure.                                                                                                                                                                                                                                                                                                                                                                                                            |
| `g1-nishi-bundle/`            | Selects the G1 ladder's **absolute** branch, `abs_pose_gate_m: 0.5`, for cell C: max NDT error **0.062 m** against the 0.5 m gate on the `map_defaults.sh` Nishi-Shinjuku bundle, 400 static samples, bias 21 mm. Raw series plus the bundle digest and the build provenance of the boot.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `g2-nishi-cellc/`             | Cell C's live closed-loop certification (Task 15): closest approach **0.046 m** on the **230.5 m** pre-registered route, armed through the legacy `/autoware/engage` path. Keeps three distances apart (route polyline 230.5 m, straight-line start→goal 227.30 m, first retained sample 222.110 m ≈ 5.2 m after engage) and states that the teleport-back reset is attested, not retained.                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `task-15-adapi-engage-cellc/` | The arming-path discriminator re-observed live on cell C: AD-API `change_to_autonomous` **ACCEPTED** (`code=0`) with `control_mode` reading MANUAL, and the ego measured driving at 4.1498 m/s under it with no `/autoware/engage` publish. Refutes step 11.6's root cause; does NOT diagnose why cell A refused, and marks the route-completion and no-publish claims as attested rather than retained.                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `p3-phase0/`                  | The P3 decision gate, and the three-stage arc by which it was ruled. Probe **P1 measured 2 publishers on cell A** where 1 was pre-declared, selecting branch **(c)**; fix round 1 measured that cell A's `concatenate_data` **advertises but emits nothing** (out/in 0.995, 0 duplicate stamps), so the count criterion had not measured the double _publication_ the hypothesis names, and the task returned BLOCKED; on the owner's ruling to resume at P3/P4, cell B measured **2 emitters** (out/in 1.818, 72 duplicate stamps), **P3 PASSED** on cloud structure (`base_link`, width 6202, point_step 16, is_dense) and **P4 found no recovery** (**0.000 Hz** post-kill against the pre-declared ≥ 9.0 Hz; 4.830 Hz pre-kill). **FINAL: branch (c)** — the differential is real but is not the cause. All three stages kept in order.     |
| `b-vector-map-delivery/`      | Settles cell B's `waiting for map` blocker (Task 4b, live): `/map/vector_map` IS published (**1 305 281 B**) and a late-joining `TRANSIENT_LOCAL` subscriber receives it **9/9** (0.028–2.643 s), and `behavior_path_planner`'s own subscription is `RELIABLE / KEEP_LAST(1) / TRANSIENT_LOCAL` — the publisher's exact QoS, so **no durability mismatch**. What fails is delivery to subscribers already running at publication: the in-stack `topic_state_monitor_vector_map` first received it at +20.2 s / **never** / +11.5 s / **never** / +0.97 s / +0.05 s across six Fast-DDS `udp_only` bring-ups — **2 of 6 total failures**, reproduced standalone without CARLA. Contains the filed run's probe capture, the replica bench captures, the probe scripts and the recompute script. The planner's own receipt is labelled NOT TESTED. |
| `p4-task11-bringup/`          | Console capture for P4 Task 11's two non-scored bring-up runs (`results/A/run-015` static, `results/B-cyc/run-001` closed-loop). Supports no verdict; it exists so the console strings `PROVENANCE.md` §14 quotes are checkable — the `ros2 topic list`/`topic info -v` transcripts behind §14.2's **Publisher count: 0** argument, the step-9 flow gate, the `base_link anchor -1.39706787 m` check, the teardown summaries, and the §14.5 LiDAR-mount capture with its probe script. Retention status is stated per figure, and where a console string and a filed artifact disagree the artifact wins.                                                                                                                                                                                                                                       |
| `p4-task12-static-duel/`      | Console capture for P4 Task 12's A-vs-B-cyc **static** duel (`results/A/run-016`…`run-025`, `results/B-cyc/run-002`…`run-011`; ten interleaved pairs, all `duel_id: "A+B-cyc"`, zero exclusions). Contains no verdict and no cross-cell reading — the duel verdict is Task 16's single `duel_verdict.py` invocation. It exists so `PROVENANCE.md` §18's quoted console strings are checkable, above all §18.2's classification of the invocation-1 driver kill: the **absent** `DUEL FAIL` line, the absent `… FAILED` line, and the pair-8 pacing-floor line that is the file's last. Also carries the integrity-pass output and the exact script that produced it.                                                                                                                                                                            |

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
