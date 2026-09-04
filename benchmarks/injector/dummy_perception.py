#!/usr/bin/env python3
"""Dummy perception bridge for the perception:=false E2E stack (runs IN the container).

behavior_path_planner hard-blocks on `/perception/object_recognition/objects` ("waiting for
dynamic_object"), and AEB/obstacle_stop wait on an obstacle pointcloud. With perception OFF
(the stock universe-devel image cannot run it -- CUDA-only ground-seg + no DNN artifacts),
nothing publishes these, so no path -> no trajectory -> no control_cmd. This node supplies
the EMPTY ("clear road, no dynamic objects") versions so the planning+control chain runs --
exactly what a real perception stack would emit on an obstacle-free road. It is NOT part of
the gate; it stands in for the disabled perception so G2/G3 can exercise
localization+planning+control.

It also publishes every traffic-light group in the lanelet2 map as GREEN: with perception
off there is no traffic-light recognition, so the behavior_velocity traffic_light module
treats every signal as UNKNOWN -> STOP (a phantom red light inserts a stop wall ahead of the
ego). The green feed is the perception output a real recognition stack would emit on a green
light, supplied as a synthetic input instead of an autoware_launch overlay that deletes the
safety module. Group ids come from EITHER a live lanelet2 parse (--map, the original
behaviour) OR a committed --tl-groups YAML (benchmarks/injector/gen_tl_groups.py's schema);
see the module docstring on tl_group_ids_from_yaml for why the latter is what every campaign
cell should actually use.

Promoted to a first-class harness component (Task 7): benchmarks/, not scripts/e2e/, so this
runs identically for every approach under test (extension, bridge, tier4-native) instead of
being an e2e-only helper script -- a spec requirement, since a per-cell injector would
confound the very thing the campaign measures.

Run inside the `autoware` container (mounted at /work/benchmarks/injector/):

    source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash
    export ROS_DOMAIN_ID=0
    python3 /work/benchmarks/injector/dummy_perception.py

Stamps use SIM time (use_sim_time is forced on in main()): the whole stack is paced by
CARLA's /clock, so wall-clock stamps would be rejected as stale by the topic-rate monitors.
"""

import argparse
import os

import rclpy
import yaml
from autoware_perception_msgs.msg import (
    PredictedObjects,
    TrafficLightElement,
    TrafficLightGroup,
    TrafficLightGroupArray,
)
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import QoSDurabilityPolicy, QoSProfile
from sensor_msgs.msg import PointCloud2, PointField
from std_msgs.msg import Header

from benchmarks.injector.gen_tl_groups import tl_group_ids

# Container-side map bundle. $MAP_DIR is what run_e2e.sh / launch_autoware.sh
# already select, so this follows the map being driven without a second knob.
DEFAULT_MAP = os.path.join(
    os.environ.get("MAP_DIR", "/autoware_map/nishishinjuku"), "lanelet2_map.osm"
)
# Fallback map-frame centre for the all-free occupancy grid (the Nishi-Shinjuku
# spawn area). arm_closed_loop.sh passes --grid-center so the free area
# actually surrounds the ego (or the route) on any map; this constant only
# serves a bare invocation.
EGO_X, EGO_Y = 81377.34, 49916.93


def tl_group_ids_from_yaml(path: str) -> list[int]:
    """Traffic-light group ids from a committed YAML (gen_tl_groups.py's
    ``{map: ..., groups: [...]}`` schema), bypassing the live lanelet2 parse
    in ``tl_group_ids``.

    This is what makes the injector run IDENTICALLY in every cell: a live
    parse is deterministic given a fixed map bundle, but it still touches
    the filesystem the container mounts read-only per invocation, which is
    one more thing that could differ between cells if that mount ever
    drifts mid campaign. A committed file removes even that as a source of
    cross-cell variance -- every cell reads the exact same ids.
    """
    with open(path) as f:
        doc = yaml.safe_load(f)
    return [int(g) for g in doc["groups"]]


def occupancy_grid_geometry(
    grid_center: tuple[float, float], grid_size_m: float, resolution_m: float = 0.5
) -> dict:
    """All-free OccupancyGrid geometry for the given centre/span.

    Pure (no ROS/rclpy message type needed to call it), so the --grid-size ->
    message-dimensions link is unit-testable without stubbing a live rclpy
    Node (tests/e2e/test_dummy_perception.py). ``tick()`` below copies these
    fields onto a real OccupancyGrid.msg unchanged -- this IS the plumbing,
    not a stand-in for it.
    """
    n = max(1, round(grid_size_m / resolution_m))
    cx, cy = grid_center
    return {
        "resolution": resolution_m,
        "width": n,
        "height": n,
        "origin_x": cx - n * resolution_m / 2.0,
        "origin_y": cy - n * resolution_m / 2.0,
        "data": [0] * (n * n),
    }


