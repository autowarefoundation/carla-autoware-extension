"""Pick a Town10HD_Opt start + goal whose SHORTEST road path is >= 400 m.

Chooses the G2 closed-loop route for a town map, from MAP GEOMETRY ALONE --
never from a driven trajectory -- which is what keeps the strict 1.0 m goal
gate honest. The route it printed is the one recorded in docs/running-e2e.md
("The chosen Town10 start and route"), so this is the reproduction path for
that choice, tracked for the same reason seed_sweep.py is.

Four properties are enforced, each closing a way a route could flatter the
gate: the SHORTEST road path is scored (Autoware plans its own route, so a
merely-long walked path would not bound what it drives); >= 60 deg of
accumulated heading change, so the drive is not a straight line; >= 100 m
straight-line separation, so the ego cannot start near the goal; and the route
must never pass within 10 m of the goal before arriving, since a near pass
would let the 1.0 m gate close without completing the route -- a false PASS.

Offline: reads the committed .xodr through carla.Map, so no simulator and no
running CARLA server are needed, only the CARLA Python egg on PYTHONPATH.

    CARLA_ROOT=~/src/carla-autoware-integration python3 scripts/e2e/pick_route.py

Prints the chosen start and goal in CARLA coordinates and in the Autoware map
frame; the map-frame goal is what arm_closed_loop.sh's GOAL_* (and
map_defaults.sh's MAP_DEFAULT_GOAL) carry.
"""

import heapq
import math
import os

import carla

MAP_NAME = "Town10HD_Opt"
# $CARLA_ROOT is the CARLA source tree run_e2e.sh already requires; $XODR
# overrides the whole path for a tree laid out differently.
CARLA_ROOT = os.environ.get("CARLA_ROOT", os.path.expanduser("~/src/carla-autoware-integration"))
XODR = os.environ.get(
    "XODR",
    f"{CARLA_ROOT}/Unreal/CarlaUnreal/Content/Carla/Maps/OpenDrive/{MAP_NAME}.xodr",
)
STEP = 2.0

m = carla.Map(MAP_NAME, open(XODR).read())


def key(wp):
    return (wp.road_id, wp.section_id, wp.lane_id, round(wp.s / STEP))


nodes = {}
adj = {}
frontier = list(m.generate_waypoints(STEP))
for wp in frontier:
    nodes.setdefault(key(wp), wp)

# Expand with next() so junction connectors (absent from generate_waypoints on
# some builds) join the graph too.
queue = list(nodes.values())
while queue:
    wp = queue.pop()
    k = key(wp)
    if k in adj:
        continue
    adj[k] = []
    for nxt in wp.next(STEP):
        nk = key(nxt)
        if nk not in nodes:
            nodes[nk] = nxt
            queue.append(nxt)
        adj[k].append(nk)
print("graph nodes", len(nodes), "edges", sum(len(v) for v in adj.values()))


def yaw_of(wp):
    return wp.transform.rotation.yaw


def dijkstra(src):
    dist = {src: 0.0}
    prev = {}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        for v in adj.get(u, []):
            nd = d + STEP
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def chain_of(prev, dst):
    chain = [dst]
    while chain[-1] in prev:
        chain.append(prev[chain[-1]])
    chain.reverse()
    return chain


def path_stats(prev, dst):
    """(total |heading change| deg, closest the path prefix comes to the goal)."""
    chain = chain_of(prev, dst)
    total = 0.0
    for a, b in zip(chain, chain[1:]):
        d = (yaw_of(nodes[b]) - yaw_of(nodes[a]) + 180.0) % 360.0 - 180.0
        total += abs(d)
    gl = nodes[dst].transform.location
    # Skip the last 15 nodes (30 m) -- the genuine arrival.
    prefix = chain[:-15] if len(chain) > 15 else []
    approach = min(
        (
            math.dist((nodes[k].transform.location.x, nodes[k].transform.location.y), (gl.x, gl.y))
            for k in prefix
        ),
        default=1e9,
    )
    return total, approach


# Keep the (start, goal) whose SHORTEST road path is >= 400 m, has a real curve,
# is far enough in straight line that the ego cannot start near the goal, and
# whose route never passes close to the goal before arriving (a near pass would
# let the 1.0 m gate close without completing the route -- a false PASS).
best = None
starts = list(nodes.items())[:: max(1, len(nodes) // 60)]
for sk, swp in starts:
    if swp.is_junction:
        continue
    dist, prev = dijkstra(sk)
    sl = swp.transform.location
    for gk, d in dist.items():
        if not (400.0 <= d <= 460.0):
            continue
        gwp = nodes[gk]
        if gwp.is_junction:
            continue
        gl = gwp.transform.location
        straight = math.dist((sl.x, sl.y), (gl.x, gl.y))
        if straight < 100.0:
            continue
        turn, approach = path_stats(prev, gk)
        if turn < 60.0 or approach < 10.0:
            continue
        score = (approach, straight)
        if best is None or score > best[0]:
            best = (score, d, turn, sk, gk, straight, approach)

score, d, turn, sk, gk, straight, approach = best
print(f"straight-line {straight:.1f} m, closest prior approach to goal {approach:.1f} m")
swp, gwp = nodes[sk], nodes[gk]
st, gt = swp.transform, gwp.transform
print(f"\nshortest road path = {d:.1f} m, total heading change {turn:.1f} deg")
print(
    f"START carla  x={st.location.x:.3f} y={st.location.y:.3f} z={st.location.z:.3f} "
    f"yaw={st.rotation.yaw:.3f}  road={swp.road_id} lane={swp.lane_id}"
)
print(
    f"GOAL  carla  x={gt.location.x:.3f} y={gt.location.y:.3f} z={gt.location.z:.3f} "
    f"yaw={gt.rotation.yaw:.3f}  road={gwp.road_id} lane={gwp.lane_id}"
)

# Town10 offset is zero, so map frame = (x, -y); yaw_map = -yaw_carla.
for label, tf in (("START", st), ("GOAL", gt)):
    mx, my = tf.location.x, -tf.location.y
    yaw = math.radians(-tf.rotation.yaw)
    print(
        f"{label} map   x={mx:.3f} y={my:.3f} z={tf.location.z:.3f} "
        f"qz={math.sin(yaw / 2):.6f} qw={math.cos(yaw / 2):.6f}"
    )
