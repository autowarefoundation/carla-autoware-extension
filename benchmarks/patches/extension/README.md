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

- **No data-path, conversion, or transport code was changed** for the benchmark. The GNSS/status
  synthesis, the CDR serialisation, the DDS publish/subscribe seam and the control conversion are
  byte-for-byte the code the Nishi-Shinjuku gates ran against.
- **The Nishi-Shinjuku configuration is unchanged.** Every knob added below defaults to exactly the
  behaviour that was already there, so the existing gate results stay comparable rather than needing
  a re-run.

## Changes made for the Town10HD_Opt bring-up (bench P1)

Branch `bench/p1-town10-bringup`. All of these are map _selection_, not map-specific behaviour.

| Change                                                               | Where                                                                                                                                        | Default                                                          |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Per-map GNSS converter offset table + `$CARLA_AUTOWARE_MAP` selector | `extension/include/carla/autoware/geo/MgrsOffset.h`, `extension/src/ExtensionInit.cpp`, `extension/src/publishers/GnssPosePublisher.{h,cpp}` | unset ⇒ Nishi-Shinjuku, i.e. the previous constant               |
| Same table, Python mirror, for the host-side gate ground truth       | `scripts/e2e/verify_mgrs_handedness.py`, `scripts/e2e/collect_gt.py`                                                                         | `CONVERTER_OFFSET` still the Nishi-Shinjuku triple               |
| Offline derivation of a map's offset from its `.xodr` + lanelet2     | `scripts/e2e/fit_map_offset.py` (new)                                                                                                        | n/a — a measurement tool, not in any run path                    |
| `MAP` / `MAP_DIR` / `SPAWN_INDEX` threading                          | `scripts/e2e/run_e2e.sh`, `scripts/e2e/launch_autoware.sh`, `runner/__main__.py`                                                             | `NishishinjukuMap`, `/autoware_map/nishishinjuku`, spawn point 0 |
| Second Autoware map bundle mounted                                   | `docker/compose.yaml`                                                                                                                        | additive; the nishishinjuku mount is untouched                   |

The one behaviour change that is _not_ a pure default-preserving addition: an unknown
`$CARLA_AUTOWARE_MAP` now aborts the extension load (`kUnknownMap`) instead of loading. That is
deliberate and is argued in `MgrsOffset.h` — a silently wrong converter offset does not announce
itself, it surfaces hours later as NDT failing to converge.

Full diffs are reproduced in the report appendix; the authoritative source is the branch.
