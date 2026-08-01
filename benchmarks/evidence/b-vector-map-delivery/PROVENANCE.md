# Cell B `waiting for map` — where `/map/vector_map` actually stops (live, 2026-08-01)

Targeted live diagnostic for the blocker `PROVENANCE.md` §7.1 named: cell B's
`behavior_path_planner` logged `waiting for map` × 11 over 53.3 s, to teardown,
in `benchmarks/results/B/run-028`, after the route had reached it. Cell B has
attempted closed-loop 13 times across two sessions and has never armed, so the
A-vs-B closed-loop duel depends on this answer.

The question §7.1 handed over was: **does `map_loader` publish the lanelet map
at all, and does its `transient_local` sample reach a subscriber that joins
late?** `/map/vector_map` is not in `config/observer_topics/B.yaml`, so no filed
run in this campaign could answer it from data on disk.

## Verdict

**The map is published, and it is delivered — but not reliably to the
subscribers that are already running when it is published.** Of the four
candidate explanations the diagnostic was scoped against:

| candidate                                                                      | ruling                                                        |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------- |
| (1) the map is never published — a bring-up gap in `cells/tier4_autoware.sh`   | **REFUTED**                                                   |
| (2) published but not delivered — QoS/ordering                                 | **SUPPORTED**, with the QoS half refuted: see below           |
| (3) delivered, and the planner blocks anyway — `waiting for map` is misleading | **REFUTED** for the two endpoints that could be read directly |
| (4) something else                                                             | not needed                                                    |

Refined statement of (2), which is what the measurements support:

> `/map/lanelet2_map_loader` publishes a single 1 305 281-byte `LaneletMapBin`
> from its constructor with `RELIABLE / KEEP_LAST(1) / TRANSIENT_LOCAL`. Every
> subscriber in the stack, `behavior_path_planner` included, requests exactly
> that QoS — **there is no durability mismatch**. A dedicated probe subscriber
> with that QoS received the 1 305 281 bytes **9 times out of 9** (7 joining
> after the writer, 0.028–2.643 s; 2 joining before it, at publication). An
> **in-stack subscriber that already exists when the writer publishes** gets it
> in 4 of 6 stock-profile observations (+0.05 s to +23.2 s) and **never** in the
> other 2 (still `NotReceived` at +98.2 s and +113.35 s). The failure is in the
> Fast-DDS `transient_local` historical-delivery path for this large sample,
> under the `rmw_fastrtps_cpp` + `udp_only.xml` transport that **cell B alone
> runs**, and it is nondeterministic across otherwise identical bring-ups.

`behavior_path_planner` is one of those already-running subscribers, and
`run-028` is a run in which it drew the losing outcome.

## The run this task filed

`benchmarks/results/B/run-030` — cell B, `--arm static`, **not excluded**,
`duel_admissible: false` (no `--duel`; a bring-up/diagnostic run). Preflight
loadavg 0.36, governor `powersave` (recorded, unchanged), engine BuildId
`4210e602-78ec-46e1-8f2f-03fadbe036a3`, bundle `town10_pcd_regen`, image
`ghcr.io/autowarefoundation/autoware@sha256:5c22369a…3ae8ee`, transport
`rmw_fastrtps_cpp` / shm off / `dds_profile_sha256`
`9886f7445306632b168763acc2c96a9f643329eb5d1ccf2da77e061466565098`.

`quality.json`: `gate_pass=false`, `ndt_rate_ratio=0.303`,
`pose_err_max_m=0.054`, `reasons=["ndt rate ratio 0.30 < 0.9"]` — the
**registered** M5 rate confound (§4.1, §6), expected on B, neither a smoke
failure nor excludable. Nothing else failed.

