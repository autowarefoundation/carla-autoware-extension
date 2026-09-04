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
Nothing in that block was edited after the probes ran.

**What the console blocks below are, stated precisely** (corrected in fix
round 1, where the original wording — "every probe's raw output is
`tee`-appended unedited" and the commands "recorded exactly" — was found to
overstate what the file contains):

- Every console block's **output** is `tee`-appended **unedited**, including
  output that refutes the hypothesis and including two probes of my own that
  failed outright. Nothing was removed from any output for being inconvenient.
- Two exceptions to "unedited", both marked in place: the `pgrep` self-match
  line in §2 is truncated for width (labelled `[… TRUNCATED …]`), and several
  blocks pipe the probe through `grep`/`tail` to select lines. **Where a block
  is `grep`-filtered, its `$` command line shows the filter**, so what was kept
  and what was dropped is legible. The consequence worth naming: the cell-A
  `--no-daemon` corroboration in §3 is `grep`-filtered to counts and node
  names, so **that census's endpoint GIDs are not in this file** — the
  unfiltered cell-A census immediately above it does carry them.
- The `$` command lines are **transcribed, not captured**. Where one reads
  `bash -lc '... ros2 topic info -v …'`, the `...` elides the invariant
  `source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash &&`
  preamble that every `docker compose exec` in this campaign carries. §9 lists
  each elided command in full, so no command in this file is unrecoverable.
- Probe timing: the P1/P2 blocks in §3–§4 were **not** timestamped inline (a
  defect found in fix round 1). §8 gives the session timeline, marking which
  times are attested from filed artifacts and which are derived. The fix-round
  probes in §10 carry inline UTC timestamps.

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

---

## 8. Session timeline, and what is NOT retained about it

Fix round 1 found that no console block in §3–§7 carries a timestamp. That is a
real defect for a document whose standard is "a reader not in the session
reaches the same ruling", and it is corrected going forward rather than
back-filled by guesswork.

**Individual probe wall-clock times for P1 and P2 are NOT RETAINED.** They were
not captured inline and reconstructing them from memory would be fabrication.
What _is_ attested, from the filed run directories' own artifacts, are the
bounds each probe necessarily falls inside — every probe ran against a live
stack, so each sits strictly between its run's manifest write and its
`quality.json` write:

| Attested from                                                  | Time (host local, 2026-07-31) |
| -------------------------------------------------------------- | ----------------------------- |
| Session preamble (`uptime`, §2)                                | 22:17:09                      |
| `A/run-013` `manifest.json` written (run starts)               | 22:17:45                      |
| `A/run-013` `quality.json` written (window closed, stack down) | 22:20:11                      |
| `B/run-023` `manifest.json` written (run starts)               | 22:22:35                      |
| `B/run-023` `quality.json` written (window closed, stack down) | 22:25:01                      |

So **P1 and its corroboration fall inside 22:17:45–22:20:11**, and **P2 and its
four follow-ups inside 22:22:35–22:25:01**, in the order printed. Both bounds
are recomputable: `stat -c '%y %n' benchmarks/results/{A/run-013,B/run-023}/{manifest,quality}.json`.

The fix-round probes in §10 carry inline `date -u` stamps, captured in the same
`docker exec` as the probe itself, so they need no such reconstruction.

## 9. The elided command preambles, in full

Every `$` line in this file that reads `bash -lc '... <command>'` elides the
same invariant prefix, which is mandatory for every `docker exec` in this
campaign (the container does not inherit the entrypoint):

```bash
source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash
```

The four elided command lines, written out:

```bash
# §3 cell-A corroboration, and §4's three-attempt cell-B loop
docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && ros2 topic info -v --no-daemon /sensing/lidar/concatenated/pointcloud 2>&1 | grep -E "count|Node name"'

# §3 supplementary rate probe (FAILED: `ros2 topic hz` has no --no-daemon)
docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && timeout 12 ros2 topic hz --no-daemon /sensing/lidar/concatenated/pointcloud'

# §4 node list + relay liveness
docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && ros2 node list --no-daemon 2>&1 | grep -Ei "relay|concat" || echo "(no relay/concat node discovered)"'
docker exec autoware bash -lc 'cat /tmp/tier4-concat-relay.pid; ps -o pid,args -p "$(cat /tmp/tier4-concat-relay.pid)" 2>&1 | tail -2; echo "--- relay log tail ---"; tail -3 /tmp/tier4-concat-relay.log 2>&1'

# §4 final settled-daemon census
docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && echo "node count: $(ros2 node list 2>/dev/null | wc -l)" && (ros2 node list 2>/dev/null | grep -Ei "relay|concat" || echo "(no relay/concat in daemon node list)") && ros2 topic info -v /sensing/lidar/concatenated/pointcloud 2>&1 | grep -E "count|Node name|Node namespace"'
```

---

## 10. Fix round 1, finding F3 — does cell A's `concatenate_data` EMIT or only ADVERTISE?

This section was added **after** the ruling in §6, in response to a review
finding. It is recorded here rather than silently folded into §6 because the
question it answers is one §6's ruling depends on, and the record must show
that the check came second.

