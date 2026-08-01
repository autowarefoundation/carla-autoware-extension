#!/usr/bin/env bash
# Cell-B `waiting for map` live diagnostic prober (IN-RUN phase).
#
# Runs against the `autoware` container benchmarks/cells/tier4_autoware.sh
# creates. Read-only with respect to the harness and the run directory: it only
# execs probe processes into the (ephemeral) container. Every command is echoed
# before it runs so the capture is self-describing.
#
# BUDGET: on cell B's static arm the Autoware stack lives ~100 s wall
# (measured: B/run-028 99.9 s, B/run-029 102.8 s of launch-log span), so this
# script is ordered decisive-probe-first and keeps the whole sequence under
# ~85 s. Anything that does not fit is repeated at leisure on the standalone
# replica bench, which has no such budget.
set -u

SCRATCH="$(cd "$(dirname "$0")" && pwd)"
C=autoware
AW_ENV='source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0'

ts() { date +%s.%N; }

run() { # run <label> <shell-command-inside-container>
  echo
  echo "########## $1  [t=$(ts)]"
  echo "\$ docker exec -e ROS_DOMAIN_ID=0 $C bash -lc '<AW_ENV> && $2'"
  timeout 180 docker exec -e ROS_DOMAIN_ID=0 "$C" bash -lc "$AW_ENV && $2" 2>&1
  echo "########## exit=$?  [t=$(ts)]"
}

run_env() { # run_env <label> <cmd> <extra -e args>
  echo
  echo "########## $1  [t=$(ts)]"
  echo "\$ docker exec -e ROS_DOMAIN_ID=0 $3 $C bash -lc '<AW_ENV> && $2'"
  # shellcheck disable=SC2086 # $3 is a deliberate word-split arg list
  timeout 180 docker exec -e ROS_DOMAIN_ID=0 $3 "$C" bash -lc "$AW_ENV && $2" 2>&1
  echo "########## exit=$?  [t=$(ts)]"
}

echo "=== waiting for container $C ==="
until docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null | grep -q true; do sleep 2; done
echo "container up at t=$(ts)"

docker cp "$SCRATCH/map_probe.py" "$C:/tmp/map_probe.py" >/dev/null
docker cp "$SCRATCH/diag_probe.py" "$C:/tmp/diag_probe.py" >/dev/null
docker cp "$SCRATCH/udp_big.xml" "$C:/tmp/udp_big.xml" >/dev/null
echo "probe assets copied at t=$(ts)"

echo "=== waiting for /map/vector_map in the graph (max 600s) ==="
deadline=$((SECONDS + 600))
until timeout 30 docker exec -e ROS_DOMAIN_ID=0 "$C" bash -lc \
  "$AW_ENV && ros2 topic list --no-daemon 2>/dev/null | grep -qx /map/vector_map"; do
  [ "$SECONDS" -lt "$deadline" ] || { echo "TIMEOUT waiting for the topic"; break; }
  sleep 2
done
echo "topic present (or timed out) at t=$(ts)"

# The message type is resolved off the live graph rather than assumed.
# shellcheck disable=SC2016 # $VT/$PT expand IN the container, on purpose
TY='VT=$(ros2 topic list -t --no-daemon | awk "/^\\/map\\/vector_map /{gsub(/[][]/,\"\",\$2); print \$2}");
    PT=$(ros2 topic list -t --no-daemon | awk "/^\\/map\\/map_projector_info /{gsub(/[][]/,\"\",\$2); print \$2}");
    echo "resolved types: vector_map=$VT map_projector_info=$PT"'

# --- Q1 (operator probe 1): who advertises it, with what QoS --------------
run "Q1 topic info -v /map/vector_map" \
  "ros2 topic info -v --no-daemon /map/vector_map"

# --- Q3 (operator probe 3): what the planner subscribes to, with what QoS --
run "Q3 node info behavior_path_planner" \
  "ros2 node info --no-daemon /planning/scenario_planning/lane_driving/behavior_planning/behavior_path_planner"

# --- Q2/DECISIVE: late-joining subscriber with the planner's own QoS ------
run "Q2a late transient_local+reliable subscriber -> /map/vector_map (40s), STOCK udp_only profile" \
  "$TY; python3 /tmp/map_probe.py /map/vector_map \$VT transient_local 40"

# --- DECISIVE CONTROL: identical probe, larger UDP socket buffers ---------
run_env "Q2b same probe, 16MiB UDP socket buffers (40s)" \
  "$TY; python3 /tmp/map_probe.py /map/vector_map \$VT transient_local 40" \
  "-e FASTRTPS_DEFAULT_PROFILES_FILE=/tmp/udp_big.xml"

# --- SIZE CONTROL: a small transient_local topic from the same launch -----
run "Q4 late transient_local subscriber -> /map/map_projector_info (SMALL, 15s)" \
  "$TY; python3 /tmp/map_probe.py /map/map_projector_info \$PT transient_local 15"

# --- everything below is best-effort; the replica bench repeats it --------
run "Q5 component_state_monitor live verdict on the map topics (15s)" \
  "python3 /tmp/diag_probe.py 15"
run "Q6 transport env + profile actually in force" \
  "printenv RMW_IMPLEMENTATION FASTRTPS_DEFAULT_PROFILES_FILE; echo '--- /dds-profile.xml ---'; cat /dds-profile.xml"
run "Q7 topic info -v /map/map_projector_info and /map/pointcloud_map" \
  "ros2 topic info -v --no-daemon /map/map_projector_info; echo ---; ros2 topic info -v --no-daemon /map/pointcloud_map"
run "Q8 late VOLATILE subscriber -> /map/vector_map (10s, durability contrast)" \
  "$TY; python3 /tmp/map_probe.py /map/vector_map \$VT volatile 10"
run "Q9 ros2 topic echo --once, transient_local+reliable (30s)" \
  "timeout 30 ros2 topic echo --once --no-daemon --no-arr --qos-durability transient_local --qos-reliability reliable /map/vector_map; echo rc=\$?"
run "Q10 ros2 topic echo --once, DEFAULT qos (20s)" \
  "timeout 20 ros2 topic echo --once --no-daemon --no-arr /map/vector_map; echo rc=\$?"
run "Q11 live launch-log map/waiting lines" \
  "grep -n 'waiting for\\|Succeeded to load lanelet2_map\\|topic_rate_check/vector_map' /tmp/tier4-autoware.log 2>/dev/null | tail -40"

echo
echo "=== in-run prober done at t=$(ts) ==="
