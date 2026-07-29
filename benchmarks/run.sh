#!/usr/bin/env bash
# The campaign's single measurement entry point.
#
#   bash benchmarks/run.sh <cell> --arm static|closed-loop [--class <id>]
#        [--unpaced] [--runs N] [--no-observer] [--rpc-port N] [--rmw NAME]
#        [--shm on|off] [--dds-profile PATH|none] [--dry-run]
#
# Every measurement in P3 and P4 comes from here. Each invocation produces
# either a complete, contract-valid benchmarks/results/<cell>/run-<NNN>/ or a
# manifest marked excluded with a reason from the pre-registered set in
# benchmarks/config/exclusions.md. There is no third outcome: an abort before
# step 4 leaves no run directory at all, and every abort after it either
# completes the directory or excludes it.
#
# --dry-run prints the fourteen numbered steps with fully resolved commands
# and runs everything that has no side effects on the results tree: the cell
# and class lookup, the arm check, the next run index, the config-file
# existence checks, and the cell launcher's own `plan` (which validates the
# interpreter, images, trees and route file it would use). It writes nothing
# under benchmarks/results/ and boots nothing.
#
# LAUNCHER CONTRACT. cells/<approach>.sh is invoked as `plan` or `up` with
# this environment, and writes $BENCH_LAUNCH_ENV for steps 7-9 and teardown:
#   BENCH_REPO BENCH_CELL BENCH_APPROACH BENCH_MAP BENCH_CARLA BENCH_ARM
#   BENCH_RUN_DIR BENCH_LAUNCH_ENV BENCH_RPC_PORT BENCH_ROUTE_FILE
#   BENCH_TL_GROUPS BENCH_CARLA_TREE BENCH_AUTOWARE_IMAGE BENCH_OBSERVER_IMAGE
#   BENCH_RMW BENCH_SHM BENCH_DDS_PROFILE BENCH_CLASS_ID
set -euo pipefail

BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$BENCH/.." && pwd)"
RESULTS="$BENCH/results"

# Scoring windows, pre-registered in benchmarks/README.md (M5 definitions).
WINDOW_STATIC_S=60
WINDOW_CLOSED_S=140
# The unpaced arm free-runs, so its window is measured in SIM seconds off
# clock.csv; this multiplier bounds the wall time it may take to get there.
UNPACED_WALL_CAP=6
CLOCK_STALL_S=5
CLOCK_GRACE_S=30
SAMPLE_INTERVAL_S=1.0
OBSERVER_CONTAINER=bench-observer

CELL=""
ARM=""
CLASS_ID=""
UNPACED=0
RUNS=1
NO_OBSERVER=0
DRY_RUN=0
RPC_PORT=2000
RMW="rmw_cyclonedds_cpp"
SHM=""
DDS_PROFILE=""
# Whether --dds-profile was PASSED, as distinct from defaulted below. The
# per-family default is corrected once the approach is known (step 1), and an
# explicit operator choice must survive that correction.
DDS_PROFILE_EXPLICIT=0

die() { echo "RUN FAIL: $*" >&2; exit 2; }

usage() {
  # The usage block is the file's own header comment (lines 4-6), printed
  # with the comment markers stripped, so there is one copy of it.
  sed -n '4,6p' "$BENCH/run.sh" | sed 's/^# \?//'
  exit 2
}

# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------
[ $# -ge 1 ] || usage
CELL="$1"
shift
case "$CELL" in -*) usage ;; esac
while [ $# -gt 0 ]; do
  case "$1" in
    --arm) ARM="$2"; shift 2 ;;
    --class) CLASS_ID="$2"; shift 2 ;;
    --unpaced) UNPACED=1; shift ;;
    --runs) RUNS="$2"; shift 2 ;;
    --no-observer) NO_OBSERVER=1; shift ;;
    --rpc-port) RPC_PORT="$2"; shift 2 ;;
    --rmw) RMW="$2"; shift 2 ;;
    --shm) SHM="$2"; shift 2 ;;
    --dds-profile) DDS_PROFILE="$2"; DDS_PROFILE_EXPLICIT=1; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h | --help) usage ;;
    *) die "unknown argument $1" ;;
  esac
done
[ -n "$ARM" ] || die "--arm is required (static|closed-loop, or a sweep arm)"
case "$RUNS" in '' | *[!0-9]*) die "--runs must be a positive integer" ;; esac
[ "$RUNS" -ge 1 ] || die "--runs must be >= 1"

# --------------------------------------------------------------------------
# Transport: the (rmw, shm, profile) triple must be CONSISTENT, because the
# manifest records it as fact. A manifest claiming shm off while nothing
# turns it off is a lie the analysis cannot detect.
# --------------------------------------------------------------------------
case "$RMW" in
  rmw_cyclonedds_cpp)
    [ -n "$SHM" ] || SHM=off
    [ "$SHM" = "off" ] ||
      die "--shm on is not available for rmw_cyclonedds_cpp here: Cyclone's
  shared memory needs an Iceoryx RouDi daemon, which nothing in this harness
  starts. Recording shm_enabled=true would be false."
    [ -n "$DDS_PROFILE" ] || DDS_PROFILE="$REPO/docker/cyclonedds.xml"
    ;;
  rmw_fastrtps_cpp)
    [ -n "$SHM" ] || SHM=on
    if [ "$SHM" = "off" ] && [ -z "$DDS_PROFILE" ]; then
      # Fast DDS uses shared memory by default; only a profile turns it off.
      DDS_PROFILE="$BENCH/observer/config/udp_only.xml"
    fi
    if [ "$SHM" = "on" ] && [ -n "$DDS_PROFILE" ] && [ "$DDS_PROFILE" != "none" ]; then
      die "--shm on with an explicit --dds-profile: the profile decides the
  transport, so the recorded shm_enabled would be unverified. Pass
  --dds-profile none, or --shm off."
    fi
    [ -n "$DDS_PROFILE" ] || DDS_PROFILE=none
    ;;
  *) die "unsupported --rmw $RMW (rmw_cyclonedds_cpp | rmw_fastrtps_cpp)" ;;
esac
case "$SHM" in on | off) ;; *) die "--shm must be on or off" ;; esac
if [ "$DDS_PROFILE" != "none" ] && [ ! -f "$DDS_PROFILE" ]; then
  die "--dds-profile $DDS_PROFILE does not exist"
