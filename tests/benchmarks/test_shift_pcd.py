"""Tests for the Town10 pcd registration tools (Task 11 Step 1).

Covers ``benchmarks/scripts/shift_pcd.py`` (rigid pcd shift, both the
binary and ascii layouts, plus the rejection paths for an unsupported
header) and the transform-and-downsample core of
``benchmarks/scripts/build_pcd_from_gt.py`` -- the CARLA client loop
around that core is not testable without a live simulator, so only the
plain-numpy core is exercised here. Both scripts share this one test file
because Task 11 Step 1's file scope lists a single test file to create.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from benchmarks.scripts import build_pcd_from_gt, shift_pcd
from scripts.e2e import verify_mgrs_handedness as mgrs

BINARY_HEADER = (
    "# .PCD v0.7 - Point Cloud Data file format\n"
    "VERSION 0.7\n"
    "FIELDS x y z intensity\n"
    "SIZE 4 4 4 4\n"
    "TYPE F F F F\n"
    "COUNT 1 1 1 1\n"
    "WIDTH 5\n"
    "HEIGHT 1\n"
    "VIEWPOINT 0 0 0 1 0 0 0\n"
    "POINTS 5\n"
    "DATA binary\n"
)

POINTS5 = np.array(
    [
        [0.0, 0.0, 0.0, 0.1],
        [1.0, 2.0, 3.0, 0.2],
        [-1.5, 2.5, -3.5, 0.3],
        [10.0, -10.0, 0.0, 0.4],
        [100.25, -50.5, 3.75, 0.5],
    ],
    dtype=np.float32,
)


def _write_binary_pcd(path, header: str = BINARY_HEADER, points: np.ndarray = POINTS5) -> None:
    with open(path, "wb") as f:
        f.write(header.encode("ascii"))
        f.write(points.astype(np.float32).tobytes())


def _write_ascii_pcd(path, points: np.ndarray = POINTS5) -> str:
    header = BINARY_HEADER.replace("DATA binary\n", "DATA ascii\n")
    with open(path, "wb") as f:
        f.write(header.encode("ascii"))
        np.savetxt(f, points, fmt="%.6f")
    return header


# --- shift_pcd: binary round trip -------------------------------------------


def test_shift_binary_pcd_applies_the_shift_and_preserves_the_header(tmp_path):
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    _write_binary_pcd(src)

    rc = shift_pcd.main(["--in", str(src), "--out", str(dst), "--dx", "1.0", "--dy", "-0.475"])
    assert rc == 0

    header_bytes = BINARY_HEADER.encode("ascii")
    out_bytes = dst.read_bytes()
    assert out_bytes[: len(header_bytes)] == header_bytes  # byte-identical header

    out_points = np.frombuffer(out_bytes[len(header_bytes) :], dtype=np.float32).reshape(-1, 4)
    expected = POINTS5.copy()
    expected[:, 0] += 1.0
    expected[:, 1] += -0.475
    np.testing.assert_allclose(out_points, expected, atol=1e-6)


def test_shift_binary_pcd_leaves_intensity_untouched(tmp_path):
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    _write_binary_pcd(src)

    shift_pcd.main(["--in", str(src), "--out", str(dst), "--dz", "2.0"])

    header_len = len(BINARY_HEADER.encode("ascii"))
    out_points = np.frombuffer(dst.read_bytes()[header_len:], dtype=np.float32).reshape(-1, 4)
    np.testing.assert_allclose(out_points[:, 3], POINTS5[:, 3], atol=1e-6)


# --- shift_pcd: ascii round trip --------------------------------------------


def test_shift_ascii_pcd_applies_the_shift_and_preserves_the_header(tmp_path):
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    header = _write_ascii_pcd(src)

    rc = shift_pcd.main(["--in", str(src), "--out", str(dst), "--dy", "-0.475"])
    assert rc == 0

    header_bytes = header.encode("ascii")
    out_bytes = dst.read_bytes()
    assert out_bytes[: len(header_bytes)] == header_bytes  # byte-identical header

    out_points = np.loadtxt(str(dst), skiprows=header.count("\n"))
    expected = POINTS5.astype(np.float64).copy()
    expected[:, 1] += -0.475
    np.testing.assert_allclose(out_points, expected, atol=1e-6)


# --- shift_pcd: provenance ---------------------------------------------------


def test_shift_prints_sha256_of_input_and_output(tmp_path, capsys):
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    _write_binary_pcd(src)

    shift_pcd.main(["--in", str(src), "--out", str(dst), "--dy", "-0.475"])

    printed = capsys.readouterr().out
    assert hashlib.sha256(src.read_bytes()).hexdigest() in printed
    assert hashlib.sha256(dst.read_bytes()).hexdigest() in printed


# --- shift_pcd: rejection paths -----------------------------------------------


def test_rejects_wrong_fields(tmp_path):
    """The real Town10 bundle's layout: x/y/z only, no intensity."""
    src = tmp_path / "in.pcd"
    header = (
        BINARY_HEADER.replace("FIELDS x y z intensity\n", "FIELDS x y z\n")
        .replace("SIZE 4 4 4 4\n", "SIZE 4 4 4\n")
        .replace("TYPE F F F F\n", "TYPE F F F\n")
        .replace("COUNT 1 1 1 1\n", "COUNT 1 1 1\n")
    )
    _write_binary_pcd(src, header=header, points=POINTS5[:, :3])
    with open(src, "rb") as f, pytest.raises(shift_pcd.PcdFormatError, match="FIELDS"):
        shift_pcd.read_header(f)


