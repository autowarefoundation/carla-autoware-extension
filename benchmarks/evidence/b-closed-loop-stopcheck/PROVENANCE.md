# Cell B closed-loop gate — why it FAILED (Task 13, 2026-07-30)

Evidence for the localization-initialization block that stops cell B from
closing the loop. Promoted here because it is a **decision-run** result: it is
the cell B gate verdict the A-vs-B duel depends on, and the campaign's evidence
rule requires the numbers behind such a verdict to be recomputable from tracked
files rather than asserted in a report.

## Verdict

**FAIL — cell B cannot arm, because its localization never initializes.** The
failure is upstream of the M5 gate: no `quality.json` exists for any B run, so
there is no NDT rate and no goal closest-approach to report. Four runs are
filed, all excluded `crash:cell-launch` (`benchmarks/results/B/run-001` …
`run-004`); run-001 and run-002/003 are earlier, differently-caused failures of
the same bring-up, kept because they are the ladder that localized this one:

| run | reached                                                    | excluded because                                                                                                                                                                                                                                        |
| --- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 001 | ego spawn                                                  | the launcher's readiness probe grepped the demo's **block-buffered** stdout, so "Ego spawned!" never appeared. A launcher defect, fixed by `PYTHONUNBUFFERED=1` plus a world-side ego probe. `tier4-demo.log` is 0 bytes, which is the direct evidence. |
| 002 | full stack, LiDAR readable in the container, 600 s         | nothing seeded localization; Autoware's own automatic initializer was refused throughout (see below)                                                                                                                                                    |
| 003 | full stack + a `/initialpose` seed, 7 attempts             | `/initialpose` does not reach `pose_initializer` on this image at all                                                                                                                                                                                   |
| 004 | full stack + a `/localization/initialize` seed, 4 attempts | `pose_initializer`'s own service refused every call with the same reason                                                                                                                                                                                |

## Root cause, measured

`autoware_pose_initializer` refuses **every** initialization request —
whichever door it arrives through — with

```text
/api/localization/initialize: status code 1 'The vehicle is not stopped.'
/localization/initialize:     ... 'The vehicle is not stopped.'
```

because its stop check reads
`/sensing/vehicle_velocity_converter/twist_with_covariance`, and on cell B that
twist is **never below the stop threshold**:

```text
n=180
linear (x,y,z) first: (-1.4666111207428667e-12, 0.002172556472942233, 0.0)
|v| min=0.00216644 max=0.00217256  threshold=1e-3
over_threshold=180/180
angular.z first=9.98365e-05
```

(`twist_components.txt`, produced by `probe_twist_components.py` inside the
run-004 container.) The ego is **stationary longitudinally** — `linear.x` is
1.5e-12 m/s — but carries a constant **2.17 mm/s of LATERAL velocity**, which
the checker sees because it compares the squared norm of the whole linear
vector. Every one of 180 samples is over.

The lateral term originates in the fork: `/vehicle/status/velocity_status`
reports `lateral_velocity` ≈ 2.28e-3 m/s (and `heading_rate` ≈ 1.9e-4 rad/s)
for a parked ego — the fork's `ROS2.cpp:1110`
`SetVelocity(data.vel_x_mps, -data.vel_y_mps, -data.angVel_z_mps)` from its
`sensor.other.vehicle_status` — and `autoware_vehicle_velocity_converter`
forwards it into `twist.linear.y`.

`stop_check_duration: 3.0` and `stop_check_enabled` are from the image's own
`autoware_launch/config/localization/pose_initializer.param.yaml`.

### What is measured and what is inferred

- MEASURED: the refusals (40 lines in `refusals.log`, and every
  `seed_localization` retry in `run-004-console.log`); the twist components
  above; that the ego is stationary in x; that the whole sensing → NDT input
  chain is ALIVE while this happens.
- INFERRED, from upstream's `VehicleStopCheckerBase::isVehicleStopped`: that the
  threshold compared against is `1e-3` m/s on the squared linear norm, and that
  this is why 2.17 mm/s of pure lateral velocity reads as "not stopped". The
  threshold value is not read out of the shipped binary here. What the
  measurement establishes without it: the only non-negligible quantity in that
  twist is `linear.y` at 2.17 mm/s, and the service refuses on every attempt.
- OBSERVED LIVE BUT NOT RETAINED: the chain-liveness and velocity-status
  probes' output. `probe_chain_liveness.py` and `probe_velocity_status.py` are
  the exact scripts, kept so the measurement is repeatable, but their console
  output was not captured to a file before the container was removed (the same
  status the campaign's `step-11_6-adapi-engage` row records for its own
  interactive readings). The numbers quoted in the Task 13 report from those two
  probes — cloud counts along the chain, and n=283 velocity samples at
  |longitudinal| ≤ 3.7e-12 m/s — are therefore labelled there as not
  recomputable.

## What this is NOT

- **Not a transport fault.** Task 9's rung-1 configuration held on every run:
  the launcher's own pre-check read a sample of
  `/sensing/lidar/top/pointcloud_raw_ex` inside the Autoware container before
  each localization wait ("OK: the fork's LiDAR is readable inside the stack",
  `run-004-console.log`).
- **Not a dead sensing chain.** With the concat relay running, every stage from
  the as-emitted cloud to NDT's input
  (`/localization/util/downsample/pointcloud`) was publishing, while
  `/localization/pose_estimator/pose` and `/localization/kinematic_state`
  counted zero.
- **Not the map bundle.** `manifest.json` records
  `map_bundle_pin: town10_pcd_regen` for all four runs — the same bundle cell A
  localizes against — and NDT never ran at all, so the bundle was never
  exercised.
- **Not R4's arming path.** `run.sh` never reached step 9 on any run: the cell
  launcher failed first. `arm_and_goal.py` is therefore still unexercised
  against a real stack.

## Files

| file                        | what it is                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `run-004-console.log`       | `bash benchmarks/run.sh B --arm closed-loop` console output, verbatim: bring-up, the seed retries and every refusal |
| `refusals.log`              | the container-side launch log's `not stopped` / `not activated` lines                                               |
| `twist_components.txt`      | the stop-check input measurement quoted above                                                                       |
| `probe_twist_components.py` | the script that produced it (run inside the Autoware container)                                                     |
| `probe_chain_liveness.py`   | per-topic message counts along sensing → NDT (output not retained)                                                  |
| `probe_velocity_status.py`  | `/vehicle/status/velocity_status` + converter twist magnitudes (output not retained)                                |
