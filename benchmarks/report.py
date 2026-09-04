"""Render per-cell summaries from benchmarks/results/<cell>/run-*/."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np

from .analysis.bench_io import read_clock_csv, read_observer_csv
from .analysis.cadence import inter_arrival_stats
from .analysis.clockfit import fit_sim_wall_affine
from .analysis.latency import one_hop_wall_ms
from .analysis.manifest import load_manifest


def summarize_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    manifest = load_manifest(run_dir / "manifest.json")
    clock_ns, clock_wall = read_clock_csv(run_dir / "clock.csv")
    fit = fit_sim_wall_affine(clock_ns, clock_wall)
    topics = {}
    for topic, cols in read_observer_csv(run_dir / "observer.csv").items():
        cad = inter_arrival_stats(cols["arrival_system_ns"])
        hop = one_hop_wall_ms(cols["header_stamp_ns"], cols["arrival_system_ns"], fit)
        arrivals = cols["arrival_system_ns"]
        span_s = (arrivals.max() - arrivals.min()) / 1e9
        topics[topic] = {
            "hz": cad.hz,
            "p95_ms": cad.p95_ms,
            "n": cad.n,
            "one_hop_p50_ms": float(np.percentile(hop, 50)),
            "one_hop_p99_ms": float(np.percentile(hop, 99)),
            "bytes_per_s": float(cols["size_bytes"].sum() / span_s),
        }
    return {
        "manifest": dataclasses.asdict(manifest),
        "fit_slope": fit.slope,
        "fit_residual_ns": fit.max_abs_residual_ns,
        "topics": topics,
    }


def render_cell(cell_dir: Path) -> str:
    cell_dir = Path(cell_dir)
    lines = [
        f"## Cell {cell_dir.name}",
        "",
        "| run | topic | hz | p95 ms | 1-hop p50 ms | 1-hop p99 ms | MB/s |",
        "|---|---|---|---|---|---|---|",
    ]
    for run_dir in sorted(cell_dir.glob("run-*")):
        s = summarize_run(run_dir)
        run_label = run_dir.name
        if s["manifest"]["excluded"]:
            run_label = f"{run_label} (EXCLUDED)"
        for topic, t in sorted(s["topics"].items()):
            lines.append(
                f"| {run_label} | {topic} | {t['hz']:.2f} "
                f"| {t['p95_ms']:.2f} | {t['one_hop_p50_ms']:.2f} "
                f"| {t['one_hop_p99_ms']:.2f} "
                f"| {t['bytes_per_s'] / 1e6:.2f} |"
            )
    return "\n".join(lines)


def main() -> None:
    results = Path(sys.argv[1] if len(sys.argv) > 1 else "benchmarks/results")
    for cell_dir in sorted(p for p in results.iterdir() if p.is_dir()):
        print(render_cell(cell_dir))
        print()


if __name__ == "__main__":
    main()
