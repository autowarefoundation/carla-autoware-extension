# P3 Phase 0 — harness re-verification probes P1–P4 and the branch ruling

Live diagnostic session, 2026-07-31. Promoted here because it is a
**decision-run** result: it selects one of three pre-declared campaign
branches, and every later P3 task keys off the ruling.

- Repo: `autowarefoundation/carla-autoware-extension`, branch `bench/p3-baseline`
- Worktree: `~/src/carla-autoware-extension-worktrees/bench-p0`
- HEAD at probe time: `d7460abadd2aa116587dcb9c5925057c6c79984b`
  (`d7460ab docs(bench): fix the teardown.sh docker-rm-f citation, both copies`)
- Spec adjudicated against:
  `specs/2026-07-31-p3-completion-design.md`, section
  "Phase 0 — Harness re-verification (live, decision gate)"

The pre-declaration is reproduced **verbatim below, above every measurement**,
so the record itself shows that the hypothesis, the probes, their predicted
outcomes and the three admissible branches all existed before any datum did.
Nothing in that block was edited after the probes ran. Every probe's raw
output is `tee`-appended unedited, including output that refutes the
hypothesis.

---

## 1. Pre-declaration (verbatim from the spec, written before measurement)

> **Hypothesis.** B's NDT-rate depression is caused by double publication on
> `/sensing/lidar/concatenated/pointcloud` (harness relay + tier4
> `concatenate_data`), absent on A (relay only).
>
> **Probes** (in order; each names its expected outcome):
>
> - P1 — on a live cell-A stack: publisher count and node names on
>   `RELAY_OUT`. Predicted: 1 (`//relay`). **Two publishers here refutes the
>   hypothesis** (the probe can kill it, deliberately).
> - P2 — on a live cell-B stack: same probe. Predicted: 2, reproducing the
>   run-012 record.
> - P3 — cell B, relay stopped: is `concatenate_data`'s own output a usable
>   NDT input (non-empty clouds, sane width/point_step/frame, steady rate)?
> - P4 — cell B, relay stopped: NDT output rate over a scoring-window-length
>   interval. Predicted if hypothesis true: ratio recovers to ≥ 0.9 of the
>   registered 10 Hz.
>
> **Pre-declared adjudication branches:**
>
> - **(a) Recovery** (P2 shows 2 publishers, P4 recovers): harness defect
>   confirmed. Fix = remove the B-path relay (`concatenate_data` is the sole
>   publisher; P3 must have shown its output usable). Commit the fix, then
>   reclassify B `run-013…022` as `harness:<fix-commit>` under criterion 3,
>   and recollect the static arm as **10 fresh interleaved pairs** post-fix.
> - **(b) Concat output unusable** (P3 fails: empty/malformed clouds): the
>   relay is necessary but the coexistence is the defect. Fix = suppress the
>   concat node's publication on the B path (mechanism chosen at
>   implementation; remap or node exclusion), same reclassification and
>   recollection as (a).
> - **(c) No recovery** (P4 stays < 0.9 with a single publisher): the
>   hypothesis is wrong. No harness edit, no reclassification. Register the
>   depressed rate as a measured confound with the Phase 0 diagnostics
>   attached, keep all filed data, and proceed to collection with the harness
>   unchanged. The M5 gate keeps failing on B and the verdict carries that
>   fact — the gate is never tuned to pass.
>
> **Consequence of (a)/(b) for the A pair-halves, pre-declared.** The 10 A
> static runs (`run-003…012`) were collected interleaved against B runs now
> known defective. Interleaving exists to spread session drift across both
> cells; pairing fresh post-fix B runs against stale pre-fix A runs would
> reintroduce exactly the session confound the design forbids. Therefore on
> branch (a)/(b) the static-arm verdict pool is **the 10 fresh pairs only**:
> the pre-fix A runs stay filed and non-excluded, but their
> `duel_admissible` flag is flipped to `false` with a PROVENANCE.md entry
> recording this paragraph as the reason. This uses the admission flag for its
> stated purpose (deciding what feeds the verdict) and mutates no exclusion
> state and no data. This is the one genuinely judgment-call consequence in
> this design; it is flagged for owner review here rather than buried in the
> plan.

**Adjudication rule taken from the task brief, also pre-declared:** the
registered `ndt_expected_hz` for B is **10.0** (`benchmarks/config/cells.yaml`
line 269), so **recovery = post-kill rate ≥ 9.0 Hz sustained**. No fourth
branch may be invented; if the measurements fit none of the three, the task
stops and reports BLOCKED.

