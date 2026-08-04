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
180). §5.28 tabulates which entry covers each of those areas, so the "100 %
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
  one-stamp-for-all-six discipline. Per-field value provenance differs on three
  of the six and is cataloged separately in §5.8, §5.9 and §5.10 rather than
  folded into this verdict.

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
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Sensors/VehicleStatusSensor.cpp`
  (`CollectAndStream`), `LibCarla/source/carla/ros2/ROS2.cpp`
  (`ProcessDataFromStatusSensor`) (tier4);
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
  by using the commanded-steer proxy above; adopting that proxy is a small
  change **inside the host**, not in the `.so`, which is why this is classed as
  seam work rather than extension-side.

### 5.9 Gear-status value source

- What it does: `ProcessDataFromStatusSensor` maps the vehicle's **actual**
  current gear (`Vehicle->GetVehicleCurrentGear()`, serialized as
  `VehicleStatusData::gear`) onto the 25 `GearReport` constants, defaulting to
  `Gear::NONE` for out-of-range values.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: already-exists
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/ROS2.cpp`
  (`ProcessDataFromStatusSensor` gear switch),
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Sensors/VehicleStatusSensor.cpp`
  (tier4); `extension/src/publishers/StatusPublishers.cpp`,
  `extension/src/ExtensionInit.cpp`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension). The
  actual-gear value already crosses the ABI as
  `CarlaRos2VehicleStatusView::gear`; the extension currently ignores that field
  and echoes the **commanded** gear from `/control/command/gear_cmd` instead
  (`in.gear = st->control.CachedGear()`). Switching to the tier4 semantics is a
  one-line change in `StatusPublishers::OnVehicleStatus` with no ABI or core
  change — hence already-exists, S, not seam work.

### 5.10 Turn-indicator and hazard-light status value sources

- What it does: `VehicleStatusSensor` packs the vehicle's **actual**
  `FVehicleLightState` blinker bits into a 3-bit `turn_mask`
  (left / right / hazard), and `ProcessDataFromStatusSensor` decodes it into
  `TurnIndicatorsReport` / `HazardLightsReport`, logging an error if both
  blinkers are simultaneously set.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Autoware/Sensors/VehicleStatusSensor.cpp`,
  `LibCarla/source/carla/ros2/ROS2.cpp` (`ProcessDataFromStatusSensor` turn-mask
  decode) (tier4); `extension/src/publishers/StatusPublishers.cpp`,
  `extension/include/carla/ros2/extension/CarlaRos2Extension.h` (extension).
  Unlike gear (§5.9), the ego light state does **not** cross the C ABI — the
  status view has no light-state field — so reproducing tier4's actual-state
  semantics needs a new field in `CarlaRos2VehicleStatusView` plus a host-side
  fill, i.e. an ABI version bump. The extension's present behaviour (echo the
  commanded `turn_indicators_cmd` / `hazard_lights_cmd` bytes) is arguably the
  more useful signal for a closed loop, since neither implementation actuates
  the lights (§5.3), but it is a different quantity and is recorded as such.

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
- Reproduction path: CARLA-core seam work (sensor-side (approach-agnostic))
- Effort class: S
- Verified by: `LibCarla/source/carla/ros2/publishers/CarlaLidarPublisher.{h,cpp}`,
  `LibCarla/source/carla/ros2/ROS2.cpp`,
  `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Sensor/RayCastLidar.cpp`
  (tier4); `extension/include/carla/ros2/extension/CarlaRos2Extension.h`
  (`CARLA_ROS2_SENSOR_LIDAR_EXT`), `runner/spawn.py`
  (`ros2_extended_lidar` in `_REQUIRED_NATIVE_ATTRS`), and the sibling fork
  commit `0bd4d84c3` (`min/5-extended-lidar`,
  "feat(ros2): opt-in 10-float PointXYZIRCAEDT LiDAR layout") read via
  `git show --stat`. The point cloud is published by CARLA core, never by the
  `.so`, so no extension-side path exists — the ABI reserves a `LIDAR_EXT`
  observer kind but the extension registers only `VEHICLE_STATUS`. The effort is
  S rather than M only because the fork already carries an equivalent core
  change, gated behind a per-actor `ros2_extended_lidar` blueprint attribute
  (tier4's is unconditional for every ray-cast LiDAR) and with the derived
  fields in a dedicated `ExtendedLidarPoint.h` plus a `test_ros2_extended_lidar`
  unit test. The two implementations were compared by file inventory and commit
  subject, not field-by-field for numerical agreement.

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
  `ae166d80d` (`autoware/11-imu-sensor-frame`) via `git show --stat`. IMU data
  never crosses the C ABI in either stack — the sensor publishes natively — so
  any correction is core work by construction. The fork carries a **different**
  IMU correction (sensor-frame emission with REP-103 handedness, plus
  `test_imu_axes`), which the extension repository's own operational notes
  identify as load-bearing for the live gates. tier4's accelerometer bootstrap
  and gravity sign were not found in the fork's IMU commit; the two fixes are
  complementary, not duplicates, and merging them was not attempted here.

### 5.20 `ROS_DOMAIN_ID` support

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

### 5.21 TF-publishing suppression

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

### 5.22 `get_ego_spawn_points` RPC

- What it does: a `get_ego_spawn_points` RPC returning
  `UCarlaEpisode::GetRecommendedSpawnPoints()` — the _game mode's_ stored spawn
  points, which for `AAutowareGameModeBase` are the ones `StoreSpawnPoints()`
  populated after loading the level's MGRS geo-reference (§5.12) — exposed as
  `World::GetEgoSpawnPoints` and `world.get_ego_spawn_points()`.
  `autoware_demo.py` calls it with an `AttributeError` fallback to
  `world.get_map().get_spawn_points()` for stock CARLA packages.
- Maturity evidence: merged (main @ `6315b856f8faf2118578322eb20a2b902a45a384`)
- Reproduction path: CARLA-core seam work (ROS-side)
- Effort class: S
- Verified by: `Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Server/CarlaServer.cpp`,
  `LibCarla/source/carla/client/{World.h,World.cpp,detail/Client.h,detail/Client.cpp}`,
  `PythonAPI/carla/src/World.cpp`, `PythonAPI/examples/autoware_demo.py` (tier4);
  `runner/__main__.py` (`--initial-pose` and `--spawn-index` arguments) and
  `runner/spawn.py` (extension). The extension's runner sidesteps the RPC by
  taking an explicit initial pose or an index into the map's own spawn points —
  which is why all live gates in this repository pass an explicit
  `--initial-pose`. That is a workaround, not a reproduction: the level-authored
  spawn points tier4 exposes are not reachable from the client without this RPC.
  It is a `CarlaServer` binding, so no `.so`-side path exists. Labelled ROS-side
  in the §3 taxonomy's binary sense (a core API-surface change, not a
  sensor-rendering one).

