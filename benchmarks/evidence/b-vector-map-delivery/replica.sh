#!/usr/bin/env bash
# Standalone replica bench for the cell-B `waiting for map` diagnostic.
#
# WHY IT EXISTS: on cell B's static arm the Autoware stack lives ~100 s wall
# (B/run-028 99.9 s, B/run-029 102.8 s), which is too short to settle DDS
# discovery, dump every endpoint's QoS, and run a transport comparison. This
# bench brings up the SAME image, SAME map bundle and SAME `ros2 launch` line as
# benchmarks/cells/tier4_autoware.sh, under a DIFFERENT container name, with no
# CARLA and no harness involvement. It writes nothing into benchmarks/results/
# and modifies no harness file.
#
# DEVIATIONS FROM THE CELL, STATED: (1) no simulator, so `use_sim_time:=false`
# -- with sim time on and no /clock publisher every timer and throttled log in
# the stack would be frozen at t=0 and nothing would be observable; the map
# publish/deliver path does not read the clock. (2) container name `aw-replica`.
# Everything else -- image digest, RMW, DDS profile, map bundle, sensor/vehicle
# model, simulator_type, perception/rviz flags -- is the cell's.
#
# MUST NOT run while a harness run is live: same ROS_DOMAIN_ID, same host.
set -u

SCRATCH="$(cd "$(dirname "$0")" && pwd)"
REPO=/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0
IMAGE="ghcr.io/autowarefoundation/autoware@sha256:5c22369a312f1cd8a03fb65b30c1ab542919c2c7a2cbd18e799956daef3ae8ee"
MAP_HOST="$HOME/autoware_map/town10-regen"
MAP_DIR=/autoware_map/town10-regen
POSE_INIT="$REPO/benchmarks/config/autoware/pose_initializer.param.yaml"
POSE_TGT=/opt/autoware/share/autoware_launch/config/localization/pose_initializer.param.yaml
UDP_ONLY="$REPO/benchmarks/observer/config/udp_only.xml"
BPP=/planning/scenario_planning/lane_driving/behavior_planning/behavior_path_planner
C=aw-replica

ts() { date +%s.%N; }
cx() { docker exec -e ROS_DOMAIN_ID=0 "$C" bash -lc "$AW_ENV && $1" 2>&1; }

