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
docker compose -f "$COMPOSE" exec -T autoware bash -lc '
  source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0
  ros2 topic pub -1 /autoware/engage autoware_vehicle_msgs/msg/Engage "{engage: true}"
  echo "engaged; checking control_cmd liveness:"
  timeout 10 ros2 topic hz /control/command/control_cmd --window 30 \
    || { echo "G2 FAIL: no control_cmd (vehicle_cmd_gate not commanding)"; exit 1; }'

# Ego-to-goal distance series (map frame; CARLA Y is flipped to map).
python3 - "$WIN" "$GOAL_X" "$GOAL_Y" "$DIST" <<'PY'
import sys, time, math, carla
win=float(sys.argv[1]); gx=float(sys.argv[2]); gy=float(sys.argv[3]); out=sys.argv[4]
w=carla.Client("localhost",2000).get_world()
ego=next(a for a in w.get_actors().filter("vehicle.*") if a.attributes.get("role_name")=="ego")
end=time.time()+win; rows=[]
while time.time()<end:
    t=ego.get_transform().location
    rows.append(f"{math.hypot(t.x-gx, (-t.y)-gy):.4f}")
    time.sleep(0.1)
open(out,"w").write("\n".join(rows)+"\n"); print(f"dist_rows={len(rows)}")
PY

# Programmatic PASS/FAIL. On FAIL (ego never approached the goal — e.g. sync-mode
# non-propulsion), re-run the runner with --async and repeat.
python3 "$HERE/measure_route.py" --distances "$DIST" --goal-tol-m 1.0
