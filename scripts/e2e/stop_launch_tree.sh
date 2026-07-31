#!/usr/bin/env bash
# Stop a RECORDED process tree: the pid in each pid file, plus that pid's own
# descendants, and nothing else. Called by launch_autoware.sh --stop, which
# pipes this file into the Autoware container (`bash -s -- <pidfiles>`) so no
# bind mount has to exist for teardown to work.
#
# WHY THIS EXISTS -- a MEASURED defect, not a tidy-up. launch_autoware.sh
# --stop used to SIGTERM the recorded `ros2 launch` pid and print "autoware
# launch + concat relay stopped". Ten minutes after such a teardown, with
# CARLA gone and port 2000 free (Task 15, 2026-07-30):
#   ros2 node list --no-daemon -> 169 nodes
#   container ps -e            -> 74 processes
#   /proc/loadavg              -> 42.16 26.66 13.45
# The composable-node containers had survived the launch supervisor and were
# spinning hard because /clock no longer advanced. `docker compose down`
# cleared it and the host settled to 2.44.
#
# MECHANISM, MEASURED 2026-07-31 against a real `ros2 launch` started exactly
# the way launch_autoware.sh starts it (`nohup ros2 launch ... &` inside
# `bash -lc` under `docker compose exec -T`, two long-lived ExecuteProcess
# children). It is worse than "launch orphans on SIGTERM":
#
#   /proc/<launch>/status -> SigIgn 0000000001001007, SigCgt 0000000100000000
#
# SigIgn bits 0/1/2 are SIGHUP/SIGINT/SIGQUIT: all three are IGNORED, because
# a shell without job control sets exactly those to SIG_IGN for a background
# job, and SIG_IGN survives exec. SigCgt shows NO signal in 1-31 caught at
# all, so launch's own handlers are not installed either -- its
# AsyncSafeSignalManager routes signals through `signal.set_wakeup_fd`, which
# does nothing unless CPython has a Python-level handler for that signal, and
# CPython does not install one over an inherited SIG_IGN. Verified end to end:
#
#   SIGINT  -> launch stays in state S, both children keep running, and its
#              log gains nothing. A NO-OP.
#   SIGTERM -> launch dies by the DEFAULT action (state Z) with no launch code
#              running -- the log has no shutdown line, not even
#              launch_service.py's own "using SIGTERM ... can result in
#              orphaned processes" warning -- and BOTH launched children keep
#              running. Exactly the old --stop, exactly the reported defect.
#
# So there is no signal that reaches this launch AND tears its children down,
# and no signal ordering alone can fix it. What fixes it is signalling the
# CHILDREN, which is what this script does. The SIGINT-to-the-root rung is
# kept first and short: it is the correct and graceful path whenever the
# launch CAN receive it (a hand-run foreground `ros2 launch`, per
# docs/running-e2e.md), and it costs a few seconds when it cannot.
#
# NOT FIXED HERE, named rather than silently left: the root cause is the
# launch-side `nohup ... &`, and it could be undone (e.g. exec'ing through a
# shim that resets SIGINT to SIG_DFL -- bash cannot, since a signal ignored at
# shell entry cannot be trapped, but a two-line python `signal.signal` +
# `os.execvp` shim can). That is a change to the BRING-UP path, which this
# task cannot validate against a real stack, and the teardown contract is made
# true without it. Left for whoever owns a bring-up change.
#
# BOUNDED TO WHAT WAS LAUNCHED, and deliberately not one process further.
# The descendant set is snapshotted BEFORE the first signal (afterwards the
# children are reparented to pid 1 and the relationship is gone), and only
# members of that set are ever signalled. This script NEVER refuses and never
# exits non-zero: a teardown that blocks a legitimate measurement is worse
# than one that under-reports, and this campaign has recorded six separate
# cases of a correctness check doing exactly that. What it could not stop is
# REPORTED instead -- including the container's own post-stop process count,
# so the caller sees an observation rather than a success message.
#
# WHAT THAT BOUND RESTS ON, since "not one process further" is only as good as
# the pid file. A recorded pid identifies a process only until it EXITS; after
# that the kernel may hand the number to something unrelated, and this script
# would sweep that stranger AND ITS WHOLE SUBTREE. The window is real, not
# theoretical: the WARN path below deliberately KEEPS the pid file so a second
# --stop can retry, and the container it runs in is long-lived. `survivors()`
# cannot catch it either -- it re-tests liveness by pid alone, which a reused
# pid passes.
#
# So the pid is checked against the COMMAND LINE recorded beside it.
# launch_autoware.sh writes `<pidfile>.cmd` from /proc/<pid>/cmdline at launch;
# if that file exists and no longer matches, this script REPORTS the mismatch
# and SKIPS that pid file. Exact, so it cannot fire on a healthy teardown: the
# comparison is against the recorded string, never a guessed pattern -- a
# heuristic like "does the cmdline contain ros2" would be a blocking check in
# disguise, and its false positive would skip a REAL teardown. When the sidecar
# is ABSENT (an older launch, or a pid file written by something else) the
# check is skipped rather than failed, so nothing that works today stops
# working.
#
# KNOWN LIMIT, stated rather than papered over: processes orphaned by an
# EARLIER SIGTERM-only teardown are descendants of nothing this script has a
# pid for, so it cannot claim them. `docker compose down` remains the
# documented recovery for that state (CLAUDE.md; benchmarks/README.md).
#
# SECOND KNOWN LIMIT -- WHICH CELLS THIS COVERS, and it is not all of them.
# Nothing reaches this script except `launch_autoware.sh --stop` (a documented
# standalone entry point too -- docs/running-e2e.md), and the only HARNESS
# caller of that is run_e2e.sh's cleanup() at scripts/e2e/run_e2e.sh:254.
# On the bench side that is the EXTENSION family only:
# benchmarks/cells/extension.sh:192 is the sole cell launcher that starts
# run_e2e.sh, and benchmarks/config/cells.yaml gives `approach: extension` to
# cells A and C. The tier4-native family never comes through here. Cell B
# starts its own `ros2 launch` inside its own container and records the pid in
# its own container-side pid file (benchmarks/cells/tier4_autoware.sh:389-395;
# AW_PIDFILE=/tmp/tier4-autoware.pid at tier4_autoware.sh:41), and nothing
# outside that launcher ever reads it -- benchmarks/scripts/teardown.sh's
# `tier4-native` branch (teardown.sh:157-165) stops the demo and CARLA and not
# the Autoware launch tree. The python-bridge family has the same shape
# (/tmp/bridge-stage1.pid, /tmp/bridge-stage2.pid --
# benchmarks/cells/python-bridge.sh:330,369).
#
# WHAT THAT DOES AND DOES NOT MEAN, because the difference matters and the
# stronger claim does not survive checking. On the HAPPY path cell B's stack is
# cleared by removing its container outright: cells/tier4-native.sh:110 sets
# AW_COMPOSE="", so teardown.sh:227-231 takes the `docker rm -f "$AW_CONTAINER"`
# branch, and the launcher re-creates the container fresh next run
# (tier4_autoware.sh:323,326). So the measured accumulation defect -- survivors
# piling up inside a container that OUTLIVES the launch, which is exactly the
# run_e2e.sh shape -- does not reproduce there run over run. What cell B does
# NOT have is any graceful, recorded-tree shutdown at all: its launch tree dies
# with the container, with no signal ladder and no exit handlers, and if a run
# is interrupted before teardown reaches that step the whole tree survives with
# nothing holding a pid for it. Recovery is again `docker rm -f` /
# `docker compose down`.
#
# DELIBERATELY NOT FIXED HERE. Extending the recorded-tree teardown to the B
# path is outside Task 16's scope and is sequenced separately, to land before
# Task 18 (the primary duel) so that duel's cell-B runs are torn down the same
# way its cell-A runs are.
#
# /proc is read directly. `pgrep`/`pkill -f` self-match this script's own
# command line, a documented project gotcha that has cost live runs.
set -u

