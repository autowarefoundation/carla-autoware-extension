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
# Nishi-Shinjuku's goal: the geometry-scored reroute goal 23.3 m into lanelet 226 (chain
# 253->255->495->280->283->382->226; min width 2.61 m @ 0.52 deg/m -- inside the proven
# envelope). Chosen from map geometry only, never from a driven trajectory, so the
# strict 1.0 m gate stays honest.
#
# MAP: everything per-map (bundle, grid centre, route goal) is derived from
# scripts/e2e/map_defaults.sh via CARLA_AUTOWARE_MAP, which also selects the extension's
# converter offset -- run_e2e.sh prints the exact export line for the active map. Unset
# selects Nishi-Shinjuku, so an argument-free arm is unchanged. GOAL_* still override.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"
export ROS_DOMAIN_ID=0

SUPPRESS_MRM="${SUPPRESS_MRM:-1}"

# Which map is armed. DERIVED from CARLA_AUTOWARE_MAP -- the one variable the
# operator already exports for the gates -- through the shared table, so the
# bundle can never disagree with the map being driven. A hard-coded default here
# would silently feed dummy_perception another map's lanelet2; on a signalised
# map that publishes signals which do not exist as GREEN, and the empty-list
# warning cannot fire because the list is not empty. That is precisely the
# two-knobs-must-agree failure this harness exists to prevent.
MAP_NAME="${CARLA_AUTOWARE_MAP:-NishishinjukuMap}"
# The linter runs without -x in pre-commit and so cannot follow the source even
# with the directive below; SC1091 is informational and disabled for that reason.
# shellcheck source=scripts/e2e/map_defaults.sh disable=SC1091
. "$HERE/map_defaults.sh"
carla_autoware_map_defaults "$MAP_NAME"
MAP_DIR="${MAP_DIR:-$MAP_DEFAULT_DIR}"
if [ -z "$MAP_DIR" ]; then
  echo "ARM FAIL: CARLA_AUTOWARE_MAP=$MAP_NAME has no known Autoware bundle;" >&2
  echo "  set MAP_DIR to its container path (see scripts/e2e/map_defaults.sh)." >&2
  exit 1
fi
# Route goal, from the SAME table. It used to default to Nishi's constants
# unconditionally while MAP_DIR and the grid centre had already moved into the
# table, so a Town10 arm that forgot GOAL_* routed to a point 81 km outside the
# map frame. That failure is loud, unlike the bundle one, but it is the last
# per-map knob that still had to be typed by hand.
if [ -n "$MAP_DEFAULT_GOAL" ]; then
  # MAP_DEFAULT_GOAL is five space-separated numbers by construction.
  read -r DEF_GX DEF_GY DEF_GZ DEF_GQZ DEF_GQW <<<"$MAP_DEFAULT_GOAL"
fi
GOAL_X="${GOAL_X:-${DEF_GX:-}}" GOAL_Y="${GOAL_Y:-${DEF_GY:-}}" GOAL_Z="${GOAL_Z:-${DEF_GZ:-}}"
GOAL_QZ="${GOAL_QZ:-${DEF_GQZ:-}}" GOAL_QW="${GOAL_QW:-${DEF_GQW:-}}"
if [ -z "$GOAL_X" ] || [ -z "$GOAL_Y" ] || [ -z "$GOAL_Z" ] ||
  [ -z "$GOAL_QZ" ] || [ -z "$GOAL_QW" ]; then
  echo "ARM FAIL: map $MAP_NAME has no registered route goal;" >&2
  echo "  export GOAL_X/GOAL_Y/GOAL_Z/GOAL_QZ/GOAL_QW (map-frame metres +" >&2
  echo "  yaw quaternion), or add MAP_DEFAULT_GOAL for it in map_defaults.sh." >&2
  exit 1
