#!/usr/bin/env bash
# G3: LiDAR sustained at 20 Hz; control loop at sim rate. ros2 topic hz measures
# WALL-CLOCK arrival, so the runner MUST be real-time-paced (Task 24) for 20 Hz to
# mean cadence. Captures both hz outputs to files and feeds each through
# measure_rates.py, which EXITS NON-ZERO when a rate leaves its band (so an 80 Hz
# free-running LiDAR FAILS instead of reading as PASS). Record which was measured.
set -euo pipefail
export ROS_DOMAIN_ID=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"
LHZ=/tmp/g3_lidar_hz.txt CHZ=/tmp/g3_control_hz.txt

docker compose -f "$COMPOSE" exec -T autoware bash -lc '
  source /opt/ros/humble/setup.bash && export ROS_DOMAIN_ID=0
  timeout 12 ros2 topic hz /sensing/lidar/top/pointcloud_raw_ex --window 40' | tee "$LHZ"
docker compose -f "$COMPOSE" exec -T autoware bash -lc '
  source /opt/ros/humble/setup.bash && export ROS_DOMAIN_ID=0
  timeout 12 ros2 topic hz /control/command/control_cmd --window 60' | tee "$CHZ"

rc=0
python3 "$HERE/measure_rates.py" --hz-file "$LHZ" --target 20 --tol 1  --label LiDAR   || rc=1
python3 "$HERE/measure_rates.py" --hz-file "$CHZ" --target 60 --tol 15 --label control || rc=1
exit "$rc"
