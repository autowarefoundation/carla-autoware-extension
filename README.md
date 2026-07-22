# carla-autoware-extension

> **Status: Proposal** — This repository accompanies a proposal for semi-native Autoware support in CARLA (`ue5-dev`). It depends on CARLA pull requests that are **not yet merged** (native ROS 2 series #9743–#9758, DDS middleware abstraction #9807–#9816, `ue5-dev` ports of #9786/#9787). Nothing here is usable against a stock CARLA release yet. See [docs/prerequisites.md](docs/prerequisites.md) for the exact CARLA build this content is verified against.

## Purpose

CARLA `ue5-dev` can publish sensor and vehicle data as native ROS 2 (DDS) topics — no bridge process, no republishing. This repository holds the Autoware-side companion assets for driving Autoware against that native path:

- a Docker Compose setup that brings up the official Autoware container sharing the host's DDS domain with CARLA over CycloneDDS, and
- an interoperability gate (`scripts/interop_check.py`) that proves, from inside the Autoware container, that every expected CARLA topic is present, correctly typed, QoS-correct, and deserializable.

This is the verified foundation (gate **G0** of the staged plan below) for the semi-native support architecture described in [docs/architecture.md](docs/architecture.md).

## Relationship to `autoware_carla_interface`

`autoware_carla_interface` is the Python bridge for CARLA 0.9.15: it subscribes to CARLA data over the CARLA Python API and republishes it as ROS 2 topics. This proposal targets CARLA `ue5-dev`'s native DDS publishers instead, removing the bridge process from the data path entirely. The two serve different CARLA generations; this repository does not replace `autoware_carla_interface` for 0.9.15.

## Repository contents

| Path       | Purpose                                                                                     |
| ---------- | ------------------------------------------------------------------------------------------- |
| `docker/`  | Autoware container Compose file and the shared CycloneDDS profile                           |
| `scripts/` | Interop gate: check library + CLI, topic contract, spike sensor stack, orchestration script |
| `tests/`   | pytest suite over the pure check logic (runs in CI)                                         |
| `docs/`    | Architecture proposal, prerequisites, and captured verification records                     |

## Quick start

Requires a CARLA build from the prerequisite branch (see [docs/prerequisites.md](docs/prerequisites.md)) and Docker.

```bash
# 1. Bring up the Autoware container (one-time carla_msgs build: see prerequisites)
cd docker && docker compose up -d && cd ..

# 2. Run the G0 interop gate (boots CARLA, spawns the spike sensors, checks all topics)
CARLA_ROOT=/path/to/carla CARLA_UNREAL_ENGINE_PATH=/path/to/ue5 bash scripts/run_g0.sh
```

Expected output: a per-topic check table and `8/8 topics passed`.

## Roadmap

| Gate | Content                                                                                                   | Status                         |
| ---- | --------------------------------------------------------------------------------------------------------- | ------------------------------ |
| G0   | Native-DDS interop proven from inside the Autoware container                                              | **Done** (assets in this repo) |
| G1   | Extension publishes `/vehicle/status/*`; NDT localization tracks on the Nishi-Shinjuku map (AWSIM v2.0.0) | Future                         |
| G2   | Closed loop: RViz route → engage → route completion via `/control/command/control_cmd`                    | Future                         |
| G3   | LiDAR sustained at the configured rate; closed control loop at simulation rate                            | Future                         |
| G4   | Packaged CARLA + extension `.so` drop-in reproduces G2 without rebuild                                    | Future                         |

The semi-native core — the CARLA-core extension API, `libcarla-autoware-extension.so` (`extension/`), and the declarative runner (`runner/`) — lands in this repository in future phases; see [docs/architecture.md](docs/architecture.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
