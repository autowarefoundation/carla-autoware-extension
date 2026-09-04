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
read -r GX GY <<<"$(PYTHONPATH="$REPO" python3 -c "
from scripts.e2e.map_frame import carla_to_map, parse_origin
x, y, _ = (float(v) for v in '$GOAL'.split(','))
mx, my, _ = carla_to_map(x, y, 0.0, parse_origin('$ORIGIN')); print(f'{mx:.3f} {my:.3f}')")"
echo "G2 goal: CARLA '$GOAL' -> map ($GX, $GY)"
PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" "${CARLA_PYTHON:-python3}" -m scripts.e2e.collect_gt \
  --window "$WIN" --out "$OUT/g2_dist.txt" --port "$PORT" --goal "$GX" "$GY" ${ORIGIN:+--map-origin "$ORIGIN"}
python3 "$HERE/measure_route.py" --distances "$OUT/g2_dist.txt" --goal-tol-m "$TOL"
