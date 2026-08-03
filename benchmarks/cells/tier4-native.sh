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

# The M4 sweep's ABLATION arm (cells.yaml `sweep_arms`): the identical LiDAR
# rig with PUBLISHING DISABLED, so the sweep can decompose
# `transport cost = total - baseline`. On this family that is the editor boot
# below MINUS the Autoware half -- no container, no autoware_demo.py -- with
# benchmarks/scripts/raycast_baseline.py taking the demo's place as the world's
# only client and only tick authority. The editor invocation itself, including
# `--ros2`, is unchanged: the arm ablates the SENSOR's emission (no ros_*
# attributes, no enable_for_ros), not the server's transport layer, so
# `total - baseline` isolates publishing rather than also crediting the DDS
# participant's existence.
BENCH_ARM_IS_ABLATION=0
[ "$BENCH_ARM" = "ablation" ] && BENCH_ARM_IS_ABLATION=1

# The Autoware half (Task 13). Still checked, not assumed: an overridden or
# deleted hook must fail here, in `plan`, and not after CARLA has booted.
# Skipped on the ablation arm, which never runs it: refusing a run over a hook
# it does not use would be a false refusal of exactly the kind this campaign
# has now recorded six times.
TIER4_DEMO="${BENCH_TIER4_DEMO:-$BENCH_REPO/benchmarks/cells/tier4_autoware.sh}"
if [ "$BENCH_ARM_IS_ABLATION" = "0" ]; then
  [ -x "$TIER4_DEMO" ] || [ -f "$TIER4_DEMO" ] ||
    fail "BENCH_TIER4_DEMO=$TIER4_DEMO is not a file (the default is
  benchmarks/cells/tier4_autoware.sh, which runs the fork's patched
  autoware_demo.py plus the Autoware container)"
fi

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
#
# OWNED 2026-08-03 (Task 6, P4 spec 1e): the two paragraphs above are kept
# as the strike-history record -- "NO owner"/"permanent" read historically,
# not currently, now that the mapping below exists. The pre-registered
# 32ch step-up branch this second paragraph names is
# benchmarks/README.md's own "per cell, if no vlp16 ceiling disjunct
# fires, the 32ch class executes mechanically; 128ch stays struck on
# either branch".
#
# Class id -> sensor arguments, derived HERE (registered 2026-08-03, P4
# spec 1e -- the residue of struck Task 26, now owned). Explicit env still
# wins; an id with no mapping still refuses, because an unmapped class
# would file a run under the WRONG workload label (a false measurement,
# not an out-of-scope one). Rotation frequency stays at each family's
# registered contract; a class pins channels + points_per_second only
# (cells.yaml sweep_classes).
if [ -n "${BENCH_CLASS_ID:-}" ] && [ -z "${BENCH_TIER4_SWEEP_ARGS:-}" ]; then
  case "$BENCH_CLASS_ID" in
    vlp16) BENCH_TIER4_SWEEP_ARGS="--lidar-channels 16 --lidar-pps 288000" ;;
    32ch)  BENCH_TIER4_SWEEP_ARGS="--lidar-channels 32 --lidar-pps 1200000" ;;
    *) fail "--class $BENCH_CLASS_ID has no registered sensor-argument
    mapping (vlp16 and 32ch are registered; 128ch is struck on either
    branch)" ;;
  esac
fi

# --------------------------------------------------------------------------
# ablation arm: resolve everything the baseline client needs, in `plan`, so a
# missing interpreter dependency or an unregistered tick target refuses BEFORE
# a 2-5 minute editor boot is paid for.
# --------------------------------------------------------------------------
ABLATION_PID_FILE="$BENCH_RUN_DIR/raycast_baseline.pid"
ABLATION_LOG="$BENCH_RUN_DIR/raycast_baseline.log"
ABLATION_TICK_HZ=""
ABLATION_SPAWN_ARGS=""
# A CAP on the client's tick loop, not the scoring window (run.sh step 10 owns
# that). It bounds how long an orphaned client can tick a server nobody watches.
ABLATION_DURATION_S="${BENCH_ABLATION_DURATION_S:-600}"
ABLATION_READY_S=120
if [ "$BENCH_ARM_IS_ABLATION" = "1" ]; then
  # $GT_PYTHON is already the interpreter whose `carla` matches THIS fork's
  # server (checked by import above). Checked again by importing the module it
  # will actually run: raycast_baseline pulls in runner.kit/loop/spawn and yaml.
  PYTHONPATH="$BENCH_REPO" "$GT_PYTHON" -c \
    "import benchmarks.scripts.raycast_baseline" >/dev/null 2>&1 ||
    fail "$GT_PYTHON cannot import benchmarks.scripts.raycast_baseline (the
  ablation client). It needs this repo on PYTHONPATH plus PyYAML; see the
  tier4 venv recipe above and add the missing dependency to it."

  # sweep_verdict.py scores paced and ablation at the SAME paced tick target,
  # so the client's fixed delta is the cell's REGISTERED metrics.tick_hz --
  # read from cells.yaml here, never a literal; a null binding refuses.
  ABLATION_TICK_HZ="$(BENCH_CELL="$BENCH_CELL" PYTHONPATH="$BENCH_REPO" python3 - <<'PY'
