#!/usr/bin/env bash
# Cell launcher: approach `python-bridge` (cells E0, E, E-opt).
#
#   bash benchmarks/cells/python-bridge.sh plan   # resolve + validate
#   bash benchmarks/cells/python-bridge.sh up     # plan, then boot + wait
#
# Implements benchmarks/patches/python-bridge/README.md's CORRECTED
# invocation: CARLA 0.9.15's packaged Shipping server, then one container
# running the bridge and the rest of the stack as two separate `ros2 launch`
# stages (stage 1 overrides autoware_carla_interface's Town01 default;
# stage 2 uses simulator_type:=awsim so it does not pull in a second bridge).
#
# E0 runs the AS-SHIPPED bridge and is fully launchable here: its image is
# the pinned `bridge-bench` (pins.yaml). E and E-opt run WITH
# patches/python-bridge/0001-lidar-is-dense.patch, whose image is built by
# Task 10; `plan` refuses those cells until that image exists, rather than
# silently measuring the unpatched bridge and filing it as E.
set -euo pipefail

: "${BENCH_REPO:?}" "${BENCH_CELL:?}" "${BENCH_MAP:?}" "${BENCH_ARM:?}"
: "${BENCH_RUN_DIR:?}" "${BENCH_LAUNCH_ENV:?}" "${BENCH_RPC_PORT:?}"

MODE="${1:?usage: python-bridge.sh plan|up}"

CARLA_0915_ROOT="${BENCH_CARLA_0915_ROOT:-$HOME/carla-0915}"
CARLA_0915_SH="$CARLA_0915_ROOT/CarlaUE4.sh"
AW_CONTAINER=bridge-bench
LAUNCH_LOG="$BENCH_RUN_DIR/launch.log"
CARLA_PID_FILE="$BENCH_RUN_DIR/carla.pid"
READY_TIMEOUT_S=300
# Container-side map bundle, mounted read-only from the host (same bundle the
# UE5 cells' compose mounts). e2e_simulator.launch.xml's map_path:=.
MAP_BUNDLE_HOST="$HOME/autoware_map/town10"
MAP_BUNDLE="/autoware_map/town10"

fail() { echo "LAUNCH FAIL (python-bridge/$BENCH_CELL): $*" >&2; exit 2; }

# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------
[ -x "$CARLA_0915_SH" ] ||
  fail "CARLA 0.9.15 not installed at $CARLA_0915_SH
  (run benchmarks/scripts/fetch_bridge_deps.sh, or set BENCH_CARLA_0915_ROOT)"
[ -d "$MAP_BUNDLE_HOST" ] || fail "Autoware map bundle missing: $MAP_BUNDLE_HOST"
[ -d "$HOME/autoware_data" ] ||
  fail "perception model/weights directory missing: $HOME/autoware_data
  (fetch with ansible-playbook autoware.dev_env.download_artifacts; without it
  the launch tree aborts on lidar_centerpoint's param file)"

case "$BENCH_CELL" in
  E0)
    # As-shipped: the pinned image, unpatched.
    IMAGE="${BENCH_BRIDGE_IMAGE:-bridge-bench:latest}"
    ;;
  E | E-opt)
    IMAGE="${BENCH_BRIDGE_IMAGE:-}"
    if [ -z "$IMAGE" ]; then
      fail "cell $BENCH_CELL runs the PATCHED bridge
      (patches/python-bridge/0001-lidar-is-dense.patch, benchmarks/README.md's
      named exception), and that image is built by Task 10 (Bridge viability
      patch + E-family recipes + E gate). It does not exist yet. Running the
      stock bridge-bench:latest here would measure E0 and file it as
      $BENCH_CELL. Set BENCH_BRIDGE_IMAGE once Task 10 has built and pinned
      the patched image."
    fi
    ;;
  *) fail "cell $BENCH_CELL is not a python-bridge cell" ;;
esac
docker image inspect "$IMAGE" >/dev/null 2>&1 || fail "image not present locally: $IMAGE"

cat >"$BENCH_LAUNCH_ENV" <<EOF
# Written by benchmarks/cells/python-bridge.sh ($MODE).
LAUNCH_CELL="$BENCH_CELL"
APPROACH="python-bridge"
LAUNCH_MAP="$BENCH_MAP"
LAUNCH_ARM="$BENCH_ARM"
RUN_MODE="shipping-headless"
CARLA_TREE="$CARLA_0915_ROOT"
CARLA_RPC_PORT="$BENCH_RPC_PORT"
CARLA_PID_FILE="$CARLA_PID_FILE"
LAUNCH_LOG="$LAUNCH_LOG"
AW_CONTAINER="$AW_CONTAINER"
AW_EXEC="docker exec -e ROS_DOMAIN_ID=0 $AW_CONTAINER"
AW_SETUP="source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0"
AW_COMPOSE=""
# GT runs INSIDE the container: the pinned 0.9.15 client wheel is a cp310
# build (pins.yaml gezp_wheel) and the container's python3.10 is the only
# interpreter on this host that can load it. /out is the run directory.
GT_ENABLED="1"
GT_CMD="docker exec -e PYTHONPATH=/work $AW_CONTAINER python3 -m benchmarks.scripts.collect_gt"
GT_OUT_DIR="/out"
# NEVER 1 here: the bridge publishes FROM its own sensor.listen callback and
# CARLA keeps one callback per sensor, so a counter would displace it and
# silence the run. collect_gt.py refuses --count-lidar for this approach.
GT_COUNT_LIDAR="0"
# This approach runs Autoware's real CUDA perception (pins.yaml's CUDA base),
# so the clear-road stand-in must NOT be injected on top of it.
INJECTOR_ENABLED="0"
ARM_ENABLED="1"
EXTRA_CONTAINERS=""
BRIDGE_IMAGE="$IMAGE"
EOF

