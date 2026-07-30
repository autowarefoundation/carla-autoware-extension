from pathlib import Path

import numpy as np
import pytest
from benchmarks.analysis.bench_io import (
    read_clock_csv,
    read_gt_csv,
    read_observer_csv,
    read_odometry_csv,
    read_pose_csv,
    read_published_time_csv,
    read_resources_csv,
    read_tf_csv,
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


# ---------------------------------------------------------------------------
# loadavg_1m -- the host-wide load series added to the resources.csv contract
# on 2026-07-30. It is an OPTIONAL column: every run filed before that date
# (results/B/run-007..012, all of results/E/) has a resources.csv without it,
# and results/E/ may not be modified. So absence must read as NaN -- explicitly
# "not recorded", distinguishable from a recorded 0.0 -- and never as a
# KeyError, a zero, or a missing key the caller has to .get() around.
#
# `RES` above is itself an old-format fixture (it is the pre-2026-07-30 header
# verbatim), which is why the tests above keep passing unchanged: that is the
# backward compatibility, exercised rather than asserted.
# ---------------------------------------------------------------------------

RES_WITH_LOADAVG = """sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf,loadavg_1m
1000,carla,140.5,2048,73.0,4096,0.98,25.80
1000,observer,3.25,512,-1,-1,0.98,25.80
2000,carla,150.0,4096,81.5,8192,0.94,50.05
2000,observer,3.50,512,-1,-1,0.94,50.05
"""


def test_read_resources_reads_the_loadavg_series(tmp_path):
    p = tmp_path / "resources.csv"
    p.write_text(RES_WITH_LOADAVG)
    d = read_resources_csv(p)
    np.testing.assert_allclose(d["carla"]["loadavg_1m"], [25.80, 50.05])
    assert d["carla"]["loadavg_1m"].dtype == np.float64


def test_loadavg_is_host_wide_so_it_repeats_across_processes_like_rtf(tmp_path):
    """loadavg is a property of the sample INSTANT and of the whole host, not
    of a process, so -- exactly like rtf -- it repeats across the rows sharing
    a sample_system_ns and any one process's column is the run's series. It is
    therefore NOT attributable to the process whose row carries it."""
    p = tmp_path / "resources.csv"
    p.write_text(RES_WITH_LOADAVG)
    d = read_resources_csv(p)
    np.testing.assert_allclose(d["carla"]["loadavg_1m"], d["observer"]["loadavg_1m"])


def test_a_run_filed_before_the_column_existed_reads_as_NaN_not_zero(tmp_path):
    """THE BACKWARD-COMPATIBILITY REQUIREMENT. `RES` is the pre-2026-07-30
    header verbatim -- the format every already-filed run carries. The key must
    be PRESENT (so no consumer needs a .get() and none can KeyError deep in an
    analysis run) and all-NaN, never 0.0: a real 0.0 would say the host was
    idle, and Task 13's whole finding is that it never is during a run."""
    p = tmp_path / "resources.csv"
    p.write_text(RES)
    d = read_resources_csv(p)
    assert "loadavg_1m" in d["carla"], "the key must exist even on an old file"
    load = d["carla"]["loadavg_1m"]
    assert load.shape == d["carla"]["cpu_pct"].shape, "one NaN per sample, not an empty array"
    assert np.all(np.isnan(load))
    assert not np.any(load == 0.0)


def test_NaN_absence_is_distinguishable_from_a_recorded_zero(tmp_path):
    """The two states must not collapse. A sampler that recorded a genuine 0.00
    (an idle host) and a run that predates the column are different facts, and
    only the first is a measurement."""
    old = tmp_path / "old.csv"
    old.write_text(RES)
    zeroed = tmp_path / "zeroed.csv"
    zeroed.write_text(RES_WITH_LOADAVG.replace("25.80", "0.00").replace("50.05", "0.00"))

    absent = read_resources_csv(old)["carla"]["loadavg_1m"]
    recorded = read_resources_csv(zeroed)["carla"]["loadavg_1m"]

    assert np.all(np.isnan(absent))
    assert not np.any(np.isnan(recorded))
    np.testing.assert_allclose(recorded, [0.0, 0.0])


def test_a_blank_loadavg_cell_reads_as_NaN_too(tmp_path):
    """A truncated final row (the sampler is SIGTERMed mid-write) leaves the
    field empty. That is "not recorded" for that sample, the same state as the
    whole column being absent -- not a parse error that would take down the
    analysis of an otherwise complete run."""
    p = tmp_path / "resources.csv"
    p.write_text(
        RES_WITH_LOADAVG.replace(
            "2000,carla,150.0,4096,81.5,8192,0.94,50.05", "2000,carla,150.0,4096,81.5,8192,0.94,"
        )
    )
    load = read_resources_csv(p)["carla"]["loadavg_1m"]
    assert not np.isnan(load[0])
    assert np.isnan(load[1])


def test_the_loadavg_not_applicable_sentinel_is_preserved_verbatim(tmp_path):
    """-1 is the contract's "the column exists, the sampler tried, /proc/loadavg
    was unreadable at that instant" marker -- a THIRD state, distinct from NaN
    (never recorded) and from 0.0 (an idle host). Averaging it in would
    understate load, so the reader must not massage it, exactly as for
    gpu_util_pct."""
    p = tmp_path / "resources.csv"
    p.write_text(RES_WITH_LOADAVG.replace(",25.80", ",-1"))
    load = read_resources_csv(p)["carla"]["loadavg_1m"]
    assert load[0] == -1.0
    assert not np.isnan(load[0])


_FILED_RESOURCES = sorted(
    (Path(__file__).resolve().parents[2] / "benchmarks" / "results").glob("*/run-*/resources.csv")
)


@pytest.mark.parametrize("filed", _FILED_RESOURCES, ids=lambda p: f"{p.parts[-3]}/{p.parts[-2]}")
def test_every_already_filed_run_still_reads(filed):
    """Not a fixture -- the REAL committed runs. Every one of them predates the
    column, `results/E/` may not be modified at all, and none of them is
    rewritten by this change: a reader that now REQUIRED loadavg_1m would break
    on all of them, which is the failure this parametrization exists to catch.
    Self-adjusting: a future run filed WITH the column passes here too, on the
    non-NaN branch."""
    d = read_resources_csv(filed)
    assert d, f"{filed} has no process rows"
    for process, cols in d.items():
        load = cols["loadavg_1m"]
        assert load.shape == cols["cpu_pct"].shape, f"{filed}:{process}"
        assert np.all(np.isnan(load)) or not np.any(np.isnan(load)), (
            f"{filed}:{process} mixes recorded and unrecorded loadavg samples"
        )


UNSORTED_OBS = """topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes
/a,300,3000,30,300,64
/a,100,1000,10,100,64
/a,200,2000,20,200,64
"""


def test_read_observer_preserves_row_order(tmp_path):
    """Stamps must come back in file order, not sorted -- callers that
    rely on arrival order (e.g. cadence's own np.sort) would silently
    get the wrong answer if a reader reordered rows behind their back."""
    p = tmp_path / "observer.csv"
    p.write_text(UNSORTED_OBS)
    d = read_observer_csv(p)
    np.testing.assert_array_equal(d["/a"]["header_stamp_ns"], [300, 100, 200])


def test_read_observer_header_only_returns_empty_dict(tmp_path):
    p = tmp_path / "observer.csv"
    p.write_text("topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes\n")
    assert read_observer_csv(p) == {}


ODOM = """topic,header_stamp_ns,x_m,y_m
/localization/kinematic_state,300,3.0,30.0
/localization/kinematic_state,100,1.0,10.0
/localization/kinematic_state,200,2.0,20.0
"""


def test_read_odometry_groups_by_topic_and_preserves_order(tmp_path):
    p = tmp_path / "odometry.csv"
    p.write_text(ODOM)
    d = read_odometry_csv(p)
    assert set(d) == {"/localization/kinematic_state"}
    g = d["/localization/kinematic_state"]
    np.testing.assert_array_equal(g["header_stamp_ns"], [300, 100, 200])
    np.testing.assert_allclose(g["x_m"], [3.0, 1.0, 2.0])
    np.testing.assert_allclose(g["y_m"], [30.0, 10.0, 20.0])
    assert g["header_stamp_ns"].dtype == np.int64
    assert g["x_m"].dtype == np.float64


def test_read_odometry_header_only_returns_empty_dict(tmp_path):
    p = tmp_path / "odometry.csv"
    p.write_text("topic,header_stamp_ns,x_m,y_m\n")
    assert read_odometry_csv(p) == {}


NDT_TOPIC = "/localization/pose_estimator/pose_with_covariance"
POSE = f"""topic,header_stamp_ns,x_m,y_m
{NDT_TOPIC},300,81371.1330,49912.7210
{NDT_TOPIC},100,81369.1330,49910.7210
{NDT_TOPIC},200,81370.1330,49911.7210
"""


def test_read_pose_groups_by_topic_and_preserves_order(tmp_path):
    p = tmp_path / "pose.csv"
    p.write_text(POSE)
    d = read_pose_csv(p)
    assert set(d) == {NDT_TOPIC}
    g = d[NDT_TOPIC]
    np.testing.assert_array_equal(g["header_stamp_ns"], [300, 100, 200])
    np.testing.assert_allclose(g["x_m"], [81371.133, 81369.133, 81370.133])
    np.testing.assert_allclose(g["y_m"], [49912.721, 49910.721, 49911.721])
    assert g["header_stamp_ns"].dtype == np.int64
    assert g["x_m"].dtype == np.float64


def test_read_pose_header_only_returns_empty_dict(tmp_path):
    """The observer opens pose.csv on every run, so a run with no `pose`-kind
    topic registered leaves a header-only file -- which must read as "no NDT
    pose recorded", the state the M5 gate refuses on, not as a crash."""
    p = tmp_path / "pose.csv"
    p.write_text("topic,header_stamp_ns,x_m,y_m\n")
    assert read_pose_csv(p) == {}


def test_pose_and_odometry_stay_separate_files(tmp_path):
    """Same schema, different quantities: pose.csv is the NDT estimate and
    odometry.csv the EKF-fused state, so one reader serves both but a caller
    can never pick up the wrong series by reading the wrong file."""
    (tmp_path / "pose.csv").write_text(POSE)
    (tmp_path / "odometry.csv").write_text(ODOM)
    assert set(read_pose_csv(tmp_path / "pose.csv")) == {NDT_TOPIC}
    assert set(read_odometry_csv(tmp_path / "odometry.csv")) == {"/localization/kinematic_state"}


TF = """topic,frame_id,child_frame_id,header_stamp_ns
/tf,map,base_link,100
/tf,map,base_link,150
/tf,map,base_link,200
"""


def test_read_tf_groups_by_topic_and_child_frame(tmp_path):
    p = tmp_path / "tf.csv"
    p.write_text(TF)
    d = read_tf_csv(p)
    assert set(d) == {("/tf", "base_link")}
    g = d[("/tf", "base_link")]
    np.testing.assert_array_equal(g["header_stamp_ns"], [100, 150, 200])
    assert g["header_stamp_ns"].dtype == np.int64
    # The parent is RECORDED, not filtered on, so a map->base_link claim is
    # checkable rather than assumed.
    assert g["frame_ids"] == ("map",)


def test_read_tf_surfaces_a_second_parent_frame(tmp_path):
    """A child frame reparented mid-run must be visible, not averaged into one
    rate -- that would be exactly the aggregate reading the typed `tf` kind
    exists to avoid."""
    p = tmp_path / "tf.csv"
    p.write_text(TF + "/tf,odom,base_link,250\n")
    g = read_tf_csv(p)[("/tf", "base_link")]
    assert g["frame_ids"] == ("map", "odom")
    assert g["header_stamp_ns"].size == 4


def test_read_tf_header_only_returns_empty_dict(tmp_path):
    p = tmp_path / "tf.csv"
    p.write_text("topic,frame_id,child_frame_id,header_stamp_ns\n")
    assert read_tf_csv(p) == {}


GT = """arrival_system_ns,sim_ns,x_m,y_m,z_m,yaw_rad
3000,300,3.0,30.0,0.3,0.03
1000,100,1.0,10.0,0.1,0.01
2000,200,2.0,20.0,0.2,0.02
"""


def test_read_gt_ungrouped_preserves_order(tmp_path):
    p = tmp_path / "gt.csv"
    p.write_text(GT)
    d = read_gt_csv(p)
    np.testing.assert_array_equal(d["sim_ns"], [300, 100, 200])
    np.testing.assert_allclose(d["yaw_rad"], [0.03, 0.01, 0.02])
    assert d["arrival_system_ns"].dtype == np.int64
    assert d["z_m"].dtype == np.float64


def test_read_gt_header_only_returns_empty_arrays(tmp_path):
    p = tmp_path / "gt.csv"
    p.write_text("arrival_system_ns,sim_ns,x_m,y_m,z_m,yaw_rad\n")
    d = read_gt_csv(p)
    assert all(arr.size == 0 for arr in d.values())
