#!/usr/bin/env python3
"""Report the live component_state_monitor verdict for map topics.

Subscribes to /diagnostics for a bounded window and prints every status whose
name mentions vector_map / pointcloud_map. This reads an IN-STACK subscriber's
own opinion of whether /map/vector_map was delivered to it, independently of
the probe subscribers this task creates.
"""
import sys
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.qos import QoSProfile, QoSReliabilityPolicy

window_s = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0

rclpy.init()
node = rclpy.create_node("diag_probe_%d" % (int(time.time() * 1000) % 1000000000))
seen = {}
LEVELS = {0: "OK", 1: "WARN", 2: "ERROR", 3: "STALE"}


def cb(msg):
    for st in msg.status:
        if "vector_map" in st.name or "pointcloud_map" in st.name:
            kv = " ".join("%s=%s" % (k.key, k.value) for k in st.values)
            seen[st.name] = "%s level=%s message=%r %s" % (
                st.name,
                LEVELS.get(st.level, st.level),
                st.message,
                kv,
            )


node.create_subscription(
    DiagnosticArray,
    "/diagnostics",
    cb,
    QoSProfile(depth=50, reliability=QoSReliabilityPolicy.RELIABLE),
)
t0 = time.time()
while time.time() - t0 < window_s:
    rclpy.spin_once(node, timeout_sec=0.2)
if not seen:
    print("DIAG: no vector_map/pointcloud_map status seen in %.0fs" % window_s)
for k in sorted(seen):
    print("DIAG " + seen[k])
node.destroy_node()
rclpy.shutdown()
