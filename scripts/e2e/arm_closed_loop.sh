#!/usr/bin/env bash
# Arm the perception:=false E2E stack for a closed-loop drive (the G2 recipe).
#
# Sequence (each step fails loudly; docs/e2e-report.md records why each exists):
#   1. Re-seed /initialpose at the ego's CURRENT CARLA ground-truth pose and wait for
#      NDT to re-lock (NDT drifts while parked; never trust an idling lock).
#   2. Start scripts/e2e/dummy_perception.py in the container (clear-road objects/grid/
#      pointcloud + all-green signals). Must be running BEFORE the route is set, or
#      behavior_path_planner never produces a trajectory and the gate's control_cmd
#      pre-check fails.
#   3. Clear any previous route, then set the route via the AD API.
#   4. Optionally (default ON) suppress the perception-off false MRM:
#      vehicle_cmd_gate use_emergency_handling=false. The IMU frame fix cleared the
#      IMU-driven contributor, but the perception-off diagnostics remain one
#      (verified 2026-07-23) -- without this the gate MRM-overrides the drive command.
#   5. Print the pre-engage verification lines (routing state, raw vs gated control).
#
# Engage itself is gate_g2_closed_loop.sh's job. NOTE: engage LATCHES across re-arms --
# run `arm_closed_loop.sh --disarm` before teleporting/re-seeding/re-arming, or the ego
# drives off the moment the new trajectory forms.
#
# Default goal: the geometry-scored reroute goal 23.3 m into lanelet 226 (chain
# 253->255->495->280->283->382->226; min width 2.61 m @ 0.52 deg/m -- inside the proven
# envelope). Chosen from map geometry only, never from a driven trajectory, so the
# strict 1.0 m gate stays honest.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"
export ROS_DOMAIN_ID=0

GOAL_X="${GOAL_X:-81571.616}" GOAL_Y="${GOAL_Y:-50019.827}" GOAL_Z="${GOAL_Z:-42.07}"
GOAL_QZ="${GOAL_QZ:-0.090888}" GOAL_QW="${GOAL_QW:-0.995861}"
SUPPRESS_MRM="${SUPPRESS_MRM:-1}"

cx() { docker compose -f "$COMPOSE" exec -T autoware bash -lc "$1"; }
AW_ENV='source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0'

if [ "${1:-}" = "--disarm" ]; then
  echo "== disarm: change_to_stop + engage false (engage latches across re-arms) =="
  cx "$AW_ENV
    timeout 15 ros2 service call /api/operation_mode/change_to_stop autoware_adapi_v1_msgs/srv/ChangeOperationMode '{}' 2>&1 | grep -E 'success' | head -1
    ros2 topic pub -1 /autoware/engage autoware_vehicle_msgs/msg/Engage '{engage: false}' >/dev/null
    echo disarmed"
  exit 0
fi

echo "== 1. reseed /initialpose at the ego's current ground-truth pose =="
# Host side: read the ego's CARLA pose and map it with the pinned affine (the same
# scripts.e2e transform the gates use). yaw_map = -yaw_carla (single Y flip).
SEED=$(PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import math
import carla
from scripts.e2e.collect_gt import ego_map_xy, find_ego
from scripts.e2e.verify_mgrs_handedness import CONVERTER_OFFSET
world = carla.Client("localhost", 2000).get_world()
world.wait_for_tick()
ego = find_ego(world)
tf = ego.get_transform()
x, y = ego_map_xy(tf.location.x, tf.location.y)
z = CONVERTER_OFFSET[2] + tf.location.z
yaw = math.radians(-tf.rotation.yaw)
print(f"{x:.3f} {y:.3f} {z:.3f} {math.sin(yaw / 2):.6f} {math.cos(yaw / 2):.6f}")
PY
)
echo "   seed target (map frame): $SEED"
# SEED is five space-separated numbers by construction; word-splitting is intended.
cx "$AW_ENV && python3 /work/scripts/e2e/reseed_localization.py $SEED 60"

echo "== 2. start dummy_perception (clear road + all-green signals) =="
cx "$AW_ENV
  if [ -f /tmp/dummy_perception.pid ]; then kill \"\$(cat /tmp/dummy_perception.pid)\" 2>/dev/null || true; sleep 1; fi
  nohup python3 /work/scripts/e2e/dummy_perception.py >/tmp/dummy_perception.log 2>&1 &
  echo \$! >/tmp/dummy_perception.pid
  sleep 2
  grep -q 'publishing clear-road perception' /tmp/dummy_perception.log \
    || { echo 'PREFLIGHT FAIL: dummy_perception did not start (see /tmp/dummy_perception.log)'; exit 1; }
  echo \"dummy_perception pid \$(cat /tmp/dummy_perception.pid): \$(tail -1 /tmp/dummy_perception.log)\""

echo "== 3. clear route, then set route -> ($GOAL_X, $GOAL_Y) =="
cx "$AW_ENV
  timeout 15 ros2 service call /api/routing/clear_route autoware_adapi_v1_msgs/srv/ClearRoute '{}' 2>&1 | grep -E 'success' | head -1"
cx "$AW_ENV
  timeout 20 ros2 service call /api/routing/set_route_points autoware_adapi_v1_msgs/srv/SetRoutePoints \
    '{header: {frame_id: map}, option: {allow_goal_modification: true}, goal: {position: {x: $GOAL_X, y: $GOAL_Y, z: $GOAL_Z}, orientation: {x: 0.0, y: 0.0, z: $GOAL_QZ, w: $GOAL_QW}}, waypoints: []}' 2>&1 | grep -E 'success|message'"

echo "== 4. wait for the planning trajectory (<=40 s) =="
alive=0
for _ in $(seq 1 20); do
  r=$(cx "$AW_ENV; timeout 4 ros2 topic hz /planning/scenario_planning/trajectory 2>/dev/null | grep -c 'average rate'" || true)
  if [ "${r:-0}" -ge 1 ]; then alive=1; break; fi
  sleep 2
done
[ "$alive" = "1" ] || { echo "ARM FAIL: no /planning/scenario_planning/trajectory within 40 s" >&2; exit 1; }
echo "   trajectory alive"

if [ "$SUPPRESS_MRM" = "1" ]; then
  echo "== 5. suppress the perception-off false MRM (still required; see e2e-report) =="
  cx "$AW_ENV && ros2 param set /control/vehicle_cmd_gate use_emergency_handling false"
else
  echo "== 5. MRM suppression NOT applied (SUPPRESS_MRM=0) =="
fi

echo "== 6. pre-engage verification =="
cx "$AW_ENV
  echo -n 'routing_state='; timeout 3 ros2 topic echo --once /api/routing/state 2>/dev/null | grep 'state:' | head -1
  echo -n 'raw_ctrl(accel)='; timeout 4 ros2 topic echo --once /control/trajectory_follower/control_cmd 2>/dev/null | sed -n '/^longitudinal:/,\$p' | grep 'acceleration:' | head -1
  echo -n 'gate_ctrl(accel)='; timeout 4 ros2 topic echo --once /control/command/control_cmd 2>/dev/null | sed -n '/^longitudinal:/,\$p' | grep 'acceleration:' | head -1
  echo -n 'mrm_state='; timeout 4 ros2 topic echo --once /system/fail_safe/mrm_state 2>/dev/null | grep -E 'state:|behavior:' | tr '\n' ' '; echo"
echo "== armed. engage + measure: bash scripts/e2e/gate_g2_closed_loop.sh $GOAL_X $GOAL_Y =="
