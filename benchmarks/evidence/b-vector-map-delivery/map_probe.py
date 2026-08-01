#!/usr/bin/env python3
"""Late-joining subscriber probe for one topic.

Reports, for a subscriber created AFTER the publisher has already published:
whether a sample arrives, how long it took, and how big it is. Used to
separate "never published" from "published but not delivered".

usage: map_probe.py <topic> <msg_type> <transient_local|volatile> <timeout_s>
"""
import sys
import time

import rclpy
from rosidl_runtime_py.utilities import get_message
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

topic, typestr, durability, timeout_s = (
    sys.argv[1],
    sys.argv[2],
    sys.argv[3],
    float(sys.argv[4]),
)

msg_type = get_message(typestr)
rclpy.init()
node = rclpy.create_node("map_probe_%d" % (int(time.time() * 1000) % 1000000000))
qos = QoSProfile(
    depth=1,
    history=QoSHistoryPolicy.KEEP_LAST,
    reliability=QoSReliabilityPolicy.RELIABLE,
    durability=(
        QoSDurabilityPolicy.TRANSIENT_LOCAL
        if durability == "transient_local"
        else QoSDurabilityPolicy.VOLATILE
    ),
)

state = {}
t0 = time.time()


def cb(msg):
    if "t" in state:
        return
    state["t"] = time.time() - t0
    payload = getattr(msg, "data", None)
    state["bytes"] = len(payload) if payload is not None else -1


sub = node.create_subscription(msg_type, topic, cb, qos)
npub_first = node.count_publishers(topic)
while time.time() - t0 < timeout_s and "t" not in state:
    rclpy.spin_once(node, timeout_sec=0.2)
npub_last = node.count_publishers(topic)

print(
    "PROBE topic=%s durability=%s result=%s t_first_s=%s data_bytes=%s "
    "publishers_at_start=%d publishers_at_end=%d wall_waited_s=%.2f"
    % (
        topic,
        durability,
        "RECEIVED" if "t" in state else "TIMEOUT",
        ("%.3f" % state["t"]) if "t" in state else "-",
        state.get("bytes", "-"),
        npub_first,
        npub_last,
        time.time() - t0,
    )
)
node.destroy_node()
rclpy.shutdown()
