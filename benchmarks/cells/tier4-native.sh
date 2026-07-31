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
# The AUTOWARE half lives in benchmarks/cells/tier4_autoware.sh -- the demo +
# container launch Task 13 wrote into the BENCH_TIER4_DEMO hook this file used
# to refuse on. BENCH_TIER4_DEMO still overrides it, and the refusal below is
# still a refusal: it now fires only if that script is missing or has been
# pointed somewhere that does not exist, never by defaulting to a launch with
# no Autoware in it.
set -euo pipefail

: "${BENCH_REPO:?}" "${BENCH_CELL:?}" "${BENCH_MAP:?}" "${BENCH_ARM:?}"
: "${BENCH_RUN_DIR:?}" "${BENCH_LAUNCH_ENV:?}" "${BENCH_RPC_PORT:?}"
: "${BENCH_CARLA_TREE:?}" "${BENCH_AUTOWARE_IMAGE:?}" "${BENCH_ROUTE_FILE:?}"

MODE="${1:?usage: tier4-native.sh plan|up}"

ENGINE_PATH="${CARLA_UNREAL_ENGINE_PATH:-$HOME/src/UnrealEngine}"
EDITOR="$ENGINE_PATH/Engine/Binaries/Linux/UnrealEditor"
UPROJECT="$BENCH_CARLA_TREE/Unreal/CarlaUnreal/CarlaUnreal.uproject"
AW_CONTAINER=autoware
LAUNCH_LOG="$BENCH_RUN_DIR/launch.log"
CARLA_PID_FILE="$BENCH_RUN_DIR/carla.pid"
# The host-side tick authority tier4_autoware.sh starts (autoware_demo.py).
# Named here so launch.env and the hook invocation cannot disagree about it.
TIER4_DEMO_PID_FILE="$BENCH_RUN_DIR/tier4_demo.pid"
READY_TIMEOUT_S=420

fail() { echo "LAUNCH FAIL (tier4-native/$BENCH_CELL): $*" >&2; exit 2; }

# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------
[ -x "$EDITOR" ] || fail "shared engine editor missing: $EDITOR (set CARLA_UNREAL_ENGINE_PATH)"
[ -f "$UPROJECT" ] || fail "tier4 fork uproject missing: $UPROJECT (pins.yaml tier4_carla_fork.path)"

# The B family's counterpart to cell A's editor-artifact gate, which cell A
# reaches through cells/extension.sh -> run_e2e.sh:126. Nothing stood here
# before Task 17b: this launcher boots the shared engine against the tier4
# tree's plugin (line ~181 below) and a stale .so publishes a different wire
# format from the source the record cites, silently.
#
# Called on BOTH `plan` and `up` (this block runs before the mode switch), and
# called AGAIN even though preflight.sh section 7 already ran it under run.sh:
# a launcher invoked directly -- the documented entry point at the top of this
# file -- never passes through preflight, and the tree it would boot is
# $BENCH_CARLA_TREE, which is what is checked here. The duplicate costs the
# whole gate a second time -- a `find` over four source roots plus the content
# digests, 0.07-0.08 s measured 2026-07-31 on the real tree -- and removes a way
# to boot an unverified binary. Its KEY=VALUE stdout is the manifest's business,
# not this script's, so it is discarded here; the named refusal and the OK/WARN
# prose both go to stderr and are what an operator sees.
#
# The gate's mtime staleness check can be ACKNOWLEDGED rather than only rebuilt
# away, and the acknowledgement takes TWO variables:
#   export TIER4_STALE_ACK="<why this staleness is acceptable>"
#   export TIER4_STALE_ACK_SOURCE_SHA256=<this tree's tier4_source_sha256>
# Both are inherited straight through both call sites, so nothing here forwards
# them explicitly. The digest is MANDATORY: without it the acknowledgement is
# blanket, and one export left in this shell would turn the staleness check off
# for every later run in it -- Task 18 files ~20 B-family runs from one shell.
# Every refusal that needs the digest prints the tree's current one, so obtaining
# it needs neither a rebuild nor a passing run. See the gate's own "STALENESS
# ACKNOWLEDGEMENT" block for why an mtime refusal can otherwise be unresolvable
# mid-campaign, and for what the binding does and does not buy.
TIER4_GATE="$BENCH_REPO/benchmarks/scripts/verify_tier4_artifact.sh"
[ -f "$TIER4_GATE" ] || fail "tier4 plugin-artifact gate missing: $TIER4_GATE"
TIER4_TREE="$BENCH_CARLA_TREE" bash "$TIER4_GATE" >/dev/null ||
  fail "the tier4 plugin-artifact gate refused this run (named reason above)"

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

