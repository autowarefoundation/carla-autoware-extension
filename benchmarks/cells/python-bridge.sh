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
# E0 runs the AS-SHIPPED bridge: its image is the pinned `bridge-bench`
# (pins.yaml bridge_bench). E and E-opt run the PATCHED image
# (pins.yaml bridge_bench_patched, built from
# docker/bridge-bench-patched.Dockerfile with 0001-lidar-is-dense.patch and
# 0002-sensor-config-harmonized.patch). run.sh resolves which one per cell and
# records it in the manifest; `plan` here re-checks the resolved image's actual
# CONTENT rather than its tag, in both directions, so neither "measured the
# unpatched bridge and filed it as E" nor "measured the patched bridge and
# filed it as as-shipped E0" is expressible.
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
# Second readiness gate below: the Autoware stack itself. Measured cold-start
# to first /localization/kinematic_state on this host is ~110-130 s with the
# CUDA perception stack on; 420 s leaves room for a slower disk without
# waiting so long that the bridge's ~10-minute sync-tick stall (P1 Verdict 1,
# deliberately NOT patched) eats the scoring window.
STACK_TIMEOUT_S=420
# Container-side map bundle, mounted read-only from the host (same bundle the
# UE5 cells' compose mounts). e2e_simulator.launch.xml's map_path:=.
MAP_BUNDLE_HOST="$HOME/autoware_map/town10"
MAP_BUNDLE="/autoware_map/town10"

# Both bridge launch logs live inside the container, and teardown REMOVES the
# container (the image differs per cell, so it may not be left up for the next
# one). A readiness failure would therefore destroy the only record of why, as
# it did twice while this launcher was being brought into shape. Copy them into
# the run directory on every failure path, so an excluded run carries its own
# diagnosis. A no-op before the container exists.
save_stage_logs() {
  docker inspect "$AW_CONTAINER" >/dev/null 2>&1 || return 0
  for stage in 1 2; do
    docker cp "$AW_CONTAINER:/tmp/bridge-stage$stage.log" \
      "$BENCH_RUN_DIR/bridge-stage$stage.log" >/dev/null 2>&1 || true
  done
}

fail() {
  save_stage_logs
  echo "LAUNCH FAIL (python-bridge/$BENCH_CELL): $*" >&2
  exit 2
}

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

# Spawn pose from the committed route file, so this cell starts where the route
# was scored -- exactly as cells/extension.sh does. The bridge takes it as a
# SINGLE comma-separated `spawn_point:=x,y,z,roll,pitch,yaw` string in the
# CARLA frame (carla_autoware.py's load_world splits on ","; a value that does
# not split into 6 items falls back to a RANDOM spawn, silently, which is what
# the P1 pass measured). Note the bridge adds +2 m to z on its own ("so the car
# did not stuck on the road when spawned") -- shipped behaviour, left alone.
SPAWN_POINT="$(BENCH_ROUTE_FILE="$BENCH_ROUTE_FILE" python3 - <<'PY'
import os

import yaml

route = yaml.safe_load(open(os.environ["BENCH_ROUTE_FILE"]))
pose = route.get("spawn_pose")
if not pose:
    # spawn_index is CARLA's live recommended-spawn list, which this bridge
    # cannot be given: its spawn_point parameter is a pose, and anything that
    # is not six comma-separated numbers means "randomize". Failing here beats
    # a run that silently starts somewhere else than the scored route.
    raise SystemExit(
        "route file has no spawn_pose; the bridge takes a pose, not a "
        "spawn_index, and an unparseable value spawns RANDOMLY"
    )
print(f"{pose['x']},{pose['y']},{pose['z']},0,0,{pose['yaw_deg']}")
PY
)" || fail "could not derive the spawn pose from $BENCH_ROUTE_FILE"

