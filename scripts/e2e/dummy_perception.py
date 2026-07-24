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
safety module. Group ids are parsed from the map itself (regulatory_element/traffic_light
relations), so this script has no side-channel input files.

Run inside the `autoware` container (mounted at /work/scripts/e2e/):

    source /opt/ros/humble/setup.bash && source /opt/autoware/setup.bash
    export ROS_DOMAIN_ID=0
    python3 /work/scripts/e2e/dummy_perception.py

Stamps use SIM time (use_sim_time is forced on in main()): the whole stack is paced by
CARLA's /clock, so wall-clock stamps would be rejected as stale by the topic-rate monitors.
"""

import argparse
import xml.etree.ElementTree as ET

import rclpy
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

DEFAULT_MAP = "/autoware_map/nishishinjuku/lanelet2_map.osm"
# Map-frame centre for the all-free occupancy grid (the Nishi-Shinjuku spawn area).
EGO_X, EGO_Y = 81377.34, 49916.93


def tl_group_ids(osm_path: str) -> list[int]:
    """Traffic-light regulatory-element ids from the lanelet2 .osm (= Autoware's
    traffic_light_group_id). Fails loudly if none are found -- an empty green feed
    would silently leave every signal UNKNOWN and reintroduce the phantom red light."""
    root = ET.parse(osm_path).getroot()
    ids = []
    for rel in root.iter("relation"):
        tags = {t.get("k"): t.get("v") for t in rel.findall("tag")}
        if tags.get("type") == "regulatory_element" and tags.get("subtype") == "traffic_light":
            ids.append(int(rel.get("id")))
    if not ids:
        raise RuntimeError(f"no traffic_light regulatory elements found in {osm_path}")
    return sorted(ids)


class DummyPerception(Node):
    def __init__(self, tl_ids: list[int]):
        super().__init__(
            "dummy_perception",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        self.tl_ids = tl_ids
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
        res = 0.5
        n = 400  # 200 m span, all free
        og.info.resolution = res
        og.info.width = n
        og.info.height = n
        og.info.origin.position.x = EGO_X - n * res / 2.0
        og.info.origin.position.y = EGO_Y - n * res / 2.0
        og.info.origin.orientation.w = 1.0
        og.data = [0] * (n * n)
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--map", default=DEFAULT_MAP, help="lanelet2 .osm to read TL groups from")
    args = p.parse_args()
    ids = tl_group_ids(args.map)
    rclpy.init()
    node = DummyPerception(ids)
    node.get_logger().info(f"publishing clear-road perception; {len(ids)} TL groups GREEN")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
