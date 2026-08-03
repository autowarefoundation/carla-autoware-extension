#!/usr/bin/env bash
# Cell launcher: approach `calibration` (cells CAL-rmw, CAL-seam).
#
#   bash benchmarks/cells/calibration.sh plan   # resolve + validate
#   bash benchmarks/cells/calibration.sh up     # plan, then boot + wait
#
# CAL-rmw has no simulator and no Autoware: it is bench_pub publishing a
# synthetic PointCloud2 into the observer under a requested RMW/SHM variant,
# which is what turns "how much of the measured latency is transport" into a
# measured number instead of an argument. bench_pub runs in the SAME image as
# the observer (benchmarks/docker/bench-observer.Dockerfile builds both), so
# publisher and recorder share one message set and one DDS build.
#
# CAL-seam is REFUSED: its in-core/out-of-core publisher pair is Task 14
# ("CAL-seam publisher pair") and does not exist. There is nothing to launch
# and nothing to observe, and a run that produced an empty-but-valid results
# directory would be indistinguishable from a transport that delivered
# nothing.
#
# That refusal is now PERMANENT for this campaign. Cell CAL-seam was STRUCK
# 2026-07-30 by the owner's core-duel scope cut (cells.yaml `dropped:`;
# benchmarks/README.md's 2026-07-30 amendment), taking Task 14's live half and
# Task 17 with it, so no CAL-seam run will be filed and C1(a) seam overhead is
# UNMEASURED. An owner TIME-BUDGET decision, not a technical block: the
# extension-side half of the publisher pair DID land (Task 14's code half) and
# only the fork-side twin was ever missing. The refusal is kept exactly as it
# is -- a launcher that quietly came up for a struck cell would file a run
# nothing is going to score.
#
# REINSTATED 2026-08-03 by the owner (P4 transport-sweep plan, spec decision
# 6), on the D8 lift that makes the fork-side twin publisher buildable (Task
# 9: LibCarla/source/carla/ros2/ROS2.cpp, gated on
# $CARLA_BENCH_INCORE_CLOUD=1). The paragraph above (":14-30") is UNEDITED --
# present tense, "is now PERMANENT", "is kept exactly as it is" and all -- it
# stays the true record of what the 2026-07-30 author asserted, and this
# reinstatement does not get to revise it. Read from here rather than
# corrected up there: "permanent" was true of the owner's 2026-07-30
# decision, not a prediction this note falsifies -- the owner made a NEW
# decision, on new evidence (the twin is now buildable), rather than the old
# one turning out wrong. That decision's own grounding, worth stating because
# the paragraph above does not draw the conclusion itself: the refusal's
# proximate cause was always the missing fork-side twin (the paragraph names
# it -- "only the fork-side twin was ever missing"), so its becoming
# buildable is what gave the owner grounds to revisit a decision the
# paragraph never claimed was irrevocable. CAL-seam now boots the extension
# fork editor WITHOUT Autoware (cells/extension.sh's recipe,
# scripts/e2e/run_e2e.sh with WITH_AUTOWARE=0), with both bench publishers
# enabled via $CARLA_BENCH_SEAM_CLOUD=1 and $CARLA_BENCH_INCORE_CLOUD=1
# exported into the editor's own environment -- see the `CAL-seam` branch
# below, which reuses the same launch.env / pidfile / teardown plumbing that
# family uses (APPROACH="extension" selects teardown.sh's graceful
# CARLA_PID_FILE case) and sets ARM_ENABLED="0": CAL-seam is a
# transport/serialization calibration, not a drive, so nothing is armed and
# no ground truth is collected (GT_ENABLED="0").
set -euo pipefail

: "${BENCH_REPO:?}" "${BENCH_CELL:?}" "${BENCH_ARM:?}"
: "${BENCH_RUN_DIR:?}" "${BENCH_LAUNCH_ENV:?}"
: "${BENCH_RMW:?}" "${BENCH_SHM:?}"

MODE="${1:?usage: calibration.sh plan|up}"

PUB_CONTAINER=bench-pub
OBSERVER_IMAGE="${BENCH_OBSERVER_IMAGE:-bench-observer:universe-devel}"
PUB_BIN=/ws/install/bench_observer/lib/bench_observer/bench_pub
PUB_TOPIC=/bench/cloud
LAUNCH_LOG="$BENCH_RUN_DIR/launch.log"
READY_TIMEOUT_S=60

fail() { echo "LAUNCH FAIL (calibration/$BENCH_CELL): $*" >&2; exit 2; }

# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------
if [ "$BENCH_CELL" = "CAL-seam" ]; then
  : "${BENCH_MAP:?}" "${BENCH_RPC_PORT:?}" "${BENCH_ROUTE_FILE:?}" "${BENCH_CARLA_TREE:?}"

  EXT_SO="$BENCH_REPO/extension/build/libcarla-autoware-extension.so"
  CARLA_PID_FILE="$BENCH_RUN_DIR/run_e2e.pid"
  READY_TIMEOUT_S=420 # booting an UnrealEditor, not a docker container -- CAL-rmw's 60s above does not apply here.

  # Same disagreement cells/extension.sh refuses: run_e2e.sh hardcodes RPC
  # port 2000 in both the editor invocation and its own port_bound() probe.
  [ "$BENCH_RPC_PORT" = "2000" ] ||
    fail "CAL-seam runs on RPC port 2000: scripts/e2e/run_e2e.sh hardcodes it
    (editor invocation + port_bound()). Parameterise run_e2e.sh before using
    --rpc-port $BENCH_RPC_PORT here."

  [ -f "$EXT_SO" ] ||
    fail "extension .so missing: $EXT_SO (build extension/ first)"
  [ -d "$BENCH_CARLA_TREE" ] ||
    fail "extension CARLA fork tree missing: $BENCH_CARLA_TREE (pins.yaml extension_carla_fork.path)"
  [ -f "$BENCH_ROUTE_FILE" ] ||
    fail "route file missing: $BENCH_ROUTE_FILE"

  # The GT client is used here ONLY as a bring-up READINESS PROBE (CARLA
  # reachable, ego spawned) -- GT_ENABLED="0" below, so it never collects
  # ground truth. Same interpreter requirement as cells/extension.sh: it must
  # be able to import the extension fork's own 0.10 client wheel.
  GT_PYTHON="${BENCH_GT_PYTHON:-$HOME/carla-venv/bin/python3}"
  [ -x "$GT_PYTHON" ] ||
    fail "GT interpreter not executable: $GT_PYTHON (set BENCH_GT_PYTHON)"
  "$GT_PYTHON" -c "import carla" >/dev/null 2>&1 ||
    fail "GT interpreter $GT_PYTHON cannot import carla (set BENCH_GT_PYTHON to
    an interpreter with the extension fork's 0.10 client wheel installed)"

  # Spawn pose from the shared route file (cell A's Town10HD_Opt.yaml).
  # CAL-seam measures transport, not driving, so pose accuracy is
  # irrelevant -- only a ticking world with a spawned ego is needed to drive
  # ext_on_tick (extension/src/ExtensionInit.cpp) and the fork's in-core twin
  # (LibCarla/source/carla/ros2/ROS2.cpp).
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
# Written by benchmarks/cells/calibration.sh ($MODE) -- CAL-seam branch.
LAUNCH_CELL="$BENCH_CELL"
# APPROACH is teardown.sh's case-select key (extension|tier4-native|
# python-bridge), NOT cells.yaml's own \`approach: calibration\` -- that stays
# the authoritative record everywhere else (the manifest writer and
# preflight.sh both read cells.yaml directly, not this file). CAL-seam boots
# and tears down through the IDENTICAL run_e2e.sh + CARLA_PID_FILE mechanism
# the "extension" family uses, so selecting that teardown case here is the
# correct reuse, not a misclassification.
APPROACH="extension"
LAUNCH_MAP="$BENCH_MAP"
LAUNCH_ARM="$BENCH_ARM"
RUN_MODE="editor-game"
CARLA_TREE="$BENCH_CARLA_TREE"
CARLA_RPC_PORT="$BENCH_RPC_PORT"
CARLA_PID_FILE="$CARLA_PID_FILE"
LAUNCH_LOG="$LAUNCH_LOG"
AW_CONTAINER=""
AW_EXEC=""
AW_SETUP=""
AW_COMPOSE=""
# No Autoware, so no ground truth comparison and nothing to arm or inject
# into -- CAL-seam is a transport/serialization calibration, not a drive.
GT_ENABLED="0"
GT_CMD=""
GT_OUT_DIR=""
GT_COUNT_LIDAR="0"
INJECTOR_ENABLED="0"
ARM_ENABLED="0"
EXTRA_CONTAINERS=""
SPAWN_ARGS="$SPAWN_ARGS"
EOF

  if [ "$MODE" = "plan" ]; then exit 0; fi
  [ "$MODE" = "up" ] || fail "unknown mode $MODE (expected plan|up)"

  mkdir -p "$BENCH_RUN_DIR"

  # Both bench publishers live INSIDE the same UnrealEditor process
  # run_e2e.sh execs -- the extension's C-ABI-seam publisher
  # (extension/src/publishers/BenchCloudPublisher.{h,cpp}, gated on
  # CARLA_BENCH_SEAM_CLOUD) and the fork's in-core twin
  # (LibCarla/source/carla/ros2/ROS2.cpp, gated on CARLA_BENCH_INCORE_CLOUD)
  # -- so both env vars must be present in run_e2e.sh's own environment, not
  # just this shell's. WITH_AUTOWARE=0 is explicit rather than relied-on
  # default: run_e2e.sh's own header documents that as "original CARLA+
  # runner smoke behaviour (no Autoware), for extension-only publisher
  # checks" -- exactly this cell's shape. ROS_DOMAIN_ID=0 is passed
  # explicitly for the same reason cells/extension.sh does: a login shell
  # exporting a nonzero domain must not silently split CARLA and the runner.
  (
    cd "$BENCH_REPO"
    MAP="$BENCH_MAP" \
    WITH_AUTOWARE=0 \
    ROS_DOMAIN_ID=0 \
    ROUTE_FILE="$BENCH_ROUTE_FILE" \
    CARLA_ROOT="$BENCH_CARLA_TREE" \
    CARLA_UNREAL_ENGINE_PATH="${CARLA_UNREAL_ENGINE_PATH:-$HOME/src/UnrealEngine}" \
    CARLA_BENCH_SEAM_CLOUD=1 \
    CARLA_BENCH_INCORE_CLOUD=1 \
    RUNNER_EXTRA_ARGS="$SPAWN_ARGS" \
      nohup bash scripts/e2e/run_e2e.sh >"$LAUNCH_LOG" 2>&1 &
    echo $! >"$CARLA_PID_FILE"
  )

  # Same readiness definition as cells/extension.sh: a CARLA the GT client
  # can reach, with the ego spawned -- used here purely as a bring-up probe
  # (GT_ENABLED="0" above), not to collect ground truth.
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
  echo "OK: CARLA up on port $BENCH_RPC_PORT with both bench publishers enabled (/bench/seam_cloud, /bench/incore_cloud)"
  exit 0
