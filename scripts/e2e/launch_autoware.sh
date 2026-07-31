#!/usr/bin/env bash
# Launch the Autoware e2e_simulator stack in the correct order (blocker #4,
# docs/e2e-report.md).
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
# fired and can no longer wipe an ego. run_e2e.sh (WITH_AUTOWARE=1) calls this between
# bringing CARLA up and running the spawn+tick runner. Fails loudly (named preflight
# checks, run_g0.sh style) rather than proceeding on a half-up stack.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"

# The Autoware container runs on DDS domain 0; pin it so a login-shell override cannot leak.
export ROS_DOMAIN_ID=0

AW_LOG=/tmp/e2e-autoware.log            # container-side launch log
AW_PIDFILE=/tmp/e2e-autoware.cpid       # container-side ros2-launch PID (for --stop)
RELAY_PIDFILE=/tmp/e2e-concat-relay.cpid  # container-side single-LiDAR relay PID
CARLA_INTERFACE_NODE="/autoware_carla_interface"
# The e2e stack settles at ~168 nodes. Wait for it to be NEARLY complete (>= 150) AND stable
# before declaring ready: a too-eager threshold (e.g. 50) lets the runner spawn + the relay
# start while the sensing composable nodes (crop_box/distortion/ring) are still loading, and
# the DDS discovery churn from that has been observed to make some of those loads silently
# fail (empty pointcloud_container -> dead per-LiDAR chain). Requiring a high, settled count
# lets sensing finish loading first.
READY_NODE_THRESHOLD=150
READY_TIMEOUT_S=300                         # bounded; a slow cold container can take minutes

# Single-LiDAR concatenation (blocker #2, docs/e2e-report.md): the awsim_labs concatenate node
# (PointCloudConcatenateDataSynchronizerComponent) HARD-REQUIRES >= 2 input topics -- with one
# it throws "Only one topic given. Need at least two topics to continue." and never loads. This
# rig has ONE top LiDAR, so instead of concatenating we RELAY the single per-LiDAR
# cloud straight to the concatenated topic the localization chain consumes. This is
# frame-correct: /sensing/lidar/top/pointcloud_before_sync is already in base_link (the concat
# node's own output_frame), so the relay needs no transform. (The concat node is left with its
# stock 3-topic config; it stays silent with a single publisher, so the relay
# is the sole publisher on the concatenated topic -- verified live after bring-up.)
RELAY_IN=/sensing/lidar/top/pointcloud_before_sync
RELAY_OUT=/sensing/lidar/concatenated/pointcloud

# CONTAINER-side path of the Autoware map bundle (pcd + lanelet2 + projector info) this launch
# localizes against; it becomes the launch's map_path:=. Each bundle needs a matching read-only
# mount in docker/compose.yaml.
#
# DERIVED from CARLA_AUTOWARE_MAP -- the one variable the operator already exports for the gates
# -- through the shared table, exactly as arm_closed_loop.sh does. run_e2e.sh exports MAP_DIR
# before calling this script, so on the harness path nothing changes. The derivation is for the
# OTHER path: this script is a documented standalone entry point (--stop; docs/running-e2e.md
# shows a hand-run bring-up), and a hard-coded Nishi default meant a manual Town10 bring-up
# localized against Nishi's pointcloud SILENTLY -- it surfaces only as NDT never converging.
# Unset still selects Nishi-Shinjuku, so every argument-free historical invocation is unchanged.
MAP_NAME="${CARLA_AUTOWARE_MAP:-NishishinjukuMap}"
# The linter runs without -x in pre-commit and so cannot follow the source even with the
# directive below; SC1091 is informational and disabled for that reason.
# shellcheck source=scripts/e2e/map_defaults.sh disable=SC1091
. "$HERE/map_defaults.sh"
carla_autoware_map_defaults "$MAP_NAME"
MAP_DIR="${MAP_DIR:-$MAP_DEFAULT_DIR}"
# An unknown map leaves MAP_DIR empty; that is fatal for a launch but NOT for --stop, which only
# kills recorded PIDs, so the loud failure lives below the --stop branch as preflight 0.

