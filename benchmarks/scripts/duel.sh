#!/usr/bin/env bash
# Interleaved A/B driver: the primary duel's run order.
#
#   bash benchmarks/scripts/duel.sh <cell-a> <cell-b> --arm closed-loop \
#        --pairs N [any other run.sh flag ...]
#
# WHY INTERLEAVE. The duel's n >= 10 runs per cell take hours, over which the
# host drifts: thermals, page cache, accumulated DDS shared memory, whatever
# else the machine is doing. Running all of cell A and then all of cell B
# would charge that drift entirely to whichever cell ran second, and the
# equivalence verdict would be reading the clock as much as the approaches.
# Alternating one run each spreads any drift across both cells.
#
# WHY ALTERNATE THE ORDER WITHIN A PAIR. Interleaving alone still gives one
# cell every odd slot and the other every even slot, so a per-pair effect
# (the first run after a teardown pays the cold caches the second does not)
# lands entirely on one cell. Pairs therefore run A,B then B,A then A,B --
# each cell takes the first slot in half the pairs.
#
# Each run is a full `run.sh` invocation, so every run gets its own preflight,
# its own manifest and its own teardown; the duel adds ordering and nothing
# else. Extra flags after --pairs are passed through to run.sh unchanged.
#
# WHY THIS SCRIPT PASSES --duel ITSELF (amendment 2026-07-30, Task 15b).
# `RunManifest.duel_admissible` decides whether a run reaches the primary
# duel's equivalence verdict, and it defaults to FALSE so that a standalone
# bring-up or gate run -- a cell-A/cell-B launcher shake-out, an M5 gate
# check -- cannot silently become duel data. Only the caller that ORDERED the
# interleaving knows a run is part of an interleaved pair, and that caller is
# this script: interleaving IS its entire job. So it declares it on every run
# it makes, unconditionally, rather than leaving an operator to remember a
# flag whose omission would quietly shrink the duel's n.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH="$(cd "$HERE/.." && pwd)"

# A duel that keeps failing is a systemic problem (a stale image, a wedged
# port), not bad luck: stop rather than burn hours producing excluded runs.
MAX_CONSECUTIVE_FAILURES=2

die() { echo "DUEL FAIL: $*" >&2; exit 2; }

[ $# -ge 2 ] || die "usage: duel.sh <cell-a> <cell-b> --arm ARM --pairs N [run.sh flags]"
CELL_A="$1"
CELL_B="$2"
shift 2

PAIRS=""
PASSTHROUGH=()
while [ $# -gt 0 ]; do
  case "$1" in
    --pairs) PAIRS="$2"; shift 2 ;;
    *) PASSTHROUGH+=("$1"); shift ;;
  esac
done
[ -n "$PAIRS" ] || die "--pairs N is required (N runs of EACH cell)"
case "$PAIRS" in '' | *[!0-9]*) die "--pairs must be a positive integer" ;; esac
[ "$PAIRS" -ge 1 ] || die "--pairs must be >= 1"
[ "$CELL_A" != "$CELL_B" ] || die "a duel needs two different cells"

declare -A COMPLETED=([$CELL_A]=0 [$CELL_B]=0)
declare -A FAILED=([$CELL_A]=0 [$CELL_B]=0)
consecutive=0

one_run() {
  local cell="$1" pair="$2"
  echo
  echo "################ duel pair $pair/$PAIRS -> $cell ################"
  # --duel goes FIRST, before the passthrough, so it is present even when
  # PASSTHROUGH is empty (an unquoted empty array expansion would otherwise
  # be the only argument slot) and so a reader of the printed command sees
  # the declaration next to the cell it applies to.
  if bash "$BENCH/run.sh" "$cell" --duel "${PASSTHROUGH[@]}"; then
    COMPLETED[$cell]=$((COMPLETED[$cell] + 1))
    consecutive=0
  else
    FAILED[$cell]=$((FAILED[$cell] + 1))
    consecutive=$((consecutive + 1))
    echo "duel: $cell run in pair $pair FAILED (see above)" >&2
    if [ "$consecutive" -ge "$MAX_CONSECUTIVE_FAILURES" ]; then
      die "$consecutive consecutive failed runs; stopping the duel"
    fi
  fi
}

for pair in $(seq 1 "$PAIRS"); do
  # Order alternates per pair so neither cell always takes the first slot.
  if [ $((pair % 2)) -eq 1 ]; then
    one_run "$CELL_A" "$pair"
    one_run "$CELL_B" "$pair"
  else
    one_run "$CELL_B" "$pair"
    one_run "$CELL_A" "$pair"
  fi
done

echo
echo "duel complete: $CELL_A ${COMPLETED[$CELL_A]} ok / ${FAILED[$CELL_A]} failed,"\
  "$CELL_B ${COMPLETED[$CELL_B]} ok / ${FAILED[$CELL_B]} failed"
if [ "${FAILED[$CELL_A]}" -gt 0 ] || [ "${FAILED[$CELL_B]}" -gt 0 ]; then
  echo "duel: some runs failed; the duel's n is BELOW the requested $PAIRS per cell" >&2
  exit 1
fi
