#!/usr/bin/env python3
"""Live measurement of the CARLA-world <-> OpenDRIVE/MGRS transform (Nishi-Shinjuku).

Step 5 "live handedness check" for Task 5. It *measures* the handedness (Y-flip)
and unit convention that ``verify_mgrs_handedness.world_to_mgrs_local`` encodes,
using the running CARLA map as ground truth. The projection-free CARLA<->
OpenDRIVE comparison is the pivot; the offline xodr-header analysis (see
``docs/mgrs-handedness.md``) closes the OpenDRIVE-local <-> MGRS-local half.

Why not use ``transform_to_geolocation``? On this build the loaded map carries a
**degenerate geo-reference** -- ``transform_to_geolocation((0,0,0))`` returns
lat=0.0 (not ~35.688), so CARLA's WGS84 output is unusable as a lat/lon ground
truth (and the extension must NOT depend on it for GNSS -- it must use the affine
offset directly, which is the whole point of ``world_to_mgrs_local``). We record
that degenerate value as evidence, then verify against the xodr geometry instead.

Two checks, neither trusting the affine it verifies:

  1. Handedness by point-cloud overlap (decisive, lane-offset-robust).
     ``generate_waypoints`` -> CARLA world (x,y) cloud; xodr planView -> (x,y)
     cloud. Under the Y-flip hypothesis a xodr point (x,y) maps to CARLA (x,-y);
     under no-flip to (x,+y). We report each cloud's bbox and the median nearest-
     neighbour distance under both hypotheses. Flip ~ lane-half-width, no-flip ~
     hundreds of metres => the flip is real, X is not flipped, units are metres.

  2. Reference-line residual table (sub-metre, per probe point).
     For a spread of road geometry segments (road, s) the xodr planView gives the
     reference-line point (x,y). ``get_waypoint_xodr(road,lane,s)`` returns a lane
     *centre*, offset from the reference line by ~half a lane width, so we recover
     CARLA's reference line by shifting the innermost-lane centre by +/- w/2 along
     the waypoint's right-vector (sign chosen to match, which is itself a check
     that the offset is exactly a lane half-width). Compare to the Y-flipped xodr
     point (x,-y): residual is then sub-decimetre, i.e. pure frame agreement with
     the lane geometry removed.

CARLA PythonAPI reports metres; the extension .so sees UE centimetres. This
script works in metres and converts only at the boundary.

Usage:
    export ROS_DOMAIN_ID=0
    python3 scripts/phase_b/probe_carla_mgrs.py \
        --xodr <...>/NishishinjukuMap.xodr [--map NishishinjukuMap]
"""

from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET


def parse_xodr_geoms(xodr_path):
    """Return list of (road_id:int, s:float, x:float, y:float) planView starts."""
    geoms = []
    road_id = None
    for _ev, elem in ET.iterparse(xodr_path, events=("start",)):
        if elem.tag == "road":
            road_id = int(elem.get("id"))
        elif elem.tag == "geometry" and road_id is not None:
            geoms.append(
                (road_id, float(elem.get("s")), float(elem.get("x")), float(elem.get("y")))
            )
    return geoms


def check_georef_degenerate(carla, world_map):
    g = world_map.transform_to_geolocation(carla.Location(x=0.0, y=0.0, z=0.0))
    print("\n=== Geo-reference sanity (evidence of degeneracy) ===")
    print(f"transform_to_geolocation((0,0,0)) = lat {g.latitude:.6f}, lon {g.longitude:.6f}")
    ok = abs(g.latitude) > 1.0  # Nishi-Shinjuku is ~35.69 N
    print(
        "expected lat ~35.69 for Nishi-Shinjuku ->",
        "OK" if ok else "DEGENERATE (lat~0): CARLA geolocation unusable here",
    )
    return ok


def check_cloud_handedness(carla, world_map, geoms):
    """Check 1: waypoint cloud vs xodr cloud, flip vs no-flip."""
    import numpy as np

    wps = world_map.generate_waypoints(3.0)
    cw = np.array([[w.transform.location.x, w.transform.location.y] for w in wps])
    cx = np.array([[g[2], g[3]] for g in geoms])  # xodr (x,y)
    print("\n=== Check 1: point-cloud handedness (bounding boxes) ===")
    print(
        f"CARLA waypoints: n={len(cw)}  x[{cw[:, 0].min():.1f},{cw[:, 0].max():.1f}] "
        f"y[{cw[:, 1].min():.1f},{cw[:, 1].max():.1f}]"
    )
    print(
        f"xodr planView : n={len(cx)}  x[{cx[:, 0].min():.1f},{cx[:, 0].max():.1f}] "
        f"y[{cx[:, 1].min():.1f},{cx[:, 1].max():.1f}]"
    )
    print(f"  -> Y-flip predicts CARLA y in [{-cx[:, 1].max():.1f},{-cx[:, 1].min():.1f}]")

    # Median nearest-neighbour of a CARLA sample to the xodr cloud under each map.
    rng = np.random.default_rng(0)
    sample = cw[rng.choice(len(cw), size=min(400, len(cw)), replace=False)]

    def median_nn(target_xy):
        d = []
        for p in sample:
            dd = np.hypot(target_xy[:, 0] - p[0], target_xy[:, 1] - p[1])
            d.append(dd.min())
        return float(np.median(d)), float(np.max(d))

    flip = np.column_stack([cx[:, 0], -cx[:, 1]])
    noflip = np.column_stack([cx[:, 0], cx[:, 1]])
    m_flip, mx_flip = median_nn(flip)
    m_no, mx_no = median_nn(noflip)
    print(f"median NN(CARLA -> xodr) under Y-FLIP (x,-y): {m_flip:.3f} m (max {mx_flip:.3f})")
    print(f"median NN(CARLA -> xodr) under NO-FLIP (x,+y): {m_no:.3f} m (max {mx_no:.3f})")
    verdict = m_flip < 5.0 and m_flip * 5 < m_no
    print(
        "-> handedness:",
        "Y IS FLIPPED (CARLA y = -xodr y)" if verdict else "INCONCLUSIVE / not a clean flip",
    )
    return verdict, m_flip


