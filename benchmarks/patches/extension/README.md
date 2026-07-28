# extension (approach A) — no patches, by construction

The benchmark's patch policy requires every approach's sensor-parameter, launch-parameter and
scenario-script edit to be committed here as a reviewable diff. **This directory holds no patches,
and is expected to stay empty of them.** The reason is structural rather than an omission: the
extension approach is _this repository_, so a change it needs is a first-party commit on a branch,
reviewed as an ordinary PR, and not a patch applied on top of somebody else's source tree.

This file exists so the report's per-approach patch appendix has an entry for approach A, and so a
reader who finds `benchmarks/patches/python-bridge/` populated and this one empty knows that is
deliberate.

## What "no patches" does and does not mean

It does **not** mean the extension was unmodified for the benchmark. It means the modifications are
in the repository's own history where they can be diffed, tested and reverted, instead of in a patch
file. Two things stay true either way, and both are what the policy is actually protecting:

- **The GNSS conversion code WAS edited, and is semantically unchanged for Nishi-Shinjuku.** Be
  precise about this, because the table below contradicts any claim that nothing was touched:
  `world_to_mgrs_local` gained a defaulted `offset` parameter and `GnssPosePublisher::Init` gained a
  defaulted argument, so those files are **not** byte-for-byte what the Nishi gates ran against. What
  is unchanged is the behaviour on the default path — same offset literals, same single Y negation,
  same quaternion rule — verified at the published-wire-bytes level by
  `GnssPoseTest.init_without_a_map_offset_still_publishes_nishishinjuku` and end to end through the
  real entrypoint by `InitTest.unset_map_env_keeps_the_nishishinjuku_offset`. The CDR serialisation,
  the DDS publish/subscribe seam and the control conversion are genuinely untouched.
- **The Nishi-Shinjuku configuration is unchanged, with one edit made specifically to keep it that
  way.** `arm_closed_loop.sh` briefly passed `--ego-xy` unconditionally, which would have moved
  Nishi's all-free occupancy-grid origin ~7.5 m from its baked constant to the live ego pose. Since
  the Nishi live gate could not be re-run in this session, that invariant is protected by not
  changing it: the grid centre is now map-conditional (`scripts/e2e/map_defaults.sh`), Nishi keeps
  the exact constant `81377.34 49916.93`, and only maps without one centre on the ego.

## Changes made for the Town10HD_Opt bring-up (bench P1)

Branch `bench/p1-town10-bringup`. All of these are map _selection_, not map-specific behaviour.

| Change                                                                  | Where                                                                                                                                        | Default                                                                   |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Per-map GNSS converter offset table + `$CARLA_AUTOWARE_MAP` selector    | `extension/include/carla/autoware/geo/MgrsOffset.h`, `extension/src/ExtensionInit.cpp`, `extension/src/publishers/GnssPosePublisher.{h,cpp}` | unset ⇒ Nishi-Shinjuku, i.e. the previous constant                        |
| Same table, Python mirror, for the host-side gate ground truth          | `scripts/e2e/verify_mgrs_handedness.py`, `scripts/e2e/collect_gt.py`                                                                         | `CONVERTER_OFFSET` still the Nishi-Shinjuku triple                        |
| Offline derivation of a map's offset from its `.xodr` + lanelet2        | `scripts/e2e/fit_map_offset.py` (new)                                                                                                        | n/a — a measurement tool, not in any run path                             |
| `MAP` / `MAP_DIR` / `SPAWN_INDEX` threading                             | `scripts/e2e/run_e2e.sh`, `scripts/e2e/launch_autoware.sh`, `runner/__main__.py`                                                             | `NishishinjukuMap`, `/autoware_map/nishishinjuku`, spawn point 0          |
| Second Autoware map bundle mounted                                      | `docker/compose.yaml`                                                                                                                        | additive; the nishishinjuku mount is untouched                            |
| Traffic-light feed tolerates a map with no signals; map from `$MAP_DIR` | `scripts/e2e/dummy_perception.py`[^moved]                                                                                                    | Nishi still finds its groups and forces them green                        |
| All-free occupancy-grid origin, now map-conditional                     | `scripts/e2e/dummy_perception.py`[^moved], `scripts/e2e/arm_closed_loop.sh`, `scripts/e2e/map_defaults.sh`                                   | Nishi keeps the constant `81377.34 49916.93`; other maps use the ego pose |
| `MAP_DIR` derived from `$CARLA_AUTOWARE_MAP` via one shared table       | `scripts/e2e/map_defaults.sh` (new), sourced by `run_e2e.sh` + `arm_closed_loop.sh`                                                          | `NishishinjukuMap` ⇒ `/autoware_map/nishishinjuku`                        |

[^moved]: Path as of this P1 bring-up. Task 7 later moved this file to
    `benchmarks/injector/dummy_perception.py`, promoting it to a first-class
    harness component run identically from every cell; the table above is
    left as the historical record of what changed at P1 time.

The one behaviour change that is _not_ a pure default-preserving addition: an unknown
`$CARLA_AUTOWARE_MAP` now aborts the extension load (`kUnknownMap`) instead of loading. That is
deliberate and is argued in `MgrsOffset.h` — a silently wrong converter offset does not announce
itself, it surfaces hours later as NDT failing to converge.

Full diffs are reproduced in the report appendix; the authoritative source is the branch.