if [ "$MODE" = "plan" ]; then exit 0; fi
[ "$MODE" = "up" ] || fail "unknown mode $MODE (expected plan|up)"

# --------------------------------------------------------------------------
# up
# --------------------------------------------------------------------------
mkdir -p "$BENCH_RUN_DIR"

# ROS_DOMAIN_ID=0 is pinned on the sim process for uniformity with the other
# launchers, not because this one is currently exposed: CARLA 0.9.15 has no
# native ROS 2 layer, so this server is not a DDS participant and the bridge
# that is one runs inside $AW_CONTAINER, which gets the domain explicitly
# below. Pinning here costs nothing and removes the whole class of "the sim
# inherited a login shell's ROS_DOMAIN_ID" defect from this file, which is
# real for the UE5-tree launchers (see cells/tier4-native.sh).
nohup env ROS_DOMAIN_ID=0 "$CARLA_0915_SH" -RenderOffScreen -nosound \
  "-carla-rpc-port=$BENCH_RPC_PORT" >"$LAUNCH_LOG" 2>&1 &
echo $! >"$CARLA_PID_FILE"

echo "waiting up to ${READY_TIMEOUT_S}s for CARLA 0.9.15 RPC on $BENCH_RPC_PORT"
deadline=$((SECONDS + READY_TIMEOUT_S))
while :; do
  ss_out="$(ss -ltn 2>/dev/null)" || true
  [[ "$ss_out" =~ :${BENCH_RPC_PORT}[[:space:]] ]] && break
  [ "$SECONDS" -lt "$deadline" ] ||
    fail "CARLA RPC port $BENCH_RPC_PORT never bound (see $LAUNCH_LOG)"
  sleep 3
done
echo "OK: CARLA 0.9.15 up on port $BENCH_RPC_PORT"

# --gpus all and the autoware_data mount are both load-bearing (the CUDA
# base and the perception weights); /work carries the harness so the
# in-container collect_gt/arm_and_goal invocations resolve, and /out is the
# run directory the observer and GT both write into.
docker rm -f "$AW_CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$AW_CONTAINER" --gpus all --net=host --ipc=host \
  -e ROS_DOMAIN_ID=0 \
  -v "$MAP_BUNDLE_HOST:$MAP_BUNDLE:ro" \
  -v "$HOME/autoware_data:/root/autoware_data" \
  -v "$BENCH_REPO:/work:ro" \
  -v "$BENCH_RUN_DIR:/out" \
  "$IMAGE" sleep infinity >/dev/null

cx() { docker exec -e ROS_DOMAIN_ID=0 "$AW_CONTAINER" bash -lc "$1"; }
AW_ENV='source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0'

# Stage 1 -- the bridge alone, so carla_map can be overridden. Launched
# separately precisely because e2e_simulator.launch.xml forwards NO arguments
# to it and its own default is Town01 (README bug 1: the map silently
# diverges from map_path:=).
cx "$AW_ENV
  nohup ros2 launch autoware_carla_interface autoware_carla_interface.launch.xml \
    carla_map:=$BENCH_MAP host:=localhost port:=$BENCH_RPC_PORT \
    sensor_kit_name:=carla_sensor_kit_description \
    >/tmp/bridge-stage1.log 2>&1 &
  echo \$! >/tmp/bridge-stage1.pid"

# Stage 2 -- the rest of the stack. simulator_type:=awsim so it does not
# include a SECOND bridge with the wrong default map; sensing:=true is
# load-bearing (without it GNSS -> EKF -> /localization/kinematic_state never
# comes up); perception left at its default ON, which the CUDA-pinned image
# supports.
cx "$AW_ENV
  nohup ros2 launch autoware_launch e2e_simulator.launch.xml \
    map_path:=$MAP_BUNDLE vehicle_model:=sample_vehicle \
    sensor_model:=carla_sensor_kit simulator_type:=awsim \
    sensing:=true rviz:=false \
    >/tmp/bridge-stage2.log 2>&1 &
  echo \$! >/tmp/bridge-stage2.pid"

# Readiness = the map the bridge actually loaded, verified through the client
# rather than trusted: README bug 1 is a SILENT wrong-map failure, and this
# is the check that catches it before a window is recorded on Town01.
echo "waiting up to ${READY_TIMEOUT_S}s for the bridge to load $BENCH_MAP"
deadline=$((SECONDS + READY_TIMEOUT_S))
until cx "python3 -c \"
import carla, sys
c = carla.Client('localhost', $BENCH_RPC_PORT); c.set_timeout(10.0)
name = c.get_world().get_map().name
sys.exit(0 if name.endswith('$BENCH_MAP') else 1)\"" >/dev/null 2>&1; do
  [ "$SECONDS" -lt "$deadline" ] || fail "the bridge never loaded $BENCH_MAP
  (check: docker exec $AW_CONTAINER cat /tmp/bridge-stage1.log)"
  sleep 5
done
echo "OK: bridge stack up on $BENCH_MAP"
