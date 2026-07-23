#!/usr/bin/env bash
# Phase B M4-blocker #4: launch the Autoware e2e_simulator stack in the correct order.
#
# `simulator_type:=carla` pulls in autoware_carla_interface, whose main() calls
# client.load_world(carla_map) at startup (carla_autoware.py:226) -- a full world RELOAD
# that WIPES every actor, including a runner-spawned ego. In this native-DDS setup that
# node then fire-and-dies (it also tries to spawn its OWN prius ego + run a bridge loop,
# which the native path neither needs nor tolerates). The report's clean fix is ordering:
# bring Autoware (and thus that one-shot load_world) up FIRST, while the CARLA world is
# still ego-less, and let the runner spawn the ego ONLY AFTER carla_interface has fired
# and exited. This script encodes that: it launches Autoware and BLOCKS until the stack is
# up AND /autoware_carla_interface is gone from the node graph -- i.e. its load_world has
# fired and can no longer wipe an ego. run_phase_b.sh (WITH_AUTOWARE=1) calls this between
# bringing CARLA up and running the spawn+tick runner.
#
# NOT exercised live yet (same status as run_phase_b.sh): the full E2E campaign waits on a
# fresh carla-unreal-editor rebuild + GPU + this stack. This script is verified by `bash -n`
# + shellcheck + review; it fails loudly (named preflight checks, run_g0.sh style) rather
# than proceeding on a half-up stack.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"

# The Autoware container runs on DDS domain 0; the login shell exports 123 (CLAUDE.md).
export ROS_DOMAIN_ID=0

AW_LOG=/tmp/phase-b-autoware.log            # container-side launch log
AW_PIDFILE=/tmp/phase-b-autoware.cpid       # container-side ros2-launch PID (for --stop)
CARLA_INTERFACE_NODE="/autoware_carla_interface"
READY_NODE_THRESHOLD=50                     # Autoware e2e brings up ~170 nodes; 50 = "core up"
READY_TIMEOUT_S=240                         # bounded; a slow cold container can take minutes

# AW_LOG / AW_PIDFILE are CONTAINER-side paths; pass them (and the domain) in via -e so the
# single-quoted container scripts below expand them in the container -- no host-string
# injection, which is fragile and reads as a shellcheck SC2016 false positive.
compose_exec() {
  docker compose -f "$COMPOSE" exec -T \
    -e ROS_DOMAIN_ID=0 -e AW_LOG="$AW_LOG" -e AW_PIDFILE="$AW_PIDFILE" \
    autoware bash -lc "$1"
}

# --stop: tear the launch down (kill the recorded container-side ros2-launch PID). Uses the
# PID file, NEVER pkill -f, which self-matches the exec's own command line (project gotcha).
if [ "${1:-}" = "--stop" ]; then
  # $AW_PIDFILE/$pid are expanded IN THE CONTAINER (compose_exec passes -e AW_PIDFILE); the
  # single quotes are deliberate so the host does not expand them first.
  # shellcheck disable=SC2016
  compose_exec '
    if [ -f "$AW_PIDFILE" ]; then
      pid="$(cat "$AW_PIDFILE")"
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
      fi
      rm -f "$AW_PIDFILE"
    fi
    echo "autoware launch stopped"'
  exit 0
fi

# Preflight 1: container up.
docker inspect -f '{{.State.Running}}' autoware 2>/dev/null | grep -q true \
  || { echo "PREFLIGHT FAIL: container 'autoware' not running (docker compose up -d)"; exit 1; }

# Preflight 2: the map is mounted (map_path the launch needs).
compose_exec 'test -f /autoware_map/nishishinjuku/lanelet2_map.osm' \
  || { echo "PREFLIGHT FAIL: /autoware_map/nishishinjuku not mounted (see docker/compose.yaml)"; exit 1; }

