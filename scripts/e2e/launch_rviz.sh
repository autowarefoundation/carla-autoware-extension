#!/usr/bin/env bash
# Launch RViz2 INSIDE the `autoware` container against the live E2E stack, using the
# autoware_launch RViz profile (the image ships the Autoware RViz plugins -- vehicle
# overlay, trajectory/route displays, mission goal tool -- so the run is watchable the
# same way an AWSIM bring-up is).
#
# X11 path: the container runs network_mode:host + ipc:host and docker/compose.yaml
# mounts /tmp/.X11-unix, so the host X server is reachable both via the filesystem
# socket and the abstract socket. Grant local clients access once per session:
#     xhost +local:
# GL: the container has no NVIDIA runtime, so default to Mesa software rendering
# (LIBGL_ALWAYS_SOFTWARE=1). Override with LIBGL_ALWAYS_SOFTWARE=0 if the container
# is started with GPU access.
#
# use_sim_time is forced on: the whole stack is paced by CARLA's /clock, and a
# wall-clock RViz would reject every TF as stale.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"

: "${DISPLAY:?PREFLIGHT FAIL: DISPLAY is not set -- run from the desktop session (e.g. export DISPLAY=:1)}"

docker inspect -f '{{.State.Running}}' autoware 2>/dev/null | grep -q true \
  || { echo "PREFLIGHT FAIL: container 'autoware' not running (docker compose -f docker/compose.yaml up -d)" >&2; exit 1; }

# Fail loudly if X access was never granted: a missing grant otherwise surfaces as an
# unhelpful "Could not connect to display" deep inside rviz2's startup.
if command -v xhost >/dev/null 2>&1 && ! xhost 2>/dev/null | grep -qE 'LOCAL:|SI:localuser'; then
  echo "NOTE: X access control may block the container; if RViz cannot connect, run: xhost +local:" >&2
fi

# The universe-devel image ships the Autoware RViz plugins but NOT their
# rviz_2d_overlay_plugins dependency, so every autoware_*_rviz_plugin (and the
# planning Trajectory/Path displays) fails to dlopen without this. Installed
# into the container (idempotent); like the carla_msgs workspace, it lives
# outside every compose mount, so a recreated container needs it again.
docker compose -f "$COMPOSE" exec -T autoware bash -lc '
  [ -f /opt/ros/humble/lib/librviz_2d_overlay_plugins.so ] && exit 0
  echo "bootstrap: installing ros-humble-rviz-2d-overlay-plugins (one-time per container)"
  apt-get update -qq >/dev/null && apt-get install -y -qq ros-humble-rviz-2d-overlay-plugins >/dev/null
  [ -f /opt/ros/humble/lib/librviz_2d_overlay_plugins.so ]' \
  || { echo "PREFLIGHT FAIL: could not install rviz_2d_overlay_plugins in the container" >&2; exit 1; }

docker compose -f "$COMPOSE" exec \
  -e DISPLAY="$DISPLAY" \
  -e QT_X11_NO_MITSHM=1 \
  -e LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
  autoware bash -lc '
    source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash
    export ROS_DOMAIN_ID=0
    exec rviz2 -d "$(ros2 pkg prefix autoware_launch)/share/autoware_launch/rviz/autoware.rviz" \
      --ros-args -p use_sim_time:=true'
