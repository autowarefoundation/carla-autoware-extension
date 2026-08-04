#!/usr/bin/env bash
# P4 Task 14 -- the vlp16 sweep driver (cells A and B-cyc, three arms each).
#
# WHAT THIS IS. Session orchestration, not harness code: it decides the ORDER
# of `run.sh` invocations and applies the campaign's inter-run hygiene and a
# settle wait between them. Every measurement decision -- window, arm, class,
# transport, exclusion -- belongs to `benchmarks/run.sh`, which this script
# calls once per run with no environment of its own beyond ROS_DOMAIN_ID.
# It is filed here because the collection's order and spacing are facts a
# reader of benchmarks/results/PROVENANCE.md sec 22 needs to check.
#
# WHY IT IS NOT `duel.sh`. This is a SWEEP, not a duel: the runs are not
# interleaved pairs, carry no --duel/--duel-id, and are never admitted to a
# duel pool. duel.sh's interleaving is exactly what must NOT happen here.
#
# NEVER ABORTS ON A FAILED RUN. run.sh's own contract is that every
# invocation yields either a contract-valid run directory or one excluded
# under a pre-registered reason, so a failure is DATA, not a reason to stop
# the collection and leave the remaining arms unmeasured. Outcomes are read
# afterwards from the manifests, never inferred from this script's exit code.
set -uo pipefail

REPO=/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0
cd "$REPO" || exit 2

# Domain 0 or nothing: a login shell exporting a nonzero domain silently
# splits CARLA from the container and no topic is ever discovered.
export ROS_DOMAIN_ID=0

# Inter-run settle, mirroring the constants scripts/duel.sh's registered
# pacing amendment uses (PROVENANCE sec 3): a fixed floor, then poll the
# 1-minute loadavg down to a target, capped so this script can never itself
# refuse to proceed. NOT applied before the first run.
PACE_FLOOR_S="${SWEEP_PACE_FLOOR_S:-120}"
PACE_CEILING_S="${SWEEP_PACE_CEILING_S:-300}"
PACE_POLL_S="${SWEEP_PACE_POLL_S:-5}"
PACE_TARGET_LOADAVG="${SWEEP_PACE_TARGET_LOADAVG:-6}"

RUN_COUNT=0

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

# The campaign's inter-run hygiene. The bootstrap REFUSES when no `autoware`
# container exists, which is the normal state on the ablation arm (it boots no
# Autoware at all) and after a tier4-native run (whose launcher `docker rm -f`s
# its own container). That refusal is recorded, not treated as a failure --
# same deviation Task 10 recorded for CAL-seam (PROVENANCE sec 12.7).
hygiene() {
  echo "=== HYGIENE $(date -Is) ==="
  docker compose -f docker/compose.yaml down --remove-orphans
  echo "    docker compose down exit=$?"
  bash scripts/bootstrap_carla_msgs.sh
  local rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "    bootstrap_carla_msgs.sh exit=0"
  else
    echo "    bootstrap_carla_msgs.sh exit=$rc (REFUSED -- expected with no autoware container)"
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

for _ in 1 2 3; do one A --arm paced --class vlp16; done
for _ in 1 2 3; do one A --arm paced --class vlp16 --unpaced; done
for _ in 1 2 3; do one A --arm ablation --class vlp16; done
for _ in 1 2 3; do one B-cyc --arm paced --class vlp16; done
for _ in 1 2 3; do one B-cyc --arm paced --class vlp16 --unpaced; done
for _ in 1 2 3; do one B-cyc --arm ablation --class vlp16; done

echo "=== SWEEP COMPLETE $(date -Is): $RUN_COUNT run.sh invocations ==="
