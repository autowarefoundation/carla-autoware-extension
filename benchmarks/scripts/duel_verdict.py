#!/usr/bin/env python3
"""Primary duel equivalence verdict: A (extension) vs B (tier4-native).

For each pre-registered margin metric (`benchmarks/config/margins.yaml`):
resolve the run's registered scoring window, reduce every non-excluded
run in a cell to ONE run-level scalar over that window, feed cell A's
and cell B's run-level values into
`benchmarks.analysis.stats.bootstrap_ci_median_diff` + `equivalence_
decision` -- never re-implemented here -- and render metric / n /
delta-median / 95% CI / margin / verdict / notes as a markdown table.
This is the campaign's headline result, run once after every
pre-registered P3 cell is collected (no-peeking rule); Step 1 (this
file) delivers the tool and its tests, ahead of any real P3 data.

Every metric's definition -- source columns, join rule, scoring window,
aggregation -- is REGISTERED in `benchmarks/README.md`, "Primary-duel
metric definitions", and this module implements exactly that, not an
independent interpretation of it: read that section before changing any
extractor below. Per-cell bindings (topics, process label, expected
rates) are never hardcoded here; they come from
`benchmarks.scripts.cell_info.metrics_for`, reading
`benchmarks/config/cells.yaml`'s per-cell `metrics:` block. A `None`
binding is a legitimate registered state ("not pre-registered yet"),
never a value to guess -- the metric is reported UNAVAILABLE for that
cell instead.

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
Runs that are not DUEL-ADMISSIBLE (`RunManifest.duel_admissible` false --
the pre-registration amendment of 2026-07-30, Task 15b) are dropped the
same way and counted SEPARATELY, because they are a different thing: an
excluded run's data is invalid, whereas an inadmissible run's data is
perfectly valid and merely not part of the primary duel's interleaved
design (a cell-A bring-up/gate run is the case that motivated the
field). Conflating the two counts would report good evidence as broken.

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
An unbound metric (a registered `None` binding, e.g. cell B's
`lidar_expected_hz` pending Task 13) renders the SAME way -- explicit
"insufficient-data" plus an UNAVAILABLE reason -- without ever touching
a run directory for that metric, so a null binding cannot be mistaken
for a metric that was measured and happened to come back short.

`achieved_rate_ratio`'s registered companion output, the M2 three-way
reconciliation (`ReconciliationRow` / `_cell_reconciliation_row` /
`render_reconciliation_table`), is appended after the main table: per
cell, per arm, over the SAME resolved scoring window (never a second,
independent one), separating publisher drop from observer loss via
`benchmarks.analysis.cadence.reconcile_drops` -- never re-implemented
here either. See that section's own comment block for what is and is
not shared with `sweep_verdict.py`'s equivalent, M4-scoped computation.
"""

from __future__ import annotations

import argparse
import dataclasses
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import yaml

from benchmarks.analysis.bench_io import (
    read_clock_csv,
    read_observer_csv,
    read_odometry_csv,
    read_published_time_csv,
    read_resources_csv,
)
from benchmarks.analysis.cadence import (
    DropStats,
    expected_count,
    inter_arrival_stats,
    reconcile_drops,
)
from benchmarks.analysis.clockfit import AffineFit, fit_sim_wall_affine, sim_to_wall
from benchmarks.analysis.latency import match_stamps, staleness_ms
from benchmarks.analysis.latency import one_hop_wall_ms as _one_hop_wall_ms_series
from benchmarks.analysis.manifest import ARMS, RunManifest, load_manifest
from benchmarks.analysis.publisher_counts import read_publisher_counts
from benchmarks.analysis.stats import bootstrap_ci_median_diff, equivalence_decision, load_margins
from benchmarks.analysis.window import spatial_window, static_window
from benchmarks.scripts.cell_info import UnknownIdError, cell_entry, load_cells_doc, metrics_for

# Pre-registered minimum runs per side for the primary duel (README.md,
# spec: Statistical treatment). Not read from margins.yaml -- it applies
# to every metric uniformly, unlike a per-metric margin.
MIN_RUNS = 10

MARGINS_YAML = Path(__file__).resolve().parent.parent / "config" / "margins.yaml"
ROUTES_DIR = Path(__file__).resolve().parent.parent / "config" / "routes"

# Scoring-window warm-up discard (README, "Scoring window"): 20 s, in ns.
WARMUP_NS = 20_000_000_000

# The odometry topic the closed-loop scoring window is resolved against.
# Registered directly in prose in benchmarks/README.md ("spatial_window
# over odometry.csv's /localization/kinematic_state rows") rather than as
# a per-cell cells.yaml binding, so it is a literal here, unlike
# lidar_topic/ndt_topic/control_published_time_topic/cpu_process_label/
# lidar_expected_hz, which all come from `metrics_for`.
ODOM_TOPIC = "/localization/kinematic_state"

# control_staleness_ms's registered clock-domain discriminator: TWO
# disjoint bands, not one cut. A wall stamp is a Unix epoch (> 1e18 ns);
# a sim stamp is a run-length offset (< 1e13 ns for any window this
# harness records). A median in neither band is unclassifiable and must
# be reported so, not defaulted to either branch -- see
# benchmarks/README.md, control_staleness_ms.
WALL_STAMP_FLOOR_NS = 1e18
SIM_STAMP_CEIL_NS = 1e13


