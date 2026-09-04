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

# The base_link anchor. This family's registered offset is 0.0 -- gt.csv is an
# exact identity -- and that is true ONLY because runner/ applies no
# vehicle-frame shift. It once did: an uncompensated +wheelbase/2 biased NDT's
# base_link and cost a 1.44 m G1 near-miss (docs/e2e-report.md issue #6), fixed
# by DELETING base_link_to_vehicle_center / SAMPLE_VEHICLE_WHEELBASE /
# ego_wheelbase(). Checked here because their return would silently rebias
# every cell-A pose_error by ~1.4 m while the registry still said 0.0 -- and
# promoted numbers were measured under that 0.0 assumption.
PYTHONPATH="$BENCH_REPO" python3 - "$BENCH_REPO/runner/kit.py" \
  "$BENCH_REPO/runner/spawn.py" <<'ANCHORPY' || fail "the extension's base_link
  anchor assumption no longer holds (see the message above).
  benchmarks/analysis/gt_anchor.py registers 0.0 for approach extension; if
  runner/ must reintroduce a vehicle-frame shift, register the new offset there
  deliberately AND re-derive G1/G2, which were measured under 0.0."
import sys

from benchmarks.analysis.gt_anchor import offset_for_approach, verify_registered_offset

text = "".join(open(p).read() for p in sys.argv[1:])
verify_registered_offset("extension", text)
print(f"OK: base_link anchor {offset_for_approach('extension'):+.8f} m (no vehicle shift)")
ANCHORPY

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
#
# OWNED 2026-08-03 (Task 6, P4 spec 1e): the paragraph above is kept as the
# strike-history record -- "does not accept them yet" reads historically,
# not currently, now that the mapping below exists (the extension side was
# owed to Task 12 per that paragraph; tier4-native.sh's identical mapping
# was owed to Task 26, struck 2026-07-30 -- both are this same task now).
#
# Class id -> sensor arguments, derived HERE (registered 2026-08-03, P4
# spec 1e -- the residue of struck Task 26, now owned). Explicit env still
# wins; an id with no mapping still refuses, because an unmapped class
# would file a run under the WRONG workload label (a false measurement,
# not an out-of-scope one). Rotation frequency stays at each family's
# registered contract; a class pins channels + points_per_second only
# (cells.yaml sweep_classes).
if [ -n "${BENCH_CLASS_ID:-}" ] && [ -z "${BENCH_RUNNER_SWEEP_ARGS:-}" ]; then
  case "$BENCH_CLASS_ID" in
    vlp16) BENCH_RUNNER_SWEEP_ARGS="--lidar-channels 16 --lidar-pps 288000" ;;
    32ch)  BENCH_RUNNER_SWEEP_ARGS="--lidar-channels 32 --lidar-pps 1200000" ;;
    *) fail "--class $BENCH_CLASS_ID has no registered sensor-argument
    mapping (vlp16 and 32ch are registered; 128ch is struck on either
    branch)" ;;
  esac
fi