**Why a static run can answer a closed-loop question, and what it cannot.** The
map is published within a second of the planning container instantiating
`BehaviorPathPlannerNode` — 0.632 s on `run-028` (495.109 → 495.741) and 0.420 s
on `run-030` (1785601089.296 → 1785601089.716) — so the publish and the
delivery attempt are complete long before either arm diverges, and the probes
below read them directly. What a static run cannot do is make the planner
_report_ on the map — see "The planner never reaches its own map check on a
static arm".

## Probes and raw results

The capture files are tracked beside this document with every command echoed
before its output:

- `probe-inrun.log` — the probes run against `B/run-030`'s own live stack.
- `replica-bench.log`, `replica-bench-pass2.log` — the standalone replica bench
  (below), which exists because a cell-B static stack lives only ~100 s.

They are the tool output as captured, with **one** transformation, disclosed
because the rest of this document leans on them: the repo's
`trailing-whitespace` pre-commit hook trimmed line-end spaces in
`replica-bench.log` (`benchmarks/evidence/` is not excluded from the mutating
hooks the way `benchmarks/results/` is — see `.pre-commit-config.yaml`). No
line, value or ordering was changed.

### 1. Is it advertised, and by whom, with what QoS

Publisher, read off the live graph (`ros2 topic info -v --no-daemon
/map/vector_map`):

```text
Node name: lanelet2_map_loader
Node namespace: /map
Topic type: autoware_map_msgs/msg/LaneletMapBin
Endpoint type: PUBLISHER
QoS profile:
  Reliability: RELIABLE
  History (Depth): KEEP_LAST (1)
  Durability: TRANSIENT_LOCAL
```

16 subscription endpoints were enumerated on the same topic. **Every one of
them is `RELIABLE` + `TRANSIENT_LOCAL`** — `mission_planner`,
`behavior_path_planner`, `behavior_velocity_planner`, `motion_velocity_planner`,
`scenario_selector`, `costmap_generator`, `planning_validator`,
`planning_evaluator`, `control_evaluator`, `lane_departure_checker_node`,
`remaining_distance_time_calculator`, `manual_lane_change_handler`,
`lanelet2_map_visualization`, `vector_map_tf_generator`,
`topic_state_monitor_vector_map`.

**Publisher/subscriber counts printed by `ros2 topic info` are NOT usable as
evidence here, and are not used as such.** On the same stack, seconds apart, the
CLI reported `Publisher count: 0 / Subscription count: 15`, then `0 / 3`, then
(under the cyclonedds control) `1 / 16`. `ros2 topic info --no-daemon` starts a
fresh participant and waits a fixed, short time for discovery; the numbers are a
snapshot of _that participant's_ discovery progress, not of the graph. The
delivery findings below all rest on a subscriber that actually received bytes,
never on a count.

### 2. Does a sample reach a LATE-joining subscriber

`map_probe.py` creates one subscription with the planner's QoS
(`RELIABLE / KEEP_LAST(1) / TRANSIENT_LOCAL`), spins until a message arrives or
the budget expires, and prints the payload length.

| where                                        | when created                          | result                                   |
| -------------------------------------------- | ------------------------------------- | ---------------------------------------- |
| `B/run-030` live stack, stock profile        | late                                  | RECEIVED `t_first=0.173 s`, 1 305 281 B  |
| `B/run-030` live stack, 16 MiB probe buffers | late                                  | RECEIVED `t_first=0.951 s`, 1 305 281 B  |
| replica V1                                   | late                                  | RECEIVED `t_first=0.807 s`, 1 305 281 B  |
| replica V1b                                  | late                                  | RECEIVED `t_first=0.287 s`, 1 305 281 B  |
| replica V2 (cyclonedds)                      | late                                  | RECEIVED `t_first=0.028 s`, 1 305 281 B  |
| replica pass 2, W-stock                      | late                                  | RECEIVED `t_first=2.643 s`, 1 305 281 B  |
| replica pass 2, W-16 MiB                     | late                                  | RECEIVED `t_first=0.107 s`, 1 305 281 B  |
| replica pass 2, W-stock                      | **early** (created before the launch) | RECEIVED `t_first=11.446 s`, 1 305 281 B |
| replica pass 2, W-16 MiB                     | **early**                             | RECEIVED `t_first=11.161 s`, 1 305 281 B |

