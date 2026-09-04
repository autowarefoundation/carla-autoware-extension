#!/usr/bin/env bash
# G2: base_link reaches within --goal-tol-m of the goal at some sample of the window.
# Starting before engage is harmless: the verdict is the minimum over the window.
# Usage: gate_g2_closed_loop.sh --goal "X,Y,YAW" (CARLA coords, as given to run_carla_autoware.sh)
#        [--map-origin X,Y,Z] [--rpc-port N] [--window S] [--goal-tol-m M] [--out DIR]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO="$(cd "$HERE/../.." && pwd)"
GOAL=""; ORIGIN=""; PORT=2000; WIN=300; TOL=1.0; OUT=/tmp
while [[ $# -gt 0 ]]; do case "$1" in
  --goal) GOAL="$2"; shift 2;; --map-origin) ORIGIN="$2"; shift 2;; --rpc-port) PORT="$2"; shift 2;;
  --window) WIN="$2"; shift 2;; --goal-tol-m) TOL="$2"; shift 2;; --out) OUT="$2"; shift 2;;
  *) echo "unknown option $1" >&2; exit 2;; esac; done
[[ -n "$GOAL" ]] || { echo "--goal required" >&2; exit 2; }
mkdir -p "$OUT"
# Convert the CARLA goal with map_frame, so this gate and run_carla_autoware.sh can never
# disagree on the frame. The goal and origin go in through argv (not interpolated into the
# Python source), and a converter failure -- e.g. a --goal without three fields -- must abort
# here rather than leave GX/GY empty: `read` returns 0 on an empty here-string.
GOAL_XY="$(PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" python3 -c '
import sys
from scripts.e2e.map_frame import carla_to_map, parse_origin
x, y, _ = (float(v) for v in sys.argv[1].split(","))
mx, my, _ = carla_to_map(x, y, 0.0, parse_origin(sys.argv[2]))
print(f"{mx:.3f} {my:.3f}")' "$GOAL" "$ORIGIN")" \
  || { echo "could not convert --goal '$GOAL' to the map frame" >&2; exit 2; }
[[ -n "$GOAL_XY" ]] || { echo "empty map-frame goal from --goal '$GOAL'" >&2; exit 2; }
read -r GX GY <<<"$GOAL_XY"
# Deliberately NOT prefixed "G2 ": run_gates.sh harvests verdicts by prefix, and a progress
# line that looked like a verdict would let a crashed G2 read as a pass.
echo "goal: CARLA '$GOAL' -> map ($GX, $GY)"
PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" "${CARLA_PYTHON:-python3}" -m scripts.e2e.collect_gt \
  --window "$WIN" --out "$OUT/g2_dist.txt" --port "$PORT" --goal "$GX" "$GY" ${ORIGIN:+--map-origin "$ORIGIN"}
python3 "$HERE/measure_route.py" --distances "$OUT/g2_dist.txt" --goal-tol-m "$TOL"
