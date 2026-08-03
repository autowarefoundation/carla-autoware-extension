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

# ---------------------------------------------------------------------------
# INTER-RUN PACING (amendment 2026-07-31, Task 18a). Host-idle time between
# chained runs is a MEASUREMENT CONDITION, exactly like the interleaving and
# per-pair alternation above (:7-22) -- it is disclosed and derived here for
# the same reason those are, not tuned to make a stuck duel pass. Full
# disclosure: benchmarks/results/PROVENANCE.md.
#
# THE PROBLEM THIS FIXES. A completed run leaves the host loaded long after
# `run.sh` exits: a 2 s-interval /proc/loadavg sample across a whole cell-B
# run, nothing else running on the box, recorded mean 25.80 / peak 50.05 on
# 24 cores (benchmarks/README.md:1789-1797), and the 1-min loadavg decays
# with a ~60 s time constant. preflight.sh:28 refuses any run at loadavg >= 8
# (MAX_LOADAVG; exclusions.md criterion 6) -- correctly: that gate is a
# measurement-validity condition (localization degrades under load), not a
# bug, and it is NOT relaxed here. Before this amendment `one_run` invoked
# `run.sh` back to back with zero cooldown, so the run immediately following
# any completed run was refused at preflight, and two consecutive refusals
# tripped MAX_CONSECUTIVE_FAILURES above -- measured live on this duel's pair
# 2: hostload:26.52, then hostload:24.55, then the abort
# (benchmarks/results/PROVENANCE.md:115-126). Task 18 additionally measured
# that same host's decay by hand afterwards: 24.55 -> 13.74 after 38 s ->
# 1.92 after 162 s, i.e. ~70-95 s of idle is what a post-run host needs to
# clear the gate (that decay series is not itself committed to this repo --
# see this task's own report for where it is recorded).
#
# THE FLOOR IS UNIFORM; THE TOP-UP IS NOT -- AND THAT IS A DELIBERATE TRADE.
# (An earlier cut of this comment claimed the whole wait was load-independent;
# it was not, and the correction below -- and the arithmetic that motivates
# it -- is recorded in Task 18a's fix-round report and PROVENANCE.md
# section 3.) The 120 s floor applies identically before every run after the
# first (see "NOT applied before the FIRST run" below), regardless of which
# cell just finished -- that part IS uniform and load-independent. The
# top-up poll that follows it is NOT: it is load-TRIGGERED by construction,
# so its length can differ depending on which cell just ran.
#
# That is a real departure from strict uniformity, and it is the right one.
# :7-22's own drift argument is about HOST STATE (thermals, page cache,
# accumulated DDS shared memory), not clock time as such -- and host state at
# run start is exactly what preflight.sh's loadavg gate measures. Equalising
# host-state-at-start is therefore closer to that design intent than
# equalising idle seconds would be: the trade is uniform-idle-time (what a
# floor-only design gives) versus uniform-host-state-at-start (what floor +
# top-up gives), and the latter is chosen deliberately, because a load-
# triggered top-up that never fires is free, while a floor alone that proves
# insufficient reproduces the exact preflight-refusal defect this amendment
# exists to remove.
#
# The residual is bounded (never past PACE_CEILING_S) and recorded per run as
# topup_s (pace_between_runs' own log write, below), precisely so Task 22 can
# check whether it ever fired at all and whether it correlates with the
# preceding cell: a disclosed, bounded, measured residual is a covariate Task
# 22 can account for; an undisclosed one would have been a confound.
#
# And on the cited decay the top-up is expected to be EXACTLY ZERO in the
# typical case: 24.55 * e^(-120/60) ~= 3.3, already under
# PACE_TARGET_LOADAVG's default of 6, so after the 120 s floor the poll
# usually finds the target already met on its first read and returns without
# sleeping again. In the measured typical case, then, the wait actually paid
# IS the uniform 120 s floor alone -- the top-up is insurance that is not
# expected to fire, not a routine load-dependent tax.
#
# FLOOR then a BOUNDED TOP-UP, never a bare wait and never an unbounded poll.
# PACE_FLOOR_S is fixed above the interpolated worst case (~95 s, read off
# the two measured decay points above -- neither lands exactly at the gate,
# so 95 s itself is interpolated, not measured) plus margin: a floor alone is
# what a fixed number that turns out insufficient would make it -- a bare
# preflight refusal -- so after the floor this polls the loadavg down to
# PACE_TARGET_LOADAVG (a margin under preflight's own gate of 8, so a reading
# taken here is not stale by the time run.sh's OWN preflight re-reads moments
# later -- the 1-min average can still tick up while decaying overall) but
# bounded by PACE_CEILING_S, because this script must NEVER itself refuse,
# fail, or abort a run (six recorded cases in this campaign of a correctness
# check blocking a legitimate measurement). If the ceiling is reached,
# pace_between_runs proceeds anyway, unchanged, and lets `run.sh`'s own
# preflight be the ONLY thing that may refuse. 300 s is sized against the
# measured PEAK (50.05, over 2x the 25.80 mean the floor is sized from): a
# host that hot needs longer than the mean case to clear the gate, and the
# ceiling gives it room the floor alone does not, while remaining a small
# fraction of a single run's own multi-minute duration.
#
# NEITHER wait is failure-isolated from the other's I/O: an unreadable
# loadavg source or an unwritable pacing log are infrastructure faults, not
# run failures, and must never turn into this script's own abort or into
# `duel.sh`'s documented "some runs failed" exit-1 status -- see
# pace_between_runs' own error handling below for how each is kept
# non-fatal.
#
# NOT applied before the FIRST run of a `duel.sh` invocation (one_run's
# RUN_COUNT check below). Argument for including it anyway: uniformity,
# every run including run 1 would then start from the same condition.
# Argument against, which wins here: the operator starts a duel from a host
# they already know is quiescent (that is the whole reason to START a duel
# then), and run 1's OWN preflight already gates on the SAME loadavg check --
# a mandatory 120 s tax on every duel invocation's first run, paid whether or
# not the host needed it, buys nothing a standalone bring-up or gate run does
# not already have. Pair 1 of this campaign's primary duel
# (results/A/run-003, results/B/run-013) also started this way, unpaced, from
# a quiescent host (Task 18a's report, D2) -- so this keeps new duels
# consistent with the one already on record rather than retroactively
# disagreeing with it.
#
# Every knob below is overridable by env var FOR TESTS ONLY (same pattern as
# scripts/e2e/stop_launch_tree.sh:188-192's signal ladder) so the suite can
# pin the REAL pacing code path without actually sleeping for minutes;
# defaults are what production uses and are never overridden by run.sh or by
# an operator's shell.
PACE_FLOOR_S="${DUEL_PACE_FLOOR_S:-120}"
PACE_CEILING_S="${DUEL_PACE_CEILING_S:-300}"
PACE_POLL_S="${DUEL_PACE_POLL_S:-5}"
PACE_TARGET_LOADAVG="${DUEL_PACE_TARGET_LOADAVG:-6}"
# Where every run's actual wait is recorded (D1 property 4): a duel-level
# log rather than a change to run.sh's manifest schema, so this fix stays
# contained to the one file this task is scoped to touch and never reaches
# into the frozen benchmarks/analysis/ manifest layer. Overridable so tests
# never write into the real results tree.
PACE_LOG="${DUEL_PACE_LOG:-$BENCH/results/duel-pacing.log}"
# The loadavg source itself, overridable so a test can feed pace_between_runs
# a controlled sequence of readings instead of the real host's.
LOADAVG_SRC="${DUEL_LOADAVG_SRC:-/proc/loadavg}"
# ---------------------------------------------------------------------------

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
RUN_COUNT=0

