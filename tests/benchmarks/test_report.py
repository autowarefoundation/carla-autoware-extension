import json
import sys

import numpy as np
import pytest
from benchmarks import report
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
        placement={
            "run_mode": "editor-game",
            "container_image": "img@sha256:x",
            "observer_env": "bench-observer:universe-devel",
            "engine_build_id": "b4c93e55-fc8f-42fc-b377-358910364e1c",
        },
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
    cell = _make_run(tmp_path, name="run-002", excluded=True, exclusion_reason="crash:observer")
    md = render_cell(cell)
    assert "run-002 (EXCLUDED)" in md


def test_render_cell_survives_a_run_with_no_observer_output(tmp_path):
    """Regression: one aborted run must not make its whole cell unrenderable.

    An excluded run whose observer never started has no clock.csv, so
    summarize_run raises FileNotFoundError on it. render_cell used to
    propagate that, which meant the first bring-up failure in a cell made
    EVERY later healthy run of that cell report as not contract-valid -- and
    in an interleaved duel, two such runs aborted the duel. Excluded runs
    stay in the tree by pre-registration (exclusions.md), so this is the
    normal steady state, not a corner case.
    """
    cell = _make_run(tmp_path, name="run-002")  # healthy
    broken = cell / "run-001"
    broken.mkdir(parents=True)
    RunManifest(
        **{
            **json.loads((cell / "run-002" / "manifest.json").read_text()),
            "run_index": 1,
            "excluded": True,
            "exclusion_reason": "crash:cell-launch",
        }
    ).save(broken / "manifest.json")

    md = render_cell(cell)

    # The healthy run still renders...
    assert "| run-002 " in md and "/lidar" in md
    # ...and the broken one is REPORTED, by name and by cause, not skipped.
    assert "run-001" in md
    assert "RENDER FAILED: FileNotFoundError" in md


def test_render_cell_reports_a_run_with_no_manifest_at_all(tmp_path):
    """The other route into the same state: a directory created before its
    manifest was written. render_cell must name it rather than raise."""
    cell = _make_run(tmp_path, name="run-002")
    (cell / "run-001").mkdir(parents=True)

    md = render_cell(cell)

    assert "| run-002 " in md
    assert "run-001" in md and "RENDER FAILED" in md


def test_summarize_run_still_raises_on_a_broken_run(tmp_path):
    """render_cell's tolerance must not have loosened summarize_run: the
    harness's post-run smoke calls it on THIS run and needs it to raise."""
    cell = _make_run(tmp_path, name="run-002")
    broken = cell / "run-001"
    broken.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        summarize_run(broken)


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


def test_render_cell_tags_an_excluded_runs_render_failure(tmp_path):
    """A run that is both excluded AND unrenderable (no observer output, the
    normal shape of a run aborted before the window) must carry the same
    (EXCLUDED) tag a successfully-summarized excluded run gets -- otherwise a
    reader (and main()'s exit code, below) cannot tell it apart from an
    unexplained failure."""
    cell = _make_run(tmp_path, name="run-002")  # healthy
    broken = cell / "run-001"
    broken.mkdir(parents=True)
    RunManifest(
        **{
            **json.loads((cell / "run-002" / "manifest.json").read_text()),
            "run_index": 1,
            "excluded": True,
            "exclusion_reason": "crash:cell-launch",
        }
    ).save(broken / "manifest.json")

    md = render_cell(cell)

    row = next(line for line in md.splitlines() if "run-001" in line)
    assert "(EXCLUDED)" in row
    assert "RENDER FAILED" in row


def test_render_cell_escapes_pipe_in_render_failed_message(tmp_path):
    """The exception message is interpolated into a markdown table cell: a
    '|' in it (e.g. from a path) must not be read as an extra column
    separator, and must not change the row's column count."""
    cell = tmp_path / "A|weird"
    (cell / "run-001").mkdir(parents=True)  # no manifest.json at all

    md = render_cell(cell)

    row = next(line for line in md.splitlines() if "RENDER FAILED" in line)
    assert "\\|" in row  # the path's "|" was escaped, not left bare
    # 7 columns -> 8 unescaped "|" delimiters -> 9 elements once split; the
    # same shape every other row in the table has (checked against the
    # header row so this does not silently drift from it).
    header = "| run | topic | hz | p95 ms | 1-hop p50 ms | 1-hop p99 ms | MB/s |"
    assert len(row.replace("\\|", "").split("|")) == len(header.split("|"))


def test_main_exits_nonzero_on_an_unexplained_render_failure(tmp_path, monkeypatch):
    """report.main() used to exit 0 even when every row RENDER FAILED; a run
    with no manifest at all (so `_best_effort_excluded` cannot vouch for it)
    must fail the process, not just print a table nobody is required to
    read."""
    (tmp_path / "A" / "run-001").mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["report", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        report.main()
    assert exc_info.value.code != 0


def test_main_exits_zero_when_every_failure_is_excluded(tmp_path, monkeypatch, capsys):
    """The counterpart to the test above: a RENDER FAILED row that IS tagged
    (EXCLUDED) is the expected steady state of an aborted, pre-registered
    run, not something that should stop a script piping this output."""
    cell = _make_run(tmp_path, name="run-002")  # healthy
    broken = cell / "run-001"
    broken.mkdir(parents=True)
    RunManifest(
        **{
            **json.loads((cell / "run-002" / "manifest.json").read_text()),
            "run_index": 1,
            "excluded": True,
            "exclusion_reason": "crash:cell-launch",
        }
    ).save(broken / "manifest.json")

    monkeypatch.setattr(sys, "argv", ["report", str(tmp_path)])
    report.main()  # must not raise SystemExit
    assert "RENDER FAILED" in capsys.readouterr().out
