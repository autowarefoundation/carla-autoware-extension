# Prerequisites

Everything in this repository is verified against a specific CARLA `ue5-dev` build that stacks pull requests **not yet merged upstream**. This page pins that build and the container-side setup; it is the single place these pins live.

## CARLA build

Branch: [`youtalk/carla` `feat/autoware-native-ros2-stack`](https://github.com/youtalk/carla/tree/feat/autoware-native-ros2-stack) — upstream `ue5-dev` plus, in order:

| Content                                                                                                                                                                                                                                      | Upstream reference                                                                                  |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| V2X sensor family + WalkerManager null guard                                                                                                                                                                                                 | carla-simulator/carla#9757, #9758 (open drafts, tail of the merged #9743–#9756 native ROS 2 series) |
| DDS middleware abstraction: CDR foundation → middleware abstraction → CycloneDDS → `--rmw=` runtime selection → Zenoh → `--ros-domain-id` → Fast-DDS 2.14.6                                                                                  | carla-simulator/carla#9807–#9816 (open drafts, the #9762 series)                                    |
| Publisher durability QoS + latched `/carla/map` topic (`ue5-dev` port)                                                                                                                                                                       | carla-simulator/carla#9786 (opened against `ue4-dev`)                                               |
| Ego vehicle status/info + odometry publishers (`ue5-dev` port; TF tree and traffic lights excluded)                                                                                                                                          | carla-simulator/carla#9787 (opened against `ue4-dev`)                                               |
| Integration fixes: ego publisher constructors defined out-of-line so middleware creation succeeds; publisher Init failures logged at error severity; empty-mesh guard in `Map::GenerateChunkedMesh`; CycloneDDS `from_ser` sample reassembly | Found while stacking; reportable as review comments on the PRs above                                |

Build the editor target (the binary `scripts/run_g0.sh` launches):

```bash
cmake --preset Development   # first time only
ninja -C Build/Development carla-unreal-editor
```

## Autoware container

`docker/compose.yaml` runs `ghcr.io/autowarefoundation/autoware:universe-devel` with host networking, CycloneDDS as the RMW, and the shared `docker/cyclonedds.xml` profile (localhost-scoped). The CARLA process must use the same profile and DDS domain; `scripts/run_g0.sh` exports both.

One-time per container (lost when the container is recreated): the interop gate echoes `carla_msgs` types, which the image does not ship, so build them from source inside the container:

```bash
docker compose exec autoware bash -lc '
  source /opt/ros/humble/setup.bash &&
  mkdir -p ~/carla_msgs_ws/src &&
  git clone https://github.com/carla-simulator/ros-carla-msgs.git ~/carla_msgs_ws/src/ros-carla-msgs &&
  cd ~/carla_msgs_ws && colcon build --symlink-install'
```

## Manual G0 verification procedure

CI runs lint and the pure-logic tests only; the interop gate itself needs a CARLA build and a GPU, so it is manual:

```bash
cd docker && docker compose up -d && cd ..
CARLA_ROOT=/path/to/carla CARLA_UNREAL_ENGINE_PATH=/path/to/ue5 bash scripts/run_g0.sh
```

Environment variables consumed by `run_g0.sh`:

| Variable                   | Required | Meaning                                                                                                                               |
| -------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `CARLA_ROOT`               | yes      | CARLA source tree built from the reference branch                                                                                     |
| `CARLA_UNREAL_ENGINE_PATH` | yes      | CARLA-fork Unreal Engine 5 tree (standard CARLA build variable)                                                                       |
| `CARLA_VENV`               | no       | Python virtualenv with the matching `carla` client wheel; the spawner needs `import carla` to work in whatever Python runs the script |

Pass criterion: `8/8 topics passed`, exit code 0.