# --------------------------------------------------------------------------
# The M4 sweep's ABLATION arm (registered in cells.yaml `sweep_arms`): the
# identical LiDAR rig with PUBLISHING DISABLED, so the sweep can decompose
# `transport cost = total - baseline`. This branch boots the cell's CARLA side
# from the same fork tree the normal path uses, MINUS Autoware, MINUS the
# ego-spawning runner and MINUS the whole ROS 2 layer, and then runs
# benchmarks/scripts/raycast_baseline.py as the world's only client and only
# tick authority.
#
# THREE CLAIMS IN THIS HEADER WERE SUPERSEDED (2026-08-03, corrected by the P4
# whole-branch review). They are the arm's PRE-FIX description; a later fix
# updated the code and the inner comments and left this block standing. Quoted
# verbatim, because they record what the arm was designed to be and the
# difference is the finding:
#
#   SUPERSEDED (1): "the same fork tree, the same extension .so, the same
#   `--ros2 --rmw=cyclonedds` server".
#   SUPERSEDED (2): "every gate that invocation is fronted by is re-run here
#   (see the artifact gate and the ABI preflight in the ablation block)".
#   SUPERSEDED (3), from the "Why not simply" paragraph below, where the
#   correction is applied in place rather than quoted a second time: the editor
#   invocation here was "run_e2e.sh's own, line for line, with the runner and
#   the Autoware bring-up dropped". It is no longer line for line -- the ROS 2
#   flags are dropped too, which is what (1) is about.
#
# On (1): the editor line in the ablation block below carries NO `--ros2`, no
# `--rmw` and no `--ros2-extension` -- see the MEASURED 2026-08-03 note there.
# The extension .so is NOT loaded on this arm, deliberately: it IS the native
# publisher layer, so it belongs on the `total` side of the decomposition, not
# in the baseline. Only the fork TREE is shared.
# On (2): exactly ONE of run_e2e.sh's two preflights is re-run here -- the
# stale-.so editor-artifact gate, which is load-bearing because it checks
# libUnrealEditor-Carla.so, the plugin that implements the sensors and the
# raycast. The OTHER (`--extension-check`, the extension .so's ABI) is
# deliberately NOT run, for the reason its own comment in the ablation block
# gives: this arm never dlopens that file, so gating on it would assert
# something the run does not depend on. "Every gate" was true of the boot the
# sentence described and is not true of the boot the code performs.
#
# Why not simply `WITH_AUTOWARE=0 bash scripts/e2e/run_e2e.sh`: that path still
# ends in `python3 -m runner`, which spawns the ego with the fork's native ROS 2
# publisher attributes on the LiDAR -- and it passes `--ros2 --rmw=cyclonedds
# --ros2-extension` unconditionally besides. The baseline would then pay the
# whole transport cost it exists to subtract, and `total - baseline` would
# collapse to ~0. The editor invocation below is run_e2e.sh's own with the ROS 2
# flags, the runner and the Autoware bring-up dropped, and the artifact gate
# re-run, because preflight.sh does NOT run the extension family's
# editor-artifact gate itself -- it reaches it through
# `cells/extension.sh -> run_e2e.sh:126` (preflight.sh:295), which this branch
# bypasses. Without re-running it, the ablation arm would be the one path in
# this campaign that can boot a stale editor .so.
BENCH_ARM_IS_ABLATION=0
[ "$BENCH_ARM" = "ablation" ] && BENCH_ARM_IS_ABLATION=1
ABLATION_PID_FILE="$BENCH_RUN_DIR/raycast_baseline.pid"
ABLATION_LOG="$BENCH_RUN_DIR/raycast_baseline.log"
ABLATION_TICK_HZ=""
# A CAP on the client's tick loop, not the scoring window (run.sh step 10 owns
# that: 140 s on any non-static arm). It only bounds how long an orphaned
# client -- teardown missed, launcher gone -- can keep ticking a server nobody
# is watching.
ABLATION_DURATION_S="${BENCH_ABLATION_DURATION_S:-600}"
ABLATION_READY_S=120
if [ "$BENCH_ARM_IS_ABLATION" = "1" ]; then
  # The client is the GT collector's interpreter -- the one whose `carla`
  # module matches the server this cell boots, already resolved and
  # import-checked above. Checked again by IMPORTING the module it will run:
  # raycast_baseline pulls in runner.kit/runner.loop/runner.spawn (and so
  # yaml), and a venv missing any of them must fail HERE, in plan, not after a
  # 2-5 minute editor boot.
  PYTHONPATH="$BENCH_REPO" "$GT_PYTHON" -c \
    "import benchmarks.scripts.raycast_baseline" >/dev/null 2>&1 ||
    fail "$GT_PYTHON cannot import benchmarks.scripts.raycast_baseline (the
  ablation client). It needs this repo on PYTHONPATH plus PyYAML; set
  BENCH_GT_PYTHON to an interpreter that has the fork's 0.10 client wheel AND
  can import runner.kit."

  # The stale-.so gate run_e2e.sh:126 fronts every live extension run with. It
  # checks libUnrealEditor-Carla.so -- the CARLA plugin that implements the
  # sensors and the raycast -- so it is load-bearing here even though this arm
  # does not load the ROS 2 extension .so. run_e2e.sh's OTHER preflight
  # (`--extension-check`, the extension .so's ABI) is deliberately NOT run:
  # this arm boots without --ros2-extension, so that file is never dlopen'd and
  # a gate on it would assert something this run does not depend on.
  CARLA_ROOT="$BENCH_CARLA_TREE" \
  CARLA_UNREAL_ENGINE_PATH="${CARLA_UNREAL_ENGINE_PATH:-$HOME/src/UnrealEngine}" \
    bash "$BENCH_REPO/scripts/e2e/verify_editor_artifact.sh" ||
    fail "the editor-artifact gate refused this run (named reason above)"

  # sweep_verdict.py scores paced and ablation at the SAME paced tick target
  # (its `manifest.arm == "unpaced"` branch is the only one that substitutes
  # tick_rate_ratio), so the client's fixed delta must be the cell's REGISTERED
  # metrics.tick_hz -- read from cells.yaml here, never a literal, and a null
  # binding refuses rather than picking a plausible number.
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
fi

