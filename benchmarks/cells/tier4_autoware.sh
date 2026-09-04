#!/usr/bin/env bash
# The AUTOWARE half of the tier4-native cells (B, B-hf, B45, D) -- the
# BENCH_TIER4_DEMO hook benchmarks/cells/tier4-native.sh refuses to launch
# without. Written by Task 13; the CARLA half stays in tier4-native.sh, which
# has already booted the fork's editor and waited for its RPC port by the time
# this script runs.
#
# It does three things, in this order, and the order is load-bearing:
#
#   1. the fork's own PythonAPI/examples/autoware_demo.py (patched by
#      benchmarks/patches/tier4-native/0003-autoware-demo-params.patch) --
#      spawns the ego + sensor rig and becomes the world's SYNC TICK
#      AUTHORITY. It runs FIRST, unlike the extension path, because
#      `simulator_type:=awsim` gives this stack no autoware_carla_interface
#      and therefore no startup `load_world` that could wipe an ego (blocker
#      #4 of docs/e2e-report.md does not apply here). Running it first also
#      means /clock is already advancing at the harmonised 20 Hz while every
#      use_sim_time node in the stack comes up, instead of those nodes
#      starting against a frozen or free-running clock.
#   2. the Autoware container + `ros2 launch autoware_launch
#      e2e_simulator.launch.xml`, with the DDS transport Task 9 proved is
#      MANDATORY for this family in BOTH directions.
#   3. the single-LiDAR concat relay, then blocks until the stack localizes.
#
# Everything it starts is recorded in a PID file or a container name;
# benchmarks/scripts/teardown.sh stops the demo BEFORE the editor, because the
# demo is the tick authority and a client left ticking a dead server hangs on
# actor destroy (CLAUDE.md's teardown gotcha).
set -euo pipefail

: "${BENCH_REPO:?}" "${BENCH_CELL:?}" "${BENCH_MAP:?}" "${BENCH_RUN_DIR:?}"
# BENCH_ARM is required rather than defaulted: section 5 below keys the
# vector-map delivery gate off it, and an UNSET value would silently skip
# that gate on a closed-loop run -- the exact silent-pass this campaign
# spent thirteen unarmed attempts paying for. cells/tier4-native.sh already
# requires it and forwards it, so this can only fire on a wiring mistake.
: "${BENCH_ARM:?}"
: "${BENCH_RPC_PORT:?}" "${BENCH_ROUTE_FILE:?}" "${BENCH_AUTOWARE_IMAGE:?}"
: "${BENCH_AW_CONTAINER:?}" "${TIER4_DEMO_PID_FILE:?}"

DEMO="$BENCH_CARLA_TREE/PythonAPI/examples/autoware_demo.py"
GT_PYTHON="${BENCH_GT_PYTHON:-$HOME/carla-tier4-venv/bin/python3}"
PHYSICS="$BENCH_REPO/benchmarks/config/physics.yaml"
UDP_ONLY="$BENCH_REPO/benchmarks/observer/config/udp_only.xml"
DEMO_LOG="$BENCH_RUN_DIR/tier4-demo.log"
AW_LOG=/tmp/tier4-autoware.log        # container-side
AW_PIDFILE=/tmp/tier4-autoware.pid    # container-side
RELAY_PIDFILE=/tmp/tier4-concat-relay.pid
RELAY_IN=/sensing/lidar/top/pointcloud_before_sync
RELAY_OUT=/sensing/lidar/concatenated/pointcloud
LIDAR_TOPIC=/sensing/lidar/top/pointcloud_raw_ex

# Autoware's OWN simulation value for pose_initializer's stop check, mounted
# read-only over the image's own copy of the same path below. A campaign-wide
# MEASUREMENT-ENVIRONMENT configuration, mounted IDENTICALLY in all three cell
# families: docker/compose.yaml (A/A-hf/C), here (B/B-hf/B45/D) and
# cells/python-bridge.sh (E/E0/E-opt). Identical in all three IS the
# justification -- a mount present for B but absent for A would make it an
# approach-side change to one half of the primary duel. The override file
# carries its source digest, its single changed line and the upstream
# citations; benchmarks/README.md's "Localization initialization (Task 13)"
# section carries the amendment disclosure.
POSE_INIT_OVERRIDE="$BENCH_REPO/benchmarks/config/autoware/pose_initializer.param.yaml"
POSE_INIT_TARGET=/opt/autoware/share/autoware_launch/config/localization/pose_initializer.param.yaml

# Harmonisation, and the ONE place the numbers cells.yaml registers for this
# family are actually applied (benchmarks/config/cells.yaml metrics.tick_hz /
# lidar_expected_hz / ndt_expected_hz for B/B45/D). Changing either of these
# invalidates those bindings, so they are named here, not inlined below.
#
# TICK is harmonised to cell A's runner/loop.py DEFAULT_FIXED_DELTA = 0.05, so
# the duel does not compare a 20 Hz world against the demo's own 100 Hz
# default (--hz_rate 100, a 5x physics-step difference that would land inside
# every M3 CPU and RTF number).
#
# The LiDAR is NOT re-rated: the demo's sensor_tick 0.1 (10 Hz) stays, because
# its points_per_second is derived FROM that period ("horizontal_fov /
# horizontal_resolution / sensor_tick * channels", autoware_demo.py's own
# comment), so halving the period at a fixed 288000 pts/s would halve the
# angular resolution -- a fidelity change dressed as harmonisation -- while
# doubling pts/s would specify a different sensor than the VLP16 the demo
# documents. The M4 sweep classes (cells.yaml sweep_classes, applying to A and
# B alike) are where the two rigs ARE equalised, via BENCH_TIER4_SWEEP_ARGS.
# Per-message size happens to land within 4% either way (A: 600000 * 0.05 =
# 30000 points/message; B: 288000 * 0.1 = 28800), so M1/M2's per-message
# latency terms compare like with like even at different rates.
TIER4_TICK_HZ=20
TIER4_LIDAR_ROTATION_HZ=10.0

# The demo's default rig carries ONE 1920x1080 traffic-light camera; cell A's
# baseline rig carries no camera at all, and this cell runs perception:=false
# with the clear-road injector, so nothing consumes it. Spawning it would put
# a GPU capture path in B's M3 series that A's does not have. THAT is the whole
# reason for the 0, and it stands on its own: it keeps the two duel cells'
# sensor rigs comparable.
#
# The justification USED to end "...the M4 camera-load arm (cells.yaml
# camera_classes) drives both approaches up from zero instead". That half is now
# stale: the camera-load arm was STRUCK IN FULL 2026-07-30 by the owner's
# core-duel scope cut, so nothing drives either approach up from zero and there
# is no camera axis in this campaign. The setting does not change -- 0 is still
# correct, and now it is simply where every B-family run stays.
TIER4_CAMERAS=0

