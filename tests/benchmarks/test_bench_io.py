import numpy as np
from benchmarks.analysis.bench_io import read_clock_csv, read_observer_csv, read_published_time_csv

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
