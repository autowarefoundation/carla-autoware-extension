"""Unit tests for dummy_perception's traffic-light group parsing.

``tl_group_ids`` is the one safety guard in this harness whose failure
condition was changed rather than added: it used to raise when the map yielded
no traffic-light ids, and now raises only when it yields no lanelet relations.
That is the correct scope -- a genuinely signal-free map (CARLA's Town10
export: 168 lanelets, zero regulatory elements) must not abort the arm -- but
it makes "signalised map, zero groups parsed" non-fatal, which is exactly the
phantom-red-light case the green feed exists to prevent. The three cases below
pin both halves of that boundary.

``scripts.e2e.dummy_perception`` imports rclpy and the Autoware/ROS message
packages at module scope, and CI has none of them. They are stubbed here with
``setdefault``, so a real ROS environment still uses the real modules; the
function under test is pure ``xml.etree`` and never touches them.
"""

from __future__ import annotations

import sys
import types

import pytest


class _StubModule(types.ModuleType):
    """Yields a fresh empty class for any attribute, so ``from x import Y``
    and ``class Z(Node)`` both work without the real package."""

    def __getattr__(self, name: str):
        return type(name, (), {})


for _name in (
    "rclpy",
    "rclpy.node",
    "rclpy.parameter",
    "rclpy.qos",
    "autoware_perception_msgs",
    "autoware_perception_msgs.msg",
    "nav_msgs",
    "nav_msgs.msg",
    "sensor_msgs",
    "sensor_msgs.msg",
    "std_msgs",
    "std_msgs.msg",
):
    sys.modules.setdefault(_name, _StubModule(_name))

from scripts.e2e.dummy_perception import tl_group_ids  # noqa: E402


def _osm(tmp_path, lanelet_ids, traffic_light_ids):
    """Write a minimal lanelet2-shaped .osm carrying the given relations."""
    parts = ["<?xml version='1.0' encoding='UTF-8'?>", "<osm version='0.6'>"]
    for rel_id in lanelet_ids:
        parts.append(f"<relation id='{rel_id}'><tag k='type' v='lanelet'/></relation>")
    for rel_id in traffic_light_ids:
        parts.append(
            f"<relation id='{rel_id}'>"
            f"<tag k='type' v='regulatory_element'/>"
            f"<tag k='subtype' v='traffic_light'/></relation>"
        )
    parts.append("</osm>")
    path = tmp_path / "lanelet2_map.osm"
    path.write_text("\n".join(parts))
    return str(path)


def test_returns_traffic_light_group_ids_sorted(tmp_path):
    path = _osm(tmp_path, lanelet_ids=[1, 2], traffic_light_ids=[3020, 21, 700])
    assert tl_group_ids(path) == [21, 700, 3020]


def test_signal_free_map_yields_empty_list(tmp_path):
    """Legal: some maps genuinely carry no signals (Town10's export), and
    there is then nothing to force green."""
    path = _osm(tmp_path, lanelet_ids=[1, 2, 3], traffic_light_ids=[])
    assert tl_group_ids(path) == []


def test_no_lanelet_relations_raises(tmp_path):
    """Not legal: no lanelets means the wrong file or a broken parse, and a
    silently empty green feed leaves every signal UNKNOWN -> STOP."""
    path = _osm(tmp_path, lanelet_ids=[], traffic_light_ids=[])
    with pytest.raises(RuntimeError, match="no lanelet relations"):
        tl_group_ids(path)
