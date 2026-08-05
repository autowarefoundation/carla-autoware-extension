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

## 5. Capability catalog: `tier4/autoware-support` (main)

Every entry below cites the pinned SHA from §1.1 —
`6315b856f8faf2118578322eb20a2b902a45a384` (`tier4/autoware-support` tip,
2026-04-08) — as its maturity evidence, and follows §3's entry template
field-for-field.

### 5.0 How the capabilities were enumerated

Per the task's Step 1, four sources were read end to end, and every distinct
user-facing capability found in any of them got an entry:

1. **The `Autoware/` module inventory** —
   `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/` is exactly 10
   files: `Data/FGeoLocation.h`, `Data/MgrsDataAsset.h`,
   `Game/AutowareGameModeBase.{h,cpp}`, `Game/AutowareWorldSettings.{h,cpp}`,
   `Sensors/AutowareGnssSensor.{h,cpp}`, `Sensors/VehicleStatusSensor.{h,cpp}`.
2. **The `LibCarla/source/carla/ros2/` delta vs upstream `ue5-dev`** — see
   §5.0.1 for the diff mechanics; 127 files, +16 580 / −252.
3. **`PythonAPI/examples/autoware_demo.py`** (698 lines, entirely new) for the
   client-side feature surface.
4. **`Unreal/CarlaUnreal/Config/DefaultGame.ini` + `DefaultEngine.ini` +
   `CMakePresets.json`** for packaging/build entries, and **`README.md`**
   (rewritten at the pinned tip, +295 / −160) for the branch's own feature
   claims.

The whole-tree delta over the same range is **180 files, +19 660 / −1 198**,
distributed as: `LibCarla/source/carla/ros2` 127 files, the Carla UE plugin 33,
`LibCarla/source/carla/client` 7, `LibCarla/source/carla/sensor` 4, `PythonAPI`
4, and 5 top-level config / ignore / README files (127 + 33 + 7 + 4 + 4 + 5 =
180). §5.29 tabulates which entry covers each of those areas, so the "100 %
coverage of main" bar is auditable rather than asserted.

#### 5.0.1 The `ue5-dev` diff: what was actually comparable

The task's literal command was
`git diff ue5-dev...tier4/autoware-support --stat -- LibCarla/source/carla/ros2`.
Run against the `upstream` remote (`carla-simulator/carla`) in the shallow
archaeology clone it **fails outright**:

```console
$ git -C ~/src/carla-autoware-native diff upstream/ue5-dev...tier4/autoware-support --stat -- LibCarla/source/carla/ros2
fatal: upstream/ue5-dev...tier4/autoware-support: no merge base
$ git merge-base upstream/ue5-dev tier4/autoware-support; echo "exit=$?"
exit=1
```

This is the same shallow-clone merge-base failure recorded in §1.2, not
evidence of unrelated histories. The **substitute actually used**, and the one
every figure in §5 is computed from, is the tier4 remote's own mirror of the
upstream branch:

```console
$ git merge-base tier4/ue5-dev tier4/autoware-support
a40939fd5f3f5f41c1d43e6a862bdc2b98752e29
$ git rev-parse tier4/ue5-dev
a40939fd5f3f5f41c1d43e6a862bdc2b98752e29
```

`tier4/ue5-dev`'s tip **is** the merge base, so
`git diff tier4/ue5-dev...tier4/autoware-support` is byte-for-byte the
three-dot diff the task asked for — no two-dot fallback and no approximation
were needed. `tier4/ue5-dev` is itself an upstream commit
(`fix(LibCarla): eliminate compiler warnings (#9587)`, 2026-03-31, upstream
PR number in the subject), i.e. a genuine `ue5-dev` baseline rather than a
tier4 patch.

Two honest limits on that substitution:

- **It is the branch point, not today's upstream.** `upstream/ue5-dev`'s tip is
  `0a5ce0d5b4952bd8294a163c12d49f197bdb2aba` (2026-07-14), 3.5 months newer, and
  upstream restructured `LibCarla/source/carla/ros2` substantially in between
  (`git diff upstream/ue5-dev tier4/ue5-dev --stat -- LibCarla/source/carla/ros2`
  → 76 files, +7 972 / −4 548, including files that only exist on one side such
  as `PublisherImpl.h`, `SubscriberImpl.h`, `AckermannControlSubscriber.*`).
  Every "tier4 added X" statement below therefore means **added relative to the
  2026-03-31 `ue5-dev` branch point**, which is the correct baseline for
  attributing tier4's work, but is _not_ a claim that upstream still lacks X
  today.
- **`git merge-base --is-ancestor a40939fd upstream/ue5-dev` returns 1** in this
  clone. That is the §1.2 grafted-history artifact again (the commit is an
  upstream PR merge by subject and date); it could not be positively proven from
  the shallow clone, and is recorded here rather than papered over.

#### 5.0.2 What "already-exists" is argued against

The competing architecture is this repository: an out-of-tree
`libcarla-autoware-extension.so` behind the frozen C ABI in
`extension/include/carla/ros2/extension/CarlaRos2Extension.h`, plus the
declarative Python runner in `runner/`. Reading that header, exactly this
crosses the seam today:

- **Inbound to the extension:** one registered sensor observer of kind
  `CARLA_ROS2_SENSOR_VEHICLE_STATUS`, delivering a `CarlaRos2VehicleStatusView`
  POD per frame (ego transform in CARLA cm + quaternion, longitudinal/lateral
  velocity, yaw rate, steering tire angle, gear, sim time); raw CDR buffers from
  `create_subscriber` callbacks; `get_ego_actor_id` / `get_actor_ros_name`; and
  an `on_tick(sim_time_s)` hook. The enum reserves `LIDAR`, `LIDAR_EXT`, `IMU`
  and `GNSS` kinds, but `extension/src/ExtensionInit.cpp` registers **only**
  `VEHICLE_STATUS`.
- **Outbound from the extension:** `create_publisher` / `publish` (raw CDR,
  encapsulation header included), `create_subscriber`, and
  `apply_ackermann_control(actor_id, CarlaRos2AckermannPod)`.

So an "extension-side work" verdict means: implementable with those primitives
plus the Python runner, no CARLA rebuild. A "CARLA-core seam work" verdict means
it needs a change inside CARLA itself — either because the data never crosses
the ABI (sensor rendering, vehicle physics, UE assets, RPC surface) or because
the ABI would have to grow. Where the sibling CARLA fork (`youtalk/carla`;
branches read read-only from the shared object store) already carries an
equivalent core change, the entry says so and the effort class reflects the
_remaining_ work, not the work already done.

#### 5.0.3 The seam sub-label rule

§3's taxonomy asks every `CARLA-core seam work` entry to be labelled
**sensor-side (approach-agnostic)** or **ROS-side**. One rule decides it for
every such entry below, applied mechanically rather than argued case by case:

> **Is the underlying datum already obtainable through an existing CARLA
> client/actor API?** If **no** — the measurement, asset or physical behaviour
> does not exist outside CARLA core, so a Python bridge, an in-tree native
> ROS 2 stack and this out-of-tree extension would each need the _same_ core
> change — the entry is **sensor-side (approach-agnostic)**. If **yes** — the
> world already produces it and what is missing is only how it reaches a
> consumer (topic name, QoS, TF gating, an RPC, an ABI field) — the entry is
> **ROS-side**, because a different integration approach could already reach
> the datum today.

The test is applied against the _client API surface at the pinned SHA_, and each
entry names the specific API that decided it (for example
`vehicle.get_light_state()` for §5.10, `LidarMeasurement.get_point_count()` for
§5.14) or records that the grep found none (§5.9). Three consequences worth
stating up front, because they flip labels a case-by-case reading would get
wrong:

- An RPC is **not** automatically ROS-side. §5.17 ships an RPC pair, but the
  capability is the UE physics component behind it, which no client API can
  install — sensor-side. §5.23, by contrast, ships an RPC whose payload is
  already returned by an existing upstream RPC, so it is not even seam work.
- A change inside `LibCarla/source/carla/ros2` is **not** automatically
  ROS-side, and one outside it is not automatically sensor-side. §5.19 lives in
  the UE sensor and is sensor-side; §5.20 lives in the ROS publisher and is not
  seam work at all; §5.14 lives in the ROS publisher and is ROS-side.
- "Approach-agnostic" is a claim about _other_ integration approaches, not about
  this one. §5.10's blocker is an ABI field this architecture lacks — a property
  of this seam, not of CARLA — so it is ROS-side even though the extension
  cannot fix it without a version bump.

#### 5.0.4 Verdict tally

28 capability entries (§5.1–§5.28); §5.29 is the coverage map, not an entry.

| Class                              | Count | Entries                                                               |
| ---------------------------------- | ----- | --------------------------------------------------------------------- |
| already-exists                     | 11    | §5.1, §5.2, §5.3, §5.5, §5.6, §5.7, §5.11, §5.20, §5.23, §5.25, §5.28 |
| extension-side work                | 4     | §5.4, §5.18, §5.26, §5.27                                             |
| CARLA-core seam work — sensor-side | 6     | §5.9, §5.12, §5.13, §5.17, §5.19, §5.24                               |
| CARLA-core seam work — ROS-side    | 7     | §5.8, §5.10, §5.14, §5.15, §5.16, §5.21, §5.22                        |

Effort: 25 × S, 3 × M (§5.12, §5.13, §5.17). No entry carries an overall
`needs prototype` verdict; two entries carry a **scoped** `needs prototype`
marker on a named sub-claim while their overall verdict stands — §5.14 (whether
the two `PointXYZIRCAEDT` implementations agree field-for-field) and §5.20
(whether the two IMU gyroscope axis maps agree).

These counts cover **`tier4/autoware-support` only**. The side-branch entries
are tallied separately in §6.0.3, which also carries the combined whole-catalog
totals (53 entries: 14 already-exists, 8 extension-side work, 21
seam/sensor-side, 10 seam/ROS-side). Do not read the 28 above as the document's
total.

---

### 5.1 Autoware vehicle-status report publishers (six `/vehicle/status/*` topics)

- What it does: publishes the six AWSIM-compatible ego status topics —
  `/vehicle/status/velocity_status` (`autoware_vehicle_msgs/VelocityReport`,
  `frame_id: base_link`), `/steering_status`, `/control_mode`, `/gear_status`,
  `/turn_indicators_status`, `/hazard_lights_status` — all six stamped with one
  shared clock value and written in a single `Publish()` call, at
  RELIABLE / VOLATILE / KEEP_LAST-1. `AutowarePublisher.cpp` carries the full
  `ControlModeReport` / `GearReport` / `TurnIndicatorsReport` constant mappings.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/publishers/AutowarePublisher.{h,cpp}`,
  `LibCarla/source/carla/ros2/publishers/AutowarePublisherBase.hpp` (tier4);
  `extension/src/publishers/StatusPublishers.cpp`,
  `extension/src/ExtensionInit.cpp`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension).
  The extension publishes the identical six topic names and message types at the
  identical QoS triple (`StatusQos()` → reliability 0 / durability 0 / depth 1),
  with the same `base_link` frame on `VelocityReport` and the same
  one-stamp-for-all-six discipline. Per-field value provenance differs on **five
  of the six** — only `VelocityReport` matches outright (both take body-frame
  longitudinal / lateral velocity and yaw rate from the vehicle actor) — and is
  cataloged separately across §5.8 (control mode, steering), §5.9 (gear) and
  §5.10 (turn indicators, hazard lights) rather than folded into this verdict.
  Read this entry as "the topics, types, QoS and stamping are reproduced", not
  "the values agree".

### 5.2 Autoware control-command subscriber and ego actuation

- What it does: `AutowareController` subscribes `/control/command/control_cmd`
  (`autoware_control_msgs/Control`) at RELIABLE / TRANSIENT_LOCAL / KEEP_LAST-1,
  converts it to a control POD, and `ROS2::SetFrame` routes it into the ego
  actor callback ahead of the upstream `CarlaEgoVehicleControlSubscriber`
  ("Autoware input has priority").
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/subscribers/AutowareController.{h,cpp}`,
  `LibCarla/source/carla/ros2/subscribers/AutowareSubscriber.h`,
  `LibCarla/source/carla/ros2/ROS2.cpp` (`SetFrame`, `AddActorCallback`) (tier4);
  `extension/src/subscribers/ControlSubscribers.cpp`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension).
  The extension subscribes the same topic and type and actuates via
  `apply_ackermann_control`. Two deviations, both already documented in the
  extension source and neither of which requires a core change: it subscribes
  at BEST_EFFORT rather than TRANSIENT_LOCAL, and it forwards
  velocity + acceleration + jerk where tier4 deliberately forwards acceleration
  only. The _actuation mechanism_ those pods feed is a separate capability
  (§5.17).

### 5.3 Gear / turn-indicator / hazard-light command subscribers

- What it does: three further `AutowareSubscriber` instances on
  `/control/command/gear_cmd`, `/control/command/turn_indicators_cmd` and
  `/control/command/hazard_lights_cmd`, sharing the controller's
  TRANSIENT_LOCAL config. On main their payloads are received but **not** acted
  on — `AutowareController::GetControl` carries the literal comment
  `// TODO: Use input from all subscribers to perform actions in simulation`,
  and only the `control_cmd` longitudinal/lateral fields reach the output POD.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/subscribers/AutowareController.cpp`
  (tier4); `extension/src/subscribers/ControlSubscribers.cpp` (extension). The
  extension subscribes all three and caches each `command` byte atomically; like
  tier4 it does not actuate them, but unlike tier4 it feeds them back out as the
  corresponding status reports (§5.9, §5.10).

### 5.4 Emergency-command subscriber (`/control/command/emergency_cmd`)

- What it does: an `AutowareSubscriber<tier4_vehicle_msgs::msg::VehicleEmergencyStamped>`
  on `/control/command/emergency_cmd`, wired into `HasNewControl()`. As with
  §5.3 the value is received and then dropped by the same `TODO` — no emergency
  behaviour is implemented on main.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: extension-side work
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/subscribers/AutowareController.cpp`,
  `LibCarla/source/carla/ros2/types/VehicleEmergencyStamped.h` (tier4);
  `extension/src/subscribers/ControlSubscribers.cpp`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension —
  this topic has no subscriber). Adding it is one more `create_subscriber` call
  behind the existing ABI; the only new dependency is a `tier4_vehicle_msgs`
  type in the extension's rosidl message layer
  (`extension/include/carla/autoware/messages/RosIdl.h`), where every other
  Autoware type already comes from. No core change.

### 5.5 Engage subscriber

- What it does: an `AutowareSubscriber<autoware_vehicle_msgs::msg::Engage>` on
  `/vehicle/engage`, counted in `HasNewControl()`.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/subscribers/AutowareController.cpp`,
  `LibCarla/source/carla/ros2/publishers/AutowarePublisher.cpp` (tier4);
  `extension/src/engage/EngageStateMachine.h`,
  `extension/src/ExtensionInit.cpp` (extension). Two differences, both in the
  extension's favour and both verified by reading the sources: the extension
  subscribes `/autoware/engage` — the topic `vehicle_cmd_gate.launch.xml`
  actually remaps `input/engage` to in the pinned Autoware container, pinned in
  the `EngageStateMachine.h` header comment — where tier4 subscribes
  `/vehicle/engage`; and the extension _uses_ the value to drive
  `ControlModeReport.mode`, where tier4 discards it and hardwires
  `SetControlMode(ControlMode::AUTONOMOUS)` unconditionally (§5.8).

### 5.6 Autoware GNSS pose publishers with MGRS offset

- What it does: `AutowareGNSSPublisher` replaces the stock `CarlaGNSSPublisher`
  for GNSS actors and emits two topics off the sensor's base name — a
  `geometry_msgs/Pose` on the `/pose` suffix and a
  `geometry_msgs/PoseWithCovarianceStamped` on `/pose_with_covariance` — from
  the sensor's **world** transform (not its parent-relative one), with a single
  Y negation and the level's MGRS offset added to the position, and an all-zero
  covariance matrix (`// TODO: Add some covariance matrix`).
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/publishers/AutowareGNSSPublisher.{h,cpp}`,
  `LibCarla/source/carla/ros2/ROS2.cpp` (`ProcessDataFromAutowareGNSS`, and the
  `if (false) { CarlaGNSSPublisher } else { AutowareGNSSPublisher }` switch in
  `GetOrCreateSensor`) (tier4); `extension/src/publishers/GnssPosePublisher.cpp`,
  `extension/include/carla/autoware/geo/MgrsOffset.h` (extension). The extension
  publishes `/sensing/gnss/pose` and `/sensing/gnss/pose_with_covariance` with
  the same single-Y-negation handedness rule and a per-map offset, decimated to
  1 Hz. Two differences worth recording: tier4's first topic carries a bare
  unstamped `geometry_msgs/Pose` where the extension publishes `PoseStamped`
  (which is what Autoware's `/sensing/gnss/pose` expects); and tier4 takes the
  pose from a spawned GNSS actor's world transform, where the extension
  synthesizes it from the ego transform in the status view.

### 5.7 Steering-compensation lookup table

- What it does: `AutowareSteeringCompensation.h` holds a 26-point measured
  (desired, actual) tire-angle table for the Lincoln MKZ with linear
  interpolation and a symmetric-abs lookup, exposed as a forward
  (`GetSteeringOutput`) and an inverse (`GetSteeringInput`) map. tier4 applies
  the inverse on the inbound command in `AutowareController::GetControl` **and**
  the forward on the outbound `SteeringReport` in `AutowarePublisher::SetSteering`.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/AutowareSteeringCompensation.h` (tier4);
  `extension/include/carla/autoware/control/AutowareSteeringCompensation.h`,
  `extension/src/subscribers/ControlSubscribers.cpp`,
  `extension/src/publishers/StatusPublishers.cpp` (extension). A `diff -u` of the
  two headers shows the table and the interpolation logic are **identical** —
  the only changes are the namespace (`carla::ros2` → `carla::autoware`), an
  explicit `<tuple>` include, and added comments including a provenance note
  citing this exact pinned SHA. The extension applies the inverse on the inbound
  path exactly as tier4 does; it does **not** apply the forward map on the
  outbound `SteeringReport` (see §5.8, where that value is a stub anyway).

### 5.8 Control-mode and steering-status value sources

