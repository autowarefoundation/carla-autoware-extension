#!/usr/bin/env python3
"""Rigid-shift a PCD file (binary or ascii, x/y/z/intensity float32).

Provenance tool for the Town10 map-bundle registration fix: the P1 seed
sweep localized a +0.475 m cross-track offset to the pcd. Usage:

    python3 shift_pcd.py --in a.pcd --out b.pcd --dy -0.475

Writes the same header (POINTS/WIDTH preserved verbatim) with shifted
point data and prints the sha256 of both files, in a form meant to be
pasted straight into ``benchmarks/pins.yaml``.

Layout: this tool supports exactly ONE PCD layout -- ``FIELDS x y z
intensity``, ``SIZE 4 4 4 4``, ``TYPE F F F F``, and ``DATA`` either
``ascii`` or (uncompressed) ``binary``. Anything else is refused loudly
(``PcdFormatError``) rather than silently reinterpreted: a wrong FIELDS
count or an unhandled ``binary_compressed`` payload would silently
misalign every point in the map if accepted and processed anyway.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys

import numpy as np

REQUIRED_FIELDS = "x y z intensity"
REQUIRED_SIZE = "4 4 4 4"
REQUIRED_TYPE = "F F F F"
SUPPORTED_DATA_FORMATS = ("ascii", "binary")

EXIT_BAD_FORMAT = 1


class PcdFormatError(ValueError):
    """A .pcd header does not match the one layout this tool supports."""


def _header_value(lines: list[str], key: str) -> str:
    for line in lines:
        if line.startswith(key + " "):
            return line[len(key) + 1 :].strip()
    raise PcdFormatError(f"missing {key!r} header line")


def read_header(f) -> tuple[list[str], str, int]:
    """Read PCD header lines (binary file object) up to and including DATA.

    Returns ``(header_lines, data_format, n_points)``. Validates FIELDS,
    SIZE, and TYPE against :data:`REQUIRED_FIELDS`/:data:`REQUIRED_SIZE`/
    :data:`REQUIRED_TYPE`, and DATA against :data:`SUPPORTED_DATA_FORMATS`
    -- in particular this rejects ``binary_compressed`` (LZF-compressed,
    a different byte layout entirely) even when the fields happen to
    already match, since reading it as raw float32 would corrupt the map.
    """
    header_lines: list[str] = []
    while True:
        raw = f.readline()
        if not raw:
            raise PcdFormatError("unexpected end of file before a DATA line")
        header_lines.append(raw.decode("ascii"))
        if header_lines[-1].startswith("DATA"):
            break

    fields = _header_value(header_lines, "FIELDS")
    size = _header_value(header_lines, "SIZE")
    type_ = _header_value(header_lines, "TYPE")
    if fields != REQUIRED_FIELDS:
        raise PcdFormatError(f"unsupported FIELDS {fields!r}, expected {REQUIRED_FIELDS!r}")
    if size != REQUIRED_SIZE:
        raise PcdFormatError(f"unsupported SIZE {size!r}, expected {REQUIRED_SIZE!r}")
    if type_ != REQUIRED_TYPE:
        raise PcdFormatError(f"unsupported TYPE {type_!r}, expected {REQUIRED_TYPE!r}")

    data_format = header_lines[-1].split()[1].strip()
    if data_format not in SUPPORTED_DATA_FORMATS:
        raise PcdFormatError(
            f"unsupported DATA {data_format!r}; only {SUPPORTED_DATA_FORMATS} are "
            "handled (binary_compressed is LZF-compressed and would be "
            "misread as raw float32 if processed as-is)"
        )

    n_points = int(_header_value(header_lines, "POINTS"))
    return header_lines, data_format, n_points


def read_points(f, data_format: str, n_points: int) -> np.ndarray:
    """Read ``n_points`` x/y/z/intensity rows following the header."""
    if data_format == "binary":
        raw = f.read(n_points * 4 * 4)  # 4 float32 fields, 4 bytes each
        return np.frombuffer(raw, dtype=np.float32).reshape(-1, 4)
    text = f.read()
    if isinstance(text, bytes):
        text = text.decode("ascii")
    return np.loadtxt(io.StringIO(text), dtype=np.float64).reshape(-1, 4)


def shift_points(points: np.ndarray, dx: float, dy: float, dz: float) -> np.ndarray:
    """Rigid-translate x/y/z; the intensity column (index 3) is untouched."""
    shifted = points.copy()
    shifted[:, 0] += dx
    shifted[:, 1] += dy
    shifted[:, 2] += dz
    return shifted


def make_header(n_points: int) -> list[str]:
    """Build a fresh binary-format PCD header for ``n_points`` xyz/intensity
    points. Used by ``build_pcd_from_gt.py``, which writes a new file from
    scratch rather than shifting an existing one."""
    return [
        "# .PCD v0.7 - Point Cloud Data file format\n",
        "VERSION 0.7\n",
        f"FIELDS {REQUIRED_FIELDS}\n",
        f"SIZE {REQUIRED_SIZE}\n",
        f"TYPE {REQUIRED_TYPE}\n",
        "COUNT 1 1 1 1\n",
        f"WIDTH {n_points}\n",
        "HEIGHT 1\n",
        "VIEWPOINT 0 0 0 1 0 0 0\n",
        f"POINTS {n_points}\n",
        "DATA binary\n",
    ]


def write_pcd(path, header_lines: list[str], points: np.ndarray, data_format: str) -> None:
    """Write ``header_lines`` verbatim, followed by ``points`` in
    ``data_format``. Shared by this module's CLI and
    ``build_pcd_from_gt.py``, so both tools emit identically-shaped PCD
    files for the data they produce."""
    with open(path, "wb") as f:
        f.write("".join(header_lines).encode("ascii"))
        if data_format == "binary":
            f.write(points.astype(np.float32).tobytes())
        else:
            np.savetxt(f, points, fmt="%.6f")


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="in_path", required=True, help="input .pcd path")
    p.add_argument("--out", dest="out_path", required=True, help="output .pcd path")
    p.add_argument("--dx", type=float, default=0.0, help="shift along x, metres")
    p.add_argument("--dy", type=float, default=0.0, help="shift along y, metres")
    p.add_argument("--dz", type=float, default=0.0, help="shift along z, metres")
    args = p.parse_args(argv)

    try:
        with open(args.in_path, "rb") as f:
            header_lines, data_format, n_points = read_header(f)
            points = read_points(f, data_format, n_points)
    except PcdFormatError as e:
        print(f"shift_pcd: refusing {args.in_path}: {e}", file=sys.stderr)
        return EXIT_BAD_FORMAT

    shifted = shift_points(points, args.dx, args.dy, args.dz)
    write_pcd(args.out_path, header_lines, shifted, data_format)

    print(f"in  sha256={sha256_file(args.in_path)}  {args.in_path}")
    print(f"out sha256={sha256_file(args.out_path)}  {args.out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