**Why it matters, stated before the measurement.** P1's pre-declared criterion
is a publisher **count**. A count cannot distinguish a publisher that
_advertises_ from one that _emits_. The spec's hypothesis names double
**publication**. So if cell A's `concatenate_data` advertises but never emits,
then double publication is _not_ present on cell A, the differential the
hypothesis rests on survives, and (a)/(b) could be the correct branch — the
count would not have measured the phenomenon its own hypothesis names.

**Instrument, and why it answers the question.** `ros2 topic hz` reports the
**sum** over publishers and cannot attribute flow to a source. So the primary
instrument is stamp identity, in
`benchmarks/evidence/p3-phase0/probe_concat_emission.py` (committed with this
round; its decision rule is fixed in its module docstring, written before the
probe was run). `topic_tools relay` forwards its input **verbatim**, so every
message the relay puts on `RELAY_OUT` carries a header stamp that also appeared
on `RELAY_IN`. A second emitting publisher cannot have that property for free:
it either stamps its own output (producing `RELAY_OUT` stamps absent from
`RELAY_IN`) or copies its input's stamp as a concatenation node does (producing
**duplicate** stamps on `RELAY_OUT`). Matching the two streams therefore
attributes traffic to a source. Cell A's registered `lidar_expected_hz` is
**20.0**, so two emitting 20 Hz publishers would also drive the aggregate rate
toward 40 Hz — a factor-of-two separation, far outside noise, which the
independent `ros2 topic hz` reading below tests.

The probe's known bias is stated in its docstring and repeated here: it is a
subscriber-side BEST_EFFORT measurement, so dropped samples would push it
toward the "only advertises" reading — i.e. **against** the ruling it is
checking. It cannot manufacture a false confirmation of §6.

Diagnostic run: `bash benchmarks/run.sh A --arm static` (no `--duel`), filed as
`benchmarks/results/A/run-014`. Full preamble and inter-run hygiene first
(loadavg 0.23, GPU 1281 MiB / 32607 MiB with no CARLA consumer, no CARLA
process, governor `powersave` recorded, `docker compose down` +
`bootstrap_carla_msgs.sh`).

```console
$ docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && echo "T_START=$(date -u +%FT%TZ)" && python3 /work/benchmarks/evidence/p3-phase0/probe_concat_emission.py --seconds 20 && echo "T_END=$(date -u +%FT%TZ)"'
T_START=2026-08-01T05:51:16Z
collecting for 20 s on:
  IN  /sensing/lidar/top/pointcloud_before_sync
  OUT /sensing/lidar/concatenated/pointcloud

--- /sensing/lidar/top/pointcloud_before_sync ---
messages received      : 400
wall span / rate       : 19.99 s / 19.956 Hz
unique header stamps   : 400
widths (value: count)  : {14563: 3, 12733: 1, 14700: 2, 12625: 1, 14649: 1, 12677: 1, … [310 distinct widths, TRUNCATED for width; full histogram not retained]}
frame_ids              : {'base_link': 400}
stamp span / rate      : 19.95 s / 20.000 Hz

--- /sensing/lidar/concatenated/pointcloud ---
messages received      : 398
wall span / rate       : 19.89 s / 19.958 Hz
unique header stamps   : 398
widths (value: count)  : {12733: 1, 14700: 2, 12625: 1, 14649: 1, 12677: 1, 14581: 2, … [309 distinct widths, TRUNCATED for width; full histogram not retained]}
frame_ids              : {'base_link': 398}
stamp span / rate      : 19.85 s / 20.000 Hz

=== ATTRIBUTION ===
RELAY_IN  messages                        : 400
RELAY_OUT messages                        : 398
out/in ratio                              : 0.995
RELAY_OUT stamps NOT seen on RELAY_IN     : 0
RELAY_OUT duplicate stamps (extra copies) : 0

=== VERDICT (by the decision rule in this file's docstring) ===
concatenate_data only ADVERTISES: every RELAY_OUT message is one the
relay forwarded (matched stamp, no duplicates, out/in ~= 1).
T_END=2026-08-01T05:51:37Z
```

Independent corroboration, on the **same live stack**, taken so that the count
and the flow are measured against the same stack state rather than two
different ones:

```console
$ docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && echo "T=$(date -u +%FT%TZ)" && ros2 topic info -v /sensing/lidar/concatenated/pointcloud | grep -E "count|Node name|Node namespace" && timeout 12 ros2 topic hz /sensing/lidar/concatenated/pointcloud && timeout 12 ros2 topic hz /sensing/lidar/top/pointcloud_before_sync && echo "T_END=$(date -u +%FT%TZ)"'
T=2026-08-01T05:51:53Z
--- census, same stack state ---
Publisher count: 2
Node name: concatenate_data
Node namespace: /sensing/lidar
Node name: relay
Node namespace: /
Subscription count: 1
Node name: crop_box_filter_measurement_range
Node namespace: /localization/util
--- hz RELAY_OUT (aggregate over BOTH publishers) ---
 min: 0.046s max: 0.054s std dev: 0.00141s window: 201
average rate: 19.957
 min: 0.046s max: 0.054s std dev: 0.00138s window: 221
--- hz RELAY_IN ---
 min: 0.047s max: 0.053s std dev: 0.00112s window: 102
average rate: 19.960
 min: 0.047s max: 0.053s std dev: 0.00115s window: 122
T_END=2026-08-01T05:52:18Z
```