The two `early` rows are the same probe started ~4 s _before_ `ros2 launch`, so
its subscription existed before `map_loader` did; `t_first` is measured from the
probe's own start and the map is published ~11 s into the launch, so both
received the sample essentially **at** publication. A dedicated, quiet probe
process never failed, whichever side of the writer it was created on — the
failures are all on in-stack subscribers (next section).

`ros2 topic echo --once --no-daemon --no-arr` on `B/run-030`'s live stack
returned the message as well, both with `--qos-durability transient_local
--qos-reliability reliable` and with the CLI's default QoS:

```text
header:
  stamp:
    sec: 16
    nanosec: 715411101
  frame_id: map
version_map_format: ''
version_map: ''
name_map: ''
data: '<sequence type: uint8, length: 1305281>'
```

**Durability contrast, the control that makes the above mean something.** A
deliberately `VOLATILE` late subscriber received **nothing**, 3/3 (10 s, 15 s,
15 s budgets) — confirming there is no re-publication and that what the
transient_local subscribers get is the _retained_ sample:

```text
PROBE topic=/map/vector_map durability=volatile result=TIMEOUT t_first_s=- data_bytes=- wall_waited_s=15.04
```

So **candidate (1) is refuted** (`map.lanelet2_map_loader: Succeeded to load
lanelet2_map. Map is published.` appears in every run, and the bytes are
readable), and **the "planner joins after a volatile publication" form of
candidate (2) is refuted** (the planner's subscription is `TRANSIENT_LOCAL`, and
transient_local late joiners are served).

### 3. What the planner subscribes to, and with what QoS

```text
$ ros2 node info /planning/scenario_planning/lane_driving/behavior_planning/behavior_path_planner
  Subscribers:
    /map/vector_map: autoware_map_msgs/msg/LaneletMapBin
...
Node name: behavior_path_planner
Node namespace: /planning/scenario_planning/lane_driving/behavior_planning
Endpoint type: SUBSCRIPTION
QoS profile:
  Reliability: RELIABLE
  History (Depth): KEEP_LAST (1)
  Durability: TRANSIENT_LOCAL
```

An **exact** match with the publisher on all three axes. **There is no QoS
durability mismatch on `/map/vector_map`.**

**Where this reading was taken, stated rather than glossed.** Under the
`rmw_fastrtps_cpp` + `udp_only.xml` transport the ros2 CLI could not enumerate
the node at all (`Unable to find node '…/behavior_path_planner'`, three separate
attempts) because its own participant's discovery was incomplete; the QoS above
was read on the **cyclonedds control variant** of the replica, which is the same
image and the same node binary. The QoS is declared in the node's own code and
is RMW-independent, so it applies to cell B — but that last step is an
inference, not a second measurement, and is labelled as one.

### 4. The subscribers that were already running when the map was published

`/system/topic_state_monitor_vector_map` is an in-stack subscriber with the same
`RELIABLE / TRANSIENT_LOCAL` QoS, loaded well before `map_loader` publishes. Its
verdict is readable two ways: live off `/diagnostics` (`diag_probe.py`,
`diag_watch.py`), and after the fact from any filed launch log, because
`logging_diag_graph` prints the not-OK subtree every ~3 s
(`monitor_convergence.py`, which recomputes the filed numbers below from the
tracked logs).

