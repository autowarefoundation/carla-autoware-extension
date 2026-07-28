#!/usr/bin/env python3
"""Derive a closed-loop route from map geometry alone, as a committed YAML file.

Chooses a G2 closed-loop route for a town map, from MAP GEOMETRY ALONE --
never from a driven trajectory -- which is what keeps the strict 1.0 m goal
gate honest. This is the committed adaptation of the tool that produced the
route recorded in docs/running-e2e.md ("The chosen Town10 start and route");
running it again is the reproduction path for that class of choice, tracked
for the same reason seed_sweep.py is.

Four properties are enforced on the candidate goal, each closing a way a route
could flatter the gate: the SHORTEST road path is scored (Autoware plans its
own route, so a merely-long walked path would not bound what it drives); a
minimum accumulated heading change, so the drive is not a straight line; a
minimum straight-line separation, so the ego cannot start near the goal; and
the route must never pass within a minimum distance of the goal before
arriving, since a near pass would let the 1.0 m gate close without completing
the route -- a false PASS. See MIN_TURN_DEG / MIN_STRAIGHT_M / MIN_APPROACH_M
below.

Offline: reads the given .xodr through carla.Map, so no simulator and no
running CARLA server are needed, only the CARLA Python egg on PYTHONPATH.
``carla`` is imported lazily (inside build_graph()), so the pure geometry/
scoring core below stays importable -- and unit-testable -- under bare pytest
with no CARLA egg, which is how CI runs it (see
tests/benchmarks/test_pick_route.py; the convention matches
scripts/e2e/collect_gt.py's lazy carla import).

CLI (the map name is taken from the .xodr's own filename stem, e.g.
Town10HD_Opt.xodr -> map: Town10HD_Opt); search for a goal:

    python3 benchmarks/scripts/pick_route.py --xodr <path/to/Map.xodr> \\
        --spawn-index <N> --min-length <metres>

--spawn-index indexes a deterministic, sorted list of non-junction waypoints
sampled from the .xodr every STEP_M metres -- a stand-in for CARLA's live
recommended spawn-point list, which bare .xodr data does not carry (that list
is level/world data, populated only for a Map obtained from a running server).
Print the route once with a chosen index, then treat the printed spawn_pose as
authoritative (the emitted YAML says so too); do not assume this tool's
--spawn-index N lines up with the live world's SPAWN_INDEX=N.

--spawn-pose is the alternative to --spawn-index (mutually exclusive): a
CARLA-frame pose "X Y Z YAW_DEG" -- e.g. a pose already recorded elsewhere,
such as a prior gate's Task-15 start -- snapped to the nearest graph node.
The snap distance is always printed (stderr) so a pose far from any known
road is visible, not silently absorbed.

--goal X Y (map frame) reproduces a SPECIFIC, already-known route instead of
searching for one: the four gate-honesty properties are then VERIFIED on the
start->goal route instead of used as search criteria, and the tool aborts
naming whichever property fails. There is no override flag -- a route that
fails a property can let the 1.0 m G2 goal gate close on a false PASS, which
is why the properties exist.

    python3 benchmarks/scripts/pick_route.py --xodr <path/to/Map.xodr> \\
        --spawn-pose <x> <y> <z> <yaw_deg> --goal <x> <y> --min-length <metres>

Prints the route YAML (schema: docs/running-e2e.md; consumed by
scripts/e2e/arm_closed_loop.sh's ROUTE_FILE and by
benchmarks/analysis/window.py) to stdout.
"""

from __future__ import annotations

import argparse
import heapq
import math
import sys
from pathlib import Path
from typing import Any, Hashable

import yaml

Key = Hashable
XY = tuple[float, float]

STEP_M = 2.0  # waypoint sampling step along the road network
MIN_TURN_DEG = 60.0  # minimum accumulated |heading change| along the route
MIN_STRAIGHT_M = 100.0  # minimum straight-line start<->goal separation
MIN_APPROACH_M = 10.0  # minimum distance from the goal before the final approach
APPROACH_SKIP_NODES = 15  # skip the last 15 nodes (30 m) -- the genuine arrival
POLYLINE_MAX_SPACING_M = 5.0  # emitted polyline point spacing, map frame
STATION_MARGIN_M = 20.0  # start_m/end_m margin from spawn/goal (Task 7 convention)

