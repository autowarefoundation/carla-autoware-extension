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
# Preflight: without a recorded container every gate that shells into Autoware is doomed,
# so fail now instead of burning the whole --g2-window first.
[[ -n "$(head -1 "$LOG_DIR/carla_autoware.containers" 2>/dev/null)" ]] \
  || { echo "no Autoware container recorded in $LOG_DIR/carla_autoware.containers" >&2; exit 2; }
# G2 runs for the whole window in the background; G3 then G1 sample inside it.
bash "$HERE/gate_g2_closed_loop.sh" --goal "$GOAL" --rpc-port "$PORT" --window "$G2WIN" --out "$OUT" ${ORIGIN:+--map-origin "$ORIGIN"} > "$OUT/g2.log" 2>&1 &
G2PID=$!
sleep 20
bash "$HERE/gate_g3_performance.sh" --log-dir "$LOG_DIR" --domain-id "$DOMAIN" --lidar-hz "$LHZ" --out "$OUT" > "$OUT/g3.log" 2>&1 || true
bash "$HERE/gate_g1_localization.sh" --log-dir "$LOG_DIR" --rpc-port "$PORT" --domain-id "$DOMAIN" --out "$OUT" ${ORIGIN:+--map-origin "$ORIGIN"} > "$OUT/g1.log" 2>&1 || true
wait $G2PID || true
# Harvest only real verdicts: a gate's log also carries progress lines, and a gate that died
# before scoring must never be able to read as a pass. Every gate has to be represented by at
# least one "-> PASS|FAIL" line (G3 legitimately emits two: LiDAR and control), and each gate
# that produced none is named before we exit non-zero.
: > "$OUT/gates.txt"
MISSING=()
for n in 1 2 3; do
  grep -E "^G$n .* -> (PASS|FAIL)$" "$OUT/g$n.log" >> "$OUT/gates.txt" || MISSING+=("$n")
done
cat "$OUT/gates.txt"
if [[ ${#MISSING[@]} -gt 0 ]]; then
  for n in "${MISSING[@]}"; do echo "G$n produced no verdict (see $OUT/g$n.log)" >&2; done
  exit 1
fi
! grep -q FAIL "$OUT/gates.txt"
