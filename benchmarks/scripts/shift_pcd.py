#!/usr/bin/env python3
"""Rigid-shift a PCD file (x/y/z, with or without intensity, float32).

Provenance tool for the Town10 map-bundle registration fix: the P1 seed
sweep localized a +0.475 m cross-track offset to the pcd. Usage:

    python3 shift_pcd.py --in a.pcd --out b.pcd --dy -0.475

Writes the same header (POINTS/WIDTH preserved verbatim) with shifted
point data and prints the sha256 of both files, in a form meant to be
pasted straight into ``benchmarks/pins.yaml``.

Layout: this tool supports exactly TWO PCD point layouts -- ``FIELDS x y
z intensity`` / ``SIZE 4 4 4 4`` / ``TYPE F F F F`` and ``FIELDS x y z``
/ ``SIZE 4 4 4`` / ``TYPE F F F`` (the real Town10 bundle's layout, no
intensity) -- both with ``COUNT`` all-``1`` (one scalar per point per
field; anything else is not the flat layout this tool assumes). Any
other FIELDS/SIZE/TYPE/COUNT combination is refused loudly
(``PcdFormatError``) rather than silently reinterpreted: a wrong FIELDS
count would silently misalign every point in the map if accepted and
processed anyway.

``DATA`` may be ``ascii``, ``binary``, or ``binary_compressed`` (PCL's
LZF-compressed framing, decompressed here with a pure-Python
implementation -- see :func:`lzf_decompress` -- since neither an ``lzf``
package nor an LZF *compressor* is available under this repo's
no-new-dependencies rule). Output is always written as uncompressed
``DATA binary``: when the input was ``binary_compressed``, the output
header is the input header with *only* the ``DATA`` line rewritten to
``binary``, every other header line byte-identical, and the point data
re-encoded uncompressed. That is why a shifted output file is larger
than a ``binary_compressed`` input (e.g. Town10's ~110 MB compressed
bundle becomes ~120 MB uncompressed): the tool never re-compresses.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys

import numpy as np

# (FIELDS, SIZE, TYPE) -> field count, for the flat layouts this tool
# supports. COUNT is checked separately against this field count.
SUPPORTED_LAYOUTS: dict[tuple[str, str, str], int] = {
    ("x y z intensity", "4 4 4 4", "F F F F"): 4,
    ("x y z", "4 4 4", "F F F"): 3,
}
REQUIRED_FIELDS = "x y z intensity"
REQUIRED_SIZE = "4 4 4 4"
REQUIRED_TYPE = "F F F F"
SUPPORTED_DATA_FORMATS = ("ascii", "binary", "binary_compressed")

EXIT_BAD_FORMAT = 1


class PcdFormatError(ValueError):
    """A .pcd header does not match a layout this tool supports."""


def _header_value(lines: list[str], key: str) -> str:
    for line in lines:
        if line.startswith(key + " "):
            return line[len(key) + 1 :].strip()
    raise PcdFormatError(f"missing {key!r} header line")


def read_header(f) -> tuple[list[str], str, int, int]:
    """Read PCD header lines (binary file object) up to and including DATA.

    Returns ``(header_lines, data_format, n_points, n_fields)``. FIELDS/
    SIZE/TYPE must match one of :data:`SUPPORTED_LAYOUTS`'s flat x/y/z(/
    intensity) layouts, and COUNT must be all-``1`` for that same field
    count (one scalar per point per field -- the flat layout this tool
    assumes; anything else, e.g. a run-length-style COUNT, is refused
    rather than ignored). DATA must be one of
    :data:`SUPPORTED_DATA_FORMATS` -- in particular ``binary_compressed``
    is accepted and decompressed (see :func:`lzf_decompress`), not
    misread as raw float32.
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
    count = _header_value(header_lines, "COUNT")

    n_fields = SUPPORTED_LAYOUTS.get((fields, size, type_))
    if n_fields is None:
        raise PcdFormatError(
            f"unsupported FIELDS/SIZE/TYPE combination: FIELDS {fields!r} "
            f"SIZE {size!r} TYPE {type_!r}"
        )
    expected_count = " ".join(["1"] * n_fields)
    if count != expected_count:
        raise PcdFormatError(
            f"unsupported COUNT {count!r}, expected {expected_count!r} for "
            "a flat (one scalar per point per field) layout"
        )

    data_format = header_lines[-1].split()[1].strip()
    if data_format not in SUPPORTED_DATA_FORMATS:
        raise PcdFormatError(
            f"unsupported DATA {data_format!r}; only {SUPPORTED_DATA_FORMATS} are handled"
        )

    n_points = int(_header_value(header_lines, "POINTS"))
    return header_lines, data_format, n_points, n_fields


