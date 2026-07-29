"""Tests for the Town10 pcd registration tools (Task 11 Step 1, amended
by S1 for the real bundle's layout).

Covers ``benchmarks/scripts/shift_pcd.py`` (rigid pcd shift across both
supported field layouts -- ``x y z intensity`` and ``x y z`` -- all
three ``DATA`` encodings -- ``ascii``, ``binary``, and
``binary_compressed`` -- plus the rejection paths for a header outside
that supported set) and the transform-and-downsample core of
``benchmarks/scripts/build_pcd_from_gt.py`` -- the CARLA client loop
around that core is not testable without a live simulator, so only the
plain-numpy core is exercised here. Both scripts share this one test file
because Task 11 Step 1's file scope lists a single test file to create.
"""

from __future__ import annotations

import hashlib
import io

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

# The real Town10 bundle's layout: x/y/z only, no intensity (verified
# on disk against ~/autoware_map/town10/pointcloud_map.pcd's header).
XYZ_HEADER = (
    "# .PCD v0.7 - Point Cloud Data file format\n"
    "VERSION 0.7\n"
    "FIELDS x y z\n"
    "SIZE 4 4 4\n"
    "TYPE F F F\n"
    "COUNT 1 1 1\n"
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
POINTS5_XYZ = POINTS5[:, :3].copy()


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


def _lzf_literal_compress(data: bytes) -> bytes:
    """Encode ``data`` as LZF using literal runs only (``ctrl = n - 1``
    for each <=32-byte chunk). Valid LZF framing that shares no logic
    with ``shift_pcd.lzf_decompress``'s back-reference handling, so a
    shared bug can't make a round trip look correct by accident."""
    out = bytearray()
    for i in range(0, len(data), 32):
        chunk = data[i : i + 32]
        out.append(len(chunk) - 1)
        out.extend(chunk)
    return bytes(out)


def _write_binary_compressed_pcd(
    path, header: str, points: np.ndarray, uncompressed_len: int | None = None
) -> None:
    """Write a ``DATA binary_compressed`` PCD: SoA (field-major) float32
    payload, LZF-encoded with literal runs only via
    :func:`_lzf_literal_compress`. ``uncompressed_len`` overrides the
    declared uncompressed byte count, to build a deliberately-wrong
    header for the mismatch test."""
    soa = points.astype(np.float32).T.copy()  # (n_fields, n_points), field-major
    raw = soa.tobytes()
    compressed = _lzf_literal_compress(raw)
    if uncompressed_len is None:
        uncompressed_len = len(raw)
    with open(path, "wb") as f:
        f.write(header.encode("ascii"))
        f.write(len(compressed).to_bytes(4, "little"))
        f.write(uncompressed_len.to_bytes(4, "little"))
        f.write(compressed)


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


def test_shift_binary_pcd_applies_dz_to_the_z_column_only(tmp_path):
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    _write_binary_pcd(src)

    shift_pcd.main(["--in", str(src), "--out", str(dst), "--dz", "2.0"])

    header_len = len(BINARY_HEADER.encode("ascii"))
    out_points = np.frombuffer(dst.read_bytes()[header_len:], dtype=np.float32).reshape(-1, 4)
    np.testing.assert_allclose(out_points[:, 2], POINTS5[:, 2] + 2.0, atol=1e-6)
    np.testing.assert_allclose(out_points[:, :2], POINTS5[:, :2], atol=1e-6)  # x/y untouched


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


# --- shift_pcd: xyz-only layout (the real Town10 bundle) ----------------------


def test_shift_xyz_only_binary_pcd_applies_the_shift_and_preserves_the_header(tmp_path):
    """The real Town10 bundle's layout: x/y/z only, no intensity."""
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    _write_binary_pcd(src, header=XYZ_HEADER, points=POINTS5_XYZ)

    rc = shift_pcd.main(["--in", str(src), "--out", str(dst), "--dx", "1.0", "--dy", "-0.475"])
    assert rc == 0

    header_bytes = XYZ_HEADER.encode("ascii")
    out_bytes = dst.read_bytes()
    assert out_bytes[: len(header_bytes)] == header_bytes  # byte-identical header

    out_points = np.frombuffer(out_bytes[len(header_bytes) :], dtype=np.float32).reshape(-1, 3)
    expected = POINTS5_XYZ.copy()
    expected[:, 0] += 1.0
    expected[:, 1] += -0.475
    np.testing.assert_allclose(out_points, expected, atol=1e-6)


# --- shift_pcd: binary_compressed round trip ----------------------------------


def test_shift_binary_compressed_pcd_round_trips_with_the_shift_applied(tmp_path):
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    header = BINARY_HEADER.replace("DATA binary\n", "DATA binary_compressed\n")
    _write_binary_compressed_pcd(src, header, POINTS5)

    rc = shift_pcd.main(["--in", str(src), "--out", str(dst), "--dx", "1.0", "--dy", "-0.475"])
    assert rc == 0

    out_header = header.replace("DATA binary_compressed\n", "DATA binary\n")
    out_header_bytes = out_header.encode("ascii")
    out_bytes = dst.read_bytes()
    # Only the DATA line changes; everything else stays byte-identical.
    assert out_bytes[: len(out_header_bytes)] == out_header_bytes

    out_points = np.frombuffer(out_bytes[len(out_header_bytes) :], dtype=np.float32).reshape(-1, 4)
    expected = POINTS5.copy()
    expected[:, 0] += 1.0
    expected[:, 1] += -0.475
    np.testing.assert_allclose(out_points, expected, atol=1e-6)


def test_shift_xyz_only_binary_compressed_pcd_matches_the_real_bundles_layout(tmp_path):
    """The exact combination the real Town10 bundle uses: ``FIELDS x y
    z`` (no intensity) plus ``DATA binary_compressed``."""
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    header = XYZ_HEADER.replace("DATA binary\n", "DATA binary_compressed\n")
    _write_binary_compressed_pcd(src, header, POINTS5_XYZ)

    rc = shift_pcd.main(["--in", str(src), "--out", str(dst), "--dy", "-0.475"])
    assert rc == 0

    out_header = header.replace("DATA binary_compressed\n", "DATA binary\n")
    out_header_bytes = out_header.encode("ascii")
    out_bytes = dst.read_bytes()
    assert out_bytes[: len(out_header_bytes)] == out_header_bytes

    out_points = np.frombuffer(out_bytes[len(out_header_bytes) :], dtype=np.float32).reshape(-1, 3)
    expected = POINTS5_XYZ.copy()
    expected[:, 1] += -0.475
    np.testing.assert_allclose(out_points, expected, atol=1e-6)


def test_read_points_binary_compressed_is_soa_not_interleaved():
    """Pins field-major (SoA) decoding: field 0 for every point, then
    field 1 for every point, etc. A reader that (wrongly) reshapes the
    decompressed payload as interleaved (AoS) float32 quads without
    transposing gets different -- and here, provably different --
    numbers, so this fails under that mutation."""
    soa = POINTS5.T.copy()  # (4, 5): all x, then all y, then all z, then all i
    raw = soa.tobytes()
    compressed = _lzf_literal_compress(raw)

    buf = io.BytesIO()
    buf.write(len(compressed).to_bytes(4, "little"))
    buf.write(len(raw).to_bytes(4, "little"))
    buf.write(compressed)
    buf.seek(0)

    decoded = shift_pcd.read_points(buf, "binary_compressed", n_points=5, n_fields=4)
    np.testing.assert_allclose(decoded, POINTS5, atol=1e-6)

    naive_aos = np.frombuffer(raw, dtype=np.float32).reshape(-1, 4)
    assert not np.allclose(decoded, naive_aos)  # SoA reading != naive AoS reinterpretation


def test_read_points_binary_rejects_a_truncated_payload(tmp_path):
    """A plain `DATA binary` file whose payload is short must be refused,
    not read as however many whole points it happens to contain: the
    header still declares POINTS 5, so the silent result is a map missing
    its tail that every consumer downstream treats as complete. This
    tool's own output is `DATA binary`, so a reproduction check of the
    shifted bundle re-reads through exactly this branch."""
    src = tmp_path / "in.pcd"
    with open(src, "wb") as f:
        f.write(BINARY_HEADER.encode("ascii"))
        f.write(POINTS5[:3].astype(np.float32).tobytes())  # 3 of the 5 points

    with open(src, "rb") as f:
        _, data_format, n_points, n_fields = shift_pcd.read_header(f)
        assert (data_format, n_points) == ("binary", 5)
        with pytest.raises(shift_pcd.PcdFormatError, match="mismatch"):
            shift_pcd.read_points(f, data_format, n_points, n_fields)


def test_main_refuses_a_truncated_binary_file_without_a_traceback(tmp_path, capsys):
    """The CLI path: refusal reaches the operator as a message and a
    non-zero exit code, the same way a corrupt compressed stream does."""
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    with open(src, "wb") as f:
        f.write(BINARY_HEADER.encode("ascii"))
        f.write(POINTS5[:3].astype(np.float32).tobytes())

    rc = shift_pcd.main(["--in", str(src), "--out", str(dst), "--dy", "-0.475"])
    assert rc == shift_pcd.EXIT_BAD_FORMAT
    assert "mismatch" in capsys.readouterr().err
    assert not dst.exists()


def test_read_points_binary_compressed_rejects_uncompressed_length_mismatch(tmp_path):
    src = tmp_path / "in.pcd"
    header = BINARY_HEADER.replace("DATA binary\n", "DATA binary_compressed\n")
    _write_binary_compressed_pcd(src, header, POINTS5, uncompressed_len=1)

    with open(src, "rb") as f:
        _, data_format, n_points, n_fields = shift_pcd.read_header(f)
        with pytest.raises(shift_pcd.PcdFormatError, match="mismatch"):
            shift_pcd.read_points(f, data_format, n_points, n_fields)


# --- shift_pcd: pure LZF decompressor -----------------------------------------


def test_lzf_decompress_handles_literal_runs():
    payload = bytes(range(50))  # forces two literal-run chunks (32 + 18 bytes)
    compressed = _lzf_literal_compress(payload)
    assert shift_pcd.lzf_decompress(compressed) == payload


def test_lzf_decompress_handles_an_overlapping_back_reference():
    """Hand-built LZF stream: a 2-byte literal run (``"AB"``) followed by
    an 8-byte back-reference with ``offset=1`` (2 bytes back). Since
    ``offset + 1`` (2) ``< length + 2`` (8), the source range overlaps
    the destination range still being written -- this is the case a
    slice-based (rather than byte-by-byte) copy gets wrong."""
    literal = bytes([1]) + b"AB"  # ctrl=1 -> 2 literal bytes "AB"
    back_ref = bytes([6 << 5, 1])  # length field=6 -> copy 8 bytes, offset=1
    compressed = literal + back_ref

    assert shift_pcd.lzf_decompress(compressed) == b"ABABABABAB"  # "AB" x 5


def test_lzf_decompress_handles_the_length_extension_byte():
    """Hand-built LZF stream exercising ``ctrl >> 5 == 7``, the case
    where an extra byte extends ``length`` before the offset byte is
    even read. Every round-trip fixture in this file goes through
    ``_lzf_literal_compress`` (literal runs only) or the plain overlap
    test above (``length field=6``, deliberately avoiding 7), so this
    branch had no coverage even though real PCL output over a
    multi-megabyte cloud hits it constantly.

    Layout: a 2-byte literal run (``"AB"``), then a back-reference with
    ``length_field=7`` (extended by the next byte, ``3``, to 10) and
    ``offset=1``. Verified by hand, not just by trusting the numbers:
    ``ctrl = 7 << 5 = 224``; ``224 >> 5 = 7`` so the extension byte
    (``3``) applies, giving ``length = 10``; ``offset = ((224 & 0x1f)
    << 8) | 1 = (0 << 8) | 1 = 1``; ``ref = len(out) - offset - 1 = 2 -
    1 - 1 = 0``, so the back-reference copies ``length + 2 = 12`` bytes
    starting at index 0 while ``out`` is still only 2 bytes long -- the
    same overlapping self-reference as the other back-reference test,
    just long enough to require the length-extension byte. Result:
    ``"AB"`` (2 bytes) + ``"AB"`` repeated 6 more times (12 bytes) =
    ``"AB"`` x 7 (14 bytes)."""
    literal = bytes([1]) + b"AB"  # ctrl=1 -> 2 literal bytes "AB"
    back_ref = bytes([7 << 5, 3, 1])  # length field=7, +3 -> 10; offset=1
    compressed = literal + back_ref

    assert shift_pcd.lzf_decompress(compressed) == b"AB" * 7


def test_lzf_decompress_rejects_a_back_reference_that_points_before_the_start():
    """A back-reference whose offset reaches past everything
    decompressed so far must not silently wrap via Python's negative
    indexing (``out[-1]`` is the *last* byte, not "out of bounds") --
    that would produce plausible-looking bytes of the right length
    that sail straight through the length check in ``read_points``,
    exactly the "parses fine, geometrically nonsense" failure mode the
    module docstring says this tool refuses."""
    compressed = bytes([32, 0])  # ctrl=32 -> back-ref, length=1, offset=0
    with pytest.raises(shift_pcd.PcdFormatError, match="offset"):
        shift_pcd.lzf_decompress(compressed)


@pytest.mark.parametrize(
    "compressed",
    [
        bytes([32]),  # ctrl -> back-ref, but no offset byte follows
        bytes([7 << 5]),  # ctrl -> length==7, but no extension byte follows
    ],
    ids=["missing_offset_byte", "missing_length_extension_byte"],
)
def test_lzf_decompress_rejects_a_stream_truncated_mid_token(compressed):
    """A stream that runs out of bytes partway through a back-reference
    token must raise ``PcdFormatError`` -- this tool's loud-refusal
    contract -- rather than leak a bare ``IndexError`` past callers
    that only catch ``PcdFormatError`` (see
    ``test_main_refuses_a_corrupt_binary_compressed_stream_without_a_traceback``
    for that at the ``main()`` level)."""
    with pytest.raises(shift_pcd.PcdFormatError, match="truncated"):
        shift_pcd.lzf_decompress(compressed)


def test_main_refuses_a_corrupt_binary_compressed_stream_without_a_traceback(tmp_path, capsys):
    """Regression: a truncated ``binary_compressed`` payload used to
    escape ``main()``'s ``except PcdFormatError`` as a bare
    ``IndexError``, printing a traceback instead of the usual
    ``shift_pcd: refusing ...`` message."""
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    header = BINARY_HEADER.replace("DATA binary\n", "DATA binary_compressed\n")
    truncated = bytes([32])  # a back-reference ctrl byte, then nothing
    with open(src, "wb") as f:
        f.write(header.encode("ascii"))
        f.write(len(truncated).to_bytes(4, "little"))
        f.write((999).to_bytes(4, "little"))  # uncompressed_len, irrelevant here
        f.write(truncated)

    rc = shift_pcd.main(["--in", str(src), "--out", str(dst)])

    assert rc != 0
    assert "shift_pcd: refusing" in capsys.readouterr().err
    assert not dst.exists()


# --- shift_pcd: provenance ---------------------------------------------------


def test_shift_prints_sha256_of_input_and_output(tmp_path, capsys):
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    _write_binary_pcd(src)

    shift_pcd.main(["--in", str(src), "--out", str(dst), "--dy", "-0.475"])

    printed = capsys.readouterr().out
    assert hashlib.sha256(src.read_bytes()).hexdigest() in printed
    assert hashlib.sha256(dst.read_bytes()).hexdigest() in printed


# --- shift_pcd: rejection paths -----------------------------------------------


def test_rejects_a_fields_combination_outside_the_two_supported_layouts(tmp_path):
    """Neither of the two supported layouts (``x y z`` / ``x y z
    intensity``) -- e.g. a 2-field header -- must still be refused."""
    src = tmp_path / "in.pcd"
    header = (
        BINARY_HEADER.replace("FIELDS x y z intensity\n", "FIELDS x y\n")
        .replace("SIZE 4 4 4 4\n", "SIZE 4 4\n")
        .replace("TYPE F F F F\n", "TYPE F F\n")
        .replace("COUNT 1 1 1 1\n", "COUNT 1 1\n")
    )
    _write_binary_pcd(src, header=header, points=POINTS5[:, :2])
    with open(src, "rb") as f, pytest.raises(shift_pcd.PcdFormatError, match="FIELDS 'x y'"):
        shift_pcd.read_header(f)


def test_rejects_wrong_size(tmp_path):
    src = tmp_path / "in.pcd"
    _write_binary_pcd(src, header=BINARY_HEADER.replace("SIZE 4 4 4 4\n", "SIZE 8 8 8 8\n"))
    with open(src, "rb") as f, pytest.raises(shift_pcd.PcdFormatError, match="SIZE '8 8 8 8'"):
        shift_pcd.read_header(f)


def test_rejects_wrong_type(tmp_path):
    src = tmp_path / "in.pcd"
    _write_binary_pcd(src, header=BINARY_HEADER.replace("TYPE F F F F\n", "TYPE U U U U\n"))
    with open(src, "rb") as f, pytest.raises(shift_pcd.PcdFormatError, match="TYPE 'U U U U'"):
        shift_pcd.read_header(f)


def test_rejects_count_not_all_ones(tmp_path):
    """COUNT must be checked, not ignored: a non-``1`` COUNT is not the
    flat one-scalar-per-point-per-field layout this tool assumes, even
    though FIELDS/SIZE/TYPE otherwise match a supported layout."""
    src = tmp_path / "in.pcd"
    _write_binary_pcd(src, header=BINARY_HEADER.replace("COUNT 1 1 1 1\n", "COUNT 1 1 1 2\n"))
    with open(src, "rb") as f, pytest.raises(shift_pcd.PcdFormatError, match="COUNT"):
        shift_pcd.read_header(f)


def test_rejects_an_unsupported_data_format(tmp_path):
    src = tmp_path / "in.pcd"
    _write_binary_pcd(src, header=BINARY_HEADER.replace("DATA binary\n", "DATA xdr\n"))
    with open(src, "rb") as f, pytest.raises(shift_pcd.PcdFormatError, match="DATA"):
        shift_pcd.read_header(f)


def test_main_refuses_a_malformed_input_and_does_not_write_output(tmp_path, capsys):
    src, dst = tmp_path / "in.pcd", tmp_path / "out.pcd"
    header = BINARY_HEADER.replace("COUNT 1 1 1 1\n", "COUNT 1 1 1 2\n")
    _write_binary_pcd(src, header=header)

    rc = shift_pcd.main(["--in", str(src), "--out", str(dst), "--dy", "-0.475"])

    assert rc != 0
    assert "COUNT" in capsys.readouterr().err
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


def _rotation_from_elementary_matrices(
    roll_deg: float, pitch_deg: float, yaw_deg: float
) -> np.ndarray:
    """Independent reference rotation, built from first principles.

    Composes the standard right-handed elementary rotation matrices about
    X (roll), Y (pitch), and Z (yaw) as ``Rz(yaw) @ Ry(pitch) @ Rx(roll)``
    -- roll applied first, then pitch, then yaw, CARLA/UE's Euler order.
    This is assembled from separate 3x3 blocks, deliberately not sharing
    a code path with ``sensor_pose_matrix``'s combined closed-form terms,
    so it can catch a sign error in that closed form rather than just
    restating it.
    """
    r, p, y = np.radians(roll_deg), np.radians(pitch_deg), np.radians(yaw_deg)
    cr, sr = np.cos(r), np.sin(r)
    cp, sp = np.cos(p), np.sin(p)
    cy, sy = np.cos(y), np.sin(y)
    rot_x = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    rot_y = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]])
    rot_z = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    return rot_z @ rot_y @ rot_x


