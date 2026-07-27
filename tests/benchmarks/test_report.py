import numpy as np
from benchmarks.analysis.manifest import RunManifest
from benchmarks.report import render_cell, summarize_run


def _make_run(tmp_path, name="run-001"):
    d = tmp_path / "A" / name
    d.mkdir(parents=True)
    RunManifest(
        cell="A",
        approach="extension",
        map_name="Town10HD_Opt",
        run_index=1,
        arm="static",
        harness_git_sha="abc",
        patches_git_sha="def",
        transport={
            "rmw": "rmw_cyclonedds_cpp",
            "shm_enabled": False,
            "dds_profile_sha256": "0" * 64,
        },
        carla_version="0.10-fork",
        autoware_image="img",
        started_at_ns=0,
    ).save(d / "manifest.json")
    sim = np.arange(0, 5_000_000_000, 100_000_000, dtype=np.int64)
    wall = 1_000_000_000_000 + sim
    with open(d / "clock.csv", "w") as f:
        f.write("clock_ns,arrival_system_ns\n")
        for s, w in zip(sim, wall):
            f.write(f"{s},{w}\n")
    with open(d / "observer.csv", "w") as f:
        f.write("topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes\n")
        for s, w in zip(sim, wall):
            f.write(f"/lidar,{s},{w + 7_000_000},{w},{s},1048576\n")
    (d / "published_time.csv").write_text("topic,source_header_ns,published_ns\n")
    (d / "resources.csv").write_text("sample_system_ns,process,cpu_pct,rss_bytes\n")
    return tmp_path / "A"


def test_summarize_run(tmp_path):
    cell = _make_run(tmp_path)
    s = summarize_run(cell / "run-001")
    lid = s["topics"]["/lidar"]
    assert abs(lid["one_hop_p50_ms"] - 7.0) < 0.1
    assert abs(lid["hz"] - 10.0) < 0.1
    assert s["manifest"]["cell"] == "A"


def test_render_cell_markdown(tmp_path):
    cell = _make_run(tmp_path)
    md = render_cell(cell)
    assert "| run-001 " in md and "/lidar" in md
