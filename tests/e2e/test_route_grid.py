"""Unit tests for route_grid.grid_from_polyline -- the bbox-midpoint /
bbox-diagonal-plus-margin arithmetic arm_closed_loop.sh's ROUTE_FILE path
feeds to dummy_perception.py's --grid-center/--grid-size.

This is pure arithmetic (no yaml/carla/rclpy involved), so every case here
runs under bare pytest with no fixtures needed -- the same style as
tests/benchmarks/test_pick_route.py's coverage of pick_route.py's core.
"""

from __future__ import annotations

import math

import pytest

from scripts.e2e.route_grid import grid_from_polyline


def test_bbox_midpoint_and_diagonal_plus_margin():
    # bbox: x in [0, 100], y in [0, 50] -> midpoint (50, 25), diagonal
    # sqrt(100^2 + 50^2) = sqrt(12500) = 111.803..., + 100 m margin.
    polyline = [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]
    cx, cy, size = grid_from_polyline(polyline, margin_m=100.0)
    assert (cx, cy) == pytest.approx((50.0, 25.0))
    assert size == pytest.approx(math.hypot(100.0, 50.0) + 100.0)


def test_margin_is_added_on_top_of_the_diagonal():
    polyline = [(0.0, 0.0), (10.0, 0.0)]  # bbox diagonal = 10
    _, _, size_small_margin = grid_from_polyline(polyline, margin_m=0.0)
    _, _, size_large_margin = grid_from_polyline(polyline, margin_m=50.0)
    assert size_small_margin == pytest.approx(10.0)
    assert size_large_margin == pytest.approx(60.0)


def test_single_point_polyline_degenerates_to_zero_diagonal():
    """A one-point polyline has a zero-area bbox, so size must be exactly
    the margin -- not zero, not an error."""
    polyline = [(42.0, -7.0)]
    cx, cy, size = grid_from_polyline(polyline, margin_m=100.0)
    assert (cx, cy) == pytest.approx((42.0, -7.0))
    assert size == pytest.approx(100.0)


def test_straight_line_polyline_has_one_zero_bbox_dimension():
    """A polyline that never moves in y has bbox height 0; the diagonal
    formula must reduce to the x-extent alone, not blow up or drop it."""
    polyline = [(0.0, 5.0), (20.0, 5.0), (40.0, 5.0)]
    cx, cy, size = grid_from_polyline(polyline, margin_m=100.0)
    assert (cx, cy) == pytest.approx((20.0, 5.0))
    assert size == pytest.approx(40.0 + 100.0)  # diagonal == x-extent == 40


def test_vertical_straight_line_polyline_has_zero_x_extent():
    polyline = [(3.0, 0.0), (3.0, 30.0)]
    cx, cy, size = grid_from_polyline(polyline, margin_m=100.0)
    assert (cx, cy) == pytest.approx((3.0, 15.0))
    assert size == pytest.approx(30.0 + 100.0)
