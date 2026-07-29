#!/usr/bin/env bash
# Cell launcher: approach `tier4-native` (cells B, B-hf, B45, D).
#
#   bash benchmarks/cells/tier4-native.sh plan   # resolve + validate, no boot
#   bash benchmarks/cells/tier4-native.sh up     # plan, then boot + wait ready
#
# The CARLA half is the exact invocation verified in
# benchmarks/patches/tier4-native/README.md ("Boot smoke"): the SHARED
# engine's UnrealEditor binary pointed at this tree's .uproject, in -game
# mode, with an explicitly pinned -carla-rpc-port.
#
# The AUTOWARE half is NOT written here. Task 13 ("tier4 demo harmonization
# patch + B closed-loop gate") owns the patched autoware_demo.py and the
# container launch that goes with it; nothing committed in this repo starts
# the tier4 stack today. `plan` therefore REFUSES rather than inventing a
# launch that would appear to work and produce a cell with no Autoware in it.
# BENCH_TIER4_DEMO is the hook Task 13 fills in.
set -euo pipefail

: "${BENCH_REPO:?}" "${BENCH_CELL:?}" "${BENCH_MAP:?}" "${BENCH_ARM:?}"
: "${BENCH_RUN_DIR:?}" "${BENCH_LAUNCH_ENV:?}" "${BENCH_RPC_PORT:?}"
: "${BENCH_CARLA_TREE:?}" "${BENCH_AUTOWARE_IMAGE:?}"

MODE="${1:?usage: tier4-native.sh plan|up}"

ENGINE_PATH="${CARLA_UNREAL_ENGINE_PATH:-$HOME/src/UnrealEngine}"
EDITOR="$ENGINE_PATH/Engine/Binaries/Linux/UnrealEditor"
UPROJECT="$BENCH_CARLA_TREE/Unreal/CarlaUnreal/CarlaUnreal.uproject"
AW_CONTAINER=autoware
LAUNCH_LOG="$BENCH_RUN_DIR/launch.log"
CARLA_PID_FILE="$BENCH_RUN_DIR/carla.pid"
READY_TIMEOUT_S=420

fail() { echo "LAUNCH FAIL (tier4-native/$BENCH_CELL): $*" >&2; exit 2; }

# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------
[ -x "$EDITOR" ] || fail "shared engine editor missing: $EDITOR (set CARLA_UNREAL_ENGINE_PATH)"
[ -f "$UPROJECT" ] || fail "tier4 fork uproject missing: $UPROJECT (pins.yaml tier4_carla_fork.path)"

# The GT client must match the SERVER this cell boots -- the tier4 fork's own
# 0.10 build. The tree's wheel is built for cp313 and this host's default
# interpreter is 3.12, so there is no ready-made venv: refuse with the exact
# recipe rather than silently falling back to the extension fork's client,
# which would put a different fork's client on B's numbers.
TIER4_WHEEL_DIR="$BENCH_CARLA_TREE/Build/PythonAPI/dist"
shopt -s nullglob
TIER4_WHEELS=("$TIER4_WHEEL_DIR"/carla-*.whl)
shopt -u nullglob
GT_PYTHON="${BENCH_GT_PYTHON:-$HOME/carla-tier4-venv/bin/python3}"
if [ ! -x "$GT_PYTHON" ] || ! "$GT_PYTHON" -c "import carla" >/dev/null 2>&1; then
  fail "no GT client matching the tier4 server. $GT_PYTHON cannot import carla.
  The tier4 tree ships ${TIER4_WHEELS[0]:-<no wheel built in $TIER4_WHEEL_DIR>},
  whose ABI tag needs its own interpreter. Create it once:
    ~/.local/bin/python3.13 -m venv ~/carla-tier4-venv
    ~/carla-tier4-venv/bin/pip install $TIER4_WHEEL_DIR/carla-*.whl
  or point BENCH_GT_PYTHON at an interpreter that already has it."
fi

# The Autoware half. Task 13 dependency, made loud on purpose.
TIER4_DEMO="${BENCH_TIER4_DEMO:-}"
if [ -z "$TIER4_DEMO" ]; then
  fail "the tier4 Autoware launch does not exist yet: Task 13 (tier4 demo
  harmonization patch + B closed-loop gate) owns the patched autoware_demo.py
  and the container launch. Set BENCH_TIER4_DEMO to the launch script once
  Task 13 lands. The CARLA half of this cell IS implemented below and can be
  booted independently for diagnostics."
fi
[ -x "$TIER4_DEMO" ] || [ -f "$TIER4_DEMO" ] ||
  fail "BENCH_TIER4_DEMO=$TIER4_DEMO is not a file"