| bring-up                               | transport                            | outcome for the early-joining in-stack subscriber                        |
| -------------------------------------- | ------------------------------------ | ------------------------------------------------------------------------ |
| `B/run-028` (filed, closed-loop)       | fastrtps `udp_only`                  | OK between **+20.2 s** and **+23.2 s**                                   |
| `B/run-029` (filed, static)            | fastrtps `udp_only`                  | **NEVER** — still not-OK at **+98.2 s**, the last block of the run       |
| `B/run-030` (filed, static, this task) | fastrtps `udp_only`                  | OK between **+11.5 s** and **+14.6 s**                                   |
| replica V1                             | fastrtps `udp_only`                  | **NEVER** — `status=NotReceived last_message_time=0.00` at **+113.35 s** |
| replica V1b                            | fastrtps `udp_only`                  | OK at **+0.97 s**                                                        |
| replica pass 2, W-stock                | fastrtps `udp_only`                  | OK at **+0.05 s**                                                        |
| replica pass 2, W-16 MiB               | fastrtps `udp_only` + 16 MiB buffers | OK at **+0.11 s**                                                        |
| replica V2                             | **cyclonedds**                       | OK at **+0.24 s**                                                        |

(`+` is measured from the `Succeeded to load lanelet2_map. Map is published.`
line. For the three filed runs the granularity is the ~3 s diag-graph print
period, so those are bounds, not receipt timestamps; the replica rows are
`last_message_time` read off `/diagnostics` directly, against the publish
timestamps 1785601421.539 / 1785601556.127 / 1785601689.737 / 1785601841.637 /
1785601985.520.)

**Two of six** Fast-DDS `udp_only` bring-ups never delivered the map to that
subscriber at all. `V1` and `V1b` are consecutive runs of the **same script with
the same arguments**, two minutes apart, and they differ by "never in 113 s"
versus "0.97 s". That is the nondeterminism, reproduced standalone, without
CARLA and without the harness.

The same pattern shows on the other large map topic. `/map/pointcloud_map` (the
30.4 MB cloud) was `status=NotReceived` in 2 of 5 observations (`B/run-030`'s
live stack and replica V1 — the same two bring-ups whose `vector_map` also
failed or lagged) and `status=OK` in the other 3 — recorded as a corroborating
observation of the same delivery path. **It is NOT offered as an explanation of
anything else**: cell B's NDT rate deficit is a separately registered confound
whose ruling (branch (c)) this document does not touch.

### 5. The planner never reaches its own map check on a static arm

`behavior_path_planner`'s readiness log is an ordered sequence, and the order is
visible in the filed logs rather than assumed:

| run                            | arm         | `waiting for scenario_topic` | `waiting for route` | `waiting for map` |
| ------------------------------ | ----------- | ---------------------------- | ------------------- | ----------------- |
| `B/run-028`                    | closed-loop | 3                            | 2                   | **11**            |
| `B/run-029`                    | static      | 17                           | 0                   | 0                 |
| `B/run-030`                    | static      | 16                           | 0                   | 0                 |
| replica V1 / V2 (no simulator) | —           | 21 / 22                      | 0                   | 0                 |

A static arm sets no route, so no scenario is selected, so the planner stops at
the _first_ check and never evaluates the map. **This is why cell B's static
runs file cleanly while every closed-loop attempt dies**, and it is also why
this task's static run could not observe the planner's map state directly. The
map question was answered instead through subscribers that can be read at any
time.

### 6. The planner's own report, across all six arm failures — the NOT TESTED gap, closed from filed data

**AMENDMENT (2026-08-01, owner ruling to apply the fix).** The gap the section
below originally left open — "`behavior_path_planner`'s own receipt of the map
was never observed directly" — turns out to be closable **with no new run**,
and the answer changes the picture. `isDataReady()` emits one throttled
`waiting for <input>` line for the FIRST input it finds missing, in a fixed
order, so the planner's **last** such line names what it was still missing,
from the node itself rather than from a proxy endpoint. `planner_readiness.py`,
tracked here, recomputes this from any run's launch log.