class DummyPerception(Node):
    def __init__(
        self,
        tl_ids: list[int],
        grid_center: tuple[float, float] = (EGO_X, EGO_Y),
        grid_size_m: float = 200.0,
    ):
        super().__init__(
            "dummy_perception",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        self.tl_ids = tl_ids
        self.grid_cx, self.grid_cy = grid_center
        self.grid_size_m = grid_size_m
        self.objs = self.create_publisher(
            PredictedObjects, "/perception/object_recognition/objects", 10
        )
        grid_qos = QoSProfile(depth=1)
        grid_qos.durability = QoSDurabilityPolicy.TRANSIENT_LOCAL
        self.grid = self.create_publisher(
            OccupancyGrid, "/perception/occupancy_grid_map/map", grid_qos
        )
        self.pc = self.create_publisher(
            PointCloud2, "/perception/obstacle_segmentation/pointcloud", 10
        )
        self.tl = self.create_publisher(
            TrafficLightGroupArray, "/perception/traffic_light_recognition/traffic_signals", 10
        )
        self.timer = self.create_timer(0.1, self.tick)  # 10 Hz

    def stamp(self, frame: str) -> Header:
        h = Header()
        h.stamp = self.get_clock().now().to_msg()
        h.frame_id = frame
        return h

    def tick(self):
        po = PredictedObjects()
        po.header = self.stamp("map")
        self.objs.publish(po)

        og = OccupancyGrid()
        og.header = self.stamp("map")
        geo = occupancy_grid_geometry((self.grid_cx, self.grid_cy), self.grid_size_m)
        og.info.resolution = geo["resolution"]
        og.info.width = geo["width"]
        og.info.height = geo["height"]
        og.info.origin.position.x = geo["origin_x"]
        og.info.origin.position.y = geo["origin_y"]
        og.info.origin.orientation.w = 1.0
        og.data = geo["data"]
        self.grid.publish(og)

        pc = PointCloud2()
        pc.header = self.stamp("base_link")
        pc.height = 1
        pc.width = 0
        pc.fields = [
            PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
        ]
        pc.is_bigendian = False
        pc.point_step = 12
        pc.row_step = 0
        pc.data = b""
        pc.is_dense = True
        self.pc.publish(pc)

        tl = TrafficLightGroupArray()
        tl.stamp = self.get_clock().now().to_msg()
        for gid in self.tl_ids:
            g = TrafficLightGroup()
            g.traffic_light_group_id = gid
            e = TrafficLightElement()
            e.color = TrafficLightElement.GREEN
            e.shape = TrafficLightElement.CIRCLE
            e.status = TrafficLightElement.SOLID_ON
            e.confidence = 1.0
            g.elements.append(e)
            tl.traffic_light_groups.append(g)
        self.tl.publish(tl)


def build_arg_parser() -> argparse.ArgumentParser:
    """Split out from main() so the CLI surface (flags, defaults, types) is
    unit-testable without rclpy/ROS message stubs (tests/e2e/test_dummy_perception.py)."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--map", default=DEFAULT_MAP, help="lanelet2 .osm to read TL groups from")
    p.add_argument(
        "--tl-groups",
        default=None,
        metavar="YAML",
        help="committed traffic-light-group YAML (gen_tl_groups.py's schema); when given, "
        "TAKES PRIORITY over --map and no live lanelet2 parse happens at all -- this is "
        "what every campaign cell should pass, so the injected signal feed is identical "
        "in every cell regardless of what --map's live parse would find",
    )
    p.add_argument(
        "--grid-center",
        nargs=2,
        type=float,
        default=(EGO_X, EGO_Y),
        metavar=("MAP_X", "MAP_Y"),
        help="map-frame centre of the all-free occupancy grid (default: the "
        "Nishi-Shinjuku spawn area)",
    )
    p.add_argument(
        "--grid-size",
        type=float,
        default=200.0,
        metavar="METERS",
        help="occupancy-grid span in metres, centred on --grid-center "
        "(default: 200, today's fixed behaviour)",
    )
    return p


def main():
    args = build_arg_parser().parse_args()
    if args.tl_groups:
        # No live lanelet2 parse: see --tl-groups' help and
        # tl_group_ids_from_yaml's docstring for why this is the path every
        # campaign cell should use.
        ids = tl_group_ids_from_yaml(args.tl_groups)
        source = args.tl_groups
    else:
        ids = tl_group_ids(args.map)
        source = args.map
    rclpy.init()
    node = DummyPerception(ids, (args.grid_center[0], args.grid_center[1]), args.grid_size)
    node.get_logger().info(
        f"publishing clear-road perception; {len(ids)} TL groups GREEN "
        f"(source {source}, grid centred on {args.grid_center[0]:.1f},"
        f"{args.grid_center[1]:.1f}, span {args.grid_size:.1f} m)"
    )
    if not ids:
        # Visible, but not fatal: see tl_group_ids. Named so a signalised map
        # that somehow parsed to zero groups is still noticed in the log.
        node.get_logger().warning(f"{source} declares NO traffic lights; none to force green")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
