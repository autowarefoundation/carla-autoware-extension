#!/usr/bin/env bash
# G0 spike orchestration: boot the stacked CARLA build on CycloneDDS, spawn the
# spike sensor stack, then run interop_check.py inside the Autoware container.
# One-shot: cleans up the simulator and spawner on every exit path.
#
# Required environment:
#   CARLA_ROOT                CARLA source tree built from the reference branch
#                             (see docs/prerequisites.md)
#   CARLA_UNREAL_ENGINE_PATH  CARLA-fork Unreal Engine 5 tree
# Optional:
#   CARLA_VENV                virtualenv providing the matching `carla` wheel
set -euo pipefail

: "${CARLA_ROOT:?set CARLA_ROOT to the CARLA source tree (docs/prerequisites.md)}"
: "${CARLA_UNREAL_ENGINE_PATH:?set CARLA_UNREAL_ENGINE_PATH to the CARLA UE5 tree}"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG=/tmp/carla-g0.log
SPAWN_LOG=/tmp/carla-g0-spawner.log

export CYCLONEDDS_URI="file://$REPO/docker/cyclonedds.xml"
# The Autoware container runs on DDS domain 0 (ROS_DOMAIN_ID unset). A login
# shell that exports a nonzero ROS_DOMAIN_ID would otherwise leak into the
# CARLA process and put it on a different domain, so the container would never
# discover any topic. Pin CARLA to domain 0 to match the container.
export ROS_DOMAIN_ID=0

# Poll cheaply for whether TCP $1 is currently bound (LISTEN), via `ss`'s read
# of the kernel socket table. This only reads kernel state, so it still works
# while the process holding the port is unresponsive (e.g. stopped under
# apport/ptrace while it captures a core dump).
port_bound() {
  ss -ltn 2>/dev/null | grep -qE ":$1[[:space:]]"
}

# Bounded wait for pid $2 to release TCP port $1. A segfaulting UnrealEditor
# can sit under apport's core-dump capture for tens of seconds with the
# listening socket still bound; without this, a back-to-back invocation of
# this script would fail to bind the port and be misdiagnosed as a CARLA or
# DDS problem. Never blocks forever: after the first ceiling elapses we
# escalate to SIGKILL, then allow one more bounded window before giving up
# with a warning. Always returns 0 so it never perturbs cleanup()'s exit
# status (see below).
wait_for_port_release() {
  local port=$1 pid=$2 elapsed=0 ceiling=60
  while [ "$elapsed" -lt "$ceiling" ] && port_bound "$port"; do
    sleep 1
    elapsed=$((elapsed + 1))
  done
  if ! port_bound "$port"; then
    return 0
  fi

  echo "warning: port $port still held by pid $pid after ${ceiling}s; sending SIGKILL" >&2
  kill -9 "$pid" 2>/dev/null || true

  elapsed=0
  ceiling=15
  while [ "$elapsed" -lt "$ceiling" ] && port_bound "$port"; do
    sleep 1
    elapsed=$((elapsed + 1))
  done
  if port_bound "$port"; then
    echo "warning: port $port still held by pid $pid after SIGKILL; giving up" >&2
  fi
  return 0
}

# Clean up both child processes on any exit path. Both PIDs start empty and a
# single trap is installed up front, so the simulator is still killed even if
# the spawner never starts (e.g. the RPC port never comes up).
#
# The spawner (ros2_native.py) is killed and reaped before the simulator: it is
# mid-world.tick() when SIGTERM lands, so it always prints a
# RuntimeError/KeyboardInterrupt shutdown traceback. That's expected teardown
# noise, not a real failure, so its output is redirected to SPAWN_LOG (see
# above) instead of the terminal, and `wait` makes sure it has actually exited
# before the simulator goes down under it. After signalling the simulator, we
# also wait (bounded, see wait_for_port_release above) for it to actually
# release port 2000 before returning, so a follow-on invocation of this
# script never races a lingering apport core dump for the bind. This never
# touches the exit status: bash's EXIT trap runs after the script's exit code
# from interop_check.py (via the docker compose exec pipeline) is already
# latched, and `cleanup` never calls `exit` itself, so that status is what
# the script reports. wait_for_port_release always returns 0, and the `if`
# guarding it returns 0 whenever SIM_PID is empty, so cleanup()'s own exit
# status can't leak a failure and override the latched one.
SIM_PID=""
SPAWN_PID=""
cleanup() {
  if [ -n "$SPAWN_PID" ]; then
    kill "$SPAWN_PID" 2>/dev/null || true
    wait "$SPAWN_PID" 2>/dev/null || true
  fi
  if [ -n "$SIM_PID" ]; then
    kill "$SIM_PID" 2>/dev/null || true
    wait_for_port_release 2000 "$SIM_PID"
  fi
}
trap cleanup EXIT

"$CARLA_UNREAL_ENGINE_PATH/Engine/Binaries/Linux/UnrealEditor" \
  "$CARLA_ROOT/Unreal/CarlaUnreal/CarlaUnreal.uproject" \
  -game -RenderOffScreen -nosound --ros2 --rmw=cyclonedds >"$LOG" 2>&1 &
SIM_PID=$!

python3 - <<'EOF' # wait for the RPC port
import socket, time, sys
for _ in range(120):
    try:
        socket.create_connection(("localhost", 2000), 1).close(); sys.exit(0)
    except OSError: time.sleep(2)
sys.exit("CARLA RPC port never came up")
EOF

if [ -n "${CARLA_VENV:-}" ]; then
  # shellcheck disable=SC1091
  source "$CARLA_VENV/bin/activate"
fi
python3 "$CARLA_ROOT/PythonAPI/examples/ros2/ros2_native.py" -f "$REPO/scripts/spike_stack.json" \
  >"$SPAWN_LOG" 2>&1 &
SPAWN_PID=$!
sleep 20

(cd "$REPO/docker" && docker compose exec -T autoware bash -lc \
  'source /opt/ros/humble/setup.bash && \
   source /opt/autoware/setup.bash && \
   source ~/carla_msgs_ws/install/setup.bash && \
   python3 /work/scripts/interop_check.py \
     --topics /work/scripts/expected_topics.yaml --report-dir /work/reports')