- What it does: on main the `ControlModeReport` is hardwired to `AUTONOMOUS`
  every frame (`// TODO: Add logic to use the input of control mode`; the source
  notes the control-mode command is a service with "no easy way to get it as of
  now"), and `SteeringReport.steering_tire_angle` is derived from
  `Vehicle->GetVehicleControl().Steer * MaxSteerAngleInRadians` — i.e. the
  _commanded_ normalized steer scaled by the vehicle's max steer angle, not a
  measured wheel angle.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Sensors/VehicleStatusSensor.cpp`
  (`CollectAndStream`), `LibCarla/source/carla/ros2/ROS2.cpp`
  (`ProcessDataFromStatusSensor`), `PythonAPI/carla/src/Actor.cpp:191`
  (`.def("get_control", &cc::Vehicle::GetControl)`) and
  `PythonAPI/carla/src/Control.cpp:421`
  (`max_steer_angle` on `WheelPhysicsControl`) (tier4);
  `extension/src/publishers/StatusPublishers.cpp`,
  `extension/src/engage/EngageStateMachine.h`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension); plus
  the fork's `ROS2.cpp` at `feat/autoware-seminative-phase-b` read via
  `git show` (the block that fills `steering_tire_angle_rad`). Control mode is
  strictly better on the extension side (engage-driven, §5.5). Steering status is
  strictly worse and the reason is a **core** one: the fork's host fills
  `CarlaRos2VehicleStatusView::steering_tire_angle_rad` from
  `ACarlaWheeledVehicle::GetWheelSteerAngle`, whose real readback is `#if 0`'d on
  UE5/Chaos ("@CARLAUE5 ToDo") so it returns 0.0 — the fork's own source comment
  says so. The extension therefore publishes a constant-zero
  `/vehicle/status/steering_status` today. tier4 side-steps the same engine stub
  by using the commanded-steer proxy above; adopting that proxy is a small change
  **inside the host**, not in the `.so`, which is why this is seam work rather
  than extension-side. **ROS-side** under §5.0.3: both inputs to tier4's proxy
  are already on the client API (`vehicle.get_control().steer` and
  `get_physics_control().wheels[i].max_steer_angle`), so a bridge could publish
  the identical value today with no core change — what is missing here is only
  the ABI field's fill, which is a property of this seam.

### 5.9 Gear-status value source

- What it does: `ProcessDataFromStatusSensor` maps the vehicle's **actual**
  current gear (`Vehicle->GetVehicleCurrentGear()`, serialized as
  `VehicleStatusData::gear`) onto the 25 `GearReport` constants, defaulting to
  `Gear::NONE` for out-of-range values.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/ROS2.cpp`
  (`ProcessDataFromStatusSensor` gear switch),
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Sensors/VehicleStatusSensor.cpp:129`
  (`GetVehicleCurrentGear()`),
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Vehicle/CarlaWheeledVehicle.cpp:267-270`
  (`return BaseMovementComponent->GetVehicleCurrentGear();`) (tier4);
  `extension/src/publishers/StatusPublishers.cpp`,
  `extension/src/ExtensionInit.cpp`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension); plus
  the fork's fill chain, read in full in `~/src/carla-autoware-integration` at
  `feat/autoware-seminative-phase-b`:
  `Game/CarlaEngine.cpp:575-597` (`View->GetVehicleControl(VehicleControl)` →
  `ProcessDataFromVehicle`), `Vehicle/CarlaWheeledVehicle.h:106-110`
  (`GetVehicleControl()` → `return LastAppliedControl;`),
  `Vehicle/CarlaWheeledVehicle.cpp:305` (`LastAppliedControl = InputControl.Control;`)
  and `LibCarla/source/carla/ros2/ROS2.cpp:1247` (`control.gear`).
  **Correction to an earlier draft of this entry**, which claimed the actual
  gear "already crosses the ABI as `CarlaRos2VehicleStatusView::gear`". It does
  not. That field is filled from `LastAppliedControl.Gear`, i.e. the **commanded**
  gear — the same quantity the extension's `/control/command/gear_cmd` cache
  already holds. So the extension echoes a commanded value on _both_ legs, and
  tier4's actual-transmission-gear semantics are not reachable from the `.so` at
  all: they need a host-side fill change, structurally identical to §5.10. A grep
  of `CarlaServer.cpp`, `PythonAPI/carla/src/`, `LibCarla/source/carla/client/`
  and `LibCarla/source/carla/rpc/` at the pinned SHA finds **no** binding for
  `GetVehicleCurrentGear` — unlike light state (§5.10), the transmission's actual
  gear is exposed to no client at all, so under §5.0.3 this is **sensor-side**,
  not ROS-side: a bridge would need the same core change. (This is the one place
  this fix round diverges from the review's suggested sub-label, on that grep.)
  The remaining work is also more than the "one-line change" the earlier draft
  claimed: the host must surface the actual gear, and the consumer must carry
  tier4's 25-constant CARLA-gear → `GearReport` mapping (`REVERSE_2` … `DRIVE_18`
  plus the `NONE` default), which `StatusPublishers` does not have today.

### 5.10 Turn-indicator and hazard-light status value sources

- What it does: `VehicleStatusSensor` packs the vehicle's **actual**
  `FVehicleLightState` blinker bits into a 3-bit `turn_mask`
  (left / right / hazard), and `ProcessDataFromStatusSensor` decodes it into
  `TurnIndicatorsReport` / `HazardLightsReport`, logging an error if both
  blinkers are simultaneously set.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Sensors/VehicleStatusSensor.cpp`,
  `LibCarla/source/carla/ros2/ROS2.cpp` (`ProcessDataFromStatusSensor` turn-mask
  decode), `PythonAPI/carla/src/Actor.cpp:197`
  (`.def("get_light_state", CONST_CALL_WITHOUT_GIL(cc::Vehicle, GetLightState))`)
  and `LibCarla/source/carla/client/Vehicle.h:101` (tier4);
  `extension/src/publishers/StatusPublishers.cpp`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension). Like
  gear (§5.9), the ego light state does **not** cross the C ABI — the status view
  has no light-state field — so reproducing tier4's actual-state semantics needs
  a new field in `CarlaRos2VehicleStatusView` plus a host-side fill, i.e. an ABI
  version bump. That blocker is a property of **this** seam, not of CARLA:
  `vehicle.get_light_state()` already returns the same data to any client, and
  tier4's own sensor just reads `Vehicle->GetVehicleLightState()`. Under §5.0.3
  the entry is therefore **ROS-side** — a bridge or an in-tree native stack needs
  no core change here, which is exactly what distinguishes it from §5.9. The
  extension's present behaviour (echo the commanded `turn_indicators_cmd` /
  `hazard_lights_cmd` bytes) is arguably the more useful signal for a closed
  loop, since neither implementation actuates the lights (§5.3), but it is a
  different quantity and is recorded as such.

### 5.11 `sensor.other.vehicle_status`: a spawnable ego-status sensor

- What it does: a new UE `ASensor` subclass with its own actor definition
  (`sensor.other.vehicle_status`, one `speed_units` attribute), a
  `TG_PostPhysics` tick at a clamped `TargetRateHz` (default 30 Hz, 1–1000 Hz
  range), a retry timer that walks up the attachment chain to find its parent
  `ACarlaWheeledVehicle`, a packed `VehicleStatusData` msgpack payload
  (timestamp, speed, body-frame linear and angular velocity, actor rotation,
  steer, gear, turn mask, control flags), a `SensorRegistry` entry so ordinary
  CARLA clients can also stream it, and an ego-only guard in
  `ProcessDataFromStatusSensor` that refuses to publish for a non-ego parent.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Sensors/VehicleStatusSensor.{h,cpp}`,
  `LibCarla/source/carla/sensor/s11n/VehicleStatusSerializer.h`,
  `LibCarla/source/carla/sensor/SensorRegistry.h`,
  `LibCarla/source/carla/ros2/ROS2.cpp` (tier4);
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h`
  (`CARLA_ROS2_SENSOR_VEHICLE_STATUS`, `CarlaRos2VehicleStatusView`),
  `extension/src/ExtensionInit.cpp` (extension). The _capability_ — a per-frame
  ego ground-truth stream feeding the Autoware reports — is exactly the
  extension's one registered observer, and the field sets overlap almost
  entirely. Both take velocities from the vehicle actor, not from the attach
  point, so there is no rear-axle-vs-origin discrepancy between them. Two things
  the extension does **not** reproduce, neither of which any current consumer in
  this repository uses: a configurable publish rate (the observer fires at the
  simulation tick rate, 20 Hz at the G3 gate), and a spawnable blueprint that a
  plain CARLA client could `listen()` to. If either is required, that part is
  CARLA-core seam work at M, not S.

### 5.12 Per-map MGRS geo-reference asset pipeline

- What it does: makes a level's geo-reference an authored UE asset rather than
  an OpenDRIVE-parsed value. `UMgrsDataAsset` (a `UDataAsset` with an MGRS grid
  zone, an `FVector` offset, an `FGeoLocation` geo-reference and a name/GUID) is
  referenced by `AAutowareWorldSettings` via a `TSoftObjectPtr`;
  `ACarlaGameModeBase::InitGame` was refactored to call a new
  `virtual LoadGeoReference()` that `AAutowareGameModeBase` overrides to load
  that asset, write it into `UCarlaEpisode::MapGeoReference`, and call
  `StoreSpawnPoints()` — falling back to the stock OpenDRIVE path when the world
  settings are not the Autoware subclass. `DefaultEngine.ini` sets
  `WorldSettingsClassName=/Script/Carla.AutowareWorldSettings` project-wide,
  `CarlaEpisode` befriends the new game mode, and `Episode` plus
  `StoreSpawnPoints` were moved from `private` to `protected` on the base class.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: M
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Data/{FGeoLocation.h,MgrsDataAsset.h}`,
  `.../Autoware/Game/AutowareWorldSettings.{h,cpp}`,
  `.../Autoware/Game/AutowareGameModeBase.{h,cpp}`,
  `.../Game/CarlaGameModeBase.{h,cpp}`, `.../Game/CarlaEpisode.{h,cpp}`,
  `Unreal/CarlaUnreal/Config/DefaultEngine.ini` (tier4);
  `extension/include/carla/autoware/geo/MgrsOffset.h`,
  `extension/src/ExtensionInit.cpp`, `docs/mgrs-handedness.md`,
  `docs/nishishinjuku-map.md` (extension). The extension has a **partial**
  substitute and no more: a compile-time table of two hardcoded offsets
  (Nishi-Shinjuku and `Town10HD_Opt`) selected at load time by
  `$CARLA_AUTOWARE_MAP`, because — as `ExtensionInit.cpp` states — "the frozen C
  ABI carries no map name, so an environment variable is the only channel". That
  covers the two maps this repository gates on and nothing else; a third map
  needs an extension rebuild. Reproducing tier4's property (any level can carry
  its own authored geo-reference, editable in the UE editor, with no ROS-layer
  rebuild) requires the UE-side asset and game-mode work above. It is labelled
  approach-agnostic because the geo-reference is a world-authoring property that
  any ROS integration — bridge, native, or extension — would consume identically.

### 5.13 `sensor.other.autoware_gnss` blueprint

- What it does: a second GNSS sensor class, `AAutowareGnssSensor`, registered as
  `sensor.other.autoware_gnss` through a parameterized
  `MakeGnssDefinition(Success, Definition, Name)` and a new
  `MakeAutowareGnssDefinition()` / `SetAutowareGnss()` pair. It reads the
  episode's geo-reference at `BeginPlay`, transforms its own world location into
  lat/lon/alt each `PostPhysTick`, optionally applies per-axis Gaussian noise and
  bias through `URandomEngine`, loads the level's `UMgrsDataAsset` itself, and
  calls the dedicated `ROS2::ProcessDataFromAutowareGNSS` overload carrying both
  the world transform and the MGRS offset. `autoware_demo.py` picks between it
  and the stock `sensor.other.gnss` on a `--mgrs_off` flag and warns if the
  Autoware variant is unavailable.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: M
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Sensors/AutowareGnssSensor.{h,cpp}`,
  `.../Actor/ActorBlueprintFunctionLibrary.{h,cpp}`,
  `LibCarla/source/carla/sensor/SensorRegistry.h`,
  `LibCarla/source/carla/ros2/ROS2.cpp`, `PythonAPI/examples/autoware_demo.py`
  (tier4); `extension/src/publishers/GnssPosePublisher.cpp`,
  `extension/include/carla/autoware/geo/MgrsOffset.h`, `runner/spawn.py`
  (extension). The _pose output_ is already reproduced (§5.6). What is not, and
  cannot be behind the current ABI, is the sensor itself: a spawnable blueprint
  mounted at the kit's `gnss_link` frame, with its own tick rate and its own
  noise/bias attributes, whose measurement is taken at the sensor pose rather
  than the ego pose. The GNSS observer kind (`CARLA_ROS2_SENSOR_GNSS`) is
  reserved in the ABI but no host dispatch or extension registration exists for
  it — that plumbing is the core work. The noise/bias model alone, applied to
  the ego pose, would be extension-side S; the entry is classed on the dominant
  blocker.

### 5.14 Extended LiDAR point layout (`PointXYZIRCAEDT`)

