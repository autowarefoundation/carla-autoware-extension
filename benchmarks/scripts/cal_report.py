#!/usr/bin/env python3
"""CAL report tool: a calibration cell's per-topic latency/rate table.

    python3 -m benchmarks.scripts.cal_report <run_dir>

SCOPE -- the CALIBRATION-approach cells, not CAL-seam alone. It reads one run
directory's observer.csv + resources.csv and renders a per-topic one-hop/rate
table plus a per-process CPU table; nothing in it is specific to either CAL
cell. `benchmarks/run.sh`'s step 15 names this module as the renderer for
every `carla: none` cell, which today means CAL-rmw.

    SCOPE CORRECTED 2026-07-31 (Task 16). This docstring's first line and its
    campaign-status note used to scope the tool to CAL-seam and to state that
    it "will never be run against a measurement". Task 16 falsified that: all
    fifteen `benchmarks/results/CAL-rmw/run-*` directories were rendered
    through `summarize_run`, and the frozen `one_hop_wall_ms` margin in
    `benchmarks/config/margins.yaml` is derived from those p50s. The tool is
    LIVE; only its SEAM use is dead. See results/CAL-rmw/PROVENANCE.md.

WHAT IS DEAD is the C1(a) seam half, and it is deliberately kept
(2026-07-30). Cell CAL-seam was STRUCK by the owner's core-duel scope cut
(config/cells.yaml `dropped:`; benchmarks/README.md's 2026-07-30 amendment),
so there is no C1(a) table in the results and C1(a) seam overhead is
UNMEASURED -- not weakly measured. An owner TIME-BUDGET decision, not a
technical block: this module and its unit tests
(tests/benchmarks/test_cal_report.py) are complete and green, and so is the
extension-side publisher they were written for
(extension/src/publishers/BenchCloudPublisher.{h,cpp}, registered in
ExtensionInit.cpp). Nothing is deleted, so a later campaign can pick the seam
instrument up; nobody should read its presence as evidence that the SEAM was
measured.

CAL-seam pairs the SAME synthetic sensor_msgs/PointCloud2 message published
two ways on one CARLA fork process -- through the extension's C-ABI seam .so
(`/bench/seam_cloud`) and by an in-core publisher (`/bench/incore_cloud`) --
so the paired one-hop wall-latency difference is the only measurement the
seam-overhead claim rests on (see Task 14's brief).

Unlike `benchmarks/report.py`, a CAL run has NO `clock.csv`: there is no
simulation, so nothing ever publishes `/clock` (mirrors the `has_sim_clock`
distinction `benchmarks/scripts/cell_info.py` already draws for `carla:
none` cells). Both bench publishers stamp `header.stamp` with wall `now()`
on the SAME host as the observer, so one-hop wall latency is the direct
difference `arrival_system_ns - header_stamp_ns` -- no sim/wall affine fit
(`benchmarks/analysis/clockfit.py`) is needed, or even possible, here.

Percentile and rate math is not reimplemented: achieved Hz comes from
`benchmarks.analysis.cadence.inter_arrival_stats` (the same helper
`report.py` uses); the direct-difference one-hop latency is
`benchmarks.analysis.latency.segment_sim_ms` (dst - src, in ms) -- it needs
no sim-to-wall affine fit here because both timestamps it is fed are
already wall clock, but the arithmetic is identical, so it is reused rather
than reimplemented. Percentiles are `numpy.percentile` calls inline,
exactly like `report.py`'s own `one_hop_p50_ms`/`one_hop_p99_ms`. CSV
parsing goes through the shared `benchmarks.analysis.bench_io` readers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from benchmarks.analysis.bench_io import read_observer_csv, read_resources_csv
from benchmarks.analysis.cadence import inter_arrival_stats
from benchmarks.analysis.latency import segment_sim_ms


def summarize_run(run_dir) -> dict:
    """Reads `observer.csv` + `resources.csv` under `run_dir` and returns the
    C1(a) table as a dict: per-topic one-hop wall latency percentiles +
    achieved Hz, and per-process publish CPU. Both files are required --
    `resources.csv` supplies the CPU half of the C1(a) table, so a run
    missing it must fail loud rather than render a silently-incomplete
    report (mirrors `report.py.summarize_run`'s strictness on clock.csv)."""
    run_dir = Path(run_dir)

    topics = {}
    for topic, cols in read_observer_csv(run_dir / "observer.csv").items():
        cad = inter_arrival_stats(cols["arrival_system_ns"])
        one_hop = segment_sim_ms(cols["header_stamp_ns"], cols["arrival_system_ns"])
        topics[topic] = {
            "hz": cad.hz,
            "n": cad.n,
            "one_hop_p50_ms": float(np.percentile(one_hop, 50)),
            "one_hop_p95_ms": float(np.percentile(one_hop, 95)),
            "one_hop_p99_ms": float(np.percentile(one_hop, 99)),
        }

    processes = {}
    for process, cols in read_resources_csv(run_dir / "resources.csv").items():
        cpu = cols["cpu_pct"]
        processes[process] = {
            "n": int(cpu.size),
            "cpu_pct_mean": float(np.mean(cpu)),
            "cpu_pct_p95": float(np.percentile(cpu, 95)),
        }

    return {"topics": topics, "processes": processes}


def render_report(run_dir) -> str:
    """Markdown table for one CAL run directory: a per-topic latency/rate
    table and a per-process publish-CPU table, in the order `summarize_run`'s
    two sections list them. On CAL-seam the per-topic table would be the
    seam-vs-in-core paired comparison; on CAL-rmw it is the single synthetic
    cloud, one row.

    The heading names no cell. It used to read "CAL-seam report" and was
    LABELLING CAL-RMW RUNS WITH ANOTHER CELL'S NAME -- corrected 2026-07-31
    (Task 16), which is the first task to have rendered a real run through
    here. Text only: no percentile, rate or CPU value changes."""
    run_dir = Path(run_dir)
    s = summarize_run(run_dir)
    lines = [
        f"## CAL report: {run_dir.name}",
        "",
        "### One-hop wall latency (arrival_system_ns - header_stamp_ns)",
        "",
        "| topic | hz | n | p50 ms | p95 ms | p99 ms |",
        "|---|---|---|---|---|---|",
    ]
    for topic, t in sorted(s["topics"].items()):
        lines.append(
            f"| {topic} | {t['hz']:.2f} | {t['n']} "
            f"| {t['one_hop_p50_ms']:.2f} | {t['one_hop_p95_ms']:.2f} "
            f"| {t['one_hop_p99_ms']:.2f} |"
        )
    lines += [
        "",
        "### Per-process publish CPU (resources.csv)",
        "",
        "| process | n | cpu_pct mean | cpu_pct p95 |",
        "|---|---|---|---|",
    ]
    for process, p in sorted(s["processes"].items()):
        lines.append(f"| {process} | {p['n']} | {p['cpu_pct_mean']:.2f} | {p['cpu_pct_p95']:.2f} |")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Render the CAL latency/rate table for one run directory."
    )
    p.add_argument(
        "run_dir",
        type=Path,
        help="CAL run directory containing observer.csv + resources.csv",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    print(render_report(args.run_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