### F3 result: cell A's `concatenate_data` ADVERTISES but does NOT EMIT

| Quantity                                  | If both publishers emit                    | Measured                                          |
| ----------------------------------------- | ------------------------------------------ | ------------------------------------------------- |
| `RELAY_OUT` / `RELAY_IN` message ratio    | ≈ 2.0                                      | **0.995** (398 / 400)                             |
| `RELAY_OUT` stamps absent from `RELAY_IN` | > 0                                        | **0**                                             |
| `RELAY_OUT` duplicate header stamps       | > 0 (a concat node copies its input stamp) | **0**                                             |
| Aggregate `ros2 topic hz` on `RELAY_OUT`  | ≈ 40 Hz                                    | **19.957 Hz**, against `RELAY_IN`'s **19.960 Hz** |
| Publisher count, same stack state         | 2                                          | **2** (`concatenate_data` + `relay`)              |

Two independent instruments agree, and they agree against the probe's own known
bias direction. **Every single message on `/sensing/lidar/concatenated/pointcloud`
is a relay forward.** `concatenate_data` holds an advertised publisher on that
topic and contributes **zero** traffic to it. Both stamp streams run at exactly
20.000 Hz, matching cell A's registered `lidar_expected_hz: 20.0`, and cell A's
filed `ndt_rate_ratio` ≈ 1.0 against `ndt_expected_hz: 20.0` is consistent with
NDT being fed one clean 20 Hz stream rather than a mixed 40 Hz one.

### What this does to the §6 ruling — stated, NOT re-adjudicated

The spec's hypothesis names double **publication**. On cell A there are two
publish*ers* and one publish*er* emitting. So:

- **P1's count criterion did not measure the phenomenon its own hypothesis
  names.** The count is 2 and that is a true measurement; what it is not is
  evidence of double publication on cell A.
- The differential the hypothesis rests on — double publication present on B,
  absent on A — is therefore **not refuted by this evidence** after all, and
  branch (a) or (b) may be the correct ruling.
- §6's ruling of **(c)** remains **procedurally correct on the pre-declared
  criterion as written**, and it is left standing in this record exactly as it
  was, unedited. It is **not substantively established**, and the campaign must
  not build on it until that is resolved.

**This task stops here and reports BLOCKED.** Re-adjudicating to (a) or (b)
would mean reshaping the spec's branch table against a criterion the spec
itself declared, after seeing data — which is precisely what the pre-declaration
exists to prevent. That is the owner's call, not this task's. What is needed is
a ruling on whether P1's count criterion stands as written (in which case (c)
holds) or is superseded by a publication-based criterion (in which case Phase 0
must be re-run with the kill probes P3/P4 that were skipped on the strength of
P1).

Note for whoever takes that decision: the kill probes were never run and the
relay was never killed on either cell, so **no data was destroyed by this
outcome** — re-running Phase 0 from P2 onward costs two live runs and no
recollection.

---

## 11. Fix round 2 — owner ruling: RESUME Phase 0 at P3/P4

### 11.1 The ruling that reopened the protocol (recorded before the measurements)

Fix round 1 established that P1's count criterion did not measure double
_publication_, and this task returned BLOCKED. The owner ruled on 2026-08-01:

> **RESUME Phase 0 at P3/P4.** Not "honor the literal count criterion", not
> "re-run the whole session from P2". P3 and P4 are pre-declared in the spec
> with pre-declared thresholds and can still land on (c), so running them shapes
> no outcome — it completes a protocol that was short-circuited by an instrument
> measuring the wrong quantity. In publication terms, cell A has exactly the one
> emitter P1 predicted, so the differential is intact and the hypothesis is live
> again.

Nothing below moves a threshold. Recovery remains **≥ 9.0 Hz sustained**
(0.9 × cell B's registered `ndt_expected_hz: 10.0`,
`benchmarks/config/cells.yaml:269`), and the branch table is the spec's,
unchanged.

Four cell-B diagnostic runs were needed, all `--arm static`, no `--duel`, each
with a full preamble and `docker compose down` + `bootstrap_carla_msgs.sh`
hygiene, each waiting for the 1-min loadavg to fall below 2 first. All four are
filed, **none excluded**, all `duel_admissible: false`:

| run         | what it contributed                                                                                          | why another run was needed                                                                                                     |
| ----------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| `B/run-024` | emission census (pre-kill), pre-kill publisher census, **P4 pre-kill**, the kill, post-kill publisher census | the harness tore the stack down at the start of P4 post-kill                                                                   |
| `B/run-025` | **P4 post-kill**, P3 `width`                                                                                 | `ros2 topic hz` printed nothing; had to rule out stdout block-buffering + SIGTERM losing the output                            |
| `B/run-026` | **P4 post-kill re-measured with `PYTHONUNBUFFERED=1`**, P3 `width`                                           | buffering ruled out, but `--no-daemon` echo could not resolve `frame_id`, and the relay was found still alive 3 s after `kill` |
| `B/run-027` | **P4 across the kill on an already-discovered subscriber**, full **P3** cloud characterisation               | —                                                                                                                              |

