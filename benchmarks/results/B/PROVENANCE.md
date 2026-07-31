# Cell B (`tier4-native`) — provenance boundary of the committed run data

**Written 2026-07-30 by Task 17b** (cell B binary-vs-pinned-source provenance),
which the campaign scheduled before Task 18 precisely so the primary duel would
not collect twenty more runs under the condition this document describes.

Read this before citing any number out of `benchmarks/results/B/**`. It states
what is established about those runs' provenance, what is not, and which claims
already in the record depend on the part that was not.

Nothing under `benchmarks/results/B/run-*/` is modified by this document. Every
filed run's data is byte-identical to what was collected.

---

## 0. The one-line version

Every committed cell-B run was produced with **no check binding the running
LiDAR binary to its pinned source**. Task 17b closed that gap going forward (a
named preflight gate, `benchmarks/scripts/verify_tier4_artifact.sh`) and, for
the runs already filed, reconstructed the binding after the fact from the
artifacts on disk. The reconstruction says the binary **did** match the pin on
the LiDAR path — which means the record's registered reading that cell B's wire
`point_step` is **16** is **refuted**, and several derived figures built on it
have to move. The reconstruction is not as strong as a digest recorded at run
time, and section 5 says exactly where it is weaker.

---

## 1. What was ungated, and over which runs

Cell A's editor-plugin staleness gate `scripts/e2e/verify_editor_artifact.sh`
has exactly one call site, `scripts/e2e/run_e2e.sh:126`, which cell A reaches
through `benchmarks/cells/extension.sh:192`. Before Task 17b, neither
`benchmarks/cells/tier4-native.sh` nor `benchmarks/cells/tier4_autoware.sh`
called it or anything like it: the B family booted the shared engine's
`UnrealEditor` against `$BENCH_CARLA_TREE/.../CarlaUnreal.uproject`
(`benchmarks/cells/tier4-native.sh:27-28`, boot at `:175-177`) with no artifact
check.

What the manifests recorded instead — verified on
`benchmarks/results/B/run-012/manifest.json` — is `placement.carla_tree`
(a **path**, `/home/youtalk/src/carla-autoware-native`),
`placement.engine_build_id` (which binds the **engine**, not the plugin),
`placement.run_mode`, `carla_version`, `harness_git_sha` and `patches_git_sha`
(both of which are **this** repo, not the tier4 fork). No git SHA, no artifact
digest, no build timestamp for the tree whose binary produced the measurements.

Affected: **all twelve** run directories, `run-001` … `run-012`, started
2026-07-30 02:17:48 through 08:36:48 local. All twelve are already
`excluded: true` in their manifests (`crash:cell-launch` ×6,
`crash:collect_gt` ×1, `gate:arm-failed` ×5), so no scored duel metric rests on
them — but their observer data **is** cited in `benchmarks/README.md`'s
descriptive findings (per-message byte medians, sensing-chain rate deficits,
the 8.78× CPU figure), and those citations are what this boundary bears on.

---

## 2. What Task 17b established about the binary that ran (D1)

Four independent lines. Each is labelled **measured** (a command was run and
its output read), **derived** (arithmetic on measured values), or **inferred**.

### 2.1 The caller binary imports only the ten-field `SetDataEx` — measured

`nm -DC` on the plugin actually present in the tier4 tree
(`.../Plugins/Carla/Binaries/Linux/libUnrealEditor-Carla.so`):

- it **defines** `carla::ros2::ROS2::ProcessDataFromLidar(unsigned long,
  unsigned int, carla::geom::Transform, unsigned int, float, float,
  carla::sensor::data::LidarData&, void*)` at `0x8014c0` (`T`);
- its only undefined `CarlaLidarPublisher` references are the constructor,
  `Init`, `Publish`, and
  `SetDataEx(int, unsigned int, unsigned long, unsigned long, float*,
  unsigned long, unsigned int*, std::vector<float> const&)`.

There is **no undefined reference to either `CarlaLidarPublisher::SetData`
overload**. Both overloads exist — `libcarla-ros2-native.so` defines
`SetData(…, std::vector<unsigned char>&&)` at `0x124c40` and
`SetData(…, float*)` at `0x124b00` alongside `SetDataEx` at `0x1252c0` — so the
four-field code is compiled, and the caller does not import it. A function
existing is not evidence it is called; here the caller's import table is the
evidence that it is **not**.