fail() {
  echo "TIER4 AUTOWARE FAIL ($BENCH_CELL): $*" >&2
  exit 2
}

# ---------------------------------------------------------------------------
# Preflight. Everything that can be wrong before a process starts.
# ---------------------------------------------------------------------------
[ -f "$DEMO" ] || fail "the fork demo is missing: $DEMO"
[ -f "$PHYSICS" ] || fail "substep parity config missing: $PHYSICS"
[ -f "$UDP_ONLY" ] || fail "DDS profile missing: $UDP_ONLY"
[ -f "$BENCH_ROUTE_FILE" ] || fail "route file missing: $BENCH_ROUTE_FILE"
# Checked as a FILE before the mount, not trusted: `docker run -v` on a
# missing host path silently creates a DIRECTORY at the container target, so
# pose_initializer would read the image's own copy (or fail to read a
# directory) and this cell would reproduce the exact refusal the override
# exists to remove -- with the fix apparently in place.
[ -f "$POSE_INIT_OVERRIDE" ] ||
  fail "the campaign-wide pose_initializer override is missing:
  $POSE_INIT_OVERRIDE
  It is a committed file (benchmarks/config/autoware/), mounted identically by
  docker/compose.yaml and cells/python-bridge.sh; restore it rather than
  dropping the mount, which would put this family on a different Autoware
  configuration than the cells it is compared against."
docker image inspect "$BENCH_AUTOWARE_IMAGE" >/dev/null 2>&1 ||
  fail "Autoware image not present locally: $BENCH_AUTOWARE_IMAGE"

# patch 0003 must be APPLIED in the tree, not merely committed here. Checked by
# the flag it adds, so a tree that was reset silently cannot run: without it
# argparse rejects the arguments below and the run dies with an unhelpful
# usage block instead of naming the patch.
grep -q -- "--spawn-pose" "$DEMO" ||
  fail "$DEMO does not accept --spawn-pose: apply
  benchmarks/patches/tier4-native/0003-autoware-demo-params.patch in
  $BENCH_CARLA_TREE (git apply), then re-run."

# The base_link anchor, checked against the DEMO'S OWN SOURCE rather than
# trusted from the harness's registry. This family's demo spawns base_link
# behind the actor origin, and both gt.csv (pose_error) and the localization
# seed below correct for it. A stale registered value biases BOTH by the
# difference and would read as a localization result rather than a harness bug,
# so a drifting literal -- a fork edit, or a future patch that parameterizes
# that spawn offset -- must abort the run instead of being measured. This is the
# same defect class as the one it guards: docs/e2e-report.md issue #6, where an
# uncompensated wheelbase/2 shift cost a 1.44 m G1 near-miss.
PYTHONPATH="$BENCH_REPO" python3 - "$DEMO" <<'ANCHORPY' || fail "the tier4 demo's
  base_link anchor no longer matches benchmarks/analysis/gt_anchor.py's
  registered value for approach tier4-native (see the message above). Do NOT
  edit the registry to silence this without quoting the new source line: it
  anchors every pose_error and the localization seed for the whole B family."
import sys

from benchmarks.analysis.gt_anchor import offset_for_approach, verify_registered_offset

text = open(sys.argv[1]).read()
verify_registered_offset("tier4-native", text)
print(f"OK: base_link anchor {offset_for_approach('tier4-native'):+.8f} m matches {sys.argv[1]}")
ANCHORPY

# The demo imports PyKDL (its IMU mount is a composed KDL frame chain). The
# tier4 client wheel is cp313 and no distro PyKDL exists for that ABI, so this
# is a one-time host prerequisite of the same kind as the wheel itself --
# named with its recipe rather than discovered as a mid-run ImportError.
"$GT_PYTHON" -c "import carla, PyKDL" >/dev/null 2>&1 ||
  fail "$GT_PYTHON cannot import both carla and PyKDL.
  carla: see cells/tier4-native.sh's own message. PyKDL (needed by
  autoware_demo.py's IMU transform chain) has no wheel for this ABI; build it
  against this host's liborocos-kdl 1.5.1:
    git clone --depth 1 -b v1.5.1 \\
      https://github.com/orocos/orocos_kinematics_dynamics.git
    # replace add_subdirectory(pybind11) with
    #   find_package(pybind11 CONFIG REQUIRED)
    # in orocos_kinematics_dynamics/python_orocos_kdl/CMakeLists.txt
    # (the vendored pybind11 predates python 3.13)
    $GT_PYTHON -m pip install pybind11
    cmake -S orocos_kinematics_dynamics/python_orocos_kdl -B build \\
      -DPYTHON_VERSION=3.13 -DPYTHON_EXECUTABLE=$GT_PYTHON \\
      -DPYTHON_INCLUDE_DIR=<py3.13 include> \\
      -DPYTHON_LIBRARY=<py3.13 libpython3.13.so> \\
      -Dpybind11_DIR=\$($GT_PYTHON -m pybind11 --cmakedir)
    cmake --build build -j && cp build/PyKDL.so <venv site-packages>/"

# The map bundle. Resolved through scripts/e2e/map_defaults.sh -- the SAME
# table the extension cells use, deliberately: benchmarks/README.md's confound
# C4 is conditional on whether the B family mounts the bundle cell A localizes
# against, and sharing one table is what makes the answer "yes" verifiable
# rather than asserted. benchmarks/scripts/preflight.sh resolves this family's
# bundle the same way, so the manifest's map_bundle_pin records the bundle this
# launch actually mounts.
# shellcheck source=scripts/e2e/map_defaults.sh disable=SC1091
. "$BENCH_REPO/scripts/e2e/map_defaults.sh"
carla_autoware_map_defaults "$BENCH_MAP"
MAP_DIR="${MAP_DIR:-$MAP_DEFAULT_DIR}"
[ -n "$MAP_DIR" ] ||
  fail "map $BENCH_MAP has no Autoware bundle in scripts/e2e/map_defaults.sh;
  add it there (both the extension and the tier4 cells read that one table)."
MAP_HOST="$HOME/autoware_map/$(basename "$MAP_DIR")"
[ -f "$MAP_HOST/lanelet2_map.osm" ] ||
  fail "map bundle incomplete: $MAP_HOST/lanelet2_map.osm not found"
[ -f "$MAP_HOST/pointcloud_map.pcd" ] ||
  fail "map bundle incomplete: $MAP_HOST/pointcloud_map.pcd not found"