class MetricUnavailableError(RuntimeError):
    """A metric's extractor could not compute a value for one run (e.g. a
    topic the current data contract does not yet populate for this
    cell, or no data inside the registered scoring window). Raised
    per-run, not per-table: `cell_run_values` catches it and reports the
    run as failed without aborting the other runs."""


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
    # Which manifest `arm` this row was scored on ("" for callers that
    # don't care, e.g. a pure-function test with no run directories at
    # all). The duel is never pooled across arms -- Task 18 runs each
    # arm as its own n >= 10 session, so mixing static and closed-loop
    # runs into one median would both mix two different quantities and
    # double-count toward the pre-registered n.
    arm: str = ""


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
    inadmissible_a: int = 0,
    inadmissible_b: int = 0,
    arm: str = "",
) -> VerdictRow:
    """One metric's verdict row.

    All statistics are delegated to `benchmarks.analysis.stats`
    (`bootstrap_ci_median_diff`, `equivalence_decision`) -- this function
    only assembles their inputs/outputs and the under-n / insufficient-
    data / exclusion-count surfacing. `values_a`/`values_b` are already
    run-level values (one scalar per run of that cell, already scoped to
    a single arm by the caller): the median-of-medians step happens
    inside `bootstrap_ci_median_diff`, not here.

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
    # Reported with its own wording, never merged into the exclusion counts:
    # "excluded" means the data is invalid, "not duel-admissible" means valid
    # data outside the duel's interleaved design (see the module docstring).
    if inadmissible_a:
        notes.append(f"{inadmissible_a} run(s) not duel-admissible in A")
    if inadmissible_b:
        notes.append(f"{inadmissible_b} run(s) not duel-admissible in B")
    if a.size < min_n:
        notes.append(f"UNDER-N: a has {a.size} run(s) (< {min_n})")
    if b.size < min_n:
        notes.append(f"UNDER-N: b has {b.size} run(s) (< {min_n})")

    if a.size < 3 or b.size < 3:
        notes.append(
            f"insufficient data for a bootstrap CI (need >= 3 per side; got a={a.size}, b={b.size})"
        )
        return VerdictRow(
            metric,
            int(a.size),
            int(b.size),
            None,
            None,
            margin,
            "insufficient-data",
            "; ".join(notes),
            arm,
        )

    delta = float(np.median(a) - np.median(b))
    ci = bootstrap_ci_median_diff(a, b, iters=iters, seed=seed, alpha=alpha)
    verdict = equivalence_decision(delta, ci, margin)
    return VerdictRow(
        metric, int(a.size), int(b.size), delta, ci, margin, verdict, "; ".join(notes), arm
    )


def render_table(rows: list[VerdictRow]) -> str:
    """Render verdict rows as a markdown table.

    Required columns per the Task 22 brief (metric, delta-median, CI,
    margin, verdict) plus arm, n (a/b) and notes -- arm because the duel
    is reported per arm rather than pooled (see VerdictRow.arm); the
    latter two carry the exclusion-count / under-n / insufficient-data /
    unavailable-metric surfacing that the brief requires not be silent.
    """
    lines = [
        "| metric | arm | n (a/b) | delta_median | 95% ci | margin | verdict | notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        delta_s = f"{r.delta_median:.3f}" if r.delta_median is not None else "-"
        ci_s = f"[{r.ci[0]:.3f}, {r.ci[1]:.3f}]" if r.ci is not None else "-"
        lines.append(
            f"| {r.metric} | {r.arm} | {r.n_a}/{r.n_b} | {delta_s} | {ci_s} "
            f"| {r.margin:g} | {r.verdict} | {r.notes} |"
        )
    return "\n".join(lines)


def _append_note(existing: str, extra: str) -> str:
    return f"{existing}; {extra}" if existing else extra


# ---------------------------------------------------------------------------
# Scoring window resolution (README.md, "Scoring window").
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RunWindow:
    fit: AffineFit
    sim_lo: int
    sim_hi: int
    wall_lo: int
    wall_hi: int


def _wall_to_sim(fit: AffineFit, wall_ns):
    """Exact inverse of clockfit.sim_to_wall, per the registered formula
    in benchmarks/README.md: (wall_ns - intercept_ns) / slope."""
    return (np.asarray(wall_ns, dtype=np.float64) - fit.intercept_ns) / fit.slope


def _load_route(map_name: str) -> tuple[np.ndarray, float, float]:
    """(route_xy, start_station_m, end_station_m) for `config/routes/<map>.yaml`."""
    path = ROUTES_DIR / f"{map_name}.yaml"
    if not path.is_file():
        raise MetricUnavailableError(f"no route file for map {map_name!r} at {path}")
    doc = yaml.safe_load(path.read_text())
    route_xy = np.asarray(doc["polyline"], dtype=np.float64)
    stations = doc["stations"]
    return route_xy, float(stations["start_m"]), float(stations["end_m"])


def _resolve_window(run_dir: Path, manifest: RunManifest) -> _RunWindow:
    """The run's scoring window in BOTH domains, per benchmarks/README.md's
    "Scoring window" rule: closed-loop arm -> `window.spatial_window`
    (native SIM ns, over odometry.csv against the route polyline);
    every other arm -> `window.static_window` (native WALL ns, over
    clock.csv). The other domain's bounds always come from the run's own
    clock-fit affine: forward (`clockfit.sim_to_wall`) for sim -> wall,
    its exact inverse (`_wall_to_sim`) for wall -> sim. Windowing is not
    optional for any of the five duel metrics (README: a whole-run
    median is dominated by the 20 s warm-up against a 2.0 ms margin).
    """
    run_dir = Path(run_dir)
    clock_ns, clock_wall = read_clock_csv(run_dir / "clock.csv")
    fit = fit_sim_wall_affine(clock_ns, clock_wall)
    if manifest.arm == "closed-loop":
        odom = read_odometry_csv(run_dir / "odometry.csv")
        if ODOM_TOPIC not in odom:
            raise MetricUnavailableError(f"{ODOM_TOPIC} not in {run_dir / 'odometry.csv'}")
        cols = odom[ODOM_TOPIC]
        route_xy, start_m, end_m = _load_route(manifest.map_name)
        xy = np.stack([cols["x_m"], cols["y_m"]], axis=1)
        sim_lo_f, sim_hi_f = spatial_window(
            cols["header_stamp_ns"], xy, route_xy, start_m, end_m, WARMUP_NS
        )
        wall_lo = float(sim_to_wall(fit, sim_lo_f))
        wall_hi = float(sim_to_wall(fit, sim_hi_f))
        sim_lo, sim_hi = float(sim_lo_f), float(sim_hi_f)
    else:
        wall_lo_i, wall_hi_i = static_window(
            int(clock_wall.min()), int(clock_wall.max()), WARMUP_NS
        )
        wall_lo, wall_hi = float(wall_lo_i), float(wall_hi_i)
        sim_lo = float(_wall_to_sim(fit, wall_lo))
        sim_hi = float(_wall_to_sim(fit, wall_hi))
    return _RunWindow(
        fit, int(round(sim_lo)), int(round(sim_hi)), int(round(wall_lo)), int(round(wall_hi))
    )


# ---------------------------------------------------------------------------
# Aggregation layer: run-* directories -> run-level values.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RunRecord:
    """One run's manifest plus its (possibly failed) resolved window,
    produced by walking a cell's run-* tree exactly once."""

    run_dir: Path
    manifest: RunManifest
    window: _RunWindow | None
    window_error: str | None


