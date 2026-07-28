#!/usr/bin/env python3
"""Measure a map's CARLA-world -> Autoware-map-frame translation, offline.

This is where the numbers in ``MAP_OFFSETS`` / ``MgrsOffset.h`` come from. The
handedness half of the transform is already settled (a single Y negation at the
CARLA<->OpenDRIVE boundary; ``verify_mgrs_handedness.py`` documents the argument
and ``probe_carla_mgrs.py`` measured it live), and it is a property of that
boundary, so it is the same for every map. What is map-specific is the
TRANSLATION, and this script fits it from geometry rather than trusting a
converter config or an "it should be identity" prior.

Method. Two independent descriptions of the same road network are compared:

  * CARLA's, via ``carla.Map(name, xodr)`` -- constructed straight from the
    map's committed ``.xodr``, so NO simulator needs to be running. Lane
    centres come from ``generate_waypoints``; each is shifted by +/- half the
    lane width along the waypoint's right-vector to recover the two lane
    BOUNDARIES, which is what a lanelet2 map actually stores.
  * Autoware's, via the lanelet2 ``.osm``: every ``way`` is a boundary
    linestring, read in map-frame metres from the nodes' ``local_x``/``local_y``
    (valid because these bundles declare ``projector_type: Local``).

Residual = distance from a transformed CARLA boundary point to the nearest
lanelet2 SEGMENT (not the nearest node): point-to-segment has no sampling floor,
so a reported "median 0.000 m" means the two descriptions genuinely coincide
rather than that the polylines were resampled finely enough to hide the gap.

The translation is fitted by iterated median displacement (an ICP whose only
free parameter is the translation, since the rotation is known to be the Y
flip). The MEDIAN, not the mean, because a lanelet2 map legitimately omits
CARLA lanes -- parking aisles, service roads -- and those unmatched probes must
not drag the fit.

Handedness is re-checked here as a guard, not as a discovery: the no-flip
hypothesis is scored too, and it must lose by a wide margin. If it ever does
not, the map does not share the assumed CARLA<->OpenDRIVE convention and the
whole affine needs revisiting, not just this offset.

Usage (Town10HD_Opt; the .xodr ships with the CARLA content):

    python3 scripts/e2e/fit_map_offset.py \\
        --xodr "$CARLA_ROOT/Unreal/CarlaUnreal/Content/Carla/Maps/OpenDrive/Town10HD_Opt.xodr" \\
        --osm ~/autoware_map/town10/lanelet2_map.osm --map-name Town10HD_Opt

Exits non-zero if the fitted median residual exceeds ``--tol-m``.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET

import numpy as np

# Queries are distance-tested against every lanelet2 segment at once, so a chunk
# allocates (CHUNK, n_segments, 2) float64 intermediates. 200 keeps that in the
# tens of MB for a town-sized map while staying big enough to amortise numpy.
_QUERY_CHUNK = 200


def parse_osm_polylines(osm_path: str) -> list[np.ndarray]:
    """lanelet2 ``.osm`` -> one (N,2) array of map-frame metres per ``way``.

    Reads ``local_x``/``local_y``, which are already map-frame metres for a
    ``projector_type: Local`` bundle. Ways with fewer than two resolvable nodes
    carry no segment and are dropped.
    """
    root = ET.parse(osm_path).getroot()
    nodes: dict[str, tuple[float, float]] = {}
    for node in root.findall("node"):
        tags = {t.get("k"): t.get("v") for t in node.findall("tag")}
        if "local_x" in tags and "local_y" in tags:
            nodes[node.get("id")] = (float(tags["local_x"]), float(tags["local_y"]))
    polylines = []
    for way in root.findall("way"):
        pts = [nodes[nd.get("ref")] for nd in way.findall("nd") if nd.get("ref") in nodes]
        if len(pts) >= 2:
            polylines.append(np.asarray(pts, dtype=float))
    return polylines


def polylines_to_segments(polylines: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Flatten polylines into (starts, ends), each (S,2), for distance queries."""
    starts = [p[:-1] for p in polylines if len(p) >= 2]
    ends = [p[1:] for p in polylines if len(p) >= 2]
    if not starts:
        return np.empty((0, 2)), np.empty((0, 2))
    return np.concatenate(starts), np.concatenate(ends)


