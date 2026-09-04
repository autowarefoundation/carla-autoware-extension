#!/usr/bin/env bash
# G1: NDT pose (/localization/pose_estimator/pose, map frame, base_link) vs CARLA
# ground truth (rear axle, mapped with map_frame) over the same wall-clock window.
# Usage: gate_g1_localization.sh --log-dir DIR [--map-origin X,Y,Z] [--rpc-port N]
#        [--domain-id N] [--window S] [--max-err-m M] [--out DIR]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO="$(cd "$HERE/../.." && pwd)"
LOG_DIR=""; ORIGIN=""; PORT=2000; DOMAIN=42; WIN=30; MAXERR=1.0; OUT=/tmp
while [[ $# -gt 0 ]]; do case "$1" in
  --log-dir) LOG_DIR="$2"; shift 2;; --map-origin) ORIGIN="$2"; shift 2;; --rpc-port) PORT="$2"; shift 2;;
  --domain-id) DOMAIN="$2"; shift 2;; --window) WIN="$2"; shift 2;; --max-err-m) MAXERR="$2"; shift 2;;
  --out) OUT="$2"; shift 2;; *) echo "unknown option $1" >&2; exit 2;; esac; done
[[ -n "$LOG_DIR" ]] || { echo "--log-dir required" >&2; exit 2; }
mkdir -p "$OUT"
bash "$HERE/aw_exec.sh" "$LOG_DIR" "$DOMAIN" "python3 - $WIN <<'PY'
import sys, time, rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
end = time.time() + float(sys.argv[1]); rclpy.init(); n = Node('g1_ndt'); rows = []
n.create_subscription(PoseStamped, '/localization/pose_estimator/pose',
    lambda m: rows.append(f'{time.time():.3f} {m.pose.position.x:.4f} {m.pose.position.y:.4f}'), 10)
while time.time() < end and rclpy.ok(): rclpy.spin_once(n, timeout_sec=0.1)
sys.stdout.write('\n'.join(rows) + '\n'); sys.stderr.write(f'ndt_rows={len(rows)}\n')
PY" > "$OUT/g1_ndt.txt" &
CPID=$!
PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" "${CARLA_PYTHON:-python3}" -m scripts.e2e.collect_gt \
  --window "$WIN" --out "$OUT/g1_gt.txt" --port "$PORT" ${ORIGIN:+--map-origin "$ORIGIN"} &
GPID=$!
wait $CPID; wait $GPID
python3 "$HERE/measure_ndt.py" --ndt "$OUT/g1_ndt.txt" --gt "$OUT/g1_gt.txt" --max-err-m "$MAXERR"