# Transport. MEASURED, and mandatory for this family in BOTH directions
# (benchmarks/patches/tier4-native/README.md, "ROS 2 wire visibility"): the
# fork announces SHM-only user-data locators that ROS 2 Humble's Fast-DDS
# 2.6.11 matches but cannot read, so with shared memory left on, sensing never
# reaches Autoware (matrix row 8) AND control never reaches the fork (the
# ingress table) -- both silently, with every endpoint matched and every log
# healthy. run.sh corrects its own per-invocation default for this family;
# this is the backstop that makes a wrong explicit choice fail loudly instead
# of producing a stack that drives nothing. Same shape as
# cells/python-bridge.sh's refusal of the `lo`-pinned Cyclone profile.
# --- BEGIN registered-transport refusal (pinned by tests/benchmarks/test_vector_map_gate.py)
#
# BENCH_TIER4_TRANSPORT_DEVIATION is the ONE way past this, and it exists for
# ONE thing: a deliberate, non-duel deviation probe that measures this family
# under a different middleware on purpose. It takes a REASON string rather than
# a boolean, it is never set by run.sh or by any cell, and an empty value does
# NOT unlock it -- an exported-but-empty variable must not read as a registered
# reason. Any run that uses it is a deviation from cell B's registered
# transport, its manifest's `transport` block will not match cells.yaml's
# registration, and it can never be duel data. Task 9's matrix (rows 5 and 10)
# is why the refusal exists at all: with the lo-pinned Cyclone profile the
# fork's topics are invisible to this stack; row 11 (cyclone, NO profile) is
# the only non-fastrtps cell in which the fork is readable at all, and that one
# works only via the host's routable NIC with a flaky graph, which is why the
# README says not to use it for measurement.
TIER4_TRANSPORT_DEVIATION="${BENCH_TIER4_TRANSPORT_DEVIATION:-}"
if [ -n "$TIER4_TRANSPORT_DEVIATION" ]; then
  echo "*** DEVIATION from cell $BENCH_CELL's registered transport, on purpose:"
  echo "***   reason : $TIER4_TRANSPORT_DEVIATION"
  echo "***   rmw    : ${BENCH_RMW:-unset} (registered: rmw_fastrtps_cpp)"
  echo "***   profile: ${BENCH_DDS_PROFILE:-none} (registered: $UDP_ONLY)"
  echo "*** This run is NOT a cell-$BENCH_CELL run in the normal sense and must"
  echo "*** never be read as one. duel_admissible stays false."
else
  [ "${BENCH_RMW:-}" = "rmw_fastrtps_cpp" ] ||
    fail "cell $BENCH_CELL must run --rmw rmw_fastrtps_cpp --shm off (got
  BENCH_RMW=${BENCH_RMW:-unset}). With any other middleware the fork's topics
  are invisible to this stack and its control input is undeliverable."
  [ "${BENCH_DDS_PROFILE:-none}" = "$UDP_ONLY" ] ||
    fail "cell $BENCH_CELL needs BENCH_DDS_PROFILE=$UDP_ONLY (got
  ${BENCH_DDS_PROFILE:-none}); that profile is what turns shared memory off."
fi
# --- END registered-transport refusal

# Spawn pose, from the committed route file, in the CARLA frame -- the exact
# six numbers cells/extension.sh feeds the extension runner as --initial-pose,
# so both approaches start the SAME route at the SAME pose. spawn_index is
# accepted too, but a route's spawn pose is generally not a member of the
# map's spawn-point list, so the pose form is what a scored route needs.
SPAWN_ARGS="$(BENCH_ROUTE_FILE="$BENCH_ROUTE_FILE" python3 - <<'PY'
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

mkdir -p "$BENCH_RUN_DIR"

# ---------------------------------------------------------------------------
# 1. the demo: ego + sensor rig + sync tick authority
# ---------------------------------------------------------------------------
# ROS_DOMAIN_ID is pinned ON THIS PROCESS for the same reason
# cells/tier4-native.sh pins it on the editor: this host's login shell exports
# 123 (~/.zshrc:126) and the demo's own client would otherwise be irrelevant
# to it -- but the sensors it spawns publish through the EDITOR's participant,
# so the pin here is belt-and-braces rather than the load-bearing one. It
# costs nothing and removes the variable from the picture.
#
# --substepping AND --substep-config together, deliberately: without
# --substepping the demo takes its "pure step execution" branch and never
# applies the pair at all, so the parity file would be decorative. With both,
# benchmarks/config/physics.yaml's max_substep_delta_time/max_substeps are
# written into WorldSettings -- and CARLA's own condition (fixed_delta 0.05 <=
# 0.001 * 10) then leaves `substepping` false. That is the demo's behaviour,
# recorded in physics.yaml, not something this launcher chooses.
# PYTHONUNBUFFERED is load-bearing, not hygiene. MEASURED 2026-07-30
# (results/B/run-001): the demo's stdout is a FILE here, so CPython
# block-buffers it, and the demo prints only ~600 bytes before entering its
# tick loop -- well under the buffer. Its whole start-up log, "Ego spawned!"
# included, therefore sits unwritten indefinitely, and a readiness check that
# greps this file times out on a world that HAS an ego. That defect cost
# run-001 (excluded crash:cell-launch); the readiness probe below no longer
# depends on the log at all, and this keeps the log itself usable for
# diagnosis.
echo "starting the tier4 demo (ego + sensors + $TIER4_TICK_HZ Hz sync tick)"
# shellcheck disable=SC2086 # BENCH_TIER4_SWEEP_ARGS is a resolved arg list
nohup env ROS_DOMAIN_ID=0 PYTHONUNBUFFERED=1 "$GT_PYTHON" "$DEMO" \
  --port "$BENCH_RPC_PORT" \
  --hz_rate "$TIER4_TICK_HZ" \
  --lidar-rotation-hz "$TIER4_LIDAR_ROTATION_HZ" \
  --cameras "$TIER4_CAMERAS" \
  --substepping --substep-config "$PHYSICS" \
  $SPAWN_ARGS ${BENCH_TIER4_SWEEP_ARGS:-} >"$DEMO_LOG" 2>&1 &
echo $! >"$TIER4_DEMO_PID_FILE"

# Readiness = what every later step actually needs: a CARLA the GT client can
# reach, with the ego spawned. Probed through the world, not by grepping the
# demo's log, for the buffering reason above AND because a bring-up that
# "looks" fine in a log but has no ego must fail HERE and not at run.sh's
# step 7. Same probe, same shared find_ego, as cells/extension.sh.
# world.wait_for_tick() first: a cold client in sync mode can read an empty
# snapshot before its first tick.
echo "waiting up to 180s for CARLA + the tier4 ego"
deadline=$((SECONDS + 180))
until PYTHONPATH="$BENCH_REPO" "$GT_PYTHON" - "$BENCH_RPC_PORT" >/dev/null 2>&1 <<'PY'
import sys

import carla

from scripts.e2e.collect_gt import find_ego

