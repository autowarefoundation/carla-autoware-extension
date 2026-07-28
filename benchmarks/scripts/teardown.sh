#!/usr/bin/env bash
# Tear a run's world down, in the order that preserves its data.
#
#   bash benchmarks/scripts/teardown.sh <run-dir>
#
# Order matters and is not arbitrary:
#   1. the clock watchdog and the GT collector FIRST -- before the observer.
#      The watchdog judges the run by how stale clock.csv is; stopping the
#      observer first freezes that file, so a slow observer flush would make
#      the watchdog condemn a complete, healthy run as stall:clock.
#   2. the observer, with SIGINT -- bench_observer's ofstreams flush in its
#      destructor, which only runs when rclcpp's own SIGINT handler makes
#      spin() return. A SIGTERM/SIGKILL here loses the buffered tail of every
#      CSV, i.e. exactly the end of the scoring window. Verified live: the
#      same container SIGKILLed leaves 0-byte CSVs, SIGINTed leaves complete
#      ones.
#   3. the resource sampler, after the observer, so the observer's own
#      container cost is sampled right up to its shutdown.
#   4. the injector inside the Autoware container, by recorded PID.
#   5. the stack and the simulator, per approach, PID file first and pattern
#      only as a fallback -- and any pattern that could match a UE editor is
#      qualified by its TREE PATH, because three CARLA trees on this host
#      share one engine binary and an unqualified pattern kills the wrong
#      tree's editor.
#   6. SIGKILL escalation, because a stalled sync-mode CARLA ignores SIGTERM.
#
# Everything is best-effort and idempotent: teardown runs on the success path
# AND from run.sh's EXIT trap, so a second invocation must be a no-op rather
# than an error.
set -uo pipefail

RUN_DIR="${1:?usage: teardown.sh <run-dir>}"
LAUNCH_ENV="$RUN_DIR/launch.env"
HOST_PIDS="$RUN_DIR/host_pids.env"
OBSERVER_CONTAINER="${BENCH_OBSERVER_CONTAINER:-bench-observer}"
TERM_WAIT_S=30

say() { echo "teardown: $*"; }

