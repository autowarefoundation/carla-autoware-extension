#!/usr/bin/env python3
"""Regenerate a Town10 pcd from ground-truth-registered LiDAR sweeps.

Fallback tool for the pcd registration fix (ladder rung 2, run only if
``shift_pcd.py``'s rigid shift does not bring NDT error under the
absolute gate): drive the committed route once with the 128-channel
LiDAR, transform each sweep into the map frame using the ego's CARLA
ground-truth pose at that sweep's stamp (never NDT's own estimate, which
is the thing under test), voxel-downsample on a 0.2 m grid, and write a
PCD with ``shift_pcd.py``'s header builder and writer. Re-registering
every sweep from GT also fixes along-track sparsity, since points are no
longer inherited from the original recording's own (possibly sparse)
trajectory.

Usage (requires a running CARLA server with the committed route already
being driven by the E2E harness, e.g. ``MAP=Town10HD_Opt WITH_AUTOWARE=1
bash scripts/e2e/run_e2e.sh`` in another terminal; NOT runnable in CI):

    python3 build_pcd_from_gt.py --out town10-regen/pointcloud_map.pcd \\
        --map Town10HD_Opt --window 120 --voxel 0.2

Design: the transform-and-downsample core below (``sensor_pose_matrix``,
``transform_cloud_to_map``, ``voxel_downsample``,
``accumulate_and_downsample``) is plain numpy, unit-testable with
synthetic clouds and poses with no CARLA installed. Only
``collect_sweeps`` touches ``carla``, imported lazily inside it -- the
same discipline ``scripts/e2e/collect_gt.py`` uses -- so this module
still imports under bare pytest.

The CARLA-world -> map-frame conversion is imported from
``scripts.e2e.verify_mgrs_handedness`` (the single pinned source, kept
byte-identical to the extension's ``MgrsOffset.h``) rather than
re-derived here; a third copy of those constants is exactly the drift
this reuse avoids.
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from benchmarks.scripts.shift_pcd import make_header, sha256_file, write_pcd
from scripts.e2e.verify_mgrs_handedness import offset_for_map, world_m_to_mgrs_local

Pose6 = tuple[float, float, float, float, float, float]  # x, y, z, roll, pitch, yaw (deg)
Sweep = tuple[np.ndarray, Pose6]  # (Nx4 x/y/z/intensity in sensor frame, pose at capture)


def sensor_pose_matrix(
    x: float, y: float, z: float, roll_deg: float, pitch_deg: float, yaw_deg: float
) -> np.ndarray:
    """4x4 rigid transform: sensor-local frame -> CARLA world frame (metres).

    Mirrors ``carla.Transform.get_matrix()`` (LibCarla
    ``geom/Transform.h``, ``GetMatrix()``): the rotation equals
    ``Rz(yaw) @ Ry(pitch) @ Rx(roll)`` -- roll about X applied first,
    then pitch about Y, then yaw about Z -- all in degrees (CARLA/UE
    convention), then translated by (x, y, z).
    """
    cy, sy = np.cos(np.radians(yaw_deg)), np.sin(np.radians(yaw_deg))
    cp, sp = np.cos(np.radians(pitch_deg)), np.sin(np.radians(pitch_deg))
    cr, sr = np.cos(np.radians(roll_deg)), np.sin(np.radians(roll_deg))
    return np.array(
        [
            [cp * cy, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, x],
            [cp * sy, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, y],
            [-sp, cp * sr, cp * cr, z],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


def transform_cloud_to_map(
    points_xyzi: np.ndarray, pose: Pose6, offset: tuple[float, float, float]
) -> np.ndarray:
    """Sensor-local points (Nx4: x, y, z, intensity) -> map-frame Nx4.

    ``pose`` is the ego/sensor's ground-truth CARLA pose (PythonAPI
    metres/degrees) at the sweep's stamp. ``offset`` is the target map's
    converter offset (see ``offset_for_map``). The world -> map-frame step
    calls the pinned ``world_m_to_mgrs_local`` directly on the whole
    column (its arithmetic is a plain per-axis affine, so it vectorizes
    over an array unmodified) rather than re-deriving the offset/Y-flip.
    """
    xyz = points_xyzi[:, :3]
    matrix = sensor_pose_matrix(*pose)
    world = xyz @ matrix[:3, :3].T + matrix[:3, 3]
    mx, my, mz = world_m_to_mgrs_local(world[:, 0], world[:, 1], world[:, 2], offset)
    return np.column_stack([mx, my, mz, points_xyzi[:, 3]])


def voxel_downsample(points_xyzi: np.ndarray, voxel_m: float) -> np.ndarray:
    """Keep one point per occupied voxel cell (first occurrence wins).

    Quantizes x/y/z to a ``voxel_m`` grid and de-duplicates with
    ``np.unique``, per the brief's specified approach -- a cheap density
    cap, not a centroid average.
    """
    quantized = np.floor(points_xyzi[:, :3] / voxel_m).astype(np.int64)
    _, first_idx = np.unique(quantized, axis=0, return_index=True)
    return points_xyzi[np.sort(first_idx)]


def accumulate_and_downsample(
    sweeps: list[Sweep], offset: tuple[float, float, float], voxel_m: float
) -> np.ndarray:
    """Map every sweep, concatenate, then downsample once over the whole
    route -- so a point seen in two sweeps collapses to one regardless of
    which sweep it came from."""
    mapped = [transform_cloud_to_map(points, pose, offset) for points, pose in sweeps]
    merged = np.concatenate(mapped, axis=0) if mapped else np.zeros((0, 4))
    return voxel_downsample(merged, voxel_m)


def collect_sweeps(host: str, port: int, window_s: float, role_name: str = "ego") -> list[Sweep]:
    """Attach a 128-channel LiDAR to the ego and record sweeps for
    ``window_s`` seconds. Assumes the ego is already being driven along
    the committed route by a running E2E harness (the same precondition
    ``collect_gt.py`` observes ground truth under) -- this only records,
    it does not drive. Only this function touches ``carla``.
    """
    import carla

    from scripts.e2e.collect_gt import find_ego

    client = carla.Client(host, port)
    world = client.get_world()
    world.wait_for_tick()  # sync mode: a cold client sees an empty snapshot until ticked
    ego = find_ego(world)

    bp = world.get_blueprint_library().find("sensor.lidar.ray_cast")
    bp.set_attribute("channels", "128")
    bp.set_attribute("points_per_second", "2200000")
    bp.set_attribute("range", "100")
    lidar = world.spawn_actor(bp, carla.Transform(), attach_to=ego)

    sweeps: list[Sweep] = []

    def _on_measurement(measurement) -> None:
        raw = np.frombuffer(bytes(measurement.raw_data), dtype=np.float32).reshape(-1, 4).copy()
        t = measurement.transform  # the LiDAR's own GT pose at capture, mount offset included
        pose = (
            t.location.x,
            t.location.y,
            t.location.z,
            t.rotation.roll,
            t.rotation.pitch,
            t.rotation.yaw,
        )
        sweeps.append((raw, pose))

    lidar.listen(_on_measurement)
    try:
        end = time.time() + window_s
        while time.time() < end:
            world.wait_for_tick()
    finally:
        lidar.stop()
        lidar.destroy()
    return sweeps


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", required=True, help="output .pcd path")
    p.add_argument("--map", default=None, help="target map name (see offset_for_map)")
    p.add_argument("--window", type=float, default=120.0, help="capture window, seconds")
    p.add_argument("--voxel", type=float, default=0.2, help="voxel grid size, metres")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=2000)
    args = p.parse_args(argv)

    offset = offset_for_map(args.map)  # resolved before connecting, like collect_gt.py
    sweeps = collect_sweeps(args.host, args.port, args.window)
    merged = accumulate_and_downsample(sweeps, offset, args.voxel)

    write_pcd(args.out, make_header(len(merged)), merged, "binary")
    print(f"sweeps={len(sweeps)} points={len(merged)}")
    print(f"out sha256={sha256_file(args.out)}  {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