# run.sh resolves the per-cell image and exports it as BENCH_AUTOWARE_IMAGE --
# the SAME string it writes into the manifest. Reading it here instead of
# re-deriving it is what makes the manifest's `container_image` a fact about
# this run rather than a parallel guess. BENCH_BRIDGE_IMAGE still overrides for
# a hand-driven launch, and run.sh honours the same variable, so the two stay
# in step.
IMAGE="${BENCH_BRIDGE_IMAGE:-${BENCH_AUTOWARE_IMAGE:-}}"
[ -n "$IMAGE" ] ||
  fail "no bridge image resolved: run.sh exports BENCH_AUTOWARE_IMAGE, and
  BENCH_BRIDGE_IMAGE overrides it for a hand-driven launch"
docker image inspect "$IMAGE" >/dev/null 2>&1 || fail "image not present locally: $IMAGE"

# Observer transport. MEASURED 2026-07-29 (Task 10) with the REAL bench_observer
# binary against a live bridge, 20 s dwell per row, patches/python-bridge/
# README.md "Observer transport matrix":
#
#   cyclone + docker/cyclonedds.xml (`lo`)   clock 0    observer 0
#   cyclone + DEFAULT profile                clock 366  observer 365
#   fastrtps + image default (SHM on)        clock 386  observer 385
#   fastrtps + observer/config/udp_only.xml  clock 385  observer 386
#
# The `lo`-pinned profile discovers NOTHING here: the stack is Fast-DDS (image
# default) and Fast-DDS announces no loopback unicast locators, so a Cyclone
# participant confined to `lo` never matches it. That is the whole of cell E
# run-001's header-only observer.csv/clock.csv. benchmarks/README.md's confound
# table registers this cell family's observer as "rmw_cyclonedds_cpp, DEFAULT
# profile", which the matrix confirms works; run.sh's per-invocation default
# contradicts it, so refuse rather than record an empty observer as a property
# of the bridge.
if [ "${BENCH_RMW:-}" = "rmw_cyclonedds_cpp" ] && [ "${BENCH_DDS_PROFILE:-none}" != "none" ]; then
  fail "cell $BENCH_CELL needs the observer on CycloneDDS' DEFAULT profile, but
  BENCH_DDS_PROFILE=$BENCH_DDS_PROFILE confines it to \`lo\`, where it cannot
  discover this cell's Fast-DDS stack (measured: 0 clock rows and 0 observer
  rows in 20 s, against 366/365 on the default profile in the same minute).
  Re-run with --dds-profile none, which is the configuration
  benchmarks/README.md's DDS confound table registers for the E family."
fi

# The patch marker, checked inside the resolved image. `is_dense` is 0001's own
# line, so this tests what the run will actually execute -- not the tag, which
# is just a name somebody chose. No --gpus needed for a grep.
PATCH_MARKER='is_dense=True'
CARLA_UTILS=/opt/autoware/lib/python3.10/site-packages/autoware_carla_interface/modules/carla_utils.py
if docker run --rm "$IMAGE" grep -q "$PATCH_MARKER" "$CARLA_UTILS" 2>/dev/null; then
  IMAGE_PATCHED=1
else
  IMAGE_PATCHED=0
fi

case "$BENCH_CELL" in
  E0)
    # As-shipped, and that is the measurement: E0 exists to record the bridge's
    # own defaults failing, so a patched image here would quietly turn E0 into
    # a second copy of E.
    [ "$IMAGE_PATCHED" = "0" ] ||
      fail "cell E0 measures the AS-SHIPPED bridge, but $IMAGE carries
      patches/python-bridge/0001-lidar-is-dense.patch ($CARLA_UTILS contains
      '$PATCH_MARKER'). Use pins.yaml bridge_bench.tag (bridge-bench:latest)."
    ;;
  E | E-opt)
    [ "$IMAGE_PATCHED" = "1" ] ||
      fail "cell $BENCH_CELL runs the PATCHED bridge
      (patches/python-bridge/0001-lidar-is-dense.patch, benchmarks/README.md's
      named exception), but $IMAGE does not carry it ($CARLA_UTILS has no
      '$PATCH_MARKER'). Running it would measure E0 and file it as
      $BENCH_CELL. Build pins.yaml bridge_bench_patched.tag:
        docker build -f benchmarks/docker/bridge-bench-patched.Dockerfile \\
          -t bridge-bench-patched:latest benchmarks/"
    ;;
  *) fail "cell $BENCH_CELL is not a python-bridge cell" ;;
esac

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
#
# ego_vehicle_role_name:=ego is load-bearing for the MEASUREMENT, not for the
# drive: the bridge's own default is `ego_vehicle`, while run.sh invokes
# collect_gt.py with --role-name ego, and find_ego matches role_name EXACTLY.
# Left at the default, the GT collector raises "no ego actor found" during
# start-up and run.sh excludes the run crash:collect_gt -- i.e. no M5 ground
# truth, from a stack that was otherwise healthy.
cx "$AW_ENV
  nohup ros2 launch autoware_carla_interface autoware_carla_interface.launch.xml \
    carla_map:=$BENCH_MAP host:=localhost port:=$BENCH_RPC_PORT \
    sensor_kit_name:=carla_sensor_kit_description \
    ego_vehicle_role_name:=ego spawn_point:=$SPAWN_POINT \
    >/tmp/bridge-stage1.log 2>&1 &
  echo \$! >/tmp/bridge-stage1.pid"

# FIRST readiness gate, and it is a BARRIER, not a nicety: stage 2 must not
# start until the bridge's world exists. Launched back to back, the whole
# Autoware stack came up against the world that the bridge's
# `client.load_world()` then replaced underneath it, and
# /localization/kinematic_state never published at all -- measured 2026-07-29
# (Task 10): results/E/run-002, crash:cell-launch after the full 420 s stack
# budget. Sequenced the way a hand bring-up naturally does -- wait for the map,
# then launch the stack -- it localizes in ~110-130 s.
#
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
echo "OK: bridge on $BENCH_MAP"

# Stage 2 -- the rest of the stack, started only now (see the barrier above).
# simulator_type:=awsim so it does not include a SECOND bridge with the wrong
# default map; sensing:=true is load-bearing (without it GNSS -> EKF ->
# /localization/kinematic_state never comes up); perception left at its default
# ON, which the CUDA-pinned image supports and which benchmarks/README.md's
# perception-load confound registers for this cell family.
cx "$AW_ENV
  nohup ros2 launch autoware_launch e2e_simulator.launch.xml \
    map_path:=$MAP_BUNDLE vehicle_model:=sample_vehicle \
    sensor_model:=carla_sensor_kit simulator_type:=awsim \
    sensing:=true rviz:=false \
    >/tmp/bridge-stage2.log 2>&1 &
  echo \$! >/tmp/bridge-stage2.pid"

# SECOND readiness gate: the STACK, not just the bridge. The map check above
# passes within ~20 s (stage 1 loads the world almost immediately), while
# stage 2 needs minutes -- the 110 MiB pointcloud map, the CUDA perception
# weights, ~30 component containers. Returning after the map check alone put
# run.sh at step 9 with the stack still coming up, and arm_and_goal.py's
# 60 s budget expired before /localization/kinematic_state existed: the run
# was excluded `gate:arm-failed`, which reads as "this approach cannot
# localize" when the truth was "the launcher returned too early". Measured
# 2026-07-29 (Task 10): results/E/run-001.
#
# Waiting for one /localization/kinematic_state message is the weakest signal
# that means "the stack is up AND localizing"; the arm step still applies its
# own sustained-rate criterion on top, so this does not subsume it. A timeout
# here is a launcher readiness failure -> run.sh files it crash:cell-launch
# (exclusions.md criterion 1, which covers exactly this), never as an arm
# failure.
#
# NOTHING is retried here, deliberately. An earlier revision of this loop called
# /api/localization/initialize every iteration, on the belief that the stack
# tries GNSS+ndt_align only in its first ~75 s and then gives up. That belief is
# REFUTED by the logs of the two runs it was written from: Autoware's own
# `autoware_automatic_pose_initializer` calls the same API roughly every 2 s for
# as long as localization is UNINITIALIZED (results/E/run-003, 442 s; and the
# 2026-07-29 bring-up probe, where "Call align server" repeats at t+2 s
# intervals until it succeeds). The launcher's call carried an EMPTY pose array
# -- the AD API's "initialize from GNSS" form, i.e. exactly the request the
# automatic initializer already makes -- so it added no information, and each
# `ros2 service call` stood up and tore down a participant against a stack whose
# composable-node loads are themselves sensitive to discovery churn (see
# diagnose_localization_input below). Waiting is strictly better than nudging.
#
# What run-003 actually failed on is diagnosed, not retried: the localization
# input chain never finished loading. `pointcloud_container` logged "failed to
# send response to /pointcloud_container/_container/load_node (timeout): client
# will not receive response" four times, and `/localization/util/
# random_downsample_filter` -- the node that publishes NDT's only input,
# /localization/util/downsample/pointcloud -- was never instantiated, so
# `ndt_scan_matcher` reported "No InputSource" for the whole 442 s while
# perception, fed off the SAME cloud, ran normally. That is a dropped
# rclcpp/rmw service response under start-up load, not a bridge defect and not
# an is_dense rejection; it did not reproduce on the next bring-up. Naming it is
# the deliverable, so the timeout path reports which of the three nodes exist.
diagnose_localization_input() {
  cx "$AW_ENV
    ros2 node list --no-daemon 2>/dev/null | grep '^/localization/util/' | sort" \
    2>/dev/null || true
}

