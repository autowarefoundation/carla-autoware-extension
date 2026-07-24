#!/usr/bin/env bash
# G3: LiDAR sustained at 20 Hz; control loop at sim rate. ros2 topic hz measures
# WALL-CLOCK arrival, so the runner's real-time pacing MUST hold for 20 Hz to mean cadence.
# Captures both hz outputs to files and feeds each through
# measure_rates.py, which EXITS NON-ZERO when a rate leaves its band (so an 80 Hz
# free-running LiDAR FAILS instead of reading as PASS). Record which was measured.
set -euo pipefail
export ROS_DOMAIN_ID=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"
LHZ=/tmp/g3_lidar_hz.txt CHZ=/tmp/g3_control_hz.txt

# `ros2 topic hz` never self-terminates, so `timeout` SIGKILLs it and returns 124 on the
# expected/healthy path -- under `set -e`+`pipefail` that 124 would otherwise abort the
# script right after the LiDAR capture, before measure_rates.py or the control capture
# ever run. Scope pipefail off around each tee pipe, read the real exit code via
# PIPESTATUS (tee itself exits 0), and treat 124 (timeout fired, as expected) the same as
# 0 (clean exit) -- any OTHER rc is a genuine failure (e.g. the topic doesn't exist).
# The control topic is autoware_control_msgs/msg/Control, so its capture also needs the
# Autoware overlay sourced (matches gate_g1/gate_g2); sourcing it for LiDAR too is harmless.
set +o pipefail
docker compose -f "$COMPOSE" exec -T autoware bash -lc '
  source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0
  timeout 12 ros2 topic hz /sensing/lidar/top/pointcloud_raw_ex --window 40' | tee "$LHZ"
rc=${PIPESTATUS[0]}
set -o pipefail
[ "$rc" -eq 124 ] || [ "$rc" -eq 0 ] || { echo "G3 FAIL: LiDAR ros2 topic hz failed rc=$rc"; exit "$rc"; }

set +o pipefail
docker compose -f "$COMPOSE" exec -T autoware bash -lc '
  source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0
  timeout 12 ros2 topic hz /control/command/control_cmd --window 60' | tee "$CHZ"
rc=${PIPESTATUS[0]}
set -o pipefail
[ "$rc" -eq 124 ] || [ "$rc" -eq 0 ] || { echo "G3 FAIL: control ros2 topic hz failed rc=$rc"; exit "$rc"; }

# Control-loop band re-validated live (2026-07-23, sync-paced stack, use_sim_time:=true):
# /control/command/control_cmd (vehicle_cmd_gate output) measures a rock-steady ~19.96 Hz.
# It is the trajectory_follower's 0.03 s (33.3 Hz) design loop SUB-SAMPLED onto CARLA's 20 Hz
# /clock -- under use_sim_time every control node is paced by the simulation clock, so the
# control loop runs AT the 20 Hz simulation rate (same cadence as the LiDAR), NOT the
# free-running rate. (Corroboration: with the runner in --async, no /clock pacing, control_cmd
# free-runs at ~30 Hz, close to the 33 Hz ctrl_period design; vehicle_cmd_gate's own
# update_rate param is 10 Hz but control_cmd tracks the faster controller passthrough.) The
# original 60+-15 Hz band assumed a real-time free-running control loop, which does NOT hold
# under use_sim_time sync pacing -- hence 20+-5 Hz: PASS iff control tracks the sim rate, still
# FAILing a 10 Hz gate-timer-only or a 30 Hz async free-run reading.
rc=0
python3 "$HERE/measure_rates.py" --hz-file "$LHZ" --target 20 --tol 1  --label LiDAR   || rc=1
python3 "$HERE/measure_rates.py" --hz-file "$CHZ" --target 20 --tol 5  --label control || rc=1
exit "$rc"
