#!/usr/bin/env bash
# Cell launcher: approach `extension` (cells A, A-hf, C). Wraps the recipe
# that already exists and is live-gated --
# scripts/e2e/run_e2e.sh with WITH_AUTOWARE=1 -- parameterised by the cell.
#
#   bash benchmarks/cells/extension.sh plan   # resolve + validate, no boot
#   bash benchmarks/cells/extension.sh up     # plan, then boot + wait ready
#
# `plan` exists so `run.sh --dry-run` exercises the SAME resolution and the
# SAME prerequisite checks a real run does (interpreter, .so, route file,
# ports), and so a missing prerequisite is reported before anything boots.
# Both write $BENCH_LAUNCH_ENV, the shell-sourceable handoff run.sh reads for
# steps 7-9 and teardown.sh reads for step 11.
#
# Inputs are the BENCH_* environment run.sh exports; see run.sh's "launcher
# contract" comment for the full list.
set -euo pipefail

: "${BENCH_REPO:?}" "${BENCH_CELL:?}" "${BENCH_MAP:?}" "${BENCH_ARM:?}"
: "${BENCH_RUN_DIR:?}" "${BENCH_LAUNCH_ENV:?}" "${BENCH_RPC_PORT:?}"
: "${BENCH_ROUTE_FILE:?}" "${BENCH_CARLA_TREE:?}"

MODE="${1:?usage: extension.sh plan|up}"

EXT_SO="$BENCH_REPO/extension/build/libcarla-autoware-extension.so"
COMPOSE="$BENCH_REPO/docker/compose.yaml"
AW_CONTAINER=autoware
LAUNCH_LOG="$BENCH_RUN_DIR/launch.log"
CARLA_PID_FILE="$BENCH_RUN_DIR/run_e2e.pid"
READY_TIMEOUT_S=420

fail() { echo "LAUNCH FAIL (extension/$BENCH_CELL): $*" >&2; exit 2; }

# --------------------------------------------------------------------------
# plan: everything that can be wrong before a single process starts.
# --------------------------------------------------------------------------

# run_e2e.sh hardcodes RPC port 2000 (both the editor invocation and its own
# port_bound() probe). Rather than boot on 2000 while the manifest, preflight
# and collect_gt all believe another port -- a silent disagreement -- refuse
# the combination and name the file that would have to change.
[ "$BENCH_RPC_PORT" = "2000" ] ||
  fail "extension cells run on RPC port 2000: scripts/e2e/run_e2e.sh hardcodes it
  (editor invocation + port_bound()). Parameterise run_e2e.sh before using
  --rpc-port $BENCH_RPC_PORT here."

[ -f "$EXT_SO" ] ||
  fail "extension .so missing: $EXT_SO (build extension/ first)"
[ -d "$BENCH_CARLA_TREE" ] ||
  fail "extension CARLA fork tree missing: $BENCH_CARLA_TREE (pins.yaml extension_carla_fork.path)"
[ -f "$BENCH_ROUTE_FILE" ] ||
  fail "route file missing: $BENCH_ROUTE_FILE"
[ -f "$COMPOSE" ] || fail "compose file missing: $COMPOSE"
# The campaign-wide pose_initializer override this family mounts through
# $COMPOSE. Checked as a FILE here rather than trusted, because `docker
# compose` on a missing host path silently creates a DIRECTORY at the
# container target: the stack would then read the image's own copy (or fail on
# a directory) while the mount appears to be in place. Same check, same
# reason, in cells/tier4_autoware.sh and cells/python-bridge.sh -- the two
# families that build their own `docker run` -v list.
[ -f "$BENCH_REPO/benchmarks/config/autoware/pose_initializer.param.yaml" ] ||
  fail "the campaign-wide pose_initializer override is missing:
  $BENCH_REPO/benchmarks/config/autoware/pose_initializer.param.yaml
  It is a committed file, mounted identically by docker/compose.yaml (this
  family), cells/tier4_autoware.sh and cells/python-bridge.sh; restore it
  rather than dropping the mount, which would put this family on a different
  Autoware configuration than the cells it is compared against."

# The GT client must be the interpreter whose `carla` module matches the
# server this cell boots -- the extension fork's own 0.10 build. Checked by
# IMPORTING it, not by assuming a path exists: a venv without the module
# would otherwise fail at step 7, after CARLA has been booted.
GT_PYTHON="${BENCH_GT_PYTHON:-$HOME/carla-venv/bin/python3}"
[ -x "$GT_PYTHON" ] ||
  fail "GT interpreter not executable: $GT_PYTHON (set BENCH_GT_PYTHON)"
"$GT_PYTHON" -c "import carla" >/dev/null 2>&1 ||
  fail "GT interpreter $GT_PYTHON cannot import carla (set BENCH_GT_PYTHON to
  an interpreter with the extension fork's 0.10 client wheel installed)"

# Sweep classes are runner launch parameters and the runner does not accept
# them yet (Task 12). Named, not silently ignored: a sweep run that quietly
# used the default LiDAR would be filed as a 128ch measurement.
if [ -n "${BENCH_CLASS_ID:-}" ] && [ -z "${BENCH_RUNNER_SWEEP_ARGS:-}" ]; then
  fail "--class $BENCH_CLASS_ID needs the runner sweep parameters from Task 12
  (extension runner sweep/camera/substep parameters), which are not written
  yet. Supply BENCH_RUNNER_SWEEP_ARGS explicitly to override."
fi

# Spawn pose comes from the committed route file, so the cell starts where
# the route was scored. run_e2e.sh takes it through RUNNER_EXTRA_ARGS
# (--initial-pose x y z roll pitch yaw_deg, CARLA frame).
SPAWN_ARGS="$(BENCH_ROUTE_FILE="$BENCH_ROUTE_FILE" python3 - <<'PY'
import os

