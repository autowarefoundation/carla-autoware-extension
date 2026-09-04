#!/usr/bin/env bash
# G3: LiDAR at its configured rate (awsim_sensor_kit: sensor_tick 0.1 -> 10 Hz) and
# control_cmd at the 20 Hz simulation rate. `ros2 topic hz` never exits, so timeout's
# 124 is the healthy path; only a missing "average rate:" line is a failure.
# Usage: gate_g3_performance.sh --log-dir DIR [--domain-id N] [--lidar-hz 10] [--lidar-tol 1]
#        [--control-hz 20] [--control-tol 5] [--out DIR]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR=""; DOMAIN=42; LHZ_T=10; LHZ_TOL=1; CHZ_T=20; CHZ_TOL=5; OUT=/tmp
while [[ $# -gt 0 ]]; do case "$1" in
  --log-dir) LOG_DIR="$2"; shift 2;; --domain-id) DOMAIN="$2"; shift 2;; --lidar-hz) LHZ_T="$2"; shift 2;;
  --lidar-tol) LHZ_TOL="$2"; shift 2;; --control-hz) CHZ_T="$2"; shift 2;; --control-tol) CHZ_TOL="$2"; shift 2;;
  --out) OUT="$2"; shift 2;; *) echo "unknown option $1" >&2; exit 2;; esac; done
[[ -n "$LOG_DIR" ]] || { echo "--log-dir required" >&2; exit 2; }
mkdir -p "$OUT"
capture() { # topic window outfile
  set +e
  bash "$HERE/aw_exec.sh" "$LOG_DIR" "$DOMAIN" "timeout -k 2 15 ros2 topic hz $1 --window $2" > "$3" 2>&1
  local rc=$?; set -e
  [[ $rc -eq 124 || $rc -eq 0 || $rc -eq 137 ]] || { echo "G3 FAIL: ros2 topic hz $1 rc=$rc"; cat "$3"; exit "$rc"; }
}
capture /sensing/lidar/top/pointcloud_raw_ex 40 "$OUT/g3_lidar_hz.txt"
capture /control/command/control_cmd 60 "$OUT/g3_control_hz.txt"
rc=0
python3 "$HERE/measure_rates.py" --hz-file "$OUT/g3_lidar_hz.txt"   --target "$LHZ_T" --tol "$LHZ_TOL" --label LiDAR   || rc=1
python3 "$HERE/measure_rates.py" --hz-file "$OUT/g3_control_hz.txt" --target "$CHZ_T" --tol "$CHZ_TOL" --label control || rc=1
exit $rc
