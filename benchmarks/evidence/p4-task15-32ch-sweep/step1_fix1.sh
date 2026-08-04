#!/usr/bin/env bash
# P4 Task 15 FIX ROUND 1 -- Step-1 form verification for the two forms this
# round re-collects: cell B-cyc `paced` and `paced --unpaced`, both at
# `--class 32ch`.
#
# Same shape as the original round's Step 1 (whose verbatim output is
# step1-form-verification.log): `--check-args` first, then `--dry-run`, each
# followed by its own `exit=` line. Only the two MEASURED forms of the one
# cell being re-collected are verified -- cell A is not re-run at all and
# B-cyc's three ablation runs stand, so verifying their forms here would be
# verifying a form this round never invokes.
#
# It refuses nothing on its own: every decision belongs to benchmarks/run.sh.
# The point is that a form which will not resolve fails BEFORE a 2-5 minute
# editor boot is paid for, and that the resolution reaching `write_manifest`
# is in the record rather than asserted.
set -uo pipefail

REPO=/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0
cd "$REPO" || exit 2
export ROS_DOMAIN_ID=0

run_one() {
  local label="$1"
  shift
  echo "######## $label ########"
  bash benchmarks/run.sh "$@"
  echo "-------- exit=$? --------"
}

run_one "check-args: cell=B-cyc form='paced'" \
  B-cyc --arm paced --class 32ch --check-args
run_one "check-args: cell=B-cyc form='paced --unpaced'" \
  B-cyc --arm paced --class 32ch --unpaced --check-args
run_one "dry-run: cell=B-cyc form='paced'" \
  B-cyc --arm paced --class 32ch --dry-run
run_one "dry-run: cell=B-cyc form='paced --unpaced'" \
  B-cyc --arm paced --class 32ch --unpaced --dry-run
