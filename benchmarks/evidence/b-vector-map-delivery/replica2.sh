#!/usr/bin/env bash
# Replica bench, pass 2: does the FAILING endpoint change behaviour when the
# whole stack gets larger UDP socket buffers?
#
# Pass 1 established the contrast (late joiner 0.8 s vs the in-stack
# early-joining topic_state_monitor never). Pass 1's 16 MiB-buffer probe was
# run on a QUIET single-purpose process where the stock profile ALREADY worked,
# so it tested nothing about the failing endpoint. This pass applies the buffer
# change to EVERY node in the stack and re-reads the same in-stack monitor.
#
# Same deviations, same non-interference guarantees as replica.sh.
set -u

SCRATCH="$(cd "$(dirname "$0")" && pwd)"
REPO=/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0
IMAGE="ghcr.io/autowarefoundation/autoware@sha256:5c22369a312f1cd8a03fb65b30c1ab542919c2c7a2cbd18e799956daef3ae8ee"
MAP_HOST="$HOME/autoware_map/town10-regen"
MAP_DIR=/autoware_map/town10-regen
POSE_INIT="$REPO/benchmarks/config/autoware/pose_initializer.param.yaml"
POSE_TGT=/opt/autoware/share/autoware_launch/config/localization/pose_initializer.param.yaml
UDP_ONLY="$REPO/benchmarks/observer/config/udp_only.xml"
C=aw-replica
AW_ENV='source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0'
VT=autoware_map_msgs/msg/LaneletMapBin

ts() { date +%s.%N; }
cx() { docker exec -e ROS_DOMAIN_ID=0 "$C" bash -lc "$AW_ENV && $1" 2>&1; }

variant() { # variant <name> <docker args...>
  local name="$1"; shift
  echo
  echo "################################################################"
  echo "### PASS-2 VARIANT $name   [t=$(ts)]"
  echo "################################################################"
  docker rm -f "$C" >/dev/null 2>&1 || true
  docker run -d --name "$C" --gpus all --net=host --ipc=host -e ROS_DOMAIN_ID=0 \
    "$@" -v "$MAP_HOST:$MAP_DIR:ro" -v "$POSE_INIT:$POSE_TGT:ro" \
    "$IMAGE" sleep infinity >/dev/null || { echo "FAILED to start $C"; return 1; }
  echo "--- env in force ---"
  cx "printenv RMW_IMPLEMENTATION; printenv FASTRTPS_DEFAULT_PROFILES_FILE || echo '(unset)'; echo '--- profile ---'; cat \${FASTRTPS_DEFAULT_PROFILES_FILE:-/dev/null} 2>/dev/null"

  for f in map_probe.py diag_probe.py diag_watch.py; do
    docker cp "$SCRATCH/$f" "$C:/tmp/$f" >/dev/null
  done

  # EARLY-JOINING probe: started BEFORE the launch, so its subscription exists
  # before map_loader's writer does -- the same join order as every in-stack
  # consumer, in a process I control and can read the receipt time from.
  docker exec -d -e ROS_DOMAIN_ID=0 "$C" bash -lc \
    "$AW_ENV && python3 /tmp/map_probe.py /map/vector_map $VT transient_local 200 >/tmp/early_probe.log 2>&1"
  docker exec -d -e ROS_DOMAIN_ID=0 "$C" bash -lc \
    "$AW_ENV && python3 /tmp/diag_watch.py 200 >/tmp/diag_watch.log 2>&1"
  sleep 3

  echo "--- launching e2e_simulator [t=$(ts)] ---"
  cx "nohup ros2 launch autoware_launch e2e_simulator.launch.xml \
      map_path:=$MAP_DIR \
      sensor_model:=awsim_labs_sensor_kit vehicle_model:=sample_vehicle \
      simulator_type:=awsim launch_vehicle_interface:=false \
      use_sim_time:=false perception:=false rviz:=false >/tmp/replica.log 2>&1 &
    echo \$! >/tmp/replica.pid" >/dev/null
  echo "launch issued at wall=$(ts)"

  local d=$((SECONDS + 180))
  until cx "grep -q 'Succeeded to load lanelet2_map' /tmp/replica.log" >/dev/null 2>&1; do
    [ "$SECONDS" -lt "$d" ] || { echo "TIMEOUT: map never loaded"; break; }
    sleep 3
  done
  echo "--- map published; marker line: ---"
  cx "grep -n 'Succeeded to load lanelet2_map' /tmp/replica.log"

  echo "--- settling 100s ---"
  sleep 100

  echo; echo "--- W1 EARLY-joining transient_local probe result [t=$(ts)] ---"
  cx "cat /tmp/early_probe.log"
  echo; echo "--- W2 LATE-joining transient_local probe (30s) [t=$(ts)] ---"
  cx "python3 /tmp/map_probe.py /map/vector_map $VT transient_local 30"
  echo; echo "--- W3 in-stack monitor verdict now (15s) ---"
  cx "python3 /tmp/diag_probe.py 15"
  echo; echo "--- W4 diag watch history ---"
  cx "cat /tmp/diag_watch.log"
  echo; echo "--- W5 diag-graph blocks listing vector_map ---"
  cx "echo -n 'blocks: '; grep -c 'The target mode is not available' /tmp/replica.log; echo -n 'vector_map entries: '; grep -c 'topic_rate_check/vector_map' /tmp/replica.log"

  docker cp "$C:/tmp/replica.log" "$SCRATCH/cap/replica2-$name.log" >/dev/null 2>&1 || true
  docker rm -f "$C" >/dev/null 2>&1 || true
  echo "### PASS-2 VARIANT $name torn down [t=$(ts)]"
  sleep 10
}

variant "W-udp_only-STOCK-early-vs-late" \
  -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  -e FASTRTPS_DEFAULT_PROFILES_FILE=/dds-profile.xml -v "$UDP_ONLY:/dds-profile.xml:ro"

variant "W-udp_only-16MiB-BUFFERS-whole-stack" \
  -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  -e FASTRTPS_DEFAULT_PROFILES_FILE=/dds-profile.xml -v "$SCRATCH/udp_big.xml:/dds-profile.xml:ro"

echo
echo "=== replica pass 2 done at t=$(ts) ==="