The call site itself, disassembled inside `ProcessDataFromLidar`:

```text
801784: call 8753b0 <carla::ros2::CarlaLidarPublisher::SetDataEx(...)@plt>
801790: call 8753c0 <carla::ros2::CarlaLidarPublisher::Publish()@plt>
```

That matches the pinned source's sole `SetDataEx` call site,
`carla-autoware-native` `LibCarla/source/carla/ros2/ROS2.cpp:986` (signature at
`:959-967`), and it matches the eight-parameter,
`channel_count`/`upper_fov`/`lower_fov`-carrying signature that only the
`SetDataEx` era has.

That call site is **not** unconditional: it sits inside `if (sensors.first) {`
at `ROS2.cpp:970`, so it runs only once the LiDAR has a registered publisher.
The substance is unaffected, because no *other* branch reaches
`CarlaLidarPublisher` at all — the `SetData` at `:992` is
`CarlaTransformPublisher`'s, on the TF half of the same function — so
`SetDataEx` remains the only way a cloud from this sensor reaches the wire, and
the disassembly above shows that is the entry point the shipped binary calls.

### 2.2 The artifacts are not stale — measured

| item                                        | mtime        | local time          |
| ------------------------------------------- | ------------ | ------------------- |
| newest file under the tier4 build sources    | `1785196190` | 2026-07-27 16:49:50 |
| `libcarla-ros2-native.so`                    | `1785268031` | 2026-07-28 12:47:11 |
| `libUnrealEditor-Carla.so`                   | `1785268164` | 2026-07-28 12:49:24 |
| earliest cell-B run (`run-001` `started_at`) | —            | 2026-07-30 02:17:48 |
| latest cell-B run (`run-012` `started_at`)   | —            | 2026-07-30 08:36:48 |

Source → build → every run, strictly ordered, with no rebuild between the runs
(a rebuild would have left an mtime after them). The tier4 tree is at
`6315b856f8faf2118578322eb20a2b902a45a384`, which matches `benchmarks/pins.yaml`
`tier4_carla_fork.sha: 6315b856f`, and its working tree carries **exactly** the
three registered patches and nothing else. None of them touches the LiDAR
publish path.

