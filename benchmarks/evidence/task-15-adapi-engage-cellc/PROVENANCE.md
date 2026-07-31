# The AD-API engage discriminator, re-observed on cell C (Task 15)

`step-11_6-adapi-engage/` recorded AD-API `change_to_autonomous` **refusing for
60 s** on cell A and concluded the AD-API arming path does not arm, with the root
cause "localized to `/vehicle/status/control_mode` reporting MANUAL, so the
operation-mode transition manager never marks autonomous available". That
conclusion is carried in committed code and prose — `benchmarks/injector/`
`arm_and_goal.py`'s engage docstring, `benchmarks/README.md`'s control_mode
confound — and cell E's PROVISIONAL "static-only" classification rests on it
being a HARNESS-PATH property rather than an approach property.

Task 15 was asked to observe, live, which path cell C actually armed through and
whether the AD-API path was tried and refused. **It was tried and it was
ACCEPTED.** These captures are that observation. Nothing was patched: both paths
are exactly as committed, and the two drives below are the repo's own
`scripts/e2e/arm_closed_loop.sh` + `gate_g2_closed_loop.sh` recipe.

## The run these captures come from

One boot, Nishi-Shinjuku (`MAP=NishishinjukuMap WITH_AUTOWARE=1`,
`--initial-pose -284.597 224.709 0.0 0 0 -34.187`), 2026-07-30 UTC. Preceded by
a discarded warm-up boot (`config/exclusions.md` criterion 5). Same boot as
`g1-nishi-bundle/` (G1 PASS, max 0.062 m) and `g2-nishi-cellc/` (G2 PASS,
closest approach 0.046 m).

- engine BuildId `4210e602-78ec-46e1-8f2f-03fadbe036a3` (matches `pins.yaml`
  `engine.build_id`)
- extension fork `ae166d80d022f838b78f4a2daab1ca2880a7c8aa` (matches `pins.yaml`
  `extension_carla_fork.sha`)
- extension `.so` sha256
  `e8b024cf1509c80a2e7927c91b476edf38a86f800c6fd05f247db149a194204a`
- Autoware image
  `ghcr.io/autowarefoundation/autoware@sha256:405225eda6c05161bfde39cc7885511f3f4d9699d126891891420dd80c2e024a`

## What each file shows

| File                             | What it shows                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `adapi_change_to_autonomous.log` | Cell C armed (route SET, trajectory live, MRM suppressed), NOT engaged. Pre-attempt `is_autonomous_mode_available: true` with `/vehicle/status/control_mode` `mode: 4` (MANUAL). Attempt 1 returns `success=True, code=0, message=''`; attempts 2-6 return `code=60001 'The mode is the same as the current.'`. Operation mode goes `1` -> `2` and the ego is measured at `longitudinal_velocity: 4.14978551864624` m/s 20 s later. The capture contains no `/autoware/engage` publish, but it only records the calls made _in_ it -- that none occurred outside it in this window is attested, not retained (no publisher count was observed). |
| `adapi_arrival_dist.txt`         | Ego-to-goal ground-truth distance for the tail of that AD-API-engaged drive: closest approach **0.1087 m**, terminal 4.0989 m, against the pre-registered Nishi goal (81571.616, 50019.827) and the gate's 1.0 m tolerance. It is the SAME route, goal and tolerance `gate_g2_closed_loop.sh` uses.                                                                                                                                                                                                                                                                                                                                             |
| `legacy_autoware_engage.log`     | The legacy `/autoware/engage` path, sampled every ~2 s across `gate_g2_closed_loop.sh`'s own window after a disarm + teleport-back + re-arm. Pre-engage rows: `op_mode 1`, `ctrl_enabled false`, `auton_avail true`, `ctrl_mode 4`, commanded velocity `0.0`. At engage: `op_mode 2`, `ctrl_enabled true`, `ctrl_mode 4 -> 1`, commanded velocity ramping `0.25 -> 1.97 -> 4.17` m/s, then `0.0` on arrival. The last column is `/control/command/control_cmd`'s COMMANDED velocity, NOT measured ego motion -- nothing in this file measures ego speed.                                                                                        |

## What this establishes, stated no wider than the evidence

1. **The AD-API path armed cell C.** Fully retained, and sufficient on its own:
   `change_to_autonomous` was accepted on the first call
   (`adapi_change_to_autonomous.log:23`, `success=True, code=0, message=''`), the
   retries then reported the mode as already current (`code=60001`, five times),
   `/api/operation_mode/state` went `mode: 1` → `mode: 2` with
   `is_autoware_control_enabled` `false` → `true` (`:13`, `:14` vs `:44`, `:45`),
   and `/vehicle/status/velocity_status` measured the ego at
   **4.14978551864624 m/s** under that mode 20 s later (`:58`). So "the AD-API
   arming path does not arm" is FALSE as a cell-independent statement — that
   conclusion needs nothing beyond the lines just cited.
   **ATTESTED, NOT RETAINED, and not load-bearing above:** that it drove the
   _full_ pre-registered route, and that _no_ `/autoware/engage` publish occurred
   anywhere in the sequence. The retained distance series starts 12.827 m out
   (see "What is NOT established"), and nothing observed the topic's publisher
   count or subscriber traffic — the no-publish claim rests on the operator
   having issued no such publish in that window, which is prose. Neither is
   needed for the refutation; both are recorded so the stronger phrasing an
   earlier revision used is not read as measured.
