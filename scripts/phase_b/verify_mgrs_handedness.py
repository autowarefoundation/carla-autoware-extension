#!/usr/bin/env python3
"""Verify the CARLA-world -> MGRS-local transform against the lanelet2 .osm.

The #1 Phase B coordinate risk is the handedness / Y-flip between CARLA
(left-handed, Z-up) and OpenDRIVE / MGRS-local (right-handed, Z-up). The
extension's GNSS pose synthesis (runner/extension Task 19) reuses
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
"""

from __future__ import annotations

import argparse
import sys

# autoware_lanelet2_to_opendrive conf/map/nishishinjuku.yaml `offset:` block.
CONVERTER_OFFSET = (81655.73, 50137.43, 42.49998)  # metres, MGRS 54SUE local frame


def world_to_mgrs_local(x_cm: float, y_cm: float, z_cm: float) -> tuple[float, float, float]:
    """CARLA world transform (cm, left-handed) -> MGRS-local pose (m, right-handed)."""
    ox, oy, oz = CONVERTER_OFFSET
    mgrs_x = ox + (x_cm / 100.0)
    mgrs_y = oy - (y_cm / 100.0)  # Y flip: left-handed -> right-handed
    mgrs_z = oz + (z_cm / 100.0)
    return (mgrs_x, mgrs_y, mgrs_z)


def mgrs_local_to_world_cm(
    mgrs_x: float, mgrs_y: float, mgrs_z: float
) -> tuple[float, float, float]:
    """MGRS-local pose (m, right-handed) -> CARLA world transform (cm, left-handed).

    Exact inverse of :func:`world_to_mgrs_local`.
    """
    ox, oy, oz = CONVERTER_OFFSET
    x_cm = (mgrs_x - ox) * 100.0
    y_cm = (oy - mgrs_y) * 100.0  # Y flip: right-handed -> left-handed
    z_cm = (mgrs_z - oz) * 100.0
    return (x_cm, y_cm, z_cm)


def world_m_to_mgrs_local(x_m: float, y_m: float, z_m: float) -> tuple[float, float, float]:
    """CARLA *PythonAPI* transform (metres) -> MGRS-local pose (m).

    Convenience for verification harnesses that read the PythonAPI (which reports
    metres, not the centimetres the extension .so sees). Equivalent to scaling to
    centimetres and calling :func:`world_to_mgrs_local`.
    """
    return world_to_mgrs_local(x_m * 100.0, y_m * 100.0, z_m * 100.0)


def _compare_against_osm(carla_xyz_cm, osm_local_xy, tol_m: float) -> int:
    mx, my, _ = world_to_mgrs_local(*carla_xyz_cm)
    ex, ey = osm_local_xy
    dx, dy = abs(mx - ex), abs(my - ey)
    ok = dx <= tol_m and dy <= tol_m
    print(
        f"computed MGRS-local=({mx:.3f},{my:.3f}) expected .osm=({ex:.3f},{ey:.3f}) "
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
    a = p.parse_args()
    return _compare_against_osm(tuple(a.carla_xyz_cm), tuple(a.osm_local_xy), a.tol_m)


if __name__ == "__main__":
    sys.exit(main())