def _walk_cell_runs(
    cell_dir: Path, *, arm: str | None = None
) -> tuple[list[_RunRecord], int, int, list[str]]:
    """Walk a cell directory's `run-*` trees EXACTLY ONCE, resolving each
    surviving run's scoring window exactly once regardless of how many
    of the five metrics are later computed from the result -- this is
    the actual "resolved once per run" (README.md, "Scoring window")
    this module implements: a caller (`build_verdict_table`) walks a
    given (cell, arm) pair's runs ONCE per `build_verdict_table` call
    and reuses the returned records across every metric, rather than
    each metric re-walking and re-resolving.

    `arm`, when given, restricts to runs whose manifest `arm` matches
    exactly -- a cell's run-* tree holds every arm it registers (e.g.
    both `static` and `closed-loop` for cells A/B) and the duel is
    computed PER ARM, never pooled: Task 18 runs each arm as its own
    n >= 10 session, so mixing them would both mix two different
    quantities and double-count toward the pre-registered n. A run of a
    different arm is silently out of scope for this call, not an
    exclusion or an error.

    Excluded runs (`RunManifest.excluded`) are skipped and counted, never
    turned into a record -- that is the whole point of the exclusion
    mechanism (benchmarks/config/exclusions.md: a run marked excluded
    must not contribute to a verdict).

    Runs that are not DUEL-ADMISSIBLE are skipped and counted too, on
    their OWN counter (amendment 2026-07-30, Task 15b -- see the module
    docstring). Order matters and is deliberate: `excluded` is tested
    FIRST, so an excluded run keeps being reported as excluded rather
    than being relabelled by whichever of the two it also happens to be.
    Two counters, not one, because "the data is invalid" and "valid data
    outside the duel's interleaved design" are different facts and a
    reader acts differently on each.

    A run whose manifest is missing
    or invalid is DROPPED and reported by name in `errors`. A run whose
    WINDOW fails to resolve (e.g. no odometry sample inside the spatial
    window) still gets a record -- with `window=None` and the failure
    text in `window_error` -- so a metric that does not need a window
    (`_extract_fit_residual_ns`) can still be computed for it; a metric
    that DOES need the window reports the failure itself when applied
    (see `_apply_extractor`).

    Returns `(records, n_excluded, n_inadmissible, errors)`.
    """
    cell_dir = Path(cell_dir)
    records: list[_RunRecord] = []
    n_excluded = 0
    n_inadmissible = 0
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
        if arm is not None and manifest.arm != arm:
            continue
        if manifest.excluded:
            n_excluded += 1
            continue
        if not manifest.duel_admissible:
            n_inadmissible += 1
            continue
        window: _RunWindow | None
        window_error: str | None
        try:
            window = _resolve_window(run_dir, manifest)
            window_error = None
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            window = None
            window_error = f"{type(exc).__name__}: {exc}"
        records.append(_RunRecord(run_dir, manifest, window, window_error))
    return records, n_excluded, n_inadmissible, errors


def _apply_extractor(
    records: list[_RunRecord], extractor: Callable[[Path, RunManifest, _RunWindow], float]
) -> tuple[list[float], list[str]]:
    """Apply a windowed `extractor(run_dir, manifest, window)` to every
    record whose window resolved; a record whose window FAILED is
    reported in `errors` (never passed to `extractor`, since it has no
    window to give it) rather than silently skipped."""
    values: list[float] = []
    errors: list[str] = []
    for rec in records:
        if rec.window is None:
            errors.append(f"{rec.run_dir.name}: FAILED window: {rec.window_error}")
            continue
        try:
            values.append(extractor(rec.run_dir, rec.manifest, rec.window))
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            errors.append(f"{rec.run_dir.name}: FAILED {type(exc).__name__}: {exc}")
    return values, errors


def _apply_fit_residual(records: list[_RunRecord]) -> tuple[list[float], list[str]]:
    """Apply `_extract_fit_residual_ns` to every record REGARDLESS of
    whether its window resolved: the fit residual is a property of the
    whole run's /clock series, independent of any metric's scoring
    window (see `_extract_fit_residual_ns`), so a run whose spatial
    window failed (e.g. the ego never reached stations.start_m) must
    not lose this diagnostic -- that is exactly the run where knowing
    whether the clock fit itself was sane matters most."""
    values: list[float] = []
    errors: list[str] = []
    for rec in records:
        try:
            values.append(_extract_fit_residual_ns(rec.run_dir, rec.manifest))
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            errors.append(f"{rec.run_dir.name}: FAILED {type(exc).__name__}: {exc}")
    return values, errors


def cell_run_values(
    cell_dir: Path,
    extractor: Callable[[Path, RunManifest, _RunWindow], float],
    *,
    arm: str | None = None,
) -> tuple[list[float], int, list[str]]:
    """Run-level values for ONE metric over one cell directory: a thin
    convenience wrapper over `_walk_cell_runs` + `_apply_extractor` for
    callers (tests, or a one-off script) that only need a single
    metric. `build_verdict_table` does NOT use this function -- it calls
    `_walk_cell_runs` once per (cell, arm) and reuses the same records
    across all five metrics via `_apply_extractor`/`_apply_fit_residual`,
    which is what actually achieves "resolved once per run"; a caller
    that invokes `cell_run_values` once per metric (as this function's
    own single call always does internally) still pays for one window
    resolution per run for THAT metric specifically, same as calling
    `_walk_cell_runs` directly would.

    Returns `(values, n_excluded, n_inadmissible, errors)` -- the
    inadmissible count is its own term for the same reason `_walk_cell_
    runs` keeps it separate from `n_excluded`: a caller that folded the
    two together would report valid non-duel evidence as invalid data.
    """
    records, n_excluded, n_inadmissible, walk_errors = _walk_cell_runs(cell_dir, arm=arm)
    values, apply_errors = _apply_extractor(records, extractor)
    return values, n_excluded, n_inadmissible, walk_errors + apply_errors


# ---------------------------------------------------------------------------
# Concrete per-metric extractors: one run-level scalar per metric, over
# the resolved scoring window. Each implements exactly one formula from
# benchmarks/README.md, "Primary-duel metric definitions" -- see that
# section for the derivation and registered rationale of each.
# ---------------------------------------------------------------------------


def extract_one_hop_wall_ms(
    run_dir: Path, manifest: RunManifest, window: _RunWindow, lidar_topic: str
) -> float:
    """one_hop_wall_ms (README: transport, margin 2.0): median wall
    latency of `lidar_topic` arrivals against the run's own clock fit,
    over the scoring window. The same measurand report.summarize_run
    reports per topic as one_hop_p50_ms, narrowed to the registered
    topic and window. `window` is resolved once per run by the caller
    (`cell_run_values`), not re-resolved here."""
    run_dir = Path(run_dir)
    topics = read_observer_csv(run_dir / "observer.csv")
    if lidar_topic not in topics:
        raise MetricUnavailableError(f"{lidar_topic} not in {run_dir / 'observer.csv'}")
    cols = topics[lidar_topic]
    stamps = cols["header_stamp_ns"]
    in_w = (stamps >= window.sim_lo) & (stamps <= window.sim_hi)
    if not np.any(in_w):
        raise MetricUnavailableError(f"no {lidar_topic} rows inside the scoring window")
    hop = _one_hop_wall_ms_series(stamps[in_w], cols["arrival_system_ns"][in_w], window.fit)
    return float(np.median(hop))