# Preflight 3: CARLA RPC port must already be bound -- carla_interface connects to :2000 at
# startup, so CARLA has to be up FIRST (that is the whole point of the ordering). This is why
# run_phase_b.sh boots CARLA before calling this script.
if ! (ss -ltn 2>/dev/null | grep -q ':2000[[:space:]]'); then
  echo "PREFLIGHT FAIL: CARLA RPC port 2000 is not bound. Bring CARLA up BEFORE Autoware so" >&2
  echo "  autoware_carla_interface can connect and fire its one-shot load_world on the" >&2
  echo "  ego-less world (M4-blocker #4 ordering). run_phase_b.sh WITH_AUTOWARE=1 does this." >&2
  exit 1
fi

# Launch e2e_simulator in the background INSIDE the container and record its PID. Verbatim
# report launch line: perception:=false is a stock-image workaround (ground-segmentation
# resolves a CUDA-only package eagerly, and no DNN model artifacts ship) -- localization does
# NOT depend on perception, so G1/G2 are unaffected. launch_vehicle_interface:=false because
# the extension IS the vehicle interface (native Ackermann/status over DDS).
echo "OK: bringing Autoware up (e2e_simulator, simulator_type:=carla) -- log: $AW_LOG"
# $AW_LOG/$AW_PIDFILE/$! are expanded IN THE CONTAINER (compose_exec passes them via -e; $!
# must be the container-side nohup PID), so the single quotes below are intentional.
# shellcheck disable=SC2016
compose_exec '
  source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash &&
  source ~/carla_msgs_ws/install/setup.bash 2>/dev/null || true
  export ROS_DOMAIN_ID=0
  nohup ros2 launch autoware_launch e2e_simulator.launch.xml \
    map_path:=/autoware_map/nishishinjuku \
    sensor_model:=awsim_labs_sensor_kit vehicle_model:=sample_vehicle \
    simulator_type:=carla launch_vehicle_interface:=false use_sim_time:=true \
    perception:=false rviz:=false >"$AW_LOG" 2>&1 &
  echo $! >"$AW_PIDFILE"
  echo "autoware launch pid $(cat "$AW_PIDFILE")"'

# Block until the stack is up AND carla_interface has fired-and-died. Two conditions,
# BOTH required, observed on two consecutive polls so a transient list read cannot pass us:
#   (a) node count >= READY_NODE_THRESHOLD  -> the core stack is up (we started AFTER t0), and
#   (b) /autoware_carla_interface ABSENT    -> its startup load_world has fired and it exited,
#                                              so it can no longer reload the world under the ego.
# Checking (a) first rules out the t=0 false positive where the node is trivially absent
# because nothing has launched yet.
echo "OK: waiting for Autoware to settle and $CARLA_INTERFACE_NODE to fire-and-die (<= ${READY_TIMEOUT_S}s)"
elapsed=0
consecutive_ready=0
while [ "$elapsed" -lt "$READY_TIMEOUT_S" ]; do
  nodes="$(compose_exec 'source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=0; ros2 node list 2>/dev/null' || true)"
  count="$(printf '%s\n' "$nodes" | grep -c '^/' || true)"
  if [ "$count" -ge "$READY_NODE_THRESHOLD" ] && ! printf '%s\n' "$nodes" | grep -qx "$CARLA_INTERFACE_NODE"; then
    consecutive_ready=$((consecutive_ready + 1))
    if [ "$consecutive_ready" -ge 2 ]; then
      echo "OK: Autoware up ($count nodes); $CARLA_INTERFACE_NODE has fired-and-died -- safe to spawn the native ego"
      exit 0
    fi
  else
    consecutive_ready=0
  fi
  sleep 3
  elapsed=$((elapsed + 3))
done

echo "PREFLIGHT FAIL: Autoware did not reach a safe-to-spawn state within ${READY_TIMEOUT_S}s" >&2
echo "  (need >= ${READY_NODE_THRESHOLD} nodes AND ${CARLA_INTERFACE_NODE} absent). See $AW_LOG." >&2
echo "  Do NOT spawn the ego yet: carla_interface may still reload the world and wipe it." >&2
exit 1