2. **`control_mode == MANUAL` is not what blocks the transition.**
   `/vehicle/status/control_mode` read `mode: 4` (MANUAL) in exactly the
   pre-engage state where the transition was accepted. `legacy_autoware_engage.log`
   shows why: `ctrl_mode` FOLLOWS the engage (`4` -> `1` at engage), so it is an
   output of arming, not a precondition of it. Step 11.6's root-cause attribution
   is therefore refuted, and is left in that directory with this file naming what
   refutes it.
3. **`is_autonomous_mode_available` is not a static capability of the stack.**
   Split deliberately into what is measured and what is inferred, because an
   earlier revision of this file asserted the mechanism as measured and the
   artifacts do not carry it.

   **MEASURED, and it is what does all the work here.** The flag takes BOTH
   values on cell C within one boot:
   - `true` in the pre-engage **armed and stopped** state
     (`adapi_change_to_autonomous.log:17`), and
   - `true` again at `mode: 2` while stopped after arrival
     (`legacy_autoware_engage.log:20`), against
   - `false` while the stack is driving (`adapi_change_to_autonomous.log:48`,
     `legacy_autoware_engage.log:6`).

   That pair alone is the conclusion this directory needs: a flag that reads
   `true` on cell C in exactly the state step 11.6 inferred it must have been
   `false` in on cell A cannot be a static property of the AD-API layer. So step
   11.6's decisive detail — `is_autonomous_mode_available: false` **while
   driving** — is a value this stack also shows while driving, and it therefore
   **establishes nothing about cell A's PRE-ENGAGE state**.

   **DERIVED, not measured: the transition point and the mechanism.** The
   `gated_vel_mps` column of `legacy_autoware_engage.log` is the **COMMANDED**
   velocity from `/control/command/control_cmd`, not measured ego motion, and the
   rows are 2 s apart. The flip is bounded to one interval and no closer: at
   `:5` (`00:01:45Z`, commanded 0.25 m/s) the flag is still **`true`**; at `:6`
   (`00:01:50Z`, commanded 1.97 m/s) it is `false`. Nothing retained measures ego
   speed inside that ~5 s window, and the command ramp implies motion had already
   begun by `:5` — so "flips false from the first moving sample", as an earlier
   revision put it, names a quantity these artifacts do not record. Calling the
   flag "engage-availability" is therefore a 2 s-sampled correlation with
   commanded velocity, not a measured mechanism.

   **And a competing explanation is not excluded — it is candidate 1 below.** The
   transition manager's speed-match / deviation check, named in "What is NOT
   established" as the leading candidate for cell A's refusal, predicts exactly
   these flips: a check that stops being satisfiable once the ego is moving would
   drive this flag `false` at precisely this point. So this observation must NOT
   be read as evidence against that candidate; the two are consistent, and
   distinguishing them needs the transition manager's own availability inputs,
   which were not captured.

4. **Which path cell C's certified G2 armed through: the legacy
   `/autoware/engage` topic.** `g2-nishi-cellc/`'s PASS is `gate_g2_closed_loop.sh`
   output, and that script publishes `/autoware/engage {engage: true}` and
   nothing else. The AD-API drive is a separate, earlier drive on the same boot.

## What is NOT established here, and what would settle it

**Why cell A refused is not diagnosed.** Cell A was not re-run; nothing here
observes Town10. Two candidate explanations are consistent with both records and
neither is tested:

- `operation_mode_transition_manager`'s engage-availability check (lateral/yaw
  deviation from the trajectory, and the speed match between ego and the
  trajectory's leading point). Cell C seeds ON the lanelet centreline and holds a
  0.062 m NDT lock; Town10's measured lock is stably biased ~0.5 m with metres of
  along-track slack (`cells.yaml` cell A, `docs/running-e2e.md`). A deviation
  gate would separate those two rigs without any approach difference.
- A per-run state difference in cell A's step-11.6 session unrelated to the map.

The test: repeat this capture on cell A and record the PRE-ENGAGE
`is_autonomous_mode_available` plus the transition manager's own
availability inputs. That is deliberately NOT done here — Task 15's brief scopes
this to observing and recording, and cell E's reclassification is the owner's
call, not this directory's.

**The AD-API drive's full-route series is not retained.**
`adapi_arrival_dist.txt` starts 12.827 m from the goal because the host-side
collector was started after that drive was already underway — the arming
sequence itself was what the capture was aimed at. The retained half is the
arrival only — everything before its final 12.827 m is not recomputable, and no
derived "distance covered" figure is asserted for it, since the artifact bounds
the retained part and not the missing part. The canonical
series for this boot is `g2-nishi-cellc/g2_dist.txt`, which itself opens at
222.110 m — ~5.2 m after engage rather than at the start pose, for the reason
that directory's `PROVENANCE.md` records. The pre-registered route is **230.5 m**
(`benchmarks/config/routes/NishishinjukuMap.yaml`'s own recorded total length);
neither 222.110 m nor the 227.30 m straight-line separation is that number, and
all three are kept apart there.

**`legacy_autoware_engage.log`'s gated velocity is a ~2 s sample, not a
per-message distribution.** It shows command CONTENT (which is the point step
11.6 makes about rate not being sufficient), at 34 samples rather than every
message. `g2-nishi-cellc/g2_hz.txt` carries the rate.

## Recomputing

```bash
python3 scripts/e2e/measure_route.py \
  --distances benchmarks/evidence/task-15-adapi-engage-cellc/adapi_arrival_dist.txt \
  --goal-tol-m 1.0
```

Reproduces `closest_approach=0.109 m ... PASS`. The two `.log` files are verbatim
console captures and carry no derived numbers.
