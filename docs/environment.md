# Environment record

Captured while bringing up the Autoware container for the
CARLA/Autoware ROS 2 native interop spike (G0 gate). This file pins the
exact environment the later gate scripts assume, in particular
the golden REP-2011 RIHS01 type hashes, which are distro-specific.

## Host

- Date: 2026-07-09
- Host kernel: `6.17.0-35-generic` (matches the kernel seen from inside
  the container, since it runs with `network_mode: host` / shares the
  host kernel — no separate VM).
- Docker: `Docker version 29.6.1, build 8900f1d`

## Image

- Image tag: `ghcr.io/autowarefoundation/autoware:universe-devel`
- Image digest: `sha256:405225eda6c05161bfde39cc7885511f3f4d9699d126891891420dd80c2e024a`
  (from `docker inspect --format='{{index .RepoDigests 0}}' ghcr.io/autowarefoundation/autoware:universe-devel`)

## ROS 2 / DDS

- `ROS_DISTRO`: `humble`
- RMW implementation: `rmw_cyclonedds_cpp` (set via `RMW_IMPLEMENTATION`
  in `docker/compose.yaml`)
- `CYCLONEDDS_URI`: `file:///work/docker/cyclonedds.xml` (localhost-only
  profile, shared by both the container and the CARLA host process — see
  `docker/cyclonedds.xml`)
- `ros2 doctor --report | head -30` runs successfully once ROS 2 is
  sourced (see "Sourcing ROS 2 inside `docker compose exec`" below).

## Sourcing ROS 2 inside `docker compose exec`

The image's `/ros_entrypoint.sh` sources `/opt/ros/$ROS_DISTRO/setup.bash`
and `/opt/autoware/setup.bash` before running the container's main
process (`sleep infinity`), but `docker compose exec` starts a fresh
process that does **not** inherit that sourcing. Every `docker compose
exec autoware bash -lc '...'` invocation that needs `ros2` (or any
ROS 2 tool) must source manually first:

```bash
source /opt/ros/$ROS_DISTRO/setup.bash
source /opt/autoware/setup.bash
```

## `carla_msgs`

- Apt route (`sudo apt-get install -y ros-$ROS_DISTRO-carla-msgs`) does
  **not** work: `E: Unable to locate package ros-humble-carla-msgs`. No
  `ros-humble-carla-msgs` package exists in the configured apt sources.
- Source route worked: cloned
  `https://github.com/carla-simulator/ros-carla-msgs.git` into
  `~/carla_msgs_ws/src` and built with `colcon build` (after sourcing
  `/opt/ros/$ROS_DISTRO/setup.bash`). Build succeeded: "Summary: 1
  package finished" for `carla_msgs`.
- Verified (not just built): after sourcing the workspace overlay,
  `ros2 interface show carla_msgs/msg/CarlaEgoVehicleStatus` prints the
  full message definition (header, velocity, acceleration, orientation,
  nested `CarlaEgoVehicleControl`), confirming the interface actually
  resolves.
- **Later tasks must source this exact line** (in addition to the base
  ROS 2 sourcing above) before any `ros2` command that needs
  `carla_msgs`:

  ```bash
  source ~/carla_msgs_ws/install/setup.bash
  ```

## PyYAML

- `python3 -c "import yaml; print(yaml.__version__)"` succeeds inside
  the container out of the box: PyYAML `5.4.1` is already installed as
  part of the base image (no `pip install` needed). The
  `interop_check.py` gate can rely on `import yaml` without extra setup.