import yaml

route = yaml.safe_load(open(os.environ["BENCH_ROUTE_FILE"]))
pose = route.get("spawn_pose")
index = route.get("spawn_index")
if index is not None:
    print(f"--spawn-index {int(index)}")
elif pose:
    print(f"--initial-pose {pose['x']} {pose['y']} {pose['z']} 0 0 {pose['yaw_deg']}")
else:
    raise SystemExit("route file has neither spawn_index nor spawn_pose")
PY
)" || fail "could not derive the spawn pose from $BENCH_ROUTE_FILE"

cat >"$BENCH_LAUNCH_ENV" <<EOF
# Written by benchmarks/cells/extension.sh ($MODE) -- sourced by run.sh and
# teardown.sh. Every value is resolved, never re-derived downstream.
LAUNCH_CELL="$BENCH_CELL"
APPROACH="extension"
LAUNCH_MAP="$BENCH_MAP"
LAUNCH_ARM="$BENCH_ARM"
RUN_MODE="editor-game"
CARLA_TREE="$BENCH_CARLA_TREE"
CARLA_RPC_PORT="$BENCH_RPC_PORT"
CARLA_PID_FILE="$CARLA_PID_FILE"
LAUNCH_LOG="$LAUNCH_LOG"
AW_CONTAINER="$AW_CONTAINER"
AW_EXEC="docker exec -e ROS_DOMAIN_ID=0 $AW_CONTAINER"
AW_SETUP="source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0"
AW_COMPOSE="$COMPOSE"
GT_ENABLED="1"
GT_CMD="env PYTHONPATH=$BENCH_REPO $GT_PYTHON -m benchmarks.scripts.collect_gt"
GT_OUT_DIR="$BENCH_RUN_DIR"
GT_COUNT_LIDAR="1"
INJECTOR_ENABLED="1"
ARM_ENABLED="1"
EXTRA_CONTAINERS=""
SPAWN_ARGS="$SPAWN_ARGS"
EOF

if [ "$MODE" = "plan" ]; then exit 0; fi
[ "$MODE" = "up" ] || fail "unknown mode $MODE (expected plan|up)"

# --------------------------------------------------------------------------
# up: boot the stack, then wait for OUR OWN readiness definition.
# --------------------------------------------------------------------------
mkdir -p "$BENCH_RUN_DIR"

# The Autoware container must exist before run_e2e.sh's launch_autoware.sh
# step; `up -d` is idempotent when it is already running.
docker compose -f "$COMPOSE" up -d "$AW_CONTAINER" >/dev/null

# run_e2e.sh enforces the load-bearing CARLA -> Autoware -> ego order and
# owns the CARLA teardown on every exit path via its own PID file, so it is
# launched as ONE background process and killed as one at teardown. It runs
# the spawn+tick runner in the foreground and therefore never returns; the
# readiness probe below, not its exit status, is what "up" waits on.
#
# ROS_DOMAIN_ID=0 is passed explicitly even though run_e2e.sh:79 exports it
# itself: this launcher's guarantee should not depend on a line in a script
# in another directory, and the failure it prevents is silent (a login shell
# exporting ROS_DOMAIN_ID=123 -- as this host's does, ~/.zshrc:126 -- puts
# CARLA on a different DDS domain than the container and no topic is ever
# discovered; Task 9's matrix row 7). Same pin as cells/tier4-native.sh.
(
  cd "$BENCH_REPO"
  MAP="$BENCH_MAP" \
  WITH_AUTOWARE=1 \
  ROS_DOMAIN_ID=0 \
  ROUTE_FILE="$BENCH_ROUTE_FILE" \
  CARLA_ROOT="$BENCH_CARLA_TREE" \
  CARLA_UNREAL_ENGINE_PATH="${CARLA_UNREAL_ENGINE_PATH:-$HOME/src/UnrealEngine}" \
  RUNNER_EXTRA_ARGS="$SPAWN_ARGS ${BENCH_RUNNER_SWEEP_ARGS:-}" \
    nohup bash scripts/e2e/run_e2e.sh >"$LAUNCH_LOG" 2>&1 &
  echo $! >"$CARLA_PID_FILE"
)

# Readiness = the thing every later step actually needs: a CARLA the GT
# client can reach, with the ego spawned. Probing that directly (rather than
# grepping the log for a phrase) means a bring-up that "looks" fine but has
# no ego fails here, not silently at step 7.
echo "waiting up to ${READY_TIMEOUT_S}s for CARLA + ego (log: $LAUNCH_LOG)"
deadline=$((SECONDS + READY_TIMEOUT_S))
until PYTHONPATH="$BENCH_REPO" "$GT_PYTHON" - "$BENCH_RPC_PORT" >/dev/null 2>&1 <<'PY'
import sys

import carla

from scripts.e2e.collect_gt import find_ego

client = carla.Client("localhost", int(sys.argv[1]))
client.set_timeout(5.0)
world = client.get_world()
world.wait_for_tick()
find_ego(world, attempts=1, delay_s=0.0)
sys.exit(0)
PY
do
  if [ "$SECONDS" -ge "$deadline" ]; then
    fail "CARLA/ego not ready within ${READY_TIMEOUT_S}s (see $LAUNCH_LOG)"
  fi
  if ! kill -0 "$(cat "$CARLA_PID_FILE")" 2>/dev/null; then
    fail "run_e2e.sh exited during bring-up (see $LAUNCH_LOG)"
  fi
  sleep 5
done
echo "OK: CARLA up on port $BENCH_RPC_PORT with a spawned ego"