def check_reference_line(carla, world_map, geoms, n_probe, tol_m):
    """Check 2: per-segment reference-line residual under the Y-flip map."""
    # Spread probe segments across distinct roads and the map extent.
    by_road = {}
    for g in geoms:
        by_road.setdefault(g[0], []).append(g)
    picked = [segs[len(segs) // 2] for segs in by_road.values()]  # a mid-road seg per road
    picked.sort(key=lambda g: (g[2], g[3]))
    if len(picked) > n_probe:
        step = len(picked) / n_probe
        picked = [picked[int(i * step)] for i in range(n_probe)]

    print("\n=== Check 2: reference-line residual (CARLA vs Y-flipped xodr) ===")
    print(
        f"{'road':>6} {'s':>7} {'lane':>4} {'w':>5} {'xodr_x':>9} {'-xodr_y':>9} "
        f"{'est_x':>9} {'est_y':>9} {'res_m':>6}"
    )
    residuals = []
    for road, s, x, y in picked:
        wp = None
        # Try the innermost lanes first; +/-2 only as a last resort so a road with
        # no first lane still yields a point (flagged and skipped below).
        for lane in (1, -1, 2, -2):
            try:
                wp = world_map.get_waypoint_xodr(road, lane, s)
            except Exception:
                wp = None
            if wp is not None:
                break
        if wp is None:
            continue
        # GUARD: shifting the lane centre by +/- w/2 recovers the reference line
        # ONLY for the first lane (|id|=1); for |id|>=2 the reference line is
        # ~1.5+ lane widths away, so the +/- w/2 estimate would be wrong. Skip
        # such rows (with a warning) rather than let them pollute the residual.
        if abs(wp.lane_id) != 1:
            print(
                f"{road:>6} {s:>7.2f} {wp.lane_id:>4} {'':>5} "
                f"{x:>9.3f} {-y:>9.3f} {'':>9} {'':>9}  SKIP(|lane|!=1)"
            )
            continue
        loc = wp.transform.location
        w = wp.lane_width
        rv = wp.transform.get_right_vector()
        exp_x, exp_y = x, -y  # Y-flip hypothesis
        # Recover the reference line from the lane centre: shift by +/- w/2 along
        # the right-vector, taking the sign that lands on the reference line.
        best = None
        for sign in (0.5, -0.5):
            ex, ey = loc.x + sign * w * rv.x, loc.y + sign * w * rv.y
            d = math.hypot(ex - exp_x, ey - exp_y)
            if best is None or d < best[0]:
                best = (d, ex, ey)
        residuals.append(best[0])
        print(
            f"{road:>6} {s:>7.2f} {wp.lane_id:>4} {w:>5.2f} {x:>9.3f} {-y:>9.3f} "
            f"{best[1]:>9.3f} {best[2]:>9.3f} {best[0]:>6.3f}"
        )
    if residuals:
        residuals.sort()
        med = residuals[len(residuals) // 2]
        print(
            f"n={len(residuals)} median residual {med:.3f} m  max {max(residuals):.3f} m "
            f"(tol {tol_m})"
        )
        return med, max(residuals), len(residuals)
    print("no probe points had resolvable lanes")
    return None, None, 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", default=2000, type=int)
    p.add_argument("--xodr", required=True)
    p.add_argument("--map", default="NishishinjukuMap")
    p.add_argument("--n-probe", default=20, type=int)
    p.add_argument(
        "--tol-m",
        default=0.5,
        type=float,
        help="reference-line residual tolerance (frame, lane offset removed)",
    )
    a = p.parse_args()

    import carla

    client = carla.Client(a.host, a.port)
    client.set_timeout(120.0)
    world = client.get_world()
    cur = world.get_map().name
    print(f"connected; current map = {cur}")
    if a.map not in cur:
        print(f"loading map {a.map} ...")
        world = client.load_world(a.map)
    world_map = world.get_map()
    print(f"active map = {world_map.name}")

    geoms = parse_xodr_geoms(a.xodr)
    print(f"parsed {len(geoms)} xodr planView geometries")

    check_georef_degenerate(carla, world_map)
    hand_ok, m_flip = check_cloud_handedness(carla, world_map, geoms)
    med, mx, n = check_reference_line(carla, world_map, geoms, a.n_probe, a.tol_m)

    print("\n=== VERDICT ===")
    print(
        f"handedness (Check 1): {'Y FLIPPED - PASS' if hand_ok else 'FAIL'} "
        f"(median NN under flip {m_flip:.3f} m)"
    )
    ref_ok = med is not None and med <= a.tol_m
    if med is not None:
        print(
            f"reference-line (Check 2): median {med:.3f} m <= {a.tol_m} over n={n} "
            f"-> {'PASS' if ref_ok else 'FAIL'}"
        )
    return 0 if (hand_ok and ref_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
