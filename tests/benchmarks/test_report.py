import json

import numpy as np
import pytest
from benchmarks.analysis.manifest import RunManifest
from benchmarks.report import render_cell, summarize_run


def _make_run(
    tmp_path, name="run-001", excluded=False, exclusion_reason="", reverse_observer_rows=False
):
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
        excluded=excluded,
        exclusion_reason=exclusion_reason,
    ).save(d / "manifest.json")
    sim = np.arange(0, 5_000_000_000, 100_000_000, dtype=np.int64)
    wall = 1_000_000_000_000 + sim
    with open(d / "clock.csv", "w") as f:
        f.write("clock_ns,arrival_system_ns\n")
        for s, w in zip(sim, wall):
            f.write(f"{s},{w}\n")
    rows = list(zip(sim.tolist(), wall.tolist()))
    if reverse_observer_rows:
        rows = list(reversed(rows))
    with open(d / "observer.csv", "w") as f:
        f.write("topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes\n")
        for s, w in rows:
            f.write(f"/lidar,{s},{w + 7_000_000},{w},{s},1048576\n")
    (d / "published_time.csv").write_text("topic,source_header_ns,published_ns\n")
    (d / "resources.csv").write_text(
        "sample_system_ns,process,cpu_pct,rss_bytes,gpu_util_pct,vram_bytes,rtf\n"
    )
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


def test_bytes_per_s_out_of_order_arrivals_matches_ascending(tmp_path):
    """Regression for B2: observer.csv rows are not guaranteed to be in
    ascending arrival_system_ns order (e.g. an NTP step mid-run writes
    file rows out of order). bytes_per_s must be computed from the min
    and max arrival, not first-minus-last-row, so it stays positive and
    matches the value the same rows produce in ascending order. This
    also locks bench_io's file-order-preserving read behavior, which was
    previously untested."""
    ascending = tmp_path / "asc"
    descending = tmp_path / "desc"
    cell_asc = _make_run(ascending, reverse_observer_rows=False)
    cell_desc = _make_run(descending, reverse_observer_rows=True)
    bps_asc = summarize_run(cell_asc / "run-001")["topics"]["/lidar"]["bytes_per_s"]
    bps_desc = summarize_run(cell_desc / "run-001")["topics"]["/lidar"]["bytes_per_s"]
    assert bps_asc > 0
    assert bps_desc > 0
    assert bps_desc == bps_asc


def test_render_cell_marks_excluded_run(tmp_path):
    cell = _make_run(tmp_path, name="run-002", excluded=True, exclusion_reason="sensor dropout")
    md = render_cell(cell)
    assert "run-002 (EXCLUDED)" in md


def test_summarize_run_rejects_an_invalid_manifest(tmp_path):
    """A manifest that RunManifest.save would have refused can still reach the
    reader hand-edited. Rendering it would put an unregistered cell (or a run
    excluded without a reason) into a table that reads exactly like a scored
    one, so summarize_run surfaces the validation errors instead."""
    cell = _make_run(tmp_path)
    path = cell / "run-001" / "manifest.json"
    doc = json.loads(path.read_text())
    doc["cell"] = "A-typo"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="cell"):
        summarize_run(cell / "run-001")