### 11.2 Probe 1 — emission census on cell B, PRE-kill (`B/run-024`)

The same stamp-identity instrument used on cell A in §10, so the two cells are
measured by the same rule. This is the direct differential against
`A/run-014`'s 2 advertisers / 1 emitter.

```console
$ docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && python3 /work/benchmarks/evidence/p3-phase0/probe_concat_emission.py --seconds 20 && ros2 topic info -v … && timeout 45 ros2 topic hz /localization/pose_estimator/pose_with_covariance --window 100 && kill $(cat /tmp/tier4-concat-relay.pid) && ros2 topic info -v … && timeout 45 ros2 topic hz … --window 100 && timeout 30 ros2 topic echo --once --no-daemon … --field width && …'
T_CHAIN_START=2026-08-01T13:45:46Z
===== STEP 1: emission census on B RELAY_OUT, PRE-KILL (2026-08-01T13:45:47Z) =====
collecting for 20 s on:
  IN  /sensing/lidar/top/pointcloud_before_sync
  OUT /sensing/lidar/concatenated/pointcloud

--- /sensing/lidar/top/pointcloud_before_sync ---
messages received      : 88
wall span / rate       : 18.25 s / 4.768 Hz
unique header stamps   : 88
widths (value: count)  : {6330: 1, 6195: 1, 6138: 1, 6317: 1, 6262: 2, 6203: 1, … [76 distinct widths, TRUNCATED for width; full histogram not retained]}
frame_ids              : {'base_link': 88}
stamp span / rate      : 18.25 s / 4.767 Hz

--- /sensing/lidar/concatenated/pointcloud ---
messages received      : 160
wall span / rate       : 18.43 s / 8.626 Hz
unique header stamps   : 88
widths (value: count)  : {6330: 1, 6195: 2, 6138: 2, 6317: 2, 6262: 3, 6203: 1, … [76 distinct widths, TRUNCATED for width; full histogram not retained]}
frame_ids              : {'base_link': 160}
stamp span / rate      : 18.25 s / 8.712 Hz

=== ATTRIBUTION ===
RELAY_IN  messages                        : 88
RELAY_OUT messages                        : 160
out/in ratio                              : 1.818
RELAY_OUT stamps NOT seen on RELAY_IN     : 0
RELAY_IN  stamps NOT seen on RELAY_OUT    : 0  (loss-symmetry check)
RELAY_OUT duplicate stamps (extra copies) : 72

=== VERDICT (by the decision rule in this file's docstring) ===
concatenate_data EMITS: RELAY_OUT carries traffic the relay alone
cannot account for. Double PUBLICATION is present on cell A.
===== STEP 1b: publisher census, PRE-KILL (2026-08-01T13:46:07Z) =====
Publisher count: 2
Node name: relay
Node namespace: /
Node name: concatenate_data
Node namespace: /sensing/lidar
Subscription count: 1
Node name: crop_box_filter_measurement_range
Node namespace: /localization/util
===== STEP 2: P4 PRE-KILL NDT rate (2026-08-01T13:46:07Z) =====
WARNING: topic [/localization/pose_estimator/pose_with_covariance] does not appear to be published yet
average rate: 4.615
 min: 0.121s max: 0.391s std dev: 0.08305s window: 6
average rate: 4.997
 min: 0.094s max: 0.391s std dev: 0.07737s window: 12
    … [64 lines of the same rolling ladder TRUNCATED for length] …
average rate: 4.850
 min: 0.009s max: 1.719s std dev: 0.21175s window: 100
average rate: 4.830
 min: 0.009s max: 1.719s std dev: 0.21020s window: 100
===== STEP 3: kill the harness relay (2026-08-01T13:46:53Z) =====
Publisher count: 1
Node name: concatenate_data
Node namespace: /sensing/lidar
Subscription count: 1
Node name: crop_box_filter_measurement_range
Node namespace: /localization/util
===== STEP 4: P4 POST-KILL NDT rate (2026-08-01T13:46:56Z) =====
```

**Two corrections to that raw output, both stated rather than edited out.**

1. The probe's verdict line prints "Double PUBLICATION is present on **cell A**".
   That string was hardcoded when the probe was written for the cell-A run; the
   probe does not know which cell it runs on. **This measurement is cell B.**
   The string is fixed in the committed probe (it now says "on this stack") and
   the defect is recorded here because the raw output above still carries it.
2. The trailing `average rate:` ladder of the 45 s P4 block and the ~75-entry
   `widths` histograms are truncated for length, marked in place. Every
   attribution figure is retained in full.

### P2-on-emission result — cell B has TWO emitters