def nearest_on_segments(
    points: np.ndarray, starts: np.ndarray, ends: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Nearest point on any segment, for each query.

    Returns ``(distances (Q,), closest_points (Q,2))``. Exact: each query is
    projected onto every segment with the parameter clamped to [0,1], so a
    query near a vertex or beyond a segment end is handled by the clamp rather
    than by resampling the polyline.
    """
    seg = ends - starts
    # A degenerate (zero-length) segment would divide by zero; clamping the
    # denominator makes t collapse to 0, i.e. the segment's start point, which
    # is the correct answer for a segment of zero length.
    denom = np.maximum((seg * seg).sum(axis=1), 1e-12)
    dists = np.empty(len(points))
    closest = np.empty((len(points), 2))
    for lo in range(0, len(points), _QUERY_CHUNK):
        chunk = points[lo : lo + _QUERY_CHUNK]
        rel = chunk[:, None, :] - starts[None, :, :]  # (C,S,2)
        t = np.clip((rel * seg[None, :, :]).sum(axis=2) / denom[None, :], 0.0, 1.0)
        proj = starts[None, :, :] + t[:, :, None] * seg[None, :, :]  # (C,S,2)
        delta = chunk[:, None, :] - proj
        d = np.hypot(delta[:, :, 0], delta[:, :, 1])  # (C,S)
        best = d.argmin(axis=1)
        rows = np.arange(len(chunk))
        dists[lo : lo + _QUERY_CHUNK] = d[rows, best]
        closest[lo : lo + _QUERY_CHUNK] = proj[rows, best]
    return dists, closest


def apply_affine(carla_xy: np.ndarray, ox: float, oy: float, flip: bool = True) -> np.ndarray:
    """CARLA world XY (metres) -> map frame, under the Y-flip + translation."""
    y = -carla_xy[:, 1] if flip else carla_xy[:, 1]
    return np.column_stack([ox + carla_xy[:, 0], oy + y])


def fit_translation(
    carla_xy: np.ndarray,
    starts: np.ndarray,
    ends: np.ndarray,
    initial: tuple[float, float] = (0.0, 0.0),
    iterations: int = 20,
    tol_m: float = 1e-6,
) -> tuple[float, float]:
    """Fit (ox, oy) by iterated MEDIAN displacement to the nearest segment.

    The rotation is known (the Y flip), so translation is the only free
    parameter and each iteration is a closed-form update: move by the median of
    the per-probe displacement to its nearest boundary point. The median makes
    probes on CARLA lanes the lanelet2 map simply does not contain -- which sit
    arbitrarily far away and never improve -- unable to drag the fit.

    LOCAL MINIMA ARE REAL, so ``initial`` must already be inside the right
    basin. A road network's boundaries are near-parallel lines about a lane
    width apart, which aliases: started half a lane width off, half the probes
    snap to one boundary and half to its neighbour, the median displacement
    cancels, and the iteration sits there. Measured on Town10HD_Opt -- seeded at
    ox=-1.86 m it converges to -1.86 m with a 0.544 m median residual, versus
    0.000 m at the true zero. The default (0,0) is right whenever the map frame
    is CARLA's own (any ``projector_type: Local`` bundle exported from the same
    town); a distant frame -- Nishi-Shinjuku's MGRS 54SUE origin is ~81 km away
    -- needs ``--initial-offset``. The residual this function's caller reports
    is what catches a bad basin: an aliased fit lands near half a lane width,
    nowhere near the acceptance threshold.

    Convergence is geometric, roughly halving the error per iteration (a probe
    on a boundary running along X constrains only Y and vice versa, so each axis
    is corrected by about half the probes). ``iterations`` is therefore a cap,
    not a cost: the loop exits as soon as a step falls under ``tol_m``, which is
    immediately when the initial offset is already correct.
    """
    ox, oy = initial
    for _ in range(iterations):
        _, closest = nearest_on_segments(apply_affine(carla_xy, ox, oy), starts, ends)
        step = np.median(closest - apply_affine(carla_xy, ox, oy), axis=0)
        ox, oy = ox + float(step[0]), oy + float(step[1])
        if abs(step[0]) < tol_m and abs(step[1]) < tol_m:
            break
    return ox, oy


def carla_lane_boundary_points(xodr_path: str, map_name: str, step_m: float) -> np.ndarray:
    """CARLA lane BOUNDARY points (world metres) straight from the ``.xodr``.

    ``carla`` is imported lazily so the rest of this module stays importable --
    and unit-testable -- with no CARLA egg installed, matching the import
    discipline in ``collect_gt.py`` / ``runner/__main__.py``.
    """
    import carla

    with open(xodr_path) as f:
        world_map = carla.Map(map_name, f.read())
    pts = []
    for wp in world_map.generate_waypoints(step_m):
        loc = wp.transform.location
        right = wp.transform.get_right_vector()
        half = wp.lane_width / 2.0
        pts.append((loc.x + half * right.x, loc.y + half * right.y))
        pts.append((loc.x - half * right.x, loc.y - half * right.y))
    return np.asarray(pts, dtype=float)


def _report(label: str, d: np.ndarray) -> float:
    med = float(np.median(d))
    print(
        f"{label}: n={len(d)} median={med:.5f} mean={d.mean():.5f} "
        f"p95={np.percentile(d, 95):.5f} p99={np.percentile(d, 99):.5f} "
        f"max={d.max():.5f} m"
    )
    return med


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--xodr", required=True, help="the CARLA map's OpenDRIVE file")
    p.add_argument("--osm", required=True, help="the Autoware bundle's lanelet2_map.osm")
    p.add_argument("--map-name", required=True, help="map name, e.g. Town10HD_Opt")
    p.add_argument(
        "--waypoint-step-m",
        type=float,
        default=1.0,
        help="spacing of the CARLA lane-centre samples the boundaries derive from",
    )
    p.add_argument(
        "--fit-probes",
        type=int,
        default=3000,
        help="probes used for the ITERATIVE fit (the final residual always uses all)",
    )
    p.add_argument(
        "--initial-offset",
        nargs=2,
        type=float,
        default=(0.0, 0.0),
        metavar=("OX", "OY"),
        help="starting translation for the fit. The default is right for a map "
        "frame that IS CARLA's own; a distant frame needs a seed within about "
        "half a lane width of the answer (see fit_translation on aliasing)",
    )
    p.add_argument("--tol-m", type=float, default=0.05, help="median-residual acceptance")
    a = p.parse_args(argv)

    polylines = parse_osm_polylines(a.osm)
    starts, ends = polylines_to_segments(polylines)
    print(f"lanelet2: {len(polylines)} ways, {len(starts)} segments  ({a.osm})")

    carla_xy = carla_lane_boundary_points(a.xodr, a.map_name, a.waypoint_step_m)
    print(f"CARLA   : {len(carla_xy)} lane-boundary probes at {a.waypoint_step_m} m  ({a.xodr})")

    # Deterministic subsample for the fit iterations; seeded so a re-run of this
    # derivation reproduces the recorded number exactly.
    rng = np.random.default_rng(0)
    sub = carla_xy
    if len(carla_xy) > a.fit_probes:
        sub = carla_xy[rng.choice(len(carla_xy), size=a.fit_probes, replace=False)]

    seed = (float(a.initial_offset[0]), float(a.initial_offset[1]))

    print("\n=== Handedness guard (both hypotheses at the initial offset) ===")
    flip_d, _ = nearest_on_segments(apply_affine(sub, *seed, flip=True), starts, ends)
    noflip_d, _ = nearest_on_segments(apply_affine(sub, *seed, flip=False), starts, ends)
    med_flip = _report("  Y-FLIP  (map_y = -carla_y)", flip_d)
    med_noflip = _report("  NO-FLIP (map_y = +carla_y)", noflip_d)
    handedness_ok = med_flip * 5.0 < med_noflip
    print(f"  -> {'Y IS FLIPPED' if handedness_ok else 'NOT A CLEAN FLIP -- STOP'}")

    print("\n=== Translation fit (Y flip assumed, median displacement) ===")
    ox, oy = fit_translation(sub, starts, ends, initial=seed)
    print(f"  fitted offset = ({ox:.4f}, {oy:.4f}) m")

    print("\n=== Residual at the fitted offset (ALL probes) ===")
    final_d, _ = nearest_on_segments(apply_affine(carla_xy, ox, oy), starts, ends)
    median = _report("  residual", final_d)
    print(f"  within 0.01 m: {np.mean(final_d < 0.01):.4f}   within {a.tol_m} m: "
          f"{np.mean(final_d < a.tol_m):.4f}")

    # Sensitivity: what a wrong offset would have looked like, so the reported
    # residual is readable as "the fit is resolved", not just "the maps agree".
    print("\n=== Sensitivity (median residual if the offset were wrong) ===")
    for err in (0.05, 0.10, 0.25, 1.00):
        d, _ = nearest_on_segments(apply_affine(sub, ox + err, oy), starts, ends)
        print(f"  ox off by {err:>4.2f} m -> median {np.median(d):.4f} m")

    ok = handedness_ok and median <= a.tol_m
    print(
        f"\n=== VERDICT: {a.map_name} offset = ({ox:.4f}, {oy:.4f}) "
        f"median residual {median:.5f} m <= {a.tol_m} -> {'PASS' if ok else 'FAIL'} ==="
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