# SIGTERM, bounded wait, SIGKILL. Never pkill/pgrep on a bare pattern.
stop_pid() {
  local pid="$1" label="$2" waited=0
  [ -n "$pid" ] || return 0
  kill -0 "$pid" 2>/dev/null || return 0
  say "SIGTERM $label (pid $pid)"
  kill "$pid" 2>/dev/null
  while [ "$waited" -lt "$TERM_WAIT_S" ] && kill -0 "$pid" 2>/dev/null; do
    sleep 1
    waited=$((waited + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    say "SIGKILL $label (pid $pid): still alive after ${TERM_WAIT_S}s"
    kill -9 "$pid" 2>/dev/null
  fi
}

stop_pidfile() {
  local file="$1" label="$2"
  [ -f "$file" ] || return 0
  stop_pid "$(cat "$file" 2>/dev/null)" "$label"
  rm -f "$file"
}

# INT (not TERM) and then a bounded wait, so an rclcpp node inside flushes.
stop_container() {
  local name="$1" waited=0
  [ -n "$name" ] || return 0
  docker inspect "$name" >/dev/null 2>&1 || return 0
  say "SIGINT container $name"
  docker kill -s INT "$name" >/dev/null 2>&1
  while [ "$waited" -lt 15 ] &&
    [ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null)" = "true" ]; do
    sleep 1
    waited=$((waited + 1))
  done
  docker rm -f "$name" >/dev/null 2>&1
}

# Sourced FIRST because step 1 below needs AW_CONTAINER to signal a
# container-side GT collector. Absence just means the launcher never got that
# far, which is not an error -- teardown still stops whatever did start.
LAUNCH_ENV_PRESENT=0
if [ -f "$LAUNCH_ENV" ]; then
  # shellcheck disable=SC1090 # generated at run time by the cell launcher
  . "$LAUNCH_ENV"
  LAUNCH_ENV_PRESENT=1
fi
if [ -f "$HOST_PIDS" ]; then
  # shellcheck disable=SC1090 # generated at run time by run.sh
  . "$HOST_PIDS"
fi

# ---------------------------------------------------------------------------
# 1. The clock watchdog, FIRST and before the observer.
#
# The watchdog judges the run by how stale clock.csv's newest row is (5 s
# threshold, 1 s poll). Stopping the observer first stops clock.csv growing,
# so any observer that takes more than 5 s to exit and flush -- which is
# exactly what a multi-hour CSV does -- would make the watchdog write its
# stall marker, and run.sh would then exclude a COMPLETE, HEALTHY run as
# stall:clock. The scoring window is over by the time teardown runs, so there
# is nothing left for the watchdog to catch: stopping it first costs no
# coverage and removes a whole class of false exclusion.
#
# The GT collector goes with it, for the same reason in reverse: it is the
# other process still writing into the run directory, and it has no business
# recording ticks from a stack that is being dismantled.
# ---------------------------------------------------------------------------
stop_pid "${WATCHDOG_PID:-}" "clock watchdog"
stop_pid "${GT_PID:-}" "gt collector"

# A GT collector running INSIDE a container (bridge cells) is not reachable by
# the host PID above: killing the local `docker exec` client leaves the
# in-container process untouched. Signal it in place so its exit handler runs
# before the container is removed.
if [ -n "${AW_CONTAINER:-}" ] && [ "${GT_OUT_DIR:-}" = "/out" ]; then
  docker exec "$AW_CONTAINER" pkill -TERM -f benchmarks.scripts.collect_gt >/dev/null 2>&1
fi

# ---------------------------------------------------------------------------
# 2. observer -- SIGINT, so its ofstream destructors flush
# ---------------------------------------------------------------------------
stop_container "$OBSERVER_CONTAINER"

# ---------------------------------------------------------------------------
# 3. resource sampler (after the observer, so the observer's own container
#    cost is sampled right up to its shutdown)
# ---------------------------------------------------------------------------
stop_pid "${SAMPLER_PID:-}" "resource sampler"

if [ "$LAUNCH_ENV_PRESENT" = "0" ]; then
  say "no $LAUNCH_ENV (launcher never got that far); nothing else to stop"
  exit 0
fi

# ---------------------------------------------------------------------------
# 4. injector (container-side, by the PID file it writes)
# ---------------------------------------------------------------------------
if [ -n "${AW_CONTAINER:-}" ]; then
  docker exec "$AW_CONTAINER" bash -lc '
    if [ -f /tmp/dummy_perception.pid ]; then
      kill "$(cat /tmp/dummy_perception.pid)" 2>/dev/null || true
      rm -f /tmp/dummy_perception.pid
    fi' >/dev/null 2>&1
fi

# ---------------------------------------------------------------------------
# 5/6. stack + simulator, per approach
# ---------------------------------------------------------------------------
case "${APPROACH:-}" in
  extension)
    # run_e2e.sh owns the editor and the Autoware launch through its own EXIT
    # trap, so stopping it is the primary path; the tree-qualified sweep below
    # is the fallback for the case where that trap did not run.
    stop_pidfile "${CARLA_PID_FILE:-}" "run_e2e.sh"
    ;;
  tier4-native | python-bridge)
    stop_pidfile "${CARLA_PID_FILE:-}" "carla"
    ;;
esac

# Editor sweep, ALWAYS qualified by this cell's tree path. `pkill -f
# CarlaUE4` is never used (it self-matches the invoking shell); for the UE5
# editor the uproject path is the only pattern that cannot hit another
# tree's editor.
if [ -n "${CARLA_TREE:-}" ] && [ "${RUN_MODE:-}" = "editor-game" ]; then
  for pid in $(pgrep -f "$CARLA_TREE/Unreal/CarlaUnreal/CarlaUnreal.uproject" 2>/dev/null); do
    stop_pid "$pid" "UnrealEditor -game ($CARLA_TREE)"
  done
fi

# CARLA 0.9.15 ships a packaged Shipping binary; this exact pattern (never
# the broader `CarlaUE4`) is the documented safe one.
if [ "${RUN_MODE:-}" = "shipping-headless" ]; then
  pkill -f CarlaUE4-Linux-Shipping >/dev/null 2>&1
  sleep 2
  pkill -9 -f CarlaUE4-Linux-Shipping >/dev/null 2>&1
fi

# Containers. The Autoware container is REMOVED, not left running: cells
# differ in the image they run under the same container name (B45's 0.45 pin
# vs B's, the bridge image vs compose's), so leaving one up would silently
# serve the next cell in a duel the previous cell's image.
if [ -n "${AW_COMPOSE:-}" ] && [ -f "$AW_COMPOSE" ]; then
  say "docker compose down ($AW_COMPOSE)"
  docker compose -f "$AW_COMPOSE" down --remove-orphans >/dev/null 2>&1
elif [ -n "${AW_CONTAINER:-}" ]; then
  docker rm -f "$AW_CONTAINER" >/dev/null 2>&1
fi

for extra in ${EXTRA_CONTAINERS:-}; do
  stop_container "$extra"
done

say "done"
exit 0