fi

# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
step() {
  local n="$1"
  shift
  printf '\n%2s. %s\n' "$n" "$*"
}
show() { printf '      $ %s\n' "$*"; }

json_field() { printf '%s' "$1" | python3 -c "import json,sys; print(json.load(sys.stdin).get('$2',''))"; }

# Booleans come back as shell-comparable 1/0 rather than Python's "True" --
# `[ "$x" = "True" ]` is exactly the sort of cross-language string compare
# that silently inverts when one side changes.
json_bool() { printf '%s' "$1" | python3 -c "import json,sys; print(1 if json.load(sys.stdin).get('$2') else 0)"; }

pin() {
  BENCH_PINS="$BENCH/pins.yaml" python3 - "$1" <<'PY'
import functools
import os
import sys

import yaml

doc = yaml.safe_load(open(os.environ["BENCH_PINS"]))
print(functools.reduce(lambda d, k: d[k], sys.argv[1].split("."), doc))
PY
}

# --------------------------------------------------------------------------
# One run. Called $RUNS times.
# --------------------------------------------------------------------------
do_run() {
  local run_no="$1"
  # Reset per run: with --runs N these must not leak from one run's outcome
  # into the next run's exclusion decision.
  CONTROL_SILENT=0
  WINDOW_SHORT=0
  CURRENT_RUN_DIR=""
  ABORT_REASON="harness:$(cd "$REPO" && git rev-parse --short HEAD)"
  # host_pids.env is SOURCED at step 7; without this, a PID from the previous
  # run survives into a run that does not start that recorder, and the
  # liveness check would test a stale, long-dead process.
  unset SAMPLER_PID GT_PID WATCHDOG_PID

  # ---- 1 -----------------------------------------------------------------
  step 1 "cell_info: resolve cell + class, check the arm"
  local cell_json approach map_name carla_kind has_sim_clock arms sweep_arms
  local effective_arm window_arm
  cell_json="$(cd "$REPO" && python3 -m benchmarks.scripts.cell_info "$CELL" \
    ${CLASS_ID:+--class "$CLASS_ID"})" || die "cell_info rejected $CELL"
  approach="$(json_field "$cell_json" approach)"
  map_name="$(json_field "$cell_json" map)"
  carla_kind="$(json_field "$cell_json" carla)"
  # Derived by cell_info (and unit-tested there), read ONCE here and consumed
  # by steps 7, 13 and 14. A cell with no simulator publishes no /clock, so
  # clock.csv stays header-only by design: starting the watchdog for it would
  # mark EVERY run of that cell excluded as `stall:clock` once the grace
  # period expired -- quietly, under a legitimate-looking pre-registered
  # reason, and the resulting margin freeze would feed the equivalence verdict.
  has_sim_clock="$(json_bool "$cell_json" has_sim_clock)"
  arms="$(printf '%s' "$cell_json" | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin)['arms']))")"
  sweep_arms="$(printf '%s' "$cell_json" | python3 -c "import json,sys; print(' '.join(json.load(sys.stdin)['sweep_arms']))")"
  echo "      cell=$CELL approach=$approach map=$map_name carla=$carla_kind arms=[$arms]"

  # Observer profile, corrected per FAMILY now that the approach is known. The
  # blanket Cyclone default above ($REPO/docker/cyclonedds.xml, interfaces pinned
  # to `lo`) is the configuration benchmarks/README.md's DDS confound table
  # registers for cells A and C -- and it is NOT what that table registers for the
  # python-bridge family, which is "rmw_cyclonedds_cpp, default profile". The
  # difference is measured, not stylistic: against a live bridge, bench_observer on
  # the `lo`-pinned profile recorded 0 clock and 0 observer rows in 20 s where the
  # default profile recorded 366/365 (patches/python-bridge/README.md, "Observer
  # transport matrix"), because this cell's stack is Fast-DDS and Fast-DDS
  # announces no loopback unicast locators. Applying the wrong default here filed
  # results/E/run-001 with a header-only observer. cells/python-bridge.sh refuses
  # the `lo` profile outright, so this is the fix and that is its backstop; an
  # explicit --dds-profile still wins, and still meets that refusal.
  if [ "$approach" = "python-bridge" ] && [ "$RMW" = "rmw_cyclonedds_cpp" ] &&
    [ "$DDS_PROFILE_EXPLICIT" = "0" ] && [ "$DDS_PROFILE" != "none" ]; then
    echo "      dds_profile: $DDS_PROFILE -> none (registered for the $approach family)"
    DDS_PROFILE=none
  fi
  [ -n "$CLASS_ID" ] && echo "      class=$CLASS_ID $(json_field "$cell_json" points_per_second) pts/s"

  window_arm="$ARM"
  effective_arm="$ARM"
  if [ "$UNPACED" = "1" ]; then
    # `unpaced` is the arm name cells.yaml registers for a free-running run,
    # so that is what the manifest must say -- while the window length still
    # follows the arm that was asked for.
    effective_arm="unpaced"
    echo "      arm: $ARM -> unpaced (--unpaced)"
  fi
  local allowed="$arms"
  if [ -n "$CLASS_ID" ] || [ "$UNPACED" = "1" ]; then
    allowed="$arms $sweep_arms"
  fi
  case " $allowed " in
    *" $effective_arm "*) ;;
    *) die "arm '$effective_arm' is not registered for cell $CELL (allowed: $allowed)" ;;
  esac

  # Config files this cell needs. Checked BEFORE the run directory exists, so
  # a missing topic list or process map costs nothing.
  local observer_topics processes route_file tl_groups launcher
  observer_topics="$BENCH/config/observer_topics/$CELL.yaml"
  processes="$BENCH/config/processes/$CELL.yaml"
  launcher="$BENCH/cells/$approach.sh"
  [ -f "$observer_topics" ] || die "missing observer topic list: $observer_topics"
  [ -f "$processes" ] || die "missing process map: $processes"
  [ -f "$launcher" ] || die "missing cell launcher: $launcher"
  route_file=""
  tl_groups=""
  if [ "$map_name" != "none" ]; then
    route_file="$BENCH/config/routes/$map_name.yaml"
    tl_groups="$BENCH/config/tl_groups/$map_name.yaml"
    [ -f "$route_file" ] || die "missing route file: $route_file"
    [ -f "$tl_groups" ] || die "missing traffic-light groups: $tl_groups"
  fi
  echo "      topics=$observer_topics"
  echo "      processes=$processes"
  [ -n "$route_file" ] && echo "      route=$route_file  tl_groups=$tl_groups"

  # Images. Resolved here, not in the launcher, because the manifest records
  # them at step 4 -- before any launcher runs.
  local autoware_image observer_image carla_tree
  case "$approach" in
    extension)
      autoware_image="$(python3 -c "import yaml;print(yaml.safe_load(open('$REPO/docker/compose.yaml'))['services']['autoware']['image'])")"
      carla_tree="$(eval echo "$(pin extension_carla_fork.path)")"
      ;;
    tier4-native)
      if [ "$CELL" = "B45" ]; then autoware_image="$(pin autoware_045.digest)";
      else autoware_image="$(pin autoware_universe_devel.digest)"; fi
      carla_tree="$(eval echo "$(pin tier4_carla_fork.path)")"
      ;;
    python-bridge)
      # E0 is the AS-SHIPPED measurement, so it gets the unpatched image; E and
      # E-opt get the patched one (pins.yaml bridge_bench_patched, built from
      # docker/bridge-bench-patched.Dockerfile). Resolved HERE because this is
      # the value the manifest records: cells/python-bridge.sh reads it back out
      # of BENCH_AUTOWARE_IMAGE rather than re-deriving it, so the image the run
      # used and the image the manifest claims cannot diverge. That launcher
      # additionally verifies the resolved image's CONTENT against the cell, in
      # both directions, so a wrong BENCH_BRIDGE_IMAGE fails loudly.
      if [ "$CELL" = "E0" ]; then
        autoware_image="${BENCH_BRIDGE_IMAGE:-$(pin bridge_bench.tag)}"
      else
        autoware_image="${BENCH_BRIDGE_IMAGE:-$(pin bridge_bench_patched.tag)}"
      fi
      carla_tree=""
      ;;
    calibration)
      autoware_image="none"
      carla_tree="$(eval echo "$(pin extension_carla_fork.path)")"
      ;;
    *) die "unknown approach $approach" ;;
  esac
  observer_image="${BENCH_OBSERVER_IMAGE:-bench-observer:universe-devel}"
  if [ "$CELL" = "B45" ] && [ -z "${BENCH_OBSERVER_IMAGE:-}" ]; then
    # B45 runs the 0.45 message set; its observer must be built against the
    # same base or PublishedTime will not resolve (pins.yaml notes this image
    # is built in Task 21).
    observer_image="bench-observer:045"
  fi
  echo "      autoware_image=$autoware_image"
  echo "      observer_image=$observer_image"

  # ---- 2 -----------------------------------------------------------------
  step 2 "RUN_DIR: next gap-free index under results/$CELL"
  local cell_results next_idx run_dir
  cell_results="$RESULTS/$CELL"
  next_idx=1
  if [ -d "$cell_results" ]; then
    local highest
    highest="$(find "$cell_results" -maxdepth 1 -type d -name 'run-*' -printf '%f\n' 2>/dev/null |
      sed 's/^run-//' | sort -n | tail -1)"
    [ -n "$highest" ] && next_idx=$((10#$highest + 1))
  fi
  run_dir="$(printf '%s/run-%03d' "$cell_results" "$next_idx")"
  echo "      $run_dir"

  # In a dry run nothing may touch the results tree, so the launcher's plan
  # output goes to a scratch directory instead -- the resolution and the
  # prerequisite checks are identical either way.
  local work_dir launch_env
  if [ "$DRY_RUN" = "1" ]; then
    work_dir="$(mktemp -d "${TMPDIR:-/tmp}/bench-dryrun-XXXXXX")"
    trap 'rm -rf "$work_dir"' RETURN
  else
    work_dir="$run_dir"
  fi
  launch_env="$work_dir/launch.env"

  # ---- 3 -----------------------------------------------------------------
  step 3 "preflight: host load, disk, RPC port, stale SHM, engine BuildId"
  local preflight_kv=""
  local preflight_args=("$CELL" --port "$RPC_PORT" --results-dir "$RESULTS")
  # A dry run performs the SAME checks -- including the engine BuildId, which
  # the manifest's placement needs -- but with --no-clean, so preflight's one
  # side effect (deleting stale /dev/shm segments) does not happen for a run
  # that is not going to take place.
  if [ "$DRY_RUN" = "1" ]; then preflight_args+=(--no-clean); fi
  show "bash $BENCH/scripts/preflight.sh ${preflight_args[*]}"
  preflight_kv="$(bash "$BENCH/scripts/preflight.sh" "${preflight_args[@]}")" ||
    die "preflight refused the run (see the named reason above)"
  # shellcheck disable=SC2001 # per-line prefix; parameter expansion cannot
  echo "$preflight_kv" | sed 's/^/      /'

  # ---- 4 -----------------------------------------------------------------
  step 4 "write_manifest: transport, versions, placement; excluded=false"
  local placement_json observer_topics_label
  if [ "$NO_OBSERVER" = "1" ]; then
    observer_topics_label="clock-only"
  else
    observer_topics_label="$(basename "$observer_topics")"
  fi
  placement_json="$(
    PF_KV="$preflight_kv" \
    RUN_MODE_HINT="$(case "$approach" in
      extension | tier4-native) echo editor-game ;;
      python-bridge) echo shipping-headless ;;
      *) echo container-only ;;
    esac)" \
    CONTAINER_IMAGE="$autoware_image" \
    OBSERVER_IMAGE="$observer_image" \
    OBSERVER_TOPICS="$observer_topics_label" \
    OBS_RMW="$RMW" OBS_SHM="$SHM" \
    python3 - <<'PY'