| Quantity                                                  | Cell A (`run-014`) | Cell B (`run-024`)    |
| --------------------------------------------------------- | ------------------ | --------------------- |
| Advertised publishers on `RELAY_OUT`                      | 2                  | 2                     |
| `RELAY_OUT` / `RELAY_IN` message ratio                    | 0.995              | **1.818**             |
| `RELAY_OUT` stamps absent from `RELAY_IN`                 | 0                  | 0                     |
| `RELAY_IN` stamps absent from `RELAY_OUT` (loss symmetry) | (2, = count diff)  | **0**                 |
| `RELAY_OUT` **duplicate** stamps                          | **0**              | **72** (of 88 unique) |
| **Emitters**                                              | **1**              | **2**                 |

The loss-symmetry check is 0/0, so cell B's excess is not the probe dropping
`RELAY_IN` samples — the mismatch is asymmetric in the one direction a second
emitter produces. And the excess is entirely **duplicate stamps**: 72 of the 88
unique stamps arrive twice. That is the signature of `concatenate_data`
republishing the relay's own input clouds under the input's stamp, which is what
a concatenation node does. **Double publication is confirmed present on cell B
and absent on cell A. The differential the hypothesis names is real.**

### 11.3 P4 — NDT output rate, pre- and post-kill

**P4 pre-kill (`B/run-024`, both publishers emitting)**, from the block above:
the rolling ladder runs **4.383 – 6.145 Hz** and closes at **4.830 Hz** on a
full `--window 100`. Against the registered 10.0 Hz that is a ratio of ≈ 0.48 —
and it reproduces the 4.89 Hz that `benchmarks/cells/tier4_autoware.sh`'s "THAT
PREMISE IS REFUTED" comment recorded on `results/B/run-012`.

**The kill worked**, on the same stack: the census immediately after it drops
from 2 publishers to **1**, `/sensing/lidar/concatenate_data`, with the relay
gone from the graph.

**P4 post-kill** needed three attempts because two instrument confounds had to
be eliminated first. All three agree.

```console
$ # B/run-025 -- brief-verbatim command, output redirected to a file
$ docker exec autoware bash -lc '… kill $(cat /tmp/tier4-concat-relay.pid); … timeout 45 ros2 topic hz /localization/pose_estimator/pose_with_covariance --window 100; …'
===== census, POST-KILL (2026-08-01T13:51:45Z) =====
Publisher count: 1
Node name: _NODE_NAME_UNKNOWN_
Node namespace: _NODE_NAMESPACE_UNKNOWN_
Subscription count: 0
===== P4 POST-KILL NDT rate (2026-08-01T13:51:47Z) =====
===== P3 concat output usability, relay dead (2026-08-01T13:52:32Z) =====
6254
---
WARNING: topic [/sensing/lidar/concatenated/pointcloud] does not appear to be published yet
Could not determine the type for the passed topic
```

45 s of `ros2 topic hz` produced **no output at all**. That is not yet a
measurement: with stdout redirected to a file it is block-buffered, and
`timeout`'s SIGTERM discards an unflushed buffer — the `PYTHONUNBUFFERED=1`
class of defect this repo has already been bitten by. Re-measured:

```console
$ # B/run-026 -- same, with PYTHONUNBUFFERED=1
$ docker exec autoware bash -lc '… RP=$(cat /tmp/tier4-concat-relay.pid); kill $RP; sleep 3; kill -0 $RP && echo "RELAY STILL ALIVE (pid $RP)" || echo dead; PYTHONUNBUFFERED=1 timeout 45 ros2 topic hz … --window 100; …'
===== kill the harness relay =====
RELAY STILL ALIVE (pid 439)
===== P4 POST-KILL NDT rate, UNBUFFERED (2026-08-01T13:57:43Z) =====
(P4 post-kill block ended 2026-08-01T13:58:28Z)
===== P3 brief-verbatim (2026-08-01T13:58:28Z) =====
6198
---
WARNING: topic [/sensing/lidar/concatenated/pointcloud] does not appear to be published yet
Could not determine the type for the passed topic
```

Buffering is ruled out — unbuffered, 45 s still yields **zero NDT samples**.
But this run surfaced a _second_ confound: `kill -0` reported the relay pid
**still alive 3 s after `kill`**. And a third: `ros2 topic hz` builds a fresh
node, and on cell B's transport a fresh node's discovery is exactly what Phase 0
already measured under-reporting — so "printed nothing" is ambiguous between
"NDT stopped" and "this node never discovered NDT".

`B/run-027` removes all three at once with
`benchmarks/evidence/p3-phase0/probe_relay_kill_transition.py`: it subscribes
**before** the kill so discovery settles while the relay is still up and the
_same_ subscriber sees both regimes, it performs the kill itself and escalates
SIGTERM → SIGKILL rather than trusting a fixed sleep, and it prints bucketed
rates so the transition is visible instead of averaged.