---

## 2. Session preamble (host quiescence, recorded not tuned)

```console
$ export ROS_DOMAIN_ID=0; echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
ROS_DOMAIN_ID=0
$ uptime
 22:17:09 up 13:10,  1 user,  load average: 0.29, 0.31, 0.26
$ nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv
name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
NVIDIA GeForce RTX 5090, 1402 MiB, 32607 MiB, 0 %
$ nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
pid, process_name, used_gpu_memory [MiB]
7046, /usr/bin/warp-terminal, 214 MiB
$ pgrep -af 'UnrealEditor|CarlaUE4'
(self-match) 743930 /usr/bin/zsh -c source /home/youtalk/.claude/shell-snapshots/snapshot-zsh-... && eval 'cd .../bench-p0 && ... pgrep -af 'UnrealEditor|CarlaUE4' ...'   [ONE match, TRUNCATED here for width: its cmdline IS this probe's own pgrep invocation, i.e. NO CARLA/UnrealEditor process was running]
$ cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
powersave
$ docker ps --format "{{.Names}}\t{{.Status}}"
headroom-default Up 13 hours (unhealthy)
```

Read: 1-min loadavg 0.29 (< 2), GPU 1402 MiB / 32607 MiB with no CARLA
consumer (`warp-terminal` is the desktop terminal, not a simulator), governor
`powersave` **recorded and left alone**, and the only `pgrep` hit was the
probing shell itself. No `autoware` container was running. Inter-run hygiene
(`docker compose down`, `docker compose up -d autoware`,
`scripts/bootstrap_carla_msgs.sh`) was applied before the first launch and
again between the two runs.

---

## 3. P1 — cell A publisher census on `/sensing/lidar/concatenated/pointcloud`

Run: `bash benchmarks/run.sh A --arm static` (no `--duel`, so
`duel_admissible: false`; filed as `benchmarks/results/A/run-013`). The census
is taken on the live stack, after `scripts/e2e/launch_autoware.sh` reports its
own relay up and before the harness's 60 s static window closes.

**Predicted (pre-declared): 1 publisher, `//relay`.**

```console
$ docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && ros2 topic info -v /sensing/lidar/concatenated/pointcloud'
Type: sensor_msgs/msg/PointCloud2

Publisher count: 2

Node name: concatenate_data
Node namespace: /sensing/lidar
Topic type: sensor_msgs/msg/PointCloud2
Endpoint type: PUBLISHER
GID: 01.10.25.5a.99.6c.6c.49.9a.12.b7.29.00.00.30.03.00.00.00.00.00.00.00.00
QoS profile:
  Reliability: BEST_EFFORT
  History (Depth): KEEP_LAST (5)
  Durability: VOLATILE
  Lifespan: Infinite
  Deadline: Infinite
  Liveliness: AUTOMATIC
  Liveliness lease duration: Infinite

Node name: relay
Node namespace: /
Topic type: sensor_msgs/msg/PointCloud2
Endpoint type: PUBLISHER
GID: 01.10.eb.db.8a.d3.86.08.77.0c.db.bf.00.00.15.03.00.00.00.00.00.00.00.00
QoS profile:
  Reliability: BEST_EFFORT
  History (Depth): KEEP_LAST (10)
  Durability: VOLATILE
  Lifespan: Infinite
  Deadline: Infinite
  Liveliness: AUTOMATIC
  Liveliness lease duration: Infinite

Subscription count: 1

Node name: crop_box_filter_measurement_range
Node namespace: /localization/util
Topic type: sensor_msgs/msg/PointCloud2
Endpoint type: SUBSCRIPTION
GID: 01.10.25.5a.99.6c.6c.49.9a.12.b7.29.00.00.49.04.00.00.00.00.00.00.00.00
QoS profile:
  Reliability: BEST_EFFORT
  History (Depth): KEEP_LAST (5)
  Durability: VOLATILE
  Lifespan: Infinite
  Deadline: Infinite
  Liveliness: AUTOMATIC
  Liveliness lease duration: Infinite

```

**Measured: 2 publishers — `/sensing/lidar/concatenate_data` AND `//relay`.**
The prediction was 1. Corroboration below rules out the stale-`ros2cli`-daemon
artifact this repo has been bitten by before (`benchmarks/run.sh:789`): the same
census re-taken with fresh discovery, plus a check of whether the concat
publisher is merely ADVERTISED or actually EMITTING.