def extract_lidar_to_ndt_sim_ms(
    run_dir: Path, manifest: RunManifest, window: _RunWindow, lidar_topic: str, ndt_topic: str
) -> float:
    """lidar_to_ndt_sim_ms (README: pipeline, margin 5.0): matched pairs
    via exact `header_stamp_ns` equality (the scan matcher re-stamps its
    pose with the matched scan's own stamp; a nearest-stamp fallback is
    registered as explicitly forbidden), then the matched pair's
    observer-arrival gap expressed in sim time via the clock-fit slope
    -- NOT a `clock_ns` diff, which quantizes to the world-tick period
    (50 ms) against this metric's 5.0 ms margin."""
    run_dir = Path(run_dir)
    topics = read_observer_csv(run_dir / "observer.csv")
    for topic in (lidar_topic, ndt_topic):
        if topic not in topics:
            raise MetricUnavailableError(f"{topic} not in {run_dir / 'observer.csv'}")
    lidar, ndt = topics[lidar_topic], topics[ndt_topic]
    l_mask = (lidar["header_stamp_ns"] >= window.sim_lo) & (
        lidar["header_stamp_ns"] <= window.sim_hi
    )
    n_mask = (ndt["header_stamp_ns"] >= window.sim_lo) & (ndt["header_stamp_ns"] <= window.sim_hi)
    l_stamp, l_arrival = lidar["header_stamp_ns"][l_mask], lidar["arrival_system_ns"][l_mask]
    n_stamp, n_arrival = ndt["header_stamp_ns"][n_mask], ndt["arrival_system_ns"][n_mask]
    i, j = match_stamps(l_stamp, n_stamp)
    if i.size == 0:
        raise MetricUnavailableError(
            f"no matched {lidar_topic}/{ndt_topic} header stamps inside the scoring window "
            "(stamp propagation broken for this run)"
        )
    gap_ms = (
        (n_arrival[j].astype(np.float64) - l_arrival[i].astype(np.float64)) / window.fit.slope / 1e6
    )
    return float(np.median(gap_ms))


def extract_control_staleness_ms(
    run_dir: Path, manifest: RunManifest, window: _RunWindow, published_time_topic: str | None
) -> float:
    """control_staleness_ms (README: M1b staleness, margin 10.0). Source
    is keyed by `control_published_time_topic` -- the PublishedTime
    topic's OWN name, never `control_topic` (a lookup on the latter can
    never match; bench_observer writes the topic it subscribed to, and
    the PublishedTime companion is a different topic).

    Implements BOTH registered clock-domain branches with the mechanical
    discriminator: a wall stamp is a Unix epoch (> 1e18 ns, branch b); a
    sim stamp is a run-length offset (< 1e13 ns, branch a). These are
    two DISJOINT registered bands, not a single cut -- a median that
    falls in neither (e.g. a monotonic/uptime-based `published_stamp`,
    plausible for a publisher to emit) is UNCLASSIFIABLE and must be
    reported as such, not defaulted into branch (a): silently reading it
    as sim-domain would yield a nonsense ~1e8 ms "staleness" instead of
    surfacing that this run's clock domain was never registered.
    """
    if published_time_topic is None:
        raise MetricUnavailableError(
            "control_published_time_topic is not registered for this cell (Tasks 13/20)"
        )
    run_dir = Path(run_dir)
    published = read_published_time_csv(run_dir / "published_time.csv")
    if published_time_topic not in published:
        raise MetricUnavailableError(
            f"{published_time_topic} not in {run_dir / 'published_time.csv'}"
        )
    cols = published[published_time_topic]
    src = cols["source_header_ns"]
    mask = (src >= window.sim_lo) & (src <= window.sim_hi)
    if not np.any(mask):
        raise MetricUnavailableError(f"no {published_time_topic} rows inside the scoring window")
    src_w, pub_w = src[mask], cols["published_ns"][mask]
    median_pub = float(np.median(pub_w))
    if median_pub > WALL_STAMP_FLOOR_NS:
        # branch (b): wall domain
        stale = _one_hop_wall_ms_series(src_w, pub_w, window.fit)
    elif median_pub < SIM_STAMP_CEIL_NS:
        stale = staleness_ms(src_w, pub_w)  # branch (a): sim domain
    else:
        raise MetricUnavailableError(
            f"{published_time_topic} published_ns median {median_pub:.3e} ns falls in neither "
            f"registered clock-domain band (sim < {SIM_STAMP_CEIL_NS:.0e}, "
            f"wall > {WALL_STAMP_FLOOR_NS:.0e}); clock domain not determinable"
        )
    return float(np.median(stale))


def extract_carla_process_cpu_pct(
    run_dir: Path, manifest: RunManifest, window: _RunWindow, process_label: str | None
) -> float:
    """carla_process_cpu_pct (README: M3, margin 10.0 absolute points):
    median `cpu_pct` from `resources.csv` for the process labelled
    `process_label` (a `config/processes/<cell>.yaml` `label`, never a
    pattern or a process name), over the scoring window in WALL time."""
    if process_label is None:
        raise MetricUnavailableError("cpu_process_label is not registered for this cell")
    run_dir = Path(run_dir)
    processes = read_resources_csv(run_dir / "resources.csv")
    if process_label not in processes:
        raise MetricUnavailableError(
            f"process {process_label!r} not in {run_dir / 'resources.csv'} "
            f"(present: {sorted(processes)})"
        )
    cols = processes[process_label]
    stamps = cols["sample_system_ns"]
    mask = (stamps >= window.wall_lo) & (stamps <= window.wall_hi)
    if not np.any(mask):
        raise MetricUnavailableError(f"no {process_label!r} samples inside the scoring window")
    return float(np.median(cols["cpu_pct"][mask]))


def extract_achieved_rate_ratio(
    run_dir: Path,
    manifest: RunManifest,
    window: _RunWindow,
    lidar_topic: str,
    expected_hz: float | None,
) -> float:
    """achieved_rate_ratio (README: M2, margin 0.02):
    `cadence.inter_arrival_stats(header_stamp_ns).hz / lidar_expected_hz`
    over `lidar_topic`'s in-window rows. SIM header stamps, not wall
    arrivals (a wall-domain rate would fold the simulator's RTF into a
    0.02 margin; RTF is separately measured via resources.csv)."""
    if expected_hz is None:
        raise MetricUnavailableError("lidar_expected_hz is not registered for this cell")
    if expected_hz <= 0:
        raise ValueError(f"lidar_expected_hz must be > 0, got {expected_hz}")
    run_dir = Path(run_dir)
    topics = read_observer_csv(run_dir / "observer.csv")
    if lidar_topic not in topics:
        raise MetricUnavailableError(f"{lidar_topic} not in {run_dir / 'observer.csv'}")
    stamps = topics[lidar_topic]["header_stamp_ns"]
    in_w = stamps[(stamps >= window.sim_lo) & (stamps <= window.sim_hi)]
    if in_w.size < 2:
        raise MetricUnavailableError(
            f"fewer than 2 {lidar_topic} arrivals inside the scoring window"
        )
    return float(inter_arrival_stats(in_w).hz / expected_hz)