# ---------------------------------------------------------------------------
# Pure geometry / graph / scoring core. No `carla` import is reachable from
# here (build_graph() imports it lazily), so every function below is
# unit-testable with a synthetic polyline / graph -- no CARLA object needed.
# ---------------------------------------------------------------------------


def cumulative_arc_length(points: list[XY]) -> list[float]:
    """Arc-length (m) at each point of a polyline; result[0] == 0.0."""
    out = [0.0]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        out.append(out[-1] + math.dist((x0, y0), (x1, y1)))
    return out


def resample_polyline(points: list[XY], max_spacing_m: float = POLYLINE_MAX_SPACING_M) -> list[XY]:
    """Resample a polyline so consecutive points are <= max_spacing_m apart.

    Every original vertex is kept (never dropped, so corners are not smoothed
    away); extra points are inserted by linear interpolation on segments that
    exceed max_spacing_m.
    """
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        seg_len = math.dist((x0, y0), (x1, y1))
        n = max(1, math.ceil(seg_len / max_spacing_m))
        for i in range(1, n + 1):
            t = i / n
            out.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
    return out


def route_stations(polyline: list[XY], margin_m: float = STATION_MARGIN_M) -> tuple[float, float]:
    """(start_m, end_m): margin_m after spawn, margin_m before goal.

    Raises ValueError rather than emitting a negative or inverted window --
    silently swapping start_m/end_m is exactly the "silent wrong number"
    class of defect this tool exists to avoid.
    """
    total = cumulative_arc_length(polyline)[-1]
    start_m, end_m = margin_m, total - margin_m
    if end_m <= start_m:
        raise ValueError(f"route too short ({total:.1f} m) for a {margin_m:.1f} m margin on each end")
    return start_m, end_m


def carla_to_map_xy(x: float, y: float) -> XY:
    """CARLA (x, y) -> Autoware map-frame (x, y).

    Preserved from the original script: the registered offset for the maps
    this tool has been run against is zero, so the map frame is a single Y
    flip. A map with a nonzero registered offset needs the pinned affine in
    scripts/e2e/verify_mgrs_handedness.py (offset_for_map()) instead of this
    shortcut -- this tool does not attempt to cover that case.
    """
    return x, -y


def carla_to_map_yaw(yaw_deg: float) -> float:
    """CARLA yaw (deg) -> Autoware map-frame yaw (rad). Same Y-flip source as
    carla_to_map_xy: yaw_map = -yaw_carla."""
    return math.radians(-yaw_deg)


def dijkstra(adj: dict[Key, list[Key]], src: Key, step_m: float = STEP_M) -> tuple[dict[Key, float], dict[Key, Key]]:
    """Shortest-path distances/predecessors from src over a graph whose edges
    all cost step_m (the uniform waypoint-sampling step)."""
    dist: dict[Key, float] = {src: 0.0}
    prev: dict[Key, Key] = {}
    pq: list[tuple[float, Key]] = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, math.inf):
            continue
        for v in adj.get(u, []):
            nd = d + step_m
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def chain_of(prev: dict[Key, Key], dst: Key) -> list[Key]:
    """Reconstruct the src->dst node chain from a dijkstra() predecessor map."""
    chain = [dst]
    while chain[-1] in prev:
        chain.append(prev[chain[-1]])
    chain.reverse()
    return chain


def path_stats(
    positions: dict[Key, tuple[float, float, float]],  # key -> (x, y, yaw_deg)
    prev: dict[Key, Key],
    dst: Key,
    approach_skip_nodes: int = APPROACH_SKIP_NODES,
) -> tuple[float, float]:
    """(total |heading change| deg, closest the path prefix comes to the goal).

    The SHORTEST road path is scored (Autoware plans its own route, so a
    merely-long walked path would not bound what it drives), and "prior
    approach" excludes the last approach_skip_nodes*STEP_M metres -- the
    genuine arrival -- so a route that loops near the goal before actually
    reaching it is caught (that near pass would let the 1.0 m gate close
    without completing the route).
    """
    chain = chain_of(prev, dst)
    total = 0.0
    for a, b in zip(chain, chain[1:]):
        ya, yb = positions[a][2], positions[b][2]
        d = (yb - ya + 180.0) % 360.0 - 180.0
        total += abs(d)
    gx, gy, _ = positions[dst]
    prefix = chain[:-approach_skip_nodes] if len(chain) > approach_skip_nodes else []
    approach = min(
        (math.dist(positions[k][:2], (gx, gy)) for k in prefix),
        default=math.inf,
    )
    return total, approach


