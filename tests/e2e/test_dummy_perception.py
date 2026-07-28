"""Unit tests for dummy_perception's traffic-light parsing and grid sizing.

``tl_group_ids`` (now defined in ``benchmarks.injector.gen_tl_groups`` and
re-exported here, Task 7) is the one safety guard in this harness whose
failure condition was changed rather than added: it used to raise when the
map yielded no traffic-light ids, and now raises only when it yields no
lanelet relations. That is the correct scope -- a genuinely signal-free map
(CARLA's Town10 export: 168 lanelets, zero regulatory elements) must not
abort the arm -- but it makes "signalised map, zero groups parsed"
non-fatal, which is exactly the phantom-red-light case the green feed exists
to prevent. The three cases below pin both halves of that boundary.

``build_arg_parser``/``occupancy_grid_geometry`` cover the --grid-size ->
message-dimensions plumbing added for route-scoped free-space grids: the CLI
tests pin the flag's existence/type/default, and the geometry tests pin the
exact width/height/origin math ``tick()`` copies onto the real OccupancyGrid
message -- the same function, not a re-implementation of it, so this is
testing the plumbing rather than a mock standing in for it.

``tl_group_ids_from_yaml`` covers the --tl-groups path (Task 7): reading a
committed ``gen_tl_groups.py``-schema YAML instead of live-parsing a lanelet2
.osm, which is what lets the injector run identically in every campaign cell.

``benchmarks.injector.dummy_perception`` imports rclpy and the Autoware/ROS
message packages at module scope, and CI has none of them. They are stubbed
here with ``setdefault``, so a real ROS environment still uses the real
modules; the functions under test are pure (``xml.etree``, ``argparse``,
``yaml``, arithmetic) and never touch them.
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

from benchmarks.injector.dummy_perception import (  # noqa: E402
    build_arg_parser,
    occupancy_grid_geometry,
    tl_group_ids,
    tl_group_ids_from_yaml,
)


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


def test_grid_size_flag_defaults_to_todays_200m_span():
    """Default must reproduce today's behaviour byte-for-byte: no --grid-size
    means the historical 200 m / 0.5 m-resolution / 400x400-cell grid."""
    args = build_arg_parser().parse_args([])
    assert args.grid_size == 200.0
    assert tuple(args.grid_center) == pytest.approx((81377.34, 49916.93))


def test_grid_center_and_size_flags_are_parsed():
    args = build_arg_parser().parse_args(
        ["--grid-center", "10.5", "-20.25", "--grid-size", "50"]
    )
    assert tuple(args.grid_center) == pytest.approx((10.5, -20.25))
    assert args.grid_size == 50.0


def test_occupancy_grid_geometry_default_span_matches_todays_grid():
    """Pinned regression: 200 m span at 0.5 m resolution has always been
    400x400 cells; a --grid-size refactor must not silently change it."""
    geo = occupancy_grid_geometry((0.0, 0.0), 200.0)
    assert geo["width"] == 400
    assert geo["height"] == 400
    assert geo["resolution"] == 0.5
    assert len(geo["data"]) == 400 * 400


def test_occupancy_grid_geometry_dimensions_follow_grid_size():
    """The message's width/height (cell counts) must scale with --grid-size,
    not stay pinned at the old fixed 200 m span."""
    small = occupancy_grid_geometry((0.0, 0.0), 50.0)
    large = occupancy_grid_geometry((0.0, 0.0), 600.0)
    assert small["width"] == small["height"] == 100
    assert large["width"] == large["height"] == 1200
    assert large["width"] > small["width"]
    # The physical span the message covers (cells * resolution) must equal
    # the requested --grid-size, not just some arbitrary larger cell count.
    assert small["width"] * small["resolution"] == pytest.approx(50.0)
    assert large["width"] * large["resolution"] == pytest.approx(600.0)
    assert len(small["data"]) == small["width"] * small["height"]
    assert len(large["data"]) == large["width"] * large["height"]


def test_occupancy_grid_geometry_is_centred_on_grid_center():
    """origin = centre - half the physical span, on both axes independently,
    so a --grid-center that is not the ego (e.g. a route bbox midpoint) still
    produces a grid that actually surrounds that point."""
    geo = occupancy_grid_geometry((1000.0, -500.0), 100.0)
    span = geo["width"] * geo["resolution"]
    assert geo["origin_x"] == pytest.approx(1000.0 - span / 2.0)
    assert geo["origin_y"] == pytest.approx(-500.0 - span / 2.0)


# ---------------------------------------------------------------------------
# --tl-groups: reading gen_tl_groups.py's committed YAML instead of live
# lanelet2 parsing (Task 7 -- what makes the injector identical in every cell).
# ---------------------------------------------------------------------------


def _tl_groups_yaml(tmp_path, map_name, groups):
    path = tmp_path / f"{map_name}.yaml"
    lines = [f"map: {map_name}", "groups:" + (" []" if not groups else "")]
    lines += [f"  - {g}" for g in groups]
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def test_tl_group_ids_from_yaml_reads_the_committed_groups_list(tmp_path):
    path = _tl_groups_yaml(tmp_path, "NishishinjukuMap", [21, 700, 3020])
    assert tl_group_ids_from_yaml(path) == [21, 700, 3020]


def test_tl_group_ids_from_yaml_handles_an_empty_groups_list(tmp_path):
    """Town10HD_Opt's committed file: signal-free map, groups: []."""
    path = _tl_groups_yaml(tmp_path, "Town10HD_Opt", [])
    assert tl_group_ids_from_yaml(path) == []


def test_tl_groups_flag_defaults_to_none_so_the_live_parse_still_runs():
    """No --tl-groups means today's behaviour is unchanged: main() falls back
    to tl_group_ids(args.map)."""
    args = build_arg_parser().parse_args([])
    assert args.tl_groups is None


def test_tl_groups_flag_is_parsed():
    args = build_arg_parser().parse_args(["--tl-groups", "/some/path.yaml"])
    assert args.tl_groups == "/some/path.yaml"