```console
$ docker exec autoware bash -lc '... ros2 topic info -v --no-daemon /sensing/lidar/concatenated/pointcloud | grep -E "count|Node name"'
Publisher count: 2
Node name: concatenate_data
Node namespace: /sensing/lidar
Node name: relay
Node namespace: /
Subscription count: 1
Node name: crop_box_filter_measurement_range
Node namespace: /localization/util
```

Census confirmed with fresh discovery (`--no-daemon`): **2 publishers**, not a
daemon-cache artifact.

Supplementary (NOT adjudication input, recorded for mechanism): is cell A's
second publisher merely advertised, or actually emitting? `launch_autoware.sh:46`
asserts "the concat node is left with its stock 3-topic config; it stays silent
with a single publisher".

```console
$ docker exec autoware bash -lc '... timeout 12 ros2 topic hz --no-daemon /sensing/lidar/concatenated/pointcloud'
usage: ros2 [-h] [--use-python-default-buffering]
            Call `ros2 <command> -h` for more detailed usage. ...
ros2: error: unrecognized arguments: --no-daemon
```

That supplementary probe did **not** land: `ros2 topic hz` has no `--no-daemon`
flag (only `topic info`/`echo`/`list` do), and by the time the argument error
came back the harness's 60 s static window had closed and teardown had begun.
Recorded rather than retried, because it is not adjudication input — the
pre-declared P1 criterion is a **publisher count**, and that count is 2 under
both a daemon-backed and a fresh-discovery census. Whether cell A's
`concatenate_data` is emitting or silent is left as an open mechanism question
below (§6), not resolved here. (Note the brief's Step 4 `ros2 topic hz`
invocations are correctly written without `--no-daemon`.)

### P1 result

|                                        | Predicted (pre-declared) | Measured                                            |
| -------------------------------------- | ------------------------ | --------------------------------------------------- |
| Publisher count on `RELAY_OUT`, cell A | **1**                    | **2**                                               |
| Node names                             | `//relay`                | `/sensing/lidar/concatenate_data` **and** `//relay` |

The spec pre-declared exactly this outcome as decisive: _"Two publishers here
refutes the hypothesis (the probe can kill it, deliberately)."_ Cell A carries
the same double publication the hypothesis attributes only to cell B, while
cell A's filed `ndt_rate_ratio` is ≈ 1.0 across 12 runs. The differential
explanation is therefore gone before cell B is ever measured.

Cell A's own run closed normally and filed as `benchmarks/results/A/run-013`
(`duel_admissible: false`). Its harness-printed gate line is reproduced here as
raw session evidence only — it is a bring-up-class run and, per the campaign's
no-peeking rule, it is **not** compared against any cell-B number:

```console
/…/benchmarks/results/A/run-013/quality.json: gate_pass=True branch=absolute ndt_rate_ratio=1.000 pose_err_max_m=0.099
```

---

## 4. P2 — cell B publisher census on `/sensing/lidar/concatenated/pointcloud`

Run for the record. The brief pre-commits the consequence of P1: _"Two
publishers on A refutes the hypothesis → the ruling is (c) regardless of what B
shows (the differential explanation is gone); still run P2 for the record, skip
the kill probes, go to Step 6."_ P2 is therefore recorded, and **P3/P4 and the
relay kill are deliberately not run** — not because they were inconvenient, but
because the pre-declaration removed their decisional role the moment P1 came
back 2.

Inter-run hygiene applied first: `docker compose -f docker/compose.yaml down`,
then `scripts/bootstrap_carla_msgs.sh`.

Run: `bash benchmarks/run.sh B --arm static` (no `--duel`).

**Predicted (pre-declared): 2 publishers — `//relay` and
`/sensing/lidar/concatenate_data`**, reproducing the `results/B/run-012` record
cited in `benchmarks/cells/tier4_autoware.sh`'s "THAT PREMISE IS REFUTED"
comment.

