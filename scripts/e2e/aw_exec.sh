#!/usr/bin/env bash
# Run a command inside the Autoware container that run_carla_autoware.sh started.
# Usage: aw_exec.sh <log-dir> <domain-id> <bash -c string>
set -euo pipefail
LOG_DIR="$1"; DOMAIN="$2"; CMD="$3"
C="$(head -1 "$LOG_DIR/carla_autoware.containers")"
[ -n "$C" ] || { echo "no container recorded in $LOG_DIR/carla_autoware.containers" >&2; exit 2; }
docker exec -i "$C" bash -lc "for s in /opt/ros/*/setup.bash /opt/autoware/setup.bash; do [ -f \$s ] && source \$s; done; export ROS_DOMAIN_ID=$DOMAIN; $CMD"