### 5.23 Nishi-Shinjuku map packaging entry

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

### 5.24 Declarative Autoware sensor-kit spawn

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

### 5.25 Client-side simulation pacing and world controls

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

### 5.26 Traffic-light camera post-process profile

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

### 5.27 Build and documentation surface

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

### 5.28 Coverage map

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
| `ros2/publishers/CarlaPublisher.h`, `subscribers/CarlaSubscriber.h`, `ROS2.{h,cpp}` topic-name maps                                                                                      | §5.15                                                                                                                                                                                                                                                                                                                                                                 |
| `ros2/data_types.h`, per-publisher `Init(TopicConfig)` churn                                                                                                                             | §5.16                                                                                                                                                                                                                                                                                                                                                                 |
| `ros2/ROS2.cpp` `ObtainDomainId`                                                                                                                                                         | §5.20                                                                                                                                                                                                                                                                                                                                                                 |
| `ros2/ROS2.cpp` `_publish_tf` gates, `client/World.*`, `CarlaServer.cpp` TF RPCs                                                                                                         | §5.21                                                                                                                                                                                                                                                                                                                                                                 |
| `CarlaServer.cpp` `get_ego_spawn_points`, `client/World::GetEgoSpawnPoints`                                                                                                              | §5.22                                                                                                                                                                                                                                                                                                                                                                 |
| `Autoware/Data/*`, `Autoware/Game/*`, `Game/CarlaGameModeBase.*`, `Game/CarlaEpisode.*`, `DefaultEngine.ini`                                                                             | §5.12                                                                                                                                                                                                                                                                                                                                                                 |
| `Autoware/Sensors/AutowareGnssSensor.*`, `Actor/ActorBlueprintFunctionLibrary.*` GNSS defs                                                                                               | §5.13                                                                                                                                                                                                                                                                                                                                                                 |
| `Autoware/Sensors/VehicleStatusSensor.*`, `sensor/s11n/VehicleStatusSerializer.*`, `sensor/SensorRegistry.h`, `sensor/data/VehicleStatusEvent.h`                                         | §5.11                                                                                                                                                                                                                                                                                                                                                                 |
| `Vehicle/VehicleAccelerationControl.*`, `Vehicle/CarlaWheeledVehicle.*`, `Vehicle/VehicleVelocityControl.cpp`, `Actor/CarlaActor.cpp`, `client/Actor.*`, `PythonAPI/carla/src/Actor.cpp` | §5.17                                                                                                                                                                                                                                                                                                                                                                 |
| `Actor/ActorROS2Handler.*` `FlattenSteeringCurve`, `Actor/ActorDispatcher.cpp` ego hook                                                                                                  | §5.18                                                                                                                                                                                                                                                                                                                                                                 |
| `Sensor/InertialMeasurementUnit.*`                                                                                                                                                       | §5.19                                                                                                                                                                                                                                                                                                                                                                 |
| `Sensor/GnssSensor.cpp` (world-transform argument)                                                                                                                                       | §5.6, §5.13                                                                                                                                                                                                                                                                                                                                                           |
| `DefaultGame.ini` `+MapsToCook`                                                                                                                                                          | §5.23                                                                                                                                                                                                                                                                                                                                                                 |
| `PythonAPI/examples/autoware_demo.py` sensor kit                                                                                                                                         | §5.24                                                                                                                                                                                                                                                                                                                                                                 |
| `PythonAPI/examples/autoware_demo.py` pacing/world controls, `PythonAPI/carla/src/World.cpp`                                                                                             | §5.25, §5.21                                                                                                                                                                                                                                                                                                                                                          |
| `PythonAPI/examples/autoware_demo.py` post-process profile                                                                                                                               | §5.26                                                                                                                                                                                                                                                                                                                                                                 |
| `CMakePresets.json`, `README.md`                                                                                                                                                         | §5.27                                                                                                                                                                                                                                                                                                                                                                 |
| `PythonAPI/examples/ros2/ros2_native.py` `--disable-tf`                                                                                                                                  | §5.21 (evidence)                                                                                                                                                                                                                                                                                                                                                      |
| `Sensor/SceneCaptureSensor.{h,cpp}` (header +60/−136 with 28 `UFUNCTION` declarations removed and 0 added; `.cpp` +74/−288)                                                              | _not a capability_ — measured as a net **removal** of Blueprint-callable post-process accessors relative to the branch point, with no replacement added on this branch. Whether that is deliberate scoping or a lost hunk from one of the `patch/autoware-support-sync-upstream-*` merges was not determined; recorded as an unexplained delta rather than guessed at |
| `.gitignore` (Rider/Perforce entries)                                                                                                                                                    | _not a capability_                                                                                                                                                                                                                                                                                                                                                    |
| `ros2/listeners/SubscriberListenerBase.*`, `ROS2CallbackData.h` variant widening                                                                                                         | _internal plumbing for_ §5.2–§5.5, §5.17                                                                                                                                                                                                                                                                                                                              |
