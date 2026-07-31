# G1 on the Nishi-Shinjuku bundle — selects cell C's ladder branch

The run that selects `ladder_branch: absolute` + `abs_pose_gate_m: 0.5` for
`benchmarks/config/cells.yaml` cell C. `g1_summary.txt` is the gate's own output
(map, container bundle path, the bundle pcd's sha256, window, verdict); this file
adds the build provenance and the per-axis decomposition the `cells.yaml` comment
quotes, so every number there is recomputable from this directory.

`ladder_branch` is a property of the BUNDLE a cell localizes against
(`cells.yaml` header; `benchmarks/README.md`, "M5 definitions"), and the bundle
here is the one `scripts/e2e/map_defaults.sh` resolves for `NishishinjukuMap`:
container `/autoware_map/nishishinjuku`, `pointcloud_map.pcd` sha256
`78b6cf81047489efb1f008a44238d497241da64bb158c824a3f18f23eb50e9d3`.

## Verdict

`max_err=0.062 m` against the 0.5 m gate over 400 NDT samples in a 19.98 s
static window (399 ground-truth samples) — **PASS**, 438 mm inside the gate.

| Statistic                    | Value                      |
| ---------------------------- | -------------------------- |
| max XY error                 | **0.0616 m**               |
| mean / median / std          | 0.0308 / 0.0300 / 0.0104 m |
| bias (dx, dy)                | (−0.0038, +0.0211) m       |
| per-axis jitter std (dx, dy) | 0.0212 / 0.0121 m          |

The bias is 21 mm, i.e. there is no map-registration offset of the kind Town10
carries (`cells.yaml` cell A: +0.475 m cross-track on the rigid bundles). This
bundle is independently sourced, not rebuilt from this rig's own sweeps, so it
does not carry cell A's rung-2 self-registration confound (README, "Known
confounds"); the two numbers are still cross-map and not a like-for-like
comparison.

Relation to the previously recorded figure: `docs/e2e-report.md`'s post-refactor
re-run recorded 0.078 m on this map, and `cells.yaml` cell A's comment cites that
0.078 m. This run's 0.062 m neither supersedes nor contradicts it — both are
static windows on the same bundle, 16 mm apart on a max statistic — but 0.062 m
is the one the branch selection rests on, because it is measured on the current
engine state and its raw series are tracked here.

## Run provenance

One boot, `MAP=NishishinjukuMap WITH_AUTOWARE=1`,
`RUNNER_EXTRA_ARGS="--initial-pose -284.597 224.709 0.0 0 0 -34.187"`,
2026-07-30 UTC (`g1_run: 20260730T235427Z`), preceded by a discarded warm-up boot
(`config/exclusions.md` criterion 5, the exact sensor suite). Static ego,
GNSS-initialised lock, **no reseed** before the window. Host 1-min loadavg 1.35 at
preflight (criterion 6 aborts at ≥ 8).

- engine BuildId `4210e602-78ec-46e1-8f2f-03fadbe036a3` — matches `pins.yaml`
  `engine.build_id`, so `config/exclusions.md` criterion 8 does not apply
- extension fork `ae166d80d022f838b78f4a2daab1ca2880a7c8aa` — matches `pins.yaml`
  `extension_carla_fork.sha`
- extension `.so` sha256
  `e8b024cf1509c80a2e7927c91b476edf38a86f800c6fd05f247db149a194204a`
- Autoware image
  `ghcr.io/autowarefoundation/autoware@sha256:405225eda6c05161bfde39cc7885511f3f4d9699d126891891420dd80c2e024a`
- cadence observed on the same stack: LiDAR 19.94–19.95 Hz, `/clock` 19.95 Hz,
  `/localization/pose_estimator/pose` 19.97 Hz,
  `/localization/kinematic_state` 19.96 Hz

The same boot produced `g2-nishi-cellc/` (G2 PASS) and
`task-15-adapi-engage-cellc/` (the arming-path discriminator).

## Recomputing

```bash
python3 scripts/e2e/measure_ndt.py \
  --ndt benchmarks/evidence/g1-nishi-bundle/g1_ndt.txt \
  --gt  benchmarks/evidence/g1-nishi-bundle/g1_gt.txt --max-err-m 0.5
```

Reproduces `max_err=0.062 m ... PASS` (verified, exit 0, before promotion). The
bias / jitter table above comes from the same two `<t> <x> <y>` series, pairing
each NDT sample with its nearest-in-time ground-truth sample exactly as
`measure_ndt.errors_from_series` does and taking the mean and population standard
deviation of the signed per-axis residuals.
