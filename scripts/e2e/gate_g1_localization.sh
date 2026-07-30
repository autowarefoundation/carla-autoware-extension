#!/usr/bin/env bash
# G1: after setting an initial pose, NDT must track the ego on the active map.
# Collects an NDT pose series (container) + a CARLA ground-truth series (host) over the
# SAME wall-clock window, then feeds both through measure_ndt.py, which computes the max
# XY error and EXITS NON-ZERO on FAIL (automated pass/fail, run_g0.sh style — no eyeballing).
#
# EVIDENCE DURABILITY (2026-07-29). This script used to write two FIXED paths,
# /tmp/g1_ndt.txt and /tmp/g1_gt.txt, so every invocation silently DESTROYED the
# previous run's raw series. That cost the Task 11 record three measured
# windows: once the ladder's refit run had overwritten them, the 0.824 m and
# 0.749 m maxima could no longer be re-derived by anyone. In this campaign a
# gate report is an evidence document (CLAUDE.md: "exact digests, commits,
# thresholds, PASS/FAIL per check"), and a number nobody can recompute is weak
# evidence. Each invocation now gets its OWN directory and retains both series
# plus a provenance summary, so a later reader recomputes the verdict from
# artifacts instead of trusting a transcript.
#
#   G1_RUN_DIR=<dir>   where to retain this run's artifacts
#                      (default: reports/g1-<UTC timestamp>)
#
# Retained per run: g1_ndt.txt, g1_gt.txt (the raw series measure_ndt.py
# consumes) and g1_summary.txt (map, bundle + its sha256, window, sample
# counts, verdict). reports/ is the natural home: docker/compose.yaml already
# bind-mounts it read-write and it is the one path in this tree runs are
# expected to write to.
set -euo pipefail
export ROS_DOMAIN_ID=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"
WIN=20   # seconds

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${G1_RUN_DIR:-$REPO/reports/g1-$STAMP}"
# Named refusal, not a bare mkdir error. docker/compose.yaml bind-mounts
# ../reports into a container that runs as ROOT, so if the host directory did
# not already exist Docker CREATES IT root-owned and the host user then cannot
# make a run directory inside it -- measured 2026-07-29. The repair is one
# command and it is the message, because the alternative (silently relocating
# the artifacts) is how evidence goes missing.
if ! mkdir -p "$RUN_DIR" 2>/dev/null; then
  echo "PREFLIGHT FAIL: cannot create $RUN_DIR" >&2
  echo "  reports/ is bind-mounted into the root-running autoware" >&2
  echo "  container, so Docker may have created it root-owned." >&2
  echo "  Fix ownership with:" >&2
  echo "    docker compose -f docker/compose.yaml exec -T autoware \\" >&2
  echo "      bash -lc 'chown -R $(id -u):$(id -g) /work/reports'" >&2
  echo "  or set G1_RUN_DIR to a directory you can write." >&2
  exit 1
fi
NDT="$RUN_DIR/g1_ndt.txt"
GT="$RUN_DIR/g1_gt.txt"
SUMMARY="$RUN_DIR/g1_summary.txt"
# The container-side path is stamped too: two gate runs overlapping against
# the same container would otherwise collide on one /tmp file -- the same
# defect one scale down.
CNDT="/tmp/g1_ndt_$STAMP.txt"
echo "OK: G1 artifacts -> $RUN_DIR"

# Which bundle is being localized against, recorded BEFORE measuring so the
# verdict is attributable to specific bytes. MAP_DIR is the CONTAINER path; the
# host copy is $HOME/autoware_map/<basename> by docker/compose.yaml's
# one-mount-per-bundle convention. Unreadable is RECORDED, never fatal: this
# gate's job is the measurement, not bundle bookkeeping, and a missing host
# copy does not invalidate the series.
MAP_NAME="${CARLA_AUTOWARE_MAP:-NishishinjukuMap}"
# The linter runs without -x in pre-commit and so cannot follow the source
# even with the directive below; SC1091 is informational, disabled for that.
# shellcheck source=scripts/e2e/map_defaults.sh disable=SC1091
. "$REPO/scripts/e2e/map_defaults.sh"
carla_autoware_map_defaults "$MAP_NAME"
BUNDLE_DIR="${MAP_DIR:-$MAP_DEFAULT_DIR}"
HOST_PCD="$HOME/autoware_map/$(basename "${BUNDLE_DIR:-unknown}")/pointcloud_map.pcd"
if [ -r "$HOST_PCD" ]; then
  PCD_SHA="$(sha256sum "$HOST_PCD" | cut -d' ' -f1)"
else
  PCD_SHA="unreadable ($HOST_PCD)"
fi

# 1) NDT pose series inside the container -> $CNDT (t x y), then copy out.
docker compose -f "$COMPOSE" exec -T autoware bash -lc '
  source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0
  python3 - "'"$WIN"'" "'"$CNDT"'" <<PY
import sys, time, rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
end=time.time()+float(sys.argv[1]); out=sys.argv[2]; rclpy.init(); n=Node("g1"); rows=[]
n.create_subscription(PoseStamped,"/localization/pose_estimator/pose",
  lambda m: rows.append(f"{time.time():.3f} {m.pose.position.x:.4f} {m.pose.position.y:.4f}"), 10)
while time.time()<end and rclpy.ok(): rclpy.spin_once(n, timeout_sec=0.1)
open(out,"w").write("\n".join(rows)+"\n"); print(f"ndt_rows={len(rows)}")
PY' &
CPID=$!
# 2) CARLA ground-truth series on the host over the same window (ego = role_name "ego").
# collect_gt.py maps CARLA metres into the map frame via the pinned affine
# (verify_mgrs_handedness.MAP_OFFSETS, byte-identical to the extension's MgrsOffset.h). The active
# map comes from $CARLA_AUTOWARE_MAP -- export it in THIS shell for a non-default map (run_e2e.sh
# prints the exact line), or the ground truth lands in the wrong frame.
PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m scripts.e2e.collect_gt --window "$WIN" --out "$GT" &
GPID=$!
wait $CPID; wait $GPID
docker compose -f "$COMPOSE" cp "autoware:$CNDT" "$NDT"

# 3) Programmatic PASS/FAIL (exit non-zero on FAIL). The verdict is tee'd into
# the run directory so it is retained beside the series it was computed from;
# PIPESTATUS keeps measure_ndt.py's exit code authoritative rather than tee's.
{
  echo "g1_run: $STAMP"
  echo "map: $MAP_NAME"
  echo "bundle_container_dir: ${BUNDLE_DIR:-unknown}"
  echo "bundle_pcd_sha256: $PCD_SHA"
  echo "window_s: $WIN"
  echo "ndt_series: $(basename "$NDT")  gt_series: $(basename "$GT")"
} >"$SUMMARY"
set +o pipefail
python3 "$HERE/measure_ndt.py" --ndt "$NDT" --gt "$GT" --max-err-m 0.5 | tee -a "$SUMMARY"
rc="${PIPESTATUS[0]}"
set -o pipefail
echo "OK: retained $RUN_DIR/{g1_ndt.txt,g1_gt.txt,g1_summary.txt}"
exit "$rc"