fi
[ "$BENCH_CELL" = "CAL-rmw" ] || fail "cell $BENCH_CELL is not a calibration cell"

docker image inspect "$OBSERVER_IMAGE" >/dev/null 2>&1 ||
  fail "observer/publisher image not present locally: $OBSERVER_IMAGE
  (build it from benchmarks/docker/bench-observer.Dockerfile; the local
  digest is recorded in pins.yaml under bench_observer_images)"

# The sweep point is the (rmw, shm) pair, so the workload must be described
# too, or two variants would differ in more than the transport under test.
#
# rate_hz MUST carry a decimal point. bench_pub.cpp declares it
# `declare_parameter<double>("rate_hz", 10.0)`, and rclcpp's statically-typed
# parameters REJECT an integer override for a double: the node throws
# InvalidParameterTypeException and the container dies on startup. Verified
# live -- `-p rate_hz:=10` gives "parameter 'rate_hz' has invalid type ...
# setting it to {integer} is not allowed", `-p rate_hz:=10.0` runs at exactly
# 10 Hz. Normalised here rather than only defaulted, so BENCH_PUB_RATE_HZ=20
# cannot reintroduce it. points_per_msg/point_step are declared int, so plain
# integers are correct for those.
PUB_RATE_HZ="${BENCH_PUB_RATE_HZ:-10.0}"
case "$PUB_RATE_HZ" in *.*) ;; *) PUB_RATE_HZ="${PUB_RATE_HZ}.0" ;; esac
PUB_POINTS="${BENCH_PUB_POINTS:-28800}"
PUB_POINT_STEP="${BENCH_PUB_POINT_STEP:-32}"

cat >"$BENCH_LAUNCH_ENV" <<EOF
# Written by benchmarks/cells/calibration.sh ($MODE).
LAUNCH_CELL="$BENCH_CELL"
APPROACH="calibration"
LAUNCH_MAP="none"
LAUNCH_ARM="$BENCH_ARM"
RUN_MODE="container-only"
CARLA_TREE=""
CARLA_RPC_PORT=""
CARLA_PID_FILE=""
LAUNCH_LOG="$LAUNCH_LOG"
AW_CONTAINER=""
AW_EXEC=""
AW_SETUP=""
AW_COMPOSE=""
# No simulator, so no ground truth and nothing to arm or inject into.
GT_ENABLED="0"
GT_CMD=""
GT_OUT_DIR=""
GT_COUNT_LIDAR="0"
INJECTOR_ENABLED="0"
ARM_ENABLED="0"
EXTRA_CONTAINERS="$PUB_CONTAINER"
PUB_CONTAINER="$PUB_CONTAINER"
PUB_TOPIC="$PUB_TOPIC"
PUB_RATE_HZ="$PUB_RATE_HZ"
PUB_POINTS="$PUB_POINTS"
PUB_POINT_STEP="$PUB_POINT_STEP"
EOF