import os

from benchmarks.scripts.cell_info import load_cells_doc, metrics_for

cell = os.environ["BENCH_CELL"]
tick_hz = metrics_for(load_cells_doc(), cell)["tick_hz"]
if tick_hz is None:
    raise SystemExit(
        f"metrics.tick_hz is not registered (null) for cell {cell}: the ablation arm "
        "cannot pick a tick target the campaign has not pre-registered"
    )
print(tick_hz)
PY
  )" || fail "could not resolve the registered tick target for cell $BENCH_CELL"

  # Spawn pose from the committed route file, in the SAME two spellings
  # cells/tier4_autoware.sh derives for the patched demo (--spawn-pose x y z 0
  # 0 yaw_deg, else --spawn-index N) -- raycast_baseline.py accepts both, so
  # the ablation arm starts the rig where the measured arm starts it. The
  # derivation is duplicated rather than sourced because tier4_autoware.sh is
  # the whole Autoware launch, which this arm exists not to run; the two must
  # be changed together.
  ABLATION_SPAWN_ARGS="$(BENCH_ROUTE_FILE="$BENCH_ROUTE_FILE" python3 - <<'PY'
import os

import yaml

route = yaml.safe_load(open(os.environ["BENCH_ROUTE_FILE"]))
index = route.get("spawn_index")
pose = route.get("spawn_pose")
if pose:
    print(f"--spawn-pose {pose['x']} {pose['y']} {pose['z']} 0 0 {pose['yaw_deg']}")
elif index is not None:
    print(f"--spawn-index {int(index)}")
else:
    raise SystemExit("route file has neither spawn_pose nor spawn_index")
PY
  )" || fail "could not derive the spawn pose from $BENCH_ROUTE_FILE"
fi

# The four harness switches the ablation arm flips; each one is acted on
# directly by run.sh. ARM_ENABLED=0 -> step 9 reports "(nothing to arm for this
# cell)" and skips the post-engage control_cmd probe. INJECTOR_ENABLED=0 ->
# step 8 has no Autoware container to docker-exec into (it would exclude the
# run gate:injector-failed). GT_ENABLED=0 -> no second CARLA client competing
# with the very measurement this arm isolates, and step 15's smoke drops its
# gt.csv assertion. GT_COUNT_LIDAR=0 -> publisher_counts.json stays ABSENT,
# which sweep_verdict.py reads as "not measurable"; a file-backed 0 would fire
# the ceiling's publisher disjunct on a run that never intended to publish.
LAUNCH_GT_ENABLED=1
LAUNCH_GT_COUNT_LIDAR=1
LAUNCH_INJECTOR_ENABLED=1
LAUNCH_ARM_ENABLED=1
if [ "$BENCH_ARM_IS_ABLATION" = "1" ]; then
  LAUNCH_GT_ENABLED=0
  LAUNCH_GT_COUNT_LIDAR=0
  LAUNCH_INJECTOR_ENABLED=0
  LAUNCH_ARM_ENABLED=0
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
GT_ENABLED="$LAUNCH_GT_ENABLED"
GT_CMD="env PYTHONPATH=$BENCH_REPO $GT_PYTHON -m benchmarks.scripts.collect_gt"
GT_OUT_DIR="$BENCH_RUN_DIR"
GT_COUNT_LIDAR="$LAUNCH_GT_COUNT_LIDAR"
INJECTOR_ENABLED="$LAUNCH_INJECTOR_ENABLED"
ARM_ENABLED="$LAUNCH_ARM_ENABLED"
EXTRA_CONTAINERS=""
TIER4_DEMO="$TIER4_DEMO"
# Declared for teardown.sh, which stops the demo BEFORE the editor: the demo
# drives world.tick(), and a client left ticking a dead server hangs on actor
# destroy. Written by the plan step too, so a launcher that dies half-way
# through the up step still leaves teardown something to stop.
TIER4_DEMO_PID_FILE="$TIER4_DEMO_PID_FILE"
EOF