current_loadavg() { awk '{print $1}' "$LOADAVG_SRC"; }

# Sleeps the floor, then polls loadavg down to PACE_TARGET_LOADAVG (capped at
# PACE_CEILING_S), then records the actual wait -- see the pacing block above
# for why each property is shaped this way. Called before every run except
# the first (one_run's RUN_COUNT check), identically regardless of $cell:
# reading $cell here is only for the log line, never for the wait's length.
pace_between_runs() {
  local cell="$1" pair="$2"
  echo
  echo "duel: pacing ${PACE_FLOOR_S}s floor before $cell (pair $pair) --" \
    "inter-run host-idle time is a measurement condition, see the pacing" \
    "block near the top of this script"
  sleep "$PACE_FLOOR_S"

  local topup_start=$SECONDS
  local loadavg topup
  # current_loadavg's read is isolated from set -e (F1): an unreadable
  # $LOADAVG_SRC is a PACING infrastructure fault, not a run failure, and
  # must never abort the duel -- that would masquerade as this script's own
  # documented "some runs failed" exit-1 status. An empty/unparseable
  # reading already takes the safe branch below: awk coerces "" to 0 in a
  # numeric comparison, which is under any real PACE_TARGET_LOADAVG, so the
  # poll falls straight through as if the target were already met -- never a
  # busy-wait, never a hang.
  loadavg="$(current_loadavg 2>/dev/null || true)"
  while awk -v l="$loadavg" -v t="$PACE_TARGET_LOADAVG" 'BEGIN { exit !(l >= t) }'; do
    topup=$((SECONDS - topup_start))
    if [ "$topup" -ge "$PACE_CEILING_S" ]; then
      echo "duel: pacing ceiling (${PACE_CEILING_S}s) reached at loadavg" \
        "$loadavg (target < $PACE_TARGET_LOADAVG); proceeding anyway --" \
        "run.sh's own preflight judges this run, not this script"
      break
    fi
    sleep "$PACE_POLL_S"
    loadavg="$(current_loadavg 2>/dev/null || true)"
  done
  topup=$((SECONDS - topup_start))
  local total=$((PACE_FLOOR_S + topup))

  echo "duel: pacing done for $cell (pair $pair) -- waited ${total}s total" \
    "(floor ${PACE_FLOOR_S}s + top-up ${topup}s), loadavg now $loadavg"
  # Recorded per run so Task 22's analysis can see the inter-run gap for
  # every run, not just infer it from wall-clock gaps between manifests.
  # before_pair/before_cell (F5) name the run this wait PRECEDES, not the run
  # that just finished -- read them that way, not the reverse. There is no
  # run id here (this line is written before run.sh allocates one) and no
  # duel-invocation id, so two separate duel.sh invocations can both log
  # before_pair=1 before_cell=B; the only disambiguator is this line's own
  # `ts` (1s resolution) joined against the next manifest's started_at_ns.
  #
  # A write failure here is likewise a PACING fault, not a run failure (F1):
  # warn to stderr and proceed, the same non-fatal treatment as the loadavg
  # read above, rather than letting mkdir/the redirect's exit status trip
  # set -e and abort the duel.
  if ! mkdir -p "$(dirname "$PACE_LOG")" 2>/dev/null; then
    echo "duel: WARNING: could not create $(dirname "$PACE_LOG")," \
      "pacing record for $cell (pair $pair) lost, proceeding anyway" >&2
  elif ! {
    printf 'ts=%s before_pair=%s before_cell=%s floor_s=%s topup_s=%s' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$pair" "$cell" \
      "$PACE_FLOOR_S" "$topup"
    printf ' total_wait_s=%s loadavg_end=%s target=%s ceiling_s=%s\n' \
      "$total" "$loadavg" "$PACE_TARGET_LOADAVG" "$PACE_CEILING_S"
  } >>"$PACE_LOG" 2>/dev/null; then
    echo "duel: WARNING: could not append to $PACE_LOG," \
      "pacing record for $cell (pair $pair) lost, proceeding anyway" >&2
  fi
}