# Signal ladder, in seconds. Overridable so a test can exercise the whole
# ladder in a couple of seconds; the defaults are what teardown uses.
#
# Rung 1 is SHORT on purpose. Under the launch pattern measured above the root
# cannot receive SIGINT at all, so a long rung-1 budget is pure dead time on
# every teardown -- an earlier revision waited 20 s here and the measurement
# showed all 20 wasted. Five seconds is enough for a launch that CAN receive
# it to run its shutdown.
#
# Rung 2 is the LONGEST, because it is the one expected to do the work on a
# real stack: SIGINT reaches each composable-node container directly, and
# rclcpp installs its own SIGINT handler (overriding the inherited SIG_IGN), so
# this is where a graceful rclcpp shutdown happens and it needs real time.
INT_WAIT_S="${STOP_INT_WAIT_S:-5}"
REINT_WAIT_S="${STOP_REINT_WAIT_S:-15}"
TERM_WAIT_S="${STOP_TERM_WAIT_S:-10}"
KILL_WAIT_S="${STOP_KILL_WAIT_S:-5}"
POLL_S="${STOP_POLL_S:-0.5}"

declare -A KIDS

# A ZOMBIE is not a survivor. `kill -0` succeeds on an unreaped child, so a
# tree whose members died while their (still-signalled) parent had not reaped
# them yet would be reported as having survived SIGKILL -- a false alarm in
# the one message a reader is meant to trust. The state field is read with the
# same `##*") "` strip as scan_proc, because comm can contain spaces.
alive() {
  local line state
  kill -0 "$1" 2>/dev/null || return 1
  read -r line <"/proc/$1/stat" 2>/dev/null || return 1
  state="${line##*") "}"
  state="${state%% *}"
  [ "$state" != "Z" ]
}