if [ "$BENCH_ARM_IS_ABLATION" = "1" ]; then
  # Same contract as TIER4_DEMO_PID_FILE above, for the process that REPLACES
  # the demo on this arm: teardown.sh stops it before the editor, because it is
  # the world's tick authority and a client left ticking a dead server hangs on
  # actor destroy.
  cat >>"$BENCH_LAUNCH_ENV" <<EOF
ABLATION_PID_FILE="$ABLATION_PID_FILE"
ABLATION_LOG="$ABLATION_LOG"
ABLATION_TICK_HZ="$ABLATION_TICK_HZ"
EOF
fi

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
# editor's own PID and the PID-file contract below is unchanged. On the
# ablation arm the pin is a no-op (no ROS 2 layer runs); it is kept anyway.
#
# `--ros2` is DROPPED on the ablation arm, and that is the arm's central
# mechanism rather than an optimisation. MEASURED 2026-08-03 on the extension
# fork (the same native ROS 2 layer; bring-up probe through the matched
# Humble/cyclonedds instrument): WITH `--ros2` the editor EMITS /clock at
# 19.959 Hz with no runner attached -- which would make bench_observer an
# active, per-row-flushed writer to the very clock.csv this arm's client has to
# write -- and it ADVERTISES `/carla/<vehicle>/ray_cast2/point_cloud` for a rig
# spawned with no ros_* attributes and no enable_for_ros(), i.e. dropping the
# attributes alone does NOT disable publishing. WITHOUT the flag the same
# instrument sees no CARLA topic at all. See
# benchmarks/scripts/raycast_baseline.py's module docstring for the evidence
# and for why a smaller baseline still leaves `T - B` a lower bound.
ROS2_ARGS=(--ros2)
[ "$BENCH_ARM_IS_ABLATION" = "1" ] && ROS2_ARGS=()
nohup env ROS_DOMAIN_ID=0 "$EDITOR" "$UPROJECT" "$BENCH_MAP" \
  -game ${ROS2_ARGS[@]+"${ROS2_ARGS[@]}"} "-carla-rpc-port=$BENCH_RPC_PORT" \
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

# The ablation arm stops here on the Autoware side and starts the
# publish-disabled baseline client in the demo's place.
if [ "$BENCH_ARM_IS_ABLATION" = "1" ]; then
  # $BENCH_TIER4_SWEEP_ARGS is the class mapping resolved above
  # (--lidar-channels/--lidar-pps, the patched demo's own flag names) and
  # $ABLATION_SPAWN_ARGS the route's spawn in the demo's spelling;
  # raycast_baseline.py accepts both verbatim, so neither is re-derived here.
  # Both are deliberately word-split: resolved multi-flag strings, not single
  # arguments.
  # shellcheck disable=SC2086
  nohup env PYTHONPATH="$BENCH_REPO" "$GT_PYTHON" -m benchmarks.scripts.raycast_baseline \
    --host localhost --port "$BENCH_RPC_PORT" --rig tier4 \
    --class-id "${BENCH_CLASS_ID:-}" --tick-hz "$ABLATION_TICK_HZ" \
    --duration-s "$ABLATION_DURATION_S" --out-dir "$BENCH_RUN_DIR" \
    $ABLATION_SPAWN_ARGS ${BENCH_TIER4_SWEEP_ARGS:-} >"$ABLATION_LOG" 2>&1 &
  echo $! >"$ABLATION_PID_FILE"

  # Readiness is the FILE, not the process: nothing publishes /clock on this
  # arm, so this client is clock.csv's only writer -- and run.sh step 7's
  # watchdog starts judging the run by that file within 30 s. Two data rows
  # also clears fit_sim_wall_affine's ">= 2 paired samples", which the step-15
  # smoke needs.
  echo "waiting up to ${ABLATION_READY_S}s for the baseline client to tick (log: $ABLATION_LOG)"
  deadline=$((SECONDS + ABLATION_READY_S))
  until [ "$(wc -l <"$BENCH_RUN_DIR/clock.csv" 2>/dev/null || echo 0)" -ge 3 ]; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      fail "the raycast baseline client wrote no clock.csv rows within
  ${ABLATION_READY_S}s (see $ABLATION_LOG)"
    fi
    if ! kill -0 "$(cat "$ABLATION_PID_FILE" 2>/dev/null)" 2>/dev/null; then
      fail "the raycast baseline client exited during bring-up (see $ABLATION_LOG)"
    fi
    sleep 2
  done
  echo "OK: publish-disabled baseline ticking at ${ABLATION_TICK_HZ} Hz (no Autoware: ablation arm)"
  exit 0
fi

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