Run over every cell-B run that reached the arm and failed it — the six
`gate:arm-failed` runs, which are 6 of the 13 closed-loop attempts (the other
seven are 6 `crash:cell-launch` + 1 `crash:collect_gt` and never reached the
arm):

| run       | planner blocked on | its last readiness line | counts                                |
| --------- | ------------------ | ----------------------- | ------------------------------------- |
| `run-008` | **map**            | −2.2 s (teardown)       | scenario 6, route 3, **map 8**        |
| `run-009` | route              | −49.4 s                 | scenario 3, route 4                   |
| `run-010` | route              | −9.9 s                  | scenario 4, route 12                  |
| `run-011` | route              | −2.0 s (teardown)       | scenario 11, route 4                  |
| `run-012` | **operation_mode** | −5.6 s (teardown)       | scenario 4, route 4, operation_mode 7 |
| `run-028` | **map**            | −2.2 s (teardown)       | scenario 3, route 2, **map 11**       |

**This reconciles an arithmetic that did not work.** A ~1-in-3 delivery defect
predicts roughly 4 of 6 arm attempts succeeding; all six failed, which under a
single map-only cause has probability ≈ 0.14 %. The table says why: **the map is
the blocker in 2 of the 6, not 6 of 6.**

- **2 of 6 (`run-008`, `run-028`) blocked on the map**, to teardown — the
  planner's own statement that its map pointer was null with scenario and route
  both satisfied. That is this document's defect, confirmed **at the planner**
  rather than inferred from `topic_state_monitor_vector_map`.
- **3 of 6 (`run-009`, `run-010`, `run-011`) blocked on the ROUTE**, never
  reaching the map check. `run-011` also failed the route service itself
  (`set_route_points: no response (spin timed out)`, its `arm.log`).
- **1 of 6 (`run-012`) got PAST the map** and blocked on `operation_mode`.

So the planner does **not** fail on the map at a higher rate than the monitor
does — it fails on _different inputs_ in different runs, and the map is one of
at least three. All six end with `/planning/trajectory` not-OK and
`Waiting for trajectory data` up to teardown, so no trajectory ever formed in
any of them; they simply did not stall in the same place.

**A pattern worth naming, and NOT ESTABLISHED as a shared cause.**
`/map/vector_map`, `/planning/mission_planning/route` and
`/system/operation_mode/state` are all latched (`TRANSIENT_LOCAL`) topics
published once or rarely, and all three appear here as inputs an already-running
subscriber did not get. §7.4's cell-E finding — the route published by
`mission_planner` never reaching `behavior_path_planner` — is the same shape on
a **different** transport (cyclonedds). That is suggestive of one defect class
rather than three, and it is recorded as a **hypothesis with a named next
probe** (repeat this task's delivery measurement against the route and
`operation_mode` topics), not as a finding: nothing here measured either topic's
delivery.

**Consequence for the fix, stated before it was validated:** it addresses 2 of
the 6 historical arm failures. It is necessary, and on this evidence it is not
sufficient.

## What was NOT tested

Stated explicitly, because this campaign has three times had a claim outrun its
measurement:

- ~~**`behavior_path_planner`'s own receipt of the map was never observed
  directly.**~~ **CLOSED by section 6 above**, from filed data: the planner's
  own `waiting for map` line is its report that the map pointer is null, and it
  names the map in 2 of the 6 arm failures. The original entry read: "On the
  static arm it never reaches the check, and under cell B's transport the ros2
  CLI could not enumerate the node to introspect it. The planner's failure in
  `run-028` is attributed to the mechanism above by two steps of inference." The
  inference was sound for `run-028` and `run-008`; what it missed is that four
  other runs failed elsewhere entirely.
- **Whether the fix makes cell B arm** — see the validation section below.
- **Whether cyclonedds is immune.** n = 1. One clean bring-up is not a rate.
- **The 16 MiB socket-buffer variant proves nothing about the fix.** It was run
  once (monitor OK at +0.11 s) and the stock configuration _also_ succeeded on
  its own single run in the same pass (+0.05 s). Against a failure that appears
  in 2 of 6 bring-ups, one passing run has no power. The buffer hypothesis is
  neither supported nor refuted here.
