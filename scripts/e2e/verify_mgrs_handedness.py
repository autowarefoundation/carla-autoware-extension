#!/usr/bin/env python3
"""Verify the CARLA-world -> MGRS-local transform against the lanelet2 .osm.

The integration's #1 coordinate risk is the handedness / Y-flip between CARLA
(left-handed, Z-up) and OpenDRIVE / MGRS-local (right-handed, Z-up). The
extension's GNSS pose synthesis (runner + extension) reuses
``world_to_mgrs_local()`` verbatim, so this transform is pinned here first and
its handedness is measured against the Nishi-Shinjuku map by the companion
``probe_carla_mgrs.py`` (results recorded in ``docs/mgrs-handedness.md``).

Verified affine relation (both directions), with CARLA world in *centimetres*:

    mgrs_x = offset_x + (x_cm / 100)          x_cm  =  (mgrs_x - offset_x) * 100
    mgrs_y = offset_y - (y_cm / 100)   <-Y    y_cm  =  (offset_y - mgrs_y) * 100  <-Y
    mgrs_z = offset_z + (z_cm / 100)          z_cm  =  (mgrs_z - offset_z) * 100

    offset = CONVERTER_OFFSET = (81655.73, 50137.43, 42.49998)  # MGRS 54SUE, m

Units -- READ THIS. The forward function takes centimetres because that is the
frame the extension .so sees: a UE ``FTransform`` is native centimetres. The
CARLA *PythonAPI* instead reports metres (LibCarla parses OpenDRIVE metres
straight into the road map), so any verification done through the PythonAPI must
scale by 100 first -- use ``world_m_to_mgrs_local()`` for that. Getting this
wrong is a silent factor-of-100 error.

Handedness: the only axis flip is Y, and it lives entirely at the CARLA<->
OpenDRIVE boundary (LibCarla negates Y when it ingests the right-handed xodr
into left-handed UE world space). OpenDRIVE-local and MGRS-local share
handedness -- ``mgrs = converter_offset + opendrive_local`` with no flip -- so
the single Y negation between CARLA and OpenDRIVE is also the single Y negation
between CARLA and MGRS-local. Corroborated offline by the xodr <header> bounds
(MGRS-local) matching the planView geometry (OpenDRIVE-local) once the offset is
added, and live by ``probe_carla_mgrs.py``.

Per-map offset: only the TRANSLATION is map-specific -- the Y flip and the unit
convention are properties of the CARLA<->OpenDRIVE boundary and therefore hold
for every map. ``MAP_OFFSETS`` is the Python mirror of the extension's
``MgrsOffset.h`` table and ``offset_for_map()`` mirrors its ``map_offset_for``
lookup, including the refusal to fall back on an unknown name. The transforms
below still DEFAULT to Nishi-Shinjuku, so every historical call site is
unchanged; the harness entry points resolve the active map explicitly.
"""

from __future__ import annotations

import argparse
import os
import sys

# Per-map converter offsets, metres, in the Autoware `map` frame. Byte-identical
# to the extension's MgrsOffset.h table -- keep the two in lockstep.
MAP_OFFSETS: dict[str, tuple[float, float, float]] = {
    # autoware_lanelet2_to_opendrive conf/map/nishishinjuku.yaml `offset:` block;
    # MGRS 54SUE local frame.
    "NishishinjukuMap": (81655.73, 50137.43, 42.49998),
    # autoware-contents Town10: `projector_type: Local`, exported from the SAME
    # CARLA town, so the map frame IS the CARLA world frame up to the Y flip.
    # Measured by fit_map_offset.py, not assumed (median residual 0.000 m).
    "Town10HD_Opt": (0.0, 0.0, 0.0),
}
DEFAULT_MAP = "NishishinjukuMap"
MAP_ENV_VAR = "CARLA_AUTOWARE_MAP"  # the same selector the extension .so reads

CONVERTER_OFFSET = MAP_OFFSETS[DEFAULT_MAP]  # historical name, kept for call sites