fi
echo "== map $MAP_NAME  bundle $MAP_DIR  goal $GOAL_X $GOAL_Y =="

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
# offset_for_map() resolves the ACTIVE map from $CARLA_AUTOWARE_MAP; the yaw rule is
# offset-independent (it comes from the shared Y flip), so only z/x/y move per map.
SEED=$(PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import math
import carla
from scripts.e2e.collect_gt import ego_map_xy, find_ego
from scripts.e2e.verify_mgrs_handedness import offset_for_map
offset = offset_for_map()
world = carla.Client("localhost", 2000).get_world()
world.wait_for_tick()
ego = find_ego(world)
tf = ego.get_transform()
x, y = ego_map_xy(tf.location.x, tf.location.y, offset)
z = offset[2] + tf.location.z
yaw = math.radians(-tf.rotation.yaw)
print(f"{x:.3f} {y:.3f} {z:.3f} {math.sin(yaw / 2):.6f} {math.cos(yaw / 2):.6f}")
PY
)
echo "   seed target (map frame): $SEED"
# SEED is five space-separated numbers by construction; word-splitting is intended.
cx "$AW_ENV && python3 /work/scripts/e2e/reseed_localization.py $SEED 60"

echo "== 2. start dummy_perception (clear road + all-green signals) =="
# Free-space grid centre + size. A committed route file (config/routes/<map>.yaml,
# Task 7's schema; ROUTE_FILE points at one) gives the tightest correct answer: the
# grid is sized from the route's OWN bounding box (midpoint + diagonal), so it
# always covers the driven corridor without a fixed span that could clip a long
# route or waste cells on a short one. Without ROUTE_FILE, today's behaviour is
# unchanged: a map with a baked constant in the shared table keeps it EXACTLY
# (Nishi-Shinjuku, whose live gate could not be re-run when the table was
# introduced -- not changing it is the only honest way to protect an invariant you
# cannot retest); any other map centres the grid on the ego pose just seeded
# above, which is the more correct behaviour. MAP_DIR selects which lanelet2
# supplies the traffic-light groups regardless of which centre/size path is used.
GRID_SIZE_ARG=""
if [ -n "${ROUTE_FILE:-}" ]; then
  # Host side: bbox midpoint + diagonal of the route's map-frame polyline,
  # +100 m margin so the free-space grid still reaches past the route ends.
  # The bbox->(centre,size) arithmetic lives in the tested pure function
  # scripts/e2e/route_grid.grid_from_polyline (tests/e2e/test_route_grid.py)
  # rather than an unverified inline heredoc -- this exact heredoc used to
  # carry a `read` word-splitting bug (GRID_XY got only the first number),
  # caught only by hand, which is the class of defect this task closes.
  read -r GRID_X GRID_Y GRID_SIZE <<<"$(PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m scripts.e2e.route_grid "$ROUTE_FILE")"
  GRID_XY="$GRID_X $GRID_Y"
  GRID_SIZE_ARG="--grid-size $GRID_SIZE"
  echo "   grid centre $GRID_XY, size ${GRID_SIZE} m (from $ROUTE_FILE)"
elif [ -n "$MAP_DEFAULT_GRID_CENTRE" ]; then
  GRID_XY="$MAP_DEFAULT_GRID_CENTRE"
  echo "   free-space grid centre: $GRID_XY"
else
  GRID_XY="$(echo "$SEED" | cut -d' ' -f1-2)"  # SEED's first two fields are map x/y
  echo "   free-space grid centre: $GRID_XY"
fi
cx "$AW_ENV
  export MAP_DIR='$MAP_DIR'
  if [ -f /tmp/dummy_perception.pid ]; then kill \"\$(cat /tmp/dummy_perception.pid)\" 2>/dev/null || true; sleep 1; fi
  nohup python3 /work/scripts/e2e/dummy_perception.py --grid-center $GRID_XY $GRID_SIZE_ARG >/tmp/dummy_perception.log 2>&1 &
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