def select_goal(
    positions: dict[Key, tuple[float, float, float]],
    adj: dict[Key, list[Key]],
    junctions: set[Key],
    start: Key,
    min_length_m: float,
    step_m: float = STEP_M,
    min_turn_deg: float = MIN_TURN_DEG,
    min_straight_m: float = MIN_STRAIGHT_M,
    min_approach_m: float = MIN_APPROACH_M,
    approach_skip_nodes: int = APPROACH_SKIP_NODES,
) -> tuple[Key, dict[Key, Key]] | None:
    """Pick the goal reachable from start whose shortest road path clears all
    four gate-honesty properties (see module docstring), preferring the
    candidate that stays farthest from the goal until it actually arrives
    (largest closest-approach), tie-broken by the largest straight-line
    start<->goal separation.

    Returns (goal_key, prev) so the caller can reconstruct the winning chain
    via chain_of(prev, goal_key), or None if start has no reachable goal
    clearing every gate.
    """
    dist, prev = dijkstra(adj, start, step_m)
    sx, sy, _ = positions[start]
    best_score: tuple[float, float] | None = None
    best_goal: Key | None = None
    for k, d in dist.items():
        if k == start or k in junctions or d < min_length_m:
            continue
        gx, gy, _ = positions[k]
        straight = math.dist((sx, sy), (gx, gy))
        if straight < min_straight_m:
            continue
        turn, approach = path_stats(positions, prev, k, approach_skip_nodes)
        if turn < min_turn_deg or approach < min_approach_m:
            continue
        score = (approach, straight)
        if best_score is None or score > best_score:
            best_score, best_goal = score, k
    if best_goal is None:
        return None
    return best_goal, prev


def nearest_node(positions: dict[Key, tuple[float, float, float]], x: float, y: float) -> tuple[Key, float]:
    """(key, distance) of the graph node nearest to (x, y).

    Backs --spawn-pose/--goal: a hand-recorded pose (e.g. the Task-15 poses
    docs/running-e2e.md pins) is almost never exactly on a sampled waypoint,
    so it is snapped to the nearest one. The distance is returned, not just
    the key, so the caller can report it -- a large snap distance means the
    given pose is far from any road the graph knows about, and that must be
    visible, not silently absorbed into "close enough".
    """
    best_key: Key | None = None
    best_d = math.inf
    for k, (px, py, _yaw) in positions.items():
        d = math.dist((px, py), (x, y))
        if d < best_d:
            best_d, best_key = d, k
    if best_key is None:
        raise ValueError("no graph nodes to snap to (empty positions)")
    return best_key, best_d


def verify_route(
    positions: dict[Key, tuple[float, float, float]],
    dist: dict[Key, float],
    prev: dict[Key, Key],
    start: Key,
    goal: Key,
    min_length_m: float,
    min_turn_deg: float = MIN_TURN_DEG,
    min_straight_m: float = MIN_STRAIGHT_M,
    min_approach_m: float = MIN_APPROACH_M,
    approach_skip_nodes: int = APPROACH_SKIP_NODES,
) -> list[str]:
    """Check the four gate-honesty properties on a SPECIFIC start->goal route
    (an explicit --goal) instead of searching for a goal that clears them.

    Returns the list of property-failure messages (empty == the route clears
    every gate). This is deliberately a check, not a filter with an override:
    a route that fails one of these properties can let the 1.0 m G2 goal
    gate close on a false PASS (a near pass, a straight line, too short a
    path, or a start too close to the goal), which is the whole reason the
    four properties exist -- so there is no flag to bypass this.
    """
    failures: list[str] = []
    d = dist.get(goal)
    if d is None:
        return ["goal is not reachable from start"]
    if d < min_length_m:
        failures.append(f"shortest road path {d:.1f} m < --min-length {min_length_m:.1f} m")
    sx, sy, _ = positions[start]
    gx, gy, _ = positions[goal]
    straight = math.dist((sx, sy), (gx, gy))
    if straight < min_straight_m:
        failures.append(f"straight-line separation {straight:.1f} m < {min_straight_m:.1f} m")
    turn, approach = path_stats(positions, prev, goal, approach_skip_nodes)
    if turn < min_turn_deg:
        failures.append(f"accumulated heading change {turn:.1f} deg < {min_turn_deg:.1f} deg")
    if approach < min_approach_m:
        failures.append(
            f"route passes within {approach:.1f} m of the goal before arriving "
            f"(< {min_approach_m:.1f} m -- a near pass could let the 1.0 m gate "
            "close without completing the route)"
        )
    return failures