client = carla.Client("localhost", int(sys.argv[1]))
client.set_timeout(10.0)
world = client.get_world()
world.wait_for_tick()
find_ego(world, attempts=1, delay_s=0.0)
sys.exit(0)
PY
do
  if ! kill -0 "$(cat "$TIER4_DEMO_PID_FILE")" 2>/dev/null; then
    fail "the tier4 demo exited during ego spawn. Last lines:
$(tail -20 "$DEMO_LOG" 2>/dev/null)"
  fi
  [ "$SECONDS" -lt "$deadline" ] ||
    fail "no ego with role_name=ego appeared within 180s (see $DEMO_LOG)"
  sleep 5
done
echo "OK: tier4 ego + sensor rig up, world ticking at $TIER4_TICK_HZ Hz"

# ---------------------------------------------------------------------------
# 2. the Autoware container + stack
# ---------------------------------------------------------------------------
# --gpus all because pins.yaml's autoware_universe_devel digest is the CUDA
# variant (see its own note); /work carries the harness so run.sh's
# container-side injector and arm_and_goal invocations resolve, /out is the
# run directory. autoware_data is mounted when present: perception is off, so
# nothing needs the weights, but a launch tree that resolves a param file out
# of it should find it rather than abort.
docker rm -f "$BENCH_AW_CONTAINER" >/dev/null 2>&1 || true
DATA_MOUNT=()
[ -d "$HOME/autoware_data" ] && DATA_MOUNT=(-v "$HOME/autoware_data:/root/autoware_data:ro")
# The transport the container actually runs. On every REGISTERED run the
# refusal above has already pinned BENCH_RMW=rmw_fastrtps_cpp and
# BENCH_DDS_PROFILE=$UDP_ONLY, so this array expands to exactly the
# `-e RMW_IMPLEMENTATION=rmw_fastrtps_cpp -e FASTRTPS_DEFAULT_PROFILES_FILE=...
# -v $UDP_ONLY:/dds-profile.xml:ro` it has always been -- byte-identical, which
# is what keeps every filed B run comparable. It is written as a selection
# rather than a literal ONLY so a registered deviation probe actually gets the
# middleware it asked for instead of a manifest that says one thing while the
# container runs another.
TRANSPORT_ARGS=(-e "RMW_IMPLEMENTATION=${BENCH_RMW:-rmw_fastrtps_cpp}")
case "${BENCH_RMW:-rmw_fastrtps_cpp}" in
  rmw_fastrtps_cpp)
    TRANSPORT_ARGS+=(-e FASTRTPS_DEFAULT_PROFILES_FILE=/dds-profile.xml
      -v "${BENCH_DDS_PROFILE:-$UDP_ONLY}:/dds-profile.xml:ro") ;;
  rmw_cyclonedds_cpp)
    [ "${BENCH_DDS_PROFILE:-none}" = "none" ] ||
      TRANSPORT_ARGS+=(-e CYCLONEDDS_URI=file:///dds-profile.xml
        -v "$BENCH_DDS_PROFILE:/dds-profile.xml:ro") ;;
esac
docker run -d --name "$BENCH_AW_CONTAINER" --gpus all --net=host --ipc=host \
  -e ROS_DOMAIN_ID=0 \
  "${TRANSPORT_ARGS[@]}" \
  -v "$MAP_HOST:$MAP_DIR:ro" \
  -v "$POSE_INIT_OVERRIDE:$POSE_INIT_TARGET:ro" \
  -v "$BENCH_REPO:/work:ro" \
  -v "$BENCH_RUN_DIR:/out" \
  "${DATA_MOUNT[@]}" \
  "$BENCH_AUTOWARE_IMAGE" sleep infinity >/dev/null ||
  fail "could not start the Autoware container $BENCH_AW_CONTAINER"

# Every exec re-exports the transport: `docker exec` inherits the container's
# environment, but run.sh's later `docker exec -e ROS_DOMAIN_ID=0` execs do
# too, and stating it here documents what each of them relies on.
cx() { docker exec -e ROS_DOMAIN_ID=0 "$BENCH_AW_CONTAINER" bash -lc "$1"; }
AW_ENV='source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0'

# Copy the container-side launch log out on every failure path from here on:
# teardown removes the container (cells differ in the image they run under one
# name), which would otherwise destroy the only record of why a bring-up
# failed. Same lesson as cells/python-bridge.sh's save_stage_logs.
save_aw_log() {
  docker cp "$BENCH_AW_CONTAINER:$AW_LOG" "$BENCH_RUN_DIR/tier4-autoware.log" \
    >/dev/null 2>&1 || true
}
fail_with_log() {
  save_aw_log
  fail "$*"
}

cx "test -f $MAP_DIR/lanelet2_map.osm" >/dev/null 2>&1 ||
  fail "the map bundle is not visible in the container at $MAP_DIR"

