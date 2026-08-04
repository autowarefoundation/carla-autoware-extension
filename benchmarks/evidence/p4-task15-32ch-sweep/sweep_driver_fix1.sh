#!/usr/bin/env bash
# P4 Task 15 FIX ROUND 1 -- re-collection of cell B-cyc's six MEASURED 32ch
# runs (paced x3, unpaced x3) after review finding C1.
#
# WHAT THIS IS, AND HOW IT RELATES TO sweep_driver.sh. Same session
# orchestration, deliberately the same shape: it decides the ORDER of
# `run.sh` invocations and applies the campaign's inter-run hygiene and the
# settle wait between them, and it makes no measurement decision -- window,
# arm, class, transport, exclusion all belong to `benchmarks/run.sh`.
# sweep_driver.sh stays exactly as it ran; it is the certified verbatim
# producer of the original eighteen and is NOT re-run or edited. This is a
# second, separate driver for a second, separate collection.
#
# WHY A RE-COLLECTION AT ALL. Finding C1: cells/tier4-native.sh derived
# BENCH_TIER4_SWEEP_ARGS into an UNEXPORTED shell variable. The ablation arm
# consumes it in-process and was fine; the measured arms spawn
# `bash "$TIER4_DEMO"` through a prefix-assignment whitelist that did not
# carry it, so cells/tier4_autoware.sh expanded it to empty and the patched
# demo fell back to its own defaults -- `--lidar-channels 16 --lidar-pps
# 288000`, which IS the vlp16 class -- under a manifest stamped
# `class_id: "32ch"`. results/B-cyc/run-031..036 are now excluded
# `harness:65fbe09` under exclusions.md criterion 3 and stay in place with
# all their data. The three ablation runs (run-037..039) STAND and are not
# re-run. Cell A is unaffected -- cells/extension.sh expands its variable in
# the PARENT -- and is not re-run either.
#
# TWO PHASES, AND WHY THE SPLIT IS NOT COSMETIC:
#
#   proof -- ONE paced run. Before five more are paid for, the fix is checked
#            AT THE RIG rather than at the label: the observer's median
#            `size_bytes` on the registered lidar topic must step to ~x4.17
#            of this cell's own vlp16 baseline (1200000/288000 = 4.1667).
#            A label check cannot see this defect -- the label was always
#            right and the rig was always wrong -- which is the whole reason
#            the check is a measured quantity. If it does not step, the run
#            stops here and the round is reported, not continued.
#   rest  -- the remaining two paced and three unpaced runs.
#
#   bash sweep_driver_fix1.sh proof
#   <check the rig>
#   bash sweep_driver_fix1.sh rest
#
# NEVER ABORTS ON A FAILED RUN, same contract as sweep_driver.sh: run.sh
# yields either a contract-valid run directory or one excluded under a
# pre-registered reason, so a failure is DATA, not a reason to leave the
# remaining arms unmeasured. Outcomes are read afterwards from the manifests,
# never inferred from this script's exit code.
set -uo pipefail

PHASE="${1:?usage: sweep_driver_fix1.sh proof|rest}"

REPO=/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0
cd "$REPO" || exit 2

# Domain 0 or nothing: a login shell exporting a nonzero domain silently
# splits CARLA from the container and no topic is ever discovered.
export ROS_DOMAIN_ID=0

# Inter-run settle: the constants are UNCHANGED from sweep_driver.sh, which
# measured them adequate at this very class -- seventeen applications, every
# one exactly the 120 s floor, pre-floor loadavg up to 18.17 drained to at
# most 2.72, the poll never adding a second (PROVENANCE sec 26.6). The poll
# is what absorbs a heavier tail if one appears; blind extra settle would
# only cost wall time.
PACE_FLOOR_S="${SWEEP_PACE_FLOOR_S:-120}"
PACE_CEILING_S="${SWEEP_PACE_CEILING_S:-300}"
PACE_POLL_S="${SWEEP_PACE_POLL_S:-5}"
PACE_TARGET_LOADAVG="${SWEEP_PACE_TARGET_LOADAVG:-6}"

