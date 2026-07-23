#!/usr/bin/env bash
# Phase B live harness. Mirrors run_g0.sh's structure: pins ROS_DOMAIN_ID=0 and
# CYCLONEDDS_URI, waits out a lingering port 2000 (apport core capture) before
# launching, verifies the editor plugin .so is fresh, boots CARLA headless with the
# native ROS 2 extension loaded, then runs the Python spawn+tick runner in the
# foreground so it owns SIGINT directly. CARLA is torn down (SIGTERM -> bounded
# wait -> SIGKILL) on every exit path via a PID file, never pgrep/pkill patterns.
#
# BRING-UP ORDER (M4-blocker #4, docs/phase-b-report.md): with WITH_AUTOWARE=1 this
# harness enforces the load-bearing sequence CARLA -> Autoware -> ego. autoware_carla_interface
# (pulled in by simulator_type:=carla) calls client.load_world() at startup, WIPING any actor
# already present; if the runner spawned the ego first, that reload would destroy it. So we
# boot CARLA (ego-less), THEN launch Autoware via launch_autoware.sh -- which blocks until the
# stack is up and carla_interface has fired-and-died -- and ONLY THEN run the spawn+tick
# runner. Without WITH_AUTOWARE=1 the harness keeps its original CARLA+runner smoke behaviour
# (no Autoware), for extension-only publisher checks.
#
# NOT exercised live yet: the editor .so is currently stale
# relative to the CARLA branch tip, and a --ros2/extension live run without a
# fresh carla-unreal-editor rebuild is forbidden by this repo's rules. This
# script is verified by `bash -n` + shellcheck + review only; the live E2E run
# waits on that rebuild. verify_editor_artifact.sh failing
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

# Opt-in Autoware bring-up (M4-blocker #4 ordering). Default 0 keeps the CARLA+runner-only
# smoke path; set WITH_AUTOWARE=1 to bring Autoware up (Autoware-first) between the CARLA boot
# and the ego spawn, so carla_interface's one-shot load_world cannot wipe the ego.
WITH_AUTOWARE="${WITH_AUTOWARE:-0}"

# Opt-in async tick loop (the documented G2 fallback -- see the runner launch comment at the
# foot of this script). Default 0 keeps sync pacing (0.05 fixed delta = 20 Hz), which is what
# G3's LiDAR-cadence check requires. Set RUNNER_ASYNC=1 for the G2 closed-loop route gate:
# CARLA 0.10/Chaos vehicles do NOT propel in synchronous mode on this build (control delivered,
# wheels configured, ego stays at 0 m/s), so route completion is only measurable in async, where
# MPC-style steering-delay compensation absorbs the loop latency.
RUNNER_ASYNC="${RUNNER_ASYNC:-0}"
RUNNER_MODE_ARGS=()
[ "$RUNNER_ASYNC" = "1" ] && RUNNER_MODE_ARGS+=(--async)

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

# Preflight: the host `carla` python module must expose carla.World.set_publish_tf.
#
# runner/__main__.py calls `world.set_publish_tf(False)` UNCONDITIONALLY, before
# spawning any actor (so Autoware -- not CARLA -- owns the localization TF tree).
# The carla wheel pip-installed into ~/.local (May 15) PREDATES that API and
# lacks the method, so the runner would AttributeError mid-spawn -- but only
# AFTER the 2-5 min editor boot, with the ego half-attached and CARLA already
# up. Catch it here, cheaply, before the boot is ever paid for.
#
# The fork ships a fresh wheel, but it bundles the native `carla*.so` extension
# module, so it CANNOT be imported zip-style off PYTHONPATH (CPython will not
# dlopen a .so from inside a .whl/zip) -- it must be EXTRACTED to a real
# directory first, and that directory prepended to PYTHONPATH. A PYTHONPATH
# entry sorts ahead of ~/.local/site-packages in sys.path, so the stale install
# is SHADOWED without uninstalling it (leaving the operator's pip state alone).
CARLA_WHEEL_CACHE=/tmp/carla-phase-b-carla-wheel
carla_has_set_publish_tf() {
  # 0 = fresh (method present); non-zero = stale OR carla not importable at all
  # (both cases want the wheel injected below). stderr hushed so a bare "no
  # carla installed" ImportError does not masquerade as a script error.
  python3 - <<'PY' 2>/dev/null
import sys
try:
    import carla
except Exception:
    sys.exit(1)
sys.exit(0 if hasattr(carla.World, "set_publish_tf") else 1)
PY
}

if carla_has_set_publish_tf; then
  echo "OK: host carla module already exposes World.set_publish_tf"
