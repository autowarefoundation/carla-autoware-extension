#!/usr/bin/env bash
# G2: engage -> closed-loop drive -> route completion on a traffic-light-free route.
# Sends engage, confirms control_cmd is flowing, then records the ego-to-goal distance
# series (host, CARLA ground-truth) and feeds it to measure_route.py, which EXITS
# NON-ZERO unless the ego reaches within tolerance of the goal (automated pass/fail).
# Usage: gate_g2_closed_loop.sh <goal_map_x> <goal_map_y>
set -euo pipefail
export ROS_DOMAIN_ID=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"
GOAL_X="${1:?goal map x required}"; GOAL_Y="${2:?goal map y required}"
WIN=120   # seconds to reach the goal
DIST=/tmp/g2_dist.txt

# Engage + assert control_cmd is actually flowing (a hard precondition for actuation).
# `ros2 topic hz` never self-terminates, so `timeout` SIGKILLs it and returns 124 on the
# expected/healthy path -- that is NOT a failure. The real liveness test is whether the
# captured output contains an "average rate:" line; a 124 with rate lines present means
# control_cmd IS live, so proceed. Only a genuinely silent topic (no rate lines) is FAIL.
docker compose -f "$COMPOSE" exec -T autoware bash -lc '
  source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0
  ros2 topic pub -1 /autoware/engage autoware_vehicle_msgs/msg/Engage "{engage: true}"
  echo "engaged; checking control_cmd liveness:"
  set +o pipefail
  timeout 10 ros2 topic hz /control/command/control_cmd --window 30 > /tmp/g2_hz.txt 2>&1; rc=$?
  set -o pipefail
  cat /tmp/g2_hz.txt
  grep -q "average rate:" /tmp/g2_hz.txt \
    || { echo "G2 FAIL: no control_cmd (vehicle_cmd_gate not commanding)"; exit 1; }
  [ "$rc" -eq 124 ] || [ "$rc" -eq 0 ] || { echo "G2 FAIL: ros2 topic hz errored rc=$rc"; exit "$rc"; }'

# Ego-to-goal distance series (map frame; CARLA Y is flipped to map).
# collect_gt.py maps CARLA metres into the MGRS-local map frame via the pinned affine
# (verify_mgrs_handedness.CONVERTER_OFFSET, byte-identical to the extension's MgrsOffset.h)
# before taking the XY distance to the goal.
PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m scripts.e2e.collect_gt --window "$WIN" --out "$DIST" --goal "$GOAL_X" "$GOAL_Y"

# Programmatic PASS/FAIL. Run this gate against the SYNC stack: sync propels given a valid
# trajectory, and async breaks NDT outright (docs/e2e-report.md "Async localization").
python3 "$HERE/measure_route.py" --distances "$DIST" --goal-tol-m 1.0
