#!/usr/bin/env bash
# THE cyclonedds bounding probe (Task 5, owner ruling): ONE cell-B closed-loop
# run under rmw_cyclonedds_cpp instead of the registered rmw_fastrtps_cpp +
# udp_only.xml, to test whether the latched-delivery defect is Fast-DDS-specific.
#
# TRANSPORT ACTUALLY IN FORCE, stated because it is the whole point:
#   --rmw rmw_cyclonedds_cpp --dds-profile none
#     -> the Autoware container runs RMW_IMPLEMENTATION=rmw_cyclonedds_cpp with
#        NO CYCLONEDDS_URI and NO profile mounted at all.
#     -> observer/config/udp_only.xml is a FAST-DDS profile and is NOT mounted
#        and NOT read: nothing in this run consumes it.
#   `--dds-profile none` rather than the harness's cyclone default
#   (docker/cyclonedds.xml) because that profile pins interfaces to `lo`, and
#   Task 9's matrix row 10 measured the fork INVISIBLE to the Autoware image
#   under it (no list, no echo, no rate). Row 11 -- cyclone, NO profile -- is
#   the only non-fastrtps cell in which the fork is readable at all (echo yes,
#   9.930 Hz), and it works by binding the host's routable NIC. The patches
#   README says not to use rows 6/11 for MEASUREMENT; this is a deviation probe
#   whose entire purpose is a different transport, and the dependency on the
#   host NIC and on Cyclone's flaky graph for bare-DDS publishers is disclosed
#   in the record rather than designed away.
#
# NON-DUEL: no --duel, so duel_admissible stays false. This is never verdict data.
set -u
REPO=/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0
OUT="$(cd "$(dirname "$0")" && pwd)/cap"

export ROS_DOMAIN_ID=0
export BENCH_TIER4_TRANSPORT_DEVIATION="task5 cyclonedds bounding probe: is the latched-delivery defect Fast-DDS-specific?"

echo "=== PREAMBLE at $(date +%s) ==="
uptime
nvidia-smi --query-gpu=name,memory.used,utilization.gpu --format=csv,noheader
echo "governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
# shellcheck disable=SC2009 # pgrep self-matches this script's own cmdline;
# the campaign preamble is explicit that the check is judged by cmdline, and
# `ps -eo pid,comm` is what makes a self-match impossible to mistake for CARLA.
echo "unreal/carla processes:"
# shellcheck disable=SC2009 # pgrep self-matches this script's own cmdline; the
# campaign preamble judges this check by cmdline, and `ps -eo pid,comm` makes a
# self-match impossible to mistake for a real CARLA process.
ps -eo pid,comm | grep -iE 'unreal|carla' || echo "  none"
echo "=== HYGIENE ==="
docker compose -f "$REPO/docker/compose.yaml" down --remove-orphans >/dev/null 2>&1 || true
docker rm -f autoware bench-observer aw-replica >/dev/null 2>&1 || true

echo "=== EXACT COMMAND ==="
echo "BENCH_TIER4_TRANSPORT_DEVIATION=\"$BENCH_TIER4_TRANSPORT_DEVIATION\" \\"
echo "  bash benchmarks/run.sh B --arm closed-loop --rmw rmw_cyclonedds_cpp --dds-profile none"
cd "$REPO" || exit 1
bash benchmarks/run.sh B --arm closed-loop --rmw rmw_cyclonedds_cpp --dds-profile none \
  >"$OUT/cyclone-probe.log" 2>&1
echo "run.sh exit=$?"
tail -25 "$OUT/cyclone-probe.log"
echo "=== CYCLONE PROBE DONE at $(date +%s) ==="