def _extract_fit_residual_ns(run_dir: Path, manifest: RunManifest) -> float:
    """The run's own sim<->wall clock-fit residual (ns), reported
    alongside one_hop_wall_ms per its registered definition: the duel
    term carries this fit's error on top of the transport it measures.
    Deliberately takes NO `window` and is applied via `_apply_fit_
    residual`, not `_apply_extractor`/`cell_run_values`: the fit is over
    the whole run's /clock series, independent of any metric's scoring
    window, so gating it on window resolution would lose this
    diagnostic on exactly the runs (a broken spatial window) where it is
    most wanted."""
    del manifest  # part of the uniform extractor shape; unused here
    clock_ns, clock_wall = read_clock_csv(Path(run_dir) / "clock.csv")
    fit = fit_sim_wall_affine(clock_ns, clock_wall)
    return float(fit.max_abs_residual_ns)


# ---------------------------------------------------------------------------
# Per-cell binding: cells.yaml's `metrics:` block -> bound extractors.
# A `None` binding makes the metric unavailable for that cell WITHOUT
# calling any extractor (cheap, and produces one clear reason instead of
# one identical error per run).
# ---------------------------------------------------------------------------

_Binder = Callable[
    [dict], "tuple[Callable[[Path, RunManifest, _RunWindow], float] | None, str | None]"
]


def _bind_one_hop_wall_ms(metrics: dict):
    topic = metrics["lidar_topic"]
    if topic is None:
        return None, "lidar_topic not registered for this cell"
    return (
        lambda run_dir, manifest, window: extract_one_hop_wall_ms(run_dir, manifest, window, topic)
    ), None


def _bind_lidar_to_ndt_sim_ms(metrics: dict):
    lidar_topic, ndt_topic = metrics["lidar_topic"], metrics["ndt_topic"]
    missing = [k for k, v in (("lidar_topic", lidar_topic), ("ndt_topic", ndt_topic)) if v is None]
    if missing:
        return None, f"{', '.join(missing)} not registered for this cell"
    return (
        lambda run_dir, manifest, window: extract_lidar_to_ndt_sim_ms(
            run_dir, manifest, window, lidar_topic, ndt_topic
        )
    ), None


def _bind_control_staleness_ms(metrics: dict):
    topic = metrics["control_published_time_topic"]
    if topic is None:
        return None, "control_published_time_topic not registered for this cell (Tasks 13/20)"
    return (
        lambda run_dir, manifest, window: extract_control_staleness_ms(
            run_dir, manifest, window, topic
        )
    ), None


def _bind_carla_process_cpu_pct(metrics: dict):
    label = metrics["cpu_process_label"]
    if label is None:
        return None, "cpu_process_label not registered for this cell"
    return (
        lambda run_dir, manifest, window: extract_carla_process_cpu_pct(
            run_dir, manifest, window, label
        )
    ), None


def _bind_achieved_rate_ratio(metrics: dict):
    lidar_topic, expected_hz = metrics["lidar_topic"], metrics["lidar_expected_hz"]
    missing = [
        k
        for k, v in (("lidar_topic", lidar_topic), ("lidar_expected_hz", expected_hz))
        if v is None
    ]
    if missing:
        return None, f"{', '.join(missing)} not registered for this cell"
    return (
        lambda run_dir, manifest, window: extract_achieved_rate_ratio(
            run_dir, manifest, window, lidar_topic, expected_hz
        )
    ), None


# Every margin metric this tool can bind, keyed exactly as in
# benchmarks/config/margins.yaml. A metric present in margins.yaml with
# no entry here is reported separately (build_verdict_table's
# "no registered extractor" footer) rather than silently skipped.
METRIC_BINDERS: dict[str, _Binder] = {
    "one_hop_wall_ms": _bind_one_hop_wall_ms,
    "lidar_to_ndt_sim_ms": _bind_lidar_to_ndt_sim_ms,
    "control_staleness_ms": _bind_control_staleness_ms,
    "carla_process_cpu_pct": _bind_carla_process_cpu_pct,
    "achieved_rate_ratio": _bind_achieved_rate_ratio,
}


# ---------------------------------------------------------------------------
# M2 three-way reconciliation: achieved_rate_ratio's registered companion
# output (benchmarks/README.md, achieved_rate_ratio: "the M2 three-way
# reconciliation (cadence.reconcile_drops over publisher_counts.json)
# separates publisher drop from observer loss and is reported per cell
# alongside the duel row"). This is a diagnostic, not a duel metric: no
# margin, no cross-cell equivalence verdict -- so it is reported PER CELL
# (never as an A-B delta), alongside the arm-scoped achieved_rate_ratio
# row it explains. `sweep_verdict.py` implements the same idea for the M4
# sweep, over a DIFFERENT window (clock.csv's whole-run SIM extent, no
# warm-up discard) -- the two tools share the expected-count arithmetic
# itself (`cadence.expected_count`) but not the window it is applied to,
# nor the file-reading wrapper around it: sweep_verdict's wrapper folds
# "not measurable" into a ratio/NaN pair shaped for evaluate_ceiling's
# numeric contract, which this tool has no equivalent consumer for.
# ---------------------------------------------------------------------------

# Same wording sweep_verdict.py uses for the identical condition -- a
# duplicated literal, not duplicated logic (see the block comment above).
NOT_MEASURABLE = "publisher rate not measurable (no publisher_counts.json)"