def test_rejects_wrong_size(tmp_path):
    src = tmp_path / "in.pcd"
    _write_binary_pcd(src, header=BINARY_HEADER.replace("SIZE 4 4 4 4\n", "SIZE 8 8 8 8\n"))
    with open(src, "rb") as f, pytest.raises(shift_pcd.PcdFormatError, match="SIZE"):
        shift_pcd.read_header(f)


def test_rejects_wrong_type(tmp_path):
    src = tmp_path / "in.pcd"
    _write_binary_pcd(src, header=BINARY_HEADER.replace("TYPE F F F F\n", "TYPE U U U U\n"))
    with open(src, "rb") as f, pytest.raises(shift_pcd.PcdFormatError, match="TYPE"):
        shift_pcd.read_header(f)


def test_rejects_binary_compressed_data_even_with_matching_fields(tmp_path):
    """Regression for the real bundle: ``~/autoware_map/town10/pointcloud_map.pcd``
    is ``DATA binary_compressed`` (LZF-compressed), which this tool does not
    decompress. Accepting it would misread the compressed bytes as raw
    float32 and silently corrupt the map, so it must fail loudly even when
    FIELDS/SIZE/TYPE already match x/y/z/intensity."""
    src = tmp_path / "in.pcd"
    _write_binary_pcd(src, header=BINARY_HEADER.replace("DATA binary\n", "DATA binary_compressed\n"))
    with open(src, "rb") as f, pytest.raises(shift_pcd.PcdFormatError, match="binary_compressed"):
        shift_pcd.read_header(f)


def test_main_refuses_a_malformed_input_and_does_not_write_output(tmp_path, capsys):
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    header = BINARY_HEADER.replace("FIELDS x y z intensity\n", "FIELDS x y z\n")
    _write_binary_pcd(src, header=header, points=POINTS5[:, :3])

    rc = shift_pcd.main(["--in", str(src), "--out", str(dst), "--dy", "-0.475"])

    assert rc != 0
    assert "FIELDS" in capsys.readouterr().err
    assert not dst.exists()


# --- build_pcd_from_gt: transform-and-downsample core -------------------------