def offset_for_map(map_name: str | None = None) -> tuple[float, float, float]:
    """Resolve a map name to its converter offset.

    ``None``/empty falls back to ``$CARLA_AUTOWARE_MAP`` and then to
    :data:`DEFAULT_MAP`, matching the extension's resolution order. An UNKNOWN
    name RAISES rather than falling back: silently using one map's offset on
    another surfaces only downstream, as NDT never converging, which is far more
    expensive to diagnose than a config error raised here.
    """
    name = map_name or os.environ.get(MAP_ENV_VAR) or DEFAULT_MAP
    if name not in MAP_OFFSETS:
        known = ", ".join(sorted(MAP_OFFSETS))
        raise ValueError(f"unknown map {name!r}; known maps: {known}")
    return MAP_OFFSETS[name]


def world_to_mgrs_local(
    x_cm: float, y_cm: float, z_cm: float, offset: tuple[float, float, float] = CONVERTER_OFFSET
) -> tuple[float, float, float]:
    """CARLA world transform (cm, left-handed) -> map-local pose (m, right-handed)."""
    ox, oy, oz = offset
    mgrs_x = ox + (x_cm / 100.0)
    mgrs_y = oy - (y_cm / 100.0)  # Y flip: left-handed -> right-handed
    mgrs_z = oz + (z_cm / 100.0)
    return (mgrs_x, mgrs_y, mgrs_z)


def mgrs_local_to_world_cm(
    mgrs_x: float,
    mgrs_y: float,
    mgrs_z: float,
    offset: tuple[float, float, float] = CONVERTER_OFFSET,
) -> tuple[float, float, float]:
    """Map-local pose (m, right-handed) -> CARLA world transform (cm, left-handed).

    Exact inverse of :func:`world_to_mgrs_local`.
    """
    ox, oy, oz = offset
    x_cm = (mgrs_x - ox) * 100.0
    y_cm = (oy - mgrs_y) * 100.0  # Y flip: right-handed -> left-handed
    z_cm = (mgrs_z - oz) * 100.0
    return (x_cm, y_cm, z_cm)


def world_m_to_mgrs_local(
    x_m: float, y_m: float, z_m: float, offset: tuple[float, float, float] = CONVERTER_OFFSET
) -> tuple[float, float, float]:
    """CARLA *PythonAPI* transform (metres) -> map-local pose (m).

    Convenience for verification harnesses that read the PythonAPI (which reports
    metres, not the centimetres the extension .so sees). Equivalent to scaling to
    centimetres and calling :func:`world_to_mgrs_local`.
    """
    return world_to_mgrs_local(x_m * 100.0, y_m * 100.0, z_m * 100.0, offset)


def _compare_against_osm(carla_xyz_cm, osm_local_xy, tol_m: float, offset) -> int:
    mx, my, _ = world_to_mgrs_local(*carla_xyz_cm, offset)
    ex, ey = osm_local_xy
    dx, dy = abs(mx - ex), abs(my - ey)
    ok = dx <= tol_m and dy <= tol_m
    print(
        f"computed map-local=({mx:.3f},{my:.3f}) expected .osm=({ex:.3f},{ey:.3f}) "
        f"dx={dx:.3f} dy={dy:.3f} tol={tol_m} -> {'PASS' if ok else 'FAIL'}"
    )
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--carla-xyz-cm",
        nargs=3,
        type=float,
        required=True,
        help="ego world x y z in centimetres (extension .so frame; PythonAPI "
        "metres must be multiplied by 100 first)",
    )
    p.add_argument(
        "--osm-local-xy",
        nargs=2,
        type=float,
        required=True,
        help="the paired lanelet2 node local_x local_y in metres",
    )
    p.add_argument("--tol-m", type=float, default=0.5)
    p.add_argument(
        "--map",
        default=None,
        help=f"map whose converter offset to apply; defaults to ${MAP_ENV_VAR} "
        f"and then to {DEFAULT_MAP}",
    )
    a = p.parse_args()
    return _compare_against_osm(
        tuple(a.carla_xyz_cm), tuple(a.osm_local_xy), a.tol_m, offset_for_map(a.map)
    )


if __name__ == "__main__":
    sys.exit(main())