def _reconcile_run(
    run_dir: Path, window: _RunWindow, lidar_topic: str, lidar_expected_hz: float
) -> DropStats | None:
    """One run's M2 reconciliation, over the SAME resolved scoring
    window `extract_achieved_rate_ratio` uses for this run
    (`window.sim_lo`/`sim_hi`) -- not a second, independently-resolved
    window and not the whole run. The metric-definition amendment's
    most dangerous catch was exactly this tool once aggregating whole
    runs, warm-up included, instead of the registered scoring window;
    this reconciliation must not repeat that.

    Expected count: `cadence.expected_count(window_s, lidar_expected_hz)`,
    `window_s` THIS window's own SIM-domain span -- the same relation
    `sweep_verdict._expected_lidar_count` uses, applied to a different
    window (see the module-level comment above for why the two differ).

    Published count: `publisher_counts.json`'s messages for `lidar_topic`
    whose recorded SIM stamp falls in THIS SAME window -- the identical
    inclusive bounds the observed count is filtered on, per
    `publisher_counts.count_in_window`. Windowing this term is not a
    refinement of a whole-run count but a correction of a different
    quantity: against windowed expected/observed terms, a whole-run
    published count clamps `publisher_drop_rate` to 0.000 and fabricates
    `observer_loss_rate` out of the interval mismatch (owner ruling,
    2026-07-28; `benchmarks/README.md`, `achieved_rate_ratio`). A file in
    the pre-`publisher_counts/2` shape carries no stamps and so cannot be
    windowed at all: it is REFUSED by name
    (`PublisherCountsFormatError`, surfaced as this run's FAILED note),
    never silently reinterpreted as if its count were windowed.

    Valid as the publisher-side proxy for A/B cells only -- absent for
    E-cells, where the bridge is the sensor stream's only listener.
    Returns None exactly when the file is absent: "not measurable", a
    state `cadence.reconcile_drops` cannot even be asked about, and
    distinct from a present file recording a real zero (that reaches
    `reconcile_drops`'s own NaN branch instead, via the return below).

    Observed count: in-window `observer.csv` rows for `lidar_topic`,
    filtered on the sim-domain `header_stamp_ns` -- the same column and
    the same bounds `extract_achieved_rate_ratio` filters on. A `lidar_
    topic` altogether absent from this run's `observer.csv` raises
    MetricUnavailableError (mirroring `extract_achieved_rate_ratio`'s
    own requirement for the same topic on the same run) rather than
    being read as a silent zero.

    `lidar_expected_hz <= 0` raises `ValueError`, mirroring `extract_
    achieved_rate_ratio`'s own guard exactly: `expected_count` floors
    at 1 regardless of the (bad) rate, so an unguarded call would
    report a clean-looking ~0.000 publisher_drop_rate right next to
    that OTHER metric failing outright for the same cell -- a
    registered-but-invalid binding must not look healthier here than it
    does there. `_cell_reconciliation_row` already screens this cell-
    wide before calling here (cheaper, and named once instead of once
    per run); this is the defense-in-depth twin for any other caller.
    """
    if lidar_expected_hz <= 0:
        raise ValueError(f"lidar_expected_hz must be > 0, got {lidar_expected_hz}")
    run_dir = Path(run_dir)
    counts_path = run_dir / "publisher_counts.json"
    if not counts_path.is_file():
        return None
    published_count = read_publisher_counts(counts_path).count_in_window(
        lidar_topic, window.sim_lo, window.sim_hi
    )
    topics = read_observer_csv(run_dir / "observer.csv")
    if lidar_topic not in topics:
        raise MetricUnavailableError(f"{lidar_topic} not in {run_dir / 'observer.csv'}")
    stamps = topics[lidar_topic]["header_stamp_ns"]
    observed_count = int(np.count_nonzero((stamps >= window.sim_lo) & (stamps <= window.sim_hi)))
    window_s = (window.sim_hi - window.sim_lo) / 1e9
    n_expected = expected_count(window_s, lidar_expected_hz)
    return reconcile_drops(n_expected, published_count, observed_count)


@dataclass(frozen=True)
class ReconciliationRow:
    """One cell's M2 three-way reconciliation summary for one arm --
    reported alongside (never instead of, never pooled into) that arm's
    achieved_rate_ratio duel row. Computed independently PER CELL,
    unlike the duel row itself (which needs BOTH cells bound to render
    at all): a cell whose own lidar_topic/lidar_expected_hz IS
    registered still gets a useful reconciliation even when its
    counterpart's binding is null -- the current state of cell B's,
    A-hf's and B-hf's lidar_expected_hz -- so a null binding on one side
    never withholds a computable diagnostic on the other.

    `publisher_drop_rate_median`/`_max` and `observer_loss_rate_median`/
    `_max` are BOTH reported over this cell's measurable runs -- owner
    ruling, 2026-07-28 (`benchmarks/README.md`, `achieved_rate_ratio`):
    median for continuity with the campaign's per-run -> per-cell
    convention, max alongside it because this output is an instrument-
    artefact DETECTOR, not a central-tendency estimate -- at the
    registered minimum of n = 3 measurable runs, a single run that lost
    40% of its frames IS the finding, and median alone would report a
    clean 0.000 over it. Both exclude runs where `publisher_counts.json`
    was absent (`n_not_measurable`); `observer_loss_rate`'s pair
    additionally excludes runs where it was NaN (`n_zero_published`, a
    real file-backed zero-throughput run) -- reported as counts rather
    than folded silently into either statistic.

    The two axes therefore have DIFFERENT sample sizes, so both are
    printed: `n_measurable` is the publisher statistics' n, `n_observer`
    is the observer statistics' (see its own docstring).
    """

    cell: str
    arm: str
    n_measurable: int
    n_not_measurable: int
    n_zero_published: int
    publisher_drop_rate_median: float | None
    publisher_drop_rate_max: float | None
    observer_loss_rate_median: float | None  # over measurable, non-NaN runs
    observer_loss_rate_max: float | None  # over measurable, non-NaN runs
    notes: str = ""

    @property
    def n_observer(self) -> int:
        """The n behind `observer_loss_rate_median`/`_max`.

        `n_measurable` is the n behind the PUBLISHER pair only. The
        observer reduction additionally drops the runs whose
        `observer_loss_rate` is NaN (`n_zero_published`), so pairing the
        printed `n_measurable` with an observer statistic overstates its
        sample size -- by all of it when every measurable run published
        nothing. Derived rather than stored: it is a function of two
        recorded counts, and a stored third copy could disagree with
        them.
        """
        return self.n_measurable - self.n_zero_published