import json
import os

placement = {
    "run_mode": os.environ["RUN_MODE_HINT"],
    "container_image": os.environ["CONTAINER_IMAGE"],
    "observer_env": {
        "image": os.environ["OBSERVER_IMAGE"],
        "rmw": os.environ["OBS_RMW"],
        "shm": os.environ["OBS_SHM"],
        "topics_file": os.environ["OBSERVER_TOPICS"],
    },
}
# Preflight's KEY=VALUE lines become host facts: governor, core count, load
# at start, free disk, cleared SHM counts, and the engine BuildId the UE
# cells were verified against.
for line in os.environ.get("PF_KV", "").splitlines():
    key, _, value = line.partition("=")
    if key:
        placement[key] = value
print(json.dumps(placement, sort_keys=True))
PY
  )"
  show "python3 -m benchmarks.scripts.write_manifest --run-dir $run_dir --cell $CELL" \
    "--arm $effective_arm --rmw $RMW --shm $SHM --dds-profile $DDS_PROFILE" \
    "--carla-version $carla_kind --autoware-image $autoware_image --placement-json '<json>'"
  # In a dry run the manifest goes to the SCRATCH directory, never to
  # results/. It is still a real write through RunManifest.save(), so a dry
  # run PROVES the manifest this cell would file is valid (placement keys,
  # engine BuildId, transport, registered cell/arm) instead of asserting it.
  local manifest_dir="$run_dir"
  if [ "$DRY_RUN" = "1" ]; then
    manifest_dir="$(printf '%s/run-%03d' "$work_dir" "$next_idx")"
  fi
  # NO mkdir here. write_manifest is the ONLY thing that creates a run
  # directory, and it does so only after the manifest validates -- so a
  # refusal leaves no directory at all. Creating it first meant a refusal
  # left an empty run-NNN/ with no manifest: it consumed a run index, was
  # never labelled excluded (there was no manifest to label), and made the
  # whole cell unrenderable for every later run.
  (cd "$REPO" && python3 -m benchmarks.scripts.write_manifest \
    --run-dir "$manifest_dir" --cell "$CELL" --arm "$effective_arm" \
    --rmw "$RMW" --shm "$SHM" --dds-profile "$DDS_PROFILE" \
    --carla-version "$carla_kind" --autoware-image "$autoware_image" \
    --placement-json "$placement_json") >/dev/null ||
    die "manifest refused; nothing measured"
  if [ "$DRY_RUN" = "1" ]; then
    echo "      manifest VALIDATED (written to $manifest_dir, not results/)"
    echo "      placement: $placement_json"
  else
    # From here on the run directory EXISTS, so no failure may leave it
    # half-written and unlabelled: on_abort tears the world down and marks
    # the manifest excluded under a pre-registered reason.
    CURRENT_RUN_DIR="$run_dir"
    trap on_abort EXIT
  fi

  # ---- 5 -----------------------------------------------------------------
  step 5 "cells/$approach.sh: boot sim + stack, wait for readiness"
  export BENCH_REPO="$REPO" BENCH_CELL="$CELL" BENCH_APPROACH="$approach" \
    BENCH_MAP="$map_name" BENCH_CARLA="$carla_kind" BENCH_ARM="$effective_arm" \
    BENCH_RUN_DIR="$work_dir" BENCH_LAUNCH_ENV="$launch_env" \
    BENCH_RPC_PORT="$RPC_PORT" BENCH_ROUTE_FILE="$route_file" \
    BENCH_TL_GROUPS="$tl_groups" BENCH_CARLA_TREE="$carla_tree" \
    BENCH_AUTOWARE_IMAGE="$autoware_image" BENCH_OBSERVER_IMAGE="$observer_image" \
    BENCH_RMW="$RMW" BENCH_SHM="$SHM" BENCH_DDS_PROFILE="$DDS_PROFILE" \
    BENCH_CLASS_ID="$CLASS_ID"
  if [ "$DRY_RUN" = "1" ]; then
    show "bash $launcher plan   # resolution + prerequisite checks only"
    bash "$launcher" plan || die "cells/$approach.sh cannot plan this run (see above)"
    show "bash $launcher up"
  else
    show "bash $launcher up"
    # criterion 1 (crash:<process>): the cell never came up, so nothing was
    # measured. Set before the call so the EXIT trap uses it if `up` dies in
    # a way that skips the || branch.
    ABORT_REASON="crash:cell-launch"
    bash "$launcher" up || die "cells/$approach.sh could not bring the cell up"
    # The cell IS up now, so ABORT_REASON must not stay "crash:cell-launch":
    # left as-is, an unhandled abort anywhere in steps 6-10 that no specific
    # site catches (route_grid failing, the goal-args YAML read, an operator
    # Ctrl-C during the window) would be filed as a launch crash for a cell
    # that demonstrably came up. From here a failure with no specific
    # handler is a harness orchestration defect (criterion 3), the same
    # reason finalization failures get after the window closes below.
    ABORT_REASON="harness:$(cd "$REPO" && git rev-parse --short HEAD)"
  fi
  # shellcheck disable=SC1090 # written by the launcher just above
  [ -f "$launch_env" ] && . "$launch_env"

  # ---- 6 -----------------------------------------------------------------
  step 6 "observer: bench_observer container recording into the run dir"
  local topics_dest="$work_dir/observer_topics.yaml"
  if [ "$NO_OBSERVER" = "1" ]; then
    # An EMPTY topics list, not a list containing /clock: bench_observer.cpp
    # subscribes /clock unconditionally in its constructor, so `topics: []`
    # already records exactly /clock and nothing else.
    show "write an empty topics list to $topics_dest (/clock is always subscribed)"
  else
    show "cp $observer_topics $topics_dest"
  fi
  local obs_env=(-e "RMW_IMPLEMENTATION=$RMW")
  local obs_mounts=()
  if [ "$DDS_PROFILE" != "none" ]; then
    obs_mounts+=(-v "$DDS_PROFILE:/dds-profile.xml:ro")
    case "$RMW" in
      rmw_cyclonedds_cpp) obs_env+=(-e "CYCLONEDDS_URI=file:///dds-profile.xml") ;;
      rmw_fastrtps_cpp) obs_env+=(-e "FASTRTPS_DEFAULT_PROFILES_FILE=/dds-profile.xml") ;;
    esac
  fi
  # `exec` so the recorder is PID 1: teardown sends SIGINT, and only rclcpp's
  # own handler makes spin() return so the CSV buffers flush. A wrapper shell
  # as PID 1 swallows the signal and the CSVs come back empty.
  local obs_cmd='. /opt/ros/humble/setup.sh; [ -f /opt/autoware/setup.bash ] && . /opt/autoware/setup.bash; . /ws/install/setup.bash; exec /ws/install/bench_observer/lib/bench_observer/bench_observer --ros-args -p out_dir:=/out --params-file /out/observer_topics.yaml'
  show "docker run -d --name $OBSERVER_CONTAINER --net=host --ipc=host -v $run_dir:/out" \
    "${obs_env[*]} ${obs_mounts[*]} $observer_image bash -lc '<sourced> exec bench_observer ...'"
  if [ "$DRY_RUN" = "0" ]; then
    if [ "$NO_OBSERVER" = "1" ]; then
      printf '/**:\n  ros__parameters:\n    topics: []\n' >"$topics_dest"
    else
      cp "$observer_topics" "$topics_dest"
    fi
    docker rm -f "$OBSERVER_CONTAINER" >/dev/null 2>&1 || true
    docker run -d --name "$OBSERVER_CONTAINER" --net=host --ipc=host \
      "${obs_env[@]}" "${obs_mounts[@]}" -v "$run_dir:/out" \
      "$observer_image" bash -lc "$obs_cmd" >/dev/null ||
      exclude_and_die "$run_dir" "crash:observer" "the observer container did not start"
  fi

  # ---- 7 -----------------------------------------------------------------
  step 7 "sampler + collect_gt + clock_watchdog (background)"
  show "python3 -m benchmarks.sampler.sample_resources --processes $processes" \
    "--out $run_dir/resources.csv --interval $SAMPLE_INTERVAL_S"
  local gt_args=(--host localhost --port "$RPC_PORT" --role-name ego
    --map "$map_name" --approach "$approach" --out "${GT_OUT_DIR:-$run_dir}/gt.csv")
  [ "${GT_COUNT_LIDAR:-0}" = "1" ] && gt_args+=(--count-lidar)
  if [ "${GT_ENABLED:-1}" = "1" ]; then
    show "${GT_CMD:-<from launch.env>} ${gt_args[*]}"
  else
    echo "      (no ground truth for this cell: no simulator)"
  fi
  # The watchdog runs ONLY where a sim clock exists. A `carla: none` cell
  # publishes no /clock at all, so clock.csv is header-only by design and the
  # watchdog would report "no /clock rows at all" the moment its grace period
  # expired -- excluding every single run of that cell as `stall:clock`,
  # silently and under a pre-registered reason that looks entirely
  # legitimate. Same flag step 13 and step 14 branch on.
  if [ "$has_sim_clock" = "1" ]; then
    show "python3 -m benchmarks.scripts.clock_watchdog --clock-csv $run_dir/clock.csv" \
      "--stall-s $CLOCK_STALL_S --grace-s $CLOCK_GRACE_S --marker $run_dir/clock_stall.marker"
  else
    echo "      (no clock watchdog: this cell has no simulator, so nothing"
    echo "       publishes /clock and clock.csv is header-only by design)"
  fi
  if [ "$DRY_RUN" = "0" ]; then
    (cd "$REPO" && exec python3 -m benchmarks.sampler.sample_resources \
      --processes "$processes" --out "$run_dir/resources.csv" \
      --interval "$SAMPLE_INTERVAL_S") >>"$run_dir/sampler.log" 2>&1 &
    echo "SAMPLER_PID=$!" >"$run_dir/host_pids.env"
    if [ "${GT_ENABLED:-1}" = "1" ]; then
      # Deliberate word-split: GT_CMD is a resolved command prefix written by
      # the launcher (a venv python here, a `docker exec` there).
      # shellcheck disable=SC2086
      (cd "$REPO" && exec ${GT_CMD} "${gt_args[@]}") >>"$run_dir/gt.log" 2>&1 &
      echo "GT_PID=$!" >>"$run_dir/host_pids.env"
    fi
    if [ "$has_sim_clock" = "1" ]; then
      (cd "$REPO" && exec python3 -m benchmarks.scripts.clock_watchdog \
        --clock-csv "$run_dir/clock.csv" --stall-s "$CLOCK_STALL_S" \
        --grace-s "$CLOCK_GRACE_S" --marker "$run_dir/clock_stall.marker") \
        >>"$run_dir/watchdog.log" 2>&1 &
      echo "WATCHDOG_PID=$!" >>"$run_dir/host_pids.env"
    fi

    # Backgrounded recorders die silently: a GT collector that fails at
    # import, on a version mismatch, or in find_ego leaves only gt.log, and
    # the run would otherwise burn its whole window and be filed with no M5
    # ground truth. Give each a moment to get past construction, then check
    # it is still there rather than discovering it 140 s later.
    sleep 3
    # shellcheck disable=SC1090,SC1091 # generated by this script, just above
    . "$run_dir/host_pids.env"
    if [ -n "${SAMPLER_PID:-}" ] && ! kill -0 "$SAMPLER_PID" 2>/dev/null; then
      exclude_and_die "$run_dir" "crash:sampler" \
        "the resource sampler exited during start-up (see $run_dir/sampler.log)"
    fi
    if [ -n "${GT_PID:-}" ] && ! kill -0 "$GT_PID" 2>/dev/null; then
      exclude_and_die "$run_dir" "crash:collect_gt" \
        "the GT collector exited during start-up (see $run_dir/gt.log)"
    fi
    if [ -n "${WATCHDOG_PID:-}" ] && ! kill -0 "$WATCHDOG_PID" 2>/dev/null; then
      exclude_and_die "$run_dir" "crash:clock_watchdog" \
        "the clock watchdog exited during start-up (see $run_dir/watchdog.log)"
    fi
  fi

  # ---- 8 -----------------------------------------------------------------
  step 8 "injector: clear-road objects + all-green signals (docker exec)"
  if [ "${INJECTOR_ENABLED:-0}" = "1" ]; then
    local grid
    if [ -n "$route_file" ]; then
      grid="$(cd "$REPO" && python3 -m scripts.e2e.route_grid "$route_file")"
    else
      grid=""
    fi
    local grid_cx grid_cy grid_size
    read -r grid_cx grid_cy grid_size <<<"$grid"
    show "${AW_EXEC:-<from launch.env>} bash -lc '<setup> PYTHONPATH=/work" \
      "python3 /work/benchmarks/injector/dummy_perception.py" \
      "--tl-groups /work/benchmarks/config/tl_groups/$map_name.yaml" \
      "--grid-center $grid_cx $grid_cy --grid-size $grid_size'"
    if [ "$DRY_RUN" = "0" ]; then
      # Direct script path, not `python3 -m`: docker/compose.yaml sets no
      # working_dir and the container shell does not cd /work, so the module
      # form would not resolve. PYTHONPATH=/work is still needed for the
      # injector's own benchmarks.injector.gen_tl_groups import.
      # shellcheck disable=SC2086
      ${AW_EXEC} bash -lc "$AW_SETUP
        export PYTHONPATH=/work
        if [ -f /tmp/dummy_perception.pid ]; then kill \"\$(cat /tmp/dummy_perception.pid)\" 2>/dev/null || true; sleep 1; fi
        nohup python3 /work/benchmarks/injector/dummy_perception.py \
          --tl-groups /work/benchmarks/config/tl_groups/$map_name.yaml \
          --grid-center $grid_cx $grid_cy --grid-size $grid_size \
          >/tmp/dummy_perception.log 2>&1 &
        echo \$! >/tmp/dummy_perception.pid
        sleep 3
        grep -q 'publishing clear-road perception' /tmp/dummy_perception.log" ||
        exclude_and_die "$run_dir" "gate:injector-failed" \
          "the injector did not start (docker exec $AW_CONTAINER cat /tmp/dummy_perception.log)"
    fi
  else
    echo "      (not injected for this cell: it runs its own perception, or has none)"
  fi

  # ---- 9 -----------------------------------------------------------------
  step 9 "arm: localization only (static) or route + engage (closed-loop)"
  local goal_args=""
  if [ -n "$route_file" ]; then
    goal_args="$(BENCH_ROUTE_FILE="$route_file" python3 - <<'PY'
