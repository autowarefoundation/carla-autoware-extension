# carla-autoware-extension

> **Status: Proposal** — This repository accompanies a proposal for semi-native Autoware support in CARLA (`ue5-dev`). It depends on CARLA changes that are **not yet merged upstream** (native ROS 2 series #9743–#9758, DDS middleware abstraction #9807–#9816, and the `ue5-dev` port + extension-API series staged as draft PRs on the `youtalk/carla` fork). Nothing here is usable against a stock CARLA release yet. See [docs/prerequisites.md](docs/prerequisites.md) for the exact CARLA build this content is verified against.

## Purpose

CARLA `ue5-dev` can publish sensor and vehicle data as native ROS 2 (DDS) topics — no bridge process, no republishing. This repository holds the Autoware-side companion assets for driving Autoware against that native path:

- a Docker Compose setup that brings up the official Autoware container sharing the host's DDS domain with CARLA over CycloneDDS, and
- an interoperability gate (`scripts/interop_check.py`) that proves, from inside the Autoware container, that every expected CARLA topic is present, correctly typed, QoS-correct, and deserializable.

This is the verified foundation (gate **G0** in the roadmap below) for the semi-native support architecture described in [docs/architecture.md](docs/architecture.md).

## Relationship to `autoware_carla_interface`

`autoware_carla_interface` is the Python bridge for CARLA 0.9.15: it subscribes to CARLA data over the CARLA Python API and republishes it as ROS 2 topics. This proposal targets CARLA `ue5-dev`'s native DDS publishers instead, removing the bridge process from the data path entirely. The two serve different CARLA generations; this repository does not replace `autoware_carla_interface` for 0.9.15.

## Repository contents

| Path         | Purpose                                                                                                                                                                                                                                                                                                                         |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docker/`    | Autoware container Compose file and the shared CycloneDDS profile                                                                                                                                                                                                                                                               |
| `scripts/`   | Interop gate (check library + CLI, topic contract, reference sensor stack, orchestration script) and the live E2E harness + G1–G3 gate scripts (`scripts/e2e/`)                                                                                                                                                                 |
| `extension/` | Out-of-tree CARLA ROS 2 extension `.so` (`libcarla-autoware-extension.so`): Autoware-vocabulary message PODs + CDR codec + pinned RIHS01 type hashes, the `/vehicle/status/*` and `/sensing/gnss/pose*` publishers, the `/control/command/*` and `/autoware/engage` subscribers, and the `carla_ros2_extension_init` entrypoint |
| `runner/`    | Declarative Python CARLA-client runner: reads the sensor-kit calibration YAML as the source of truth, spawns the ego + sensor set with the right topic/QoS attributes, and owns the tick loop                                                                                                                                   |
| `tests/`     | pytest suites over the pure check logic and the runner (kit math, spawn attributes, CLI); runs in CI                                                                                                                                                                                                                            |
| `docs/`      | Architecture proposal, prerequisites, bring-up docs, and captured verification records                                                                                                                                                                                                                                          |

## Quick start

Requires a CARLA build from the prerequisite branch (see [docs/prerequisites.md](docs/prerequisites.md)) and Docker.

```bash
# 1. Bring up the Autoware container (one-time carla_msgs build: see prerequisites)
cd docker && docker compose up -d && cd ..

# 2. Run the G0 interop gate (boots CARLA, spawns the reference sensors, checks all topics)
CARLA_ROOT=/path/to/carla CARLA_UNREAL_ENGINE_PATH=/path/to/ue5 bash scripts/run_g0.sh
```

Expected output: a per-topic check table and `8/8 topics passed`.

For the full live stack (CARLA + extension `.so` + runner + official Autoware driving the Nishi-Shinjuku map), follow [docs/running-e2e.md](docs/running-e2e.md).

## Roadmap

| Gate | Content                                                                                                   | Status                                                         |
| ---- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| G0   | Native-DDS interop proven from inside the Autoware container                                              | **Done** ([docs/g0-report.md](docs/g0-report.md))              |
| G1   | Extension publishes `/vehicle/status/*`; NDT localization tracks on the Nishi-Shinjuku map (AWSIM v2.0.0) | **Done** — max err 0.077 m ([report](docs/e2e-report.md))      |
| G2   | Closed loop: route → engage → route completion via `/control/command/control_cmd`                         | **Done** — goal reached 0.111 m ([report](docs/e2e-report.md)) |
| G3   | LiDAR sustained at the configured rate; closed control loop at simulation rate                            | **Done** — 19.96 Hz both ([report](docs/e2e-report.md))        |
| G4   | Packaged CARLA + extension `.so` drop-in reproduces G2 without rebuild                                    | Future                                                         |

The semi-native core has two parts. **Tier A** — the CARLA-core extension API (the server `--ros2-extension` flag plus the `carla_ros2_extension_init` ABI) — is an upstream proposal against `carla-simulator/carla`, staged as draft PRs on the `youtalk/carla` fork and not yet merged upstream. **Tier B and Tier C** — `libcarla-autoware-extension.so` (`extension/`) and the declarative runner (`runner/`) — have landed in this repository, are built and unit-tested in CI, and are live-verified against official Autoware ([docs/e2e-report.md](docs/e2e-report.md)). See [docs/architecture.md](docs/architecture.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
