"""Does cell A's `concatenate_data` EMIT, or does it only ADVERTISE?

Written for P3 Phase 0 fix round 1 (finding F3). Phase 0's probe P1 measured
**2 publishers** on `/sensing/lidar/concatenated/pointcloud` on a live cell-A
stack, which refuted the campaign's pre-declared hypothesis (that the same
double publication is present only on cell B). But P1's pre-declared criterion
is a publisher *count*, and a count cannot tell an advertised publisher from an
emitting one. The spec's hypothesis names double *publication*. So the ruling
rests on the count meaning what it was declared to mean, and this probe is what
establishes that -- or refutes it.

DECISION RULE, stated here before the probe was ever run:

  * `concatenate_data` EMITS  <=> RELAY_OUT carries strictly more traffic than
    the relay alone forwards. Concretely, ANY of:
      - out_count materially exceeds in_count (approaching 2x for two 20 Hz
        sources), or
      - RELAY_OUT carries header stamps that never appeared on RELAY_IN (a
        second source with its own stamps), or
      - RELAY_OUT carries DUPLICATE header stamps (a second source that copies
        its input's stamp, which is what a concatenation node does).
  * `concatenate_data` only ADVERTISES <=> out_count ~= in_count, every
    RELAY_OUT stamp is one the relay could have forwarded (present on
    RELAY_IN), and there are no duplicates.

Both outcomes are decision-relevant and neither is the "hoped for" one, which
is why the rule is fixed in this docstring rather than chosen after the
numbers land.

WHY STAMP IDENTITY AND NOT JUST A RATE. `ros2 topic hz` reports the SUM over
publishers and cannot attribute flow. The relay (`topic_tools relay`) forwards
its input message verbatim, so every message it puts on RELAY_OUT carries a
header stamp that also appeared on RELAY_IN. A second publisher cannot fake
that property for free: it either stamps its output itself (unmatched stamps)
or copies its input's stamp (duplicate stamps). Matching the two stamp streams
therefore attributes traffic to a source, which a rate cannot.

KNOWN LIMITATION, stated rather than hidden: this is a subscriber-side
measurement over BEST_EFFORT QoS, so it can under-count if the probe drops
samples. That biases toward the "only advertises" conclusion, i.e. AGAINST the
ruling this probe is checking, so it cannot manufacture a false confirmation.
It is mitigated three ways: a deep queue, a reported drop-sensitive
in-count/out-count pair, and the independent `ros2 topic hz` readings taken
alongside it (an entirely separate subscriber). The duplicate-stamp signal in
particular survives drops -- losing samples cannot create duplicates.

Run INSIDE the Autoware container, where /work/benchmarks is mounted:

    docker exec autoware bash -lc 'source /opt/ros/humble/setup.bash &&
      source /opt/autoware/setup.bash &&
      python3 /work/benchmarks/evidence/p3-phase0/probe_concat_emission.py --seconds 20'
"""

from __future__ import annotations

import argparse
import collections
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import PointCloud2

RELAY_IN = "/sensing/lidar/top/pointcloud_before_sync"
RELAY_OUT = "/sensing/lidar/concatenated/pointcloud"


def sensor_qos(depth: int) -> QoSProfile:
    # Matches what `ros2 topic info -v` reported for BOTH publishers on
    # RELAY_OUT during P1: BEST_EFFORT / KEEP_LAST / VOLATILE. A RELIABLE
    # subscriber would not match them at all and would silently record zero.
    return QoSProfile(
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=depth,
        durability=QoSDurabilityPolicy.VOLATILE,
    )


class Probe(Node):
    def __init__(self, depth: int) -> None:
        super().__init__("probe_concat_emission")
        self.records: dict[str, list[tuple[float, int, int, str]]] = {
            RELAY_IN: [],
            RELAY_OUT: [],
        }
        for topic in (RELAY_IN, RELAY_OUT):
            self.create_subscription(
                PointCloud2,
                topic,
                lambda msg, t=topic: self._on_msg(t, msg),
                sensor_qos(depth),
            )

    def _on_msg(self, topic: str, msg: PointCloud2) -> None:
        stamp_ns = int(msg.header.stamp.sec) * 1_000_000_000 + int(msg.header.stamp.nanosec)
        self.records[topic].append(
            (time.monotonic(), stamp_ns, int(msg.width), msg.header.frame_id)
        )


def summarize(topic: str, rows: list[tuple[float, int, int, str]]) -> None:
    print(f"\n--- {topic} ---")
    print(f"messages received      : {len(rows)}")
    if not rows:
        print("  (no samples -- nothing to summarize)")
        return
    span = rows[-1][0] - rows[0][0]
    if span > 0:
        print(f"wall span / rate       : {span:.2f} s / {(len(rows) - 1) / span:.3f} Hz")
    stamps = [r[1] for r in rows]
    widths = collections.Counter(r[2] for r in rows)
    frames = collections.Counter(r[3] for r in rows)
    print(f"unique header stamps   : {len(set(stamps))}")
    print(f"widths (value: count)  : {dict(widths)}")
    print(f"frame_ids              : {dict(frames)}")
    stamp_span_s = (max(stamps) - min(stamps)) / 1e9
    if stamp_span_s > 0:
        print(f"stamp span / rate      : {stamp_span_s:.2f} s / {(len(stamps) - 1) / stamp_span_s:.3f} Hz")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--depth", type=int, default=200)
    args = parser.parse_args()

    rclpy.init()
    node = Probe(args.depth)
    print(f"collecting for {args.seconds:.0f} s on:\n  IN  {RELAY_IN}\n  OUT {RELAY_OUT}")
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)

    in_rows = node.records[RELAY_IN]
    out_rows = node.records[RELAY_OUT]
    summarize(RELAY_IN, in_rows)
    summarize(RELAY_OUT, out_rows)

    in_stamps = collections.Counter(r[1] for r in in_rows)
    out_stamps = collections.Counter(r[1] for r in out_rows)
    unmatched = sum(c for s, c in out_stamps.items() if s not in in_stamps)
    duplicates = sum(c - 1 for c in out_stamps.values() if c > 1)

    print("\n=== ATTRIBUTION ===")
    print(f"RELAY_IN  messages                        : {len(in_rows)}")
    print(f"RELAY_OUT messages                        : {len(out_rows)}")
    ratio = (len(out_rows) / len(in_rows)) if in_rows else float("nan")
    print(f"out/in ratio                              : {ratio:.3f}")
    print(f"RELAY_OUT stamps NOT seen on RELAY_IN     : {unmatched}")
    print(f"RELAY_OUT duplicate stamps (extra copies) : {duplicates}")

    emits = unmatched > 0 or duplicates > 0 or (in_rows and ratio > 1.25)
    print("\n=== VERDICT (by the decision rule in this file's docstring) ===")
    if not in_rows or not out_rows:
        print("INDETERMINATE: one of the two topics delivered no samples.")
    elif emits:
        print("concatenate_data EMITS: RELAY_OUT carries traffic the relay alone")
        print("cannot account for. Double PUBLICATION is present on cell A.")
    else:
        print("concatenate_data only ADVERTISES: every RELAY_OUT message is one the")
        print("relay forwarded (matched stamp, no duplicates, out/in ~= 1).")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