# Spawn pose comes from the committed route file, so the cell starts where
# the route was scored. run_e2e.sh takes it through RUNNER_EXTRA_ARGS
# (--initial-pose x y z roll pitch yaw_deg, CARLA frame). The ablation client
# takes the SAME string (it accepts --initial-pose/--spawn-index with the
# runner's own spelling), so both arms start the rig at one pose.
#
# PRECEDENCE IS POSE-FIRST, and it is not free choice: it must match what
# cells/tier4_autoware.sh derives for the OTHER family, whose comment states
# the reason -- "a route's spawn pose is generally not a member of the map's
# spawn-point list, so the pose form is what a scored route needs". This block
# read `spawn_index` first until 2026-08-04, inverted against BOTH tier4
# derivations. It was a latent no-op only because every committed route sets
# `spawn_index: null` (config/routes/*.yaml); a route setting both would have
# started cell A at the map's spawn point and cell B-cyc at the scored pose,
# changing what each ray terminates on and therefore the very `T - B` the
# ablation arm subtracts -- silently, on a run that completes and scores.
# All three derivations are now pinned together by
# tests/benchmarks/test_raycast_baseline.py's spawn-precedence test.
SPAWN_ARGS="$(BENCH_ROUTE_FILE="$BENCH_ROUTE_FILE" python3 - <<'PY'
import os

import yaml

route = yaml.safe_load(open(os.environ["BENCH_ROUTE_FILE"]))
pose = route.get("spawn_pose")
index = route.get("spawn_index")
if pose:
    print(f"--initial-pose {pose['x']} {pose['y']} {pose['z']} 0 0 {pose['yaw_deg']}")
elif index is not None:
    print(f"--spawn-index {int(index)}")
else:
    raise SystemExit("route file has neither spawn_pose nor spawn_index")
PY
)" || fail "could not derive the spawn pose from $BENCH_ROUTE_FILE"

# The four harness switches the ablation arm flips, each for a reason run.sh
# acts on directly:
#   ARM_ENABLED=0      step 9 has no stack to arm -> "(nothing to arm for this
#                      cell)", and the post-engage control_cmd probe is skipped.
#   INJECTOR_ENABLED=0 there is no Autoware container; the step-8 `docker exec`
#                      would fail and exclude the run gate:injector-failed.
#   GT_ENABLED=0       a second CARLA client would add load to the very
#                      measurement this arm isolates; it also switches step 15's
#                      smoke off its gt.csv assertion (BENCH_GT_EXPECTED).
#   GT_COUNT_LIDAR=0   publisher_counts.json must be ABSENT. sweep_verdict.py
#                      reads an absent file as "not measurable" (ratio 1.0), and
#                      a file-backed 0 as REAL zero throughput -- which would
#                      fire the ceiling's publisher disjunct on a run that
#                      never intended to publish.
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

