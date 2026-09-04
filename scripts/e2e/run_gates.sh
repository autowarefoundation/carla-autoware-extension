#!/usr/bin/env bash
# Run G1-G3 against a stack started by CARLA's run_carla_autoware.sh.
# Usage: run_gates.sh --log-dir DIR --goal "X,Y,YAW" [--map-origin X,Y,Z] [--rpc-port 2000]
#        [--domain-id 42] [--lidar-hz 10] [--g2-window 300] [--out DIR]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR=""; GOAL=""; ORIGIN=""; PORT=2000; DOMAIN=42; LHZ=10; G2WIN=300; OUT=""
while [[ $# -gt 0 ]]; do case "$1" in
  --log-dir) LOG_DIR="$2"; shift 2;; --goal) GOAL="$2"; shift 2;; --map-origin) ORIGIN="$2"; shift 2;;
  --rpc-port) PORT="$2"; shift 2;; --domain-id) DOMAIN="$2"; shift 2;; --lidar-hz) LHZ="$2"; shift 2;;
  --g2-window) G2WIN="$2"; shift 2;; --out) OUT="$2"; shift 2;; *) echo "unknown option $1" >&2; exit 2;; esac; done
[[ -n "$LOG_DIR" && -n "$GOAL" ]] || { echo "--log-dir and --goal required" >&2; exit 2; }
OUT="${OUT:-$LOG_DIR/gates}"; mkdir -p "$OUT"
# G2 runs for the whole window in the background; G3 then G1 sample inside it.
bash "$HERE/gate_g2_closed_loop.sh" --goal "$GOAL" --rpc-port "$PORT" --window "$G2WIN" --out "$OUT" ${ORIGIN:+--map-origin "$ORIGIN"} > "$OUT/g2.log" 2>&1 &
G2PID=$!
sleep 20
bash "$HERE/gate_g3_performance.sh" --log-dir "$LOG_DIR" --domain-id "$DOMAIN" --lidar-hz "$LHZ" --out "$OUT" > "$OUT/g3.log" 2>&1 || true
bash "$HERE/gate_g1_localization.sh" --log-dir "$LOG_DIR" --rpc-port "$PORT" --domain-id "$DOMAIN" --out "$OUT" ${ORIGIN:+--map-origin "$ORIGIN"} > "$OUT/g1.log" 2>&1 || true
wait $G2PID || true
{ grep -h '^G1 ' "$OUT/g1.log"; grep -h '^G2 ' "$OUT/g2.log"; grep -h '^G3 ' "$OUT/g3.log"; } | tee "$OUT/gates.txt"
! grep -q FAIL "$OUT/gates.txt"