# Container-side paths passed in via -e so the single-quoted container scripts below expand
# them in the container -- no host-string injection (fragile + a shellcheck SC2016 false
# positive).
compose_exec() {
  docker compose -f "$COMPOSE" exec -T \
    -e ROS_DOMAIN_ID=0 -e AW_LOG="$AW_LOG" -e AW_PIDFILE="$AW_PIDFILE" \
    -e RELAY_PIDFILE="$RELAY_PIDFILE" -e RELAY_IN="$RELAY_IN" -e RELAY_OUT="$RELAY_OUT" \
    -e MAP_DIR="$MAP_DIR" \
    autoware bash -lc "$1"
}

# Run a HOST script inside the container by piping it in on stdin
# (`bash -s --`), so no bind mount has to exist for it to work.
# docker/compose.yaml does mount ../scripts read-only at /work/scripts, but
# --stop is the one path that must still work against a container started
# from an older compose file, and a teardown that could not find its own
# helper would silently leave the stack up -- the very failure this replaces.
compose_exec_script() {
  local script="$1"
  shift
  docker compose -f "$COMPOSE" exec -T -e ROS_DOMAIN_ID=0 \
    autoware bash -s -- "$@" <"$script"
}

# --stop: tear the launch down. Uses the recorded container-side PIDs, NEVER
# pkill -f, which self-matches the exec's own command line (project gotcha).
#
# MEASURED DEFECT this now fixes (Task 15, 2026-07-30). The previous form
# SIGTERMed the recorded `ros2 launch` PID, waited 20 s, SIGKILLed it, and
# printed "autoware launch + concat relay stopped" unconditionally. It did
# NOT stop the stack. Ten minutes after such a teardown, with CARLA gone and
# port 2000 free: `ros2 node list --no-daemon` -> 169 nodes, container
# `ps -e` -> 74 processes, /proc/loadavg -> 42.16 26.66 13.45 (they spin hard
# because /clock no longer advances). `docker compose down` cleared it and the
# host settled to 2.44.
#
# ROOT CAUSE, measured 2026-07-31 against a real `ros2 launch` started by
# THIS script's own `nohup ... &` pattern -- and it is worse than "launch
# orphans on SIGTERM". That launch has SigIgn 0x1001007 (SIGHUP, SIGINT and
# SIGQUIT all ignored, because a shell without job control sets exactly those
# to SIG_IGN for a background job, and SIG_IGN survives exec) and SigCgt with
# NO signal 1-31 caught, so launch's own handlers never install. SIGINT is a
# verified no-op; SIGTERM kills it by default action with no launch code
# running at all -- not even launch_service.py's own "using SIGTERM ... can
# result in orphaned processes" warning appears -- and its children keep
# running. No signal sent to the recorded PID can both reach it and take its
# children with it.
#
# So stop_launch_tree.sh signals the CHILDREN: it snapshots the recorded PID's
# own descendants BEFORE the first signal and escalates
# SIGINT -> SIGINT -> SIGTERM -> SIGKILL over that set and nothing wider. It
# never refuses and never exits non-zero -- a teardown that blocks a
# legitimate measurement is worse than one that under-reports -- and it prints
# the container's post-stop running/defunct counts, so this is a reported
# observation rather than an unconditional claim. See that file's header for
# the full measurement, for the launch-side change deliberately NOT made here,
# and for the one case it cannot claim (processes already orphaned by an
# earlier SIGTERM-only stop).
if [ "${1:-}" = "--stop" ]; then
  compose_exec_script "$HERE/stop_launch_tree.sh" "$RELAY_PIDFILE" "$AW_PIDFILE"
  exit 0
fi

# Preflight 0: the map name resolved to a bundle. Fails loudly rather than launching against
# another map's pointcloud (same failure mode, and same message shape, as arm_closed_loop.sh).
if [ -z "$MAP_DIR" ]; then
  echo "PREFLIGHT FAIL: CARLA_AUTOWARE_MAP=$MAP_NAME has no known Autoware bundle;" >&2
  echo "  set MAP_DIR to its container path (see scripts/e2e/map_defaults.sh)." >&2
  exit 1
fi

# Preflight 1: container up.
docker inspect -f '{{.State.Running}}' autoware 2>/dev/null | grep -q true \
  || { echo "PREFLIGHT FAIL: container 'autoware' not running (docker compose up -d)"; exit 1; }

# Preflight 2: the map bundle is mounted (map_path the launch needs). $MAP_DIR expands IN THE
# CONTAINER (compose_exec passes it via -e), so the single quotes are intentional.
# shellcheck disable=SC2016
compose_exec 'test -f "$MAP_DIR/lanelet2_map.osm"' \
  || { echo "PREFLIGHT FAIL: $MAP_DIR not mounted (see docker/compose.yaml)"; exit 1; }