- What it does: `CarlaLidarPublisher::SetDataEx` emits a ten-field
  `PointCloud2` — `x, y, z, intensity, return_type, channel, azimuth,
elevation, distance, time_stamp` — instead of the stock four floats.
  `ROS2::ProcessDataFromLidar` gained `channel_count` / `upper_fov_limit` /
  `lower_fov_limit` parameters (passed from `ARayCastLidar::PostPhysTick` out of
  the sensor description) and synthesizes a per-channel vertical-angle table by
  even subdivision of the FOV; `channel` and `elevation` are then assigned from
  the per-channel point counts in the LiDAR data header, with the remaining
  polar fields computed from the Cartesian ones. A compile-time
  `sizeof(PointEx) != offset` check guards the packed layout.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/publishers/CarlaLidarPublisher.{h,cpp}`,
  `LibCarla/source/carla/ros2/ROS2.cpp`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/RayCastLidar.cpp`,
  `PythonAPI/carla/src/SensorData.cpp:426,428` and
  `LibCarla/source/carla/sensor/data/LidarMeasurement.h:47,54`
  (`LidarMeasurement.channels` / `.get_point_count(channel)`) (tier4);
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h`
  (`CARLA_ROS2_SENSOR_LIDAR_EXT`), `runner/spawn.py`
  (`ros2_extended_lidar` in `_REQUIRED_NATIVE_ATTRS`), and the sibling fork
  commit `0bd4d84c3` (`min/5-extended-lidar`,
  "feat(ros2): opt-in 10-float PointXYZIRCAEDT LiDAR layout") read via
  `git show --stat`. The point cloud is published by CARLA core, never by the
  `.so`, so no extension-side path exists — the ABI reserves a `LIDAR_EXT`
  observer kind but the extension registers only `VEHICLE_STATUS`. **ROS-side**
  under §5.0.3, not sensor-side: every input the layout needs is already on the
  client API (the per-channel point counts and channel count above, plus the
  blueprint's own FOV attributes), so a bridge could synthesize the identical
  ten-field cloud in userspace — the core change is specific to the in-core
  publishing path. The effort is S rather than M only because the fork already
  carries an equivalent core change, gated behind a per-actor
  `ros2_extended_lidar` blueprint attribute (tier4's is unconditional for every
  ray-cast LiDAR) and with the derived fields in a dedicated
  `ExtendedLidarPoint.h` plus a `test_ros2_extended_lidar` unit test.
- **needs prototype** — scoped sub-claim only; the seam / ROS-side / S verdict
  above stands. The two `PointXYZIRCAEDT` implementations were compared by file
  inventory and commit subject, **not** field-by-field: whether they agree
  numerically (field order and offsets, the `azimuth` / `elevation` /
  `distance` / `time_stamp` derivations, and in particular tier4's even-subdivision
  vertical-angle synthesis versus whatever `ExtendedLidarPoint.h` computes) was
  not established, and cannot be from a stat-level comparison. Treat "the fork
  already has this" as a claim about the capability, not about wire equivalence.

### 5.15 Per-actor `ros_topic_name` override

- What it does: adds a `ros_topic_name` blueprint variation to every actor
  definition alongside `ros_name`, an
  `AddActorRosTopicName` / `RemoveActorRosTopicName` / `UpdateActorRosTopicName`
  / `GetActorRosTopicName` map on the `ROS2` singleton, `ValidTopicName()`
  helpers on both `CarlaPublisher` and `CarlaSubscriber` that turn a
  user-supplied name into a `rt/`-prefixed FastDDS topic, and the plumbing to
  thread it from `UActorDispatcher::RegisterActor` and the `CarlaServer`
  attribute walk into every publisher and subscriber constructor. An empty value
  is the signal to fall back to the generated default.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/ROS2.{h,cpp}`,
  `LibCarla/source/carla/ros2/publishers/CarlaPublisher.h`,
  `LibCarla/source/carla/ros2/subscribers/CarlaSubscriber.h`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Actor/{ActorDispatcher.cpp,ActorBlueprintFunctionLibrary.cpp}`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Server/CarlaServer.cpp`
  (tier4); `runner/spawn.py` (`ros_topic_name` in `_REQUIRED_NATIVE_ATTRS` and
  `_CAMERA_REQUIRED_ATTRS`), and fork commits `09084d216`
  (`min/3-blueprint-attributes`) / `f35a862f8` (`autoware/5-ros-topic-name`) /
  `6ce758603` (`autoware/8-extended-lidar`, "honor `ros_topic_name` verbatim
  across the point-cloud publisher family") via `git show --stat`. Topic naming
  is decided inside core's publisher construction, entirely upstream of the C
  ABI, so no extension-side path exists. The fork already implements the same
  attribute, and `runner/spawn.py` _requires_ it — it is load-bearing for the
  live gates, with an extensive comment block on the `ros_name` mangling it
  works around.

### 5.16 Per-endpoint DDS QoS configuration

- What it does: introduces `data_types.h` with `TopicConfig`
  (`suffix`, `domain_id`, reliability / durability / history / depth enums) and
  threads it through every publisher and subscriber `Init()`, replacing the
  hardcoded `DATAWRITER_QOS_DEFAULT`. `ROS2.cpp` then assigns a per-sensor-type
  profile: LiDAR BEST_EFFORT depth 5, IMU RELIABLE depth 1000, RGB camera
  BEST_EFFORT depth 1 on both the `/image_raw` and `/camera_info` sub-topics,
  clock and status RELIABLE depth 1, command subscribers
  RELIABLE / TRANSIENT_LOCAL depth 1.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/data_types.h`,
  `LibCarla/source/carla/ros2/ROS2.cpp`,
  `LibCarla/source/carla/ros2/publishers/AutowarePublisherBase.hpp`,
  `LibCarla/source/carla/ros2/publishers/CarlaLidarPublisher.cpp` (tier4);
  `runner/spawn.py` (`ros2_qos_reliability` / `ros2_qos_durability` /
  `ros2_qos_history_depth`),
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (`CarlaRos2Qos`),
  and fork commit `09084d216` (`min/3-blueprint-attributes`) /
  `447496dcd` (`autoware/6-sensor-qos`) via `git show --stat`. The distinction
  matters for the comparison: the extension's own endpoints already choose their
  QoS through the ABI's `CarlaRos2Qos` struct, so _extension-created_ topics need
  nothing. What needs core work is QoS on **core-created sensor topics** (LiDAR,
  camera, IMU), and the fork solves it differently from tier4 — per-actor
  blueprint attributes chosen by the client, versus tier4's per-sensor-type
  constants baked into `ROS2.cpp`. `runner/spawn.py` notes that
  `sensor.camera.rgb` does not declare the QoS attributes at all in the fork
  build, so cameras there publish at their as-emitted default; tier4's approach
  has no such gap. Effort is S for the remaining delta only.

### 5.17 Acceleration-based longitudinal actuation

- What it does: a new `UVehicleAccelerationControl` actor component that, on a
  `TG_PostPhysics` tick, integrates a commanded forward acceleration into a
  forward speed, clamps it non-negative (no reverse; flagged `TODO` for
  gear-awareness), preserves the physics-derived lateral velocity so tyres can
  still generate cornering force, and writes the result back with
  `SetPhysicsLinearVelocity`. `ACarlaWheeledVehicle::ApplyVehicleAccelerationControl`
  deactivates Ackermann and velocity control, activates it, and sets steer
  directly on `InputControl`; `TickActor` flushes control every frame while
  either override is active. A `VehicleAckermannControl` and a
  `VehicleAccelerationControl` variant were added to the `ROS2CallbackData`
  variant and to `ActorROS2Handler`, and the mode is also exposed to clients as
  `enable_actor_constant_acceleration` / `disable_actor_constant_acceleration`
  RPCs → `FVehicleActor::EnableActorConstantAcceleration` →
  `Actor.enable_constant_acceleration()` in the Python API. The same commit
  fixes `UVehicleVelocityControl` to bind to the vehicle **mesh** rather than
  the root component.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic) —
  a vehicle-physics component and RPC surface, not a ROS-layer change)
- Effort class: M
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Vehicle/VehicleAccelerationControl.{h,cpp}`,
  `.../Vehicle/CarlaWheeledVehicle.{h,cpp}`, `.../Vehicle/VehicleVelocityControl.cpp`,
  `.../Actor/{ActorROS2Handler.h,ActorROS2Handler.cpp,CarlaActor.cpp}`,
  `.../Server/CarlaServer.cpp`,
  `LibCarla/source/carla/ros2/ROS2CallbackData.h`,
  `LibCarla/source/carla/client/{Actor.cpp,Actor.h,detail/Client.cpp,detail/Client.h,detail/Simulator.h}`,
  `PythonAPI/carla/src/Actor.cpp` (tier4);
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h`
  (`apply_ackermann_control`, `CarlaRos2AckermannPod`),
  `extension/src/subscribers/ControlSubscribers.cpp` (extension). The extension's
  only actuation primitive is `apply_ackermann_control`, which routes into
  CARLA's existing target-based Ackermann controller; there is no way to install
  a new UE tick component or a new RPC from a `.so`. `ControlSubscribers.cpp`
  documents this as a deliberate deviation and records that the live G2
  closed-loop drive passed with the Ackermann path, so this is a
  behaviour/tuning difference rather than a missing capability — but tier4's
  specific acceleration-integration semantics are not reproducible without the
  core component.

### 5.18 Flatten the ego steering curve at registration

- What it does: `ActorROS2Handler::FlattenSteeringCurve` resets the ego's
  `SteeringCurve` to a constant 1.0 across 0–120 km/h and re-applies the physics
  control, so a commanded normalized steer maps to the same wheel angle at every
  speed. `UActorDispatcher::RegisterActor` calls it for any actor whose
  `role_name` is `hero` or `ego`, right before registering the ROS 2 callback.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: extension-side work
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Actor/{ActorROS2Handler.h,ActorROS2Handler.cpp,ActorDispatcher.cpp}`,
  `PythonAPI/carla/src/Control.cpp` (`steering_curve` is a first-class
  `VehiclePhysicsControl` property in the Python bindings at this same SHA)
  (tier4); `runner/spawn.py`, `runner/__main__.py` — a repository-wide grep for
  `steering_curve` finds no hit, so the runner does not do this today
  (extension). Because the curve is reachable from the Python API
  (`ego.apply_physics_control(...)` after `get_physics_control()`), reproducing
  it is a few lines in `runner/spawn.py` at ego-spawn time, with no core change
  and no ABI involvement. It is nonetheless a real behavioural difference that
  interacts with the steering LUT of §5.7 (that table was measured on a vehicle
  whose curve tier4 had already flattened), and is worth flagging to anyone
  comparing lateral tracking between the two stacks.

### 5.19 IMU accelerometer bootstrap and gravity-sign fix

- What it does: `AInertialMeasurementUnit::ComputeAccelerometer` now takes the
  absolute world time rather than a per-frame delta, keeps a NaN-sentinel
  `PrevTime` / `PrevLocation` history so the first two frames return a zero
  vector instead of a garbage second derivative, and flips the gravity constant
  from `+9.81` to `-9.81` m/s².
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/InertialMeasurementUnit.{h,cpp}`
  (tier4); `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (the
  `CARLA_ROS2_SENSOR_IMU` kind is reserved but unregistered), `runner/spawn.py`
  (the IMU is spawned as a native CARLA sensor publishing on its own),
  and fork commit `610b08f31` (`min/7-imu-sensor-frame`) /
  `ae166d80d` (`autoware/11-imu-sensor-frame`) via `git show --stat`, plus the
  fork's `LibCarla/source/carla/ros2/publishers/CarlaIMUPublisher.cpp` and
  `publishers/ImuMath.h` read in full. IMU data never crosses the C ABI in
  either stack — the sensor publishes natively — and this fix changes the
  measurement itself, so every consumer (including a bridge reading
  `carla.IMUMeasurement`) sees it: sensor-side by the §5.0.2 rule, and core work
  by construction. **Scope of the "complementary" claim:** tier4's accelerometer
  bootstrap and gravity sign were not found anywhere in the fork's IMU commit,
  so _those two changes specifically_ are complementary to the fork's work, not
  duplicates. That is **not** true of tier4's IMU work as a whole — its
  ROS-layer REP-103 handedness flip is cataloged separately in §5.20 and **is**
  duplicated by the fork. Merging the accelerometer half was not attempted here.

### 5.20 IMU ROS-layer REP-103 handedness correction

- What it does: flips three components in the ROS publisher rather than in the
  sensor — `CarlaIMUPublisher::SetData` writes `linear_acceleration.y(-ay)`,
  `gyroscope.y(-gy)` and `gyroscope.z(-gz)`, with the inline comment
  `// Invert pitch and yaw to match ROS`. This is a distinct change from §5.19:
  it is applied on the publishing path only, so a non-ROS CARLA client reading
  `carla.IMUMeasurement` still receives the unflipped UE components.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/publishers/CarlaIMUPublisher.{h,cpp}`
  (tier4, three-dot diff read in full); the fork's
  `LibCarla/source/carla/ros2/publishers/CarlaIMUPublisher.cpp` (lines 54–70)
  and `LibCarla/source/carla/ros2/publishers/ImuMath.h`, both read in full from
  `~/src/carla-autoware-integration` at `feat/autoware-seminative-phase-b`;
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (no IMU path
  runs through the `.so`). The fork applies the equivalent conversion at the
  same point in the pipeline, factored into named helpers `LinearUEToRos` /
  `AngularUEToRos` and pinned by `test_imu_axes.cpp`, so having the capability
  needs no new work.
- **needs prototype** — scoped sub-claim only; the already-exists / S verdict
  above stands. The two implementations do **not** apply the same axis map to
  the gyroscope, and code reading cannot say which is right. tier4 flips Y and Z
  (`(x, -y, -z)`); the fork flips X and Z (`(-x, y, -z)`), arguing in
  `ImuMath.h` that angular velocity is a pseudovector and therefore transforms
  as `det(M)·M = -M` under the `diag(1, -1, 1)` handedness map, and citing a
  live G2 closed-loop crash from getting it wrong. The linear-acceleration half
  **does** agree exactly (`(x, -y, z)` on both sides). Adjudicating the
  gyroscope map needs a measurement against a known mounting — plausibly the two
  are reconciled by tier4's flip-mounted `tamagawa/imu_link`
  (`roll = yaw = π` in `autoware_demo.py`) — and no such measurement was taken
  here. Do not read this entry as "the two agree".

### 5.21 `ROS_DOMAIN_ID` support

- What it does: `ROS2::ObtainDomainId()` parses `$ROS_DOMAIN_ID` with
  `std::from_chars`, rejecting negatives, overflow and trailing garbage, and the
  resolved value is threaded through `TopicConfig::domain_id` into every
  `create_participant` call. The README makes the corresponding operational
  claim that `ROS_LOCALHOST_ONLY` is unsupported and a unique `ROS_DOMAIN_ID`
  should be used instead.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/ROS2.{h,cpp}`,
  `LibCarla/source/carla/ros2/data_types.h`, `README.md` (tier4); and the fork's
  `LibCarla/source/carla/ros2/ROS2.cpp` at `feat/autoware-seminative-phase-b`
  read via `git show`, whose `ROS2::Enable(bool, Middleware, int domain_id)`
  resolves a domain through a `SetActiveDomainId()` helper with an explicit
  `DomainIdSource::Environment` (`ROS_DOMAIN_ID`) case — i.e. the fork already
  implements this, and more generally (a `--ros-domain-id` flag, per
  `docs/prerequisites.md`'s #9807–#9816 row, rather than the environment
  variable alone). Nothing here is reachable from the `.so`: DDS participants for
  extension endpoints are created by the host.

### 5.22 TF-publishing suppression

- What it does: a world-global `set_publish_tf` / `get_publish_tf` RPC pair
  gating every `CarlaTransformPublisher` emission in `ROS2.cpp` behind
  `if (sensors.second && _publish_tf)` (15 added call sites), surfaced as
  `World::SetPublishTF` / `GetPublishTF` in LibCarla and
  `world.set_publish_tf(...)` in the Python API, plus a `--disable-tf` flag on
  the stock `PythonAPI/examples/ros2/ros2_native.py` example.
  `autoware_demo.py` calls `world.set_publish_tf(False)` in
  `apply_world_settings` with the comment that Autoware publishes TF from the
  vehicle and sensor-kit URDFs instead.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/ROS2.{h,cpp}`,
  `LibCarla/source/carla/client/{World.h,World.cpp,detail/Client.h,detail/Client.cpp,detail/Simulator.h}`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Server/CarlaServer.cpp`,
  `PythonAPI/carla/src/World.cpp`, `PythonAPI/examples/ros2/ros2_native.py`,
  `PythonAPI/examples/autoware_demo.py` (tier4); and fork commit `78a35db54`
  (`min/4-set-publish-tf`, same feature name, including
  `test_ros2_publish_tf.cpp`) / `e6976992c` (`autoware/7-set-publish-tf`) via
  `git show --stat`. The TF publishers live in core, upstream of the ABI; the
  fork already implements the identical RPC.

### 5.23 `get_ego_spawn_points` RPC

- What it does: a `get_ego_spawn_points` RPC returning
  `UCarlaEpisode::GetRecommendedSpawnPoints()` — the _game mode's_ stored spawn
  points, which for `AAutowareGameModeBase` are the ones `StoreSpawnPoints()`
  populated after loading the level's MGRS geo-reference (§5.12) — exposed as
  `World::GetEgoSpawnPoints` and `world.get_ego_spawn_points()`.
  `autoware_demo.py` calls it with an `AttributeError` fallback to
  `world.get_map().get_spawn_points()` for stock CARLA packages.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Server/CarlaServer.cpp`
  (both the new `get_ego_spawn_points` at :760-763 **and** the pre-existing
  upstream `get_map_info` at :513-523, which fills `cr::MapInfo` from the very
  same `Episode->GetRecommendedSpawnPoints()` call),
  `LibCarla/source/carla/client/Map.h:50-52`
  (`GetRecommendedSpawnPoints()` → `_description.recommended_spawn_points`),
  `LibCarla/source/carla/client/Map.cpp:30-34` (the `Map` is constructed **from**
  that `rpc::MapInfo`), `LibCarla/source/carla/client/detail/Client.cpp:205-206`
  (`GetMapInfo()` → `"get_map_info"`),
  `LibCarla/source/carla/client/detail/Simulator.cpp:161`,
  `PythonAPI/carla/src/Map.cpp:134`
  (`get_spawn_points` → `Map::GetRecommendedSpawnPoints`),
  `LibCarla/source/carla/client/{World.h,World.cpp,detail/Client.h,detail/Client.cpp}`,
  `PythonAPI/carla/src/World.cpp`, `PythonAPI/examples/autoware_demo.py` (tier4);
  `runner/__main__.py:296`
  (`select_spawn_point(world.get_map().get_spawn_points(), args.spawn_index)`)
  and `runner/spawn.py` (extension).
  **Correction to an earlier draft of this entry**, which asserted that "the
  level-authored spawn points tier4 exposes are not reachable from the client
  without this RPC". Tracing the call chain above shows the opposite:
  `world.get_map().get_spawn_points()` is served out of `rpc::MapInfo`, which the
  **pre-existing upstream** `get_map_info` RPC already fills from
  `Episode->GetRecommendedSpawnPoints()` — byte-identical to what
  `get_ego_spawn_points` returns. tier4's RPC is therefore a convenience
  duplicate of an API surface that already exists, and this repository's runner
  is already calling the equivalent one at `runner/__main__.py:296`. Reclassified
  from CARLA-core seam work (ROS-side) to already-exists, S. The one behavioural
  difference left: the client-side `Map` is cached and refreshed only when
  `Simulator::ShouldUpdateMap` fires, so `get_ego_spawn_points` is a live query
  where `get_spawn_points()` may serve a cached list — irrelevant for a
  spawn-time read, and not a capability gap.

### 5.24 Nishi-Shinjuku map packaging entry

- What it does: adds `+MapsToCook=(FilePath="/Game/Carla/Maps/NishishinjukuMap")`
  to `DefaultGame.ini`, so the Nishi-Shinjuku level is cooked into
  `cmake --build Build --target package` shipping builds alongside the stock
  Carla maps. `autoware_demo.py --load_map NishinjukuMap` is the documented way
  to switch to it at runtime.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Config/DefaultGame.ini`,
  `PythonAPI/examples/autoware_demo.py`, `README.md`, and
  `git ls-tree -r tier4/autoware-support -- Unreal/CarlaUnreal/Content`
  (**0 files** — the map assets themselves are not tracked in the tier4
  repository, so this catalog can assess only the packaging manifest line, not
  the content) (tier4); `runner/__main__.py` (`--map` defaults to
  `NishishinjukuMap`), `docs/nishishinjuku-map.md` (extension). This repository
  drives the same map by name and documents the same converter offset
  (`x=81655.73 y=50137.43 z=42.49998`, from
  `autoware_lanelet2_to_opendrive conf/map/nishishinjuku.yaml`) that
  `MgrsOffset.h` hardcodes, but map cooking is a CARLA build-config property no
  `.so` can influence; the fork's `autoware/4-nishishinjuku-loader` branch
  (`ca6e1994c`) carries the loader side. Recorded as a distinct entry because it
  is the one place tier4's tree names the map.

### 5.25 Declarative Autoware sensor-kit spawn

- What it does: `autoware_demo.py` spawns a Lexus-RX450h-equivalent AWSIM kit on
  a `vehicle.lincoln.mkz` ego: a `util.actor.empty` `base_link` at the rear-axle
  offset, a `sensor_kit_base_link` above it, and under it a VLP16-parameterized
  `sensor.lidar.ray_cast` (16 channels, 100 m, +10/−20° FOV, 288 000 pps,
  10 Hz → `/sensing/lidar/top/pointcloud_raw_ex`, frame `velodyne_top`), a
  1920×1080 90° RGB traffic-light camera at 10 Hz
  (→ `/sensing/camera/traffic_light`), a 30 Hz IMU mounted directly on the ego
  "because this is required for angular velocity to work"
  (→ `/sensing/imu/tamagawa/imu_raw`), a 1 Hz GNSS (→ `/sensing/gnss`), and the
  vehicle-status sensor on `base_link`. Mount transforms are transcribed from
  the `awsim_sensor_kit_description` URDF and composed with a PyKDL
  `chain_transforms` helper through an explicit ROS↔CARLA handedness/degree
  conversion class.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `PythonAPI/examples/autoware_demo.py` (tier4); `runner/spawn.py`,
  `runner/kit.py`, `runner/config/sensor_kit_calibration.yaml`,
  `runner/config/sensors_calibration.yaml`, `runner/__main__.py` (extension).
  The runner does the same job data-driven rather than hardcoded: it parses the
  two calibration YAMLs extracted from the Autoware container
  (`base_link → sensor_kit_base_link` and `sensor_kit_base_link →` each of 15
  sensor frames, including `velodyne_top_base_link`, `gnss_link`,
  `tamagawa/imu_link` and the traffic-light cameras) and composes them in
  `kit.sensor_in_base_link`. LiDAR geometry is parameterized on the command line
  (`--lidar-channels`, `--lidar-pps`, `--lidar-rotation-hz`, `--lidar-range`)
  rather than fixed to VLP16. One documented gap on the extension side:
  `runner/spawn.py` mounts cameras at the ego origin rather than the kit's
  off-centreline camera frames, because `runner/kit.py` flags an unimplemented
  Y-flip for off-centre sensors — that affects the M4 camera load arm only, not
  the G1–G3 gates.

### 5.26 Client-side simulation pacing and world controls

- What it does: `autoware_demo.py`'s `TimeStepData` / `apply_world_settings` /
  `run_sync_simulation_loop` provide, from one CLI: synchronous mode with a
  fixed time step (`--hz_rate`, default 100 Hz, `0`/`None` selecting a variable
  step), physics substepping (`--substepping`, with CARLA's
  `max_substep_delta_time × max_substeps` admissibility condition applied), an
  asynchronous mode (`--run_async`), a wall-clock-paced tick loop with a
  real-time multiplier (`--time_scale`), lag detection with an optional
  resynchronize-to-now behaviour (`--resync`), a spectator that follows the ego
  (`--follow`), map load / force-reload / `--list_maps`
  (`--load_map`, `--force_reload`), and a `KeyboardInterrupt` handler that
  restores CARLA to async + variable step so the server is not left wedged.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: extension-side work
- Effort class: S
- Verified by: `PythonAPI/examples/autoware_demo.py`, `README.md` (which
  documents each flag) (tier4); `runner/loop.py`, `runner/__main__.py`
  (extension). The runner already covers synchronous fixed-step
  (`--fixed-delta`, default 0.05 = 20 Hz), an async fallback (`--async`), an
  unpaced mode (`--unpaced`), substepping (`--substep-config`) and map
  selection (`--map`). A repository-wide grep finds **no** `time_scale`,
  `resync` or `spectator` usage, so the real-time multiplier, the
  resynchronize-on-lag behaviour, the follow-cam and the map force-reload /
  list-maps conveniences are genuinely absent. All of them are pure PythonAPI
  calls with no core or ABI dependency, hence extension-side S.

### 5.27 Traffic-light camera post-process profile

- What it does: `autoware_demo.py` ships a 40-key `AUTOWARE_POSTPROCESS_SETTINGS`
  dict (motion blur, auto-exposure, local exposure, shutter/ISO, depth of field,
  film tonemap, white balance, chromatic aberration, colour grading, vignette)
  and writes it as `autoware_demo.json` into the source tree's and every
  packaged build's `Content/Carla/Config/PostProcess/` directory before
  connecting, then sets `post_process_profile=autoware_demo` on the
  traffic-light camera blueprint. Its own comment says these values "were
  originally hardcoded in `ActorBlueprintFunctionLibrary.cpp` and are now managed
  as a JSON profile".
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: extension-side work
- Effort class: S
- Verified by: `PythonAPI/examples/autoware_demo.py` (tier4);
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/BlueprintLibary/PostProcessJsonUtils.{h,cpp}`
  and `.../Actor/ActorBlueprintFunctionLibrary.cpp` (the `post_process_profile`
  variation and the `LoadAllPostProcessFromJsonToSceneCapture` call) — both
  verified **unchanged** over the ue5-dev range, so the loader is upstream and
  only the profile _content_ plus its deployment is tier4's; `runner/spawn.py`
  (the camera path sets no `post_process_profile`) (extension). Reproducing it is
  writing the same JSON from the runner and adding one blueprint attribute; the
  attribute and the loader already exist in any ue5-dev-derived build.

### 5.28 Build and documentation surface

- What it does: (a) `CMakePresets.json` rewrites the hidden base preset to build
  into a single `Build/` directory with `ENABLE_ROS2=ON` and
  `CMAKE_POLICY_VERSION_MINIMUM=3.5` by default, so a plain
  `cmake --preset ...` produces an ROS 2-enabled server; (b) `README.md` is
  rewritten into a full bring-up guide — system requirements, `CarlaSetup.sh`
  usage, editor vs. packaged launch, `cmake --build Build --target package`, the
  `autoware_demo.py` client, obtaining the Town10 lanelet2 + point-cloud maps
  from the `carla-simulator/autoware-contents` bucket and writing
  `map_projector_info.yaml`, the `e2e_simulator.launch.xml` command line with
  `sample_vehicle` / `awsim_sensor_kit`, a manual `ros2 topic pub` drive-forward
  smoke test, and one section per demo flag.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `CMakePresets.json`, `README.md` (tier4); `README.md`,
  `docs/prerequisites.md`, `docs/running-e2e.md`, `docs/architecture.md`,
  `docs/nishishinjuku-map.md`, `docs/e2e-report.md`, `docker/compose.yaml`
  (extension). The extension repository's bring-up documentation covers the same
  ground and more (a pinned container, a scripted `run_e2e.sh`, committed gate
  evidence). One structural difference worth stating rather than glossing:
  tier4's build config is a preset inside the CARLA tree, so a reader clones one
  repository; this repository's build path spans two (the CARLA fork plus this
  one), which `docs/prerequisites.md` pins explicitly. That is a property of the
  out-of-tree architecture, not a documentation gap.

### 5.29 Coverage map

Every changed area of the pinned three-dot diff, and the entry that covers it.
Areas marked _not a capability_ are listed in the same table so nothing in the
diff is silently unaccounted for.

| Changed area (three-dot diff vs `tier4/ue5-dev`)                                                                                                                                         | Entry                                                                                                                                                                                                                                                                                                                                                                 |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ros2/publishers/AutowarePublisher.*`, `AutowarePublisherBase.hpp`                                                                                                                       | §5.1, §5.8, §5.9, §5.10                                                                                                                                                                                                                                                                                                                                               |
| `ros2/subscribers/AutowareController.*`, `AutowareSubscriber.*`                                                                                                                          | §5.2, §5.3, §5.4, §5.5                                                                                                                                                                                                                                                                                                                                                |
| `ros2/publishers/AutowareGNSSPublisher.*`, `CarlaPoseStampedPublisher.*`                                                                                                                 | §5.6                                                                                                                                                                                                                                                                                                                                                                  |
| `ros2/AutowareSteeringCompensation.h`                                                                                                                                                    | §5.7                                                                                                                                                                                                                                                                                                                                                                  |
| `ros2/types/*` (64 added files = 16 new Autoware/tier4/geometry message types), `ros2/util/conversions.hpp`                                                                              | §5.1–§5.6 (message layer)                                                                                                                                                                                                                                                                                                                                             |
| `ros2/publishers/CarlaLidarPublisher.*`, `Sensor/RayCastLidar.cpp`                                                                                                                       | §5.14                                                                                                                                                                                                                                                                                                                                                                 |
| `ros2/publishers/CarlaIMUPublisher.*` (the three sign flips in `SetData`)                                                                                                                | §5.20                                                                                                                                                                                                                                                                                                                                                                 |
| `ros2/publishers/CarlaPublisher.h`, `subscribers/CarlaSubscriber.h`, `ROS2.{h,cpp}` topic-name maps                                                                                      | §5.15                                                                                                                                                                                                                                                                                                                                                                 |
| `ros2/data_types.h`, per-publisher `Init(TopicConfig)` churn (the QoS/domain/suffix half of every publisher, including `CarlaIMUPublisher`)                                              | §5.16                                                                                                                                                                                                                                                                                                                                                                 |
| `ros2/ROS2.cpp` `ObtainDomainId`                                                                                                                                                         | §5.21                                                                                                                                                                                                                                                                                                                                                                 |
| `ros2/ROS2.cpp` `_publish_tf` gates, `client/World.*`, `CarlaServer.cpp` TF RPCs                                                                                                         | §5.22                                                                                                                                                                                                                                                                                                                                                                 |
| `CarlaServer.cpp` `get_ego_spawn_points`, `client/World::GetEgoSpawnPoints`                                                                                                              | §5.23                                                                                                                                                                                                                                                                                                                                                                 |
| `Autoware/Data/*`, `Autoware/Game/*`, `Game/CarlaGameModeBase.*`, `Game/CarlaEpisode.*`, `DefaultEngine.ini`                                                                             | §5.12                                                                                                                                                                                                                                                                                                                                                                 |
| `Autoware/Sensors/AutowareGnssSensor.*`, `Actor/ActorBlueprintFunctionLibrary.*` GNSS defs                                                                                               | §5.13                                                                                                                                                                                                                                                                                                                                                                 |
| `Autoware/Sensors/VehicleStatusSensor.*`, `sensor/s11n/VehicleStatusSerializer.*`, `sensor/SensorRegistry.h`, `sensor/data/VehicleStatusEvent.h`                                         | §5.11                                                                                                                                                                                                                                                                                                                                                                 |
| `Vehicle/VehicleAccelerationControl.*`, `Vehicle/CarlaWheeledVehicle.*`, `Vehicle/VehicleVelocityControl.cpp`, `Actor/CarlaActor.cpp`, `client/Actor.*`, `PythonAPI/carla/src/Actor.cpp` | §5.17                                                                                                                                                                                                                                                                                                                                                                 |
| `Actor/ActorROS2Handler.*` `FlattenSteeringCurve`, `Actor/ActorDispatcher.cpp` ego hook                                                                                                  | §5.18                                                                                                                                                                                                                                                                                                                                                                 |
| `Sensor/InertialMeasurementUnit.*`                                                                                                                                                       | §5.19                                                                                                                                                                                                                                                                                                                                                                 |
| `Sensor/GnssSensor.cpp` (world-transform argument)                                                                                                                                       | §5.6, §5.13                                                                                                                                                                                                                                                                                                                                                           |
| `DefaultGame.ini` `+MapsToCook`                                                                                                                                                          | §5.24                                                                                                                                                                                                                                                                                                                                                                 |
| `PythonAPI/examples/autoware_demo.py` sensor kit                                                                                                                                         | §5.25                                                                                                                                                                                                                                                                                                                                                                 |
| `PythonAPI/examples/autoware_demo.py` pacing/world controls, `PythonAPI/carla/src/World.cpp`                                                                                             | §5.26, §5.22                                                                                                                                                                                                                                                                                                                                                          |
| `PythonAPI/examples/autoware_demo.py` post-process profile                                                                                                                               | §5.27                                                                                                                                                                                                                                                                                                                                                                 |
| `CMakePresets.json`, `README.md`                                                                                                                                                         | §5.28                                                                                                                                                                                                                                                                                                                                                                 |
| `PythonAPI/examples/ros2/ros2_native.py` `--disable-tf`                                                                                                                                  | §5.22 (evidence)                                                                                                                                                                                                                                                                                                                                                      |
| `Sensor/SceneCaptureSensor.{h,cpp}` (header +60/−136 with 28 `UFUNCTION` declarations removed and 0 added; `.cpp` +74/−288)                                                              | _not a capability_ — measured as a net **removal** of Blueprint-callable post-process accessors relative to the branch point, with no replacement added on this branch. Whether that is deliberate scoping or a lost hunk from one of the `patch/autoware-support-sync-upstream-*` merges was not determined; recorded as an unexplained delta rather than guessed at |
| `.gitignore` (Rider/Perforce entries)                                                                                                                                                    | _not a capability_                                                                                                                                                                                                                                                                                                                                                    |
| `ros2/listeners/SubscriberListenerBase.*`, `ROS2CallbackData.h` variant widening                                                                                                         | _internal plumbing for_ §5.2–§5.5, §5.17                                                                                                                                                                                                                                                                                                                              |

## 6. Capability catalog: tier4 side branches

Every entry below cites a pinned SHA from §1.1 and follows §3's entry template
field-for-field, with the seam sub-label decided by §5.0.3's rule applied
mechanically (each seam entry names the client API that decided it, or records
that the grep found none). Where a side branch extends or fixes a capability
already cataloged for `tier4/autoware-support`, the entry cross-references the
§5 entry rather than restating it.

### 6.0 How the side branches were read

Per this task's Step 1 the intended command is
`git diff tier4/autoware-support...tier4/<branch> --stat`. It was usable
unchanged for only 2 of the branches below. §6.0.1 records, per branch, what was
actually run and why — a fallback is never silently substituted.

#### 6.0.1 Per-branch diff mechanics

Two distinct failure modes made the three-dot form unusable:

- **Shallow-clone merge-base failure (§1.2).** For the branches marked † in
  §1.1, `git merge-base` resolves nothing and the branch tip's own parent is not
  in the clone (`git rev-parse <tip>^` → `unknown revision`), so neither
  `A...B` nor `<tip>^..<tip>` exists. Fallback: two-dot `git diff
tier4/autoware-support <tip>` plus `git ls-tree` file inventories.
- **Wrong-baseline three-dot (§1.3).** For every branch on the `tier4/main`
  lineage, `git merge-base tier4/autoware-support tier4/<branch>` is
  `a40939fd5f3f5f41c1d43e6a862bdc2b98752e29` — i.e. `tier4/ue5-dev`, the branch
  point, not a shared trunk. The three-dot diff therefore _succeeds_ and returns
  the entire 136–349-commit `ue5-dev`→branch delta, of which the branch's own
  change is a small fraction. Fallback: diff from the branch's own fork point in
  that lineage — `git merge-base tier4/main tier4/<branch>` where the branch is
  ahead of `main`, otherwise the commit below the branch's first topic-scoped
  commit in `git log --oneline a40939fd..tier4/<branch>`.
- **Merge-base unresolvable but the commit chain still readable.** A third
  variant, hit only by `tier4/feature/ue5-dev-cyclonedds-support`:
  `git merge-base` resolves nothing against `tier4/autoware-support` **or**
  `tier4/ue5-dev`, yet the tip's parent (`b504f0d3d`) is present and
  `git log tier4/ue5-dev..tier4/feature/ue5-dev-cyclonedds-support` returns a
  clean 13-commit range — the §1.2 artifact again (rev-list reachability
  survives where the merge-base walk does not). The range is used, and labelled
  a **rev-list exclusion rather than a merge-base delta** in the table below,
  because its ancestry could not be positively verified.

| Branch                                              | Mechanic used                                                                                                                                                                                                                                                                            | Isolated delta                           | Limit                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tier4/experiment/cyclonedds-support`               | **three-dot as instructed** (merge-base `27583999d`)                                                                                                                                                                                                                                     | 447 files, +17 820 / −7 159              | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/feature/agnocast-integration`                | **three-dot as instructed** (merge-base `27583999d`)                                                                                                                                                                                                                                     | 14 files, +792                           | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/feature/ue5-dev-cyclonedds-support`          | rev-list exclusion `git log --oneline tier4/ue5-dev..tier4/feature/ue5-dev-cyclonedds-support` (13 commits); `git merge-base` resolves nothing against either `tier4/autoware-support` **or** `tier4/ue5-dev`, but the tip's parent `b504f0d3d` **is** present, so the range is readable | 13 commits                               | ancestry unverified (§1.2): the range is a rev-list exclusion, not a merge-base delta. **Disposition — no capability hides here:** the 13 subjects are the CycloneDDS port itself (§6.1) plus `ros_topic_name to all publisher/subscriber constructors` (= §5.15), `ROS_DOMAIN_ID and ValidTopicName support` (= §5.21), `SetDataEx to CarlaLidarPublisher` (= §5.14), `TopicConfig.suffix for camera image topic name` (= §6.17), and four build/refactor commits — i.e. `ue5-dev`-lineage ports of already-cataloged capabilities                                                                                                                                            |
| `tier4/feature/ue5-dev-autoware-integration`        | two-dot from `git merge-base tier4/feature/ue5-dev-cyclonedds-support …` = `011032e97` (its parent branch tip)                                                                                                                                                                           | 3 commits, 53 files, +4 054 / −788       | **Disposition — no capability hides here:** `git diff --name-status` over that range shows every added file mapping to an existing entry — `Autoware/Data/*` + `Autoware/Game/*` → §5.12, `Autoware/Sensors/AutowareGnssSensor.*` → §5.13, `Autoware/Sensors/VehicleStatusSensor.*` + `sensor/{data/VehicleStatusEvent.h,s11n/VehicleStatusSerializer.*}` → §5.11, `Vehicle/VehicleAccelerationControl.*` + the `enable/disable_constant_acceleration` bindings → §5.17, `ActorROS2Handler::FlattenSteeringCurve` → §5.18, `World::{Get,Set}PublishTF` → §5.22, `World::GetEgoSpawnPoints` → §5.23, `autoware_demo.py` → §5.25–§5.27, `dds/cyclonedds/ROS2.cpp` → §6.1 + §6.17 |
| `tier4/feature/ros2-async-publish-queue`            | two-dot vs `tier4/autoware-support` (†: no merge base, parent absent)                                                                                                                                                                                                                    | 9 files, +344 / −315                     | the `README.md` half of that stat is lineage drift, not the capability                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `tier4/feature/ros2-async-camera-publish`           | two-dot vs `tier4/autoware-support` (†)                                                                                                                                                                                                                                                  | 10 files, +384 / −346                    | as above                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `tier4/feature/sensor-timing-instrumentation`       | two-dot vs `tier4/autoware-support` (†)                                                                                                                                                                                                                                                  | 4 files, +189 / −296                     | as above                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `tier4/feature/docker-dev-env`                      | two-dot vs `tier4/autoware-support` (†) + `git ls-tree -- docker` + `git show <tip>`                                                                                                                                                                                                     | `docker/` only: 5 files, +307            | the two-dot's 185-file / −19 660 figure is the whole Autoware stack being _absent_ (this branch sits on upstream `ue5-dev`), not a change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `tier4/feature/lanelet2-traffic-light`              | two-dot from fork point `583f9238e` (below the first `lanelet2_traffic_light` commit)                                                                                                                                                                                                    | 127 files, +7 021 (35 of them `.uasset`) | binary assets counted, not inspected                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/feature/autoware-v2i-publisher`              | two-dot from `git merge-base tier4/main` = `a23011c20`                                                                                                                                                                                                                                   | 10 files, +707                           | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/feature/lidar-udp-raw-packet`                | two-dot from fork point `3d90d023d` (the last `origin/main` merge below the topic commits)                                                                                                                                                                                               | 42 files, +3 384 / −128                  | the range also re-carries the rebased culling/ring-id commits (§6.5, §6.6), attributed to their own branches                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `tier4/feature/pandar128e4x-highres-udp`            | two-dot from `04d0a44c6` (its merge of `lidar-udp-raw-packet`)                                                                                                                                                                                                                           | 7 files, +223 / −15                      | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/feature/rgl-distance-culling-multisensor`    | two-dot from `git merge-base tier4/main` = `893a8e22f`                                                                                                                                                                                                                                   | 6 files, +534 / −36                      | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/fix/rgl-ring-id-0based`                      | two-dot from `git merge-base tier4/main` = `bb8009f96`                                                                                                                                                                                                                                   | 12 files, +91 / −66                      | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/feature/rgl-on-ue5-dev-autoware-integration` | **no isolating base exists** — read by `git ls-tree` inventory + `git show <blob>`                                                                                                                                                                                                       | 46 RGL-named paths at the tip            | its 141 commits interleave RGL work with two upstream syncs and a traffic-light merge; no range isolates the RGL change. Recorded as a limit, not worked around                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `tier4/feature/vehicle-simulation`                  | two-dot from `93d920f57` (its parent branch tip)                                                                                                                                                                                                                                         | 15 files, +1 644 / −63                   | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/feature/vehicle-plot`                        | two-dot from `893a8e22f`                                                                                                                                                                                                                                                                 | 1 file, +657                             | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/feature/vehicle-sim-package`                 | two-dot from `tier4/feature/pandar128e4x-highres-udp` (the branch it last merged)                                                                                                                                                                                                        | 3 commits, 8 files, +155 / −129          | tip is byte-identical to `tier4/main` (§1.3). **Disposition — fully attributed:** the delta is `Fix RGL UDP raw packet geometry: emit rays in azimuth-major order` plus `sync Hesai lidar presets with verified UDP raw-packet geometry`, both cataloged in §6.5; no third capability                                                                                                                                                                                                                                                                                                                                                                                          |
| `tier4/fix/largemap-editor-rebase`                  | `git show --stat <tip>` (1 commit ahead of `main`, parent present)                                                                                                                                                                                                                       | 2 files, +28                             | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/fix/traffic-light-freeze`                    | `git show --stat <tip>`                                                                                                                                                                                                                                                                  | 1 file, +9 / −15                         | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/fix/traffic-light-controller-null-check`     | `git show --stat <tip>`                                                                                                                                                                                                                                                                  | 1 file, +12 / −2                         | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/fix/carlaserver-enum-typo`                   | `git show --stat <tip>`                                                                                                                                                                                                                                                                  | 1 file, +4 / −4                          | none                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `tier4/feature/pigz-zstd-compression`               | `git ls-tree` + commit subject only (†, lineage-dominated two-dot)                                                                                                                                                                                                                       | not separable                            | the same work is readable on the RGL branch (`bc2ce9afa`, `5e06661ea`) and in `README_RGL.md`; read there instead                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `tier4/feature/build-dependency-share-tool`         | `git ls-tree` + commit subject only (†)                                                                                                                                                                                                                                                  | not separable                            | as above (`995ab1eae`, `8713d80eb`, `52906f293`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `tier4/test/navmesh-scanner`                        | `git ls-tree` + commit subject only (†)                                                                                                                                                                                                                                                  | 4 named files                            | no diff was obtainable; entry describes the files present, not a delta                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `tier4/feature/rgl-support`                         | `git ls-tree` + commit subject only (†)                                                                                                                                                                                                                                                  | 5 named files                            | as above; superseded lineage (§2), folded into §6.4 rather than given its own entry                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `tier4/shinjuku-test-map`                           | `git ls-tree` + commit subject only (†)                                                                                                                                                                                                                                                  | none found                               | tip subject is `Remove Autoware Game Mode debug cast`; a `git ls-tree` of the tip filtered for `shinjuku` returns **0 paths**. No capability found; recorded in §6.26 as not-a-capability                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

#### 6.0.2 What "unmerged" means for these branches

The design spec calls these "the major unmerged side branches". That is true
**only relative to the instructed `tier4/autoware-support` baseline**. Measured
against the repository's actual default branch, `git rev-list --count
tier4/main..tier4/<branch>` is **0** for `feature/lanelet2-traffic-light`,
`feature/lidar-udp-raw-packet`, `feature/pandar128e4x-highres-udp`,
`feature/rgl-on-ue5-dev-autoware-integration`, `feature/vehicle-plot`,
`feature/vehicle-simulation` and `feature/vehicle-sim-package` — every one of
them is already **merged into `tier4/main`** (whose tip is byte-identical to
`feature/vehicle-sim-package`'s, §1.3). Only these are genuinely unmerged
anywhere: `experiment/cyclonedds-support` (263 ahead of `main`),
`feature/agnocast-integration` (220), `feature/autoware-v2i-publisher` (8),
`feature/rgl-distance-culling-multisensor` (7), `fix/rgl-ring-id-0based` (1),
`fix/largemap-editor-rebase` (1), `fix/traffic-light-freeze` (1),
`fix/traffic-light-controller-null-check` (1), `fix/carlaserver-enum-typo` (1),
and the †-marked branches whose ancestry cannot be verified at all. Each entry's
**Maturity evidence** field states which of the two it is, because "on a side
branch" and "shipped on the default branch" are very different maturity claims
to put in front of the branches' own authors.

#### 6.0.3 Verdict tally

25 capability entries (§6.1–§6.25); §6.26 is the coverage map, not an entry.

| Class                              | Count | Entries                                                                                           |
| ---------------------------------- | ----- | ------------------------------------------------------------------------------------------------- |
| already-exists                     | 3     | §6.1, §6.2, §6.10                                                                                 |
| extension-side work                | 4     | §6.15, §6.21, §6.22, §6.23                                                                        |
| CARLA-core seam work — sensor-side | 15    | §6.4, §6.5, §6.6, §6.7, §6.8, §6.9, §6.11, §6.12, §6.13, §6.14, §6.16, §6.19, §6.20, §6.24, §6.25 |
| CARLA-core seam work — ROS-side    | 3     | §6.3, §6.17, §6.18                                                                                |

Effort: 13 × S, 8 × M, 4 × L (§6.3, §6.4, §6.7, §6.12). No entry carries an
overall `needs prototype` verdict; four carry a **scoped** `needs prototype`
marker on a named sub-claim while the overall verdict stands — §6.7 (whether the
private RGL UDP extension is obtainable at all), §6.9 (whether the substep IMU's
axis map agrees with the fork's), §6.12 (whether the untracked JP signal assets
are redistributable) and §6.17 (whether the camera topic name this repository
actually emits matches the one derived from the fork's source). The class and
effort counts above are unaffected — a scoped marker never changes a verdict.

**Combined with §5.0.4**, the whole catalog is 53 entries: 14 already-exists,
8 extension-side work, 21 seam/sensor-side, 10 seam/ROS-side. The side-branch
half skews far harder toward CARLA-core seam work (18 of 25, vs 13 of 28 on
main), which is the single most decision-relevant fact in this section: main's
capabilities are largely ROS-layer, the side branches' largely are not.

---

### 6.1 DDS vendor abstraction with a CycloneDDS backend

- What it does: splits every ROS 2 endpoint into a vendor-neutral
  `dds/DDSPublisherImpl.h` / `dds/DDSSubscriberImpl.h` interface plus two
  complete backends — `dds/fastdds/` (factory, listeners, type registry, 23
  publishers, 4 subscribers) and `dds/cyclonedds/` (the same set again, plus
  `CycloneDDSConversions.hpp` and `CycloneDDSTypeRegistry`) — selected at
  **configure time** by a new `CARLA_DDS_VENDOR` CMake cache variable
  (`FastDDS` default, `CycloneDDS` alternative), threaded through
  `CarlaSetup.sh --dds-vendor=`, and resolved at link time by a
  `Carla.Build.cs` that probes for `libddsc.so` vs `libfastrtps.so` and adds
  whichever is present. `Docs/ros2_native.md` gains a "DDS Vendor Selection"
  section.
- Maturity evidence: branch `tier4/experiment/cyclonedds-support` @
  `ab8cc46349c54090acaad58a9785659f37122cbe` — genuinely unmerged (263 commits
  ahead of `tier4/main`); the tip commit is still a fix
  (`add default QoS values to TopicConfig to fix CycloneDDS writer creation`).
  A second, later implementation of the same idea for the `ue5-dev` lineage
  exists on `tier4/feature/ue5-dev-cyclonedds-support` @ `011032e97` and is an
  ancestor of `tier4/feature/ue5-dev-autoware-integration` @ `16a71014`.
- Reproduction path: already-exists
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/dds/DDSPublisherImpl.h`,
  `.../dds/cyclonedds/{CycloneDDSFactory.cpp,CycloneDDSTypeRegistry.{h,cpp},CycloneDDSPublisherImpl.{h,cpp}}`,
  `.../dds/fastdds/FastDDSFactory.cpp`, `CMake/Options.cmake`, `CarlaSetup.sh`,
  `Docs/ros2_native.md`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Carla.Build.cs` (tier4, three-dot
  diff read in full); the fork's
  `LibCarla/source/carla/ros2/middleware/{Middleware.h,ActiveMiddleware.{h,cpp},MiddlewareFactory.h,MiddlewareConfig.h}`
  and `middleware/{fastdds,cyclonedds,zenoh}/` read in full from
  `~/src/carla-autoware-integration` at `feat/autoware-seminative-phase-b`;
  `docs/prerequisites.md` (the `#9807–#9816` middleware-abstraction row),
  `docs/running-e2e.md` (`--ros2 --rmw=cyclonedds`), `docs/g0-report.md` and
  `docs/e2e-report.md` (`rmw_cyclonedds_cpp` in the pinned gate environment)
  (extension). **The spec's pre-classification is confirmed, and the fork is a
  strict superset on three axes**, each verified by reading rather than assumed:
  it carries a third backend (Zenoh); selection is a **runtime** argument
  (`ROS2::Enable(bool, Middleware, int domain_id)` fed by `--rmw=`, with
  `SetActiveMiddleware` / `GetActiveMiddleware` exported DDS-free across the
  shared-library boundary) where tier4's is compile-time-exclusive; and the
  whole G0–G3 evidence chain was recorded over CycloneDDS, so this is a run
  capability rather than a branch claim. The one thing tier4 has that the fork
  does not is a `Carla.Build.cs` that auto-detects the installed vendor —
  irrelevant once selection is runtime.

### 6.2 CycloneDDS publisher/type code generator

- What it does: `tools/generate_cyclonedds_publishers.py` (637 lines)
  mechanically emits the CycloneDDS twin of each FastDDS publisher and the
  matching IDL-derived type support, so the 23-publisher × 2-vendor matrix in
  §6.1 does not have to be hand-maintained. The branch's own history shows the
  generator being re-run and its output hand-patched several times
  (`chore(ros2): regenerate CycloneDDS files with header comments, re-apply
manual fixes`, `fix(tools): fix sed quoting in type generation script,
regenerate types`, `fix(ros2): add missing string backing stores to 5
CycloneDDS publishers`, `fix(ros2): normalize DDS wire format type names in
FastDDS TypeRegistry`).
- Maturity evidence: branch `tier4/experiment/cyclonedds-support` @
  `ab8cc46349c54090acaad58a9785659f37122cbe` (unmerged)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `tools/generate_cyclonedds_publishers.py`,
  `LibCarla/source/carla/ros2/dds/cyclonedds/publishers/` (23 generated files)
  and the branch's commit log (tier4); the fork's
  `LibCarla/source/carla/ros2/middleware/fastdds/GenericCdrPubSubType.h`,
  `middleware/cyclonedds/CycloneDDSSertype.{h,cpp}` and
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h`
  (`create_publisher` / `publish` take a **raw CDR buffer**, encapsulation header
  included) (extension). Recorded as a separate entry from §6.1 because it is a
  separate artifact, but the honest framing is that the fork **designs the need
  away** rather than reproducing the tool: because both fork backends serialize
  an opaque CDR blob with a per-type name and hash, one publisher
  implementation serves every message type and there is no per-type file to
  generate. So no work remains to have the capability (CycloneDDS endpoints for
  every Autoware type) — but this repository has no counterpart to the
  _generator_, and would need one if it ever adopted tier4's IDL-typed endpoint
  style. Read the verdict as "the end is already reached", not "the tool
  exists".

### 6.3 Agnocast zero-copy shared-memory sensor transport

- What it does: adds `LibCarla/source/carla/ros2/agnocast/` — a POSIX shared
  memory protocol (`ShmProtocol.h`: cache-line-aligned `ShmHeader` /
  `SlotMetadata`, a 3-slot triple buffer, a 64-entry
  `/carla_agnocast_registry` segment mapping sensor id → segment name, all with
  `static_assert`ed layouts), a `ShmWriter` that creates one segment per sensor
  (10 MiB for LiDAR, 3840×2160×4 for RGB camera) and a `TripleBufferWriter`,
  and a `SensorRegistryWriter` / `SensorRegistryReader` pair. `ROS2::Enable`
  lazily brings up the writer; `ProcessDataFromCamera` and
  `ProcessDataFromLidar` then **skip the FastDDS `Publish()` entirely** and
  write the pixel/point payload into shared memory instead. Gated behind a new
  `ENABLE_AGNOCAST` CMake option (hard-errors without `ENABLE_ROS2`), linking
  `rt`. `PythonAPI/examples/autoware_demo_with_agnocast.py` wraps
  `autoware_demo.py` and inspects `/dev/shm` for the registry.
- Maturity evidence: branch `tier4/feature/agnocast-integration` @
  `cb6539a45d8a826467d237d1ab9fa28881b31ab3` — genuinely unmerged (220 commits
  ahead of `tier4/main`). The consuming half is **not in this repository**: a
  `git ls-tree -r | grep -i agnocast` at the tip returns only the seven files
  above, and the demo script's own instructions require
  `ros2 launch carla_agnocast_bridge carla_agnocast_bridge.launch.xml` plus
  `ENABLE_AGNOCAST=1 ros2 launch autoware_launch …` from outside the tree. The
  branch history also records the design oscillating
  (`feat: skip FastDDS publish … when Agnocast enabled` → `revert: re-enable
FastDDS publish … alongside Agnocast` → `feat: skip … when Agnocast active`),
  and the tip is `chore: remove debug fprintf, add null checks`.
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: L
- Verified by: `LibCarla/source/carla/ros2/agnocast/{ShmProtocol.h,ShmWriter.{h,cpp},SensorRegistry.{h,cpp},TripleBuffer.h}`,
  `LibCarla/source/carla/ros2/{ROS2.cpp,ROS2.h}` (the `EnableAgnocast` hook and
  the two `#if defined(ENABLE_AGNOCAST) if (!_agnocast_enabled)` publish gates),
  `CMake/Options.cmake`, `CMakeLists.txt`,
  `Ros2Native/LibCarlaRos2Native/CMakeLists.txt`,
  `PythonAPI/examples/autoware_demo_with_agnocast.py` (tier4, three-dot diff read
  in full); `extension/include/carla/ros2/extension/CarlaRos2Extension.h`
  (extension). Camera and LiDAR payloads never cross the C ABI — the extension's
  only registered observer is `VEHICLE_STATUS` (§5.0.2) — and the shm write
  replaces a publish call **inside** `ROS2::ProcessDataFrom*`, so no `.so`-side
  path exists at any effort. **ROS-side** under §5.0.3, on
  `PythonAPI/carla/src/Sensor.cpp:26` (`.def("listen", &SubscribeToStream)`):
  the underlying data — image pixels, LiDAR points — is already delivered to any
  CARLA client through the existing sensor stream, and what tier4 changes is
  only _how it reaches the consumer_, which is exactly the ROS-side case. The
  honest caveat that the rule does not capture: the _performance property_
  (zero-copy, no serialization, no DDS hop) is precisely what a `listen()`-based
  bridge cannot have, since it has already paid a copy over the streaming
  socket. L rather than M because the CARLA half (792 lines) is the smaller
  half: a usable capability also needs the `carla_agnocast_bridge` node, an
  Agnocast-enabled Autoware launch, and the Agnocast kernel module, none of
  which exist in either tree.

### 6.4 RGL GPU ray-traced LiDAR sensor (`sensor.lidar.rgl`)

- What it does: integrates RobotecAI's `RobotecGPULidar` as a second LiDAR
  implementation. `ARGLLidar` is a new `ASensor` subclass (not a
  `ARayCastSemanticLidar` subclass) registered as `sensor.lidar.rgl`, whose
  `PostPhysTick` drives an RGL/OptiX compute graph instead of UE line traces
  while keeping the stock `LidarData` → `LidarSerializer` → stream output path;
  all RGL calls go through an `IRGLBackend` interface so the `UCLASS` compiles
  without RGL present. A separate `CarlaRGL` UE plugin holds the implementation
  (`RGLBackendImpl`, `RGLSceneManager` for registering UE geometry into the RGL
  scene, `RGLDynLoader` for `dlopen`/`dlsym` of `libRobotecGPULidar.so`,
  `RGLCoordinateUtils`) plus a `RclcppBridge` ExternalProject built with the
  **system** compiler against `/opt/ros/humble` to arbitrate rclcpp/DDS domain
  ownership between CARLA and RGL's own ROS 2 publisher. `RglSetup.sh` is a
  three-step `prepare` / `CarlaSetup.sh` / `build` workflow that clones and
  builds RGL and its colcon extensions, verifies CUDA + OptiX 7.2 + ROS 2
  Humble + `patchelf`, and carries three stale-artifact detectors that wipe
  relocated CMake/colcon caches. A `bRglRos2Active` flag lets RGL publish the
  point cloud itself and suppresses CARLA's own ROS 2 publish; viewport point
  drawing is controllable by three blueprint attributes. `README_RGL.md` (235
  lines) documents the whole flow.
- Maturity evidence: branch `tier4/feature/rgl-on-ue5-dev-autoware-integration`
  @ `93d920f571e28b11c4a8bc895d060e4fb83563b6` — **merged into `tier4/main`**
  (0 commits ahead of it), i.e. shipped on the default branch, not an
  experiment. `tier4/feature/rgl-support` @ `19b5eae7d` is a separate, earlier
  and architecturally distinct attempt (a native
  `Carla/RGL/RGLSceneManager.cpp` + `Sensor/RGLLidar.cpp` with no `CarlaRGL`
  plugin and no `RglSetup.sh`) that is not an ancestor of this branch (§2); it
  is folded here rather than given its own entry because it is a superseded
  implementation of the same capability.
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: L
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/RGLLidar.{h,cpp}`,
  `.../Carla/Source/Carla/RGL/IRGLBackend.{h,cpp}`,
  `Unreal/CarlaUnreal/Plugins/CarlaRGL/Source/CarlaRGL/{RGLBackendImpl.{h,cpp},RGLSceneManager.{h,cpp},RGLDynLoader.{h,cpp},RGLCoordinateUtils.h,CarlaRGLModule.{h,cpp},CarlaRGL.Build.cs}`,
  `.../CarlaRGL/ThirdParty/RclcppBridge/{RclcppBridge.{h,cpp},CMakeLists.txt}`,
  `RglSetup.sh`, `README_RGL.md`, `PythonAPI/examples/rgl_test_autoware_demo.py`
  (tier4, read at the pinned tip by `git ls-tree` inventory + `git show`, see
  §6.0.1's recorded limit — no commit range isolates this work);
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h`,
  `runner/spawn.py` (`sensor.lidar.ray_cast` only; a repository-wide grep for
  `rgl` finds exactly one hit, `benchmarks/patches/tier4-native/README.md:158`,
  which records that RGL is _not_ on `tier4/autoware-support`) (extension). A
  new UE sensor class, a new UE plugin, an OptiX/CUDA dependency and a
  scene-registration path into a third-party ray tracer are all upstream of the
  C ABI by construction; no `.so` can install them. **Sensor-side** under
  §5.0.3: a grep of `PythonAPI/carla/src/`, `LibCarla/source/carla/client/` and
  `LibCarla/source/carla/rpc/` at the pinned SHA finds **no** client API through
  which GPU-ray-traced returns are obtainable — the measurement does not exist
  outside CARLA core, so a bridge, an in-tree native stack and this extension
  would each need the identical core change. L is driven by the out-of-CARLA
  surface as much as by the in-tree code: OptiX SDK 7.2, a CUDA toolchain, a
  `develop`-branch RGL clone, colcon-built RGL extensions and a bespoke
  rclcpp bridge library are all build-environment prerequisites this repository
  does not have today.

### 6.5 RGL real-sensor model presets and scan geometry

- What it does: `PythonAPI/rgl/lidar_models/` is a preset library for 15 real
  LiDAR products — `VelodyneVLP16/VLP32C/VLS128`, `HesaiPandar40P`,
  `HesaiPandarQT`, `HesaiPandarXT32`, `HesaiQT128C2X`, `HesaiPandar128E4X` (+ a
  high-resolution variant), `HesaiAT128E2X`, `OusterOS1_64`, `SickMRS6000`,
  a range meter — each giving per-channel elevation angles, azimuth offsets,
  ring ids and firing patterns, applied to the `sensor.lidar.rgl` blueprint
  through an `apply_preset(bp, model, …)` entry point. Two correctness passes
  ride on top: `fix/rgl-ring-id-0based` renumbers every preset's `ring_ids` from
  1-based to 0-based channel indexing (11 preset files, plus a regression test),
  and `feature/vehicle-sim-package` later re-emits rays in azimuth-major rather
  than channel-major order and re-syncs the Hesai presets to the verified
  wire geometry. A `PythonAPI/rgl/tests/` harness (`test_regression.py`,
  `test_preset_visual.py`, `test_special_firing.py`, `test_benchmark.py`,
  `compare_lidar_topics.py`, `measure_lidar_rate.py`) pins the results.
- Maturity evidence: `tier4/fix/rgl-ring-id-0based` @
  `fbbc380567870f8180c48c0a0ebdc84996b5d781` is 1 commit ahead of `tier4/main`
  (genuinely unmerged, though the same change appears rebased as `ab013745a` on
  `tier4/feature/lidar-udp-raw-packet`, which **is** merged into `main`); the
  preset library itself and the azimuth-major fix are on
  `tier4/feature/vehicle-sim-package` @
  `5642dfdd2fb5035f0435f4ce6a50d477800b6248` = `tier4/main`'s tip, i.e. shipped.
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: M
- Verified by: `PythonAPI/rgl/lidar_models/__init__.py` and the 15 model
  modules, `PythonAPI/rgl/tests/test_regression.py`,
  `Unreal/CarlaUnreal/Plugins/CarlaRGL/Source/CarlaRGL/RGLBackendImpl.cpp`
  (the ray-emission order and `SweepCenterOffset` handling),
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/LidarDescription.h`
  (tier4; `fix/rgl-ring-id-0based` and `feature/lidar-udp-raw-packet` isolated
  per §6.0.1); `runner/spawn.py` (`--lidar-channels` / `--lidar-pps` /
  `--lidar-rotation-hz` / `--lidar-range`, i.e. a uniform-FOV ray-cast LiDAR
  parameterized by four scalars — no per-channel elevation table exists),
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension).
  Classed on the dominant blocker exactly as §5.13 was: the preset _tables_ are
  pure client-side Python and a `runner/` module could hold them at S, but there
  is nothing for them to configure without §6.4, and the ray-order and
  sweep-offset halves are inside `RGLBackendImpl.cpp`. **Sensor-side** under
  §5.0.3: the nearest existing client API is the stock ray-cast LiDAR blueprint
  (`Channels` / `UpperFovLimit` / `LowerFovLimit` / `PointsPerSecond` /
  `RotationFrequency` / `HorizontalFov` — the complete geometry surface of
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/LidarDescription.h`),
  which can only express an evenly subdivided FOV — the per-channel angle table
  a real product has is obtainable through no client API, so every integration
  approach needs the same core change. Worth flagging for the comparison: §5.14
  notes that tier4's `PointXYZIRCAEDT` publisher **synthesizes** per-channel
  elevations by even FOV subdivision; this branch is where the real tables
  finally arrive, which makes §5.14's synthesized values a stopgap in tier4's
  own eyes.

### 6.6 RGL distance-culled dynamic scene registration

- What it does: cuts RGL's VRAM footprint by registering into the RGL scene only
  the UE geometry within a radius of the sensor, re-evaluated as the world
  moves, rather than the whole level once. `RGLSceneManager` (296 changed lines in the `.cpp`, 68 in the header) gains
  the distance-culling state machine and, in a second commit, support for **several
  spatially separated sensors** sharing one RGL scene (the union of their
  neighbourhoods, not one sensor's), a guard against removing scene entries
  whose UE component key has already been destroyed, and a
  `test_multisensor_culling.sh` regression harness with a no-culling baseline
  run last for comparison.
- Maturity evidence: branch `tier4/feature/rgl-distance-culling-multisensor` @
  `254fa617db11b6c33eb2157a0f7881260d2a85bc` — 7 commits ahead of `tier4/main`,
  i.e. genuinely unmerged; the same first two commits appear rebased
  (`7db5c1b52`, `fc99fc2cf`) on `tier4/feature/lidar-udp-raw-packet`, which is
  merged.
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: M
- Verified by: `Unreal/CarlaUnreal/Plugins/CarlaRGL/Source/CarlaRGL/RGLSceneManager.{h,cpp}`
  (the substantive change),
  `.../CarlaRGL/Source/CarlaRGL/RGLBackendImpl.cpp`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Server/CarlaServer.cpp`,
  `PythonAPI/rgl/tests/test_multisensor_culling.sh`,
  `PythonAPI/examples/rgl_test_autoware_demo.py` (tier4, isolated from
  `893a8e22f` per §6.0.1); `extension/include/carla/ros2/extension/CarlaRos2Extension.h`
  (extension). Depends entirely on §6.4 — there is no RGL scene to cull without
  it. **Sensor-side** under §5.0.3: the datum is which UE meshes are resident in
  a third-party ray tracer's scene, exposed through no client API (the grep in
  §6.4 applies unchanged). Recorded separately from §6.4 because it is the one
  RGL capability that is still unmerged on tier4's own default branch, which
  makes it the least safe of the RGL family to describe as shipped.

### 6.7 Raw-UDP LiDAR packet emission in real driver wire formats

- What it does: makes a `sensor.lidar.rgl` emit **UDP packets in the on-the-wire
  format of the real product** — Velodyne Legacy (1206 B), Hesai Standard,
  PandarQT, XT32, QT128 and Pandar128 — so a production ROS 2 driver
  (`tier4/nebula`) consumes the simulated stream unchanged, with no CARLA-aware
  code anywhere in the pipeline. tier4's own tree carries the CARLA-side half:
  nine `rgl_udp_*` blueprint attributes (`enabled`, `source_ip`, `dest_ip`,
  `dest_port`, `hesai_enable_udp_sequence`, `hesai_blockage_detection`,
  `hesai_pandar_driver_compat`) plus a `horizontal_start_angle` sweep-window
  offset on `LidarDescription`, a `RGLUdpExtensionShim.h` that `dlsym`s
  `rgl_node_points_udp_publish` / `rgl_get_extension_info` and disables itself
  with a warning when absent, a UDP branch appended to the RGL compute graph, a
  per-model `return_mode` whitelist mirrored from AWSIM's
  `LidarUdpPublisher.cs`, an `apply_preset(..., udp_publish={...})` extension,
  and a two-phase verification suite (`test_udp_raw_packets.py`: eight-model
  smoke, a VLP16 packet-structure deep decode, a start-angle end-to-end check;
  `test_phase2_nebula_e2e.py`, 641 lines: launch Nebula in `udp_only` mode,
  decode its `PointCloud2`, check ring counts and ranges per model).
- Maturity evidence: branch `tier4/feature/lidar-udp-raw-packet` @
  `6437fbcc51fca6bdc5d35dbd8ec51cdd8e1c1a18` — **merged into `tier4/main`**
  (0 ahead), with end-to-end verification against the production driver
  documented in `Docs/rgl/phase2_nebula_e2e.md`. The strongest maturity evidence
  of any entry in §6.
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: L
- Verified by: `Docs/rgl/udp_raw_packets.md`, `Docs/rgl/phase2_nebula_e2e.md`,
  `Unreal/CarlaUnreal/Plugins/CarlaRGL/Source/CarlaRGL/{RGLUdpExtensionShim.h,RGLBackendImpl.{h,cpp},RGLDynLoader.cpp}`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/LidarDescription.h`,
  `.../Carla/Actor/ActorBlueprintFunctionLibrary.{h,cpp}`,
  `PythonAPI/rgl/lidar_models/__init__.py`,
  `PythonAPI/rgl/tests/{test_udp_raw_packets.py,test_phase2_nebula_e2e.py}`
  (tier4, isolated from `3d90d023d` per §6.0.1);
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h`,
  `runner/spawn.py` (extension). Nothing about this is reachable from the `.so`:
  the packets are emitted by a compute-graph node inside the RGL library, from
  data that never enters the ABI, on a socket CARLA owns. **Sensor-side** under
  §5.0.3, on the same grep as §6.4 — no client API returns a
  product-wire-format packet, and the whole point of the capability is that the
  consumer is a driver that has never heard of CARLA, which is as
  approach-agnostic as a capability gets. L, and stacked on §6.4's L.
- **needs prototype** — scoped sub-claim only; the seam / sensor-side / L
  verdict above stands. The packet **encoder itself is not in either tree**:
  `Docs/rgl/udp_raw_packets.md` states it lives in
  `RobotecAI/RGL-extension-udp`, a **private** repository requiring an SSH key
  with read access, cloned by `RglSetup.sh --with-udp` (the same mechanism as
  the also-private `--with-weather` extension). Whether that extension is
  obtainable, and under what licence, could not be established from either tree
  and is not guessed at here. Until it is, the reproduction cost of this
  capability is unbounded from this repository's side, and the L above should be
  read as "at least L, conditional on access".

### 6.8 Pandar128E4X high-resolution UDP mode and Hesai driver-compat default

- What it does: extends §6.7 with the Hesai Pandar128E4X's high-resolution
  operating mode — a `HesaiPandar128E4XHighRes` preset wired to RGL's
  `RGL_UDP_HIGH_RESOLUTION_MODE`, added to the Phase-2 Nebula end-to-end matrix
  — and flips `hesai_ros_driver_compat` to default **ON** for Hesai models,
  which changes the effective Hesai sweep start from 0° to −90°
  (`docs(rgl): flag changed default — Hesai sweep start now -90deg`). A
  `test_apply_preset_compat.py` covers the True+Hesai and False+non-Hesai rows.
- Maturity evidence: branch `tier4/feature/pandar128e4x-highres-udp` @
  `25c2ca59ebab77dbaf8accbce842c1271184535d` — **merged into `tier4/main`**
  (0 ahead).
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Docs/rgl/udp_raw_packets.md`, `Docs/rgl/phase2_nebula_e2e.md`,
  `PythonAPI/rgl/lidar_models/__init__.py`,
  `PythonAPI/rgl/lidar_models/hesai_pandar128e4x_highres.py`,
  `PythonAPI/rgl/tests/test_apply_preset_compat.py`,
  `Unreal/CarlaUnreal/Plugins/CarlaRGL/Source/CarlaRGL/{RGLBackendImpl.cpp,RGLUdpExtensionShim.h}`
  (tier4, isolated from `04d0a44c6` per §6.0.1);
  `runner/spawn.py` (extension). Cross-references §6.7: this is a 223-line
  increment on that capability, so S is the _remaining_ delta once §6.7 exists,
  not a standalone cost. It is recorded as its own entry only because the design
  spec names `pandar128e4x-highres-udp` as a separate capability. The
  changed-default note matters for anyone comparing point clouds across the two
  stacks and is reproduced here rather than left in the branch.

### 6.9 `sensor.other.imu_highprecision`: physics-substep IMU with per-sample stamps

- What it does: a new IMU blueprint that publishes **once per Chaos physics
  substep** instead of once per frame. `AInertialMeasurementUnitHighPrecision`
  subclasses the stock IMU, registers an `FIMUSubstepCallback`
  (`Chaos::TSimCallbackObject`, `PostIntegrate`) against the vehicle's
  `FSingleParticlePhysicsProxy` to capture body kinematics on the physics
  thread, and computes gyro by quaternion finite difference and accelerometer by
  second position derivative per substep, each carrying its own timestamp
  offset. A `substep_mode` attribute selects `Auto` / `Substep` / `Upsample`,
  and `output_rate_hz` (default 200) drives a zero-order-hold fallback that
  emits N copies of the frame-rate value when no physics proxy is available.
  Publishing needs a new `ROS2::ProcessDataFromIMUStamped` overload that
  back-dates each sample from the frame stamp; `SensorRegistry` gains an
  `imu_highprecision` entry appended **at the end** so the wire type ids stay
  additive. A `PythonAPI/examples/imu_highprecision_check.py` verifies the rate.
- Maturity evidence: branch `tier4/feature/lidar-udp-raw-packet` @
  `6437fbcc51fca6bdc5d35dbd8ec51cdd8e1c1a18` — **merged into `tier4/main`**
  (0 ahead). Not spec-named; found by reading the branch's commit range rather
  than its name (`7b67c41cf`, `a21224efb`, `d686895b6`, `1a71c6efb`).
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: M
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/InertialMeasurementUnitHighPrecision.{h,cpp}`,
  `.../Carla/Sensor/IMUSubstepCallback.{h,cpp}`,
  `.../Carla/Sensor/InertialMeasurementUnit.h`,
  `.../Carla/Actor/ActorBlueprintFunctionLibrary.{h,cpp}`,
  `LibCarla/source/carla/ros2/{ROS2.h,ROS2.cpp}` (`ProcessDataFromIMUStamped`),
  `LibCarla/source/carla/sensor/SensorRegistry.h`,
  `PythonAPI/examples/imu_highprecision_check.py` (tier4, isolated from
  `3d90d023d` per §6.0.1); `runner/spawn.py` (the IMU is a stock
  `sensor.other.imu` spawned natively at the kit's `tamagawa/imu_link`),
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (the
  `CARLA_ROS2_SENSOR_IMU` kind is reserved but unregistered — the same finding
  as §5.19) (extension). **Sensor-side** under §5.0.3: the datum is the vehicle
  body's kinematics sampled between frames, and a grep of
  `PythonAPI/carla/src/`, `LibCarla/source/carla/client/` and
  `LibCarla/source/carla/rpc/` at the pinned SHA finds **no** sub-frame
  kinematics accessor — the nearest client API,
  `carla.IMUMeasurement` via `sensor.listen()`, is delivered once per frame by
  construction, so no integration approach can synthesize substep samples
  without this core change. M rather than S because the substep path is a Chaos
  physics-thread callback, not a tick hook.
- **needs prototype** — scoped sub-claim only; the seam / sensor-side / M
  verdict above stands. Whether this sensor's axis convention agrees with the
  fork's was **not** established. §5.20 already records that tier4's ROS-layer
  gyroscope flip `(x, −y, −z)` and the fork's `(−x, y, −z)` disagree and that
  code reading cannot adjudicate them; this sensor computes its gyro by a
  different method again (quaternion finite difference on the physics thread,
  not a Chaos angular-velocity read), so its numbers were not compared
  field-for-field against either. Treat "tier4 has a high-rate IMU" as a claim
  about the capability, not about sign agreement.

### 6.10 Turn-indicator and hazard-light command echo as vehicle status

- What it does: adds `AutowareController::GetTurnIndicatorCommand()` /
  `GetHazardLightsCommand()`, backed by a new `PeekMessage()` on the subscriber
  reader that samples the last received command **without** clearing the
  changed-flag the control loop uses, and feeds those values back out as
  `TurnIndicatorsReport` / `HazardLightsReport`. The commit comment states the
  rationale explicitly: "CARLA does not actuate the ego blinker from these
  commands, so they are echoed back as vehicle status to keep the Autoware
  feedback loop closed (the planner consumes the status)."
- Maturity evidence: branch `tier4/feature/lidar-udp-raw-packet` @
  `6437fbcc51fca6bdc5d35dbd8ec51cdd8e1c1a18` — **merged into `tier4/main`**
  (0 ahead); commit `f45eb4e3d`.
- Reproduction path: already-exists
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/subscribers/AutowareController.h`,
  `LibCarla/source/carla/ros2/dds/cyclonedds/subscribers/AutowareController.cpp`
  (tier4, isolated from `3d90d023d` per §6.0.1);
  `extension/src/publishers/StatusPublishers.cpp`,
  `extension/src/subscribers/ControlSubscribers.cpp` (extension). This is the
  one place in the whole catalog where a tier4 side branch **converges on
  behaviour this repository already had**: §5.10 records that
  `tier4/autoware-support` decodes the ego's _actual_ light state from the
  status sensor while the extension echoes the commanded
  `turn_indicators_cmd` / `hazard_lights_cmd` bytes, and notes that the echo "is
  arguably the more useful signal for a closed loop, since neither
  implementation actuates the lights". This branch adopts exactly that. Two
  small deltas remain, neither requiring core work: tier4 echoes only when the
  actual-state path is unavailable on this lineage, and it introduces
  `PeekMessage()` to avoid stealing the control loop's handshake, where the
  extension caches each command byte atomically for the same reason. Read this
  entry as evidence that the design question is settled the same way on both
  sides, not as a gap.

### 6.11 Acceleration-control steering dropout fix

- What it does: one line plus a five-line comment in
  `ACarlaWheeledVehicle::ApplyVehicleAccelerationControl` — also assign
  `DesiredSteer = Steer`, because `FlushVehicleControl` derives the applied
  steer from `DesiredSteer` and overwrites `ControlToApply.Steer` with it, so
  the acceleration-control path was dropping the Autoware steer command entirely
  and "the vehicle drives straight (no turn)".
- Maturity evidence: branch `tier4/feature/lidar-udp-raw-packet` @
  `6437fbcc51fca6bdc5d35dbd8ec51cdd8e1c1a18` — **merged into `tier4/main`**
  (0 ahead); commit `ab7926231`.
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Vehicle/CarlaWheeledVehicle.cpp`
  (tier4, isolated from `3d90d023d` per §6.0.1);
  `extension/src/subscribers/ControlSubscribers.cpp`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h`
  (`apply_ackermann_control` is the extension's only actuation primitive)
  (extension). It is seam work by the same argument as §5.17 — a UE vehicle
  component's input flushing, which no `.so` can reach — and **sensor-side**
  under §5.0.3 because the affected quantity is the physical steer the vehicle
  applies, produced by no client API (`vehicle.get_control().steer`, cited at
  §5.8, returns the _commanded_ value and would report the un-dropped command
  either way). The practical reproduction cost for this repository is
  nevertheless **zero**: the defect is in the acceleration-control component the
  extension deliberately does not use, and the Ackermann path it uses instead
  passes steer through `ApplyVehicleAckermannControl`. Recorded because it is
  useful evidence in the other direction — anyone arguing that tier4's
  acceleration-integration actuation (§5.17) is more faithful than
  `apply_ackermann_control` should know it shipped with a steering dropout
  serious enough to need this fix.

### 6.12 lanelet2-driven traffic-light placement toolchain and JP signal assets

- What it does: builds Japanese traffic signals into a UE level **from the same
  lanelet2 `.osm` Autoware navigates by**, so signal ids match between simulator
  and planner. `PythonAPI/util/lanelet2_traffic_light/` (74 files) is a layered
  package: a `corelib` with a lanelet2 OSM parser (nodes, ways, regulatory
  elements, `light_bulbs`, optional `ele` elevation), an MGRS transform, a pose
  estimator, a traffic-light IR, a JP signal profile, a way-id resolver and an
  OSM feedback writer that allocates ids for pedestrian signals missing from the
  source map; and a `frontend_editor` that runs inside the UE editor — a
  blueprint factory, arrow/LED material setup, mesh transplant and cleanup, snap
  targeting with Pole/Ground exclusion, subtype splitting into vehicle/pedestrian
  controllers, group deduplication, label naming (`TLV_`/`TLP_`), a save-level
  resolver and a `run_placement` orchestrator surfaced as an Editor Utility
  Widget. 35 `.uasset` JP signal assets under a new
  `Unreal/CarlaUnreal/Plugins/T4/Content/` plugin content root (arrow textures,
  LED dot materials, lens meshes, vehicle and pedestrian traffic-light
  blueprints) plus a `DefaultGame.ini` cook entry for an Odaiba map, an
  `init_unreal.py` editor-menu hook, and 25 pytest modules covering the
  pure-Python layer.
- Maturity evidence: branch `tier4/feature/lanelet2-traffic-light` @
  `2dbe5a6c25b7984059b072a2ab70ae2ce34737a5` — **merged into `tier4/main`**
  (0 ahead). Imported from a separate tier4 repository
  (`feat: import lanelet2_traffic_light package from tier4/odaiba-carla`) and
  developed over ~110 commits.
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: L
- Verified by: `PythonAPI/util/lanelet2_traffic_light/` (the full 74-file
  inventory via `git diff --name-only 583f9238e..`, with
  `corelib/parser/lanelet2_parser.py`, `corelib/geometry/mgrs_transform.py`,
  `frontend_editor/editor_placer.py` and `README.md` read),
  `Unreal/CarlaUnreal/Content/Python/init_unreal.py`,
  `Unreal/CarlaUnreal/Config/DefaultGame.ini`,
  `Unreal/CarlaUnreal/Plugins/T4/Content/{Lanelet2TrafficLight,TrafficLightSample/VehicleTrafficLight,TrafficLightSample/PedestrianTrafficLight}/*.uasset`
  (tier4, isolated from `583f9238e` per §6.0.1);
  `docs/nishishinjuku-map.md`, `runner/__main__.py` (`--map`), a
  repository-wide grep for `lanelet2_traffic_light` returning no hit
  (extension). This is level authoring, not integration code: it runs in the UE
  editor, writes `.umap` content and ships binary assets. **Sensor-side** under
  §5.0.3 for the same reason §5.12 (the MGRS geo-reference asset) is: what a
  level contains is a world-authoring property that a bridge, an in-tree native
  stack and this extension would each consume identically, and no client API
  places actors into a cooked level. L: the toolchain is the smaller half — the
  capability also needs the JP signal art, a map whose lanelet2 source has
  matching regulatory elements, and an editor workflow this repository has no
  counterpart to.
- **needs prototype** — scoped sub-claim only; the seam / sensor-side / L
  verdict above stands. §5.24 records that
  `git ls-tree -r tier4/autoware-support -- Unreal/CarlaUnreal/Content` returns
  **0 files**, i.e. the Nishi-Shinjuku map content is untracked. That is _not_
  true here — these 35 `.uasset` files **are** tracked — but they were counted,
  not opened, and whether they are redistributable (they are JP signal art of
  unstated provenance, imported from `tier4/odaiba-carla`) could not be
  established from the tree. Anyone costing a reproduction should resolve that
  before assuming the assets come with the code.

### 6.13 Traffic-light arrow-state API

- What it does: gives CARLA traffic lights a directional-arrow state alongside
  the stock red/yellow/green. `carla::rpc::TrafficLightArrowState` defines a
  frozen 32-bit `(colour × direction)` bitmask — 8 directions
  (Left, Straight, Right, UpLeft, UpRight, Down, DownLeft, DownRight) × 3 colour
  rows + 7 user bits — with the layout documented as never-renumberable because
  baked map content stamps the bits. `ATrafficLightBase` gains `ArrowState` and
  `ArrowCapabilities` `UPROPERTY`s (the latter recording which arrow faces
  physically exist on the mesh, so `requested & ~capabilities` is the set that
  cannot light), `Set/GetArrowState`, `GetArrowCapabilities`, and an
  `OnArrowStateChanged` `BlueprintImplementableEvent` mirroring the existing
  state-changed event. Three RPCs (`set_traffic_light_arrow_state`,
  `get_traffic_light_arrow_state`, `get_traffic_light_arrow_capabilities`) are
  threaded through `FCarlaActor`, `carla::client::TrafficLight` and the Python
  API as `set_arrow_state` / `get_arrow_state` / `get_arrow_capabilities` plus a
  32-value `carla.TrafficLightArrow` enum.
- Maturity evidence: branch `tier4/feature/lanelet2-traffic-light` @
  `2dbe5a6c25b7984059b072a2ab70ae2ce34737a5` — **merged into `tier4/main`**
  (0 ahead)
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: M
- Verified by: `LibCarla/source/carla/rpc/TrafficLightArrowState.h`,
  `LibCarla/source/carla/client/TrafficLight.{h,cpp}`,
  `LibCarla/source/carla/client/detail/{Client.h,Client.cpp,Simulator.h}`,
  `PythonAPI/carla/src/Actor.cpp`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Traffic/TrafficLightBase.{h,cpp}`,
  `.../Carla/Actor/CarlaActor.{h,cpp}`, `.../Carla/Server/CarlaServer.cpp`
  (tier4, isolated from `583f9238e` per §6.0.1);
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (the ABI has no
  traffic-light surface at all — the only inbound observer is
  `VEHICLE_STATUS`), `runner/spawn.py` (extension). **Sensor-side** under
  §5.0.3, and this is the case §5.0.3's first consequence bullet warns about
  in reverse: it ships an RPC, but the RPC is not the capability. Reading
  `LibCarla/source/carla/client/TrafficLight.h` at the pinned baseline SHA, the
  complete client surface is `SetState` / `GetState` / `Set|GetGreenTime` /
  `Yellow` / `Red` / `GetElapsedTime` / `Freeze` / `IsFrozen` / `GetPoleIndex` /
  `ResetGroup` — **no arrow accessor of any kind**, and the underlying datum is
  a `UPROPERTY` on a UE actor that does not exist until this branch adds it, so
  a Python bridge would need the identical core change. M rather than S because
  the bitmask is a wire contract that must be frozen before any map content is
  baked against it, and because `ArrowCapabilities` has to be stamped by the
  placement toolchain (§6.12) to be meaningful.

### 6.14 Level-placed actor `key:value` tags as client actor attributes

- What it does: 12 lines in `UCarlaEpisode::InitializeAtBeginPlay` that split
  each level-placed traffic sign's UE `Actor->Tags` on `:` and add every
  well-formed pair to the `FActorDescription::Variations` map, so a tag written
  in the editor as `lanelet2_id:1412` or `signal_kind:vehicle` surfaces to any
  CARLA client as `actor.attributes["lanelet2_id"]`. This is the mechanism that
  makes level-authored identity (§6.12's placer stamps the tags) reachable
  without a bespoke RPC, and it is what `carla_v2i` (§6.15) and
  `t4_signal_utils.py` key off.
- Maturity evidence: branch `tier4/feature/lanelet2-traffic-light` @
  `2dbe5a6c25b7984059b072a2ab70ae2ce34737a5` — **merged into `tier4/main`**
  (0 ahead)
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Game/CarlaEpisode.cpp`
  (the `InitializeAtBeginPlay` tag loop),
  `PythonAPI/util/lanelet2_traffic_light/frontend_editor/editor_placer.py:713`
  (which documents stamping `lanelet2_id:<sign_id>` /
  `signal_kind:<vehicle|pedestrian>`),
  `PythonAPI/examples/t4_signal_utils.py` (tier4, isolated from `583f9238e` per
  §6.0.1); `runner/spawn.py`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension).
  **Sensor-side** under §5.0.3, decided by a grep that found nothing: searching
  `CarlaServer.cpp`, `Unreal/.../Carla/Actor/`,
  `LibCarla/source/carla/client/` and `PythonAPI/carla/src/` at the pinned
  baseline SHA for `Actor->Tags` / `GetActorTags` / `actor_tags` returns **no**
  binding — the only tag-like client property is `semantic_tags`
  (`PythonAPI/carla/src/Actor.cpp:104`), which carries
  `rpc::CityObjectLabel` segmentation labels, an unrelated quantity. UE actor
  tags on level-placed actors are therefore visible to no integration approach
  today, so all three need the same core change. Recorded separately from §6.12
  because it is a **generic** mechanism with no lanelet2 content in it, and is
  by far the cheapest single upstreamable piece of the traffic-light family.

### 6.15 V2I traffic-signal publisher (`carla_v2i`)

- What it does: a standalone rclpy node (`python3 -m carla_v2i --osm-path …`)
  that publishes CARLA's live traffic-light states as
  `autoware_perception_msgs/TrafficLightGroupArray` on `/v2x/traffic_signals` at
  10 Hz, RELIABLE / VOLATILE / KEEP_LAST(1), so Autoware obeys signals through
  `autoware_traffic_light_arbiter`'s `external_traffic_signals` input with no
  camera recognition. A pure `conversion.py` maps CARLA state + arrow mask +
  vehicle/pedestrian kind onto `TrafficLightElement` colour/shape/status triples
  (mirroring AWSIM's `V2IRos2Publisher`, including reporting pedestrian yellow as
  green-flashing), builds the lanelet2 relation → way grouping from the `.osm`,
  and asserts at startup that its mirrored message constants still match the
  installed `autoware_perception_msgs`. The node reads CARLA on a background
  thread (a full sweep of ~120 lights costs ~1 s of sequential RPC, far over the
  100 ms publish period), supports an ego-radius filter, skips the arrow RPC for
  pedestrian lights, and — in the last three commits — emits
  `PredictedTrafficLightState` entries for CARLA-cycled lights from
  `get_elapsed_time` / `get_green_time` / `get_yellow_time` / `get_red_time`. A
  `verify_topic.py` is the topic-level verification gate.
- Maturity evidence: branch `tier4/feature/autoware-v2i-publisher` @
  `1ab5fecd532979fbafda137f6c2fc120c6e72f37` — genuinely unmerged (8 commits
  ahead of `tier4/main`); the tip is a "verify-gate freeze note".
- Reproduction path: extension-side work
- Effort class: M
- Verified by: `PythonAPI/util/carla_v2i/{README.md,node.py,conversion.py,verify_topic.py,tests/test_conversion.py}`
  (tier4, isolated from `a23011c20` per §6.0.1);
  `benchmarks/injector/dummy_perception.py`,
  `benchmarks/injector/gen_tl_groups.py`, `tests/e2e/test_dummy_perception.py`,
  `tests/benchmarks/test_tl_groups.py`, `docker/compose.yaml` (extension).
  **The spec's pre-classification (V2I publisher = extension-side work) is
  confirmed for the node itself, and it is cheaper than the spec implies**:
  nothing here touches the C ABI at all — it is an out-of-process rclpy client,
  the same shape as the runner. This repository is further along than a blank
  sheet: `dummy_perception.py` already publishes `TrafficLightGroupArray` with
  `TrafficLightElement` colour/shape/status fields, and `gen_tl_groups.py`
  already extracts group ids from the lanelet2 `.osm` by exactly the same rule
  (`type=regulatory_element` + `subtype=traffic_light` relations). The delta is
  real but bounded: read live CARLA state instead of forcing GREEN, publish on
  `/v2x/traffic_signals` instead of
  `/perception/traffic_light_recognition/traffic_signals`, add the relation→way
  grouping and the prediction. **Two hard preconditions the spec does not
  mention, both verified by code reading**: the node discovers lights by
  `actor.attributes.get("lanelet2_id")`, which is empty on any build without
  §6.14 + §6.12 — the dict is then empty and nothing is ever published — and it
  calls `actor.get_arrow_state()` unconditionally for vehicle lights inside a
  `except RuntimeError` block that would **not** catch the `AttributeError` a
  build without §6.13 raises. So M covers the node on a CARLA that already has
  §6.12–§6.14; without them the arrow half is unreachable and only circle
  states could be published, after replacing the discovery key.

### 6.16 Traffic-light subsystem robustness fixes

- What it does: two independent guards in the UE traffic-light subsystem.
  `fix/traffic-light-controller-null-check` guards
  `UTrafficLightController`'s cycle against a null `UTrafficLightComponent`
  (12 added lines), and `fix/traffic-light-freeze` makes
  `ATrafficLightManager::freeze_all_traffic_lights` iterate only the groups it
  actually owns so dynamically spawned groups are skipped rather than
  dereferenced (a net simplification, +9 / −15).
- Maturity evidence: branches `tier4/fix/traffic-light-controller-null-check` @
  `28ead4191bbbb7df1f8f6b9acd13db48f4b34020` and
  `tier4/fix/traffic-light-freeze` @ `87936f3c585b13a568ec67c0cf3d4a4ba01fa167`
  — each 1 commit ahead of `tier4/main`, i.e. genuinely unmerged; both fork from
  the same `583f9238e` lineage point.
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Traffic/TrafficLightController.cpp`,
  `.../Carla/Traffic/TrafficLightManager.cpp` (tier4, `git show --stat` +
  `git show` per §6.0.1); `runner/spawn.py`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension).
  **Sensor-side** under §5.0.3: the fixed behaviour is UE traffic-light
  actor/component lifetime, and the relevant client APIs
  (`world.freeze_all_traffic_lights()` at `PythonAPI/carla/src/World.cpp:335`,
  `carla.TrafficLight.freeze()` at `LibCarla/source/carla/client/TrafficLight.h:54`) are the _callers_ that
  trigger the crash, not a route to the datum — every integration approach that
  spawns traffic lights dynamically hits the same defect. Grouped into one entry
  because they are the same subsystem and the same class of defect; recorded at
  all because a crash guard in a path this repository's dummy-perception feed
  substitutes for (§6.15) is exactly the kind of thing that looks free until a
  campaign spawns a light.

### 6.17 Camera image topic-suffix override on the CycloneDDS publisher family

- What it does: makes the camera image sub-topic suffix configurable rather than
  a hardcoded `"/image"` — every camera publisher takes
  `_impl->_config.suffix` when non-empty, so a caller can select `/image_raw`
  as Autoware expects, and `ROS2.cpp`'s per-camera-type `TopicConfig` sets
  `cam_config.suffix = "/image_raw"` at all seven construction sites.
- Maturity evidence: branch `tier4/feature/ue5-dev-autoware-integration` @
  `16a71014425f6751dc5b21229402c6038e6244a9`, commit `680d0d764` — not
  spec-named as a branch, but the design spec's C3 paragraph names "camera
  topic-suffix/QoS override" as one of its pre-classified examples. **A
  correction to the spec's framing:** the capability is not side-branch work at
  all on the FastDDS side — `git grep 'image_raw' tier4/autoware-support`
  returns `LibCarla/source/carla/ros2/ROS2.cpp:594` (`config.suffix =
"/image_raw"`) and `:604` (`/camera_info`), so it is **already merged on
  `tier4/autoware-support`** and is part of what §5.16 catalogs. `680d0d764` is
  the port of that same mechanism to this lineage's CycloneDDS publisher family.
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/dds/cyclonedds/publishers/Carla{RGB,Depth,SS,IS,Normals,OpticalFlow,DVS}CameraPublisher.cpp`,
  `LibCarla/source/carla/ros2/dds/cyclonedds/ROS2.cpp` (the seven
  `cam_config.suffix = "/image_raw"` sites),
  `LibCarla/source/carla/ros2/data_types.h`,
  and `tier4/autoware-support`'s `LibCarla/source/carla/ros2/ROS2.cpp:594,604`
  - `publishers/CarlaRGBCameraPublisher.cpp:97,150` (tier4, via `git show
680d0d764` and `git grep` at both SHAs); the fork's
    `LibCarla/source/carla/ros2/publishers/CarlaCameraPublisher.cpp:37,40`
    (`_impl_image->Init(GetBaseTopicName() + "/image", …)` — the suffix is a
    **string literal**, with no `has_override` escape of the kind
    `ROS2.cpp:660-675` gives the DVS/radar/point-cloud family), and
    `runner/spawn.py:415` (`camera_topic()` →
    `/sensing/camera/camera<N>/image_raw`, set as both `ros_topic_name` and
    `ros_name`) (extension). **This is a gap derived from code reading on both
    trees, not yet observed on a running stack** — see the scoped marker below
    for exactly what is and is not established. The derivation: because the fork
    appends `"/image"` unconditionally, the runner's `ros_topic_name` override
    should yield `/sensing/camera/camera<N>/image_raw/image` — the base name is
    overridable, the suffix is not, and no combination of blueprint attributes
    produces Autoware's expected topic. `runner/spawn.py`'s own docstring records
    that the M4 camera arm treats "topic names as-emitted" and so never checked.
    **ROS-side**
    under §5.0.3, on `PythonAPI/carla/src/Sensor.cpp:26`
    (`.def("listen", &SubscribeToStream)`): the image is already delivered to any
    client, and what is missing is only the topic name it is published under —
    the textbook ROS-side case, and one a bridge solves for free. S: the fork
    change is the same one-line shape as tier4's, at seven sites.
    Cross-references §5.15 (per-actor `ros_topic_name`, which the fork already
    has) and §5.16 (the `TopicConfig` this suffix rides in).
- **needs prototype** — scoped sub-claim only; the seam / ROS-side / S verdict
  above stands, and so does the reading of tier4's side. What is **not**
  established is the emitted topic name on _our_ stack. Every link in the chain
  was read and holds — `CarlaCameraPublisher.cpp:37`
  (`GetBaseTopicName() + "/image"`, a string literal),
  `CarlaRGBCameraPublisher.h:17,20` (the base name passes straight through),
  `ROS2.cpp:660-675` (the `has_override` suffix-skip exists for the
  DVS/radar/point-cloud family and **not** for the camera), and
  `runner/spawn.py:415-417`. The reading is in fact self-contradicting on the
  fork's side, which is why it is worth settling rather than dropping:
  `BuildBaseTopicName`'s own comment at `ROS2.cpp:565` claims a verbatim
  override skips "the `carla/` segment, the parent chain, AND the per-type
  suffix so the Autoware topic name is emitted exactly as configured", yet
  `CarlaCameraPublisher`'s constructor appends `/image` unconditionally, with
  no `has_override` parameter to honour that claim — so either the comment or
  the camera path is wrong. **But it was not observed.** No native-camera topic
  list exists anywhere in this repository's committed evidence: every
  `sensing/camera` string under `benchmarks/results/` comes from the **bridge**
  arm's `autoware_carla_interface` (cells `E0`, `CAM_FRONT`-style names its own
  node chose), `scripts/expected_topics.yaml` contains **zero** camera entries,
  and the G1–G3 gates never spawn a camera. So this is a code-derived
  prediction, held to the same bar §5.14 and §5.20 are held to, not a
  measurement. One `ros2 topic list | grep sensing/camera` on the next live run
  with `--cameras` settles it; until that is on the record the finding must not
  be repeated as observed.

### 6.18 Off-game-thread ROS 2 publish queue

- What it does: `ROS2PublishQueue` is a single-worker task queue that drains
  `std::function<void()>` publish lambdas off the UE game thread, with an
  `Enqueue` for sensors where every sample matters and an `EnqueueLatest` that
  discards pending work for sensors where only the freshest frame does. A second
  branch applies it to the camera path specifically ("offload camera ROS2
  publish to dedicated worker thread"). `ROS2.cpp` starts and drains the queue;
  `LidarData.h` / `SemanticLidarData.h` gain the copy affordances the lambdas
  need to own their captured payloads.
- Maturity evidence: branches `tier4/feature/ros2-async-publish-queue` @
  `2da85dbfabdde8242fa7915f16488083071aded0` and
  `tier4/feature/ros2-async-camera-publish` @
  `83533bc142a49bf4e482954b12bc67da2866051c` — both †-marked in §1.1, so their
  ancestry could not be verified at all (§1.2); each is a single commit dated
  2026-04-01, not spec-named, found by the branch scan. Treat as an experiment,
  not a shipped capability: no test, no doc, and no evidence in either tree that
  it was measured.
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: M
- Verified by: `LibCarla/source/carla/ros2/ROS2PublishQueue.h` (read in full),
  `LibCarla/source/carla/ros2/{ROS2.cpp,ROS2.h}`,
  `LibCarla/source/carla/sensor/data/{LidarData.h,SemanticLidarData.h}`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/Sensor.h` (tier4, two-dot
  per §6.0.1); `extension/include/carla/ros2/extension/CarlaRos2Extension.h`,
  `benchmarks/` and `docs/e2e-report.md` (the G3 cadence gate, 19.96/19.94 Hz)
  (extension). Sensor publishing is entirely core-side, so no `.so` path exists;
  the extension's own endpoints publish from whichever thread calls
  `publish()`, and moving _those_ off the caller would be extension-side, but
  that is not this capability. **ROS-side** under §5.0.3, on
  `PythonAPI/carla/src/Sensor.cpp:26` (`.def("listen", …)`): the datum is
  unchanged sensor data and what moves is only the thread it reaches the
  consumer on — and a bridge already publishes from its own process, so it has
  the property for free, which is exactly what "a different integration approach
  could already reach the datum today" means. M rather than S because the
  correctness burden (lambda-owned payloads, shutdown draining, and the
  latest-wins policy per sensor type) is where the work is, not the 109-line
  header.

### 6.19 Sensor-pipeline stage timing instrumentation

- What it does: brackets the sensor send path with
  `std::chrono::high_resolution_clock` and prints per-stage millisecond timings
  to stderr — `ASceneCaptureSensor::PostPhysTick` reports
  `CaptureScene: %.1fms` around `EnqueueRenderSceneImmediate()`, and
  `FAsyncDataStream`'s send helper in `Sensor.h` reports
  `SendDataToClient: serialize=… ros2=… stream=… total=…` around the
  serialization, ROS 2 publish and streaming stages separately, with a further
  probe in `ImageUtil.cpp`.
- Maturity evidence: branch `tier4/feature/sensor-timing-instrumentation` @
  `0203ee13080aefac6ae905e708aebccc5def98eb` — †-marked in §1.1 (ancestry
  unverifiable, §1.2), a single commit dated 2026-04-01, not spec-named. This is
  explicitly a debugging patch, not a feature: raw `fprintf(stderr, …)` on every
  frame of every sensor, no flag, no sampling, no aggregation, and its own
  commit subject says "for sensor pipeline debugging".
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/Sensor.h`,
  `.../Carla/Sensor/SceneCaptureSensor.cpp`, `.../Carla/Sensor/ImageUtil.cpp`
  (tier4, two-dot per §6.0.1); `benchmarks/`, `tests/benchmarks/`,
  `docs/e2e-report.md` (extension). **Sensor-side** under §5.0.3, decided by a
  grep that found nothing: the datum is the wall-clock cost of stages _inside_
  CARLA's sensor pipeline, and no client API returns it —
  `world.get_snapshot().timestamp` gives frame boundaries, not the serialize /
  ROS 2 / stream split. Any approach wanting this split needs the same core
  probes. Recorded honestly rather than dressed up: this repository measures the
  same territory from outside with a committed harness (`benchmarks/`, the G3
  cadence gate) rather than from inside, which answers a different question, and
  nothing in the extension architecture forbids adding these probes to a fork
  build if a campaign ever needs them.

### 6.20 Actuator dynamics: jerk limits, first-order lag, steer-rate limit

- What it does: gives the ego a configurable actuator model on top of §5.17's
  acceleration control. Four new RPCs —
  `set_actor_constant_acceleration_jerk_limit(pos, neg)`,
  `set_actor_constant_acceleration_first_order_lag_tau(tau)`,
  `set_vehicle_steer_rate_limit(rate)` and
  `set_vehicle_steer_first_order_lag_tau(tau)` — thread through
  `carla::client::Actor` / `Vehicle`, the Python API
  (`set_constant_acceleration_jerk_limit`,
  `set_constant_acceleration_first_order_lag_tau`, `set_steer_rate_limit`,
  `set_steer_first_order_lag_tau`) and into `UVehicleAccelerationControl` and
  `ACarlaWheeledVehicle`, where the commanded acceleration is rate-limited by
  asymmetric positive/negative jerk bounds and lagged by a first-order filter,
  and the steer output is likewise rate-limited and lagged. Each parameter
  disables itself at `<= 0`.
- Maturity evidence: branch `tier4/feature/vehicle-simulation` @
  `98d821be867409bf7825ae73b344bd7da37cb9d7` — **merged into `tier4/main`**
  (0 ahead). Not spec-named; found by the branch scan.
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: M
- Verified by: `LibCarla/source/carla/client/{Actor.h,Actor.cpp,Vehicle.h,Vehicle.cpp,detail/Client.{h,cpp},detail/Simulator.h}`,
  `PythonAPI/carla/src/Actor.cpp`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Server/CarlaServer.cpp`
  (the four new `BIND_SYNC` blocks),
  `.../Carla/Vehicle/{CarlaWheeledVehicle.{h,cpp},VehicleAccelerationControl.{h,cpp}}`
  (tier4, isolated from `93d920f57` per §6.0.1);
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h`
  (`apply_ackermann_control`, `CarlaRos2AckermannPod`),
  `extension/src/subscribers/ControlSubscribers.cpp` (extension). Same argument
  as §5.17: the extension's only actuation primitive routes into CARLA's
  existing Ackermann controller, and a `.so` cannot install a UE tick behaviour
  or an RPC. **Sensor-side** under §5.0.3, decided by a grep that found nothing:
  `git grep -i 'jerk_limit\|first_order_lag\|steer_rate_limit'` at the pinned
  baseline SHA returns **no** hit anywhere, and the nearest existing client API,
  `apply_ackermann_controller_settings()` /
  `carla.AckermannControllerSettings` (`PythonAPI/carla/src/Actor.cpp:200-201`,
  `Control.cpp:325+`), carries PID gains only — no jerk bound, no lag constant,
  no steer-rate limit. The physical response is produced inside the vehicle
  component, so every approach needs the same core change. One honest partial
  overlap: `extension/src/subscribers/ControlSubscribers.cpp:48` already
  forwards Autoware's `longitudinal.jerk` into `CarlaRos2AckermannPod`, and
  CARLA's stock Ackermann controller applies its own accel/jerk limits — but
  that is a **target-tracking** limit inside a controller, not the actuator
  model this entry describes, and the source comment already flags the
  difference as "a tuning watch-point".

### 6.21 Vehicle-model characterization and plotting scripts

- What it does: `PythonAPI/examples/vehicle_simulation.py` (1 178 lines) drives
  scripted longitudinal and lateral manoeuvres against the §6.20 knobs and
  records the response; `PythonAPI/examples/vehicle_acceleration_control_plot.py`
  (657 lines, on `tier4/feature/vehicle-plot`) renders acceleration-control
  step responses so a tuning change can be read off a chart rather than a log.
  Together they are the calibration loop for §6.20 and for §5.17's acceleration
  actuation.
- Maturity evidence: branches `tier4/feature/vehicle-simulation` @
  `98d821be867409bf7825ae73b344bd7da37cb9d7` and `tier4/feature/vehicle-plot` @
  `61883b59eca4fc3db63d72d66f7e2e0f1ae5381d` — **both merged into `tier4/main`**
  (0 ahead). Neither is spec-named.
- Reproduction path: extension-side work
- Effort class: M
- Verified by: `PythonAPI/examples/vehicle_simulation.py`,
  `PythonAPI/examples/vehicle_acceleration_control_plot.py` (tier4, isolated
  from `93d920f57` and `893a8e22f` respectively per §6.0.1);
  `benchmarks/`, `runner/loop.py`, `runner/__main__.py`,
  `docs/e2e-report.md` (extension). Both scripts are ordinary CARLA Python
  clients — no core change, no ABI involvement — so they sit exactly where the
  runner does. This repository has a substantial measurement harness already
  (`benchmarks/`, the committed G1–G3 evidence in `docs/e2e-report.md`), but it
  measures **stack-level** outcomes (localization error, closed-loop deviation,
  topic cadence), not **vehicle-model step response**; a repository-wide grep
  finds no acceleration or steer step-response instrument. M rather than S for
  the volume (1 835 lines across the two) and because the useful half of what
  they measure is the §6.20 parameters, which do not exist here — against
  `apply_ackermann_control` alone the scripts would characterize CARLA's stock
  controller instead, which is a different (still useful) experiment.

### 6.22 Containerized CARLA/UE5 build environment

- What it does: a `docker/` directory holding a GPU-enabled development
  container for **building** CARLA — `nvidia/cuda:12.8.0-devel-ubuntu22.04` with
  the UE5 build dependencies (cmake/ninja/clang/lld, SDL2, Vulkan, OpenMP,
  `xdg-user-dirs`), ROS 2 Humble base, a UID/GID-matched non-root user for bind
  mounts, and a `docker-compose.yml` that reserves all NVIDIA GPUs, mounts a
  single `WORK_PATH` **at the same absolute path inside the container** so
  symlinks created by the host setup scripts still resolve, exposes CARLA's
  2000–2002 and 1985 in bridge mode, and switches to `network_mode: host` for
  ROS 2 multicast discovery via one `.env` variable. A 134-line `README.md`
  documents the first-time setup and the in-container configure/build/package
  commands.
- Maturity evidence: branch `tier4/feature/docker-dev-env` @
  `89c44284c0e07ed9cf7cde110572a0b0b31a7183` — †-marked in §1.1: ancestry
  unverifiable and the tip's own parent is absent from the clone, so only the
  tree could be read (§6.0.1). It sits on upstream `ue5-dev`, not on
  `autoware-support`. A second copy of the same idea rides on the RGL lineage
  (`785594562 feat(Util/Docker): add Ubuntu 22.04 Docker dev environment for
UE5`). Two things temper the maturity claim, both from the files themselves:
  the Dockerfile's header says "Private use only — do not publish (UE5 EULA
  restriction on redistribution)", and it installs
  `@anthropic-ai/claude-code` and mounts `~/.claude` + `ANTHROPIC_API_KEY`,
  i.e. it is one engineer's agent workstation as much as a shared dev container.
- Reproduction path: extension-side work
- Effort class: S
- Verified by: `docker/{Dockerfile,docker-compose.yml,.env.example,README.md}`
  read in full at the pinned tip (tier4); `docker/compose.yaml`,
  `docker/env.sh`, `docker/cyclonedds.xml`, `docs/prerequisites.md`,
  `docs/running-e2e.md`, and `find . -name 'Dockerfile*'` returning **no hit**
  (extension). **A partial divergence from the spec's pre-classification**,
  which lists "docker bring-up" among its already-exists examples. The two
  `docker/` directories solve opposite ends of the stack: this repository's runs
  the **Autoware consumer** (`ghcr.io/autowarefoundation/autoware:universe-devel`,
  host networking, the shared CycloneDDS profile, the map bundles) and is
  mature; tier4's builds **CARLA itself**, which this repository does on the
  host per `docs/prerequisites.md` and has no container for. So the
  already-exists half is real but is not this capability. It is nonetheless
  extension-side, not seam work: a Dockerfile plus a compose file is repository
  tooling with no CARLA source change, and S is honest — the hard part (the
  same-absolute-path mount rule for symlink compatibility, the bridge/host
  network switch) is already written down above and is a day's work to adapt.

### 6.23 Shared build-dependency staging and parallel package compression

- What it does: two build-tooling capabilities that ride the RGL lineage.
  `Util/BuildDependencyShare` (originally `Util/BuildShare`) lets several
  developers or several checkouts share one built dependency tree — a
  `build-share.conf`, a `check-update` mode that works without the config, and
  update checks for RGL and its extensions — and `CARLA_PACKAGE_COMPRESSION`
  makes the package target's compressor selectable (`pigz` parallel gzip as the
  new default, `zstd` via `pzstd`, `gzip` for compatibility), both auto-detecting
  CPU count, with `InstallPrerequisites.sh` and `Unreal/Package/Compress.cmake`
  updated to match.
- Maturity evidence: branches `tier4/feature/build-dependency-share-tool` @
  `fdbf018d29329b26977bd5530ad8c72b9b495bab` and
  `tier4/feature/pigz-zstd-compression` @
  `b16cc5dbab516cfe6cc9fc69d9d4344d093b16ab` — both †-marked in §1.1 (ancestry
  unverifiable, and their two-dot diffs are dominated by lineage difference, so
  neither was separable; §6.0.1). Both were read instead on
  `tier4/feature/rgl-on-ue5-dev-autoware-integration` @ `93d920f57`, where the
  same work appears as `995ab1eae` / `3a6e68ad7` / `8713d80eb` / `52906f293` /
  `9743a1e68` and `5e06661ea` / `bc2ce9afa`, and where `README_RGL.md`
  documents the compression matrix — that branch is **merged into `tier4/main`**,
  so the capability is shipped even though these two branches' own status is
  unverifiable.
- Reproduction path: extension-side work
- Effort class: S
- Verified by: `README_RGL.md` ("Package compression" section, read in full),
  `RglSetup.sh`, and the branch log of
  `tier4/feature/rgl-on-ue5-dev-autoware-integration` (tier4);
  `docs/prerequisites.md`, `docs/running-e2e.md`, `scripts/e2e/run_e2e.sh`
  (extension). No CARLA source is involved — these are shell/CMake build
  utilities — so the verdict is extension-side by the §5.0.2 rule even though
  the files would live in the CARLA fork rather than in this repository.
  Recorded because build-time cost is a real adoption factor for a
  two-repository build path (§5.28), not because the extension architecture
  interacts with it.

### 6.24 Large-map origin rebase in the editor viewport

- What it does: 27 lines in `ALargeMapManager` that rebase the streaming world
  origin to the **editor viewport camera** when not in PIE, so a large map's
  tiles load around whatever the author is looking at instead of only around a
  running ego. Without it, inspecting a distant part of a large map in the editor
  shows unloaded tiles.
- Maturity evidence: branch `tier4/fix/largemap-editor-rebase` @
  `32a3b2edcce27fb31b9e6a55afa7a3293c95235c` — 1 commit ahead of `tier4/main`,
  i.e. genuinely unmerged. Not spec-named. A rebased copy (`d22c37295`) rides on
  `tier4/feature/lidar-udp-raw-packet`, which **is** merged.
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/MapGen/LargeMapManager.{h,cpp}`
  (tier4, `git show` per §6.0.1); `docs/nishishinjuku-map.md`,
  `runner/__main__.py` (extension). **Sensor-side** under §5.0.3, decided by a grep
  that found nothing: a search of `PythonAPI/carla/src/` and
  `LibCarla/source/carla/client/World.h` at the pinned baseline SHA for
  `map_origin` / `large_map` returns **no** client-facing accessor — the only
  hit anywhere is the internal `detail::EpisodeState::_map_origin`
  (`LibCarla/source/carla/client/detail/EpisodeState.h:111`), a read-only
  observation inside LibCarla that is not exported to Python. In any case the
  behaviour is editor-only, i.e. outside every client's reach by construction. Its relevance
  to this comparison is limited and is stated as such: this repository's live
  gates run against packaged/editor builds of a single Nishi-Shinjuku level and
  never author a large map, so the practical reproduction demand is currently
  zero — it is catalogued because it is an inventoried unmerged branch, not
  because it blocks anything here.

### 6.25 NavMesh map scanner game mode

- What it does: a standalone `ANavMeshScannerGameMode` plus `UNavMeshMapScanner`
  that walk a level's navigation mesh — the tooling side of validating that a
  map's walkable surface is complete before pedestrians are spawned on it.
- Maturity evidence: branch `tier4/test/navmesh-scanner` @
  `590ce22deb3a8a5fb01327273351f05bf667e8dd` — †-marked in §1.1, ancestry
  unverifiable and no diff obtainable (§6.0.1); the tip subject is
  `Add scanner to root` and the branch is under `test/`, so treat it as a
  scratch investigation rather than a delivered capability. Not spec-named.
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Source/CarlaUnreal/{Public,Private}/{NavMeshMapScanner.{h,cpp},NavMeshScannerGameMode.{h,cpp}}`
  (tier4 — **file inventory only**, via `git ls-tree`; no diff was obtainable
  and the sources were not read line by line, which is recorded here rather than
  papered over); `runner/spawn.py`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension).
  **Sensor-side** under §5.0.3: a `AGameModeBase` subclass is installed by the
  UE project, not by any client, and a grep of `LibCarla/source/carla/client/`
  and `PythonAPI/carla/src/` at the pinned baseline SHA finds **no** navmesh
  accessor of any kind — the nearest client surface,
  `world.get_random_location_from_navigation()`
  (`PythonAPI/carla/src/World.cpp:310`), samples the mesh but does not expose
  it. Like §6.24, its bearing on this comparison is small and is stated
  as such: no gate in this repository spawns pedestrians.

### 6.26 Coverage map

Every inventoried side branch, and the entry (or non-entry) that accounts for
it. Branches marked _not a capability_ are listed in the same table so nothing
in §1.1's candidate pool is silently unaccounted for.

| Branch (from §1.1)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Entry                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tier4/experiment/cyclonedds-support`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | §6.1, §6.2                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `tier4/feature/ue5-dev-cyclonedds-support`, `tier4/feature/ue5-dev-autoware-integration`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | §6.1 (evidence), §6.17                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `tier4/feature/agnocast-integration`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | §6.3                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `tier4/feature/rgl-on-ue5-dev-autoware-integration`, `tier4/feature/rgl-support`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | §6.4 (the latter as the superseded lineage), §6.23                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `tier4/feature/rgl-distance-culling-multisensor`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | §6.6                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `tier4/fix/rgl-ring-id-0based`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | §6.5                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `tier4/feature/lidar-udp-raw-packet`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | §6.5, §6.7, §6.9, §6.10, §6.11 (this branch carries five distinct capabilities, only one named by the spec)                                                                                                                                                                                                                                                                                                                                                               |
| `tier4/feature/pandar128e4x-highres-udp`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | §6.8                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `tier4/feature/lanelet2-traffic-light`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | §6.12, §6.13, §6.14                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `tier4/feature/autoware-v2i-publisher`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | §6.15                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tier4/fix/traffic-light-controller-null-check`, `tier4/fix/traffic-light-freeze`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | §6.16                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tier4/feature/ros2-async-publish-queue`, `tier4/feature/ros2-async-camera-publish`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | §6.18                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tier4/feature/sensor-timing-instrumentation`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | §6.19                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tier4/feature/vehicle-simulation`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | §6.20, §6.21                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `tier4/feature/vehicle-plot`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | §6.21                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tier4/feature/vehicle-sim-package`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | §6.5 (its own delta above `pandar128e4x-highres-udp` is the azimuth-major ray-order fix and the Hesai preset re-sync); otherwise identical to `tier4/main` (§1.3)                                                                                                                                                                                                                                                                                                         |
| `tier4/feature/docker-dev-env`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | §6.22                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tier4/feature/build-dependency-share-tool`, `tier4/feature/pigz-zstd-compression`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | §6.23                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tier4/fix/largemap-editor-rebase`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | §6.24                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tier4/test/navmesh-scanner`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | §6.25                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `tier4/feature/override-steering-curve` (spec: steering-lut)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | _no §6 entry_ — already merged into `tier4/autoware-support` (0 ahead, ancestry verified in §2) and cataloged as §5.7, where a `diff -u` shows the extension's vendored copy is **identical** to tier4's apart from the namespace, an added `<tuple>` include and a provenance comment. Verified again here by file presence: `extension/include/carla/autoware/control/AutowareSteeringCompensation.h` exists on this branch. The spec's "already vendored" is confirmed |
| `tier4/feature/gnss-pose-publish`, `tier4/feature/pose-publisher`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | _no §6 entry_ — both already merged into the baseline (0 ahead) and cataloged as §5.6                                                                                                                                                                                                                                                                                                                                                                                     |
| `tier4/reference/pose-publisher`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | _not a capability_ — earlier unmerged draft superseded by `feature/pose-publisher` (§2)                                                                                                                                                                                                                                                                                                                                                                                   |
| `tier4/fix/carlaserver-enum-typo`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | _not a capability_ — a 4-line `ECarlaServerResponse` spelling fix that unbreaks the build on its lineage                                                                                                                                                                                                                                                                                                                                                                  |
| `tier4/shinjuku-test-map`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | _not a capability_ — tip subject is `Remove Autoware Game Mode debug cast`; a `git ls-tree` of the tip filtered for `shinjuku` returns 0 paths, so nothing map-specific is on it                                                                                                                                                                                                                                                                                          |
| `tier4/main`, `tier4/ue5-dev`, `tier4/sync/upstream-ue5-dev-2026042*`, `tier4/patch/*`, `tier4/wc/add-cmake-preset`, `tier4/refactor/qos-settings`, `tier4/feature/{autoware-demo-ros-configuration,autoware-plugin,autoware-publishers,autoware-subscriber,autoware-subscribers,publish-report-data,ros-domain-id,time-scale,topic-name,vehicle-topic-support}`, `tier4/fix/{autoware-publishers-frame-id,dark-camera-sensor,gnss-null-check,imu-delta-time,incorrect-steering-angle-normalization,nishishinjuku-map-cook-path,ros-types,status-publish-stamp,steering,transform-names}` | _not side-branch capabilities_ — every one is either 0 commits ahead of `tier4/autoware-support` (i.e. already merged and therefore covered by §5), a lineage/sync/baseline pointer, or a superseded precursor of a merged capability. §5.15 (`ros_topic_name`), §5.16 (QoS), §5.21 (`ROS_DOMAIN_ID`), §5.19/§5.20 (IMU) and §5.8 (steering) are the merged forms of the like-named branches                                                                              |