```console
$ docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && ros2 topic info -v /sensing/lidar/concatenated/pointcloud'
Type: sensor_msgs/msg/PointCloud2

Publisher count: 1

Node name: _NODE_NAME_UNKNOWN_
Node namespace: _NODE_NAMESPACE_UNKNOWN_
Topic type: sensor_msgs/msg/PointCloud2
Endpoint type: PUBLISHER
GID: 01.0f.0f.85.ba.01.41.60.00.00.00.00.00.00.12.03.00.00.00.00.00.00.00.00
QoS profile:
  Reliability: BEST_EFFORT
  History (Depth): UNKNOWN
  Durability: VOLATILE
  Lifespan: Infinite
  Deadline: Infinite
  Liveliness: AUTOMATIC
  Liveliness lease duration: Infinite

Subscription count: 1

Node name: _NODE_NAME_UNKNOWN_
Node namespace: _NODE_NAMESPACE_UNKNOWN_
Topic type: sensor_msgs/msg/PointCloud2
Endpoint type: SUBSCRIPTION
GID: 01.0f.0f.85.e1.01.24.24.00.00.00.00.00.00.1d.04.00.00.00.00.00.00.00.00
QoS profile:
  Reliability: BEST_EFFORT
  History (Depth): UNKNOWN
  Durability: VOLATILE
  Lifespan: Infinite
  Deadline: Infinite
  Liveliness: AUTOMATIC
  Liveliness lease duration: Infinite

```

That first census reports **1 publisher** with `_NODE_NAME_UNKNOWN_` /
`_NODE_NAMESPACE_UNKNOWN_` and `History (Depth): UNKNOWN` — the signature of a
just-started `ros2cli` daemon whose graph discovery is still incomplete, which
is exactly the failure mode `benchmarks/run.sh:789` documents. It is recorded
unedited, then immediately re-taken with fresh discovery and repeated, because
a publisher COUNT is the pre-declared quantity and an under-discovered count
would be a false measurement in either direction.

```console
$ for i in 1 2 3; do docker exec autoware bash -lc '... ros2 topic info -v --no-daemon /sensing/lidar/concatenated/pointcloud | grep -E "count|Node name|Node namespace"'; done
--- attempt 1 (--no-daemon) ---
--- attempt 2 (--no-daemon) ---
Publisher count: 1
Node name: _NODE_NAME_UNKNOWN_
Node namespace: _NODE_NAMESPACE_UNKNOWN_
Subscription count: 0
--- attempt 3 (--no-daemon) ---
Publisher count: 1
Node name: _NODE_NAME_UNKNOWN_
Node namespace: _NODE_NAMESPACE_UNKNOWN_
Subscription count: 1
Node name: _NODE_NAME_UNKNOWN_
Node namespace: _NODE_NAMESPACE_UNKNOWN_
```

Discovery on cell B's SHM-off Fast-DDS transport is itself unreliable: attempt
1 returned NOTHING, the subscription count moved 0 -> 1 between attempts, and
no endpoint's node name resolves. Two follow-ups on the same live stack —
which nodes exist, and is the harness relay actually alive:

```console
$ docker exec autoware bash -lc '... ros2 node list --no-daemon | grep -Ei "relay|concat"'
$ docker exec autoware bash -lc 'cat /tmp/tier4-concat-relay.pid; ps -o pid,args -p $(cat /tmp/tier4-concat-relay.pid); tail -3 /tmp/tier4-concat-relay.log'
(no relay/concat node discovered)
--- relay process ---
437
    PID COMMAND
    437 /usr/bin/python3 /opt/ros/humble/bin/ros2 run topic_tools relay /sensing/lidar/top/pointcloud_before_sync /sensing/lidar/concatenated/pointcloud
--- relay log tail ---
```

The relay process **is** alive (pid 437, the expected `topic_tools relay`
cmdline) yet `ros2 node list --no-daemon` discovers **neither** it nor
`concatenate_data`. So on cell B the graph-introspection instrument itself is
under-reporting — the census cannot be trusted as a count in either direction.
One last census, now that the `ros2cli` daemon has been resident for ~2 min and
has had time to complete discovery:

```console
$ docker exec autoware bash -lc '... ros2 node list | wc -l; ros2 node list | grep -Ei "relay|concat"; ros2 topic info -v /sensing/lidar/concatenated/pointcloud | grep -E "count|Node name|Node namespace"'
node count: 162
/relay
/sensing/lidar/concatenate_data
/trajectory_relay
Publisher count: 2
Node name: relay
Node namespace: /
Node name: concatenate_data
Node namespace: /sensing/lidar
Subscription count: 1
Node name: crop_box_filter_measurement_range
Node namespace: /localization/util
```

With the daemon resident and discovery complete, the census resolves cleanly and
**reproduces the `run-012` record exactly**: 2 publishers, `/relay` and
`/sensing/lidar/concatenate_data`, against a single subscriber
`/localization/util/crop_box_filter_measurement_range`.

### P2 result