else
  # Locate the fork's fresh wheel. Glob (not a literal path) because the cp312
  # ABI tag moves with the interpreter; the pinned dist dir only ever holds the
  # one 0.10.0 build. Fail loudly with the expected path so a missing/never-built
  # PythonAPI is diagnosable, not a silent stale-import that surfaces mid-spawn.
  shopt -s nullglob
  wheels=("$CARLA_ROOT"/Build/Development/PythonAPI/dist/carla-0.10.0-*.whl)
  shopt -u nullglob
  if [ "${#wheels[@]}" -eq 0 ]; then
    echo "PREFLIGHT FAIL: host carla lacks World.set_publish_tf and no fork wheel found at" >&2
    echo "  $CARLA_ROOT/Build/Development/PythonAPI/dist/carla-0.10.0-*.whl" >&2
    echo "  build the fork PythonAPI first (in \$CARLA_ROOT: make PythonAPI)." >&2
    exit 1
  fi
  WHEEL="${wheels[0]}"

  # Idempotent extract: re-extract ONLY when the wheel is newer than our marker.
  # `touch` stamps the marker at extraction time, so an unchanged wheel is never
  # "newer" and the (comparatively slow) unzip is skipped on repeat runs; a
  # rebuilt PythonAPI bumps the wheel mtime past the marker and refreshes the
  # cache automatically.
  MARKER="$CARLA_WHEEL_CACHE/.extracted"
  if [ ! -e "$MARKER" ] || [ "$WHEEL" -nt "$MARKER" ]; then
    rm -rf "$CARLA_WHEEL_CACHE"
    mkdir -p "$CARLA_WHEEL_CACHE"
    # `python3 -m zipfile -e`, not `unzip`: python3 is already a hard dependency
    # of this harness (it runs the runner), whereas unzip may not be installed.
    python3 -m zipfile -e "$WHEEL" "$CARLA_WHEEL_CACHE"
    touch "$MARKER"
    echo "OK: extracted fork carla wheel -> $CARLA_WHEEL_CACHE ($(basename "$WHEEL"))"
  else
    echo "OK: reusing extracted fork carla wheel at $CARLA_WHEEL_CACHE"
  fi

  # Prepend so it shadows the stale ~/.local install for THIS process and the
  # runner it execs at the end. Also PRINTED because the G1-G3 gate scripts run
  # `python3 ... import carla` on the host in the OPERATOR's shell -- a separate
  # process this export cannot reach -- so they need the same recipe applied by
  # hand (copy the `export` line below into that shell before running a gate).
  export PYTHONPATH="$CARLA_WHEEL_CACHE${PYTHONPATH:+:$PYTHONPATH}"
  echo "OK: export PYTHONPATH=$CARLA_WHEEL_CACHE:\$PYTHONPATH  # gate scripts in this shell need this too"

  if ! carla_has_set_publish_tf; then
    echo "PREFLIGHT FAIL: injected fork wheel STILL lacks World.set_publish_tf" >&2
    echo "  extracted: $CARLA_WHEEL_CACHE   wheel: $WHEEL" >&2
    echo "  the fork PythonAPI build is itself stale -- rebuild it (in \$CARLA_ROOT: make PythonAPI)." >&2
    exit 1
  fi
  echo "OK: fork carla wheel injected; World.set_publish_tf present"
fi

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
  # Stop the Autoware launch FIRST (if we started it): its carla_interface holds no ego, but
  # its ros2 launch tree should not outlive this harness. --stop uses a recorded container PID,
  # never pkill -f. Best-effort; a failure here must not skip the CARLA teardown below.
  if [ "$WITH_AUTOWARE" = "1" ]; then
    bash "$REPO/scripts/phase_b/launch_autoware.sh" --stop 2>/dev/null || true
  fi
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

# M4-blocker #4 ordering: with WITH_AUTOWARE=1, bring Autoware up NOW -- after CARLA is bound
# but BEFORE the runner spawns the ego. launch_autoware.sh blocks until the stack is up and
# autoware_carla_interface has fired its one-shot load_world and exited, so the reload happens
# on the still-ego-less world and cannot wipe the ego the runner is about to spawn. cleanup()
# tears this launch down on every exit path (registered above).
if [ "$WITH_AUTOWARE" = "1" ]; then
  bash "$REPO/scripts/phase_b/launch_autoware.sh"
fi

# Run the spawn+tick runner in the FOREGROUND (never `nohup ... &`): backgrounding
# it here would leave it immune to this shell's Ctrl-C (an OS-level
# ignored-SIGINT gotcha documented in this project), so a live operator's Ctrl-C
# would kill this script's wait but leave the runner (and thus the ego/sensors)
# running headless. No kit-calibration flags are passed: the runner defaults to
# the committed runner/config/ copies (see runner/__main__.py), so this harness
# has nothing kit-specific to override. Sync mode is the runner's default; CARLA
# 0.10/Chaos vehicles have been observed NOT to propel in synchronous mode on
# this build (control delivered, wheels configured, ego stays at 0 m/s) -- for the
# G2 closed-loop route gate set RUNNER_ASYNC=1 (appends --async here; the validated
# fallback, MPC-style steering-delay compensation absorbs the loop latency). G3's
# LiDAR-cadence check stays on the sync default so 20 Hz means a real paced cadence.
python3 -m runner --host localhost --port 2000 --map "$MAP" "${RUNNER_MODE_ARGS[@]}"