```console
$ docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && PYTHONUNBUFFERED=1 python3 /work/benchmarks/evidence/p3-phase0/probe_relay_kill_transition.py --pre-s 12 --post-s 35'
subscribed; observing 12 s PRE-kill (discovery settles here)

=== KILLING THE RELAY at t+12.0s ===
relay pidfile records pid 438; sending SIGTERM
  STILL ALIVE after 5 s of SIGTERM; escalating to SIGKILL
  WARNING: relay pid STILL alive; post-kill labels below are NOT trustworthy

=== NDT OUTPUT RATE, bucketed (topic: /localization/pose_estimator/pose_with_covariance) ===
window (s rel. start)     regime        msgs        Hz
[  0.0,   5.0)            PRE-kill         8     1.600
[  5.0,  10.0)            PRE-kill         8     1.600
[ 10.0,  15.0)            PRE-kill         0     0.000
[ 15.0,  20.0)            PRE-kill         0     0.000
[ 20.0,  25.0)            spans kill       0     0.000
[ 25.0,  30.0)            POST-kill        0     0.000
[ 30.0,  35.0)            POST-kill        0     0.000
[ 35.0,  40.0)            POST-kill        0     0.000
[ 40.0,  45.0)            POST-kill        0     0.000
[ 45.0,  47.0)            POST-kill        0     0.000

=== SUMMARY ===
NDT   PRE-kill  :   16 msgs over  22.1 s =  0.725 Hz
NDT   POST-kill :    0 msgs over  25.0 s =  0.000 Hz
CLOUD PRE-kill  :   59 msgs over  22.1 s =  2.673 Hz
CLOUD POST-kill :  190 msgs over  25.0 s =  7.612 Hz

=== P3: FIRST CLOUD ON RELAY_OUT AFTER THE RELAY IS CONFIRMED DEAD ===
(by construction a concatenate_data cloud: it is the only publisher left)
header.frame_id : 'base_link'
header.stamp    : 67.162079379
height          : 1
width           : 6202
point_step      : 16
row_step        : 99232
is_dense        : True
is_bigendian    : False
data length     : 99232 bytes
fields          : [('x', 0, 7, 1), ('y', 4, 7, 1), ('z', 8, 7, 1), ('intensity', 12, 2, 1), ('return_type', 13, 2, 1), ('channel', 14, 4, 1)]
T_END=2026-08-01T14:04:19Z
```

**Three caveats on `run-027`, none of which changes the P4 reading, all stated.**

1. _"WARNING: relay pid STILL alive"_ after SIGKILL. A pid that survives SIGKILL
   is almost certainly a **zombie** — the `ros2 run` wrapper exited and was never
   reaped, so `kill -0` keeps succeeding on an entry that is no longer a running
   process. This was **not confirmed directly**: by the time the hypothesis
   formed, the harness had removed the container, and `/proc/<pid>/stat` is not
   retained. What _is_ measured is the DDS-level fact that settles the point for
   P4's purposes — on `run-024` and `run-025` the post-kill census shows the
   relay **gone from the graph** and the publisher count down to 1.
2. **NDT had already stopped BEFORE the kill on this run.** The buckets show
   1.600 Hz for the first 10 s and then 0.000 Hz from t≈10 s, while the kill
   completed at t≈22 s. So `run-027`'s post-kill zero is _not attributable to the
   kill_; NDT on cell B stopped on its own. This is why `run-025` and `run-026`
   carry the post-kill measurement and `run-027` carries P3. It is also not
   anomalous for this cell: `B/run-025` and `B/run-026` were both **unscoreable**
   by the M5 gate (too few NDT↔GT stamp pairs), the same class as the filed
   `B/run-019`, and `run-027` scored `ndt_rate_ratio=0.039`.
3. The **cloud** rates in that block (2.673 Hz pre → 7.612 Hz post) must **not**
   be read as the relay's removal increasing traffic. A BEST_EFFORT subscription
   discovering on this transport ramps up; the trustworthy figure is the settled
   post-kill one, **7.612 Hz from `concatenate_data` alone**.

### P4 result

|                            | Predicted (pre-declared)                 | Measured                                                                                                   |
| -------------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| P4 pre-kill (2 emitters)   | —                                        | **4.830 Hz** (`run-024`, ladder 4.383–6.145, `--window 100`) ⇒ ratio ≈ **0.48**                            |
| P4 post-kill (1 publisher) | **≥ 9.0 Hz** if the hypothesis were true | **0.000 Hz** — `run-025` (45 s), `run-026` (45 s, unbuffered), `run-027` (25 s, pre-discovered subscriber) |

**No recovery.** Killing the relay did not raise NDT's rate toward 9.0 Hz; it
removed NDT's output entirely. The pre-kill rate was already 0.48 of the
registered expectation, and the post-kill rate is 0.

### 11.4 P3 — is `concatenate_data`'s own output a usable NDT input?

The brief's verbatim command answered `width` on two runs (**6254**, **6198**)
but never `frame_id`: `ros2 topic echo --once --no-daemon` failed twice with
"Could not determine the type for the passed topic", which is the same cell-B
fresh-discovery failure, not an absent topic. `run-027`'s probe answers it
without the CLI, on the first cloud to arrive after the relay is dead — by
construction a `concatenate_data` cloud, since it is then the only publisher:

```text
header.frame_id : 'base_link'
height          : 1
width           : 6202
point_step      : 16
row_step        : 99232
is_dense        : True
data length     : 99232 bytes
fields          : [('x', 0, 7, 1), ('y', 4, 7, 1), ('z', 8, 7, 1),
                   ('intensity', 12, 2, 1), ('return_type', 13, 2, 1), ('channel', 14, 4, 1)]
```