import os

import yaml

goal = yaml.safe_load(open(os.environ["BENCH_ROUTE_FILE"]))["goal"]
print(f"{goal['x']} {goal['y']} {goal['yaw_rad']}")
PY
    )"
  fi
  local arm_flag=""
  [ "$window_arm" = "static" ] && arm_flag="--wait-localized-only"
  if [ "${ARM_ENABLED:-0}" = "1" ]; then
    show "${AW_EXEC:-<from launch.env>} bash -lc '<setup>" \
      "python3 /work/benchmarks/injector/arm_and_goal.py --goal $goal_args $arm_flag --timeout 60'"
    if [ "$DRY_RUN" = "0" ]; then
      # shellcheck disable=SC2086
      ${AW_EXEC} bash -lc "$AW_SETUP
        python3 /work/benchmarks/injector/arm_and_goal.py --goal $goal_args $arm_flag --timeout 60" ||
        exclude_and_die "$run_dir" "gate:arm-failed" "arm_and_goal.py did not arm the stack"
    fi
  else
    echo "      (nothing to arm for this cell)"
  fi

  # arm_and_goal.py engages via the AD API's change_to_autonomous service,
  # which DIVERGES from the repo's only live-gated engage path
  # (gate_g2_closed_loop.sh publishes /autoware/engage). That divergence is
  # unresolved, so a successful service response is not evidence the vehicle
  # is under command: check the GATED output -- /control/command/control_cmd,
  # what vehicle_cmd_gate actually sends -- rather than
  # /control/trajectory_follower/control_cmd, which flows even while the gate
  # suppresses everything. A silent gate is a bring-up gate failure
  # (exclusions.md criterion 2), recorded, not hidden.
  if [ "$window_arm" != "static" ] && [ "${ARM_ENABLED:-0}" = "1" ]; then
    show "${AW_EXEC:-<from launch.env>} bash -lc '<setup> timeout 15 ros2 topic echo --once /control/command/control_cmd'"
    if [ "$DRY_RUN" = "0" ]; then
      # shellcheck disable=SC2086
      if ${AW_EXEC} bash -lc "$AW_SETUP
        timeout 15 ros2 topic echo --once /control/command/control_cmd >/dev/null 2>&1"; then
        echo "      OK: /control/command/control_cmd is flowing"
      else
        CONTROL_SILENT=1
        echo "      WARNING: /control/command/control_cmd is SILENT after a successful" >&2
        echo "      change_to_autonomous. The AD-API engage path may not be sufficient;" >&2
        echo "      gate_g2_closed_loop.sh's /autoware/engage publish is the fallback." >&2
      fi
    fi
  fi

  # ---- 10 ----------------------------------------------------------------
  local window_s
  if [ "$window_arm" = "static" ]; then window_s="$WINDOW_STATIC_S"; else window_s="$WINDOW_CLOSED_S"; fi
  if [ "$UNPACED" = "1" ]; then
    step 10 "window: $window_s SIM seconds off clock.csv (unpaced), wall cap $((window_s * UNPACED_WALL_CAP))s"
    show "poll $run_dir/clock.csv until it spans ${window_s}s of sim time"
    if [ "$DRY_RUN" = "0" ]; then
      # A sim that never reaches the pre-registered window in the wall budget
      # has NOT produced a comparable run: its scoring window is shorter than
      # every other run's, and a merely-slow sim (RTF below 1/CAP) gets there
      # without ever tripping the clock watchdog. Recorded and excluded at
      # step 13 rather than filed as if it were a full window.
      if ! wait_sim_window "$run_dir/clock.csv" "$window_s" "$run_dir/window.json"; then
        WINDOW_SHORT=1
      fi
    fi
  else
    step 10 "window: sleep ${window_s}s ($window_arm arm)"
    show "sleep $window_s"
    if [ "$DRY_RUN" = "0" ]; then sleep "$window_s"; fi
  fi
  # Past this point a failure is a FINALIZATION failure: the data is on disk,
  # so an unhandled abort is "the harness could not finish it" (exclusions.md
  # criterion 3) -- the same reason ABORT_REASON was already reset to right
  # after step 5's launcher succeeded. Reaffirmed here rather than relied on
  # from further back, so this stays correct even if a future change adds an
  # intermediate step that sets ABORT_REASON to something else and forgets
  # to reset it before the window.
  ABORT_REASON="harness:$(cd "$REPO" && git rev-parse --short HEAD)"

  # ---- 11 ----------------------------------------------------------------
  step 11 "teardown: watchdog + GT -> observer (SIGINT, to flush) -> stack -> sim"
  show "bash $BENCH/scripts/teardown.sh $run_dir"
  if [ "$DRY_RUN" = "0" ]; then
    # The EXIT trap stays ARMED across steps 12-14. teardown is idempotent, so
    # a second run of it from on_abort is a no-op; clearing the trap here
    # instead left every failure in finalization (finalize_rtf, the exclusion
    # rewrites, the smoke) exiting without labelling the directory at all.
    bash "$BENCH/scripts/teardown.sh" "$run_dir"
  fi

  # ---- 12 ----------------------------------------------------------------
  step 12 "finalize_rtf: fill resources.csv's rtf column from clock.csv"
  show "python3 -m benchmarks.sampler.finalize_rtf --resources $run_dir/resources.csv --clock $run_dir/clock.csv"
  if [ "$DRY_RUN" = "0" ]; then
    (cd "$REPO" && python3 -m benchmarks.sampler.finalize_rtf \
      --resources "$run_dir/resources.csv" --clock "$run_dir/clock.csv") ||
      echo "WARN: finalize_rtf failed; rtf stays at the -1 sentinel" >&2
  fi

  # ---- 13 ----------------------------------------------------------------
  step 13 "exclusions: clock stall, short unpaced window, silent control gate"
  show "if $run_dir/clock_stall.marker exists: write_manifest --exclude 'stall:clock'"
  RUN_EXCLUDED=0
  if [ "$DRY_RUN" = "0" ]; then
    # `has_sim_clock` guards the marker test as well as the watchdog itself.
    # Defence in depth: with no watchdog started the marker cannot exist, but
    # if a future change ever starts one for a clock-less cell, this stops it
    # translating into an exclusion.
    if [ "$has_sim_clock" = "1" ] && [ -f "$run_dir/clock_stall.marker" ]; then
      # stall:clock wins over the others: a frozen sim clock is the cause a
      # short window or a suppressed control output would be a symptom of.
      exclude_run "$run_dir" "stall:clock" "$(cat "$run_dir/clock_stall.marker")"
    elif [ "$WINDOW_SHORT" = "1" ]; then
      exclude_run "$run_dir" "stall:unpaced-window-cap" \
        "$(cat "$run_dir/window.json" 2>/dev/null)"
    elif [ "${CONTROL_SILENT:-0}" = "1" ]; then
      exclude_run "$run_dir" "gate:control_cmd-silent" \
        "the gated control output never published after change_to_autonomous"
    else
      echo "      none"
    fi
  fi

  # ---- 14 ----------------------------------------------------------------
  step 14 "smoke: the results tree renders through the real analysis path"
  # NOT `python3 -m benchmarks.report <results>/<cell>`. report.main() takes
  # the results ROOT and treats each child as a cell, so handing it a single
  # cell directory makes it walk that cell's run-NNN directories AS IF they
  # were cells, find no `run-*` inside them, and print an EMPTY table -- a
  # smoke test that passes on any input, which is worse than none. Verified
  # directly against a synthetic results tree. render_cell() is the function
  # that renders a cell, and summarize_run() is what validates ONE run
  # (manifest.validate() plus every CSV read through the real readers), so
  # the smoke calls those.
  show "python3 -c 'benchmarks.report.summarize_run($run_dir); render_cell($RESULTS/$CELL)'"
  if [ "$DRY_RUN" = "0" ]; then
    # Paths travel by environment, never interpolated into the -c string, so
    # a path with a quote in it cannot break the command.
    if BENCH_RUN_DIR_SMOKE="$run_dir" BENCH_CELL_DIR="$RESULTS/$CELL" \
      BENCH_REPO_SMOKE="$REPO" BENCH_REPORT_MD="$run_dir/report.md" \
      BENCH_HAS_SIM_CLOCK="$has_sim_clock" BENCH_GT_EXPECTED="${GT_ENABLED:-1}" \
      bash -c 'cd "$BENCH_REPO_SMOKE" && python3 - >"$BENCH_REPORT_MD"' <<'PY'
