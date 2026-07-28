import numpy as np
import pytest

from benchmarks.analysis.window import project_station_m, spatial_window, static_window

ROUTE = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 50.0]])  # 150 m polyline


def test_project_station_walks_the_polyline():
    xy = np.array([[0.0, 0.0], [50.0, 2.0], [100.0, 25.0]])
    st = project_station_m(ROUTE, xy)
    assert st == pytest.approx([0.0, 50.0, 125.0], abs=1e-6)


def test_spatial_window_bounds_by_station_and_warmup():
    stamps = np.arange(10, dtype=np.int64) * 1_000_000_000  # 0..9 s
    xy = np.column_stack([np.linspace(0, 135, 10), np.zeros(10)])
    xy[9] = [100.0, 35.0]
    # warm-up 2 s: samples at 0/1 s excluded even though station >= 10
    start, end = spatial_window(stamps, xy, ROUTE, start_station_m=10.0,
                                end_station_m=130.0, warmup_ns=2_000_000_000)
    st = project_station_m(ROUTE, xy)
    assert start == stamps[2]
    assert end == stamps[np.nonzero(st <= 130.0)[0][-1]]


def test_spatial_window_empty_raises():
    stamps = np.array([0, 1], dtype=np.int64)
    xy = np.array([[500.0, 500.0], [501.0, 500.0]])  # never on route window
    with pytest.raises(ValueError):
        spatial_window(stamps, xy, ROUTE, 10.0, 130.0, 0)


def test_static_window_is_warmup_trimmed():
    assert static_window(0, 60_000_000_000, 20_000_000_000) == (
        20_000_000_000, 60_000_000_000)
