#!/usr/bin/env bash
# Smoke-test benchmarks/injector/republish_vector_map.py against a REAL stack
# before spending a live closed-loop run on it. Same replica bench as Task 4b
# (same image, bundle, launch line, cell-B transport), container aw-replica,
# no CARLA, no harness, nothing written into benchmarks/results/.
set -u

REPO=/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0
IMAGE="ghcr.io/autowarefoundation/autoware@sha256:5c22369a312f1cd8a03fb65b30c1ab542919c2c7a2cbd18e799956daef3ae8ee"
MAP_HOST="$HOME/autoware_map/town10-regen"
MAP_DIR=/autoware_map/town10-regen
POSE_INIT="$REPO/benchmarks/config/autoware/pose_initializer.param.yaml"
POSE_TGT=/opt/autoware/share/autoware_launch/config/localization/pose_initializer.param.yaml
UDP_ONLY="$REPO/benchmarks/observer/config/udp_only.xml"
C=aw-replica
AW_ENV='source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0'
ts() { date +%s.%N; }
cx() { docker exec -e ROS_DOMAIN_ID=0 "$C" bash -lc "$AW_ENV && $1" 2>&1; }

for i in 1 2; do
  echo "################ SMOKE ITERATION $i [t=$(ts)]"
  docker rm -f "$C" >/dev/null 2>&1 || true
  docker run -d --name "$C" --gpus all --net=host --ipc=host -e ROS_DOMAIN_ID=0 \
    -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    -e FASTRTPS_DEFAULT_PROFILES_FILE=/dds-profile.xml -v "$UDP_ONLY:/dds-profile.xml:ro" \
    -v "$MAP_HOST:$MAP_DIR:ro" -v "$POSE_INIT:$POSE_TGT:ro" \
    -v "$REPO:/work:ro" \
    "$IMAGE" sleep infinity >/dev/null || { echo "FAILED to start $C"; exit 1; }

  cx "nohup ros2 launch autoware_launch e2e_simulator.launch.xml \
      map_path:=$MAP_DIR sensor_model:=awsim_labs_sensor_kit \
      vehicle_model:=sample_vehicle simulator_type:=awsim \
      launch_vehicle_interface:=false use_sim_time:=false \
      perception:=false rviz:=false >/tmp/replica.log 2>&1 &" >/dev/null

  d=$((SECONDS + 180))
  until cx "grep -q 'Succeeded to load lanelet2_map' /tmp/replica.log" >/dev/null 2>&1; do
    [ "$SECONDS" -lt "$d" ] || { echo "TIMEOUT: map never loaded"; break; }
    sleep 3
  done
  echo "--- publish marker ---"
  cx "grep 'Succeeded to load lanelet2_map' /tmp/replica.log"

  echo "--- settle 40s, then run the REAL helper exactly as the launcher calls it ---"
  sleep 40
  cx "mkdir -p /out"
  cx "python3 /work/benchmarks/injector/republish_vector_map.py \
      --settle-s 5 --capture-timeout-s 90 --match-timeout-s 60 \
      --verify-timeout-s 60 --attempts 3 --report /out/vector-map-delivery.json"
  echo "--- helper exit=$? ---"
  echo "--- report ---"
  cx "cat /out/vector-map-delivery.json"
  echo "--- publishers on the topic after the re-publish ---"
  cx "ros2 topic info --no-daemon /map/vector_map"
  docker rm -f "$C" >/dev/null 2>&1 || true
  sleep 10
done
echo "=== smoke done at t=$(ts) ==="