|                                        | Predicted (pre-declared)                        | Measured                                       |
| -------------------------------------- | ----------------------------------------------- | ---------------------------------------------- |
| Publisher count on `RELAY_OUT`, cell B | **2**                                           | **2**                                          |
| Node names                             | `//relay` and `/sensing/lidar/concatenate_data` | `/relay` and `/sensing/lidar/concatenate_data` |

**Instrument caveat, recorded because it inverts this repo's standing advice.**
On cell B (`rmw_fastrtps_cpp`, SHM off) `--no-daemon` **under-reports**: three
fresh-discovery censuses returned nothing, then 1 publisher with
`_NODE_NAME_UNKNOWN_`, and `ros2 node list --no-daemon` found neither the relay
nor `concatenate_data` while the relay process was demonstrably alive (pid 437).
The settled daemon found 162 nodes including both. This is the opposite polarity
of the stale-daemon trap `benchmarks/run.sh:789` warns about, and on this
transport a CLI graph query must be given time to discover before its count
means anything. Cell A (`rmw_cyclonedds_cpp`) showed no such split — daemon and
`--no-daemon` agreed on 2 there — so P1's count is not exposed to this caveat.

---

## 5. P3 and P4 — deliberately NOT run

`P3` (concat output usability with the relay stopped) and `P4` (NDT rate with
the relay stopped, pre- and post-kill) were **not executed**, and the relay was
**not killed**. This is the pre-declared consequence of P1, not a shortcut:

> Two publishers on A refutes the hypothesis → the ruling is (c) regardless of
> what B shows (the differential explanation is gone); still run P2 for the
> record, skip the kill probes, go to Step 6.

The kill probes exist to test whether removing the second publisher restores
cell B's NDT rate. They can only carry that meaning while double publication is
a **differential** between the two cells. P1 measured it on cell A as well, so
the probes lost their decisional role before they were run; executing them would
have produced numbers with no pre-declared reading. The `9.0 Hz` recovery
threshold (0.9 × the registered `ndt_expected_hz: 10.0`,
`benchmarks/config/cells.yaml:269`) is therefore **not evaluated**, and no value
is asserted for it anywhere in this record.

---

## 6. Step 6 — adjudication against the spec's branch table

| Probe                                         | Predicted (pre-declared)                          | Measured                                                                                 | Verdict                                         |
| --------------------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------- | ----------------------------------------------- |
| **P1** cell A publisher census on `RELAY_OUT` | 1 (`//relay`)                                     | **2** (`/sensing/lidar/concatenate_data` + `//relay`), daemon and `--no-daemon` agreeing | **Prediction FAILED — hypothesis refuted**      |
| **P2** cell B publisher census on `RELAY_OUT` | 2 (`//relay` + `/sensing/lidar/concatenate_data`) | **2** (`/relay` + `/sensing/lidar/concatenate_data`)                                     | Prediction held; reproduces `results/B/run-012` |
| **P3** concat output usable, relay stopped    | —                                                 | **not run** (P1 removed its decisional role)                                             | n/a                                             |
| **P4** NDT rate ≥ 9.0 Hz, relay stopped       | recovery if hypothesis true                       | **not run** (same reason)                                                                | n/a                                             |

### Ruling: branch (c) — "No recovery" / the hypothesis is wrong

The spec's branch (c) is the branch whose _content_ is "the hypothesis is
wrong … no harness edit, no reclassification … register the depressed rate as a
measured confound with the Phase 0 diagnostics attached, keep all filed data,
and proceed to collection with the harness unchanged. The M5 gate keeps failing
on B and the verdict carries that fact — the gate is never tuned to pass."

It is reached here through the route the spec and the brief both pre-declared
for a 2-publisher P1, rather than through P4's arithmetic. The reasoning:

1. The hypothesis is explicitly **differential** — "double publication … absent
   on A (relay only)". It explains B's depressed rate _by_ the difference.
