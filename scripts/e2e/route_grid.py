#!/usr/bin/env python3
"""Free-space occupancy-grid centre/size for a route file's bounding box.

``arm_closed_loop.sh``'s ROUTE_FILE path (Step 3, dummy_perception.py's
``--grid-center``/``--grid-size``) needs a centre and size that cover the
driven corridor, derived from a committed route YAML
(``benchmarks/scripts/pick_route.py``'s schema: a ``polyline`` list of
map-frame ``[x, y]`` pairs). This is the pure Tier-1 arithmetic behind that --
bbox midpoint, size = bbox diagonal + margin -- extracted so it is
unit-tested (``tests/e2e/test_route_grid.py``) instead of verified only by
hand inside a shell heredoc, which is exactly the "silent wrong number" class
of defect this campaign's Tier-1 fixes exist to close.

Invoked from ``arm_closed_loop.sh`` as:

    python3 -m scripts.e2e.route_grid "$ROUTE_FILE"

printing ``"<centre_x> <centre_y> <size>"`` on stdout, matching the shell's
existing ``GRID_X GRID_Y GRID_SIZE`` word-split convention.
"""

from __future__ import annotations

import argparse
import math
import sys

import yaml

XY = tuple[float, float]

DEFAULT_MARGIN_M = 100.0


def grid_from_polyline(polyline: list[XY], margin_m: float = DEFAULT_MARGIN_M) -> tuple[float, float, float]:
    """(centre_x, centre_y, size) covering a route polyline's bounding box.

    centre is the bbox midpoint; size is the bbox diagonal plus margin_m, so
    the free-space grid dummy_perception.py publishes still reaches past the
    route ends on every side (the grid is a square "clear road" area, not a
    corridor mask -- it only has to cover the driven area, not trace it
    tightly).

    Degenerate inputs are handled by the same formula, not a special case: a
    single-point polyline has a zero-area bbox (diagonal 0), so size ==
    margin_m exactly; a polyline that is a straight line on one axis (e.g.
    every y identical) has zero width on that axis, and math.hypot with one
    argument 0 already reduces to the other axis's extent.
    """
    xs = [p[0] for p in polyline]
    ys = [p[1] for p in polyline]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    diagonal = math.hypot(maxx - minx, maxy - miny)
    return cx, cy, diagonal + margin_m


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("route_file", help="route YAML (benchmarks/scripts/pick_route.py schema)")
    ap.add_argument("--margin-m", type=float, default=DEFAULT_MARGIN_M)
    args = ap.parse_args(argv)
    with open(args.route_file) as f:
        route = yaml.safe_load(f)
    cx, cy, size = grid_from_polyline(route["polyline"], args.margin_m)
    print(f"{cx:.3f} {cy:.3f} {size:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