# One /proc pass -> KIDS[ppid] = " child child ...".
# The comm field can contain spaces and parentheses, so the prefix is
# stripped up to the LAST ") " (`##*") "`) rather than by field number.
scan_proc() {
  local statfile line pid rest ppid
  KIDS=()
  for statfile in /proc/[0-9]*/stat; do
    read -r line <"$statfile" 2>/dev/null || continue
    pid="${line%% *}"
    rest="${line##*") "}"
    ppid="${rest#* }"
    ppid="${ppid%% *}"
    case "$ppid" in '' | *[!0-9]*) continue ;; esac
    KIDS[$ppid]="${KIDS[$ppid]-} $pid"
  done
}

# Descendants of $1, breadth-first, from the KIDS snapshot.
descendants() {
  local queue=("$1") out=() cur kid
  while [ "${#queue[@]}" -gt 0 ]; do
    cur="${queue[0]}"
    queue=("${queue[@]:1}")
    # Deliberate word split: KIDS holds a space-separated pid list.
    # shellcheck disable=SC2086
    for kid in ${KIDS[$cur]-}; do
      out+=("$kid")
      queue+=("$kid")
    done
  done
  [ "${#out[@]}" -gt 0 ] && printf '%s\n' "${out[@]}"
  return 0
}

# Members of $2.. still alive, printed one per line.
survivors() {
  local pid
  for pid in "$@"; do
    alive "$pid" && printf '%s\n' "$pid"
  done
  return 0
}

# Poll until every pid in $2.. is gone, or $1 seconds elapse.
wait_gone() {
  local budget="$1" left
  shift
  local deadline=$((SECONDS + budget))
  while [ "$SECONDS" -lt "$deadline" ]; do
    left="$(survivors "$@" | wc -l)"
    [ "$left" -eq 0 ] && return 0
    sleep "$POLL_S"
  done
  return 1
}

signal_each() {
  local sig="$1" pid
  shift
  for pid in "$@"; do
    kill "-$sig" "$pid" 2>/dev/null || true
  done
}

# RUNNING and ZOMBIE counted separately, because in this container they mean
# opposite things and a single number would mislead the reader this line is
# for. docker/compose.yaml runs the container as `command: sleep infinity`, so
# pid 1 is NOT an init and never calls wait(): every process orphaned in here
# becomes a PERMANENT zombie. MEASURED 2026-07-30 while verifying this script
# -- after a teardown that genuinely killed a 9-process tree, `ps -e` still
# listed all nine, every one of them `Z <defunct>` and reparented to pid 1.
# So a post-teardown `ps -e | wc -l` over-reports, and only the running count
# says whether anything is still executing. (It is also why alive() above
# treats Z as gone. Task 15's post-teardown count of 74 processes was
# nonetheless real work, not this artefact: nothing that is defunct drives
# /proc/loadavg to 42.16 or answers `ros2 node list`.)
proc_count() {
  local statfile line state running=0 zombie=0
  for statfile in /proc/[0-9]*/stat; do
    read -r line <"$statfile" 2>/dev/null || continue
    state="${line##*") "}"
    state="${state%% *}"
    if [ "$state" = "Z" ]; then zombie=$((zombie + 1)); else running=$((running + 1)); fi
  done
  echo "$running running, $zombie defunct"
}

TOTAL_TREE=0
TOTAL_LEFT=0

