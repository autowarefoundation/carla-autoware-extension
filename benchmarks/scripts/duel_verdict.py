#!/usr/bin/env python3
"""Primary duel equivalence verdict: A (extension) vs B (tier4-native).

For each pre-registered margin metric (`benchmarks/config/margins.yaml`):
reduce every non-excluded run in a cell to ONE run-level scalar, feed
cell A's and cell B's run-level values into
`benchmarks.analysis.stats.bootstrap_ci_median_diff` +
`equivalence_decision` -- never re-implemented here -- and render
metric / n / delta-median / 95% CI / margin / verdict / notes as a
markdown table. This is the campaign's headline result, run once after
every pre-registered P3 cell is collected (no-peeking rule); Step 1
(this file) delivers the tool and its tests, ahead of any real P3 data.

Two layers, per the design note in the Task 22 brief:

* `verdict_row` / `render_table` are pure functions over plain numbers
  and have no filesystem dependency -- directly testable with synthetic
  run-level values (see tests/benchmarks/test_duel_verdict.py).
* `cell_run_values` / `build_verdict_table` / the concrete `extract_*`
  functions are the filesystem-touching aggregation layer, and `main`
  is a thin CLI shell around `build_verdict_table`.

Excluded runs (`RunManifest.excluded`) never contribute to a verdict --
`cell_run_values` drops them and reports how many, so a duel table never
looks like it counted a run the exclusion mechanism was built to drop.

A cell with fewer than the pre-registered n >= 10 runs per side still
gets a verdict (the underlying statistics are valid from n >= 3): the
alternative, silently omitting the metric, invites someone to "just
check" the number anyway with no visible caveat. Instead the row is
computed and flagged UNDER-N in its notes, so a duel report can never
present an under-powered comparison as an ordinary one. Below stats.py's
own hard minimum (n < 3 per side) no CI can be bootstrapped at all; that
renders as an explicit "insufficient-data" verdict rather than raising
and aborting the whole table -- mirroring benchmarks/report.py's
render_cell, where one bad run must not make a whole cell unrenderable.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from benchmarks.analysis.bench_io import (
    read_clock_csv,
    read_observer_csv,
    read_published_time_csv,
    read_resources_csv,
)
from benchmarks.analysis.clockfit import fit_sim_wall_affine
from benchmarks.analysis.latency import match_stamps, segment_sim_ms, staleness_ms
from benchmarks.analysis.latency import one_hop_wall_ms as _one_hop_wall_ms_series
from benchmarks.analysis.manifest import load_manifest
from benchmarks.analysis.stats import bootstrap_ci_median_diff, equivalence_decision, load_margins

# Pre-registered minimum runs per side for the primary duel (README.md,
# spec: Statistical treatment). Not read from margins.yaml -- it applies
# to every metric uniformly, unlike a per-metric margin.
MIN_RUNS = 10

MARGINS_YAML = Path(__file__).resolve().parent.parent / "config" / "margins.yaml"

# The primary duel is exactly cells A (extension) and B (tier4-native);
# their observer_topics/A.yaml and observer_topics/B.yaml register these
# identical four topics, so these are safe module-level constants for
# THIS duel specifically -- not a general cross-cell mapping (other
# cells, e.g. the python-bridge family, use different topic names).
LIDAR_TOPIC = "/sensing/lidar/top/pointcloud_raw_ex"
NDT_TOPIC = "/localization/pose_estimator/pose_with_covariance"
CONTROL_TOPIC = "/control/command/control_cmd"

# resources.csv's `process` column is an operator-chosen label from the
# run's process-map YAML (benchmarks/sampler/sample_resources.py
# --processes), which is not yet committed anywhere in this repo. "carla"
# is this tool's assumed default label for the CARLA server process --
# override with --carla-process-label if the real process map differs.
DEFAULT_CARLA_PROCESS_LABEL = "carla"


class MetricUnavailableError(RuntimeError):
    """A metric's extractor could not compute a value for one run (e.g. a
    topic the current data contract does not yet populate for this
    cell). Raised per-run, not per-table: `cell_run_values` catches it
    and reports the run as failed without aborting the other runs."""


@dataclass(frozen=True)
class VerdictRow:
    metric: str
    n_a: int
    n_b: int
    delta_median: float | None
    ci: tuple[float, float] | None
    margin: float
    verdict: str
    notes: str = ""


def verdict_row(
    metric: str,
    values_a,
    values_b,
    margin: float,
    *,
    iters: int = 10000,
    seed: int = 20260727,
    alpha: float = 0.05,
    min_n: int = MIN_RUNS,
    excluded_a: int = 0,
    excluded_b: int = 0,
) -> VerdictRow:
    """One metric's verdict row.

    All statistics are delegated to `benchmarks.analysis.stats`
    (`bootstrap_ci_median_diff`, `equivalence_decision`) -- this function
    only assembles their inputs/outputs and the under-n / insufficient-
    data / exclusion-count surfacing. `values_a`/`values_b` are already
    run-level values (one scalar per run of that cell): the median-of-
    medians step happens inside `bootstrap_ci_median_diff`, not here.

    `iters`/`seed`/`alpha` default to the pinned campaign values
    (stats.bootstrap_ci_median_diff's own defaults) so a verdict is
    reproducible across runs of this tool, a stated campaign success
    criterion.
    """
    a = np.asarray(values_a, dtype=np.float64)
    b = np.asarray(values_b, dtype=np.float64)
    notes: list[str] = []
    if excluded_a:
        notes.append(f"{excluded_a} run(s) excluded from A")
    if excluded_b:
        notes.append(f"{excluded_b} run(s) excluded from B")
    if a.size < min_n:
        notes.append(f"UNDER-N: a has {a.size} run(s) (< {min_n})")
    if b.size < min_n:
        notes.append(f"UNDER-N: b has {b.size} run(s) (< {min_n})")

    if a.size < 3 or b.size < 3:
        notes.append(
            f"insufficient data for a bootstrap CI (need >= 3 per side; "
            f"got a={a.size}, b={b.size})"
        )
        return VerdictRow(
            metric, int(a.size), int(b.size), None, None, margin,
            "insufficient-data", "; ".join(notes),
        )

    delta = float(np.median(a) - np.median(b))
    ci = bootstrap_ci_median_diff(a, b, iters=iters, seed=seed, alpha=alpha)
    verdict = equivalence_decision(delta, ci, margin)
    return VerdictRow(metric, int(a.size), int(b.size), delta, ci, margin, verdict, "; ".join(notes))


def render_table(rows: list[VerdictRow]) -> str:
    """Render verdict rows as a markdown table.

    Required columns per the Task 22 brief (metric, delta-median, CI,
    margin, verdict) plus n (a/b) and notes -- the latter two carry the
    exclusion-count / under-n / insufficient-data surfacing that the
    brief requires not be silent.
    """
    lines = [
        "| metric | n (a/b) | delta_median | 95% ci | margin | verdict | notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        delta_s = f"{r.delta_median:.3f}" if r.delta_median is not None else "-"
        ci_s = f"[{r.ci[0]:.3f}, {r.ci[1]:.3f}]" if r.ci is not None else "-"
        lines.append(
            f"| {r.metric} | {r.n_a}/{r.n_b} | {delta_s} | {ci_s} "
            f"| {r.margin:g} | {r.verdict} | {r.notes} |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Aggregation layer: run-* directories -> run-level values.
# ---------------------------------------------------------------------------


def cell_run_values(
    cell_dir: Path, extractor: Callable[[Path], float]
) -> tuple[list[float], int, list[str]]:
    """Run-level values for one cell directory, over every `run-*` it holds.

    Excluded runs (`RunManifest.excluded`) are skipped and counted, never
    passed to `extractor` -- that is the whole point of the exclusion
    mechanism (benchmarks/config/exclusions.md: a run marked excluded
    must not contribute to a verdict). A run whose manifest is missing,
    invalid, or whose extractor call raises is DROPPED and reported by
    name in `errors`, not silently skipped and not treated as excluded --
    mirroring report.render_cell's tolerance for one bad run not making
    a whole cell unreadable, while still surfacing every failure.

    Returns `(values, n_excluded, errors)`.
    """
    cell_dir = Path(cell_dir)
    values: list[float] = []
    n_excluded = 0
    errors: list[str] = []
    for run_dir in sorted(cell_dir.glob("run-*")):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            errors.append(f"{run_dir.name}: no manifest.json")
            continue
        try:
            manifest = load_manifest(manifest_path)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            errors.append(f"{run_dir.name}: FAILED loading manifest: {exc}")
            continue
        if manifest.excluded:
            n_excluded += 1
            continue
        try:
            values.append(extractor(run_dir))
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            errors.append(f"{run_dir.name}: FAILED {type(exc).__name__}: {exc}")
    return values, n_excluded, errors


# ---------------------------------------------------------------------------
# Concrete per-metric extractors: one run-level scalar per metric.
# Built entirely from benchmarks.analysis (bench_io/clockfit/latency) --
# the same building blocks benchmarks/report.py uses.
# ---------------------------------------------------------------------------


def _clock_fit(run_dir: Path):
    clock_ns, clock_wall = read_clock_csv(Path(run_dir) / "clock.csv")
    return fit_sim_wall_affine(clock_ns, clock_wall)


def extract_one_hop_wall_ms(run_dir: Path) -> float:
    """Run-level one_hop_wall_ms: median wall latency of LIDAR_TOPIC's
    arrivals against this run's own sim->wall clock fit (spec: M1a). This
    is the same computation report.summarize_run performs per topic;
    here it is reduced to the one topic the margin is pre-registered
    against and to a single run-level scalar (the median)."""
    run_dir = Path(run_dir)
    fit = _clock_fit(run_dir)
    topics = read_observer_csv(run_dir / "observer.csv")
    if LIDAR_TOPIC not in topics:
        raise MetricUnavailableError(f"{LIDAR_TOPIC} not in {run_dir / 'observer.csv'}")
    cols = topics[LIDAR_TOPIC]
    hop = _one_hop_wall_ms_series(cols["header_stamp_ns"], cols["arrival_system_ns"], fit)
    return float(np.median(hop))


def extract_lidar_to_ndt_sim_ms(run_dir: Path) -> float:
    """Run-level lidar -> NDT-pose sim-time latency (spec: M1a).

    latency.py documents lidar -> NDT pose as one of the few hops whose
    header stamp is verified to PROPAGATE (the scan matcher republishes
    the triggering point cloud's own header.stamp), so `match_stamps` on
    `header_stamp_ns` correctly pairs "the pose computed from this scan"
    without an explicit scan id. Because that header stamp is identical
    on both sides, `segment_sim_ms` cannot be applied to it directly (the
    diff would always be exactly 0); it is applied instead to each
    matched row's `clock_ns` -- the sim-clock reading observed AT
    ARRIVAL (observer.csv's own contract column) -- giving the sim-time
    elapsed between the scan's and its pose's observer arrivals. The
    match is still by header stamp; only the diffed quantity differs
    from `one_hop_wall_ms`'s wall-domain measurement.
    """
    run_dir = Path(run_dir)
    topics = read_observer_csv(run_dir / "observer.csv")
    for topic in (LIDAR_TOPIC, NDT_TOPIC):
        if topic not in topics:
            raise MetricUnavailableError(f"{topic} not in {run_dir / 'observer.csv'}")
    lidar, ndt = topics[LIDAR_TOPIC], topics[NDT_TOPIC]
    i, j = match_stamps(lidar["header_stamp_ns"], ndt["header_stamp_ns"])
    if i.size == 0:
        raise MetricUnavailableError(
            f"no matched {LIDAR_TOPIC}/{NDT_TOPIC} header stamps in {run_dir}"
        )
    seg = segment_sim_ms(lidar["clock_ns"][i], ndt["clock_ns"][j])
    return float(np.median(seg))


def extract_control_staleness_ms(run_dir: Path) -> float:
    """Run-level control-command staleness: median publish-time minus
    source-header sim-time for CONTROL_TOPIC (spec: M1b), from
    published_time.csv. As of this writing CONTROL_TOPIC is not yet
    registered in observer_topics/A.yaml or B.yaml's PublishedTime
    section (appended after live discovery, per that file's own
    comment), so this correctly raises MetricUnavailableError on
    today's real data -- not a bug, the metric is not wired yet."""
    run_dir = Path(run_dir)
    published = read_published_time_csv(run_dir / "published_time.csv")
    if CONTROL_TOPIC not in published:
        raise MetricUnavailableError(
            f"{CONTROL_TOPIC} not in {run_dir / 'published_time.csv'}"
        )
    cols = published[CONTROL_TOPIC]
    stale = staleness_ms(cols["source_header_ns"], cols["published_ns"])
    return float(np.median(stale))


def extract_carla_process_cpu_pct(
    run_dir: Path, process_label: str = DEFAULT_CARLA_PROCESS_LABEL
) -> float:
    """Run-level CARLA-process CPU%: median `cpu_pct` sample for the
    resources.csv process labelled `process_label` (spec: M3)."""
    run_dir = Path(run_dir)
    processes = read_resources_csv(run_dir / "resources.csv")
    if process_label not in processes:
        raise MetricUnavailableError(
            f"process {process_label!r} not in {run_dir / 'resources.csv'} "
            f"(present: {sorted(processes)})"
        )
    return float(np.median(processes[process_label]["cpu_pct"]))


def extract_achieved_rate_ratio(run_dir: Path, expected_hz: float) -> float:
    """Run-level achieved-vs-expected LiDAR publish rate ratio (spec: M2).

    `expected_hz` is a REQUIRED argument, not a hardcoded default: the
    primary duel's baseline LiDAR frequency is not pre-registered
    anywhere in benchmarks/config/cells.yaml (only the M4 sweep classes'
    points_per_second are, and those apply to a different arm). Guessing
    a number here would put an un-pre-registered constant into code the
    campaign otherwise treats as frozen before P3 -- so the CLI requires
    --expected-lidar-hz explicitly and this metric is simply not wired
    into build_extractors() when it is omitted.
    """
    if expected_hz <= 0:
        raise ValueError(f"expected_hz must be > 0, got {expected_hz}")
    run_dir = Path(run_dir)
    topics = read_observer_csv(run_dir / "observer.csv")
    if LIDAR_TOPIC not in topics:
        raise MetricUnavailableError(f"{LIDAR_TOPIC} not in {run_dir / 'observer.csv'}")
    arrivals = np.sort(topics[LIDAR_TOPIC]["arrival_system_ns"])
    if arrivals.size < 2:
        raise MetricUnavailableError(f"fewer than 2 {LIDAR_TOPIC} arrivals in {run_dir}")
    hz = (arrivals.size - 1) / ((arrivals[-1] - arrivals[0]) / 1e9)
    return float(hz / expected_hz)


def build_extractors(
    *,
    expected_lidar_hz: float | None = None,
    carla_process_label: str = DEFAULT_CARLA_PROCESS_LABEL,
) -> dict[str, Callable[[Path], float]]:
    """The default extractor for every pre-registered margin metric this
    tool can currently wire. `achieved_rate_ratio` is included only when
    `expected_lidar_hz` is given (see `extract_achieved_rate_ratio`) --
    omitting it is a deliberate "not wired" state, not an oversight."""
    extractors: dict[str, Callable[[Path], float]] = {
        "one_hop_wall_ms": extract_one_hop_wall_ms,
        "lidar_to_ndt_sim_ms": extract_lidar_to_ndt_sim_ms,
        "control_staleness_ms": extract_control_staleness_ms,
        "carla_process_cpu_pct": lambda run_dir: extract_carla_process_cpu_pct(
            run_dir, carla_process_label
        ),
    }
    if expected_lidar_hz is not None:
        extractors["achieved_rate_ratio"] = lambda run_dir: extract_achieved_rate_ratio(
            run_dir, expected_lidar_hz
        )
    return extractors


def build_verdict_table(
    cell_a_dir: Path,
    cell_b_dir: Path,
    margins: dict,
    extractors: dict[str, Callable[[Path], float]],
    *,
    min_n: int = MIN_RUNS,
) -> str:
    """The full pipeline for every metric in `margins`: aggregate cell A's
    and cell B's run-level values (dropping excluded runs), then
    `verdict_row`. A margin metric with no entry in `extractors` is
    named in a trailing note rather than silently absent from the
    table -- a missing row and a row that was never attempted must not
    look the same."""
    rows: list[VerdictRow] = []
    unavailable: list[str] = []
    for metric, spec in margins.items():
        extractor = extractors.get(metric)
        if extractor is None:
            unavailable.append(metric)
            continue
        values_a, excluded_a, errors_a = cell_run_values(Path(cell_a_dir), extractor)
        values_b, excluded_b, errors_b = cell_run_values(Path(cell_b_dir), extractor)
        row = verdict_row(
            metric, values_a, values_b, float(spec["margin"]),
            min_n=min_n, excluded_a=excluded_a, excluded_b=excluded_b,
        )
        run_errors = errors_a + errors_b
        if run_errors:
            extra = "; ".join(run_errors)
            row = dataclasses.replace(
                row, notes=(row.notes + "; " if row.notes else "") + extra
            )
        rows.append(row)
    out = [render_table(rows)]
    if unavailable:
        out.append("")
        out.append(
            "Metrics with no wired extractor in this run: " + ", ".join(sorted(unavailable))
        )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Primary A/B duel equivalence verdict.")
    p.add_argument("cell_a", nargs="?", default="A", help="cell dir name for approach A (default: A)")
    p.add_argument("cell_b", nargs="?", default="B", help="cell dir name for approach B (default: B)")
    p.add_argument(
        "--results", default="benchmarks/results", type=Path,
        help="results root (default: benchmarks/results)",
    )
    p.add_argument(
        "--margins", default=MARGINS_YAML, type=Path,
        help="margins.yaml path (default: benchmarks/config/margins.yaml)",
    )
    p.add_argument(
        "--min-n", type=int, default=MIN_RUNS,
        help=f"pre-registered minimum runs per side (default: {MIN_RUNS})",
    )
    p.add_argument(
        "--expected-lidar-hz", type=float, default=None,
        help="expected LiDAR publish rate for achieved_rate_ratio; omit to "
        "leave that metric unwired (not pre-registered for the primary duel yet)",
    )
    p.add_argument(
        "--carla-process-label", default=DEFAULT_CARLA_PROCESS_LABEL,
        help=f"resources.csv 'process' label for the CARLA process "
        f"(default: {DEFAULT_CARLA_PROCESS_LABEL!r})",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    margins = load_margins(args.margins)
    extractors = build_extractors(
        expected_lidar_hz=args.expected_lidar_hz,
        carla_process_label=args.carla_process_label,
    )
    table = build_verdict_table(
        Path(args.results) / args.cell_a,
        Path(args.results) / args.cell_b,
        margins,
        extractors,
        min_n=args.min_n,
    )
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