def _cell_reconciliation_row(
    cell_id: str,
    arm: str,
    metrics: dict,
    records: list[_RunRecord],
    *,
    n_inadmissible: int = 0,
) -> ReconciliationRow:
    """`ReconciliationRow` for one (cell, arm), from the SAME per-arm
    `records` `build_verdict_table` already walked for this cell (no
    extra directory walk) -- reusing `metrics["lidar_topic"]`/`metrics
    ["lidar_expected_hz"]`, never a second, independently-derived
    binding.

    A `None` binding, or a registered-but-invalid one (`lidar_expected_
    hz <= 0`), renders UNAVAILABLE without touching a single run
    record -- mirroring how `_bind_achieved_rate_ratio` reports a null
    binding for the duel row itself, and `extract_achieved_rate_ratio`'s
    own `expected_hz <= 0` guard for the invalid case. Screening the
    invalid case here (once, cell-wide) rather than only inside
    `_reconcile_run` (once per run) matters: without it, `expected_count`
    floors at 1 regardless of the bad rate, so this row would report a
    clean-looking ~0.000 drop rate right next to the achieved_rate_ratio
    duel row failing outright for the very same cell -- precisely the
    "plausible-looking healthy number" defect this campaign keeps
    finding.

    `n_inadmissible` is passed in (not derivable from `records`, which the
    caller already filtered) purely so this row can SAY why it has no runs.
    Without it, a cell whose only runs were bring-up/gate runs renders
    "no runs found for this arm" -- true of the filtered list but false of
    the tree, and the reader would go looking for missing directories.
    """
    lidar_topic, lidar_expected_hz = metrics["lidar_topic"], metrics["lidar_expected_hz"]
    missing = [
        k
        for k, v in (("lidar_topic", lidar_topic), ("lidar_expected_hz", lidar_expected_hz))
        if v is None
    ]
    if missing:
        return ReconciliationRow(
            cell_id,
            arm,
            0,
            0,
            0,
            None,
            None,
            None,
            None,
            f"UNAVAILABLE: {', '.join(missing)} not registered for cell {cell_id}",
        )
    if lidar_expected_hz <= 0:
        return ReconciliationRow(
            cell_id,
            arm,
            0,
            0,
            0,
            None,
            None,
            None,
            None,
            f"UNAVAILABLE: lidar_expected_hz must be > 0, got {lidar_expected_hz} "
            f"for cell {cell_id}",
        )
    drops: list[DropStats] = []
    n_not_measurable = 0
    errors: list[str] = []
    for rec in records:
        if rec.window is None:
            errors.append(f"{rec.run_dir.name}: FAILED window: {rec.window_error}")
            continue
        try:
            drop = _reconcile_run(rec.run_dir, rec.window, lidar_topic, lidar_expected_hz)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            errors.append(f"{rec.run_dir.name}: FAILED {type(exc).__name__}: {exc}")
            continue
        if drop is None:
            n_not_measurable += 1
        else:
            drops.append(drop)

    n_zero_published = sum(1 for d in drops if math.isnan(d.observer_loss_rate))
    pub_rates = [d.publisher_drop_rate for d in drops]
    pub_median = float(np.median(pub_rates)) if pub_rates else None
    pub_max = float(np.max(pub_rates)) if pub_rates else None
    non_nan_obs = [d.observer_loss_rate for d in drops if not math.isnan(d.observer_loss_rate)]
    if not drops:
        obs_median = obs_max = None
    elif non_nan_obs:
        obs_median = float(np.median(non_nan_obs))
        obs_max = float(np.max(non_nan_obs))
    else:
        # Every measurable run had published_count == 0.
        obs_median = obs_max = float("nan")

    notes: list[str] = []
    if not records:
        notes.append("no runs found for this arm")
    if n_inadmissible:
        notes.append(f"{n_inadmissible} run(s) not duel-admissible")
    if errors:
        notes.append("; ".join(errors))
    if n_not_measurable:
        notes.append(f"{n_not_measurable} run(s): {NOT_MEASURABLE}")
    if n_zero_published:
        notes.append(f"{n_zero_published} run(s) had published_count == 0 (observer_loss_rate NaN)")
    return ReconciliationRow(
        cell_id,
        arm,
        len(drops),
        n_not_measurable,
        n_zero_published,
        pub_median,
        pub_max,
        obs_median,
        obs_max,
        "; ".join(notes),
    )


def _fmt_reconciliation_rate(value: float | None) -> str:
    if value is None:
        return "-"
    if math.isnan(value):
        # Deliberate: a bare "%.3f" turns NaN into the string "nan",
        # easy to misread as "0.00" at a glance -- reconcile_drops's own
        # NaN branch is a different, real condition (see its docstring).
        # Used for EVERY rate column here, never a bare f-string, so no
        # column in this table can silently turn NaN into "0.00".
        return "NaN"
    return f"{value:.3f}"