# The bridge is the sole ticking authority in sync mode, and when its tick loop
# stops, EVERY node that runs on sim time stops with it -- so the symptom of
# P1 Verdict 1 (exclusions.md criterion 4) during bring-up is indistinguishable
# from "the stack is still coming up" unless the sim clock is checked directly.
# Measured 2026-07-29 (Task 10): the tick froze ~70 s of sim time in, moments
# after localization initialized, and the launcher then sat out its whole
# remaining budget before reporting the wrong thing.
#
# `wait_for_tick`, NOT a frame-number comparison. A first version of this check
# connected a fresh client and compared `get_snapshot().frame` across samples,
# and it FALSELY condemned results/E/run-005 fifteen seconds into a healthy
# bring-up: `get_snapshot()` returns the episode state this client has received
# so far, so a client that has just connected reports frame 0 whether or not the
# world is ticking, and two such reads are equal for that reason alone. (The
# same artifact is why a frozen world reports "actors 0" -- one external tick on
# a frozen probe world returned frame 1396 and 27 actors, the ego among them.)
# `wait_for_tick` instead BLOCKS for the next world state and raises on timeout,
# so it tests the property in question directly and needs no baseline sample.
# Two consecutive 5 s timeouts, rather than one, keep a scheduling hiccup on a
# loaded host from condemning a healthy run while still landing well inside the
# 420 s budget.
#
# The probe reports THREE outcomes, not two, and only one of them is a freeze.
# An earlier version treated any non-zero exit as a strike, so a failed
# `docker exec`, an import error or a refused connection would have been
# escalated into an assertion that P1 Verdict 1 had occurred -- indicting the
# bridge for a defect in the probe, which is the same class of mistake as the
# frame-compare above. `time-out` in the RuntimeError text is CARLA's own
# wording for `wait_for_tick` expiring ("time-out of 5000ms while waiting for
# the simulator", verified live on this host), so it is what distinguishes a
# frozen world from a probe that never ran.
#
# CONNECTING SITS OUTSIDE THE FROZEN-ELIGIBLE REGION, which is why there are two
# `try` blocks rather than one. `carla.Client` and `get_world()` raise
# RuntimeError carrying the SAME "time-out" wording when the server is merely
# unreachable: measured 2026-07-29 against a free port, verbatim "time-out of
# 10000ms while waiting for the simulator, make sure the simulator is ready and
# connected to localhost:2100". Matching that text across the whole sequence
# therefore classified an absent or not-yet-listening server as FROZEN -- both
# classifiers were run side by side on that unreachable port and the one-`try`
# form answered FROZEN where this form answers PROBE_ERROR. Left as it was, a
# server the probe never reached would have accumulated freeze strikes and been
# reported as the bridge's tick loop stalling. Only `wait_for_tick` on an
# ALREADY-OBTAINED world can answer the tick question, so only its timeout is
# allowed to mean FROZEN.
carla_tick_state() {
  cx "python3 -c \"
import carla
try:
    c = carla.Client('localhost', $BENCH_RPC_PORT); c.set_timeout(10.0)
    world = c.get_world()
except Exception as exc:
    print('PROBE_ERROR', type(exc).__name__)
else:
    try:
        print('TICKING', world.wait_for_tick(5.0).frame)
    except RuntimeError as exc:
        print('FROZEN' if 'time-out' in str(exc) else 'PROBE_ERROR', type(exc).__name__)
    except Exception as exc:
        print('PROBE_ERROR', type(exc).__name__)\"" 2>/dev/null |
    tr -d '\r' | awk 'NF {print $1; exit}'
}

