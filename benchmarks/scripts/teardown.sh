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
# Repo root, for stop_tier4_launch_tree's reference to scripts/e2e/ below --
# this file's own location, not $PWD (teardown.sh runs from wherever run.sh
# was invoked).
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

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

# Recorded-tree teardown for the tier4-native family's `ros2 launch` tree
# (Task 17c, D1). This family has no shutdown path of its own for that
# tree: cells/tier4_autoware.sh launches it with `nohup ... &` inside the
# container and only ever records its pid, so on an interrupted run (one
# that never reaches the container-removal step below) the whole tree
# survives with nothing holding a pid for it. That is the same defect
# Task 15 measured on the extension family ten minutes after a
# "successful" teardown (169 nodes, 74 processes, loadavg 42) and Task 16
# fixed there with scripts/e2e/stop_launch_tree.sh. This function wires
# that SAME script -- its behaviour untouched, since it is pinned by
# tests/e2e/test_stop_launch_tree.py -- into cell B. (Fix round 1's F2
# updated that script's own header comments to keep its design record
# accurate after this wiring landed; no functional change.)
#
# Delivery: `docker exec -i <container> bash -s -- <pidfiles>`, piping the
# script in on stdin. scripts/e2e/launch_autoware.sh's own --stop path
# uses compose_exec_script for the identical "no bind mount needed" reason
# (launch_autoware.sh:89-94), but that helper wraps `docker compose exec`,
# and this family's container is a bare `docker run` with AW_COMPOSE=""
# (cells/tier4-native.sh:144) -- there is no compose file for it to
# target. `docker exec -i` piping the script on stdin gets the same
# no-bind-mount property without that dependency.
#
# The two pidfile paths are cells/tier4_autoware.sh's own container-side
# constants (AW_PIDFILE, RELAY_PIDFILE); they are not parameterised
# anywhere else (no env var, no launch.env entry), so they are named here
# literally too.
#
# Never fatal, matching stop_launch_tree.sh's own contract (never
# refuses, always exits 0): a missing container, a missing script, or a
# failed exec all leave teardown otherwise unchanged -- a teardown that
# under-reports beats one that blocks the next run.
stop_tier4_launch_tree() {
  local container="$1"
  [ -n "$container" ] || return 0
  docker inspect "$container" >/dev/null 2>&1 || return 0
  local script="$REPO/scripts/e2e/stop_launch_tree.sh"
  if [ ! -f "$script" ]; then
    say "stop_launch_tree.sh missing at $script -- skipping tree stop"
    return 0
  fi
  # Teed into the run directory rather than left on this process's own
  # stdout (Task 17c, D3): stop_launch_tree.sh's own report -- what it
  # could not stop, plus the recorded-tree/survivor/post-stop counts -- is
  # the whole point of calling it on an interrupted run, and nothing
  # upstream of teardown.sh captures its stdout today (run.sh's own
  # teardown.sh call and duel.sh's call into run.sh both run unredirected).
  # Mirrors run.sh step 9's arm.log tee: PIPESTATUS[0] under pipefail so
  # the exec's own exit code, not tee's, decides the WARN below.
  #
  # `-a`, not a truncating `tee` (fix round 1, F3): teardown.sh runs TWICE
  # per run (:27-29 below); the second call normally returns early because
  # the container is already gone (`docker inspect` above fails after
  # :311-316's `docker rm -f`). But if THAT removal itself failed -- the
  # wedged state this whole task exists to report on -- the container is
  # still there, this function re-enters, and a truncating `tee` would
  # replace the first, informative report with whatever the second,
  # already-torn-down pass produces. Appending keeps both.
  #
  # The log target falls back to /dev/null when $RUN_DIR is unset or does
  # not exist, rather than pointing `tee` at a path it cannot create: a
  # `tee` that fails to open its target exits immediately, SIGPIPEs the
  # `docker exec` still writing to the far end of the pipe, and that
  # surfaces as the exec exiting 141 mid-ladder instead of completing it.
  # /dev/null always opens, so the exec always runs to completion; losing
  # the log in that case is strictly better than losing the tree stop.
  local log_target="$RUN_DIR/tier4-stop-launch-tree.log"
  [ -n "${RUN_DIR:-}" ] && [ -d "$RUN_DIR" ] || log_target=/dev/null
  # Bounded so a wedged `docker exec` cannot block the demo/CARLA stop
  # below or the next duel run (fix round 1, F4): 100s, derived as two
  # pidfiles walked SEQUENTIALLY through stop_launch_tree.sh's own
  # ladder (INT_WAIT_S=5 + REINT_WAIT_S=15 + TERM_WAIT_S=10 +
  # KILL_WAIT_S=5 = 35s per pidfile at that script's documented
  # defaults, so 2 * 35s = 70s worst case) plus a 30s margin for
  # `docker exec`'s own dial and startup overhead. Assumes those
  # defaults are not overridden; this bound would need revisiting if
  # they ever are. `--kill-after=10` makes the exec actually die rather
  # than merely being asked to, since nothing here owns the far end of
  # the pipe once `timeout` gives up. A fired timeout only means
  # survivors are reported instead of a clean stop -- the WARN below
  # already treats every non-zero exit (including timeout's 124) as
  # non-fatal, exactly like a real exec failure.
  local tree_stop_timeout_s=100
  local rc
  set +o pipefail
  timeout --kill-after=10 "$tree_stop_timeout_s" \
    docker exec -i "$container" bash -s -- \
    /tmp/tier4-concat-relay.pid /tmp/tier4-autoware.pid \
    <"$script" 2>&1 | tee -a "$log_target"
  rc="${PIPESTATUS[0]}"
  set -o pipefail
  [ "$rc" = "0" ] ||
    say "stop_launch_tree.sh exec ($container) exited $rc -- continuing"
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
  tier4-native)
    # D1 ordering decision 1 (Task 17c): stop_tier4_launch_tree runs FIRST,
    # before the demo/CARLA pair below -- not after, despite the existing
    # "demo before editor" rule's usual bias toward CARLA going last. That
    # rule guards a DIFFERENT hazard (a CARLA client left ticking a dead
    # server hangs on actor destroy), which this order does not trigger:
    # CARLA and the demo both stay up for the whole tree stop. What DOES
    # depend on order is the Autoware tree's own graceful shutdown --
    # stop_launch_tree.sh's SIGINT rungs want /clock still advancing so
    # rclcpp can spin() its way to a clean exit, and the demo is this
    # cell's tick source, so stopping the demo FIRST would freeze /clock
    # and turn every SIGINT rung into a dead wait, i.e. the exact
    # ungraceful-shutdown defect stop_launch_tree.sh exists to fix. Cost
    # of tree-first, corrected (fix round 1, F4): it is NOT free. The
    # demo/CARLA stop below is delayed by however long the tree stop
    # takes -- up to the full signal ladder per pidfile (INT_WAIT_S=5 +
    # REINT_WAIT_S=15 + TERM_WAIT_S=10 + KILL_WAIT_S=5 = 35s at
    # stop_launch_tree.sh's own defaults), for EACH of the two pidfiles
    # it walks sequentially -- ~70s worst case -- and the `docker exec`
    # itself was unbounded until this round, so on a loaded host with a
    # sluggish daemon that delay could land on the UE editor still
    # holding port 2000 and block the next duel run.
    # `stop_tier4_launch_tree` now wraps its `docker exec` in `timeout`
    # (see there for the budget and its derivation) to cap that
    # exposure; it does not remove it.
    #
    # D1 ordering decision 2: placed here, the call also runs before the
    # log-copy block below (guarded by
    # `docker inspect "${AW_CONTAINER}"`), so a tree stopped here can still
    # write its own shutdown lines to tier4-autoware.log before that log is
    # copied out; stopping after the copy could not.
    stop_tier4_launch_tree "${AW_CONTAINER:-}"
    # The demo BEFORE the editor, and the order is the point: the demo owns
    # world.tick(), so it is this cell's tick authority, and a CARLA client
    # left ticking a server that has just died hangs on actor destroy
    # (CLAUDE.md's teardown gotcha). Stopping it first also puts the world
    # back to a state the editor can exit from.
    stop_pidfile "${TIER4_DEMO_PID_FILE:-}" "tier4 autoware_demo.py"
    stop_pidfile "${CARLA_PID_FILE:-}" "carla"
    ;;
  python-bridge)
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