def render_reconciliation_table(rows: list[ReconciliationRow]) -> str:
    """Markdown table for the M2 three-way reconciliation, one row PER
    CELL per arm (see `ReconciliationRow`'s docstring) -- companion to
    `render_table`'s duel rows, never merged into them. Both rate axes
    carry median AND max columns (owner ruling, 2026-07-28): median for
    continuity with the campaign's per-run -> per-cell convention, max
    so a lone high-loss run is never buried by it.

    BOTH sample sizes are columns: `n measurable` is the publisher
    pair's, `n observer` the observer pair's. The two differ by the
    zero-published runs the observer reduction drops, and a reader
    pairing one printed n with both axes would misstate the second."""
    lines = [
        "| cell | arm | n measurable | n not measurable | n zero-published "
        "| n observer | publisher_drop_rate (median) | publisher_drop_rate (max) "
        "| observer_loss_rate (median) | observer_loss_rate (max) | notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        pub_med_s = _fmt_reconciliation_rate(r.publisher_drop_rate_median)
        pub_max_s = _fmt_reconciliation_rate(r.publisher_drop_rate_max)
        obs_med_s = _fmt_reconciliation_rate(r.observer_loss_rate_median)
        obs_max_s = _fmt_reconciliation_rate(r.observer_loss_rate_max)
        lines.append(
            f"| {r.cell} | {r.arm} | {r.n_measurable} | {r.n_not_measurable} "
            f"| {r.n_zero_published} | {r.n_observer} | {pub_med_s} | {pub_max_s} "
            f"| {obs_med_s} | {obs_max_s} | {r.notes} |"
        )
    return "\n".join(lines)


def _attach_fit_residual_note(
    row: VerdictRow, records_a: list[_RunRecord], records_b: list[_RunRecord]
) -> VerdictRow:
    """Attach one_hop_wall_ms's registered fit_residual_ns context, from
    the SAME per-arm records `build_verdict_table` already walked for
    this row's metrics -- no extra directory walk, and (via `_apply_fit_
    residual`) no window resolution at all, since the fit residual does
    not need one. Any per-run failure (e.g. a run whose clock fit itself
    could not be computed) is folded into the row's notes rather than
    discarded -- a note that is simply MISSING gives no reason a reader
    could act on, whereas a run-level error mirrors exactly how the
    metric's own extractor failures are surfaced above."""
    fit_a, errors_a = _apply_fit_residual(records_a)
    fit_b, errors_b = _apply_fit_residual(records_b)
    notes = row.notes
    fit_errors = errors_a + errors_b
    if fit_errors:
        notes = _append_note(notes, "fit_residual_ns: " + "; ".join(fit_errors))
    if fit_a and fit_b:
        note = f"fit_residual_ns median: a={np.median(fit_a):.0f} b={np.median(fit_b):.0f}"
        notes = _append_note(notes, note)
    if notes == row.notes:
        return row
    return dataclasses.replace(row, notes=notes)


def _registered_arms(cells_doc: dict, cell_a_id: str, cell_b_id: str) -> list[str]:
    """Arms both cells register in cells.yaml's `arms:` list, in
    `RunManifest.ARMS` order. The duel is computed PER ARM and reported
    as separate rows, never pooled -- Task 18 runs `duel.sh --arm static
    --pairs 10` and `duel.sh --arm closed-loop --pairs 10` as two
    separate n >= 10 sessions, so pooling both arms' runs into one
    median would mix two different quantities and double-count toward
    the pre-registered n."""
    a_arms = set(cell_entry(cells_doc, cell_a_id).get("arms", []))
    b_arms = set(cell_entry(cells_doc, cell_b_id).get("arms", []))
    common = a_arms & b_arms
    return [arm for arm in ARMS if arm in common]


def build_verdict_table(
    cell_a_dir: Path,
    cell_b_dir: Path,
    cell_a_id: str,
    cell_b_id: str,
    margins: dict,
    cells_doc: dict,
    *,
    min_n: int = MIN_RUNS,
    arms: list[str] | None = None,
) -> str:
    """The full pipeline for every metric in `margins`, for the duel
    between `cell_a_id` and `cell_b_id`, reported as one row PER ARM
    (see `_registered_arms`) -- `arms` defaults to both cells' common
    registered arms (typically `["static", "closed-loop"]`) and is never
    pooled into a single cross-arm row.

    Per-cell bindings come from `cell_info.metrics_for(cells_doc, ...)`.
    A binding that is `None` for either side makes the metric UNAVAILABLE
    for the whole duel (every arm) -- reported as one row per arm
    (verdict "insufficient-data", notes explaining which binding is
    missing on which cell) WITHOUT walking either cell's run
    directories, so an unbound cell fails clearly and cheaply rather
    than as N identical per-run errors. A margin metric with no entry in
    METRIC_BINDERS at all (not expected for the five currently
    registered) is named in a trailing note instead.
    """
    metrics_a = metrics_for(cells_doc, cell_a_id)
    metrics_b = metrics_for(cells_doc, cell_b_id)
    if arms is None:
        arms = _registered_arms(cells_doc, cell_a_id, cell_b_id)
    if not arms:
        raise UnknownIdError(f"cells {cell_a_id!r} and {cell_b_id!r} share no registered arm")

    # Bound ONCE, before the arm loop: a metric's binding is a fact
    # about the cell's registered config (cells.yaml's `metrics:`
    # block), not something that varies by arm.
    bound: dict[str, tuple] = {}
    unbindable: list[str] = []
    for metric, spec in margins.items():
        binder = METRIC_BINDERS.get(metric)
        if binder is None:
            unbindable.append(metric)
            continue
        extractor_a, reason_a = binder(metrics_a)
        extractor_b, reason_b = binder(metrics_b)
        bound[metric] = (extractor_a, reason_a, extractor_b, reason_b, spec)

    rows: list[VerdictRow] = []
    reconciliation_rows: list[ReconciliationRow] = []
    for arm in arms:
        # Each cell's run-* tree for THIS arm is walked exactly once
        # here (window resolved once per run), and the resulting
        # records are reused for every metric below -- this is what
        # actually achieves README.md's "resolved once per run", unlike
        # calling cell_run_values (which re-walks) once per metric.
        records_a, excluded_a, inadmissible_a, walk_errors_a = _walk_cell_runs(
            Path(cell_a_dir), arm=arm
        )
        records_b, excluded_b, inadmissible_b, walk_errors_b = _walk_cell_runs(
            Path(cell_b_dir), arm=arm
        )
        if "achieved_rate_ratio" in margins:
            # The M2 reconciliation is achieved_rate_ratio's registered
            # companion (README.md), so it is only computed when that
            # metric is actually registered for this invocation -- reusing
            # the SAME per-arm records walked above, never a second walk.
            reconciliation_rows.append(
                _cell_reconciliation_row(
                    cell_a_id, arm, metrics_a, records_a, n_inadmissible=inadmissible_a
                )
            )
            reconciliation_rows.append(
                _cell_reconciliation_row(
                    cell_b_id, arm, metrics_b, records_b, n_inadmissible=inadmissible_b
                )
            )
        for metric, spec in margins.items():
            if metric not in bound:
                continue  # already recorded in `unbindable`, once, above
            extractor_a, reason_a, extractor_b, reason_b, spec = bound[metric]
            if extractor_a is None or extractor_b is None:
                reasons = [
                    r
                    for r in (
                        f"cell {cell_a_id}: {reason_a}" if reason_a else None,
                        f"cell {cell_b_id}: {reason_b}" if reason_b else None,
                    )
                    if r
                ]
                rows.append(
                    VerdictRow(
                        metric,
                        0,
                        0,
                        None,
                        None,
                        float(spec["margin"]),
                        "insufficient-data",
                        "UNAVAILABLE: " + "; ".join(reasons),
                        arm,
                    )
                )
                continue
            values_a, apply_errors_a = _apply_extractor(records_a, extractor_a)
            values_b, apply_errors_b = _apply_extractor(records_b, extractor_b)
            row = verdict_row(
                metric,
                values_a,
                values_b,
                float(spec["margin"]),
                min_n=min_n,
                excluded_a=excluded_a,
                excluded_b=excluded_b,
                inadmissible_a=inadmissible_a,
                inadmissible_b=inadmissible_b,
                arm=arm,
            )
            run_errors = walk_errors_a + apply_errors_a + walk_errors_b + apply_errors_b
            if run_errors:
                row = dataclasses.replace(row, notes=_append_note(row.notes, "; ".join(run_errors)))
            if metric == "one_hop_wall_ms":
                row = _attach_fit_residual_note(row, records_a, records_b)
            rows.append(row)
    out = [
        'Metric definitions: benchmarks/README.md, "Primary-duel metric definitions".',
        "",
        render_table(rows),
    ]
    if unbindable:
        out.append("")
        out.append(
            "Margin metrics with no registered extractor in this tool: "
            + ", ".join(sorted(unbindable))
        )
    if reconciliation_rows:
        out.append("")
        out.append(
            "M2 three-way reconciliation (cadence.reconcile_drops over "
            "publisher_counts.json), per cell alongside the achieved_rate_ratio "
            'duel row above (README.md, "achieved_rate_ratio"):'
        )
        out.append("")
        out.append(render_reconciliation_table(reconciliation_rows))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Primary A/B duel equivalence verdict.")
    p.add_argument("cell_a", nargs="?", default="A", help="cell id for approach A (default: A)")
    p.add_argument("cell_b", nargs="?", default="B", help="cell id for approach B (default: B)")
    p.add_argument(
        "--results",
        default="benchmarks/results",
        type=Path,
        help="results root (default: benchmarks/results)",
    )
    p.add_argument(
        "--margins",
        default=MARGINS_YAML,
        type=Path,
        help="margins.yaml path (default: benchmarks/config/margins.yaml)",
    )
    p.add_argument(
        "--cells-yaml",
        default=None,
        help="override cells.yaml (tests); default: benchmarks/config/cells.yaml",
    )
    p.add_argument(
        "--min-n",
        type=int,
        default=MIN_RUNS,
        help=f"pre-registered minimum runs per side (default: {MIN_RUNS})",
    )
    return p


EXIT_UNKNOWN_ID = 2


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    margins = load_margins(args.margins)
    cells_doc = load_cells_doc(args.cells_yaml)
    try:
        table = build_verdict_table(
            Path(args.results) / args.cell_a,
            Path(args.results) / args.cell_b,
            args.cell_a,
            args.cell_b,
            margins,
            cells_doc,
            min_n=args.min_n,
        )
    except UnknownIdError as exc:
        # Match cell_info.main's own handling: an unregistered cell id
        # (or a cell with no `metrics:` block, or one sharing no arm
        # with its counterpart) is an operator typo, not a crash.
        print(f"CELL FAIL: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN_ID
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
