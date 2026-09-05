import textwrap

import pytest

from scripts.e2e import lanelet_pose as lp
from scripts.e2e.map_frame import NISHISHINJUKU_ORIGIN, carla_to_map

# Two lanelets: id 1 runs +x from x=0..100 between y=0 (right) and y=4 (left);
# id 2 runs -x from x=200..100 between y=10 (right, as seen driving -x) and y=6 (left).
FIXTURE = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <osm generator="test">
      <node id="1" lat="0" lon="0"><tag k="local_x" v="0"/><tag k="local_y" v="4"/></node>
      <node id="2" lat="0" lon="0"><tag k="local_x" v="100"/><tag k="local_y" v="4"/></node>
      <node id="3" lat="0" lon="0"><tag k="local_x" v="0"/><tag k="local_y" v="0"/></node>
      <node id="4" lat="0" lon="0"><tag k="local_x" v="100"/><tag k="local_y" v="0"/></node>
      <node id="5" lat="0" lon="0"><tag k="local_x" v="200"/><tag k="local_y" v="6"/></node>
      <node id="6" lat="0" lon="0"><tag k="local_x" v="100"/><tag k="local_y" v="6"/></node>
      <node id="7" lat="0" lon="0"><tag k="local_x" v="200"/><tag k="local_y" v="10"/></node>
      <node id="8" lat="0" lon="0"><tag k="local_x" v="100"/><tag k="local_y" v="10"/></node>
      <way id="10"><nd ref="1"/><nd ref="2"/></way>
      <way id="11"><nd ref="3"/><nd ref="4"/></way>
      <way id="12"><nd ref="5"/><nd ref="6"/></way>
      <way id="13"><nd ref="7"/><nd ref="8"/></way>
      <relation id="1">
        <member type="way" role="left" ref="10"/><member type="way" role="right" ref="11"/>
        <tag k="type" v="lanelet"/><tag k="subtype" v="road"/>
      </relation>
      <relation id="2">
        <member type="way" role="right" ref="13"/><member type="way" role="left" ref="12"/>
        <tag k="type" v="lanelet"/><tag k="subtype" v="road"/>
      </relation>
      <relation id="3"><tag k="type" v="regulatory_element"/></relation>
    </osm>
    """)

# One well-formed lanelet (id 1, reused from FIXTURE) plus one (id 99) whose left
# way references node 9, which lacks local_x/local_y -- so way 30 ends up with only
# one usable point and never enters `ways`, dropping relation 99 entirely.
MALFORMED_FIXTURE = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <osm generator="test">
      <node id="1" lat="0" lon="0"><tag k="local_x" v="0"/><tag k="local_y" v="4"/></node>
      <node id="2" lat="0" lon="0"><tag k="local_x" v="100"/><tag k="local_y" v="4"/></node>
      <node id="3" lat="0" lon="0"><tag k="local_x" v="0"/><tag k="local_y" v="0"/></node>
      <node id="4" lat="0" lon="0"><tag k="local_x" v="100"/><tag k="local_y" v="0"/></node>
      <node id="9" lat="0" lon="0"/>
      <node id="10" lat="0" lon="0"><tag k="local_x" v="100"/><tag k="local_y" v="4"/></node>
      <way id="10"><nd ref="1"/><nd ref="2"/></way>
      <way id="11"><nd ref="3"/><nd ref="4"/></way>
      <way id="30"><nd ref="9"/><nd ref="10"/></way>
      <way id="31"><nd ref="3"/><nd ref="4"/></way>
      <relation id="1">
        <member type="way" role="left" ref="10"/><member type="way" role="right" ref="11"/>
        <tag k="type" v="lanelet"/><tag k="subtype" v="road"/>
      </relation>
      <relation id="99">
        <member type="way" role="left" ref="30"/><member type="way" role="right" ref="31"/>
        <tag k="type" v="lanelet"/><tag k="subtype" v="road"/>
      </relation>
    </osm>
    """)


@pytest.fixture
def lanelets(tmp_path):
    p = tmp_path / "map.osm"
    p.write_text(FIXTURE)
    return lp.load_lanelets(str(p))