- **The mechanism inside Fast-DDS** — whether fragments of the 1.3 MB sample are
  lost on the busy container's shared UDP receive socket, or whether the
  writer's historical delivery on match never completes — is **not established**.
  Both are consistent with everything measured. What _is_ established is the
  externally visible behaviour and the configuration it is confined to.

## How the measurements were made

### In-run probes

`probe.sh` waits for the harness's `autoware` container, copies the probe
scripts in, and runs an ordered sequence sized to the ~100 s a cell-B static
stack lives (measured: `B/run-028` 99.9 s, `B/run-029` 102.8 s of launch-log
span). It only `docker exec`s probe processes; it writes nothing into the run
directory and modifies no harness file.

### Replica bench

Because ~100 s is too short to settle DDS discovery, dump every endpoint's QoS
and run a transport comparison, `replica.sh` and `replica2.sh` bring up the
**same image, same map bundle and the same `ros2 launch` line** as
`benchmarks/cells/tier4_autoware.sh`, under the container name `aw-replica`,
with no CARLA and no harness involvement. Two deviations, both stated in the
scripts' own headers:

1. no simulator, so `use_sim_time:=false` — with sim time on and no `/clock`
   publisher every timer and throttled log in the stack would be frozen at
   t = 0 and nothing would be observable; the map publish/deliver path does not
   read the clock;
2. the container name.

Image digest, RMW, DDS profile, map bundle, sensor/vehicle model,
`simulator_type`, and the `perception`/`rviz`/`launch_vehicle_interface` flags
are the cell's. The bench ran only after `B/run-030` had fully torn down; never
two stacks at once.

### Files kept here

| file                                                              | what it is                                                                               |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `map_probe.py`                                                    | one late- or early-joining subscriber; prints receipt time and payload length            |
| `diag_probe.py`                                                   | point-in-time `/diagnostics` read of the map topic monitors                              |
| `diag_watch.py`                                                   | the same, watched from t = 0, one line per state change                                  |
| `monitor_convergence.py`                                          | recomputes the filed-run rows of the table above from tracked launch logs                |
| `probe.sh`                                                        | the in-run probe driver                                                                  |
| `planner_readiness.py`                                            | which readiness input the planner was still missing when a run ended                     |
| `smoke_helper.sh`, `smoke-republisher.log`                        | the applied fix exercised against two replica bring-ups, one of them failing             |
| `cyclone_probe.sh`, `cyclone-probe-driver.log`                    | the cyclonedds bounding probe (`B/run-033`): exact command, transport in force, preamble |
| `replica.sh`, `replica2.sh`                                       | the replica bench, passes 1 and 2                                                        |
| `udp_big.xml`                                                     | probe-only 16 MiB-socket-buffer variant of `observer/config/udp_only.xml`                |
| `probe-inrun.log`, `replica-bench.log`, `replica-bench-pass2.log` | raw captures                                                                             |

These are retained evidence, not maintained code: they are the exact scripts
that produced the figures above (`benchmarks/evidence/**` is excluded from
`ruff` for this reason — see `.pre-commit-config.yaml`).

## The fix — PROPOSED here, then APPLIED on the owner's ruling