import os
import sys
from pathlib import Path

from benchmarks.analysis.manifest import load_manifest
from benchmarks.report import render_cell, summarize_run


def data_rows(path):
    """Rows past the header, or None when the file is absent entirely."""
    if not path.is_file():
        return None
    return sum(1 for _ in open(path)) - 1


run_dir = Path(os.environ["BENCH_RUN_DIR_SMOKE"])
cell_dir = Path(os.environ["BENCH_CELL_DIR"])

# Always: the manifest this run filed must still validate on the way back in.
errs = load_manifest(run_dir / "manifest.json").validate()
if errs:
    sys.exit(f"manifest invalid on read-back: {'; '.join(errs)}")

# summarize_run reads manifest.json, clock.csv and observer.csv ONLY, so the
# other two instruments have to be asserted here or a run with no M5 ground
# truth (a GT collector that died at import, on a version mismatch, or in
# find_ego) and a run with no M3 samples both pass the smoke and are filed
# non-excluded. Both are backgrounded, so nothing else notices.
gt_rows = data_rows(run_dir / "gt.csv")
if os.environ["BENCH_GT_EXPECTED"] == "1" and not gt_rows:
    sys.exit(
        f"gt.csv has {gt_rows if gt_rows is not None else 'no file'}: this run has "
        f"no M5 ground truth (see {run_dir / 'gt.log'})"
    )