# simulator_type:=awsim, NOT carla, and that is the whole reason this launcher
# can run the demo first: `carla` would include autoware_carla_interface,
# whose main() calls client.load_world() at startup -- a full world RELOAD
# that wipes every actor including the ego (docs/e2e-report.md blocker #4,
# which scripts/e2e/launch_autoware.sh works around by ordering). The tier4
# fork IS the simulator here (native DDS sensing, native vehicle status,
# native control ingress), which is exactly the contract `awsim` describes,
# and e2e_simulator.launch.xml's own default. It also selects
# config/system/diagnostics/autoware-awsim.yaml, which ships in this image.
#
# sensor_model:=awsim_labs_sensor_kit -- the spec's harmonisation target, and
# the same kit cells A/C run, so benchmarks/README.md's sensing-graph confound
# row is unchanged. Its frames MATCH the demo's mounts: this image's
# awsim_labs_sensor_kit_description and awsim_sensor_kit_description carry
# byte-identical base_link->sensor_kit_base_link (0.9/0/2.0, -0.001/0.015/
# -0.0364), velodyne_top_base_link (yaw 1.575), gnss_link (-0.1/0/-0.2) and
# tamagawa/imu_link (roll/yaw pi) entries -- the exact numbers
# autoware_demo.py composes -- so the documented fallback to
# awsim_sensor_kit is NOT needed and would only differ by the three extra
# LiDARs awsim_labs declares and this rig does not have.
#
# perception:=false is the stock-image workaround the extension path already
# uses (ground segmentation resolves a CUDA-only package eagerly and no DNN
# artifacts ship); the clear-road injector stands in, which is what
# benchmarks/README.md's perception-load confound registers for A/B/C/D.
# launch_vehicle_interface:=false because the fork IS the vehicle interface.
#
# The line after echo $! writes the SAME sidecar
# scripts/e2e/launch_autoware.sh:209-257 writes for the extension family --
# stop_launch_tree.sh's pid-reuse guard compares a recorded pid's /proc
# cmdline against this file (Task 17c, D2). Best-effort and never allowed to
# fail the launch: an absent sidecar only means that guard is skipped, never
# failed (stop_launch_tree.sh's own header), and the sidecar's REMOVAL is
# already that script's job -- this launcher only owes the write.
# cx() sends a DOUBLE-quoted string (unlike compose_exec's single-quoted
# one), so $AW_PIDFILE below expands on the HOST like every other $VAR in
# this call, and only \$-prefixed references are escaped to defer them to
# the container's own /proc at run time.
#
# THE WRITE ITSELF used to race the exec (Task 18b), on this exact shape:
# $! is valid the instant the shell forks the background job, but nohup has
# not yet exec-ed into ros2 -- an immediate cmdline read can record the
# PRE-exec argv ("nohup ros2 launch ...") while stop_launch_tree.sh later
# reads the POST-exec form ("/usr/bin/python3 .../ros2 launch ..."). MEASURED
# live on 5/10 cell-B static runs (results/B/run-017,019,020,021,022): the
# mismatch trips the pid-reuse guard -- correctly, on a racy input -- and a
# real teardown is silently skipped. Same fix as scripts/e2e/launch_autoware.sh
# (see its own comment for the full reasoning): poll for the cmdline to hold
# STEADY for 2 continuous seconds -- 21 identical reads (aw_stable starts at
# 0 and needs 20 MATCHES against the read before it, so the 21st read is the
# first that counts), 0.1s apart -- rewriting the sidecar each time a new
# steady value is reached so a still-settling read mistaken for final gets
# corrected by a later real change, as long as the true post-exec value
# itself goes steady with >= 2s left in the budget. Capped at 50 polls so a
# stuck read cannot hang the bring-up; that cap is a FLOOR, not a ceiling --
# the polls, forks and sleeps measured ~5.17s idle even with nothing to wait
# for, and load stretches it further, never shortens it. Past the cap the
# sidecar can be left holding a STALE pre-exec value, not merely absent (see
# fix round 1, F6.2) -- in theory, but this was not observed even at
# effectively ZERO added delay before this fix existed. Does not touch the
# launched process (no ptrace/strace attach, itself a launch-timing change)
# -- only /proc reads for the pid already recorded. The `|| true` after
# `done` is load-bearing, not decoration: without it, this loop's own exit
# status (a `while` returns its last BODY command's status, and that command
# is `sleep 0.1`) becomes `cx`'s exit status, so one failed fork in the ~200
# this loop forks during the launch's own fork storm would abort a launch
# that actually succeeded (fix round 1, F1).
echo "OK: bringing Autoware up (map $BENCH_MAP, bundle $MAP_DIR) -- log $AW_LOG"
# shellcheck disable=SC2016 # $AW_LOG/$! expand IN the container, on purpose
cx "$AW_ENV
  nohup ros2 launch autoware_launch e2e_simulator.launch.xml \
    map_path:=$MAP_DIR \
    sensor_model:=awsim_labs_sensor_kit vehicle_model:=sample_vehicle \
    simulator_type:=awsim launch_vehicle_interface:=false \
    use_sim_time:=true perception:=false rviz:=false >$AW_LOG 2>&1 &
  echo \$! >$AW_PIDFILE
  aw_cmd=\"\" aw_prev=\"\" aw_stable=0 aw_tries=0
  while [ \"\$aw_tries\" -lt 50 ]; do
    aw_cmd=\"\$(tr '\0' ' ' </proc/\$(cat $AW_PIDFILE)/cmdline 2>/dev/null)\"
    if [ -n \"\$aw_cmd\" ] && [ \"\$aw_cmd\" = \"\$aw_prev\" ]; then
      aw_stable=\$((aw_stable + 1))
      if [ \"\$aw_stable\" -ge 20 ]; then
        printf '%s' \"\$aw_cmd\" >$AW_PIDFILE.cmd 2>/dev/null
      fi
    else
      aw_stable=0
    fi
    aw_prev=\"\$aw_cmd\"
    aw_tries=\$((aw_tries + 1))
    sleep 0.1
  done || true" ||
  fail_with_log "the Autoware launch could not be started"

# ---------------------------------------------------------------------------
# 3. transport check, concat relay, localization
# ---------------------------------------------------------------------------
# The fork's own topic, read from INSIDE the stack's container, before the
# multi-minute localization wait. This is the one check that separates "the
# transport is wrong" from "the stack is slow": with shared memory on it
# returns nothing while every endpoint matches (Task 9 matrix row 8), and
# without it that mistake surfaces 7 minutes later as "never localized".
# --no-daemon is load-bearing: a ros2cli daemon started during bring-up caches
# an empty node graph and answers every later call from it (measured twice in
# this campaign).
echo "waiting up to 120s for $LIDAR_TOPIC to be readable in the container"
deadline=$((SECONDS + 120))
until cx "$AW_ENV
  timeout 20 ros2 topic echo --once --no-daemon $LIDAR_TOPIC >/dev/null 2>&1" \
  >/dev/null 2>&1; do
  if [ "$SECONDS" -ge "$deadline" ] ||
    ! kill -0 "$(cat "$TIER4_DEMO_PID_FILE")" 2>/dev/null; then
    fail_with_log "$LIDAR_TOPIC never delivered a sample into the Autoware
  container. If the demo is still alive and the editor is still up, this is
  the SHM interop fault of Task 9's matrix row 8 -- check that
  FASTRTPS_DEFAULT_PROFILES_FILE really reached the container:
    docker exec $BENCH_AW_CONTAINER printenv FASTRTPS_DEFAULT_PROFILES_FILE
  Demo tail:
$(tail -5 "$DEMO_LOG" 2>/dev/null)"
  fi
  sleep 5
done
echo "OK: the fork's LiDAR is readable inside the stack (Task 9 rung 1 holds)"

# Single-LiDAR concatenation, blocker #2 of docs/e2e-report.md: the awsim_labs
# concatenate node HARD-REQUIRES >= 2 input topics and never loads with one,
# so the single per-LiDAR cloud is relayed straight onto the topic the
# localization chain consumes. Frame-correct without a transform: RELAY_IN is
# already in base_link, the concat node's own output frame.
#
# *** THAT PREMISE IS REFUTED. MEASURED 2026-07-30 (results/B/run-012). ***
# The concatenate node DOES load and DOES publish. Probed from inside the
# container while this relay was running:
#
#   /sensing/lidar/concatenated/pointcloud  publishers=2 subscribers=1
#     PUB node=/sensing/lidar/concatenate_data
#     PUB node=//relay
#
# So RELAY_OUT -- which is NDT's input -- carries TWO publishers, this relay
# and the node this comment says cannot exist. That is the measured
# explanation for a rate on that topic (4.89 Hz) which is neither the fork's
# 10 Hz nor a clean fraction of the 2.77 Hz stage feeding the relay: it is the
# sum of two sources. If concatenate_data emits empty or single-frame clouds,
# NDT is fed an alternating mix of usable and unusable inputs, which would
# depress its output rate independently of any CPU effect.
#
# DELIBERATELY NOT FIXED HERE. Removing or gating either publisher changes
# what this cell measures, so it needs its own decision rather than a
# mid-round edit; benchmarks/README.md's "Sensing-chain rate deficits"
# section carries the finding and its evidence. The refuted premise is left
# above rather than deleted, per the campaign's convention that refuted
# hypotheses stay in the record WITH what refuted them -- annotated here
# because this is where a reader acts on it.
#
# Same sidecar shape as the Autoware launch step above (Task 17c, D2): a
# best-effort, never-fatal write of the recorded pid's /proc cmdline, for
# stop_launch_tree.sh's pid-reuse guard.
#
# SAME FORK/EXEC RACE AS THE AW_PIDFILE WRITE ABOVE (fix round 1, F3) --
# this is `nohup ... &` too, so it gets the identical hold-STEADY-for-2s,
# capped-at-50-polls loop; see the AW_PIDFILE comment above for the full
# mechanism, including why the trailing `|| true` after `done` is required
# (F1) and the exec-count/cap-outcome corrections (F6.2-3).
#
# BLAST RADIUS, stated so this reads as scoped rather than alarming (fix
# round 1, F3): a surviving relay is worse than an ordinary survivor
# because it keeps publishing onto RELAY_OUT, NDT's own input topic, where
# a SECOND publisher is already a measured, gate-relevant variable in this
# file (the "THAT PREMISE IS REFUTED" note above -- publishers=2 -> 4.89
# Hz). But cell B is bounded TWICE against a survivor outliving a run:
# teardown.sh:361's `docker rm -f` (taken because tier4-native.sh:144 sets
# AW_COMPOSE="") and this file's own container removal before the next
# `docker run` (:323) both clear it even if teardown never ran at all --
# the duel is not at cross-run risk. What a same-run survivor would do to
# THAT run's own NDT rate is not established from code -- duplicate
# identical clouds may be benign or may compound the mixed-source rate
# defect above; that needs a live stack, correctly left open by this round.
cx "$AW_ENV
  nohup ros2 run topic_tools relay $RELAY_IN $RELAY_OUT \
    >/tmp/tier4-concat-relay.log 2>&1 &
  echo \$! >$RELAY_PIDFILE
  rel_cmd=\"\" rel_prev=\"\" rel_stable=0 rel_tries=0
  while [ \"\$rel_tries\" -lt 50 ]; do
    rel_cmd=\"\$(tr '\0' ' ' </proc/\$(cat $RELAY_PIDFILE)/cmdline 2>/dev/null)\"
    if [ -n \"\$rel_cmd\" ] && [ \"\$rel_cmd\" = \"\$rel_prev\" ]; then
      rel_stable=\$((rel_stable + 1))
      if [ \"\$rel_stable\" -ge 20 ]; then
        printf '%s' \"\$rel_cmd\" >$RELAY_PIDFILE.cmd 2>/dev/null
      fi
    else
      rel_stable=0
    fi
    rel_prev=\"\$rel_cmd\"
    rel_tries=\$((rel_tries + 1))
    sleep 0.1
  done || true" ||
  fail_with_log "the single-LiDAR concat relay could not be started"
echo "OK: concat relay $RELAY_IN -> $RELAY_OUT"

# Seed localization at the ego's CARLA ground-truth pose. NOT optional and not
# a shortcut -- MEASURED 2026-07-30 (results/B/run-002 and run-003, both
# excluded crash:cell-launch): without it this stack never localizes at all,
# for a reason that is neither the fork's nor this launcher's, and the two
# obvious ways of doing it BOTH fail on this image. The full evidence, with the
# probe counts, is in benchmarks/injector/seed_localization.py's module
# docstring; in short:
#
#   - Autoware's own automatic initializer calls AD-API
#     /api/localization/initialize, which is refused every 1-3 s with 'The
#     vehicle is not stopped.' because its stop check reads
#     /localization/kinematic_state -- the EKF output that only exists once
#     localization HAS initialized. A deadlock, and not specific to this cell.
#     The ego was measured stationary to 3.7e-12 m/s at the time.
#   - Publishing /initialpose (what scripts/e2e/reseed_localization.py does for
#     the extension cells) does not reach pose_initializer on this image at
#     all: that node subscribes only /sensing/gnss/pose_with_covariance and
#     /sensing/vehicle_velocity_converter/twist_with_covariance. run-003 seeded
#     it seven times and NDT never published a pose.
#
# So the seed goes to /localization/initialize, pose_initializer's own service.
# Neither approach publishes /initialpose or self-initializes (both publish only
# /sensing/gnss/pose{,_with_covariance} and /vehicle/status/*), so seeding here
# puts A and B on IDENTICAL footing rather than giving B something A does not
# get -- and cell A's launcher will need the same step (Task 20). It uses the
# shared affine (scripts/e2e/verify_mgrs_handedness.offset_for_map +
# collect_gt.ego_map_xy, yaw_map = -yaw_carla), which is exactly what
# scripts/e2e/arm_closed_loop.sh step 1 computes for the extension cells.
SEED="$(
  PYTHONPATH="$BENCH_REPO" CARLA_AUTOWARE_MAP="$BENCH_MAP" \
    BENCH_RPC_PORT="$BENCH_RPC_PORT" "$GT_PYTHON" - <<'SEEDPY'
import math
import os

import carla

from benchmarks.analysis.gt_anchor import (
    base_link_from_actor_origin,
    offset_for_approach,
)
from scripts.e2e.collect_gt import ego_map_xy, find_ego
from scripts.e2e.verify_mgrs_handedness import offset_for_map

offset = offset_for_map()
client = carla.Client("localhost", int(os.environ["BENCH_RPC_PORT"]))
client.set_timeout(10.0)
world = client.get_world()
world.wait_for_tick()
tf = find_ego(world).get_transform()
x, y = ego_map_xy(tf.location.x, tf.location.y, offset)
z = offset[2] + tf.location.z
yaw = math.radians(-tf.rotation.yaw)
# pose_initializer's contract is a BASE_LINK pose, and this family's demo puts
# base_link BEHIND the actor origin, so the raw actor pose is the wrong point.
# Same registry gt.csv uses (benchmarks.analysis.gt_anchor), so the seed and
# pose_error cannot drift apart. MEASURED consequence of omitting it
# (results/B/run-006): the service SUCCEEDED and NDT locked, then the seed's own
# 1.0 m convergence check failed at 1.4879 m -- NDT had converged to the true
# base_link while the target still named the actor origin.
x, y = base_link_from_actor_origin(x, y, yaw, offset_for_approach("tier4-native"))
print(f"{x:.3f} {y:.3f} {z:.3f} {yaw:.6f}")
SEEDPY
)" || fail_with_log "could not read the ego's ground-truth pose for the seed"
echo "seeding localization at the ego's ground-truth map pose: $SEED"

# Retried, because pose_initializer may still be loading and its service does
# not exist until it is. SEED is four space-separated numbers by construction,
# so the word-splitting below is intended.
SEED_TIMEOUT_S=420
deadline=$((SECONDS + SEED_TIMEOUT_S))
seeded=0
while [ "$SECONDS" -lt "$deadline" ]; do
  # shellcheck disable=SC2086
  if cx "$AW_ENV
    python3 /work/benchmarks/injector/seed_localization.py --pose $SEED --timeout 90"; then
    seeded=1
    break
  fi
  kill -0 "$(cat "$TIER4_DEMO_PID_FILE")" 2>/dev/null ||
    fail_with_log "the tier4 demo died while seeding localization. Demo tail:
$(tail -20 "$DEMO_LOG" 2>/dev/null)"
  echo "      seed did not take yet; retrying"
done
[ "$seeded" = "1" ] ||
  fail_with_log "localization never initialized from the seeded ground-truth
  pose in ${SEED_TIMEOUT_S}s. The fork's LiDAR WAS readable in the container
  (checked above) and the seed goes to pose_initializer's own service, so this
  is a LOCALIZATION failure rather than a transport or an initializer-routing
  one -- the cloud reaching NDT, or the bundle it is matched against, or the
  seed's own affine.
  BUT CHECK THIS FIRST, and the run's own tier4-autoware.log answers it.
  MEASURED 2026-07-30 (results/B/run-005, excluded crash:cell-launch): there
  is a THIRD cause that looks identical from here and is neither of the above
  -- pose_initializer WEDGED during its own start-up, before it can serve any
  request. Its deactivation handshake with ndt_scan_matcher lost a service
  RESPONSE at the rmw layer:
    grep -n 'client will not receive response' <run>/tier4-autoware.log
  On run-005 that fired three times inside one 0.4 s window at peak bring-up
  (mrm_emergency_stop_operator/_container/load_node,
  pointcloud_container/_container/load_node, and the decisive
  /localization/pose_estimator/trigger_node), with the host at loadavg 64.
  The signature is pose_initializer's OWN log stopping mid-handshake --
    grep 'localization.util.pose_initializer]' <run>/tier4-autoware.log
  showed 'EKF triggering service is available!' -> 'EKF Deactivation
  succeeded' -> 'NDT triggering service is available!' and then NOTHING (no
  'NDT Deactivation succeeded'), with the process blocked in futex_do_wait.
  A wedged node still ADVERTISES the service, so the seed discovers it, calls
  it, and every attempt reports 'no response (spin timed out)' rather than a
  refusal -- and RETRYING CANNOT RECOVER IT, because the executor never
  returns. So: refusal text => a real precondition; 'no response' on every
  attempt + a truncated pose_initializer log => this wedge, which is the same
  dropped-rclcpp/rmw-response class as results/E/run-003 and did not reproduce
  on the next bring-up. Recycle the stack on a QUIET host; do not tune
  SEED_TIMEOUT_S, which only buys more attempts against a dead executor.
  Localization nodes present:
$(cx "$AW_ENV
    ros2 node list --no-daemon 2>/dev/null | grep '^/localization/' | sort" 2>/dev/null || true)"
echo "OK: NDT locked on the seeded pose"

# Readiness = the stack is up AND localizing. One message is the weakest
# signal that means both; run.sh's arm step then applies its own sustained
# rate criterion on top, so this does not subsume it. A timeout here is a
# launcher readiness failure, which run.sh files crash:cell-launch -- never
# as an arm failure, which would read as "this approach cannot localize".
# Reached with NDT already locked, so this is the EKF's own activation.
STACK_TIMEOUT_S=300
echo "waiting up to ${STACK_TIMEOUT_S}s for /localization/kinematic_state"
deadline=$((SECONDS + STACK_TIMEOUT_S))
until cx "$AW_ENV
  timeout 20 ros2 topic echo --once --no-daemon \
    /localization/kinematic_state >/dev/null 2>&1" >/dev/null 2>&1; do
  kill -0 "$(cat "$TIER4_DEMO_PID_FILE")" 2>/dev/null ||
    fail_with_log "the tier4 demo died during Autoware bring-up, so the world
  stopped ticking and every use_sim_time node stopped with it. Demo tail:
$(tail -20 "$DEMO_LOG" 2>/dev/null)"
  [ "$SECONDS" -lt "$deadline" ] ||
    fail_with_log "/localization/kinematic_state never published within
  ${STACK_TIMEOUT_S}s. The fork's LiDAR WAS readable in the container (checked
  above), so this is not the transport. Localization input nodes present -- all
  of crop_box_filter_measurement_range, voxel_grid_downsample_filter and
  random_downsample_filter must be listed, or a composable-node load was
  dropped and NDT has no input:
$(cx "$AW_ENV
    ros2 node list --no-daemon 2>/dev/null | grep '^/localization/util/' | sort" 2>/dev/null || true)
  (log saved to $BENCH_RUN_DIR/tier4-autoware.log)"
  sleep 5
done

# ---------------------------------------------------------------------------
# 5. /map/vector_map re-publish + delivery gate -- CLOSED-LOOP ARM ONLY
# ---------------------------------------------------------------------------
# A HARNESS-INJECTED WORKAROUND FOR A MEASURED TRANSPORT DEFECT. It is not a
# gate adjustment, not a threshold change, and it does not touch the DDS
# profile: `transport.dds_profile_sha256` stays byte-identical in every
# manifest, so this cell's already-filed runs remain transport-comparable.
#
# THE DEFECT, MEASURED (Task 4b, 2026-08-01; full evidence, every raw capture
# and the refuted alternatives in benchmarks/evidence/b-vector-map-delivery/):
# `/map/lanelet2_map_loader` publishes ONE 1 305 281-byte LaneletMapBin from
# its constructor, RELIABLE / KEEP_LAST(1) / TRANSIENT_LOCAL, and every
# subscriber in the stack -- behavior_path_planner included, read off the live
# graph -- asks for exactly that QoS, so there is NO durability mismatch. A
# late-joining subscriber with that QoS got the retained sample 9 times out of
# 9 (0.028-2.643 s). What is unreliable is delivery to subscribers that ALREADY
# EXIST when that single publication happens. On the in-stack
# /system/topic_state_monitor_vector_map, same QoS, first receipt relative to
# `Map is published.` over six Fast-DDS udp_only bring-ups was
#
#   +20.2s (run-028) | NEVER +98.2s (run-029) | +11.5s (run-030) |
#   NEVER +113.35s (replica V1) | +0.97s (replica V1b) | +0.05s (replica p2)
#
# -- TWO OUTRIGHT FAILURES IN SIX, and REPRODUCED STANDALONE with the same
# image, bundle and launch line, no CARLA and no harness at all (V1 vs V1b are
# consecutive runs of one script two minutes apart). That localises it to the
# rmw_fastrtps_cpp + observer/config/udp_only.xml transport this family alone
# runs; A/C/E run rmw_cyclonedds_cpp, and a cyclonedds control delivered at
# +0.24s (n=1, NOT a claim of immunity).
#
# WHY A RE-PUBLISH RATHER THAN A PROFILE CHANGE. The only path measured failing
# is Fast-DDS's TRANSIENT_LOCAL historical delivery on match. Re-publishing
# after the readers are matched turns the map into ordinary LIVE data -- the
# path the rest of this stack uses successfully at 20 Hz. Editing udp_only.xml
# was the obvious alternative and is REJECTED above; the 16 MiB socket-buffer
# variant was tried once and proves nothing against a 2-in-6 failure.
#
# HONEST LIMIT, kept here because a reader acts on this file: the re-publish
# creates a NEW writer, and an already-running reader must still match it --
# the same ordering that fails for map_loader. What differs is that the helper
# WAITS for its own subscriber matching to settle BEFORE publishing, so the
# sample goes out as live data to already-matched readers. That is a reasoned
# mitigation, NOT a demonstrated cure.
#
# THIS STEP WAS ONCE FATAL, AND IS NOW ADVISORY. It originally failed the
# bring-up when the verification did not take. results/B/run-031 refuted that
# design from its own log: the step failed (3 attempts, 60 s each, its
# verification endpoint never OK) while THE SAME RUN delivered the re-published
# map to lanelet2_map_visualization (:1123, :2149, :3147) and
# vector_map_tf_generator (:1128, :2155, :3152) on all three attempts -- a
# different process each time, so real inter-process receipt. The fatal form
# turned a possibly-armable run into a crash:cell-launch and, because it fires
# BEFORE any route exists, left the actual question untested: that run's
# behavior_path_planner logged `waiting for scenario_topic` 38 times and never
# evaluated its map check at all. The campaign's pass criteria are the arm
# succeeding and control_cmd flowing; this step is an ADDED precondition and is
# not one of them, so it now records and continues. If the map never reaches
# the planner the run still fails -- at the arm, more informatively.
#
# AND WHAT THE VERIFICATION CANNOT SEE: it reads topic_state_monitor, which is
# the same CLASS as behavior_path_planner but is not the planner --
# results/B/run-028 has the monitor recovering at +23.2s in a run where the
# planner reported `waiting for map` for 53.3s more, to teardown. The planner's
# own report only exists once a route is set, i.e. after this step.
#
# CLOSED-LOOP ONLY, and that is a SAFETY property rather than a preference.
# THREE DISTINCT COUNTS get confused here, so each is named: cell B has 17
# non-excluded STATIC runs, of which 10 (run-013..run-022) are the
# DUEL-ADMISSIBLE static verdict pool, and 0 statics are excluded. It is the
# 10-run pool the A-vs-B static verdict is computed from; all 17 were measured
# without this step. Branch (c) forbids recollecting them, so the static
# bring-up must not acquire a step. (Recomputed from every manifest, 2026-08-01;
# an earlier revision of this comment said "fifteen", which matches none of the
# three.)
# tests/benchmarks/test_vector_map_gate.py executes THIS block for real, with
# both arms, and asserts the static one reaches no container command at all.
#
# /out is the run-directory bind-mount, so the pre-state snapshot and the
# verification record become filed evidence instead of terminal output -- the
# gap §7.6 recorded when a real observation had no filed artifact behind it.
if [ "${BENCH_ARM:-}" = "closed-loop" ]; then
  echo "closed-loop arm: re-publishing /map/vector_map (ADVISORY -- never aborts)"
  if cx "$AW_ENV
    python3 /work/benchmarks/injector/republish_vector_map.py \
      --settle-s 5 --capture-timeout-s 90 --match-timeout-s 60 \
      --verify-timeout-s 60 --attempts 3 --advisory \
      --launch-log $AW_LOG --report /out/vector-map-delivery.json"; then
    # RAN is not VERIFIED, and this message may not blur the two. Under
    # --advisory the node's _finish returns EXIT_OK for EVERY verdict it can
    # reach, so this branch is taken on 0, 3, 4 and 5 alike -- including
    # EXIT_NO_CAPTURE, where nothing was ever published. An earlier revision
    # said "step completed", which reads as success and is true of a run whose
    # capture never happened. verdict_code is the outcome; this is only that
    # the process got far enough to write one.
    echo "OK: the /map/vector_map re-publish step RAN AND RECORDED A VERDICT" \
      "-- which is NOT the same as the map being verified. Under --advisory" \
      "the node exits 0 for every verdict it can reach, so read verdict_code" \
      "in $BENCH_RUN_DIR/vector-map-delivery.json: 0 verified (and the" \
      "verified / verified_relog keys name which oracle saw it), exit 3 the" \
      "capture never happened, 4 the publisher matching never settled," \
      "5 the verification never went OK. Only 0 means the map was observed" \
      "to arrive."
  else
    # What actually reaches here, stated precisely: NOT verdicts 3/4/5. With
    # --advisory the node returns EXIT_OK for all of those, so they take the
    # branch above. This branch is the PROCESS failing -- a crash before or
    # during the report write, or `cx` never running the command at all. An
    # earlier revision enumerated 3/4/5 here, which no reader could ever have
    # observed.
    echo "ADVISORY: the /map/vector_map re-publish step did not complete" \
      "cleanly. NOT fatal, by design (see section 5's header): the campaign's" \
      "pass criteria are the arm and control_cmd, and this is an added" \
      "precondition. Continuing to the arm, where the planner reports on the" \
      "map itself via 'waiting for map' once a route exists." \
      "This branch is NOT verdict_code 3/4/5 -- with --advisory those all" \
      "exit 0 and take the branch above. Reaching here means the PROCESS" \
      "failed: a crash before or during the report write (verdict_code 6)," \
      "or the container command itself never running. So" \
      "$BENCH_RUN_DIR/vector-map-delivery.json may hold a crash stub, or be" \
      "absent entirely."
  fi
fi

save_aw_log
echo "OK: tier4 Autoware stack up on $BENCH_MAP and localizing"
