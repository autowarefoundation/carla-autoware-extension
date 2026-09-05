#!/usr/bin/env python3
"""Poses on lanelet2 centrelines, in the Autoware map frame and in CARLA coordinates.

Reads a lanelet2 .osm (nodes must carry local_x/local_y -- Autoware's convention,
present in Vector Map Builder and map_tools output), rebuilds each lanelet's
centreline as the midline of its left/right bounds, and converts poses to CARLA
with the inverse of map_frame.carla_to_map. Used to derive an on-lane
--spawn-pose and a lane-centred --goal for run_carla_autoware.sh on maps whose
spawn points are missing or off-lane (Nishi-Shinjuku). Z is not derived here:
the CARLA ground height must come from a live cast_ray (see docs/nishishinjuku-map.md).
"""

from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from collections import namedtuple

from scripts.e2e.map_frame import parse_origin

Lanelet = namedtuple("Lanelet", "id left right")


def load_lanelets(osm_path: str) -> dict[int, Lanelet]:
    root = ET.parse(osm_path).getroot()
    nodes: dict[str, tuple[float, float]] = {}
    for n in root.iter("node"):
        tags = {t.get("k"): t.get("v") for t in n.iter("tag")}
        if "local_x" in tags and "local_y" in tags:
            nodes[n.get("id")] = (float(tags["local_x"]), float(tags["local_y"]))
    ways: dict[str, list[tuple[float, float]]] = {}
    for w in root.iter("way"):
        pts = [nodes[nd.get("ref")] for nd in w.iter("nd") if nd.get("ref") in nodes]
        if len(pts) >= 2:
            ways[w.get("id")] = pts
    out: dict[int, Lanelet] = {}
    dropped: list[int] = []
    for r in root.iter("relation"):
        tags = {t.get("k"): t.get("v") for t in r.iter("tag")}
        if tags.get("type") != "lanelet":
            continue
        bounds = {
            m.get("role"): ways.get(m.get("ref"))
            for m in r.iter("member")
            if m.get("type") == "way"
        }
        lid = int(r.get("id"))
        if bounds.get("left") and bounds.get("right"):
            out[lid] = Lanelet(lid, bounds["left"], bounds["right"])
        else:
            dropped.append(lid)
    if dropped:
        shown = ", ".join(str(i) for i in dropped[:10])
        if len(dropped) > 10:
            shown += ", ..."
        sys.stderr.write(
            f"lanelet_pose: dropped {len(dropped)} malformed lanelet(s) missing usable "
            f"left/right bounds: {shown}\n"
        )
    return out


def _cumlen(pts):
    s = [0.0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        s.append(s[-1] + math.hypot(x1 - x0, y1 - y0))
    return s


def _at(pts, cum, s):
    s = min(max(s, 0.0), cum[-1])
    for i in range(1, len(cum)):
        if s <= cum[i]:
            seg = cum[i] - cum[i - 1]
            t = 0.0 if seg == 0.0 else (s - cum[i - 1]) / seg
            (x0, y0), (x1, y1) = pts[i - 1], pts[i]
            return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))
    return pts[-1]


def centerline(lanelet: Lanelet, n: int = 50) -> list[tuple[float, float]]:
    """Midline of the two bounds, sampled at n equal arclength fractions of each bound."""
    cl, cr = _cumlen(lanelet.left), _cumlen(lanelet.right)
    out = []
    for k in range(n):
        f = k / (n - 1)
        (lx, ly), (rx, ry) = _at(lanelet.left, cl, f * cl[-1]), _at(lanelet.right, cr, f * cr[-1])
        out.append(((lx + rx) / 2.0, (ly + ry) / 2.0))
    return out