res_rows = data_rows(run_dir / "resources.csv")
if not res_rows:
    sys.exit(
        f"resources.csv has {res_rows if res_rows is not None else 'no file'}: this "
        f"run has no M3 samples (see {run_dir / 'sampler.log'})"
    )

if os.environ["BENCH_HAS_SIM_CLOCK"] != "1":
    # A calibration cell publishes no /clock at all, so clock.csv is
    # header-only by design and fit_sim_wall_affine ("need >= 2 paired (sim,
    # wall) samples") cannot apply -- bench_pub stamps system time precisely
    # so the CAL analysis is a same-host wall-clock difference. The generic
    # per-cell renderer is therefore not the smoke for these cells; the CAL
    # renderer is Task 16's. Assert what IS meaningful here: rows were
    # recorded.
    obs_rows = data_rows(run_dir / "observer.csv")
    if not obs_rows:
        sys.exit("observer.csv has no rows: nothing was recorded")
    print(f"# {run_dir.name}: {obs_rows} observer rows, {res_rows} resource samples "
          f"(no sim clock; CAL rendering is Task 16's cal_report.py)")
else:
    summarize_run(run_dir)  # validates THIS run end to end
    print(render_cell(cell_dir))
PY
    then
      echo "      OK ($run_dir/report.md)"
    elif [ "$RUN_EXCLUDED" = "1" ]; then
      # An excluded run is ALREADY labelled with a pre-registered reason, so a
      # degraded render is the expected consequence, not a new failure -- and
      # hard-failing here would wedge every later run of the cell behind a
      # directory that is correctly marked.
      echo "      WARN: excluded run does not render (expected); see $run_dir/report.md" >&2
    else
      # This run's own data is bad, so it must not stay unlabelled -- and the
      # cell must not be blocked by it either. render_cell tolerates a
      # prior unreadable run, so the next run of this cell still works.
      exclude_and_die "$run_dir" "harness:$(cd "$REPO" && git rev-parse --short HEAD)" \
        "the run directory is not contract-valid (see $run_dir/report.md)"
    fi
  fi

  echo
  echo "run $run_no/$RUNS complete: $run_dir"
}