stop_one() {
  local pf="$1" pid kid s tree=() left=()
  if [ ! -f "$pf" ]; then
    echo "stop: $pf absent -- nothing was recorded for it"
    return 0
  fi
  pid="$(cat "$pf" 2>/dev/null)"
  case "$pid" in
    '' | *[!0-9]*)
      echo "stop: $pf holds '$pid', which is not a pid -- removing it"
      rm -f "$pf"
      return 0
      ;;
  esac
  if ! alive "$pid"; then
    echo "stop: pid $pid ($pf) is already gone"
    rm -f "$pf" "$pf.cmd"
    return 0
  fi

  # Pid-reuse guard. Compares against the cmdline RECORDED at launch, never a
  # guessed pattern, and only when that sidecar exists -- see the header. A
  # mismatch means the recorded pid now belongs to something else, so the only
  # safe action is to touch nothing and say so. Reported on STDOUT and exit
  # stays 0: this is not a refusal of the teardown, it is the teardown
  # declining to kill a stranger's process tree.
  if [ -f "$pf.cmd" ]; then
    local want got
    want="$(cat "$pf.cmd" 2>/dev/null)"
    got="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null)"
    if [ -n "$want" ] && [ "$want" != "$got" ]; then
      echo "stop: SKIPPING $pf -- pid $pid was REUSED. Recorded at launch as"
      echo "stop:   '$want'"
      echo "stop:   but pid $pid is now '$got'. Nothing was signalled; the"
      echo "stop:   process this pid file named is already gone. Pid file kept."
      return 0
    fi
  fi

  # Snapshot FIRST: after the root dies its children reparent to pid 1.
  scan_proc
  while read -r kid; do
    [ -n "$kid" ] && tree+=("$kid")
  done < <(descendants "$pid")
  TOTAL_TREE=$((TOTAL_TREE + 1 + ${#tree[@]}))
  echo "stop: pid $pid ($pf) + ${#tree[@]} descendant(s)"

  # 1. SIGINT the root. Graceful when it lands (a foreground `ros2 launch`
  #    shuts its own children down); a measured no-op for the `nohup ... &`
  #    launch this script exists for, hence the short budget.
  kill -INT "$pid" 2>/dev/null || true
  if wait_gone "$INT_WAIT_S" "$pid" ${tree[@]+"${tree[@]}"}; then
    echo "stop: pid $pid tree gone after SIGINT to the root"
    rm -f "$pf"
    return 0
  fi

  # 2-4. Escalate, but only over the snapshotted set. Each rung is applied to
  #      whoever is still alive, so a process that already exited is never
  #      signalled again. Note what this does NOT give: `survivors()` re-tests
  #      liveness by PID, so a pid that exited and was reused mid-ladder would
  #      still be signalled. The cmdline guard above closes that for the
  #      recorded ROOT, which is the pid that persists in a file; a descendant
  #      pid is snapshotted and swept within seconds, so its reuse window is
  #      the ladder's own duration rather than an unbounded one.
  local sig wait_s
  for sig in INT TERM KILL; do
    case "$sig" in
      INT) wait_s="$REINT_WAIT_S" ;;
      TERM) wait_s="$TERM_WAIT_S" ;;
      KILL) wait_s="$KILL_WAIT_S" ;;
    esac
    while read -r s; do [ -n "$s" ] && left+=("$s"); done \
      < <(survivors "$pid" ${tree[@]+"${tree[@]}"})
    [ "${#left[@]}" -eq 0 ] && break
    echo "stop: ${#left[@]} of pid $pid's tree still up; SIG$sig"
    signal_each "$sig" "${left[@]}"
    wait_gone "$wait_s" "${left[@]}" && break
    left=()
  done

  left=()
  while read -r s; do [ -n "$s" ] && left+=("$s"); done \
    < <(survivors "$pid" ${tree[@]+"${tree[@]}"})
  TOTAL_LEFT=$((TOTAL_LEFT + ${#left[@]}))
  if [ "${#left[@]}" -eq 0 ]; then
    echo "stop: pid $pid tree gone"
    rm -f "$pf" "$pf.cmd"
  else
    # Reported, never fatal, and the pid file is KEPT so a second --stop can
    # try again against the same recorded root.
    #
    # STDOUT, not stderr, and that is deliberate. The only in-repo caller is
    # scripts/e2e/run_e2e.sh:254, `... --stop 2>/dev/null || true` -- so on the
    # real teardown path stderr is DISCARDED, and a survivor list written there
    # reaches nobody. The count already survives via the summary line at the
    # end; the pids are the half an operator needs to go and look, so they go
    # where the caller can actually see them. Still duplicated to stderr for an
    # interactive run, where stderr is what is being watched.
    echo "stop: WARN ${#left[@]} process(es) of pid $pid's tree SURVIVED" \
      "SIGKILL: ${left[*]}"
    echo "stop: WARN ${#left[@]} process(es) of pid $pid's tree SURVIVED" \
      "SIGKILL: ${left[*]}" >&2
  fi
  return 0
}

for pidfile in "$@"; do
  stop_one "$pidfile"
done

# The claim this script is allowed to make, with the counts behind it. The
# process count is the container's own, so a reader can tell a clean teardown
# from one that left a stack spinning without trusting this message.
echo "autoware launch + concat relay stopped" \
  "($# pid file(s) checked, $TOTAL_TREE process(es) in the recorded trees," \
  "$TOTAL_LEFT survivor(s); container now: $(proc_count))"
exit 0
