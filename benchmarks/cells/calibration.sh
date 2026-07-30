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
  fail "CAL-seam's seam/in-core publisher pair is Task 14 (CAL-seam publisher
  pair) and has not been written: no process to launch, and
  config/observer_topics/CAL-seam.yaml is deliberately empty for the same
  reason. The cell was STRUCK 2026-07-30 by the owner's core-duel scope cut,
  which took Task 17 with it, so nothing will run it and C1(a) seam overhead
  stays UNMEASURED."
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