def lzf_decompress(data: bytes) -> bytes:
    """Decompress ``data`` per PCL's LZF framing (liblzf-compatible).

    Pure Python -- there is no ``lzf`` package in this venv and pulling
    one in would violate this repo's no-new-dependencies rule for PCD
    I/O. Reads control bytes until ``data`` is exhausted:

    - ``ctrl < 32``: a literal run -- copy the next ``ctrl + 1`` bytes.
    - otherwise: a back-reference -- ``length = ctrl >> 5``; if that is
      7, one more byte extends it; then one more byte ``b`` gives
      ``offset = ((ctrl & 0x1f) << 8) | b``. The copy source starts at
      ``out_pos - offset - 1`` and runs for ``length + 2`` bytes.

    Back-reference copies are done byte-by-byte, not by slicing: the
    source and destination ranges legitimately overlap (a short pattern
    repeated by referencing back into bytes the same copy is still
    writing), and a slice taken up front would freeze stale bytes
    instead of picking up ones just written.

    A corrupt or truncated stream is refused with ``PcdFormatError``
    rather than left to Python's own errors or silent misbehaviour: a
    back-reference offset reaching past everything decompressed so far
    would otherwise wrap via negative indexing and silently produce
    plausible-looking (but wrong) bytes of the expected length, and a
    stream that runs out mid-token would otherwise raise a bare
    ``IndexError`` that callers catching only ``PcdFormatError`` (e.g.
    ``main``) do not expect.
    """
    out = bytearray()
    i = 0
    n = len(data)
    try:
        while i < n:
            ctrl = data[i]
            i += 1
            if ctrl < 32:
                length = ctrl + 1
                out.extend(data[i : i + length])
                i += length
            else:
                length = ctrl >> 5
                if length == 7:
                    length += data[i]
                    i += 1
                offset = ((ctrl & 0x1F) << 8) | data[i]
                i += 1
                ref = len(out) - offset - 1
                if ref < 0:
                    raise PcdFormatError(
                        f"corrupt binary_compressed stream: back-reference "
                        f"offset {offset} reaches past the "
                        f"{len(out)} byte(s) decompressed so far"
                    )
                for _ in range(length + 2):
                    out.append(out[ref])
                    ref += 1
    except IndexError as e:
        raise PcdFormatError(
            "corrupt or truncated binary_compressed stream: ran out of compressed bytes mid-token"
        ) from e
    return bytes(out)


def read_points(f, data_format: str, n_points: int, n_fields: int) -> np.ndarray:
    """Read ``n_points`` rows of ``n_fields`` float32 columns following
    the header, for any of :data:`SUPPORTED_DATA_FORMATS`."""
    if data_format == "binary":
        raw = f.read(n_points * n_fields * 4)  # float32 fields, 4 bytes each
        return np.frombuffer(raw, dtype=np.float32).reshape(-1, n_fields)
    if data_format == "binary_compressed":
        compressed_len = int.from_bytes(f.read(4), "little")
        uncompressed_len = int.from_bytes(f.read(4), "little")
        compressed = f.read(compressed_len)
        decompressed = lzf_decompress(compressed)
        expected_len = n_points * n_fields * 4
        if len(decompressed) != uncompressed_len or len(decompressed) != expected_len:
            raise PcdFormatError(
                f"binary_compressed payload length mismatch: decompressed "
                f"{len(decompressed)} bytes, header uncompressed count says "
                f"{uncompressed_len}, expected {expected_len} for {n_points} "
                f"points x {n_fields} fields x 4 bytes"
            )
        # PCL's binary_compressed payload is field-major (SoA): every
        # point's field 0, then every point's field 1, ... i.e. shape
        # (n_fields, n_points) -- the transpose of the interleaved (AoS)
        # layout `binary` uses. Getting this backwards parses cleanly
        # but silently scrambles every point.
        soa = np.frombuffer(decompressed, dtype=np.float32).reshape(n_fields, n_points)
        return soa.T.copy()
    text = f.read()
    if isinstance(text, bytes):
        text = text.decode("ascii")
    return np.loadtxt(io.StringIO(text), dtype=np.float64).reshape(-1, n_fields)


def shift_points(points: np.ndarray, dx: float, dy: float, dz: float) -> np.ndarray:
    """Rigid-translate x/y/z (columns 0/1/2); any further column (e.g.
    intensity, column 3) is untouched, whatever the field count."""
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


def with_data_format(header_lines: list[str], data_format: str) -> list[str]:
    """Return ``header_lines`` with only the ``DATA`` line replaced --
    every other line stays byte-identical to the input. Used to downgrade
    a ``binary_compressed`` input header to ``binary`` on output, since
    this tool never writes a compressed payload back out."""
    return [f"DATA {data_format}\n" if line.startswith("DATA") else line for line in header_lines]


def write_pcd(path, header_lines: list[str], points: np.ndarray, data_format: str) -> None:
    """Write ``header_lines`` verbatim, followed by ``points`` in
    ``data_format`` (``ascii`` or uncompressed ``binary``). Shared by
    this module's CLI and ``build_pcd_from_gt.py``, so both tools emit
    identically-shaped PCD files for the data they produce."""
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
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--in", dest="in_path", required=True, help="input .pcd path")
    p.add_argument("--out", dest="out_path", required=True, help="output .pcd path")
    p.add_argument("--dx", type=float, default=0.0, help="shift along x, metres")
    p.add_argument("--dy", type=float, default=0.0, help="shift along y, metres")
    p.add_argument("--dz", type=float, default=0.0, help="shift along z, metres")
    args = p.parse_args(argv)

    try:
        with open(args.in_path, "rb") as f:
            header_lines, data_format, n_points, n_fields = read_header(f)
            points = read_points(f, data_format, n_points, n_fields)
    except PcdFormatError as e:
        print(f"shift_pcd: refusing {args.in_path}: {e}", file=sys.stderr)
        return EXIT_BAD_FORMAT

    shifted = shift_points(points, args.dx, args.dy, args.dz)

    if data_format == "binary_compressed":
        # No LZF compressor is available (no-new-deps rule); write the
        # shifted data back out uncompressed instead of re-compressing.
        out_header, out_format = with_data_format(header_lines, "binary"), "binary"
    else:
        out_header, out_format = header_lines, data_format
    write_pcd(args.out_path, out_header, shifted, out_format)

    print(f"in  sha256={sha256_file(args.in_path)}  {args.in_path}")
    print(f"out sha256={sha256_file(args.out_path)}  {args.out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