| Usability criterion (brief)   | Measured                                                                                       | Verdict                                      |
| ----------------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------- |
| non-zero `width`              | **6202** points (6198 / 6254 on the other two runs)                                            | **PASS**                                     |
| `frame_id` = `base_link`      | **`base_link`**                                                                                | **PASS**                                     |
| sane `point_step` / structure | 16 B/point, `row_step` 99232 = 6202 × 16, `is_dense` true, x/y/z/intensity/return_type/channel | **PASS**                                     |
| steady rate                   | **7.612 Hz** on the topic, but NDT downstream produces **0 Hz**                                | cloud stream steady; NDT does not consume it |

**`concatenate_data`'s clouds are neither empty nor malformed.** They are
well-formed, non-empty, `base_link` clouds with a sane field layout, arriving at
7.6 Hz. So the spec's branch-(b) trigger — _"P3 fails: empty/malformed clouds"_ —
is **not met**.

An unproven mechanism note, recorded because a later task will want it: the
emission census measured `concatenate_data` republishing clouds under **the same
header stamps the relay already published** (72 duplicate stamps). A downstream
chain that de-duplicates or time-filters on header stamp would drop such a
stream while the clouds themselves look perfectly sane — which is consistent
with what P4 measured. **This was not tested and is not evidence**; it is a
hypothesis for whoever picks the question up.

### 11.5 Adjudication against the spec's branch table, unchanged

| Probe                                           | Predicted (pre-declared)    | Measured                                                                             | Outcome                                            |
| ----------------------------------------------- | --------------------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------- |
| **P1** cell A census                            | **1** (`//relay`)           | **2 advertisers, 1 emitter**                                                         | **failed on advertisement count, MET on emission** |
| **P2** cell B census                            | **2**                       | **2 advertisers, 2 emitters** (72 duplicate stamps, out/in 1.818, loss symmetry 0/0) | **met, on both quantities**                        |
| **P3** concat output usable, relay stopped      | —                           | non-empty (6202), `base_link`, `point_step` 16, `is_dense`, 6 fields, 7.612 Hz       | **clouds usable — (b)'s trigger NOT met**          |
| **P4** NDT rate, relay stopped, vs **≥ 9.0 Hz** | recovery if hypothesis true | **0.000 Hz** across three runs (pre-kill 4.830 Hz ⇒ ratio 0.48)                      | **no recovery — (c)'s trigger MET**                |

- **(a) Recovery** — requires P4 post-kill ≥ 9.0 Hz. Measured 0.000 Hz.
  **Not selected.**
- **(b) Concat output unusable** — pre-declared trigger is _"P3 fails:
  empty/malformed clouds"_. The clouds are neither empty nor malformed.
  **Not selected.**
- **(c) No recovery** — pre-declared trigger is _"P4 stays < 0.9 with a single
  publisher"_. Measured ratio **0.000** post-kill (and 0.48 pre-kill).
  **SELECTED.**

## FINAL RULING: branch (c) — no recovery; the hypothesis is wrong

> **THE CAUSAL WORDING IN THIS SECTION IS OVERSTATED AND IS CORRECTED IN §12.**
> Kept unedited, per the convention that a claim stays in the record with the
> diagnostic that corrected it. P4 selects (c) by **failing to demonstrate
> recovery**, not by demonstrating that killing the relay stops NDT — this run's
> own filed `observer.csv` shows NDT **resuming** with `concatenate_data` as sole
> publisher, 4.2 s after the probe's window closed. **The branch ruling and the
> 9.0 Hz threshold are unaffected**; only the causal claim is.

Note precisely what is and is not concluded. The **differential is real** —
cell B genuinely has two emitters where cell A has one, which fix round 1's
correction restored to the record. What the intervention test shows is that the
differential is **not the cause of the depressed rate**: removing the second
publisher does not restore NDT's rate toward 10 Hz, it stops NDT altogether, and
the rate was already at 0.48 of expectation while both publishers ran. The
hypothesis names double publication as the _cause_; P4 is the test of causation
and it fails.

**Fix mechanism for Task 2: NONE — branch (c) prescribes no harness change.**
Not relay-removal (a): the relay is load-bearing, and killing it is what takes
NDT to zero. Not concat-suppression (b): its trigger is not met, and the
measured pre-kill rate of 0.48 shows suppressing the second publisher would not
reach the 0.9 gate either. `benchmarks/cells/tier4_autoware.sh:538` stays
exactly as it is.

Consequences, all as pre-declared for (c): no `harness:<commit>`
reclassification of B `run-013…022` under `exclusions.md` criterion 3; no
10-fresh-pair static recollection; **no `duel_admissible` flip on A
`run-003…012`** (the spec conditions that on branches (a)/(b), which did not
fire — the A static pair-halves keep `duel_admissible: true`). No gate was
tuned, no threshold moved, no run excluded. Cell B's M5 failures stand and the
verdict carries them.

---

## 12. Fix round 3 — the post-kill zeros are UNATTRIBUTED, and NDT resumed on `run-027`