# EXIT trap, armed the moment the run directory exists and kept armed through
# step 14. Its whole job is the invariant this harness promises: a results
# directory is either contract-valid or explicitly excluded, never a silent
# partial. Any failure after step 4 that no specific site already handled
# lands here, and $ABORT_REASON says which pre-registered criterion it is:
# `crash:` while the world is being built (criterion 1), `harness:<commit>`
# once the data exists and only finalization can still fail (criterion 3).
# Sites that know better (the arm, the recorder liveness check, the smoke)
# call exclude_and_die with their own precise reason.
on_abort() {
  local rc=$?
  trap - EXIT
  [ "$rc" -eq 0 ] && return 0
  [ -n "${CURRENT_RUN_DIR:-}" ] || return 0
  echo "RUN ABORTED (exit $rc): tearing down and excluding $CURRENT_RUN_DIR" >&2
  bash "$BENCH/scripts/teardown.sh" "$CURRENT_RUN_DIR" || true
  if [ -f "$CURRENT_RUN_DIR/manifest.json" ]; then
    (cd "$REPO" && python3 -m benchmarks.scripts.write_manifest \
      --run-dir "$CURRENT_RUN_DIR" --exclude "$ABORT_REASON") || true
  fi
  exit "$rc"
}

# Marks the run excluded and CONTINUES. Used at step 13, where the run is
# complete but not scorable.
exclude_run() {
  local run_dir="$1" reason="$2" detail="$3"
  (cd "$REPO" && python3 -m benchmarks.scripts.write_manifest \
    --run-dir "$run_dir" --exclude "$reason") >/dev/null
  RUN_EXCLUDED=1
  echo "      EXCLUDED $reason${detail:+ -- $detail}"
}

