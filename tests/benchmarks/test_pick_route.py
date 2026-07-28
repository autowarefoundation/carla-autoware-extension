"""Unit tests for the pure geometry/scoring core of pick_route.py.

``benchmarks.scripts.pick_route`` imports ``carla`` lazily inside
``build_graph()`` only (matching ``scripts.e2e.collect_gt``'s convention), so
every function tested here collects and runs under bare pytest with no CARLA
egg, which is how CI runs it -- no CARLA object is needed anywhere below.

The four route-scoring properties (shortest-path length, accumulated heading
change, straight-line separation, no early approach to the goal) are each
pinned by its own reject case, plus one accept case and one tie-break case,
so a future edit that silently drops or weakens one of them fails a test
instead of only showing up as a route that lets the 1.0 m G2 gate close
early. verify_route() re-checks the same four properties on a --goal-given
route (VERIFY instead of SEARCH) and is covered the same way, one reject
case per property, so each aborts naming the property that failed.
"""

from __future__ import annotations

import math

import pytest

from benchmarks.scripts.pick_route import (
    build_arg_parser,
    carla_to_map_xy,
    carla_to_map_yaw,
    chain_of,
    cumulative_arc_length,
    dijkstra,
    nearest_node,
    resample_polyline,
    route_stations,
    select_goal,
    verify_route,
)

# ---------------------------------------------------------------------------
# Polyline arc-length / resampling / stations
# ---------------------------------------------------------------------------

# Synthetic 3-point polyline: a 3-4-5 triangle leg (length 5), then a further
# 6 m straight up (total 11 m).
TRIANGLE_POLYLINE = [(0.0, 0.0), (3.0, 4.0), (3.0, 10.0)]


def test_cumulative_arc_length_synthetic_3_point_polyline():
    assert cumulative_arc_length(TRIANGLE_POLYLINE) == pytest.approx([0.0, 5.0, 11.0])


def test_resample_polyline_respects_max_spacing():
    out = resample_polyline(TRIANGLE_POLYLINE, max_spacing_m=5.0)
    for (x0, y0), (x1, y1) in zip(out, out[1:]):
        assert math.dist((x0, y0), (x1, y1)) <= 5.0 + 1e-9


def test_resample_polyline_keeps_every_original_vertex():
    out = resample_polyline(TRIANGLE_POLYLINE, max_spacing_m=5.0)
    for vertex in TRIANGLE_POLYLINE:
        assert any(math.isclose(vx, vertex[0]) and math.isclose(vy, vertex[1]) for vx, vy in out)


def test_route_stations_applies_margin_on_each_end():
    # 100 m straight polyline sampled every 10 m -> total length 100 m.
    polyline = [(float(i * 10), 0.0) for i in range(11)]
    start_m, end_m = route_stations(polyline, margin_m=20.0)
    assert (start_m, end_m) == pytest.approx((20.0, 80.0))


def test_route_stations_raises_when_route_too_short_for_the_margin():
    polyline = [(0.0, 0.0), (30.0, 0.0)]  # 30 m, less than 2 * 20 m margin
    with pytest.raises(ValueError, match="too short"):
        route_stations(polyline, margin_m=20.0)


# ---------------------------------------------------------------------------
# CARLA -> Autoware map-frame convention (Town10's zero-offset shortcut)
# ---------------------------------------------------------------------------


def test_carla_to_map_xy_is_a_single_y_flip():
    assert carla_to_map_xy(55.330, 141.161) == pytest.approx((55.330, -141.161))


