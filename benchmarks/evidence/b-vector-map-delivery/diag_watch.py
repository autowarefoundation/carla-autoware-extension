#!/usr/bin/env python3
"""Log the component_state_monitor verdict for /map/vector_map over time.

Prints one line per received DiagnosticArray status change, with the wall clock
attached, so the moment an in-stack early-joining subscriber first receives the
map is measured rather than inferred.
"""
import sys
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.qos import QoSProfile, QoSReliabilityPolicy

window_s = float(sys.argv[1]) if len(sys.argv) > 1 else 180.0
LEVELS = {0: "OK", 1: "WARN", 2: "ERROR", 3: "STALE"}

rclpy.init()
node = rclpy.create_node("diag_watch_%d" % (int(time.time() * 1000) % 1000000000))
last = {}


def cb(msg):
    for st in msg.status:
        if "vector_map" not in st.name:
            continue
        lvl = LEVELS.get(
            st.level if isinstance(st.level, int) else int.from_bytes(st.level, "big"),
            st.level,
        )
        kv = dict((k.key, k.value) for k in st.values)
        sig = (st.name, lvl, kv.get("status"), kv.get("last_message_time"))
        if last.get(st.name) == sig:
            continue
        last[st.name] = sig
        print(
            "WATCH wall=%.3f name=%s level=%s status=%s now=%s last_message_time=%s"
            % (
                time.time(),
                st.name,
                lvl,
                kv.get("status"),
                kv.get("now"),
                kv.get("last_message_time"),
            ),
            flush=True,
        )


node.create_subscription(
    DiagnosticArray,
    "/diagnostics",
    cb,
    QoSProfile(depth=100, reliability=QoSReliabilityPolicy.RELIABLE),
)
print("WATCH start wall=%.3f window=%.0fs" % (time.time(), window_s), flush=True)
t0 = time.time()
while time.time() - t0 < window_s:
    rclpy.spin_once(node, timeout_sec=0.2)
print("WATCH end wall=%.3f" % time.time(), flush=True)
node.destroy_node()
rclpy.shutdown()