def test_sensor_pose_matrix_matches_independent_rotation_at_nonzero_roll():
    m = build_pcd_from_gt.sensor_pose_matrix(0.0, 0.0, 0.0, 30.0, 0.0, 0.0)
    expected = _rotation_from_elementary_matrices(30.0, 0.0, 0.0)
    np.testing.assert_allclose(m[:3, :3], expected, atol=1e-9)


def test_sensor_pose_matrix_matches_independent_rotation_at_nonzero_pitch():
    m = build_pcd_from_gt.sensor_pose_matrix(0.0, 0.0, 0.0, 0.0, 40.0, 0.0)
    expected = _rotation_from_elementary_matrices(0.0, 40.0, 0.0)
    np.testing.assert_allclose(m[:3, :3], expected, atol=1e-9)


@pytest.mark.parametrize(
    "roll_deg, pitch_deg, yaw_deg",
    [
        (15.0, -25.0, 50.0),
        (-40.0, 10.0, -120.0),
        (90.0, 45.0, -30.0),
    ],
)
def test_sensor_pose_matrix_matches_independent_rotation_combined_roll_pitch_yaw(
    roll_deg, pitch_deg, yaw_deg
):
    m = build_pcd_from_gt.sensor_pose_matrix(1.0, -2.0, 3.5, roll_deg, pitch_deg, yaw_deg)
    expected = _rotation_from_elementary_matrices(roll_deg, pitch_deg, yaw_deg)
    np.testing.assert_allclose(m[:3, :3], expected, atol=1e-9)
    np.testing.assert_allclose(
        m[:3, 3], [1.0, -2.0, 3.5], atol=1e-9
    )  # translation untouched by the fix


