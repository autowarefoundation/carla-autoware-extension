# G2 closed loop on Nishi-Shinjuku — cell C's live certification (Task 15)

`gate_g2_closed_loop.sh`'s own output for cell C's re-gate on the current engine
state: **closest approach 0.046 m** against the 1.0 m tolerance over 1198
ground-truth samples in the 120 s window — PASS. Same boot as
`g1-nishi-bundle/` (G1 PASS, max 0.062 m) and `task-15-adapi-engage-cellc/`.

`g2_summary.txt` is the gate's output. This file records the two things a reader
of the series needs that the summary does not carry.

## Which arming path this PASS was driven through

The legacy `/autoware/engage` topic, which is the only thing
`gate_g2_closed_loop.sh` publishes. See `task-15-adapi-engage-cellc/` for the
live discriminator observation — including that AD-API `change_to_autonomous` was
also tried on this boot and was ACCEPTED, which refutes the step-11.6
attribution.

## The ego was teleported back to the start before this gate ran

Stated because it is not visible in the series. Earlier on the same boot, the
AD-API discriminator observation engaged the stack and the ego drove this same
route to the goal. To measure the canonical `/autoware/engage` path over the FULL
pre-registered route rather than from wherever that drive ended, the sequence was
the repo's documented reset (`docs/e2e-report.md`, "New operational gotchas";
`arm_closed_loop.sh`'s header):

1. `arm_closed_loop.sh --disarm` — engage latches across re-arms
2. `set_transform` the ego back to the run's `--initial-pose`, zeroing target
   linear and angular velocity (host-side CARLA PythonAPI; measured landing pose
   map (81371.135, 49912.720) against the original (81371.134, 49912.721))
3. `arm_closed_loop.sh` — reseeds `/initialpose` at the ego's ground truth
   (`dist_to_target=0.01`, LOCKED), re-routes, re-suppresses the perception-off MRM
4. `gate_g2_closed_loop.sh 81571.616 50019.827`

The teleport is a reset of the vehicle's position, not a change to any gate,
threshold or harness file. `g2_dist.txt` starts at 222.110 m from the goal, which
is the full route, and is the direct check that the reset did what it claims.

## Closest approach vs terminal distance

`g2_dist.txt`: closest **0.0459 m** at sample 549/1198, terminal **4.1370 m**.
The gate's criterion is closest approach (`measure_route.py --goal-tol-m 1.0`),
which is the pre-registered M5 split — `goal_closest_approach_m` and
`goal_terminal_distance_m` are separate metrics (`benchmarks/README.md`,
"Primary-duel metric definitions"). The ego overshoots the goal by ~4.1 m and
stops there; the route was set with `allow_goal_modification: true`. The
AD-API-engaged drive earlier on the same boot terminated at 4.0989 m, so the
overshoot is a property of this route/goal pair and not of the arming path.

## Run provenance

`MAP=NishishinjukuMap WITH_AUTOWARE=1`,
`RUNNER_EXTRA_ARGS="--initial-pose -284.597 224.709 0.0 0 0 -34.187"`, sync mode,
2026-07-30/31 UTC (`g2_run: 20260731T000140Z`), goal (81571.616, 50019.827) =
`map_defaults.sh` `MAP_DEFAULT_GOAL` for this map. Preceded by a discarded warm-up
boot (`config/exclusions.md` criterion 5). Engine BuildId, fork SHA, extension
`.so` digest and Autoware image digest are recorded in
`g1-nishi-bundle/PROVENANCE.md` for this same boot.

`g2_hz.txt` is the gated-control liveness capture: `/control/command/control_cmd`
at 19.96–20.03 Hz. Per that gate's own header the rate is a precondition, not
evidence of authority — the command CONTENT for this boot is in
`task-15-adapi-engage-cellc/legacy_autoware_engage.log` (gated velocity ramping
0.25 → 1.97 → 4.17 m/s at engage) and the distance series here is what decides G2.

## Recomputing

```bash
python3 scripts/e2e/measure_route.py \
  --distances benchmarks/evidence/g2-nishi-cellc/g2_dist.txt --goal-tol-m 1.0
```

Reproduces `closest_approach=0.046 m ... PASS`.
