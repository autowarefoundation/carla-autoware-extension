"""Unit tests for the map-offset derivation (``scripts.e2e.fit_map_offset``).

Pure-Python/numpy only: ``carla`` is imported lazily inside
``carla_lane_boundary_points``, so everything asserted here collects and runs
under a bare ``python3 -m pytest`` with no CARLA egg, which is how CI runs it.

The tests drive the fit against a SYNTHETIC road network whose true offset is
known by construction, which is what makes them a check of the estimator rather
than a restatement of the recorded Town10 number.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.e2e import fit_map_offset
from scripts.e2e.fit_map_offset import (
    apply_affine,
    fit_translation,
    nearest_on_segments,
    parse_osm_polylines,
    polylines_to_segments,
)

# A tiny two-way "network": one horizontal and one vertical boundary line.
_WAYS = [
    np.array([[0.0, 0.0], [100.0, 0.0]]),
    np.array([[0.0, 0.0], [0.0, 100.0]]),
]


def _osm(tmp_path, nodes, ways):
    """Write a minimal lanelet2-shaped .osm; nodes are (id, local_x, local_y)."""
    parts = ["<?xml version='1.0' encoding='UTF-8'?>", "<osm version='0.6'>"]
    for node_id, x, y in nodes:
        parts.append(
            f"<node id='{node_id}'>"
            f"<tag k='local_x' v='{x}'/><tag k='local_y' v='{y}'/>"
            f"<tag k='ele' v='0.0'/></node>"
        )
    for way_id, refs in ways:
        nds = "".join(f"<nd ref='{r}'/>" for r in refs)
        parts.append(f"<way id='{way_id}'>{nds}</way>")
    parts.append("</osm>")
    path = tmp_path / "lanelet2_map.osm"
    path.write_text("\n".join(parts))
    return str(path)


# --- .osm parsing ---


def test_parse_osm_reads_local_xy_in_way_order(tmp_path):
    path = _osm(tmp_path, [("1", 1.5, 2.5), ("2", 3.5, 4.5)], [("10", ["1", "2"])])
    (poly,) = parse_osm_polylines(path)
    assert poly.tolist() == [[1.5, 2.5], [3.5, 4.5]]


def test_parse_osm_drops_ways_with_fewer_than_two_nodes(tmp_path):
    # A single-node way carries no segment; keeping it would index out of range
    # in polylines_to_segments.
    path = _osm(
        tmp_path,
        [("1", 0.0, 0.0), ("2", 1.0, 0.0)],
        [("10", ["1"]), ("11", ["1", "2"])],
    )
    assert len(parse_osm_polylines(path)) == 1


def test_parse_osm_ignores_nodes_without_local_coordinates(tmp_path):
    # lat/lon-only nodes exist in the wild; a way referencing one must simply
    # skip it rather than raise.
    path = tmp_path / "m.osm"
    path.write_text(
        "<osm version='0.6'>"
        "<node id='1'><tag k='local_x' v='0'/><tag k='local_y' v='0'/></node>"
        "<node id='2' lat='1' lon='2'/>"
        "<node id='3'><tag k='local_x' v='5'/><tag k='local_y' v='0'/></node>"
        "<way id='9'><nd ref='1'/><nd ref='2'/><nd ref='3'/></way>"
        "</osm>"
    )
    (poly,) = parse_osm_polylines(str(path))
    assert poly.tolist() == [[0.0, 0.0], [5.0, 0.0]]


def test_polylines_to_segments_flattens_to_start_end_pairs():
    starts, ends = polylines_to_segments([np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])])
    assert starts.tolist() == [[0.0, 0.0], [1.0, 0.0]]
    assert ends.tolist() == [[1.0, 0.0], [2.0, 0.0]]


def test_polylines_to_segments_handles_no_input():
    starts, ends = polylines_to_segments([])
    assert starts.shape == (0, 2) and ends.shape == (0, 2)


# --- point-to-segment distance ---


def test_nearest_on_segments_projects_onto_the_segment_interior():
    starts, ends = polylines_to_segments([np.array([[0.0, 0.0], [10.0, 0.0]])])
    d, closest = nearest_on_segments(np.array([[5.0, 3.0]]), starts, ends)
    assert math.isclose(d[0], 3.0, abs_tol=1e-12)
    assert closest[0].tolist() == [5.0, 0.0]


def test_nearest_on_segments_clamps_beyond_the_ends():
    # Past the end, the answer is the endpoint -- this is the property that lets
    # the fit skip resampling polylines (no discretisation floor).
    starts, ends = polylines_to_segments([np.array([[0.0, 0.0], [10.0, 0.0]])])
    d, closest = nearest_on_segments(np.array([[13.0, 4.0]]), starts, ends)
    assert math.isclose(d[0], 5.0, abs_tol=1e-12)  # hypot(3, 4)
    assert closest[0].tolist() == [10.0, 0.0]


def test_nearest_on_segments_picks_the_closest_of_many():
    starts, ends = polylines_to_segments(_WAYS)
    d, closest = nearest_on_segments(np.array([[1.0, 40.0]]), starts, ends)
    assert math.isclose(d[0], 1.0, abs_tol=1e-12)  # the vertical way, not the horizontal
    assert closest[0].tolist() == [0.0, 40.0]


def test_nearest_on_segments_survives_a_degenerate_segment():
    # A zero-length segment must not divide by zero; it answers with its point.
    starts, ends = polylines_to_segments([np.array([[7.0, 7.0], [7.0, 7.0]])])
    d, closest = nearest_on_segments(np.array([[7.0, 9.0]]), starts, ends)
    assert math.isclose(d[0], 2.0, abs_tol=1e-12)
    assert closest[0].tolist() == [7.0, 7.0]


def test_nearest_on_segments_spans_more_than_one_query_chunk():
    # Guards the chunked writes: > _QUERY_CHUNK queries must all be filled in,
    # in order, not just the first chunk.
    starts, ends = polylines_to_segments([np.array([[0.0, 0.0], [1000.0, 0.0]])])
    ys = np.arange(1.0, 501.0)
    pts = np.column_stack([np.full_like(ys, 5.0), ys])
    d, _ = nearest_on_segments(pts, starts, ends)
    assert np.allclose(d, ys)


# --- the affine and the fit ---


def test_apply_affine_flips_y_and_translates():
    out = apply_affine(np.array([[3.0, 4.0]]), 10.0, 20.0)
    assert out.tolist() == [[13.0, 16.0]]  # 20 + (-4)


def test_apply_affine_without_the_flip_keeps_y():
    out = apply_affine(np.array([[3.0, 4.0]]), 10.0, 20.0, flip=False)
    assert out.tolist() == [[13.0, 24.0]]


@pytest.mark.parametrize("true_offset", [(0.0, 0.0), (0.4, -0.3), (12.0, -7.5)])
def test_fit_recovers_a_known_translation(true_offset):
    # Build CARLA-frame probes that land exactly on the synthetic ways once the
    # true affine is applied, then check the fit recovers that affine from a
    # cold (0,0) start. Seeded within one basin for the non-zero cases.
    starts, ends = polylines_to_segments(_WAYS)
    ox, oy = true_offset
    t = np.linspace(0.0, 100.0, 200)
    on_map = np.concatenate([np.column_stack([t, np.zeros_like(t)]),
                             np.column_stack([np.zeros_like(t), t])])
    # Invert apply_affine: carla_x = map_x - ox, carla_y = -(map_y - oy).
    carla_xy = np.column_stack([on_map[:, 0] - ox, -(on_map[:, 1] - oy)])

    got = fit_translation(carla_xy, starts, ends, initial=true_offset)
    assert math.isclose(got[0], ox, abs_tol=1e-6)
    assert math.isclose(got[1], oy, abs_tol=1e-6)

    d, _ = nearest_on_segments(apply_affine(carla_xy, *got), starts, ends)
    assert float(np.median(d)) < 1e-9


def test_fit_pulls_a_displaced_start_back_onto_the_map():
    # Started 0.3 m off (well inside one basin), the iteration must converge to
    # the true offset rather than sit where it started. Convergence is geometric
    # (~halving per iteration), so this also pins that the default iteration cap
    # is high enough to finish from a realistic seed.
    starts, ends = polylines_to_segments(_WAYS)
    t = np.linspace(0.0, 100.0, 200)
    on_map = np.concatenate([np.column_stack([t, np.zeros_like(t)]),
                             np.column_stack([np.zeros_like(t), t])])
    carla_xy = np.column_stack([on_map[:, 0], -on_map[:, 1]])  # true offset (0,0)

    got = fit_translation(carla_xy, starts, ends, initial=(0.3, -0.3))
    assert math.isclose(got[0], 0.0, abs_tol=1e-5)
    assert math.isclose(got[1], 0.0, abs_tol=1e-5)


def test_fit_stops_early_when_the_initial_offset_is_already_right(monkeypatch):
    # The iteration cap must be a cap, not a cost: an already-correct start
    # produces a zero step and must break after ONE distance pass, which is what
    # makes raising the cap free for the common case.
    starts, ends = polylines_to_segments(_WAYS)
    real = fit_map_offset.nearest_on_segments
    calls = {"n": 0}

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(fit_map_offset, "nearest_on_segments", counting)

    t = np.linspace(0.0, 100.0, 50)
    carla_xy = np.column_stack([t, np.zeros_like(t)])
    got = fit_translation(carla_xy, starts, ends, initial=(0.0, 0.0), iterations=50)

    assert calls["n"] == 1
    assert got == (0.0, 0.0)


def test_fit_is_robust_to_probes_the_map_does_not_cover():
    # Half the probes sit on a "lane" absent from the lanelet2 map, 50 m away.
    # A mean-based update would be dragged by them; the median must not be.
    starts, ends = polylines_to_segments(_WAYS)
    t = np.linspace(0.0, 100.0, 200)
    covered = np.column_stack([t, np.zeros_like(t)])
    uncovered = np.column_stack([t, np.full_like(t, 50.0)])
    on_map = np.concatenate([covered, uncovered])
    carla_xy = np.column_stack([on_map[:, 0], -on_map[:, 1]])

    got = fit_translation(carla_xy, starts, ends)
    assert math.isclose(got[0], 0.0, abs_tol=1e-6)
    assert math.isclose(got[1], 0.0, abs_tol=1e-6)