if [ -n "${BENCH_CLASS_ID:-}" ] && [ -z "${BENCH_TIER4_SWEEP_ARGS:-}" ]; then
  fail "--class $BENCH_CLASS_ID needs tier4-side sensor parameters (Task 13's
  demo patch); supply BENCH_TIER4_SWEEP_ARGS explicitly to override."
fi

cat >"$BENCH_LAUNCH_ENV" <<EOF
# Written by benchmarks/cells/tier4-native.sh ($MODE).
LAUNCH_CELL="$BENCH_CELL"
APPROACH="tier4-native"
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
AW_COMPOSE=""
GT_ENABLED="1"
GT_CMD="env PYTHONPATH=$BENCH_REPO $GT_PYTHON -m benchmarks.scripts.collect_gt"
GT_OUT_DIR="$BENCH_RUN_DIR"
GT_COUNT_LIDAR="1"
INJECTOR_ENABLED="1"
ARM_ENABLED="1"
EXTRA_CONTAINERS=""
TIER4_DEMO="$TIER4_DEMO"
EOF

if [ "$MODE" = "plan" ]; then exit 0; fi
[ "$MODE" = "up" ] || fail "unknown mode $MODE (expected plan|up)"

# --------------------------------------------------------------------------
# up
# --------------------------------------------------------------------------
mkdir -p "$BENCH_RUN_DIR"

# -nosound is load-bearing on a headless host with no audio device (startup
# can otherwise fail before LoadMap); -carla-rpc-port is pinned explicitly
# because a collision surfaces as SIGABRT inside LoadMap, not a bind error.
#
# ROS_DOMAIN_ID=0 is pinned ON THIS PROCESS, not merely exported somewhere
# upstream. `--ros2` makes the editor a Fast-DDS participant and the fork
# reads the variable itself (ROS2.cpp:297-316, ObtainDomainId), while `nohup`
# inherits the invoking shell's environment. This host's login shell exports
# ROS_DOMAIN_ID=123 (~/.zshrc:126), so without this pin the fork lands on
# domain 123 while every container of this harness lands on 0: the stack
# starts, looks healthy, and not one topic is ever discovered. That is Task
# 9's measured matrix row 7. `env` execs in place, so $! is still the
# editor's own PID and the PID-file contract below is unchanged.
nohup env ROS_DOMAIN_ID=0 "$EDITOR" "$UPROJECT" "$BENCH_MAP" \
  -game --ros2 "-carla-rpc-port=$BENCH_RPC_PORT" \
  -RenderOffScreen -nosound >"$LAUNCH_LOG" 2>&1 &
echo $! >"$CARLA_PID_FILE"

echo "waiting up to ${READY_TIMEOUT_S}s for CARLA RPC on $BENCH_RPC_PORT (log: $LAUNCH_LOG)"
deadline=$((SECONDS + READY_TIMEOUT_S))
while :; do
  # Captured, never piped to grep -q: an early pipe close SIGPIPE-kills ss and
  # pipefail then reports "not bound" for a port that IS bound.
  ss_out="$(ss -ltn 2>/dev/null)" || true
  [[ "$ss_out" =~ :${BENCH_RPC_PORT}[[:space:]] ]] && break
  if [ "$SECONDS" -ge "$deadline" ]; then
    fail "CARLA RPC port $BENCH_RPC_PORT never bound within ${READY_TIMEOUT_S}s (see $LAUNCH_LOG)"
  fi
  if ! kill -0 "$(cat "$CARLA_PID_FILE")" 2>/dev/null; then
    fail "the editor exited during bring-up (see $LAUNCH_LOG)"
  fi
  sleep 5
done
echo "OK: tier4 CARLA up on port $BENCH_RPC_PORT"

# Autoware, via Task 13's launch script. Reached only when BENCH_TIER4_DEMO
# was supplied (plan refuses otherwise), so this is a hook, not a stub: it
# runs whatever Task 13 lands and fails if that fails.
echo "starting the tier4 Autoware stack via $TIER4_DEMO"
BENCH_CELL="$BENCH_CELL" \
BENCH_MAP="$BENCH_MAP" \
BENCH_RPC_PORT="$BENCH_RPC_PORT" \
BENCH_AUTOWARE_IMAGE="$BENCH_AUTOWARE_IMAGE" \
BENCH_AW_CONTAINER="$AW_CONTAINER" \
BENCH_RUN_DIR="$BENCH_RUN_DIR" \
  bash "$TIER4_DEMO"
echo "OK: tier4 Autoware stack reported ready"
