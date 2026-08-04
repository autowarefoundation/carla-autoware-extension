# Gap catalog: tier4-native capabilities vs the extension architecture

This document is the C3 deliverable of the three-approach evaluation
(`2026-07-27-three-approach-evaluation-design.md` in `claude-superpowers`):
for every tier4-native capability — main plus the major unmerged side
branches — argue a reproduction path on the extension architecture, classed
already-exists / extension-side work / CARLA-core seam work, with an S/M/L
effort estimate. This file pins the snapshot every later entry cites and
lists the working set of branches to catalog; the entries themselves (What it
does / Maturity evidence / Reproduction path / Effort class / Verified by) are
Task 2 (main) and Task 3 (side branches).

## 1. Snapshot

**Remote:** `tier4` → `git@github.com:tier4/carla-autoware-native.git`, read
from the archaeology checkout at `~/src/carla-autoware-native` (a git
worktree sharing the shallow `.git` of `~/src/carla`; see §1.2).

**Fetched:** 2026-08-04 23:15 UTC, via:

```bash
cd ~/src/carla-autoware-native && git fetch tier4 --prune
```

**Baseline for "commits ahead":** `tier4/autoware-support`, per this task's
own instruction — **not** `tier4/main`, which is the repository's actual
GitHub default branch (`git remote show tier4` → `HEAD branch: main`) but
which has diverged from `autoware-support` (§1.3). All "commits ahead"
figures below are `git rev-list --count tier4/autoware-support..tier4/<branch>`.

### 1.1 Branch snapshot and spec-name resolution

Sourced with:

```bash
git branch -r --list 'tier4/*' | sort
git log -1 --format='%H %ci' tier4/<branch>          # tip SHA + date, per branch
git rev-list --count tier4/autoware-support..tier4/<branch>   # commits ahead
git merge-base --is-ancestor tier4/<branch> tier4/autoware-support   # merged?
```

65 `tier4/*` branches exist as of the fetch above. The **Resolution** column
records, for each branch, whether it is the (or a) match for one of the 10
spec-named capabilities (`RGL GPU lidar, lidar-udp-raw-packet,
pandar128e4x-highres-udp, agnocast-integration, cyclonedds-support,
autoware-v2i-publisher, lanelet2-traffic-light, docker-dev-env, steering-lut,
gnss-pose-publish/pose-publisher`) or was added because the branch scan found
it and the spec didn't name it.