# In-container launch logs, copied out BEFORE the container is removed.
#
# cells/python-bridge.sh already saves these on its OWN failure paths, but a run
# can fail anywhere after the launcher returns -- run.sh's arm step, the
# post-engage control check, the smoke -- and teardown then removes the only
# copy. Measured 2026-07-29 (Task 10): results/E/run-007 was excluded
# gate:arm-failed with `change_to_autonomous` reporting "The target mode is not
# available. Please check the diagnostics", and the diagnostics naming WHICH
# component was unavailable lived in the container's stage-2 log, which this
# function had just deleted. An excluded run must carry its own diagnosis.
#
# Best-effort by design: no container, no log file, or a `docker cp` failure all
# leave teardown otherwise unchanged.
#
# The tier4 cells' single launch log is here for the same reason: the B family
# runs its stack inside a container this function is about to remove, and its
# own launcher only copies the log out on ITS failure paths -- a failure after
# the launcher returns (the arm, the post-engage probe, the smoke) would leave
# no copy at all.
if [ -n "${AW_CONTAINER:-}" ] && docker inspect "${AW_CONTAINER}" >/dev/null 2>&1; then
  for stage in 1 2; do
    if docker cp "${AW_CONTAINER}:/tmp/bridge-stage${stage}.log" \
      "$RUN_DIR/bridge-stage${stage}.log" >/dev/null 2>&1; then
      say "saved bridge-stage${stage}.log"
    fi
  done
  for log in tier4-autoware tier4-concat-relay; do
    if docker cp "${AW_CONTAINER}:/tmp/${log}.log" \
      "$RUN_DIR/${log}.log" >/dev/null 2>&1; then
      say "saved ${log}.log"
    fi
  done
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