# The EDITOR's own stdout/stderr, for teardown.sh to file as carla-editor.log.
# ARM-DEPENDENT, and that is the point: the ablation arm launches the editor
# itself, straight into $LAUNCH_LOG (:372-374 below), so its editor output is
# ALREADY in the run directory and EDITOR_LOG must stay EMPTY there -- pointing
# it at the shared /tmp path on that arm would file a stale log left by
# whichever run last used run_e2e.sh. The normal path (:460) hands the editor
# to run_e2e.sh, which redirects it to that fixed path
# (scripts/e2e/run_e2e.sh:24) and overwrites it on every boot; nothing filed it
# until P4 Task 10's fix round, whose first CAL-seam collection could not
# attribute a per-run publish gap to the publisher rather than the transport
# because the in-core twin's skip diagnostics live only on that stream.
# teardown.sh carries the per-path table and the staleness guard;
# tests/benchmarks/test_teardown.py pins this path against drift from
# run_e2e.sh's own LOG=.
EDITOR_LOG=""
[ "$BENCH_ARM_IS_ABLATION" = "1" ] || EDITOR_LOG="/tmp/carla-e2e.log"

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
EDITOR_LOG="$EDITOR_LOG"
AW_CONTAINER="$AW_CONTAINER"
AW_EXEC="docker exec -e ROS_DOMAIN_ID=0 $AW_CONTAINER"
AW_SETUP="source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0"
AW_COMPOSE="$COMPOSE"
GT_ENABLED="$LAUNCH_GT_ENABLED"
GT_CMD="env PYTHONPATH=$BENCH_REPO $GT_PYTHON -m benchmarks.scripts.collect_gt"
GT_OUT_DIR="$BENCH_RUN_DIR"
GT_COUNT_LIDAR="$LAUNCH_GT_COUNT_LIDAR"
INJECTOR_ENABLED="$LAUNCH_INJECTOR_ENABLED"
ARM_ENABLED="$LAUNCH_ARM_ENABLED"
EXTRA_CONTAINERS=""
SPAWN_ARGS="$SPAWN_ARGS"
EOF

if [ "$BENCH_ARM_IS_ABLATION" = "1" ]; then
  # Declared for teardown.sh, which stops this client BEFORE the simulator:
  # it is the world's tick authority (exactly as autoware_demo.py is on the
  # tier4 cells), and a CARLA client left ticking a dead server hangs on actor
  # destroy. Written by the plan step too, so a launcher that dies half-way
  # through `up` still leaves teardown something to stop.
  cat >>"$BENCH_LAUNCH_ENV" <<EOF
ABLATION_PID_FILE="$ABLATION_PID_FILE"
ABLATION_LOG="$ABLATION_LOG"
ABLATION_TICK_HZ="$ABLATION_TICK_HZ"
EOF
fi

if [ "$MODE" = "plan" ]; then exit 0; fi
[ "$MODE" = "up" ] || fail "unknown mode $MODE (expected plan|up)"

# --------------------------------------------------------------------------
# up: boot the stack, then wait for OUR OWN readiness definition.
# --------------------------------------------------------------------------
mkdir -p "$BENCH_RUN_DIR"