| Branch                                                   | Tip SHA                                    | Last commit date | Commits ahead of `tier4/autoware-support` | Resolution                                                                                    |
| -------------------------------------------------------- | ------------------------------------------ | ---------------- | ----------------------------------------- | --------------------------------------------------------------------------------------------- |
| `tier4/autoware-support`                                 | `6315b856f8faf2118578322eb20a2b902a45a384` | 2026-04-08       | baseline                                  | baseline (commits-ahead-of-main reference point)                                              |
| `tier4/experiment/cyclonedds-support`                    | `ab8cc46349c54090acaad58a9785659f37122cbe` | 2026-04-06       | 57                                        | spec: cyclonedds-support (primary — matches spec's own "tier4 experiment branch" wording)     |
| `tier4/feature/agnocast-integration`                     | `cb6539a45d8a826467d237d1ab9fa28881b31ab3` | 2026-04-07       | 14                                        | spec: agnocast-integration (exact match)                                                      |
| `tier4/feature/autoware-demo-ros-configuration`          | `7dbdb0f11dbc7380899611934bb4b43a1fe3167c` | 2025-08-26       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/feature/autoware-plugin`                          | `dbf49e4a1d3d46a0d62da5e79c72ac8d14a2e774` | 2025-10-23       | 1†                                        | not spec-named; added by branch scan                                                          |
| `tier4/feature/autoware-publishers`                      | `e4ab17ecce9c30014743d9b706b5d47e80e82766` | 2025-08-22       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/feature/autoware-subscriber`                      | `194c99a07a442daf2ec25063fd6c5067deca4848` | 2025-08-22       | 8                                         | not spec-named; added by branch scan                                                          |
| `tier4/feature/autoware-subscribers`                     | `f77db82657f572e2a7538d45be025c8ee7d4b35f` | 2025-08-22       | 7                                         | not spec-named; added by branch scan                                                          |
| `tier4/feature/autoware-v2i-publisher`                   | `1ab5fecd532979fbafda137f6c2fc120c6e72f37` | 2026-06-10       | 278                                       | spec: autoware-v2i-publisher (exact match)                                                    |
| `tier4/feature/build-dependency-share-tool`              | `fdbf018d29329b26977bd5530ad8c72b9b495bab` | 2026-04-16       | 1†                                        | not spec-named; added by branch scan                                                          |
| `tier4/feature/docker-dev-env`                           | `89c44284c0e07ed9cf7cde110572a0b0b31a7183` | 2026-04-12       | 1†                                        | spec: docker-dev-env (exact match)                                                            |
| `tier4/feature/gnss-pose-publish`                        | `99a8676c9cbc6ce513435a3358ee0dc161ddcff7` | 2025-08-29       | 0                                         | spec: gnss-pose-publish/pose-publisher (already merged into baseline)                         |
| `tier4/feature/lanelet2-traffic-light`                   | `2dbe5a6c25b7984059b072a2ab70ae2ce34737a5` | 2026-06-11       | 273                                       | spec: lanelet2-traffic-light (exact match)                                                    |
| `tier4/feature/lidar-udp-raw-packet`                     | `6437fbcc51fca6bdc5d35dbd8ec51cdd8e1c1a18` | 2026-06-20       | 339                                       | spec: lidar-udp-raw-packet (exact match)                                                      |
| `tier4/feature/override-steering-curve`                  | `fb2160dc7e69bd2830924e4fb26bd7c2853beaa0` | 2025-10-08       | 0                                         | spec: steering-lut (already merged into baseline)                                             |
| `tier4/feature/pandar128e4x-highres-udp`                 | `25c2ca59ebab77dbaf8accbce842c1271184535d` | 2026-06-23       | 346                                       | spec: pandar128e4x-highres-udp (exact match)                                                  |
| `tier4/feature/pigz-zstd-compression`                    | `b16cc5dbab516cfe6cc9fc69d9d4344d093b16ab` | 2026-04-16       | 1†                                        | not spec-named; added by branch scan                                                          |
| `tier4/feature/pose-publisher`                           | `73c8de7fd7fce3146f8d014873caf71c6f373de4` | 2025-08-22       | 0                                         | spec: gnss-pose-publish/pose-publisher (already merged into baseline)                         |
| `tier4/feature/publish-report-data`                      | `e2dcb0aeb4a2f1ac1cab18c09528ba8dd884a87a` | 2025-09-03       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/feature/rgl-distance-culling-multisensor`         | `254fa617db11b6c33eb2157a0f7881260d2a85bc` | 2026-06-16       | 172                                       | spec: RGL GPU lidar (family — built on the integration branch)                                |
| `tier4/feature/rgl-on-ue5-dev-autoware-integration`      | `93d920f571e28b11c4a8bc895d060e4fb83563b6` | 2026-04-21       | 141                                       | spec: RGL GPU lidar (primary/foundational)                                                    |
| `tier4/feature/rgl-support`                              | `19b5eae7d4675fa5ce51b2166d35b390eccb53eb` | 2026-04-07       | 1†                                        | not spec-named; earlier/abandoned native-UE-plugin RGL attempt, unrelated lineage             |
| `tier4/feature/ros-domain-id`                            | `694b8283effb05daa69f01b3e5ca743e347cb2ac` | 2025-08-20       | 4                                         | not spec-named; added by branch scan                                                          |
| `tier4/feature/ros2-async-camera-publish`                | `83533bc142a49bf4e482954b12bc67da2866051c` | 2026-04-01       | 1†                                        | not spec-named; added by branch scan                                                          |
| `tier4/feature/ros2-async-publish-queue`                 | `2da85dbfabdde8242fa7915f16488083071aded0` | 2026-04-01       | 1†                                        | not spec-named; added by branch scan                                                          |
| `tier4/feature/sensor-timing-instrumentation`            | `0203ee13080aefac6ae905e708aebccc5def98eb` | 2026-04-01       | 1†                                        | not spec-named; added by branch scan                                                          |
| `tier4/feature/time-scale`                               | `8234fbf51b0f7044f2935fac683381e2e69dc455` | 2025-09-03       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/feature/topic-name`                               | `6f6dd207b17ad3fe3efca5ef3524e6f865cff5fd` | 2025-08-20       | 10                                        | not spec-named; added by branch scan                                                          |
| `tier4/feature/ue5-dev-autoware-integration`             | `16a71014425f6751dc5b21229402c6038e6244a9` | 2026-04-07       | 16†                                       | not spec-named; added by branch scan                                                          |
| `tier4/feature/ue5-dev-cyclonedds-support`               | `011032e9708e6f78fea0d8888a80a381717fe579` | 2026-04-07       | 13†                                       | not spec-named; earlier CycloneDDS-for-ue5-dev work, ancestor of ue5-dev-autoware-integration |
| `tier4/feature/vehicle-plot`                             | `61883b59eca4fc3db63d72d66f7e2e0f1ae5381d` | 2026-06-15       | 166                                       | not spec-named; added by branch scan                                                          |
| `tier4/feature/vehicle-sim-package`                      | `5642dfdd2fb5035f0435f4ce6a50d477800b6248` | 2026-07-07       | 349                                       | not spec-named; added by branch scan                                                          |
| `tier4/feature/vehicle-simulation`                       | `98d821be867409bf7825ae73b344bd7da37cb9d7` | 2026-05-18       | 143                                       | not spec-named; added by branch scan                                                          |
| `tier4/feature/vehicle-topic-support`                    | `1b82775902c6a9a2d44afc55fc74ca18e6d06fbf` | 2025-08-29       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/fix/autoware-publishers-frame-id`                 | `ad2d48ad1b51bd3eb986a344cc30962abe692ca3` | 2025-08-25       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/fix/carlaserver-enum-typo`                        | `936f20b6666cfe2191e9469f566a8367c82999d3` | 2026-06-15       | 166                                       | not spec-named; added by branch scan                                                          |
| `tier4/fix/dark-camera-sensor`                           | `ee0262e6f817aa28b2127d8660df833bdb9ac2f5` | 2025-09-05       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/fix/gnss-null-check`                              | `3940be124614d5f3421119d5215d347ec3524d6b` | 2026-03-31       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/fix/imu-delta-time`                               | `061189905abc6c5bbed598f2f2fbf3fd555dbae1` | 2025-11-19       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/fix/incorrect-steering-angle-normalization`       | `e9bcd7dae5663f5ad0ef6fc8f5a443bafdb53819` | 2025-12-01       | 1†                                        | not spec-named; added by branch scan                                                          |
| `tier4/fix/largemap-editor-rebase`                       | `32a3b2edcce27fb31b9e6a55afa7a3293c95235c` | 2026-06-16       | 163                                       | not spec-named; added by branch scan                                                          |
| `tier4/fix/nishishinjuku-map-cook-path`                  | `b257f68bbd3bc80362465fa90c836272190a4d6f` | 2026-03-31       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/fix/rgl-ring-id-0based`                           | `fbbc380567870f8180c48c0a0ebdc84996b5d781` | 2026-06-17       | 168                                       | spec: RGL GPU lidar (family — built on the integration branch)                                |
| `tier4/fix/ros-types`                                    | `957137502726bd707310ad871c17776dec89d655` | 2025-08-25       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/fix/status-publish-stamp`                         | `a75b2818809376afb35ba94dd7d3f0075e2ff89b` | 2025-09-25       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/fix/steering`                                     | `28a8726dec934e10d7dc2d1de87b8e727e3c84b8` | 2025-09-09       | 1†                                        | not spec-named; added by branch scan                                                          |
| `tier4/fix/traffic-light-controller-null-check`          | `28ead4191bbbb7df1f8f6b9acd13db48f4b34020` | 2026-05-27       | 163                                       | not spec-named; added by branch scan                                                          |
| `tier4/fix/traffic-light-freeze`                         | `87936f3c585b13a568ec67c0cf3d4a4ba01fa167` | 2026-06-04       | 163                                       | not spec-named; added by branch scan                                                          |
| `tier4/fix/transform-names`                              | `343cc084299b3bc0982fcb873efb76691b89498b` | 2025-10-01       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/main`                                             | `5642dfdd2fb5035f0435f4ce6a50d477800b6248` | 2026-07-07       | 349                                       | not spec-named; GitHub default branch, diverged from the baseline (see §1.3)                  |
| `tier4/patch/autoware-support-sync-upstream`             | `afd732c4d70927faa1056bee08f515733e05196a` | 2026-03-31       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/patch/autoware-support-sync-upstream-20260401-a`  | `ffc34b7231388a39af33d744593387c040a7eef9` | 2026-04-01       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/patch/upstream-post-merge-e-restore-acceleration` | `20681f8ca518c1c80a9761dc9b5c88e5f4ac0199` | 2026-03-31       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/patch/upstream-pre-merge-a-actor-impulse`         | `25ab68b721a78173591962ef3108222611582783` | 2026-03-31       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/patch/upstream-pre-merge-b-autoware-json-profile` | `c0793bc44560422fd115cde8e51de3198cdf6e0f` | 2026-03-30       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/patch/upstream-pre-merge-c-prop-mesh-path`        | `e3306876eaf7f3293db519176d970976fb9b6e3a` | 2026-03-31       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/patch/upstream-pre-merge-d-camera-json-migration` | `8f8f8597403ba6cbacce3d301c82ce867a478f77` | 2026-03-31       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/refactor/qos-settings`                            | `91877f454fc58eeb941735f45d0b9a37281dee76` | 2025-08-22       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/reference/pose-publisher`                         | `a51c521333adc1096ac65ef390d29c34cb9c4c74` | 2025-08-15       | 1†                                        | not spec-named; earlier reference draft, not merged, superseded by `feature/pose-publisher`   |
| `tier4/shinjuku-test-map`                                | `1fac16f896043f3e52fad1d6c8cd13dbea128a9a` | 2025-12-16       | 1†                                        | not spec-named; added by branch scan                                                          |
| `tier4/sync/upstream-ue5-dev-20260421`                   | `190030c752878d38a552573ffd21bcf62b131229` | 2026-04-21       | 136                                       | not spec-named; added by branch scan                                                          |
| `tier4/sync/upstream-ue5-dev-20260522`                   | `576a2a323a92b26b96b14574ea2d4add3222c9f0` | 2026-05-22       | 160                                       | not spec-named; added by branch scan                                                          |
| `tier4/test/navmesh-scanner`                             | `590ce22deb3a8a5fb01327273351f05bf667e8dd` | 2026-03-01       | 1†                                        | not spec-named; added by branch scan                                                          |
| `tier4/ue5-dev`                                          | `a40939fd5f3f5f41c1d43e6a862bdc2b98752e29` | 2026-03-31       | 0                                         | not spec-named; added by branch scan                                                          |
| `tier4/wc/add-cmake-preset`                              | `12ac513fdc74343a2aa207eb4e349f9796278239` | 2025-08-22       | 0                                         | not spec-named; added by branch scan                                                          |

† — `git merge-base` could not resolve a common ancestor with `tier4/autoware-support`
for this branch (see §1.2); its "commits ahead" figure is the raw
`rev-list --count` output and should be read as approximate, not a
verified merge-base delta.

### 1.2 Caveat: shared shallow clone

`~/src/carla-autoware-native` is not an independent clone — it is a git
worktree of `~/src/carla` (`git rev-parse --git-common-dir` →
`/home/youtalk/src/carla/.git`), which is itself a **shallow** clone
(`git rev-parse --is-shallow-repository` → `true`, `.git/shallow` present).
For 15 of the 65 branches (marked † above),
`git merge-base --is-ancestor <branch> tier4/autoware-support` and
`git merge-base <branch> tier4/autoware-support` both fail to resolve any
common ancestor, even though `git rev-list --count` still returns a small,
plausible-looking number for each. This is a known shallow-clone failure
mode (grafted history breaks the merge-base walk before it breaks the
simpler rev-list reachability walk) rather than evidence that those 15
branches have unrelated histories. The counts are reported as the best
available signal, not verified against merged-ancestor status.

### 1.3 Caveat: `tier4/autoware-support` vs `tier4/main`

The task's instructed baseline, `tier4/autoware-support`, is **not** the
tier4 repository's actual default branch — `tier4/main` is (`git remote show
tier4` reports `HEAD branch: main`). The two share a real, cleanly-resolved
merge-base (`a40939fd5f3f5f41c1d43e6a862bdc2b98752e29`, 2026-03-31, an
upstream `LibCarla` warnings fix), then diverged:

```console
$ git rev-list --count tier4/main..tier4/autoware-support   # commits only in autoware-support
207
$ git rev-list --count tier4/autoware-support..tier4/main   # commits only in main
349
```

`tier4/autoware-support` is **not** an ancestor of `tier4/main` and vice
versa. `tier4/main`'s tip is byte-identical to `tier4/feature/vehicle-sim-package`'s
tip (`5642dfdd2f...`), i.e. `main` was fast-forwarded from the UE5-dev / RGL /
vehicle-simulation side-branch lineage that grew out of `tier4/ue5-dev`
(itself the merge-base commit above). Practically: every branch in that
lineage (`ue5-dev-autoware-integration`, the RGL family, `vehicle-plot`,
`vehicle-simulation`, `vehicle-sim-package`, the `sync/upstream-ue5-dev-*`
branches, and the traffic-light/largemap fixes riding on top of them) shows a
large "commits ahead of `tier4/autoware-support`" figure (136–349) because
none of `tier4/main`'s 349 commits are reachable from `autoware-support` —
not because those branches are unusually large deltas from a shared trunk.
Read those figures as "distance from the `autoware-support` baseline
specifically", not "size of the change".

## 2. Spec-name → branch resolution

All 10 capability names in the design spec's gap-analysis scope (§4) resolve
to at least one branch; none is unresolved.

| Spec name                        | Resolved branch(es)                                                                                                                                                                                   | Note                                                                                                                                                                                                                                                                                                                                                                                                                           |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| RGL GPU lidar                    | `tier4/feature/rgl-on-ue5-dev-autoware-integration` (primary), `tier4/feature/rgl-distance-culling-multisensor`, `tier4/fix/rgl-ring-id-0based` (family, both built on top of the integration branch) | `tier4/feature/rgl-support` is a separate, much older, architecturally distinct attempt (native `Sensor`-class `RGLLidar.cpp`/`RGLSceneManager.cpp` under `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/RGL/`, vs. the resolved lineage's `PythonAPI/rgl/` + `RglSetup.sh` + `README_RGL.md` approach); it is not an ancestor of the resolved branch and is recorded separately in §1.1, not folded into this resolution.     |
| lidar-udp-raw-packet             | `tier4/feature/lidar-udp-raw-packet`                                                                                                                                                                  | Exact name match.                                                                                                                                                                                                                                                                                                                                                                                                              |
| pandar128e4x-highres-udp         | `tier4/feature/pandar128e4x-highres-udp`                                                                                                                                                              | Exact name match.                                                                                                                                                                                                                                                                                                                                                                                                              |
| agnocast-integration             | `tier4/feature/agnocast-integration`                                                                                                                                                                  | Exact name match.                                                                                                                                                                                                                                                                                                                                                                                                              |
| cyclonedds-support               | `tier4/experiment/cyclonedds-support`                                                                                                                                                                 | Exact `experiment/` match; also the branch the design spec itself points at in its C3 method paragraph ("CycloneDDS — extension mainline vs **tier4 experiment branch**", §3 below). `tier4/feature/ue5-dev-cyclonedds-support` is a separate, later CycloneDDS implementation for the ue5-dev lineage (an ancestor of `tier4/feature/ue5-dev-autoware-integration`); it is not spec-named and is recorded separately in §1.1. |
| autoware-v2i-publisher           | `tier4/feature/autoware-v2i-publisher`                                                                                                                                                                | Exact name match.                                                                                                                                                                                                                                                                                                                                                                                                              |
| lanelet2-traffic-light           | `tier4/feature/lanelet2-traffic-light`                                                                                                                                                                | Exact name match.                                                                                                                                                                                                                                                                                                                                                                                                              |
| docker-dev-env                   | `tier4/feature/docker-dev-env`                                                                                                                                                                        | Exact name match.                                                                                                                                                                                                                                                                                                                                                                                                              |
| steering-lut                     | `tier4/feature/override-steering-curve`                                                                                                                                                               | Per this task's working context (spec label does not match branch name verbatim). Confirmed by content (a curve/LUT-based steering-override implementation) and by ancestry: `git merge-base --is-ancestor tier4/feature/override-steering-curve tier4/autoware-support` is `yes` (0 commits ahead) — already merged, consistent with the spec's own phrase "steering LUT — already vendored".                                 |
| gnss-pose-publish/pose-publisher | `tier4/feature/gnss-pose-publish`, `tier4/feature/pose-publisher`                                                                                                                                     | Both are exact name matches for the two-part spec label, and both are already-merged ancestors of `tier4/autoware-support` (0 commits ahead). `tier4/reference/pose-publisher` is a separate, earlier, unmerged reference draft (single early commit, not an ancestor of the baseline) — recorded separately in §1.1, not counted as one of the two resolved branches.                                                         |

No spec-named capability failed to resolve.

## 3. Gap catalog method (C3)

Reproduced verbatim from `2026-07-27-three-approach-evaluation-design.md`,
"Gap catalog method (C3)":

> For each tier4-native capability (main + side branches): {capability, what
> it does, maturity evidence (merged/branch/demo), reproduction path on the
> extension architecture, effort class S/M/L}. Reproduction-path classes:
> **already-exists** (e.g. CycloneDDS — extension mainline vs tier4
> experiment branch; steering LUT — already vendored; docker bring-up),
> **extension-side work** (new publishers/subscribers or runner features
> behind the existing C ABI, e.g. V2I publisher), **CARLA-core seam work**
> (RGL GPU lidar, raw-UDP packet emission, per-map geo/MGRS assets, camera
> topic-suffix/QoS override — each labeled sensor-side (approach-agnostic) or
> ROS-side). Verdicts argued from code reading of both local trees; anything
> unverifiable is marked "needs prototype".

### Entry template

Every capability entry in Task 2 (main) and Task 3 (side branches) uses this
template:

```markdown
### <capability>

- What it does:
- Maturity evidence: merged (main @ <sha>) | branch <name> @ <sha> | demo <link>
- Reproduction path: already-exists | extension-side work | CARLA-core seam work
  (seam entries: sensor-side (approach-agnostic) | ROS-side)
- Effort class: S | M | L
- Verified by: <files read> | needs prototype
```

## 4. Working list of branches to catalog

Task 2 catalogs `tier4/autoware-support` (main). Task 3 catalogs the
side-branch capabilities resolved in §2 above — i.e. the primary/family
branches marked `spec: ...` in §1.1's Resolution column, plus any
non-spec-named branch from §1.1 that Task 3 judges to be a "major unmerged
side branch" under the design spec's gap-analysis scope (§4 of the design
doc). §1.1 is the complete candidate pool; §2 is the authoritative
spec-name-to-branch resolution Task 3 must use for the 10 named
capabilities.