def test_transform_cloud_to_map_reuses_the_pinned_converter_not_a_local_copy():
    """The brief's hard requirement: the CARLA-world -> map-frame conversion
    must come from ``scripts.e2e.verify_mgrs_handedness`` -- the single
    pinned source shared with the extension's ``MgrsOffset.h`` -- and not
    be re-derived a third time."""
    assert build_pcd_from_gt.world_m_to_mgrs_local is mgrs.world_m_to_mgrs_local


def test_transform_cloud_to_map_applies_pose_then_the_pinned_mgrs_offset():
    """Uses a tilted pose (nonzero roll/pitch/yaw), not translation-only,
    so this integration-style test also exercises ``sensor_pose_matrix``'s
    rotation -- a translation-only pose can't tell a correct rotation
    matrix from a wrong one. The expected world point is derived
    independently via ``_rotation_from_elementary_matrices`` rather than
    by calling ``sensor_pose_matrix`` itself."""
    offset = mgrs.MAP_OFFSETS["Town10HD_Opt"]  # (0, 0, 0): Town10's registered offset
    local_xyz = np.array([1.0, 2.0, 3.0])
    local = np.array([[*local_xyz, 0.5]])
    pose = (10.0, 5.0, 2.0, 15.0, -25.0, 50.0)  # roll, pitch, yaw all nonzero

    mapped = build_pcd_from_gt.transform_cloud_to_map(local, pose, offset)

    rotation = _rotation_from_elementary_matrices(15.0, -25.0, 50.0)
    world = rotation @ local_xyz + np.array([10.0, 5.0, 2.0])
    # map = (world_x, -world_y, world_z) on the pinned Y flip.
    expected = np.array([[world[0], -world[1], world[2], 0.5]])
    np.testing.assert_allclose(mapped, expected, atol=1e-6)


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
        header_lines, fmt, n_points, n_fields = shift_pcd.read_header(f)
        read_back = shift_pcd.read_points(f, fmt, n_points, n_fields)
    assert fmt == "binary"
    assert n_points == 1
    assert n_fields == 4
    np.testing.assert_allclose(read_back, points, atol=1e-6)