# --no-daemon, and it is load-bearing. MEASURED 2026-07-29 (Task 10): this loop
# used to poll with a plain `ros2 topic echo --once`, and against a stack that
# was demonstrably localizing -- NDT at 13 Hz, `EKF Activation succeeded`,
# `/localization/kinematic_state` delivering x=53.942 y=-141.087 to an rclpy
# subscriber in the same second -- every poll FAILED, so the launcher sat out
# its whole 420 s budget and reported "never published". Cause: the loop's own
# first poll starts a `ros2cli` daemon while the stack is absent, the daemon
# caches that empty node graph, and every later poll is answered from the cache.
# Stopping the daemon by hand made the very next poll succeed. `--no-daemon`
# removes the cache from the path; a stale-daemon false negative here is
# indistinguishable from "this approach cannot localize", which is precisely the
# claim this campaign exists to make correctly.
echo "waiting up to ${STACK_TIMEOUT_S}s for the Autoware stack to localize"
deadline=$((SECONDS + STACK_TIMEOUT_S))
freeze_strikes=0
probe_errors=0
until cx "$AW_ENV
  timeout 20 ros2 topic echo --once --no-daemon \
    /localization/kinematic_state >/dev/null 2>&1" \
  >/dev/null 2>&1; do
  case "$(carla_tick_state)" in
    TICKING) freeze_strikes=0; probe_errors=0 ;;
    FROZEN) freeze_strikes=$((freeze_strikes + 1)) ;;
    # Neither -- the probe itself did not run (docker exec died, the client
    # could not connect, the interpreter raised something else). That says
    # nothing about the sim clock, so it must NOT become a freeze strike.
    # Counted separately and reported in its own words, because a probe that
    # cannot answer is a launcher problem, not a bridge defect.
    *) probe_errors=$((probe_errors + 1)); freeze_strikes=0 ;;
  esac
  [ "$freeze_strikes" -lt 2 ] ||
    fail "the bridge stopped ticking CARLA during bring-up: two consecutive
  world.wait_for_tick(5.0) calls timed out, so the sim clock is frozen and every
  node on sim time is stopped with it. This is the python-bridge sync-tick stall
  (P1 Verdict 1, exclusions.md criterion 4), deliberately NOT patched by this
  campaign; the run is filed crash:cell-launch because it never reached an armed
  window. Localization input nodes present:
$(diagnose_localization_input)"
  [ "$probe_errors" -lt 5 ] ||
    fail "the CARLA tick probe could not run $probe_errors times in a row -- it
  neither confirmed a tick nor timed out waiting for one, so NOTHING is being
  claimed here about the sim clock or about P1 Verdict 1. Check that the
  container is up and that the 0.9.15 client can reach port $BENCH_RPC_PORT:
    docker exec $AW_CONTAINER python3 -c \"import carla; \
carla.Client('localhost', $BENCH_RPC_PORT).get_server_version()\""
  [ "$SECONDS" -lt "$deadline" ] ||
    fail "/localization/kinematic_state never published within ${STACK_TIMEOUT_S}s
  while the sim clock kept advancing (so this is NOT the tick stall).
  Localization input nodes present -- all three of
  crop_box_filter_measurement_range, voxel_grid_downsample_filter and
  random_downsample_filter must be listed, or the load_node race above ate the
  rest of that group and NDT has no input:
$(diagnose_localization_input)
  (check: $BENCH_RUN_DIR/bridge-stage2.log, saved by this launcher)"
  sleep 5
done
echo "OK: bridge stack up on $BENCH_MAP and localizing"
