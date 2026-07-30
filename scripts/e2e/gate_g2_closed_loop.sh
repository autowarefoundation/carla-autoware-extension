#!/usr/bin/env bash
# G2: engage -> closed-loop drive -> route completion on a traffic-light-free route.
# Sends engage, confirms control_cmd is flowing, then records the ego-to-goal distance
# series (host, CARLA ground-truth) and feeds it to measure_route.py, which EXITS
# NON-ZERO unless the ego reaches within tolerance of the goal (automated pass/fail).
# Usage: gate_g2_closed_loop.sh <goal_map_x> <goal_map_y>
#
# EVIDENCE DURABILITY (2026-07-29): same fix, and same reason, as
# gate_g1_localization.sh -- the fixed /tmp/g2_dist.txt and /tmp/g2_hz.txt were
# overwritten by the next invocation, so a recorded closest-approach number
# could not be re-derived afterwards. Each run now retains its own copies.
#
#   G2_RUN_DIR=<dir>   where to retain this run's artifacts
#                      (default: reports/g2-<UTC timestamp>)
#
# Retained per run: g2_dist.txt (the distance series measure_route.py consumes),
# g2_hz.txt (the gated-control liveness capture, which is the evidence that the
# vehicle was actually under command) and g2_summary.txt.
set -euo pipefail
export ROS_DOMAIN_ID=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"
GOAL_X="${1:?goal map x required}"; GOAL_Y="${2:?goal map y required}"
WIN=120   # seconds to reach the goal

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${G2_RUN_DIR:-$REPO/reports/g2-$STAMP}"
mkdir -p "$RUN_DIR"
DIST="$RUN_DIR/g2_dist.txt"
HZ="$RUN_DIR/g2_hz.txt"
SUMMARY="$RUN_DIR/g2_summary.txt"
CHZ="/tmp/g2_hz_$STAMP.txt"
echo "OK: G2 artifacts -> $RUN_DIR"

# Engage + assert control_cmd is actually flowing (a hard precondition for actuation).
# `ros2 topic hz` never self-terminates, so `timeout` SIGKILLs it and returns 124 on the
# expected/healthy path -- that is NOT a failure. The real liveness test is whether the
# captured output contains an "average rate:" line; a 124 with rate lines present means
# control_cmd IS live, so proceed. Only a genuinely silent topic (no rate lines) is FAIL.
#
# NOTE the rate alone is not evidence of command AUTHORITY: measured
# 2026-07-29, the gated topic publishes at ~19.9 Hz even in STOP mode,
# carrying zero-velocity commands. This check is a liveness precondition; the
# distance series below is what decides G2.
docker compose -f "$COMPOSE" exec -T autoware bash -lc '
  source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0
  ros2 topic pub -1 /autoware/engage autoware_vehicle_msgs/msg/Engage "{engage: true}"
  echo "engaged; checking control_cmd liveness:"
  set +o pipefail
  timeout 10 ros2 topic hz /control/command/control_cmd --window 30 > "'"$CHZ"'" 2>&1; rc=$?
  set -o pipefail
  cat "'"$CHZ"'"
  grep -q "average rate:" "'"$CHZ"'" \
    || { echo "G2 FAIL: no control_cmd (vehicle_cmd_gate not commanding)"; exit 1; }
  [ "$rc" -eq 124 ] || [ "$rc" -eq 0 ] || { echo "G2 FAIL: ros2 topic hz errored rc=$rc"; exit "$rc"; }'
docker compose -f "$COMPOSE" cp "autoware:$CHZ" "$HZ" 2>/dev/null || true

# Ego-to-goal distance series (map frame; CARLA Y is flipped to map).
# collect_gt.py maps CARLA metres into the map frame via the pinned affine
# (verify_mgrs_handedness.MAP_OFFSETS, byte-identical to the extension's MgrsOffset.h) before
# taking the XY distance to the goal. The active map comes from $CARLA_AUTOWARE_MAP -- export it
# in THIS shell for a non-default map (run_e2e.sh prints the exact line).
PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m scripts.e2e.collect_gt --window "$WIN" --out "$DIST" --goal "$GOAL_X" "$GOAL_Y"

# Programmatic PASS/FAIL. Run this gate against the SYNC stack: sync propels given a valid
# trajectory, and async breaks NDT outright (docs/e2e-report.md "Async localization").
{
  echo "g2_run: $STAMP"
  echo "map: ${CARLA_AUTOWARE_MAP:-NishishinjukuMap}"
  echo "goal_map_xy: $GOAL_X $GOAL_Y"
  echo "window_s: $WIN"
  echo "dist_series: $(basename "$DIST")  hz_capture: $(basename "$HZ")"
} >"$SUMMARY"
set +o pipefail
python3 "$HERE/measure_route.py" --distances "$DIST" --goal-tol-m 1.0 | tee -a "$SUMMARY"
rc="${PIPESTATUS[0]}"
set -o pipefail
echo "OK: retained $RUN_DIR/{g2_dist.txt,g2_hz.txt,g2_summary.txt}"
exit "$rc"