Added 2026-08-01 after review. No live run was taken for this section: every
figure comes from the **already-filed** `observer.csv` of runs this task filed.
It corrects a claim §11.5 made, and it is the **same class of error as the
count-vs-emission correction in §10** — claiming more than the measurement
carries — which is why it is registered with the same prominence rather than
folded in as a wording tweak.

### 12.1 The measured fact: NDT resumed after the kill, relay gone

`benchmarks/results/B/run-027/observer.csv`:

| arrival (UTC)    | event                                                                       |
| ---------------- | --------------------------------------------------------------------------- |
| 14:03:39.632     | last NDT pose **before** the kill                                           |
| ≈ 14:03:54       | relay kill completes (SIGTERM → SIGKILL escalation)                         |
| **14:04:23.537** | **NDT pose — ≈ 29 s AFTER the kill, `concatenate_data` the sole publisher** |
| **14:04:24.292** | **NDT pose**                                                                |
| 14:04:24.537     | observer stream ends (teardown)                                             |

```bash
python3 - <<'PY'
import csv, datetime
rows = [r for r in csv.DictReader(open("benchmarks/results/B/run-027/observer.csv"))
        if "pose_estimator/pose_with_covariance" in r["topic"]]
for r in rows[-4:]:
    ns = int(r["arrival_system_ns"])
    print(datetime.datetime.fromtimestamp(ns / 1e9, datetime.UTC).strftime("%H:%M:%S.%f")[:-3])
PY
```

**Why §11.3 reported 0.000 Hz anyway.** `probe_relay_kill_transition.py`'s
observation window closed at **14:04:19Z** — **4.2 s before** the first
resumption sample. The zero it printed is a **window artifact, not an absence**.
§11.3's caveat 2 already disclosed that NDT stopped _before_ the kill on this
run; the resumption is the other half of the same picture and was missed until
the filed observer stream was read directly.

### 12.2 The structural gap: no run pairs a pre-kill baseline with a post-kill measurement

Each run checked against its own filed `observer.csv`:

| run         | pre-kill NDT baseline                                   | post-kill NDT measurement       | why it cannot carry a causal claim                                                                                                              |
| ----------- | ------------------------------------------------------- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `B/run-024` | **yes** — 331 poses, clean 4.830 Hz                     | **none**                        | observer stream ends 13:46:46.346, **7 s before** the kill at 13:46:53                                                                          |
| `B/run-025` | none of its own                                         | zero over ≈ 50 s                | kill instant never timestamped; last NDT pose 13:51:41.320 is ≈ 3.7 s **before** the post-kill census, so NDT silence already preceded the kill |
| `B/run-026` | none of its own                                         | zero over ≈ 43 s                | relay confirmed **still alive** 3 s after `kill`; NDT already down; run M5-**unscoreable**                                                      |
| `B/run-027` | 1.600 Hz, then 0 from t≈10 s — **12 s before** the kill | 2 poses, then the window closed | NDT stopped **before** the kill and **resumed** after it                                                                                        |

**No run pairs a live pre-kill NDT baseline with a post-kill measurement on the
same stack.** The post-kill zeros are therefore **unattributed**: nothing in the
filed data establishes that the kill caused them, and `run-027` positively shows
NDT returning without the relay.

### 12.3 The ruling is unaffected — (c) stands by elimination

Restated correctly: **P4 selects (c) by failing to demonstrate recovery**, not by
showing that killing the relay stops NDT.

- **(a) Recovery** requires **≥ 9.0 Hz sustained** post-kill. The best post-kill
  reading on any of the four runs is `run-027`'s 2 poses over ≈ 30 s ≈ **0.07
  Hz** — two orders of magnitude short. No plausible correction for any confound
  above reaches 9.0 Hz.
- **(b)** is genuinely unmet: P3 passed; concat's output is a well-formed,
  non-empty `base_link` cloud stream.
- **(c)** is what remains.

The branch table, the 9.0 Hz threshold and the fix mechanism (**NONE**) are
untouched, and no re-run is required. What changes is only the claim P4 is said
to support.

Two claims from §11.5 that are **withdrawn**, explicitly: that the relay is
"load-bearing", and that removing the second publisher "stops NDT entirely".
Neither is established by these four runs.

### 12.4 The P3-vs-P4 tension, confronted

§11.4 left "a usable 7.6 Hz cloud stream drives NDT to exactly zero" resting
entirely on the untested duplicate-stamp hypothesis, eight lines below the
disclosure that NDT had stopped on its own — without putting the two together.

**The `run-027` resumption substantially dissolves the tension.** NDT did **not**
sit at zero on `concatenate_data`'s output; it returned ≈ 29 s after the relay
died. What the filed data shows is a slow, intermittent, unreliable NDT on cell
B on **both** sides of the kill — consistent with this cell's already-registered
instability (`B/run-025` and `B/run-026` M5-**unscoreable**, `run-027` scoring
`ndt_rate_ratio=0.039`, and §4.1 of `results/PROVENANCE.md` recording a filed
range of 0.257–0.989).

So the duplicate-stamp mechanism has **less** to explain than §11.4 implied. It
remains **NOT TESTED** — a hypothesis for whoever picks it up, never a finding,
wherever it appears in this record.