# --------------------------------------------------------------------------
# ablation arm: CARLA only, then the publish-disabled baseline client.
# --------------------------------------------------------------------------
if [ "$BENCH_ARM_IS_ABLATION" = "1" ]; then
  # run_e2e.sh's own editor line, with the map from BENCH_MAP and -- the one
  # material difference -- NO `--ros2`, no `--rmw`, no `--ros2-extension`.
  #
  # MEASURED 2026-08-03 (bring-up probe; the matched Humble/cyclonedds
  # instrument, not the host's Jazzy CLI, which cannot even parse this fork's
  # type hashes). Booted WITH `--ros2` and no runner:
  #   * `/clock` EMITS at 19.959 Hz as soon as a client ticks the world -- so
  #     bench_observer becomes an ACTIVE, per-row-flushed writer to the same
  #     clock.csv this arm's client has to write, two byte streams in one file.
  #     (That also settles benchmarks/README.md's open "Task 14's to settle"
  #     contradiction for this fork: a --ros2 editor publishes /clock with no
  #     runner attached.)
  #   * `/carla/<vehicle>/ray_cast2/point_cloud` is ADVERTISED for a rig
  #     spawned with no ros_* attributes and no enable_for_ros() -- so
  #     "publishing disabled" was not actually true under --ros2.
  # Booted WITHOUT it, the same instrument sees only its own /parameter_events
  # and /rosout: the server is silent. That is what makes this arm's name true,
  # and it is the right baseline besides -- a DDS participant standing
  # publishers up is transport cost, not raycast cost. The direction is safe
  # for the disclosed lower bound (dropping the layer can only make the
  # baseline smaller, and the client-stream RPC hop already holds it above pure
  # raycast). The extension .so is not loaded for the same reason: it IS the
  # native publisher layer, so it belongs on the `total` side, not the baseline.
  #
  # TRAP, kept because it applies the moment anyone re-adds the flag
  # (run_e2e.sh's own header): a SINGLE-dash `-ros2` silently DISABLES ROS2 --
  # an unrecognised flag UE just ignores -- so the working form is the
  # double-dash `--ros2 --rmw=cyclonedds --ros2-extension=<path>`.
  #
  # ROS_DOMAIN_ID=0 is still pinned ON THIS PROCESS (this host's login shell
  # exports 123, ~/.zshrc:126, and `nohup` inherits it): a no-op while no ROS 2
  # layer runs, and one less thing to get wrong if one ever does.
  nohup env ROS_DOMAIN_ID=0 \
    "${CARLA_UNREAL_ENGINE_PATH:-$HOME/src/UnrealEngine}/Engine/Binaries/Linux/UnrealEditor" \
    "$BENCH_CARLA_TREE/Unreal/CarlaUnreal/CarlaUnreal.uproject" "$BENCH_MAP" \
    -game -RenderOffScreen -nosound >"$LAUNCH_LOG" 2>&1 &
  # CARLA_PID_FILE holds the EDITOR's own pid on this arm, where the normal
  # path stores run_e2e.sh's (which owns the editor through its own EXIT
  # trap). teardown.sh's extension case stops whatever that file names, so it
  # stops the editor directly here -- exactly as the tier4-native launcher's
  # own CARLA_PID_FILE already works. `env` execs in place, so `$!` is the
  # editor, not a wrapper.
  echo $! >"$CARLA_PID_FILE"

  echo "waiting up to ${READY_TIMEOUT_S}s for CARLA RPC on $BENCH_RPC_PORT (log: $LAUNCH_LOG)"
  deadline=$((SECONDS + READY_TIMEOUT_S))
  while :; do
    # Captured, never piped to grep -q: an early pipe close SIGPIPE-kills ss
    # and pipefail then reports "not bound" for a port that IS bound (the same
    # trap cells/tier4-native.sh documents).
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
  echo "OK: CARLA up on port $BENCH_RPC_PORT (no Autoware, no runner: ablation arm)"

  # The only client. $SPAWN_ARGS is the route's spawn in the runner's own
  # spelling and $BENCH_RUNNER_SWEEP_ARGS is the class mapping resolved above
  # (--lidar-channels/--lidar-pps); raycast_baseline.py accepts both verbatim,
  # so neither is re-derived here. Both are deliberately word-split: they are
  # resolved multi-flag strings, not single arguments.
  # shellcheck disable=SC2086
  nohup env PYTHONPATH="$BENCH_REPO" "$GT_PYTHON" -m benchmarks.scripts.raycast_baseline \
    --host localhost --port "$BENCH_RPC_PORT" --rig extension \
    --class-id "${BENCH_CLASS_ID:-}" --tick-hz "$ABLATION_TICK_HZ" \
    --duration-s "$ABLATION_DURATION_S" --out-dir "$BENCH_RUN_DIR" \
    $SPAWN_ARGS ${BENCH_RUNNER_SWEEP_ARGS:-} >"$ABLATION_LOG" 2>&1 &
  echo $! >"$ABLATION_PID_FILE"

  # Readiness is the FILE, not the process: clock.csv is what this arm exists
  # to produce (nothing publishes /clock, so the client is its only writer, and
  # run.sh step 7's watchdog will start judging the run by it within 30 s). Two
  # data rows also clears `fit_sim_wall_affine`'s ">= 2 paired samples", the
  # step-15 smoke's precondition.
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
  echo "OK: publish-disabled baseline ticking at ${ABLATION_TICK_HZ} Hz"
  exit 0
fi

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