one_run() {
  local cell="$1" pair="$2"
  RUN_COUNT=$((RUN_COUNT + 1))
  # --check-args makes run.sh resolve its args and exit BEFORE preflight, so
  # no host-load gate ever runs for it to help clear -- pacing ahead of it
  # would be pure dead time. It is also documented (see
  # tests/benchmarks/test_duel_verdict.py's --check-args block comment) to
  # write nothing under benchmarks/results/; pacing would break that
  # contract by both delaying and by appending to duel-pacing.log. Skip
  # pacing entirely whenever --check-args is passed through.
  local check_args_only=0
  for arg in "${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}"; do
    [ "$arg" = "--check-args" ] && check_args_only=1
  done
  # Skip only the very first run of the whole invocation -- see the "NOT
  # applied before the FIRST run" note in the pacing block above for why.
  if [ "$RUN_COUNT" -gt 1 ] && [ "$check_args_only" -eq 0 ]; then
    pace_between_runs "$cell" "$pair"
  fi
  echo
  echo "################ duel pair $pair/$PAIRS -> $cell ################"
  # --duel goes FIRST, before the passthrough, so it is present even when
  # PASSTHROUGH is empty (an unquoted empty array expansion would otherwise
  # be the only argument slot) and so a reader of the printed command sees
  # the declaration next to the cell it applies to.
  #
  # --duel-id is stamped from duel.sh's OWN two cell arguments (Amendment
  # 2026-08-03, Task 2), never from a caller-supplied value: it is the
  # pairing THIS invocation orders, in the order THIS invocation was
  # given ($CELL_A, then $CELL_B), so both cells in the pair -- $cell
  # here is one or the other -- stamp the identical id and a verdict's
  # own f"{cell_a_id}+{cell_b_id}" lookup (duel_verdict.py) matches it
  # without normalising order. See RunManifest.duel_id for the pool rule
  # this feeds.
  if bash "$BENCH/run.sh" "$cell" --duel --duel-id "${CELL_A}+${CELL_B}" "${PASSTHROUGH[@]}"; then
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
