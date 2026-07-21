#!/usr/bin/env bash
# Build carla_msgs from source inside the running `autoware` container.
# The workspace at ~/carla_msgs_ws lives OUTSIDE every compose mount, so
# `docker compose down` destroys it. Re-run this after any recreate.
# Idempotent: skips the build when install/setup.bash already exists.
set -euo pipefail

CONTAINER=autoware
docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true \
  || { echo "PREFLIGHT FAIL: container '$CONTAINER' is not running (docker compose up -d)"; exit 1; }

docker exec "$CONTAINER" bash -lc '
  # NOTE: no "-u" here (deliberately not set -euo pipefail): /opt/ros/humble/setup.bash
  # references $AMENT_TRACE_SETUP_FILES without a default and dies under nounset.
  # Same reason the docker-exec sourcing block in run_g0.sh and Step 4 of this
  # bootstrap brief never set -u either.
  set -eo pipefail
  if [ -f ~/carla_msgs_ws/install/setup.bash ]; then
    echo "carla_msgs already built"; exit 0
  fi
  source /opt/ros/humble/setup.bash
  mkdir -p ~/carla_msgs_ws/src
  cd ~/carla_msgs_ws/src
  git clone --depth 1 https://github.com/carla-simulator/ros-carla-msgs.git carla_msgs || true
  cd ~/carla_msgs_ws
  colcon build --packages-select carla_msgs
  echo "carla_msgs built at ~/carla_msgs_ws"
'