def test_loads_only_lanelet_relations_with_both_bounds(lanelets):
    assert set(lanelets) == {1, 2}
    assert lanelets[1].left == [(0.0, 4.0), (100.0, 4.0)]
    assert lanelets[1].right == [(0.0, 0.0), (100.0, 0.0)]


def test_centerline_is_the_midline_and_pose_at_follows_travel_direction(lanelets):
    c = lp.centerline(lanelets[1], n=5)
    assert c[0] == pytest.approx((0.0, 2.0)) and c[-1] == pytest.approx((100.0, 2.0))
    x, y, yaw = lp.pose_at(c, 23.3)
    assert (x, y, yaw) == pytest.approx((23.3, 2.0, 0.0), abs=1e-6)
    x, y, yaw = lp.pose_at(lp.centerline(lanelets[2], n=5), 50.0)
    assert (x, y) == pytest.approx((150.0, 8.0), abs=1e-6)
    assert abs(abs(yaw) - 180.0) < 1e-6


def test_pose_at_clamps_to_the_lanelet(lanelets):
    c = lp.centerline(lanelets[1], n=5)
    assert lp.pose_at(c, 1e9)[0] == pytest.approx(100.0)
    assert lp.pose_at(c, -5.0)[0] == pytest.approx(0.0)


def test_pose_at_yaw_skips_a_leading_degenerate_segment():
    center = [(0.0, 0.0), (0.0, 0.0), (50.0, 50.0)]
    x, y, yaw = lp.pose_at(center, 0.0)
    assert (x, y) == pytest.approx((0.0, 0.0))
    assert yaw == pytest.approx(45.0, abs=1e-6)


def test_pose_at_yaw_still_correct_with_a_trailing_degenerate_segment():
    center = [(0.0, 0.0), (50.0, 50.0), (50.0, 50.0)]
    x, y, yaw = lp.pose_at(center, 1e9)
    assert (x, y) == pytest.approx((50.0, 50.0))
    assert yaw == pytest.approx(45.0, abs=1e-6)


def test_project_and_nearest(lanelets):
    s, d = lp.project(lp.centerline(lanelets[1]), 40.0, 2.5)
    assert (s, d) == pytest.approx((40.0, 0.5), abs=1e-6)
    lid, s, d = lp.nearest_lanelet(lanelets, 150.0, 9.0)
    assert lid == 2 and s == pytest.approx(50.0, abs=1e-6) and d == pytest.approx(1.0, abs=1e-6)


def test_map_to_carla_inverts_carla_to_map():
    cx, cy, cyaw = -84.114, 117.603, -10.43
    mx, my, _ = carla_to_map(cx, cy, 0.0, NISHISHINJUKU_ORIGIN)
    assert lp.map_to_carla(mx, my, -cyaw, NISHISHINJUKU_ORIGIN) == pytest.approx(
        (cx, cy, cyaw), abs=1e-9
    )
    assert lp.map_to_carla(81571.616, 50019.827, 10.43, NISHISHINJUKU_ORIGIN) == pytest.approx(
        (-84.114, 117.603, -10.43), abs=1e-6
    )


def test_load_lanelets_warns_on_stderr_and_drops_malformed_lanelets(tmp_path, capsys):
    p = tmp_path / "map.osm"
    p.write_text(MALFORMED_FIXTURE)
    lanelets = lp.load_lanelets(str(p))
    assert set(lanelets) == {1}
    err = capsys.readouterr().err
    assert "dropped 1 malformed" in err
    assert "99" in err


def test_cli_prints_goal_and_spawn_strings(tmp_path, capsys):
    p = tmp_path / "map.osm"
    p.write_text(FIXTURE)
    rc = lp.main(["--osm", str(p), "--map-origin", "10,20,0", "--lanelet", "1", "--s", "23.3"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "map: 23.300 2.000 0.000" in out
    assert '--goal "13.300,18.000,-0.000"' in out or '--goal "13.300,18.000,0.000"' in out
    assert '--spawn-pose "13.300,18.000,<GROUND_Z>,' in out