def test_carla_to_map_yaw_negates_and_converts_to_radians():
    assert carla_to_map_yaw(90.0) == pytest.approx(-math.pi / 2)
    assert carla_to_map_yaw(0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# dijkstra / chain_of over a plain graph -- no carla object involved
# ---------------------------------------------------------------------------


def test_dijkstra_finds_shortest_path_over_a_synthetic_graph():
    # 0 -> 1 -> 2 direct (2 hops) and a longer 0 -> 3 -> 4 -> 2 detour (3 hops);
    # the direct route must win.
    adj = {0: [1, 3], 1: [2], 2: [], 3: [4], 4: [2]}
    dist, prev = dijkstra(adj, 0, step_m=10.0)
    assert dist[2] == pytest.approx(20.0)
    assert chain_of(prev, 2) == [0, 1, 2]


# ---------------------------------------------------------------------------
# select_goal: the four gate-honesty properties, an accept case, and the
# (approach, straight) tie-break.
# ---------------------------------------------------------------------------

# A 13-node elbow: straight out to x=20, then a 90 degree turn and straight up
# to y=100. STEP_M-equivalent edge weight is 10 for readable numbers.
_ELBOW_POSITIONS = {
    0: (0.0, 0.0, 0.0),
    1: (10.0, 0.0, 0.0),
    2: (20.0, 0.0, 0.0),
    3: (20.0, 10.0, 90.0),
    4: (20.0, 20.0, 90.0),
    5: (20.0, 30.0, 90.0),
    6: (20.0, 40.0, 90.0),
    7: (20.0, 50.0, 90.0),
    8: (20.0, 60.0, 90.0),
    9: (20.0, 70.0, 90.0),
    10: (20.0, 80.0, 90.0),
    11: (20.0, 90.0, 90.0),
    12: (20.0, 100.0, 90.0),  # only node clearing every gate below
}
_ELBOW_ADJ = {i: [i + 1] for i in range(12)} | {12: []}


def _select_elbow_goal(junctions=None, **overrides):
    kwargs = dict(
        min_length_m=100.0,
        step_m=10.0,
        min_turn_deg=60.0,
        min_straight_m=100.0,
        min_approach_m=10.0,
        approach_skip_nodes=3,
    )
    kwargs.update(overrides)
    return select_goal(_ELBOW_POSITIONS, _ELBOW_ADJ, junctions or set(), 0, **kwargs)


def test_select_goal_accepts_the_route_clearing_all_four_gates():
    picked = _select_elbow_goal()
    assert picked is not None
    goal, prev = picked
    assert goal == 12
    assert chain_of(prev, goal) == list(range(13))


def test_select_goal_rejects_a_straight_line_no_real_turn():
    """Same positions, but every yaw is identical (no heading change) --
    turn(0 deg) must fail the >= min_turn_deg gate even though length/
    straight/approach all still pass."""
    straight_positions = {k: (x, y, 0.0) for k, (x, y, _yaw) in _ELBOW_POSITIONS.items()}
    picked = select_goal(
        straight_positions, _ELBOW_ADJ, set(), 0,
        min_length_m=100.0, step_m=10.0, min_turn_deg=60.0,
        min_straight_m=100.0, min_approach_m=10.0, approach_skip_nodes=3,
    )
    assert picked is None


def test_select_goal_rejects_insufficient_straight_line_separation():
    picked = _select_elbow_goal(min_straight_m=1000.0)
    assert picked is None


def test_select_goal_rejects_when_no_candidate_clears_min_length():
    picked = _select_elbow_goal(min_length_m=1000.0)
    assert picked is None


def test_select_goal_rejects_a_route_that_passes_close_to_the_goal_early():
    """Node 2 sits 1.4 m from the goal (20, 100) -- well inside the last
    approach_skip_nodes*step exclusion zone by chain position, but included
    in the scored "prior approach" prefix -- so it must be rejected even
    though length/turn/straight are unaffected (turn reads only stored yaw,
    not this position change)."""
    near_positions = dict(_ELBOW_POSITIONS)
    near_positions[2] = (19.0, 99.0, 0.0)
    picked = select_goal(
        near_positions, _ELBOW_ADJ, set(), 0,
        min_length_m=100.0, step_m=10.0, min_turn_deg=60.0,
        min_straight_m=100.0, min_approach_m=10.0, approach_skip_nodes=3,
    )
    assert picked is None


def test_select_goal_never_returns_a_junction_as_the_goal():
    picked = _select_elbow_goal(junctions={12})
    assert picked is None


def test_select_goal_prefers_larger_closest_approach_over_larger_straight():
    """Two goals reachable from a shared start: 2a has a large closest
    prior approach (100 m) and 2b has a tiny one (5 m) despite both having
    ~the same straight-line separation. score = (approach, straight) must
    pick 2a -- approach dominates the tie-break, not just straight-line
    distance."""
    positions = {
        0: (0.0, 0.0, 0.0),
        "1a": (10.0, 0.0, 90.0),
        "2a": (10.0, 100.0, 90.0),
        "1b": (-10.0, 0.0, 90.0),
        "1b2": (-10.0, 95.0, 90.0),  # swings close to 2b before arriving
        "2b": (-10.0, 100.0, 90.0),
    }
    adj = {
        0: ["1a", "1b"],
        "1a": ["2a"],
        "2a": [],
        "1b": ["1b2"],
        "1b2": ["2b"],
        "2b": [],
    }
    picked = select_goal(
        positions, adj, set(), 0,
        min_length_m=15.0, step_m=10.0, min_turn_deg=60.0,
        min_straight_m=100.0, min_approach_m=1.0, approach_skip_nodes=1,
    )
    assert picked is not None
    goal, _prev = picked
    assert goal == "2a"


# ---------------------------------------------------------------------------
# nearest_node: snapping a hand-given pose to the graph (backs --spawn-pose
# and --goal).
# ---------------------------------------------------------------------------


def test_nearest_node_returns_the_closest_key_and_its_distance():
    positions = {"a": (0.0, 0.0, 0.0), "b": (10.0, 0.0, 0.0), "c": (10.0, 10.0, 0.0)}
    key, dist = nearest_node(positions, 9.0, 1.0)
    assert key == "b"
    assert dist == pytest.approx(math.dist((10.0, 0.0), (9.0, 1.0)))


def test_nearest_node_exact_match_has_zero_distance():
    positions = {"a": (0.0, 0.0, 0.0), "b": (10.0, 0.0, 0.0)}
    key, dist = nearest_node(positions, 10.0, 0.0)
    assert key == "b"
    assert dist == pytest.approx(0.0)


def test_nearest_node_raises_on_empty_positions():
    with pytest.raises(ValueError, match="empty positions"):
        nearest_node({}, 0.0, 0.0)


# ---------------------------------------------------------------------------
# verify_route: --goal's VERIFY-not-search path. Each of the four
# gate-honesty properties gets its own reject case naming that property, plus
# a pass case and an unreachable-goal case, mirroring select_goal's coverage
# above (verify_route checks the SAME properties on a specific route instead
# of searching for one).
# ---------------------------------------------------------------------------


def _elbow_dist_prev(**dijkstra_kwargs):
    return dijkstra(_ELBOW_ADJ, 0, **dijkstra_kwargs)


def test_verify_route_passes_a_route_clearing_all_four_gates():
    dist, prev = _elbow_dist_prev(step_m=10.0)
    failures = verify_route(
        _ELBOW_POSITIONS, dist, prev, 0, 12,
        min_length_m=100.0, min_turn_deg=60.0, min_straight_m=100.0,
        min_approach_m=10.0, approach_skip_nodes=3,
    )
    assert failures == []


def test_verify_route_names_the_length_property_on_failure():
    dist, prev = _elbow_dist_prev(step_m=10.0)
    failures = verify_route(
        _ELBOW_POSITIONS, dist, prev, 0, 12,
        min_length_m=200.0, min_turn_deg=60.0, min_straight_m=100.0,
        min_approach_m=10.0, approach_skip_nodes=3,
    )
    assert len(failures) == 1
    assert "shortest road path" in failures[0]
    assert "--min-length" in failures[0]


def test_verify_route_names_the_straight_line_property_on_failure():
    dist, prev = _elbow_dist_prev(step_m=10.0)
    failures = verify_route(
        _ELBOW_POSITIONS, dist, prev, 0, 12,
        min_length_m=100.0, min_turn_deg=60.0, min_straight_m=200.0,
        min_approach_m=10.0, approach_skip_nodes=3,
    )
    assert len(failures) == 1
    assert "straight-line separation" in failures[0]


def test_verify_route_names_the_heading_change_property_on_failure():
    dist, prev = _elbow_dist_prev(step_m=10.0)
    failures = verify_route(
        _ELBOW_POSITIONS, dist, prev, 0, 12,
        min_length_m=100.0, min_turn_deg=100.0, min_straight_m=100.0,
        min_approach_m=10.0, approach_skip_nodes=3,
    )
    assert len(failures) == 1
    assert "heading change" in failures[0]


def test_verify_route_names_the_early_approach_property_on_failure():
    dist, prev = _elbow_dist_prev(step_m=10.0)
    failures = verify_route(
        _ELBOW_POSITIONS, dist, prev, 0, 12,
        min_length_m=100.0, min_turn_deg=60.0, min_straight_m=100.0,
        min_approach_m=50.0, approach_skip_nodes=3,
    )
    assert len(failures) == 1
    assert "passes within" in failures[0]


def test_verify_route_reports_unreachable_goal():
    dist, prev = _elbow_dist_prev(step_m=10.0)
    failures = verify_route(
        _ELBOW_POSITIONS, dist, prev, 0, "not-in-the-graph",
        min_length_m=100.0,
    )
    assert failures == ["goal is not reachable from start"]


# ---------------------------------------------------------------------------
# CLI surface: --spawn-index/--spawn-pose mutual exclusivity.
# ---------------------------------------------------------------------------


def test_spawn_index_and_spawn_pose_are_mutually_exclusive():
    with pytest.raises(SystemExit) as exc_info:
        build_arg_parser().parse_args([
            "--xodr", "dummy.xodr",
            "--spawn-index", "5",
            "--spawn-pose", "1", "2", "3", "4",
            "--min-length", "100",
        ])
    assert exc_info.value.code == 2


def test_one_of_spawn_index_or_spawn_pose_is_required():
    with pytest.raises(SystemExit) as exc_info:
        build_arg_parser().parse_args(["--xodr", "dummy.xodr", "--min-length", "100"])
    assert exc_info.value.code == 2


def test_spawn_pose_alone_parses_with_four_floats():
    args = build_arg_parser().parse_args([
        "--xodr", "dummy.xodr",
        "--spawn-pose", "55.330", "141.161", "0.5", "0.320",
        "--goal", "-101.021", "55.014",
        "--min-length", "400",
    ])
    assert args.spawn_index is None
    assert args.spawn_pose == pytest.approx([55.330, 141.161, 0.5, 0.320])
    assert args.goal == pytest.approx([-101.021, 55.014])