def pose_at(center: list[tuple[float, float]], s_m: float) -> tuple[float, float, float]:
    """(x, y, yaw_deg) at arclength s along the centreline; s is clamped to [0, length].

    Yaw is taken from the segment the position falls in; if that segment is
    zero-length (degenerate), the search moves forward to the next segment of
    non-zero length. If every remaining segment is degenerate, yaw is 0.0.
    """
    cum = _cumlen(center)
    s = min(max(s_m, 0.0), cum[-1])
    x, y = _at(center, cum, s)
    i = max(
        1,
        min(len(cum) - 1, next(k for k in range(1, len(cum)) if s <= cum[k] or k == len(cum) - 1)),
    )
    j = i
    (x0, y0), (x1, y1) = center[j - 1], center[j]
    while x0 == x1 and y0 == y1 and j < len(cum) - 1:
        j += 1
        (x0, y0), (x1, y1) = center[j - 1], center[j]
    yaw = 0.0 if (x0 == x1 and y0 == y1) else math.degrees(math.atan2(y1 - y0, x1 - x0))
    return (x, y, yaw)


def project(center: list[tuple[float, float]], x: float, y: float) -> tuple[float, float]:
    """(s_m, dist_m) of the closest centreline point to (x, y)."""
    cum = _cumlen(center)
    best = (0.0, float("inf"))
    for i in range(1, len(center)):
        (x0, y0), (x1, y1) = center[i - 1], center[i]
        dx, dy = x1 - x0, y1 - y0
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0.0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / seg2))
        px, py = x0 + t * dx, y0 + t * dy
        d = math.hypot(x - px, y - py)
        if d < best[1]:
            best = (cum[i - 1] + t * math.sqrt(seg2), d)
    return best


def nearest_lanelet(lanelets: dict[int, Lanelet], x: float, y: float) -> tuple[int, float, float]:
    """(lanelet id, s_m, dist_m) of the centreline closest to map point (x, y)."""
    best = (-1, 0.0, float("inf"))
    for lid, ll in lanelets.items():
        s, d = project(centerline(ll), x, y)
        if d < best[2]:
            best = (lid, s, d)
    return best


def map_to_carla(
    x: float, y: float, yaw_deg: float, origin: tuple[float, float, float]
) -> tuple[float, float, float]:
    """Inverse of map_frame.carla_to_map for x/y plus the yaw negation: CARLA (x, y, yaw_deg)."""
    ox, oy, _ = origin
    return (x - ox, oy - y, -yaw_deg)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--osm", required=True)
    p.add_argument("--map-origin", default="", help='"X,Y,Z" metres; omit for Local-projector maps')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--lanelet", type=int, help="lanelet id; use with --s")
    g.add_argument(
        "--nearest-to-carla",
        metavar="X,Y",
        help="CARLA point to snap onto the nearest lanelet"
        " (use --nearest-to-carla=-X,Y if X starts with a minus sign)",
    )
    g.add_argument(
        "--nearest-to-map",
        metavar="X,Y",
        help="map-frame point to snap onto the nearest lanelet"
        " (use --nearest-to-map=-X,Y if X starts with a minus sign)",
    )
    p.add_argument("--s", type=float, default=0.0, help="arclength into --lanelet, metres")
    a = p.parse_args(argv)
    origin = parse_origin(a.map_origin)
    lanelets = load_lanelets(a.osm)
    if a.lanelet is not None:
        if a.lanelet not in lanelets:
            sys.stderr.write(f"lanelet {a.lanelet} not found ({len(lanelets)} lanelets loaded)\n")
            return 2
        lid, s = a.lanelet, a.s
        dist = 0.0
    else:
        text = a.nearest_to_map or a.nearest_to_carla
        qx, qy = (float(v) for v in text.split(","))
        if a.nearest_to_carla:
            qx, qy = origin[0] + qx, origin[1] - qy
        lid, s, dist = nearest_lanelet(lanelets, qx, qy)
    mx, my, myaw = pose_at(centerline(lanelets[lid]), s)
    cx, cy, cyaw = map_to_carla(mx, my, myaw, origin)
    print(f"lanelet: {lid} s={s:.3f} m off_centre={dist:.3f} m")
    print(f"map: {mx:.3f} {my:.3f} {myaw:.3f}")
    print(f"carla: {cx:.3f} {cy:.3f} {cyaw:.3f}")
    print(f'--goal "{cx:.3f},{cy:.3f},{cyaw:.3f}"')
    print(
        f'--spawn-pose "{cx:.3f},{cy:.3f},<GROUND_Z>,{cyaw:.3f}"   # replace <GROUND_Z> with the live cast_ray ground height'
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
