# G2 closed loop on Nishi-Shinjuku — cell C's live certification (Task 15)

`gate_g2_closed_loop.sh`'s own output for cell C's re-gate on the current engine
state: **closest approach 0.046 m** against the 1.0 m tolerance over 1198
ground-truth samples in the 120 s window — PASS. Same boot as
`g1-nishi-bundle/` (G1 PASS, max 0.062 m) and `task-15-adapi-engage-cellc/`.

`g2_summary.txt` is the gate's output. This file records what a reader of the
series needs and the summary does not carry: which arming path drove the PASS, the
teleport-back reset and its retention status, the three distances that must not be
conflated, and the closest-vs-terminal split.

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
threshold or harness file.

### What checks the reset — and the three distances that must not be conflated

An earlier revision of this file claimed `g2_dist.txt`'s first sample "is the full
route, and is the direct check that the reset did what it claims". **Both halves
were wrong**, and they are corrected here rather than quietly replaced, because
this is exactly the kind of conflation that propagates:

| Quantity                                         | Value         | Source                                                                                                                                    |
| ------------------------------------------------ | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Route POLYLINE length (the pre-registered route) | **230.5 m**   | `benchmarks/config/routes/NishishinjukuMap.yaml`'s own recorded `total length: 230.5 m`; recomputes to 230.54 m from that file's polyline |
| Straight-line start → goal                       | **227.30 m**  | same file records 227.3 m for polyline[0] → goal; 227.298 m from the landing pose in step 2 above                                         |
| First RETAINED sample in `g2_dist.txt`           | **222.110 m** | this directory                                                                                                                            |

So the series begins about **5.2 m after engage**, not at the start pose — and it
structurally cannot begin there: `scripts/e2e/gate_g2_closed_loop.sh` publishes
`/autoware/engage` and then spends up to 10 s inside
`timeout 10 ros2 topic hz /control/command/control_cmd` before `collect_gt` is
started. The series' own opening confirms it: consecutive deltas
0.2099 / 0.2139 / 0.2179 / 0.2219 m at the collector's 10 Hz sampling, i.e. the
ego is already at **2.10 m/s and accelerating in sample 0**.

**The reset therefore rests on the landing pose recorded in step 2, which is
operator-attested prose and is NOT retained as an artifact** — no host-side
capture of the `set_transform` result was written to a file. What the series
supports on its own is weaker and still sufficient for the gate: the drive was
under way at least 222.110 m from the goal, which is inconsistent with a run
starting from where the previous AD-API drive ended (4.099 m out).

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
`task-15-adapi-engage-cellc/legacy_autoware_engage.log` (COMMANDED velocity
ramping 0.25 → 1.97 → 4.17 m/s at engage — that column is
`/control/command/control_cmd`'s command, not measured ego motion), and the
distance series here is what decides G2.

## Recomputing

```bash
python3 scripts/e2e/measure_route.py \
  --distances benchmarks/evidence/g2-nishi-cellc/g2_dist.txt --goal-tol-m 1.0
```

Reproduces `closest_approach=0.046 m ... PASS`.
