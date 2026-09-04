import numpy as np
from benchmarks.analysis.bench_io import (
    read_clock_csv,
    read_observer_csv,
    read_published_time_csv,
    read_resources_csv,
)

OBS = """topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes
/a,100,1000,10,100,64
/b,150,1100,20,100,32
/a,200,2000,30,200,64
"""


def test_read_observer_groups_by_topic(tmp_path):
    p = tmp_path / "observer.csv"
    p.write_text(OBS)
    d = read_observer_csv(p)
    assert set(d) == {"/a", "/b"}
    np.testing.assert_array_equal(d["/a"]["header_stamp_ns"], [100, 200])
    np.testing.assert_array_equal(d["/a"]["arrival_system_ns"], [1000, 2000])
    np.testing.assert_array_equal(d["/b"]["size_bytes"], [32])


def test_read_clock(tmp_path):
    p = tmp_path / "clock.csv"
    p.write_text("clock_ns,arrival_system_ns\n100,1000\n200,1990\n")
    clock, wall = read_clock_csv(p)
    np.testing.assert_array_equal(clock, [100, 200])
    np.testing.assert_array_equal(wall, [1000, 1990])


def test_read_published_time(tmp_path):
    p = tmp_path / "published_time.csv"
    p.write_text("topic,source_header_ns,published_ns\n/x,100,180\n")
    d = read_published_time_csv(p)
    np.testing.assert_array_equal(d["/x"]["published_ns"], [180])


RES = """sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf
1000,carla,140.5,2048,73.0,4096,0.98
1000,observer,3.25,512,-1,-1,0.98
2000,carla,150.0,4096,81.5,8192,0.94
2000,observer,3.50,512,-1,-1,0.94
"""


def test_read_resources_groups_by_process(tmp_path):
    p = tmp_path / "resources.csv"
    p.write_text(RES)
    d = read_resources_csv(p)
    assert set(d) == {"carla", "observer"}
    np.testing.assert_array_equal(d["carla"]["sample_system_ns"], [1000, 2000])
    np.testing.assert_allclose(d["carla"]["cpu_pct"], [140.5, 150.0])
    np.testing.assert_array_equal(d["carla"]["vram_bytes"], [4096, 8192])
    np.testing.assert_allclose(d["observer"]["cpu_pct"], [3.25, 3.50])


def test_read_resources_keeps_column_dtypes(tmp_path):
    p = tmp_path / "resources.csv"
    p.write_text(RES)
    d = read_resources_csv(p)["carla"]
    assert d["sample_system_ns"].dtype == np.int64
    assert d["rss_bytes"].dtype == np.int64
    assert d["gpu_util_pct"].dtype == np.float64
    assert d["rtf"].dtype == np.float64


def test_read_resources_preserves_the_not_applicable_marker(tmp_path):
    """`-1` means "no GPU context on this process"; averaging it in would
    silently understate GPU load, so the reader must not massage it."""
    p = tmp_path / "resources.csv"
    p.write_text(RES)
    obs = read_resources_csv(p)["observer"]
    np.testing.assert_array_equal(obs["gpu_util_pct"], [-1.0, -1.0])
    np.testing.assert_array_equal(obs["vram_bytes"], [-1, -1])


def test_read_resources_rtf_series_feeds_the_ceiling_evaluator(tmp_path):
    """rtf is a property of the sample instant, so it repeats across the
    processes sharing a sample_system_ns; either process's column is the
    per-sample series evaluate_ceiling consumes."""
    p = tmp_path / "resources.csv"
    p.write_text(RES)
    d = read_resources_csv(p)
    np.testing.assert_allclose(d["carla"]["rtf"], d["observer"]["rtf"])
    np.testing.assert_allclose(d["carla"]["rtf"], [0.98, 0.94])