The check behind that "exactly" is `git apply --reverse --check <patch>` run in
the tier4 tree for each of `0001-toolchain-libm.patch`,
`0002-glibc-compat.patch` and `0003-autoware-demo-params.patch` — all three exit
0, i.e. each patch's post-image is present in the tree verbatim. `git status
--porcelain -uall` then lists exactly the four paths those three patches write
and nothing more: `CMake/Toolchain.cmake`, `LibCarla/CMakeLists.txt` and
`PythonAPI/examples/autoware_demo.py` modified, plus untracked
`LibCarla/source/carla/GlibcCompat.c`. `--check` does not write, and the
porcelain listing was taken after the runs. What this is *not* is
`patches_sha256`: that key digests the patch **files in this repo**, so it
detects a change to the registered patch set and says nothing about the tier4
tree's content — see §6, where the tree-side counterpart is
`tier4_worktree_content_sha256`.

**The stale-build-artifact hypothesis registered at `benchmarks/README.md:1520`
is therefore REFUTED**, and it stays in the record with what refuted it: the
mtime ordering above, and the import table in 2.1.

### 2.3 The `point_step 16` witness is not CARLA's cloud — measured

The witness the record cites,
`benchmarks/results/B/run-012/tier4-autoware.log:555`, reads in full:

```text
[component_container_mt-1] [WARN] [1785425851.564993227]
[localization.util.crop_box_filter_measurement_range]: Invalid PointCloud:
row_step mismatch. Expected: 99152 (width 6197 * point_step 16), Got: 0.
Frame: 'base_link', Stamp: 19.059040338 ...
```

Three properties of that cloud are incompatible with CARLA's publisher:

- **`Frame: 'base_link'`.** CARLA's cloud is `velodyne_top` — as the *other*
  warning in the same logs confirms directly
  (`sensing.lidar.top.crop_box_filter_self`: `is_dense is false`,
  `Frame: 'velodyne_top'`).
- **`Got: 0` for `row_step`.** The pinned publisher sets `row_step` non-zero on
  **both** code paths — in `carla-autoware-native`,
  `LibCarla/source/carla/ros2/publishers/CarlaLidarPublisher.cpp:211`
  (`row_step(width * sizeof(float))`, four-field) and `:312`
  (`row_step(cloud_width * offset)`, ten-field). Neither can emit `row_step 0`.
- **`width 6197`** against a derived ~7 550 points per CARLA cloud (2.4) — a
  cropped, downstream cloud.

Where that cloud comes from is in the harness's own comment:
`benchmarks/cells/tier4_autoware.sh:431-432` states `RELAY_IN` — which is
`/sensing/lidar/top/pointcloud_before_sync` (`:43`) — "is already in
`base_link`", i.e. it is the output of Autoware's own sensing preprocessing,
byte-relayed by `ros2 run topic_tools relay` onto
`/sensing/lidar/concatenated/pointcloud` (`:44`, `:458`), which is what
`crop_box_filter_measurement_range` consumes. So the 16 is Autoware's own
re-packed point layout describing an Autoware-produced cloud. **It was never a
measurement of what CARLA put on the wire.**

Full tally over all twelve runs (`run-001` has no `tier4-autoware.log`), so the
counts in the record can be checked rather than restated:

| warning                                                        | frame          | occurrences |
| -------------------------------------------------------------- | -------------- | ----------- |
| `crop_box_filter_measurement_range` row_step mismatch, `point_step 16` | `base_link`    | **536**     |
| `sensing.lidar.top.crop_box_filter_self` is_dense is false       | `velodyne_top` | **552**     |

`point_step 16` appears 536 times and **no other `point_step` value appears
anywhere** in any B log. Note this **extends the brief's ledger**, which said
the witness is present across `run-007`…`run-012`: it is present in
`run-002`…`run-012`, every run that has a log. It is also worth stating plainly
that the CARLA cloud — the `velodyne_top` one — draws a complaint about
`is_dense` and **never** about `point_step` or `row_step`, because Autoware only
prints those when they disagree.

### 2.4 A constant-free wire test on the committed data — derived

For `sensor_msgs/msg/PointCloud2` under XCDR1, everything before the point
payload is a fixed-length header for a fixed field list and frame_id, so the
serialized size is `C + point_step × N`. That gives a test that needs no
knowledge of `C`:

- a **32-byte** stride puts every message in **one** residue class mod 32;
- a **16-byte** stride puts them in **one class mod 16**, which is **two**
  classes mod 32 — the two alternating as the point count `N` changes parity.

Measured over the committed `observer.csv` rows for
`/sensing/lidar/top/pointcloud_raw_ex`:

| cell  | runs                | rows      | distinct residues mod 32 |
| ----- | ------------------- | --------- | ------------------------ |
| **B** | `run-007`…`run-012` | **3 348** | **1** (all ≡ 21)         |
| **A** | `run-001`, `run-002` | 4 519     | **1** (all ≡ 24)         |

Cell A is the control: its 32-byte layout is source-established in the extension
fork `carla-autoware-integration`, at
`LibCarla/source/carla/ros2/publishers/PointCloudFieldsLayout.h:59-70` (ten
descriptors) with `ExtendedLidarPointStep()` returning 32 at `:74`, and it
produces exactly the single-class signature. Cell B produces it too.

**How much the test proves, stated exactly.** Under a 32-byte stride the
single-class result is *forced*. Under a 16-byte stride it is still *possible*,
but only if every one of the 3 348 clouds carries an even point count. That
even-`N` requirement is the *same* observation re-expressed — not a second,
independent check on it — and the only way to see that is to have both
constants, so they are derived below rather than asserted:

- the four-field constant is `C₄ = 149` and the ten-field one `C₁₀ = 309`;
- `149 ≡ 309 ≡ 21 (mod 32)`, which is *why* both readings land on class 21 and
  why the observed class alone cannot separate them;
- equating the two readings of one byte count, `309 + 32·N₃₂ = 149 + 16·N₁₆`,
  gives `N₁₆ = 2·N₃₂ + 10`, even for every integral `N₃₂`.

So "3 348 of 3 348 even" follows algebraically from the single-class observation
plus the two constants; counting it as a separate confirmation would be
double-counting one measurement. The evidential content of 2.4 is exactly the
table above — 3 348 rows, one class — which is why **2.4 corroborates and 2.1
decides**: on its own, 2.4 could not.

**The two constants, derived.** Positions count from the start of the CDR stream
(just after the 4-byte encapsulation header), each member aligned to its own
width:

- **header prefix — 40 B** for `frame_id = velodyne_top`: `stamp.sec` 4,
  `stamp.nanosec` 4, the `frame_id` length 4 and its 13 bytes (12 chars + NUL)
  padded to 16, `height` 4, `width` 4, the field-sequence length 4;
- **one `PointField` — `16 + ceil4(len+1)` B**: name length 4, name bytes padded
  to a 4-boundary, `offset` 4, `datatype` 1 padded to 4 because `count` follows,
  `count` 4;
- **everything else — 21 B**, independent of the field list: the 4-byte
  encapsulation header at the very front, then after the fields `is_bigendian` 1
  padded to 4, `point_step` 4, `row_step` 4, the data-sequence length 4, and
  `is_dense` 1 sitting after the payload.

`x`/`y`/`z` cost 20 B each and `intensity` 28 B, so the four-field list is 88 B
and `C₄ = 40 + 88 + 21 = 149`. The ten-field list adds `return_type` 28,
`channel` 24, `azimuth` 24, `elevation` 28, `distance` 28 and `time_stamp` 28
for 248 B, giving `C₁₀ = 40 + 248 + 21 = 309`. Both fit
`C = prefix + fields + 21`, since every prefix and every field size is a
multiple of 4 and the tail's only unaligned members are the two `bool`s.

At `C₁₀ = 309` and a 32-byte stride, every cell-B size is an exact fit to
`309 + 32N` with integral `N` (as it must be, given the class-21 observation):
per-run medians **7 528 / 7 545 / 7 550 / 7 549 / 7 545 / 7 550** points per
cloud across `run-007`…`run-012` — i.e. **7 528–7 550** — pooled mean 7 547.7,
range 7 313–7 749. The low end of that range is `run-007`, whose median rests on
only 3 rows (626–699 for each of the others); the other five span 7 545–7 550.

**One loose end, named rather than papered over.** A and B sit in *different*
classes, 24 vs 21. The derivation above rules out a different field list or
`frame_id` as the cause: `C = prefix + fields + 21` with both terms multiples of
4, so `C ≡ 21 (mod 4)` for *every* PointCloud2, and 24 is `≡ 0`. The 3-byte gap
must therefore come from the byte figure itself rather than the message layout —
padding the serialized payload up to a 4-byte boundary on one of the two
measurement paths would produce exactly 21 → 24, but that is a **conjecture**,
not something this task chased. It does not bear on the test, which counts
classes rather than identifying them, and 3 B on a ~242 KB cloud is 0.001 %,
below anything the byte-rate comparison resolves.

### 2.5 Verdict — brief outcome (b)

**The binary matched the pin on the LiDAR path, and the 16 came from somewhere
else** (Autoware's own preprocessed cloud). Cell B's clouds on
`/sensing/lidar/top/pointcloud_raw_ex` are **ten-field, `point_step` 32**, the
same layout cell A emits.

Not claimed: that the binary matched the pin on *every* path. 2.1 and 2.2 are
about the LiDAR publish path and about build ordering for the tree as a whole;
no other subsystem was disassembled.

---

## 3. Claims in the record this changes (D3)

`benchmarks/README.md` is **FROZEN**, and a measured value is outside the Owner
Ruling 1 amendment envelope, so **nothing there is edited by this task**. The
corrections are recorded here, at the results the reader is citing.

| where                                     | claim as registered                                                                          | status after 2.1–2.4                                                                                                                                                                                       |
| ----------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `README.md:1503`                          | "**Measured wire** — `point_step` **16**"                                                     | **REFUTED.** Its two legs were the byte medians (which fit both strides, so they were never evidence of 16) and the Autoware warning (which is about a `base_link` cloud, 2.3).                              |
| `README.md:1520-1530`                     | leading hypothesis: a **stale build artifact**                                                | **REFUTED** by the mtime ordering and the import table (2.1, 2.2).                                                                                                                                          |
| `README.md:1531-1537`                     | "nothing binds cell B's running LiDAR binary to its pinned source … carry that caveat on every cell-B number" | **TRUE of the filed runs and still true** — see §5. **No longer true of future runs**, see §6.                                                                                                              |
| `README.md:3620-3624`                     | "**16 006 vs 15 113** derived points — **5.9%** apart"; "both cells deliver ~53% of nominal"  | **The B half is wrong.** 15 113 was `median ÷ 16`. At the established stride it is **~7 547**, so the derived point gap is **~2.12×**, not 5.9%, and the "~53% of nominal" symmetry does not hold as stated. |
| `README.md:3626-3630`                     | "cell A ships **2.118×** the bytes **for the same point count**"                              | The **2.118× byte ratio is measured and survives**; "for the same point count" is **false**. At an equal 32 B stride the byte ratio simply *is* the point-count ratio: A ships ~2.12× the **points**.        |
| `README.md:3626-3630`                     | `one_hop_wall_ms` / `lidar_to_ndt_sim_ms` "biased **against cell A**", A-favourable result conservative | **Direction unchanged, reason changed.** A still moves 2.118× the bytes per message, so the bias direction stands; it is now a point-count difference at equal per-point cost, not a layout difference.      |
| `README.md:3671-3675`                     | "the 8.78× CPU finding keeps its direction, because a 16 B/point cloud is _less_ data"        | **Direction unchanged, reason refuted.** B still emits fewer bytes per message (241 813 vs 512 184, measured), but not because of a smaller stride. The "correcting it could only move cell B's cost up" step is void — there is nothing to correct. |
| `README.md:639`, `:2103`, `:2120`         | cell B's clouds are "**~460 KB**"                                                             | **Wrong** — see §4.                                                                                                                                                                                         |
| `results/CAL-rmw/PROVENANCE.md:307-343`   | "OPEN INCONSISTENCY … ~460 KB against ~242 KB … **Task 17b** is where this gets settled"      | **SETTLED** here, §4.                                                                                                                                                                                       |
| `cells/tier4_autoware.sh:78-80`           | per-message size lands "within 4% either way"                                                 | Still falsified (2.118×), unchanged by this task. Left untouched per the note already in the record.                                                                                                        |

The register at `README.md:1488-1503` frames this as "pinned source says 32,
measured wire says 16". With 2.3 in hand there is **no contradiction to
resolve**: both sides say 32, and the 16 was a reading of a different cloud. The
parenthetical already in the record — that the `width` in those log lines is a
downstream cropped cloud "so only the `point_step` figure is load-bearing there"
— is the step that failed: if the cloud is downstream, its `point_step`
describes the downstream re-packing too.

---

## 4. The ~460 KB vs ~242 KB discrepancy (D4) — SETTLED

**~242 KB is correct.** The measured per-message medians for
`/sensing/lidar/top/pointcloud_raw_ex` are 241 205 / 241 749 / 241 909 /
241 877 / 241 749 / 241 909 B over `run-007`…`run-012`; the pooled mean over
3 348 rows is **241 834.5 B**. `benchmarks/README.md:3928` already carries
**241 813 B/msg** as cell B's measured median — so the frozen document contains
both figures, and the ~460 KB at `:639`, `:2103` and `:2120` is contradicted by
its own later table.

**Where ~460 KB came from — derived, and consistent to the byte.**
`cells/tier4_autoware.sh:78-79` registers cell B's nominal points per message
as `288000 * 0.1 = 28800`, quoted verbatim into the frozen document at
`README.md:3920-3921` (the demo's defaults: `--lidar-pps 288000`,
`--lidar-rotation-hz 10.0`, `autoware_demo.py:740-752`; cell B passes no
`BENCH_TIER4_SWEEP_ARGS`). `28 800 × 16 B = 460 800 B ≈ 460 KB`. So the figure
is a **derivation**, not a measurement: nominal **rays** per revolution × the
now-refuted 16 B stride. It is wrong twice, in opposite directions —
~3.8× too many points (rays cast, not returns received) and 2× too few bytes per
point — netting the ~1.9× the CAL-rmw document noticed. That the ratio has the
"shape" of a `point_step` 16-vs-32 difference was a coincidence of those two
errors, and is not evidence of one.

**The third figure, bounded not settled.**
`benchmarks/patches/tier4-native/README.md:476` records 64–76 KB on the same
topic from a live acceptance check. At the established 32 B stride that is
~2 000–2 400 points per cloud, roughly a third of what the filed runs show. It
is not reconcilable with the filed runs at any stride and is therefore a
**different sensor configuration**, not a third reading of this one. Which
configuration is not recorded there, and settling it needs a live run with the
arguments logged — out of scope here and not required by anything.

**No edit to `README.md` is made.** Substituting a measured value into a frozen
document is outside Owner Ruling 1 by its own terms.

---

## 5. What is still not established about the filed runs

Stated as the limit it is, because §2 is a **reconstruction after the fact**,
not a record made at run time.

1. **No digest was recorded while the runs executed.** The link from "the binary
   I disassembled" to "the binary that ran" is the mtime ordering in 2.2:
   the artifact's mtime precedes every run and postdates every source, and no
   rebuild happened after. That is strong but it is not a hash captured at
   launch — a replacement that preserved timestamps would defeat it. Nothing
   suggests one happened; it is named because it is the actual gap.
2. **The tier4 tree's identity was never in the manifests**, so the check in 2.2
   is against the tree as it stands **today**, not as recorded then. If that
   tree changes before anyone re-reads this, the reconstruction is no longer
   reproducible from the committed record alone.
3. **Only the LiDAR path was examined.** Camera, IMU, GNSS and the control
   subscriber paths were not disassembled. §2.5's verdict does not extend to
   them.
4. **The relay/concatenate double-publisher defect stands**
   (`cells/tier4_autoware.sh:434-456`): `/sensing/lidar/concatenated/pointcloud`
   carried two publishers during the filed runs. That is a separate, already
   registered finding, unaffected either way by this task.

**What would close 1 and 2 for the filed runs:** nothing can, retroactively —
the evidence was not captured. They are closed for **future** runs by §6, which
records the digest at launch. That is the whole reason this task ran before
Task 18.

---

## 6. What is gated from now on (D2)

`benchmarks/scripts/verify_tier4_artifact.sh` — the B family's counterpart to
`scripts/e2e/verify_editor_artifact.sh`, env-driven the same way
(`TIER4_TREE=${TIER4_TREE:?…}`).

- **Refuses**, with the named check `tier4-artifact-stale`, when either
  `libUnrealEditor-Carla.so` or `libcarla-ros2-native.so` is older than the
  newest file under the tier4 tree's build sources. Also named and refused:
  `tier4-tree`, `tier4-artifact-missing`, `tier4-source-roots`,
  `tier4-artifact-older-than-head`, `tier4-stale-ack-unexplained` and
  `tier4-identity`. A refusal happens **before** `run.sh` writes a manifest, so
  no run is filed and no exclusion criterion is consumed.
- **Has one acknowledgeable refusal**, `tier4-artifact-stale`, because mtime is
  not content. Re-applying the registered patches, a `git checkout`, a `stash
  pop` or an editor save all push a scanned source's mtime past the artifacts
  with the **content unchanged**
  (`benchmarks/patches/tier4-native/README.md:15-17` documents exactly that
  `git apply`), and the remedy the refusal names first — rebuild — is forbidden
  mid-campaign, which would leave the B family refused with no way out.
  `TIER4_STALE_ACK` takes a **reason string**, never a boolean: with it set, the
  refusal becomes a loud `WARN` and the run proceeds carrying
  `tier4_stale_ack=applied`, `tier4_stale_ack_reason=<the reason>` and
  `tier4_stale_ack_artifacts=<which .so>` in its own manifest. Set-but-empty is
  itself a refusal (`tier4-stale-ack-unexplained`) — an unexplained
  acknowledgement is not expressible. All three keys are emitted on **every**
  run, so `tier4_stale_ack=none` (nothing was stale) and `unused` (set, but
  nothing was stale) are distinguishable from a manifest written before the key
  existed. `tier4-artifact-older-than-head` is deliberately **not**
  acknowledgeable: it can only fire when HEAD moved, which is real content
  change, not mtime drift. What makes the reason checkable rather than merely
  asserted is `tier4_source_sha256`: equal digests across two runs prove the
  scanned sources' content is identical however the mtimes moved.
- **Records identity** on stdout as `KEY=VALUE`, which `preflight.sh` forwards
  into `manifest.json`'s `placement` block: `tier4_git_sha`, `tier4_worktree`
  (`clean` / `registered-patches` / `diverged:+extra:-absent` against the
  registered patch set), `tier4_worktree_paths_sha256`,
  `tier4_worktree_content_sha256`, `tier4_source_sha256`, `tier4_plugin_sha256`,
  `tier4_ros2_native_sha256`, the three mtimes the staleness verdict used, and
  the three `tier4_stale_ack*` keys below.

  **Which of those are content and which are not**, because the distinction is
  the whole value of the block: `tier4_plugin_sha256` and
  `tier4_ros2_native_sha256` digest the two `.so` files, `tier4_source_sha256`
  digests every regular file under the four scanned source roots, and
  `tier4_worktree_content_sha256` digests `git diff HEAD --binary` plus the
  content of each untracked file. Those four are identities.
  `tier4_worktree_paths_sha256` is **not** — it hashes the sorted list of dirty
  **paths**, so it moves when a path appears or disappears and stays put when a
  file listed there is edited. It is a cheap divergence tripwire, and it was the
  only worktree key in the first version of this gate, which meant an edit to
  `PythonAPI/examples/autoware_demo.py` — registered patch `0003`, the file that
  sets `--lidar-pps` and `--lidar-rotation-hz`, i.e. the very sensor
  configuration §4 leaves open — would have reported an unchanged digest.
  `tier4_worktree_content_sha256` is what closes that, and it is the tree-side
  counterpart to `patches_sha256` discussed in §2.2.
- **Called from two places** so a launcher invoked directly cannot skip it:
  `benchmarks/scripts/preflight.sh` (section 7, for `approach = tier4-native`,
  which is what puts the keys in the manifest) and
  `benchmarks/cells/tier4-native.sh`, before the editor boots, on both `plan`
  and `up`.
- **Tested** in `tests/benchmarks/test_verify_tier4_artifact.py`, host-only, no
  docker and nothing booted: fresh artifacts pass; a stale editor plugin and a
  stale native lib each refuse by name; an acknowledged staleness WARNs, records
  and does not block; an unexplained acknowledgement cannot pass, on a stale
  tree or a fresh one; an acknowledgement that was not needed is recorded as
  `unused`; the HEAD-staleness refusal ignores the acknowledgement; a tree nested
  inside another repository is refused; an identity-reader failure still prints a
  named check; and `tier4_source_sha256` is unchanged by an mtime-only touch
  while `tier4_worktree_content_sha256` moves where the paths digest cannot.
  Each of those properties was confirmed to **fail** against a deliberately
  mutated gate (accepting an unexplained acknowledgement: 4 failures; ignoring
  the acknowledgement: 3; dropping `-uall` from the porcelain read: 1).

Values on the tree as of 2026-07-30, re-read unchanged on 2026-07-31 when the two
content digests were added, for whoever compares a future manifest against the
runs described here:

```text
tier4_git_sha=6315b856f8faf2118578322eb20a2b902a45a384
tier4_worktree=registered-patches
tier4_worktree_paths_sha256=880c2127133214ea5fee1dff1efbf1b8b5c2e9a3a3a9de10156bc299026eafc6
tier4_worktree_content_sha256=23038d8c20a6a0691f941bd9f0be427819a8151c81088c30cf67222764ed3e49
tier4_source_sha256=eb8aa9af8d91b65a587409771db0c08a47f3584076a06e18cd665d13db71f5e5
tier4_plugin_sha256=26f95decb0b18dda86f73f6c1ebd2445a287d8dedde3f1cb1544bfffbd093c4e
tier4_ros2_native_sha256=4485f7b6b74404729a605107a6b2c851286cd942c89db416e811677fc62f3149
tier4_stale_ack=none
tier4_stale_ack_reason=-
tier4_stale_ack_artifacts=-
```

The two `.so` digests are of the same files §2.2 dates and §2.1 disassembles, so
a future manifest that reproduces the four content digests above — the two `.so`
ones plus `tier4_source_sha256` and `tier4_worktree_content_sha256` — is running
against the same binaries built from the same tree this document describes.

A `diverged:` worktree WARNs and records but does **not** refuse. The gate's
refusals are all about whether the recorded identity can be *trusted* — a
missing artifact, a tree that is not a tree, an artifact older than the source
or than HEAD, an identity that could not be read. Whether a *legitimate* tree
state is acceptable is a different question, and turning a stray local edit into
a run-blocking condition would add an exclusion criterion the pre-registration
does not carry. Divergence is therefore recorded in full
(`tier4_worktree=diverged:+extra:-absent` plus
`tier4_worktree_content_sha256`) and left for analysis to weigh.