# ---------------------------------------------------------------------------
# CARLA-dependent layer: builds the plain graph the pure core above consumes.
# ---------------------------------------------------------------------------


def build_graph(xodr_path: str, map_name: str, step_m: float = STEP_M):
    """Return (positions, adj, junctions, spawn_candidates, waypoints) from an
    .xodr's road network.

    ``carla`` is imported here, not at module scope, so the pure core above
    stays importable -- and unit-testable -- under bare pytest with no CARLA
    egg (matches scripts/e2e/collect_gt.py's lazy-import convention, which is
    how this repo's CI runs Python tests).
    """
    import carla

    m = carla.Map(map_name, open(xodr_path).read())

    def key(wp) -> Key:
        return (wp.road_id, wp.section_id, wp.lane_id, round(wp.s / step_m))

    nodes: dict[Key, Any] = {}
    for wp in m.generate_waypoints(step_m):
        nodes.setdefault(key(wp), wp)

    # Expand with next() so junction connectors (absent from
    # generate_waypoints on some builds) join the graph too.
    queue = list(nodes.values())
    adj: dict[Key, list[Key]] = {}
    while queue:
        wp = queue.pop()
        k = key(wp)
        if k in adj:
            continue
        adj[k] = []
        for nxt in wp.next(step_m):
            nk = key(nxt)
            if nk not in nodes:
                nodes[nk] = nxt
                queue.append(nxt)
            adj[k].append(nk)

    positions = {
        k: (wp.transform.location.x, wp.transform.location.y, wp.transform.rotation.yaw)
        for k, wp in nodes.items()
    }
    junctions = {k for k, wp in nodes.items() if wp.is_junction}

    # Candidate "spawn points": non-junction nodes, sorted by key for a
    # deterministic, reproducible index -- see the module docstring for why
    # this is not the live world's recommended-spawn-point list.
    spawn_candidates = sorted(k for k in nodes if k not in junctions)
    return positions, adj, junctions, spawn_candidates, nodes