2. P1 measured the same double publication on cell A, whose filed
   `ndt_rate_ratio` is ≈ 0.99999998 across 12 runs (spec, "The finding that
   drives Phase 0"). The same alleged cause is present where the alleged effect
   is absent, so it is not the cause.
3. The spec assigned this outcome its consequence in advance: "**Two publishers
   here refutes the hypothesis** (the probe can kill it, deliberately)."
4. Branches (a) and (b) are both **fix** branches predicated on the harness
   being at fault for the rate depression. With the hypothesis refuted there is
   no established harness fault to fix, so neither is admissible. (c) is the
   only remaining pre-declared branch, and it is the one written for exactly
   this case.

No fourth branch was invented, no branch was reshaped, and no prediction was
softened after the fact — P1's prediction is recorded above as **FAILED**.

### Fix mechanism (the input Task 2 needs)

**Neither.** Relay-removal (branch a) and concat-suppression (branch b) both
drop out with the hypothesis. Branch (c) prescribes **no harness change at
all** — `benchmarks/cells/tier4_autoware.sh:538`'s relay stays exactly as it
is, and so does the "THAT PREMISE IS REFUTED" comment block above it, per the
campaign convention that refuted hypotheses stay in the record with the
diagnostics that refuted them.

Consequently **none** of the following happens:

- No `harness:<commit>` reclassification of B `run-013…022` under
  `exclusions.md` criterion 3. Those runs stay filed, unexcluded, as §4.1 of
  `benchmarks/results/PROVENANCE.md` already rules.
- No 10-fresh-pair static recollection (spec, Phase 2 item 1, which is
  explicitly "only on branch (a)/(b)").
- **No `duel_admissible` flip on A `run-003…012`.** The spec's "Consequence of
  (a)/(b) for the A pair-halves" paragraph is conditioned on branch (a)/(b) and
  therefore does not fire. The A static pair-halves keep
  `duel_admissible: true`. This is the single most consequential downstream
  effect of the ruling and is called out so no later task applies that
  paragraph by reflex.

### What Task 2 registers instead, and against what

Branch (c) says "register the depressed rate as a measured confound with the
Phase 0 diagnostics attached". That confound is **already registered** — this
session did not discover a new one, it removed a candidate competitor to the
existing one:

- `benchmarks/README.md`, "The A-side instrument-asymmetry bound: cell A loses
  NOTHING where cell B loses 17–26%": `observer_loss_rate` **0.0000** on cell A
  against **0.2564 / 0.1715** on cell B, concluding "the loss is a property of
  cell B's SHM-off Fast-DDS transport", corroborated three independent ways.
- `benchmarks/results/CAL-rmw/PROVENANCE.md`: the same transport measured at
  **0.333–6.156 Hz** against cyclonedds' **10.008–10.010 Hz**, with **Owner
  ruling 2026-07-31: retain all fifteen runs as produced, with no exclusions,
  and disclose.**
- `benchmarks/results/PROVENANCE.md` §4.1: Task 18 applied that ruling unchanged
  to the nine gate-failing cell-B static runs.

Phase 0's own instrument caveat (§4 above) is an independent fourth observation
of that same transport property, measured on a completely different quantity —
DDS **graph discovery**, not sample delivery — and it is offered as such.

**This ruling adjusts no gate.** Nothing was tuned, no threshold moved, no run
was excluded, and cell B's M5 failures stand. What changed is only that one
candidate explanation for them is now measured to be false.

---

## 7. The two diagnostic runs, and what they are not

Both runs were launched **without** `--duel`, so both file
`duel_admissible: false` and neither can ever feed the equivalence verdict.
Both completed their full 60 s static window and tore down cleanly; neither
carries an exclusion.

| run                            | cell | arm    | duel_admissible | excluded | harness gate line                                                                                             |
| ------------------------------ | ---- | ------ | --------------- | -------- | ------------------------------------------------------------------------------------------------------------- |
| `benchmarks/results/A/run-013` | A    | static | false           | none     | `gate_pass=True branch=absolute ndt_rate_ratio=1.000 pose_err_max_m=0.099`                                    |
| `benchmarks/results/B/run-023` | B    | static | false           | none     | `gate_pass=False branch=absolute ndt_rate_ratio=0.387 pose_err_max_m=0.061 reasons=ndt rate ratio 0.39 < 0.9` |

Those two gate lines are reproduced as raw session evidence — they are the
harness's own per-run gate/exclusion output, which the no-peeking rule permits
during collection. **No comparison is drawn between them, and none may be**:
they are single bring-up-class runs, they are not a pair, and the A-vs-B
verdict is computed exactly once, later, by `duel_verdict.py` over
duel-admissible runs only. They are listed together because they are the two
runs this session produced, not because they are being read against each other.

Teardown after both: no `autoware` container, no `UnrealEditor`/`CarlaUE4`
process, port 2000 free. Inter-run hygiene (`docker compose down` +
`bootstrap_carla_msgs.sh`) was applied between them, and the cell-B launch
waited for the 1-min loadavg to fall back below 2 after cell A's teardown.