variant() { # variant <name> <docker args...>
  local name="$1"; shift
  echo
  echo "################################################################"
  echo "### VARIANT $name   [t=$(ts)]"
  echo "################################################################"
  docker rm -f "$C" >/dev/null 2>&1 || true
  echo "\$ docker run -d --name $C --gpus all --net=host --ipc=host -e ROS_DOMAIN_ID=0 $* -v $MAP_HOST:$MAP_DIR:ro -v $POSE_INIT:$POSE_TGT:ro $IMAGE sleep infinity"
  docker run -d --name "$C" --gpus all --net=host --ipc=host -e ROS_DOMAIN_ID=0 \
    "$@" -v "$MAP_HOST:$MAP_DIR:ro" -v "$POSE_INIT:$POSE_TGT:ro" \
    "$IMAGE" sleep infinity >/dev/null || { echo "FAILED to start $C"; return 1; }

  echo "--- env in force ---"
  cx "printenv RMW_IMPLEMENTATION; printenv FASTRTPS_DEFAULT_PROFILES_FILE || echo '(FASTRTPS_DEFAULT_PROFILES_FILE unset)'; printenv CYCLONEDDS_URI || echo '(CYCLONEDDS_URI unset)'"

  for f in map_probe.py diag_probe.py diag_watch.py; do
    docker cp "$SCRATCH/$f" "$C:/tmp/$f" >/dev/null
  done

  echo "--- launching e2e_simulator (cells/tier4_autoware.sh line, use_sim_time:=false) [t=$(ts)] ---"
  cx "nohup ros2 launch autoware_launch e2e_simulator.launch.xml \
      map_path:=$MAP_DIR \
      sensor_model:=awsim_labs_sensor_kit vehicle_model:=sample_vehicle \
      simulator_type:=awsim launch_vehicle_interface:=false \
      use_sim_time:=false perception:=false rviz:=false >/tmp/replica.log 2>&1 &
    echo \$! >/tmp/replica.pid" >/dev/null
  local launch_wall; launch_wall=$(ts)
  echo "launch issued at wall=$launch_wall"

  # An early-joining in-stack subscriber's own receipt time, watched from t=0.
  docker exec -d -e ROS_DOMAIN_ID=0 "$C" bash -lc \
    "$AW_ENV && python3 /tmp/diag_watch.py 200 >/tmp/diag_watch.log 2>&1"

  echo "--- waiting up to 180s for 'Succeeded to load lanelet2_map' ---"
  local d=$((SECONDS + 180))
  until cx "grep -q 'Succeeded to load lanelet2_map' /tmp/replica.log" >/dev/null 2>&1; do
    [ "$SECONDS" -lt "$d" ] || { echo "TIMEOUT: map never loaded"; break; }
    sleep 3
  done
  echo "map-load marker seen at wall=$(ts)"
  cx "grep -n 'lanelet2_map\|map_projector_info.yaml' /tmp/replica.log | head -8"

  echo "--- settling 75s so discovery is complete and every probe is a LATE joiner ---"
  sleep 75

  echo; echo "--- R1 topic info -v /map/vector_map  (ALL endpoints + QoS) [t=$(ts)] ---"
  cx "ros2 topic info -v --no-daemon /map/vector_map"
  echo; echo "--- R2 node info $BPP [t=$(ts)] ---"
  cx "ros2 node info --no-daemon $BPP"
  echo; echo "--- R3 late transient_local subscriber -> /map/vector_map (60s) [t=$(ts)] ---"
  # shellcheck disable=SC2016 # $VT/$PT expand IN the container, on purpose
  cx 'VT=$(ros2 topic list -t --no-daemon | awk "/^\/map\/vector_map /{gsub(/[][]/,\"\",\$2); print \$2}"); echo "type=$VT"; python3 /tmp/map_probe.py /map/vector_map $VT transient_local 60'
  echo; echo "--- R4 late VOLATILE subscriber -> /map/vector_map (15s) [t=$(ts)] ---"
  # shellcheck disable=SC2016 # $VT expands IN the container, on purpose
  cx 'VT=$(ros2 topic list -t --no-daemon | awk "/^\/map\/vector_map /{gsub(/[][]/,\"\",\$2); print \$2}"); python3 /tmp/map_probe.py /map/vector_map $VT volatile 15'
  echo; echo "--- R5 component_state_monitor verdict now (15s) [t=$(ts)] ---"
  cx "python3 /tmp/diag_probe.py 15"
  echo; echo "--- R6 diag watch history (when the in-stack early joiner first got it) ---"
  cx "cat /tmp/diag_watch.log"
  echo; echo "--- R7 planner-side waiting histogram ---"
  cx "grep -o 'waiting for [a-z_ ]*' /tmp/replica.log | sort | uniq -c | sort -rn | head"
  echo; echo "--- R8 vector_map lines in the launch log ---"
  cx "grep -c 'The target mode is not available' /tmp/replica.log; grep -n 'topic_rate_check/vector_map' /tmp/replica.log | head -3; echo ...; grep -n 'topic_rate_check/vector_map' /tmp/replica.log | tail -3"

  docker cp "$C:/tmp/replica.log" "$SCRATCH/cap/replica-$name.log" >/dev/null 2>&1 || true
  docker rm -f "$C" >/dev/null 2>&1 || true
  echo "### VARIANT $name torn down [t=$(ts)]"
  sleep 10
}

AW_ENV='source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0'

variant "V1-fastrtps-udp_only-STOCK-CELL-B" \
  -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  -e FASTRTPS_DEFAULT_PROFILES_FILE=/dds-profile.xml -v "$UDP_ONLY:/dds-profile.xml:ro"

variant "V1b-fastrtps-udp_only-REPEAT" \
  -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  -e FASTRTPS_DEFAULT_PROFILES_FILE=/dds-profile.xml -v "$UDP_ONLY:/dds-profile.xml:ro"

variant "V2-cyclonedds-CELLS-A-C-CONTROL" \
  -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

echo
echo "=== replica bench done at t=$(ts) ==="