def build_arg_parser() -> argparse.ArgumentParser:
    """Split out from main() so the CLI surface (flags, mutual exclusivity)
    is unit-testable without carla/build_graph() (tests/benchmarks/test_pick_route.py)."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xodr", required=True, help="path to the map's .xodr file")
    start_group = ap.add_mutually_exclusive_group(required=True)
    start_group.add_argument(
        "--spawn-index",
        type=int,
        default=None,
        help="index into the deterministic candidate-start list built from --xodr "
        "(see build_graph() / module docstring -- not the live world's spawn-point list)",
    )
    start_group.add_argument(
        "--spawn-pose",
        nargs=4,
        type=float,
        default=None,
        metavar=("X", "Y", "Z", "YAW_DEG"),
        help="CARLA-frame start pose, snapped to the nearest graph node "
        "(mutually exclusive with --spawn-index)",
    )
    ap.add_argument(
        "--goal",
        nargs=2,
        type=float,
        default=None,
        metavar=("X", "Y"),
        help="map-frame goal; when given, the start->goal route is VERIFIED against "
        "the four gate-honesty properties instead of searched for -- no override flag "
        "(see module docstring)",
    )
    ap.add_argument(
        "--min-length",
        type=float,
        required=True,
        help="minimum shortest-road-path length (m) from spawn to goal",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    map_name = Path(args.xodr).stem
    positions, adj, junctions, spawn_candidates, waypoints = build_graph(args.xodr, map_name)

    reported_spawn_index: int | None = None
    reported_spawn_pose: tuple[float, float, float, float] | None = None
    if args.spawn_index is not None:
        if not spawn_candidates or not (0 <= args.spawn_index < len(spawn_candidates)):
            print(
                f"--spawn-index {args.spawn_index} out of range "
                f"[0, {len(spawn_candidates)}) for {len(spawn_candidates)} candidates",
                file=sys.stderr,
            )
            return 2
        start = spawn_candidates[args.spawn_index]
        reported_spawn_index = args.spawn_index
    else:
        sx, sy, sz, syaw = args.spawn_pose
        start, snap_d = nearest_node(positions, sx, sy)
        px, py, _ = positions[start]
        print(
            f"OK: --spawn-pose ({sx:.3f}, {sy:.3f}) snapped to graph node "
            f"({px:.3f}, {py:.3f}), {snap_d:.3f} m away",
            file=sys.stderr,
        )
        reported_spawn_pose = (sx, sy, sz, syaw)

    reported_goal_xy: tuple[float, float] | None = None
    if args.goal is not None:
        gx_map, gy_map = args.goal
        # carla_to_map_xy is a pure Y flip, so it is its own inverse.
        gx_carla, gy_carla = carla_to_map_xy(gx_map, gy_map)
        goal, goal_snap_d = nearest_node(positions, gx_carla, gy_carla)
        print(
            f"OK: --goal map-frame ({gx_map:.3f}, {gy_map:.3f}) snapped to a "
            f"graph node {goal_snap_d:.3f} m away",
            file=sys.stderr,
        )
        dist, prev = dijkstra(adj, start, STEP_M)
        failures = verify_route(positions, dist, prev, start, goal, args.min_length)
        if failures:
            print("PICK_ROUTE FAIL: --goal route fails gate-honesty checks:", file=sys.stderr)
            for msg in failures:
                print(f"  - {msg}", file=sys.stderr)
            return 1
        reported_goal_xy = (gx_map, gy_map)
    else:
        picked = select_goal(positions, adj, junctions, start, args.min_length)
        if picked is None:
            print(
                f"no goal reachable from spawn clears the four gate-honesty "
                f"properties (min length {args.min_length} m); try a different "
                "--spawn-index/--spawn-pose or a smaller --min-length",
                file=sys.stderr,
            )
            return 1
        goal, prev = picked

    chain = chain_of(prev, goal)

    swp, gwp = waypoints[start], waypoints[goal]
    st, gt = swp.transform, gwp.transform

    carla_polyline = [(waypoints[k].transform.location.x, waypoints[k].transform.location.y) for k in chain]
    map_polyline_raw = [carla_to_map_xy(x, y) for x, y in carla_polyline]
    polyline = resample_polyline(map_polyline_raw)
    start_m, end_m = route_stations(polyline)

    # spawn_pose/goal echo the operator-given values VERBATIM when given (an
    # already-trusted, externally-recorded pose, e.g. a prior gate's poses --
    # see --spawn-pose/--goal in the module docstring), not the graph-snapped
    # node's own transform; the snap is only used internally to find a real
    # path. Falls back to the graph node's own transform in search mode
    # (--spawn-index / no --goal), matching the tool's original behaviour.
    if reported_spawn_pose is not None:
        spawn_x, spawn_y, spawn_z, spawn_yaw_deg = reported_spawn_pose
    else:
        spawn_x, spawn_y, spawn_z, spawn_yaw_deg = (
            st.location.x, st.location.y, st.location.z, st.rotation.yaw,
        )
    gyaw = carla_to_map_yaw(gt.rotation.yaw)
    if reported_goal_xy is not None:
        goal_x, goal_y = reported_goal_xy
    else:
        goal_x, goal_y = carla_to_map_xy(gt.location.x, gt.location.y)

    doc = {
        "map": map_name,
        "spawn_index": reported_spawn_index,
        "spawn_pose": {
            "x": round(spawn_x, 3),
            "y": round(spawn_y, 3),
            "z": round(spawn_z, 3),
            "yaw_deg": round(spawn_yaw_deg, 3),
        },
        "goal": {"x": round(goal_x, 3), "y": round(goal_y, 3), "yaw_rad": round(gyaw, 6)},
        "stations": {"start_m": round(start_m, 1), "end_m": round(end_m, 1)},
        "polyline": [[round(x, 3), round(y, 3)] for x, y in polyline],
    }
    yaml.safe_dump(doc, sys.stdout, sort_keys=False, default_flow_style=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