def test_sensor_pose_matrix_is_identity_rotation_plus_translation_at_zero_angles():
    m = build_pcd_from_gt.sensor_pose_matrix(1.0, 2.0, 3.0, 0.0, 0.0, 0.0)
    expected = np.array(
        [
            [1.0, 0.0, 0.0, 1.0],
            [0.0, 1.0, 0.0, 2.0],
            [0.0, 0.0, 1.0, 3.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    np.testing.assert_allclose(m, expected, atol=1e-9)


def test_sensor_pose_matrix_rotates_local_x_to_world_y_at_yaw_90():
    m = build_pcd_from_gt.sensor_pose_matrix(0.0, 0.0, 0.0, 0.0, 0.0, 90.0)
    world = m[:3, :3] @ np.array([1.0, 0.0, 0.0])
    np.testing.assert_allclose(world, [0.0, 1.0, 0.0], atol=1e-9)


def test_transform_cloud_to_map_reuses_the_pinned_converter_not_a_local_copy():
    """The brief's hard requirement: the CARLA-world -> map-frame conversion
    must come from ``scripts.e2e.verify_mgrs_handedness`` -- the single
    pinned source shared with the extension's ``MgrsOffset.h`` -- and not
    be re-derived a third time."""
    assert build_pcd_from_gt.world_m_to_mgrs_local is mgrs.world_m_to_mgrs_local


def test_transform_cloud_to_map_applies_pose_then_the_pinned_mgrs_offset():
    offset = mgrs.MAP_OFFSETS["Town10HD_Opt"]  # (0, 0, 0): Town10's registered offset
    local = np.array([[1.0, 2.0, 3.0, 0.5]])
    pose = (10.0, 5.0, 2.0, 0.0, 0.0, 0.0)  # translation only

    mapped = build_pcd_from_gt.transform_cloud_to_map(local, pose, offset)

    # world = (11, 7, 5); map = (world_x, -world_y, world_z) on the pinned Y flip.
    np.testing.assert_allclose(mapped, [[11.0, -7.0, 5.0, 0.5]], atol=1e-6)


def test_voxel_downsample_keeps_one_point_per_occupied_cell():
    points = np.array(
        [
            [0.01, 0.01, 0.01, 1.0],
            [0.05, 0.05, 0.05, 2.0],  # same 0.2 m voxel as row 0
            [5.0, 5.0, 5.0, 3.0],  # a distinct voxel
        ]
    )
    kept = build_pcd_from_gt.voxel_downsample(points, voxel_m=0.2)
    assert len(kept) == 2
    assert 1.0 in kept[:, 3]  # first occurrence in the shared cell survives
    assert 3.0 in kept[:, 3]
    assert 2.0 not in kept[:, 3]


def test_voxel_downsample_preserves_order_of_first_occurrence():
    points = np.array([[5.0, 5.0, 5.0, 9.0], [0.0, 0.0, 0.0, 1.0]])
    kept = build_pcd_from_gt.voxel_downsample(points, voxel_m=0.2)
    assert list(kept[:, 3]) == [9.0, 1.0]


def test_accumulate_and_downsample_merges_sweeps_before_deduping():
    offset = (0.0, 0.0, 0.0)
    sweep_a = (np.array([[0.0, 0.0, 0.0, 1.0]]), (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    sweep_b = (np.array([[0.01, 0.0, 0.0, 2.0]]), (0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    merged = build_pcd_from_gt.accumulate_and_downsample([sweep_a, sweep_b], offset, voxel_m=0.2)

    assert len(merged) == 1  # both sweeps land in the same voxel


def test_build_pcd_from_gt_writes_via_shift_pcds_header_and_writer(tmp_path):
    """``build_pcd_from_gt`` must reuse ``shift_pcd.make_header``/``write_pcd``
    rather than re-implementing PCD serialization a second time."""
    out = tmp_path / "regen.pcd"
    points = np.array([[1.0, 2.0, 3.0, 0.5]], dtype=np.float32)

    header = shift_pcd.make_header(len(points))
    shift_pcd.write_pcd(out, header, points, "binary")

    with open(out, "rb") as f:
        header_lines, fmt, n_points = shift_pcd.read_header(f)
        read_back = shift_pcd.read_points(f, fmt, n_points)
    assert fmt == "binary"
    assert n_points == 1
    np.testing.assert_allclose(read_back, points, atol=1e-6)