if [ "$MODE" = "plan" ]; then exit 0; fi
[ "$MODE" = "up" ] || fail "unknown mode $MODE (expected plan|up)"

# --------------------------------------------------------------------------
# up
# --------------------------------------------------------------------------
mkdir -p "$BENCH_RUN_DIR"

# The transport variant under test. BENCH_DDS_PROFILE is the same file whose
# sha256 the manifest records, and it is mounted (not copied) so the manifest
# hash and the file the publisher used cannot diverge.
PUB_ENV=(-e "RMW_IMPLEMENTATION=$BENCH_RMW")
PUB_MOUNTS=()
if [ -n "${BENCH_DDS_PROFILE:-}" ] && [ "$BENCH_DDS_PROFILE" != "none" ]; then
  PUB_MOUNTS+=(-v "$BENCH_DDS_PROFILE:/dds-profile.xml:ro")
  case "$BENCH_RMW" in
    rmw_cyclonedds_cpp) PUB_ENV+=(-e "CYCLONEDDS_URI=file:///dds-profile.xml") ;;
    rmw_fastrtps_cpp) PUB_ENV+=(-e "FASTRTPS_DEFAULT_PROFILES_FILE=/dds-profile.xml") ;;
    *) fail "no DDS profile environment variable known for RMW $BENCH_RMW" ;;
  esac
fi

docker rm -f "$PUB_CONTAINER" >/dev/null 2>&1 || true
# exec so the binary is PID 1 and `docker kill -s INT` reaches rclcpp's own
# signal handler, the same reason the observer is launched this way.
docker run -d --name "$PUB_CONTAINER" --net=host --ipc=host \
  "${PUB_ENV[@]}" "${PUB_MOUNTS[@]}" "$OBSERVER_IMAGE" bash -lc "
    . /opt/ros/humble/setup.sh
    [ -f /opt/autoware/setup.bash ] && . /opt/autoware/setup.bash
    . /ws/install/setup.bash
    exec $PUB_BIN --ros-args -p topic:=$PUB_TOPIC -p rate_hz:=$PUB_RATE_HZ \
      -p points_per_msg:=$PUB_POINTS -p point_step:=$PUB_POINT_STEP" >/dev/null

# Readiness is EVIDENCE THAT SOMETHING WAS PUBLISHED, not that a container is
# running. `docker run -d` returns before the node has constructed, so a
# publisher that throws in its constructor can still be observed Running for
# one poll -- and then the whole 60 s scoring window is spent recording
# silence, with the failure surfacing only at step 15. `ros2 topic hz` inside
# the same container sees the real publisher on the real RMW.
deadline=$((SECONDS + READY_TIMEOUT_S))
while :; do
  if [ "$(docker inspect -f '{{.State.Running}}' "$PUB_CONTAINER" 2>/dev/null)" != "true" ]; then
    docker logs "$PUB_CONTAINER" >"$LAUNCH_LOG" 2>&1 || true
    fail "bench_pub exited during bring-up; see $LAUNCH_LOG
  (last line: $(tail -1 "$LAUNCH_LOG" 2>/dev/null))"
  fi
  # Captured, never piped into grep -q: an early pipe close SIGPIPEs the
  # producer, and under pipefail that reads back as "no output" for a
  # publisher that is in fact healthy.
  hz_out="$(docker exec "$PUB_CONTAINER" bash -lc "
    . /opt/ros/humble/setup.sh
    [ -f /opt/autoware/setup.bash ] && . /opt/autoware/setup.bash
    . /ws/install/setup.bash
    timeout 10 ros2 topic hz $PUB_TOPIC 2>/dev/null" || true)"
  case "$hz_out" in *"average rate"*) break ;; esac
  [ "$SECONDS" -lt "$deadline" ] ||
    fail "bench_pub never published on $PUB_TOPIC within ${READY_TIMEOUT_S}s
  (container is running, but nothing is on the wire; see $LAUNCH_LOG)"
  sleep 2
done
docker logs "$PUB_CONTAINER" >"$LAUNCH_LOG" 2>&1 || true
echo "OK: bench_pub publishing on $PUB_TOPIC ($(echo "$hz_out" | grep -m1 'average rate')," \
  "$PUB_POINTS x $PUB_POINT_STEP B) rmw=$BENCH_RMW shm=$BENCH_SHM"