# Marks the run excluded and STOPS. Used where the run has a directory (so it
# must end contract-valid or excluded) but cannot produce usable data.
exclude_and_die() {
  local run_dir="$1" reason="$2" detail="$3"
  trap - EXIT
  bash "$BENCH/scripts/teardown.sh" "$run_dir" || true
  (cd "$REPO" && python3 -m benchmarks.scripts.write_manifest \
    --run-dir "$run_dir" --exclude "$reason") || true
  die "$detail (run excluded: $reason)"
}

# Unpaced window: sim seconds, read off the observer's own clock.csv, with a
# wall-clock cap so a sim that never advances ends the run instead of hanging
# (the clock watchdog independently marks a true freeze as a stall).
#
# Returns 0 once the window is reached, NON-ZERO on the cap. The caller
# excludes on a non-zero return: a run whose scoring window is shorter than
# the pre-registered one is not comparable with the runs it would be pooled
# with, and a merely-slow sim (RTF below 1/UNPACED_WALL_CAP) reaches the cap
# without the watchdog ever seeing a stall. The achieved span is written to
# window.json either way, so a reviewer can see how short it actually was
# rather than only that it was short.
wait_sim_window() {
  local clock_csv="$1" want_s="$2" out_json="$3"
  local wall_cap=$((want_s * UNPACED_WALL_CAP))
  local deadline=$((SECONDS + wall_cap))
  local started="$SECONDS"
  while :; do
    SPAN_S="$(python3 - "$clock_csv" <<'PY'
import csv
import sys

try:
    with open(sys.argv[1], newline="") as f:
        rows = [int(r["clock_ns"]) for r in csv.DictReader(f)]
except (OSError, KeyError, ValueError):
    rows = []
print(f"{(rows[-1] - rows[0]) / 1e9:.3f}" if len(rows) >= 2 else "0.000")
PY
    )"
    # If the heredoc python did not start or printed nothing, SPAN_S is
    # empty here -- and an empty value in the printf below writes
    # `{"sim_span_s": , ...}`, invalid JSON in window.json, which is the
    # very artifact the unpaced-cap exclusion (exclusions.md criterion 10)
    # relies on for disambiguation. Fall back to the same "0.000" sentinel
    # the python side already uses for "no usable rows" so a read failure
    # here degrades the same way a read failure inside python does, rather
    # than corrupting the file.
    if ! [[ "$SPAN_S" =~ ^[0-9]+\.[0-9]+$ ]]; then
      echo "WARN: wait_sim_window could not read a sim span from" \
        "$clock_csv (got '$SPAN_S'); treating as 0.000s" >&2
      SPAN_S="0.000"
    fi
    local elapsed=$((SECONDS - started))
    if awk -v s="$SPAN_S" -v w="$want_s" 'BEGIN { exit !(s >= w) }'; then
      printf '{"sim_span_s": %s, "wall_s": %s, "requested_sim_s": %s, "capped": false}\n' \
        "$SPAN_S" "$elapsed" "$want_s" >"$out_json"
      return 0
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      printf '{"sim_span_s": %s, "wall_s": %s, "requested_sim_s": %s, "capped": true}\n' \
        "$SPAN_S" "$elapsed" "$want_s" >"$out_json"
      echo "WARN: unpaced window reached only ${SPAN_S}s of sim time in the" >&2
      echo "      ${wall_cap}s wall cap (wanted ${want_s}s); the run will be excluded" >&2
      return 1
    fi
    sleep 2
  done
}

for i in $(seq 1 "$RUNS"); do
  UNPACED_TAG=""; [ "$UNPACED" = "1" ] && UNPACED_TAG="  unpaced"
  DRY_TAG=""; [ "$DRY_RUN" = "1" ] && DRY_TAG="  (dry run)"
  echo "=== $CELL  arm=$ARM${CLASS_ID:+  class=$CLASS_ID}$UNPACED_TAG  run $i/$RUNS$DRY_TAG ==="
  do_run "$i"
done