# Preflight 3: CARLA RPC port must already be bound -- carla_interface connects to :2000 at
# startup, so CARLA has to be up FIRST (that is the whole point of the ordering). This is why
# run_e2e.sh boots CARLA before calling this script.
# Captured into a variable, not piped to `grep -q`: under `set -o pipefail`, grep -q closing
# its read end early can SIGPIPE-kill `ss` (exit 141) and flip the whole pipeline to "not
# bound" even though the port IS bound (the same hazard run_e2e.sh's port_bound documents).
listeners="$(ss -ltn 2>/dev/null)" || true
if ! [[ "$listeners" =~ :2000[[:space:]] ]]; then
  echo "PREFLIGHT FAIL: CARLA RPC port 2000 is not bound. Bring CARLA up BEFORE Autoware so" >&2
  echo "  autoware_carla_interface can connect and fire its one-shot load_world on the" >&2
  echo "  ego-less world (bring-up-order blocker #4). run_e2e.sh WITH_AUTOWARE=1 does this." >&2
  exit 1
fi

# Launch e2e_simulator in the background INSIDE the container and record its PID. Verbatim
# report launch line: perception:=false is a stock-image workaround (ground-segmentation
# resolves a CUDA-only package eagerly, and no DNN model artifacts ship) -- localization does
# NOT depend on perception, so G1/G2 are unaffected. launch_vehicle_interface:=false because
# the extension IS the vehicle interface (native Ackermann/status over DDS).
echo "OK: bringing Autoware up (e2e_simulator, simulator_type:=carla, map $MAP_NAME, bundle $MAP_DIR) -- log: $AW_LOG"
# $AW_LOG/$AW_PIDFILE/$MAP_DIR/$! are expanded IN THE CONTAINER (compose_exec passes them via -e;
# $! must be the container-side nohup PID), so the single quotes below are intentional.
# shellcheck disable=SC2016
compose_exec '
  source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash &&
  source ~/carla_msgs_ws/install/setup.bash 2>/dev/null || true
  export ROS_DOMAIN_ID=0
  nohup ros2 launch autoware_launch e2e_simulator.launch.xml \
    map_path:="$MAP_DIR" \
    sensor_model:=awsim_labs_sensor_kit vehicle_model:=sample_vehicle \
    simulator_type:=carla launch_vehicle_interface:=false use_sim_time:=true \
    perception:=false rviz:=false >"$AW_LOG" 2>&1 &
  echo $! >"$AW_PIDFILE"
  # Sidecar for stop_launch_tree.sh pid-reuse guard: the command line this pid
  # was recorded WITH. A pid names a process only until it exits, and --stop
  # KEEPS the pid file when it could not clear a tree, so a later --stop in a
  # long-lived container could otherwise sweep a strangers subtree. Best
  # effort: a missing sidecar only means the guard is skipped.
  tr "\0" " " </proc/$(cat "$AW_PIDFILE")/cmdline >"$AW_PIDFILE.cmd" 2>/dev/null || true
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
    if [ "$consecutive_ready" -ge 3 ]; then
      echo "OK: Autoware up ($count nodes); $CARLA_INTERFACE_NODE has fired-and-died -- safe to spawn the native ego"
      # Start the single-LiDAR concat relay (blocker #2). It subscribes to $RELAY_IN, which
      # does not exist until the runner spawns the LiDAR moments from now -- topic_tools relay
      # waits for the publisher and begins forwarding once it appears, so starting it here (ego
      # not yet up) is correct. Record its PID for --stop.
      echo "OK: starting single-LiDAR concat relay $RELAY_IN -> $RELAY_OUT"
      # $RELAY_* / $! expand IN THE CONTAINER (passed via -e); single quotes intentional.
      # shellcheck disable=SC2016
      compose_exec '
        source /opt/ros/humble/setup.bash 2>/dev/null; export ROS_DOMAIN_ID=0
        nohup ros2 run topic_tools relay "$RELAY_IN" "$RELAY_OUT" >/tmp/e2e-concat-relay.log 2>&1 &
        echo $! >"$RELAY_PIDFILE"
        tr "\0" " " </proc/$(cat "$RELAY_PIDFILE")/cmdline >"$RELAY_PIDFILE.cmd" 2>/dev/null || true
        echo "concat relay pid $(cat "$RELAY_PIDFILE")"'
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