# Seeded to 1 on `rest` so the settle wait applies BEFORE its first run too:
# the `proof` run finished only a rig check ago, so `rest`'s first run is an
# inter-run boundary like any other. On `proof` it starts at 0, and the
# preamble's own loadavg gate is what stands in for pacing there.
case "$PHASE" in
  proof) RUN_COUNT=0 ;;
  rest) RUN_COUNT=1 ;;
  *) echo "unknown phase: $PHASE" >&2; exit 2 ;;
esac

pace() {
  [ "$RUN_COUNT" -eq 0 ] && return 0
  echo "sweep: pacing ${PACE_FLOOR_S}s floor -- loadavg now $(cut -d' ' -f1 /proc/loadavg)"
  sleep "$PACE_FLOOR_S"
  local topup=0 loadavg
  loadavg="$(cut -d' ' -f1 /proc/loadavg)"
  while awk -v l="$loadavg" -v t="$PACE_TARGET_LOADAVG" 'BEGIN { exit !(l >= t) }'; do
    if [ "$topup" -ge "$PACE_CEILING_S" ]; then
      echo "sweep: pacing ceiling (${PACE_CEILING_S}s) reached at loadavg $loadavg" \
        "(target < $PACE_TARGET_LOADAVG); proceeding anyway"
      break
    fi
    sleep "$PACE_POLL_S"
    topup=$((topup + PACE_POLL_S))
    loadavg="$(cut -d' ' -f1 /proc/loadavg)"
  done
  echo "sweep: paced $((PACE_FLOOR_S + topup))s total; loadavg $loadavg"
}

# The campaign's inter-run hygiene.
#
# THE BOOTSTRAP REFUSAL IS EXPECTED ON EVERY BLOCK, not on some of them --
# this rule pairs a `docker compose down` with a bootstrap requiring the
# container the `down` just removed. Measured on all eighteen blocks of the
# original collection (PROVENANCE sec 22.6, sec 23.4, sec 26.6), measured runs
# included. The `down` half is what the rule exists for: DDS ghost nodes
# accumulate across hard-killed launches under `network_mode: host`. The
# bootstrap attempt is kept so its exit status stays in the record; it costs
# the collection nothing, because `carla_msgs` is sourced optionally
# (scripts/e2e/launch_autoware.sh:202) and nothing under benchmarks/ consumes
# it.
hygiene() {
  echo "=== HYGIENE $(date -Is) ==="
  docker compose -f docker/compose.yaml down --remove-orphans
  echo "    docker compose down exit=$?"
  bash scripts/bootstrap_carla_msgs.sh
  local rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "    bootstrap_carla_msgs.sh exit=0"
  else
    echo "    bootstrap_carla_msgs.sh exit=$rc (REFUSED -- expected: the" \
      'compose down above removed the container it needs)'
  fi
  echo "    loadavg $(cat /proc/loadavg)"
  echo "    containers: $(docker ps --format '{{.Names}}' | tr '\n' ' ')"
}

one() {
  pace
  hygiene
  RUN_COUNT=$((RUN_COUNT + 1))
  echo "=== SWEEP RUN $RUN_COUNT $(date -Is): benchmarks/run.sh $* ==="
  bash benchmarks/run.sh "$@"
  echo "=== SWEEP RUN $RUN_COUNT EXIT $? $(date -Is) ==="
}

case "$PHASE" in
  proof)
    one B-cyc --arm paced --class 32ch
    ;;
  rest)
    for _ in 1 2; do one B-cyc --arm paced --class 32ch; done
    for _ in 1 2 3; do one B-cyc --arm paced --class 32ch --unpaced; done
    ;;
esac

echo "=== SWEEP $PHASE COMPLETE $(date -Is) ==="