**Status: APPLIED** (2026-08-01, owner ruling "apply the fix, validate with 3
consecutive cell-B closed-loop runs"). It is a **harness-injected workaround for
a measured transport defect** — not a gate adjustment, not a threshold change,
and not a DDS profile edit. What landed:

| piece                                           | where                                          |
| ----------------------------------------------- | ---------------------------------------------- |
| the re-publish + verify node                    | `benchmarks/injector/republish_vector_map.py`  |
| the closed-loop-only call site                  | `benchmarks/cells/tier4_autoware.sh` section 5 |
| behavioural pins (both arms, executed for real) | `tests/benchmarks/test_vector_map_gate.py`     |
| the per-run record it files                     | `<run>/vector-map-delivery.json`               |

`transport.dds_profile_sha256` is unchanged, so cell B's already-filed runs stay
transport-comparable, and the static arm reaches no new step — pinned by a test
that asserts the recorder file does not exist, i.e. that no container command
ran at all, rather than that a harmless one did.

### The fix, exercised on the FAILING path before any live run was spent on it

`smoke_helper.sh` ran the real node against two consecutive replica bring-ups
(same image, bundle, launch line and cell-B transport, no CARLA, no harness);
raw capture in `smoke-republisher.log`. The second bring-up landed on the
failing side of the defect, which is the case that matters:

|                                | bring-up 1                              | bring-up 2                                                    |
| ------------------------------ | --------------------------------------- | ------------------------------------------------------------- |
| `pre_republish_delivered`      | **true** (monitor already had it, +3 s) | **false** — `NotReceived`, `last_message_time 0.00`, at +40 s |
| captured retained sample       | 1 305 281 B in 6.0 s                    | 1 305 281 B in 6.0 s                                          |
| matched subscribers at publish | 17, settled                             | 17, settled                                                   |
| attempt 1                      | verified in 0.005 s                     | **NOT verified** after 60.013 s                               |
| attempt 2                      | —                                       | **NOT verified** after 60.015 s                               |
| attempt 3                      | —                                       | **verified in 0.303 s**                                       |
| exit                           | 0                                       | 0                                                             |

**So the re-publish does rescue a bring-up that had already failed** — bring-up 2
went from `NotReceived` to `OK` and the gate passed. Two things in that column
are worth stating rather than rounding away:

- **The retry is load-bearing, not decoration.** Two publications reached
  nothing; only the third took. `--attempts 3` was chosen before this ran, and
  on this evidence a single-shot re-publish would have failed the gate.
- **17 matched subscribers, and the first two publications still did not
  arrive.** Matching is therefore _not_ sufficient for delivery here, which
  sharpens the honest limit already recorded above: waiting for matching makes
  the re-publish work most of the time, not always. The corresponding worst
  case is a run that needs a 4th attempt, and that run fails the gate loudly by
  design rather than proceeding to a silent unarmed teardown.

### Validation: STOPPED at run 1, and what run 1 proved instead

`B/run-031` (closed-loop, non-duel) **failed the gate**, exit 5 — captured
1 305 281 B in 6.0 s, 16 matched subscribers, matching settled,
`pre_republish_delivered false`, then three re-publish attempts each waiting
60 s with `topic_state_monitor_vector_map` staying `NotReceived`. Excluded
`crash:cell-launch` (criterion 1). Per the owner's ruling the fix was not
iterated on and no fourth run was taken.

**The run's log says the re-publish was delivered anyway** — just not to the
endpoint the gate reads. `run-031/tier4-autoware.log`:

| line              | t                     | event                                                                                                   |
| ----------------- | --------------------- | ------------------------------------------------------------------------------------------------------- |
| `:347`            | 1785605088.396        | `Succeeded to load lanelet2_map. Map is published.`                                                     |
| `:398` / `:419`   | 1785605088.641 / .790 | `lanelet2_map_visualization: Map is loaded` / `vector_map_tf_generator: broadcast static tf` (original) |
| `:1123` / `:1128` | 1785605117.126 / .143 | both again — **attempt 1 delivered**                                                                    |
| `:2149` / `:2155` | 1785605177.156 / .176 | both again — **attempt 2 delivered**                                                                    |
| `:3147` / `:3152` | 1785605237.147 / .159 | both again — **attempt 3 delivered**                                                                    |
| `:545`…`:4343`    | —                     | `topic_rate_check/vector_map ERROR` in **71 of 72** diag blocks                                         |

The helper runs in its own process, so each of those three is an inter-process
delivery that landed. **The publication mechanism works; the verification
endpoint is what never received.** Combined with `run-028` (monitor OK at
+23.2 s, planner still blocked at +95 s), the two runs bracket the same point
from opposite sides: `topic_state_monitor_vector_map` is an independent draw,
not a proxy for the planner.

**So the gate as built is over-strict**, and it aborts the bring-up _before_ a
route exists, which is the only condition under which the planner reports on the
map — `run-031`'s planner logged `waiting for scenario_topic` 38 times and
nothing else. **NOT TESTED: whether `run-031` would have armed.**

Across the two failing bring-ups observed so far the re-publish flipped the
monitor **1 of 2** (replica smoke: rescued on attempt 3; `run-031`: not rescued
in 3). n = 2 is not a rate.

The original proposal, kept verbatim because the applied form follows it:

**Recommended minimal fix — a re-publish-and-verify bring-up step**, added to
`cells/tier4_autoware.sh` after the Autoware launch and before the arm:

1. subscribe `transient_local` to `/map/vector_map` and capture the retained
   sample (measured to work 9/9 from a dedicated probe process);
2. create a `transient_local` publisher on the same topic, wait until it has
   matched subscribers and a short settle has elapsed, then publish the captured
   sample once;
3. poll `/diagnostics` until `topic_state_monitor_vector_map` reports OK, and
   fail the bring-up loudly with a named message otherwise.

Why this shape:

- it targets the only path that was measured failing — historical delivery to
  already-running subscribers — by turning the map into ordinary live data,
  which is the path the rest of the stack uses successfully at 20 Hz;
- it does **not** touch `benchmarks/observer/config/udp_only.xml`, so
  `dds_profile_sha256` stays byte-identical and cell B's filed runs remain
  transport-comparable. Editing that file would change the recorded transport of
  every future B run and is also shared with the observer container;
- a second publisher on a stock topic is already precedented and documented in
  this same cell (the single-LiDAR concat relay), so the disclosure pattern
  exists.

Honest limits of it, which the operator should weigh:

- step 3 gates on `topic_state_monitor_vector_map`, and `run-028` proves that
  endpoint and the planner fail **independently** (the monitor recovered at
  +23.2 s in a run where the planner never did). The gate is therefore a partial
  proxy: it catches the whole-stack failure, not a planner-only one. Step 2 is
  what is meant to cover the planner;
- it adds one participant and one publisher to the measured host, which is a
  change to what cell B measures and must be disclosed in the manifest/README
  the way the concat relay is.

**Smaller alternative, if the operator prefers zero perturbation:** step 3 only —
a bring-up gate that fails with a named reason when the map has not been
delivered. That changes nothing about what B measures, converts a 13-run silent
mystery into a fast, named, re-runnable preflight failure, and costs roughly
one bring-up in three. It does not fix delivery.

**Not recommended:** changing the DDS profile. The 16 MiB variant has no
evidence behind it (above), and the file is hashed into every filed B manifest.

## Outcome: bounded to the Fast-DDS transport, and cell B closed-loop rescoped

`B/run-033` — one deliberate, non-duel cyclonedds deviation run — **armed on the
first attempt**, drove to within **0.103 m** of the goal and passed its quality
gate (`gate_pass: true`, `reasons: []`), with `waiting for map` × 0 and
`waiting for route` × 0. On the same host, image digest, bundle, fork build and
launch line, changing only the middleware took cell B from 0-for-14 to armed.

The full finding, the attribution boundary (n = 1, uncontrolled Fast-DDS
version/kernel/loopback, and Task 9's warning that the cyclone cell is not
measurement-grade), the rescope, and the list of what was tried and did not work
are in `benchmarks/results/PROVENANCE.md` §7.11. Read that before quoting any of
this.
