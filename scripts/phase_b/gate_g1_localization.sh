#!/usr/bin/env bash
# G1: after setting an initial pose, NDT must track the ego on Nishi-Shinjuku.
# Collects an NDT pose series (container) + a CARLA ground-truth series (host) over the
# SAME wall-clock window, then feeds both through measure_ndt.py, which computes the max
# XY error and EXITS NON-ZERO on FAIL (automated pass/fail, run_g0.sh style — no eyeballing).
set -euo pipefail
export ROS_DOMAIN_ID=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
COMPOSE="$REPO/docker/compose.yaml"
WIN=20   # seconds
NDT=/tmp/g1_ndt.txt GT=/tmp/g1_gt.txt

# 1) NDT pose series inside the container -> /tmp/g1_ndt.txt (t x y), then copy out.
docker compose -f "$COMPOSE" exec -T autoware bash -lc '
  source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash && export ROS_DOMAIN_ID=0
  python3 - "'"$WIN"'" <<PY
import sys, time, rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
end=time.time()+float(sys.argv[1]); rclpy.init(); n=Node("g1"); rows=[]
n.create_subscription(PoseStamped,"/localization/pose_estimator/pose",
  lambda m: rows.append(f"{time.time():.3f} {m.pose.position.x:.4f} {m.pose.position.y:.4f}"), 10)
while time.time()<end and rclpy.ok(): rclpy.spin_once(n, timeout_sec=0.1)
open("/tmp/g1_ndt.txt","w").write("\n".join(rows)+"\n"); print(f"ndt_rows={len(rows)}")
PY' &
CPID=$!
# 2) CARLA ground-truth series on the host over the same window (ego = role_name "ego").
python3 - "$WIN" "$GT" <<'PY' &
import sys, time, carla
win=float(sys.argv[1]); out=sys.argv[2]
w=carla.Client("localhost",2000).get_world()
ego=next(a for a in w.get_actors().filter("vehicle.*") if a.attributes.get("role_name")=="ego")
end=time.time()+win; rows=[]
while time.time()<end:
    t=ego.get_transform().location; rows.append(f"{time.time():.3f} {t.x:.4f} {-t.y:.4f}")  # Y-flip to map frame
    time.sleep(0.05)
open(out,"w").write("\n".join(rows)+"\n"); print(f"gt_rows={len(rows)}")
PY
GPID=$!
wait $CPID; wait $GPID
docker compose -f "$COMPOSE" cp autoware:/tmp/g1_ndt.txt "$NDT"

# 3) Programmatic PASS/FAIL (exit non-zero on FAIL).
python3 "$HERE/measure_ndt.py" --ndt "$NDT" --gt "$GT" --max-err-m 0.5
