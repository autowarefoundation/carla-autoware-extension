#!/usr/bin/env bash
# Phase B live harness. Mirrors run_g0.sh's structure: pins ROS_DOMAIN_ID=0 and
# CYCLONEDDS_URI, waits out a lingering port 2000 (apport core capture) before
# launching, verifies the editor plugin .so is fresh, boots CARLA headless with the
# native ROS 2 extension loaded, then runs the Python spawn+tick runner in the
# foreground so it owns SIGINT directly. CARLA is torn down (SIGTERM -> bounded
# wait -> SIGKILL) on every exit path via a PID file, never pgrep/pkill patterns.
#
# NOT exercised live by this task (Task 24): the editor .so is currently stale
# relative to the CARLA branch tip, and a --ros2/extension live run without a
# fresh carla-unreal-editor rebuild is forbidden by this repo's rules. This
# script is verified by `bash -n` + shellcheck + review only; the live E2E run is
# M4's job (Tasks 26-28) after that rebuild. verify_editor_artifact.sh failing
# loudly right now on the stale .so is CORRECT behaviour, not a bug to work around.
set -euo pipefail

: "${CARLA_ROOT:?set CARLA_ROOT to ~/src/carla-autoware-integration}"
: "${CARLA_UNREAL_ENGINE_PATH:?set CARLA_UNREAL_ENGINE_PATH to the CARLA UE5 tree}"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXT_SO="$REPO/extension/build/libcarla-autoware-extension.so"
LOG=/tmp/carla-phase-b.log
CARLA_PID_FILE=/tmp/carla-phase-b.pid
MAP=NishishinjukuMap

# The Autoware container runs on DDS domain 0. The user's login shell exports
# ROS_DOMAIN_ID=123 (see CLAUDE.md); left alone that would leak into CARLA and put
# it on a different DDS domain than the container, so no topic would ever be
# discovered. Pin both explicitly, same as run_g0.sh.
export ROS_DOMAIN_ID=0
export CYCLONEDDS_URI="file://$REPO/docker/cyclonedds.xml"

# Fails loudly if the editor plugin .so is older than CARLA HEAD (see the script's
# own header for the carla-unreal-vs-carla-unreal-editor trap it guards against).
bash "$REPO/scripts/phase_b/verify_editor_artifact.sh"

[ -f "$EXT_SO" ] || {
  echo "PREFLIGHT FAIL: build extension/ first ($EXT_SO missing)" >&2
  exit 1
}
# Cheap ABI preflight (~0s) before spending ~20s+ on an editor boot that would
# otherwise fail later, inside --ros2-extension loading, with only a buried log
# line to diagnose it from.
python3 -m runner --extension-check --extension-so "$EXT_SO"

port_bound() {
  local out
  # Captured into a variable rather than piped to `grep -q`: grep -q can close its
  # read end as soon as it finds a match while `ss` is still writing later lines;
  # under this script's `set -o pipefail` that SIGPIPE-kills `ss` (exit 141), and
  # pipefail then reports the WHOLE pipeline as failed even though grep DID match
  # -- silently flipping this function's result to "not bound" when the port
  # actually is bound. Command substitution has no such early-close hazard.
  out="$(ss -ltn 2>/dev/null)" || true
  [[ "$out" =~ :2000[[:space:]] ]]
}

# A previous run's UnrealEditor can sit under apport's core-dump capture for tens
# of seconds with the listening socket still bound (see run_g0.sh); wait it out
# before trying to bind our own instance on the same port. Never fatal -- if it's
# still bound after 60s we warn and let the subsequent bind attempt fail on its
# own terms (SO_REUSEADDR sometimes lets it through anyway).
elapsed=0
while [ "$elapsed" -lt 60 ] && port_bound; do
  sleep 1
  elapsed=$((elapsed + 1))
done
port_bound && echo "WARN: port 2000 still bound after 60s (crashed CARLA?)" >&2

# Clean up the CARLA process on every exit path (normal return, error, Ctrl-C).
# PID comes from a file, not pgrep/pkill -f, which would self-match this script's
# own command line (the ss/grep pattern above, or the launch line itself) --
# a documented gotcha in this project. SIGTERM first, then a bounded wait, then
# SIGKILL if it's still alive (mirrors run_g0.sh's wait_for_port_release escalation).
cleanup() {
  if [ -f "$CARLA_PID_FILE" ]; then
    local pid
    pid="$(cat "$CARLA_PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      local waited=0
      while [ "$waited" -lt 30 ] && kill -0 "$pid" 2>/dev/null; do
        sleep 1
        waited=$((waited + 1))
      done
      if kill -0 "$pid" 2>/dev/null; then
        echo "warning: CARLA pid $pid still alive after SIGTERM+30s; sending SIGKILL" >&2
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$CARLA_PID_FILE"
  fi
}
trap cleanup EXIT

# Launch CARLA headless with the native ROS 2 layer and the extension .so.
#
# TRAP: a SINGLE-dash `-ros2` SILENTLY DISABLES ROS2 in this build -- it is not a
# short alias, it is a DIFFERENT (unrecognised) flag that UE's command line parser
# just ignores, and the failure is silent (CARLA boots fine, ROS2->Enable() never
# runs, and every downstream ros2/DDS check just times out with nothing to point
# at). The verified-working form is DOUBLE-dash `--ros2 --rmw=cyclonedds
# --ros2-extension=<path>` (run_g0.sh + Task-11 live evidence); never "fix" this
# back to a single dash.
"$CARLA_UNREAL_ENGINE_PATH/Engine/Binaries/Linux/UnrealEditor" \
  "$CARLA_ROOT/Unreal/CarlaUnreal/CarlaUnreal.uproject" "$MAP" \
  -game -RenderOffScreen -nosound \
  --ros2 --rmw=cyclonedds --ros2-extension="$EXT_SO" \
  >"$LOG" 2>&1 &
echo $! >"$CARLA_PID_FILE"

# Bounded poll for the RPC port to come up (distinct from the wait-for-RELEASE
# loop above, which runs before launch). Replaces a blind `sleep 30`: boot time
# varies with shader compilation / cold disk cache, and a fixed sleep either
# wastes time on a fast boot or races a slow one. Fails loudly with the log path
# so a boot failure is diagnosable, not a silent hang in the runner's connect call.
elapsed=0
until port_bound; do
  if [ "$elapsed" -ge 120 ]; then
    echo "PREFLIGHT FAIL: CARLA RPC port 2000 never bound within 120s (see $LOG)" >&2
    exit 1
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done
echo "OK: CARLA RPC port 2000 bound after ${elapsed}s"

# Run the spawn+tick runner in the FOREGROUND (never `nohup ... &`): backgrounding
# it here would leave it immune to this shell's Ctrl-C (an OS-level
# ignored-SIGINT gotcha documented in this project), so a live operator's Ctrl-C
# would kill this script's wait but leave the runner (and thus the ego/sensors)
# running headless. No kit-calibration flags are passed: the runner defaults to
# the committed runner/config/ copies (see runner/__main__.py), so this harness
# has nothing kit-specific to override. Sync mode is the runner's default; CARLA
# 0.10/Chaos vehicles have been observed NOT to propel in synchronous mode on
# this build (control delivered, wheels configured, ego stays at 0 m/s) -- if a
# live run reproduces that, rerun with `--async` appended below (the validated
# fallback; MPC-style steering-delay compensation absorbs the loop latency).
python3 -m runner --host localhost --port 2000 --map "$MAP"