# The Autoware half (Task 13). Still checked, not assumed: an overridden or
# deleted hook must fail here, in `plan`, and not after CARLA has booted.
TIER4_DEMO="${BENCH_TIER4_DEMO:-$BENCH_REPO/benchmarks/cells/tier4_autoware.sh}"
[ -x "$TIER4_DEMO" ] || [ -f "$TIER4_DEMO" ] ||
  fail "BENCH_TIER4_DEMO=$TIER4_DEMO is not a file (the default is
  benchmarks/cells/tier4_autoware.sh, which runs the fork's patched
  autoware_demo.py plus the Autoware container)"

# Patch 0003 gives the demo the sensor flags a sweep class needs
# (--lidar-channels/--lidar-pps/--lidar-rotation-hz/--lidar-range plus the
# camera ones), and tier4_autoware.sh passes BENCH_TIER4_SWEEP_ARGS straight
# through to it -- but nothing DERIVES those arguments from a class id, and a
# sweep run that quietly used the baseline VLP16 rig would be filed as a 128ch
# measurement. Same refusal, and the same reason, as cells/extension.sh's for
# BENCH_RUNNER_SWEEP_ARGS.
#
# That derivation was owed to Task 26, which was STRUCK 2026-07-30 by the
# owner's core-duel scope cut -- so it has NO owner now and this refusal is
# permanent until someone writes the mapping. It stays a refusal rather than
# becoming a warning: unlike a struck CELL (run.sh step 1 only WARNs there,
# because dropping is scope and un-dropping is legitimate), an unmapped class
# id would file a run under the WRONG workload label, which is a false
# measurement rather than an out-of-scope one. Relevant to the pre-registered
# 32ch step-up branch (config/cells.yaml, sweep_classes): taking it needs no
# config edit, but it does need these arguments supplied by hand.
if [ -n "${BENCH_CLASS_ID:-}" ] && [ -z "${BENCH_TIER4_SWEEP_ARGS:-}" ]; then
  fail "--class $BENCH_CLASS_ID needs the tier4-side sensor arguments spelled
  out: patch 0003's flags exist, but nothing maps a class id onto them yet.
  Supply BENCH_TIER4_SWEEP_ARGS explicitly (e.g. --lidar-channels 128
  --lidar-pps 4600000)."
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
# Declared for teardown.sh, which stops the demo BEFORE the editor: the demo
# drives world.tick(), and a client left ticking a dead server hangs on actor
# destroy. Written by the plan step too, so a launcher that dies half-way
# through the up step still leaves teardown something to stop.
TIER4_DEMO_PID_FILE="$TIER4_DEMO_PID_FILE"
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
BENCH_REPO="$BENCH_REPO" \
BENCH_CELL="$BENCH_CELL" \
BENCH_MAP="$BENCH_MAP" \
BENCH_ARM="$BENCH_ARM" \
BENCH_RPC_PORT="$BENCH_RPC_PORT" \
BENCH_ROUTE_FILE="$BENCH_ROUTE_FILE" \
BENCH_CARLA_TREE="$BENCH_CARLA_TREE" \
BENCH_AUTOWARE_IMAGE="$BENCH_AUTOWARE_IMAGE" \
BENCH_AW_CONTAINER="$AW_CONTAINER" \
BENCH_RUN_DIR="$BENCH_RUN_DIR" \
BENCH_RMW="${BENCH_RMW:-}" \
BENCH_DDS_PROFILE="${BENCH_DDS_PROFILE:-}" \
BENCH_GT_PYTHON="$GT_PYTHON" \
TIER4_DEMO_PID_FILE="$TIER4_DEMO_PID_FILE" \
  bash "$TIER4_DEMO"
echo "OK: tier4 Autoware stack reported ready"
