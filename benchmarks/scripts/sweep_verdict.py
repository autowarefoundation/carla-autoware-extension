#!/usr/bin/env python3
"""Assemble evaluate_ceiling's inputs from a run directory into a per-point
M4 sweep ceiling verdict table.

    python3 -m benchmarks.scripts.sweep_verdict <cell> --class <id>

Ceiling scoring itself is NOT reimplemented here: `analysis/ceiling.py`'s
`evaluate_ceiling` is the single pre-registered scorer (spec: M4, four
disjuncts). This module's only job is building its inputs correctly for
each run directory under `benchmarks/results/<cell>/`:

  * paced/ablation arms: `rtf`, the per-sample-instant series from
    resources.csv (`bench_io.read_resources_csv`), deduplicated across the
    processes that share a `sample_system_ns` and with the sampler's `-1`
    "not yet measured" sentinel rows dropped (see `_rtf_series_from_resources`).
  * unpaced arm: `tick_rate_ratio`, computed directly from clock.csv's
    per-tick wall-arrival gaps against the cell's registered `tick_hz`
    (`cells.yaml`'s per-cell `metrics:` block, read via
    `cell_info.metrics_for`; see `_tick_rate_ratio_series`).
  * every arm: `publisher_rate_ratio`, from the M2 three-way reconciliation
    (`analysis/cadence.reconcile_drops`) between an expected count (window
    duration x the cell's registered `lidar_expected_hz` -- a SEPARATE
    binding from `tick_hz`: the sensor's own scan rate, not the simulator's
    step rate; see `_expected_lidar_count`), the publisher-side count in
    `publisher_counts.json` (absent for E-cells: see
    `_publisher_rate_ratio`), and the observer-side count in observer.csv.
  * every arm: `quality_ok`, read from `quality.json`'s `gate_pass` -- the
    M5 gate's own already-computed verdict (see `_quality_ok`; schema
    registered in `benchmarks/README.md`'s "M5 gate result"). This module
    does not call `analysis/quality.py`'s `evaluate_quality` itself: its
    pose/route/goal inputs are not among the files this tool reads.

`lidar_topic`, `tick_hz` and `lidar_expected_hz` all come from
`cell_info.metrics_for(doc, cell)`, the registered per-cell binding
accessor (`cells.yaml`'s `metrics:` block) -- never hardcoded and never
re-derived from a second source. A `None` binding (e.g. `lidar_expected_hz`
is unregistered for cell B pending Task 13) is a legitimate "not
pre-registered yet" state and must fail loudly where it is used, never be
silently substituted with a plausible-looking number.

Each of the three bindings has a matching CLI pair (`--topic` /
`--override-topic`, `--tick-hz` / `--override-tick-hz`,
`--lidar-expected-hz` / `--override-lidar-expected-hz`, all resolved by
`_resolve_override`): the plain form fills a `None` registry entry or must
agree with a real one, and only the explicitly-named `--override-*` form
may disagree with a real registered value -- a hand-typed flag can never
silently outvote the registry the campaign's reproducibility claim rests
on. See `_resolve_override`'s docstring.

`--class <id>` is validated against cells.yaml via `cell_info.merge` (the
same typo guard `cell_info.py` uses) but does NOT filter which run
directories get scored: the manifest schema has no per-run class field yet
(sweep-class wiring into run.sh / write_manifest.py is a separate,
not-yet-landed step). Every SWEEP-ARM run under `results/<cell>/` is scored
as belonging to `--class`'s point; campaign discipline (one class in flight
per cell at a time) is what makes that correct until that wiring lands a
real per-run class field. What IS filtered here is `arm`: `run.sh` files
every run for a cell -- duel arms (static/closed-loop) and sweep arms
(paced/unpaced/ablation) alike -- under one flat, gap-free `run-NNN/`
sequence, so a cell shared by both the P3 duel and the M4 sweep needs the
non-sweep-arm rows excluded explicitly (`main`'s `sweep_arms` filter); a
skipped count is reported rather than silently dropped.

`benchmarks/README.md`'s scoring-window section registers a per-RUN
discriminator (fittable: `clock.csv` has >= 2 rows; unfittable: fewer)
and a per-CELL expectation derived from `approach` (calibration cells
expect unfittable; every other cell expects fittable). This module does
not need the window itself (unlike `duel_verdict.py`'s M5 windowing), but
mirrors the registered EXPECTATION check (S5, Task 23's half of D10): a
run whose actual branch differs from its cell's expected one is
annotated in `render_verdicts`'s notes column via
`_window_branch_note` -- a loud finding, never a raise, and never only a
log line.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from benchmarks.analysis.bench_io import read_clock_csv, read_observer_csv, read_resources_csv
from benchmarks.analysis.cadence import reconcile_drops
from benchmarks.analysis.ceiling import CeilingVerdict, evaluate_ceiling
from benchmarks.analysis.manifest import load_manifest
from benchmarks.scripts.cell_info import UnknownIdError, load_cells_doc, merge, metrics_for

NOT_MEASURABLE = "publisher rate not measurable (no publisher_counts.json)"
NOT_APPLICABLE_ABLATION = "quality not applicable (ablation arm, no closed loop)"

EXIT_UNKNOWN_ID = 2

# benchmarks/README.md's 2026-07-28 amendment log: the owning task per
# cell for a null tick_hz binding. "tick_hz set to null on the tier4
# cells (B, D, B45) and on CAL-seam, naming Tasks 13 and 14"; and, in a
# later amendment on the same dated log, "Task 26 ('Optional cells --
# E-opt, A-hf/B-hf', owner-strikable)" named explicitly, in both
# cells.yaml and README.md, as the owner of ALL THREE rate bindings
# (tick_hz, lidar_expected_hz, ndt_expected_hz) on BOTH A-hf and B-hf --
# superseding an earlier registration this file's own S2 fix was
# originally grounded in, which the amendment found had wrongly derived
# A-hf's sensor rates from cell A's. Not itself a cells.yaml field
# (there is nowhere machine-readable to read "which task owns this gap"
# from), so this is a small, explicitly-cited transcription of those
# dated entries -- used only to make _tick_rate_ratio_series's error
# message name a real task instead of a guessed one; a cell not listed
# here (including any future one) falls back to a task-agnostic message
# rather than asserting a number that could be wrong.
#
# A "Task 12" entry for A-hf appeared briefly during this file's own
# development and was corrected before landing: cells.yaml's PRIOR text
# credited Task 12 only with the underlying --fixed-delta MECHANISM and
# named the per-cell wiring as an unnumbered "follow-on" -- there was no
# single committed "Task N" citation for A-hf's null at that time
# (checked directly against cells.yaml and README.md, not assumed from
# an out-of-repo plan document or a chat instruction, which is exactly
# the un-cited-fact failure mode this campaign keeps getting bitten by).
# Task 26 is now that citation, checked the same way.
#
# Staleness guard: this mapping is hand-maintained (not derived from the
# registry -- there is no field to derive it from), so it can silently
# drift the moment any listed cell's tick_hz is actually registered (or,
# as just happened for A-hf/B-hf, the moment the OWNING TASK NUMBER
# itself changes). test_tick_hz_pending_task_entries_are_all_still_
# actually_null pins the null side; the task-number side has no
# machine-checkable pin (no field carries it), so it stays a citation to
# verify by hand against the dated log, not a value to trust from memory.
TICK_HZ_PENDING_TASK = {
    "A-hf": 26,
    "B": 13,
    "D": 13,
    "B-hf": 26,
    "B45": 13,
    "CAL-seam": 14,
}


@dataclass(frozen=True)
class RunVerdict:
    """One run directory's assembled ceiling verdict, plus diagnostics.

    `verdict` is None only when the run is excluded: an excluded run must
    never contribute to a ceiling verdict (its data may be from a crash, a
    stalled clock, or any other pre-registered exclusion reason).
    """

    run: str
    arm: str
    excluded: bool
    exclusion_reason: str
    verdict: CeilingVerdict | None
    publisher_rate_ratio: float | None
    publisher_note: str | None
    observer_loss_rate: float
    quality_ok: bool | None
    quality_note: str | None
    window_branch_note: str | None


def _rtf_series_from_resources(resources: dict) -> tuple[np.ndarray, np.ndarray]:
    """The (sample_system_ns, rtf) series `evaluate_ceiling` wants.

    resources.csv is grouped by process; rtf is a property of the sample
    instant only and repeats across every process sharing a
    `sample_system_ns` (`bench_io.read_resources_csv`'s own docstring), so
    any one process's column already IS the series -- the
    lexicographically-first process id is picked for determinism, since
    dict order is not guaranteed across runs. Rows still holding the
    sampler's `-1` "not yet measured" sentinel (before the first /clock,
    see `sampler/finalize_rtf.py`) are dropped rather than fed in as a real
    low-RTF reading, which would read as a sustained-low-RTF dip during
    ordinary run warm-up.
    """
    if not resources:
        raise ValueError("resources.csv has no process rows")
    process = sorted(resources)[0]
    cols = resources[process]
    sample_ns, rtf = cols["sample_system_ns"], cols["rtf"]
    valid = rtf >= 0.0
    sample_ns, rtf = sample_ns[valid], rtf[valid]
    if sample_ns.size == 0:
        raise ValueError("resources.csv has no valid (non-sentinel) rtf samples")
    return sample_ns, rtf


def _tick_rate_ratio_series(
    wall_ns: np.ndarray, tick_hz: float | None, cell: str
) -> tuple[np.ndarray, np.ndarray]:
    """Per-tick achieved ticks/s as a fraction of `tick_hz` (the cell's
    registered simulator step-rate target, `metrics["tick_hz"]` -- NOT the
    sensor's own scan rate; see the module docstring for why the two are
    separate bindings).

    clock.csv has one row per /clock receipt, i.e. one row per world tick,
    so consecutive rows' wall-arrival gap directly IS the tick period: the
    instantaneous reading the spec's "sustained ticks/s" wording asks for,
    rather than a trailing-window average that would smear a sharp stall
    across samples it did not occur in. The series is one sample shorter
    than the input (the first tick has no preceding gap) and is
    timestamped at the LATER tick of each pair, matching when the rate
    becomes knowable.

    A `None` `tick_hz` (e.g. cell B/B-hf today, see `TICK_HZ_PENDING_TASK`)
    means `evaluate_ceiling` would receive BOTH `rtf=None` (the unpaced arm
    never computes it) AND `tick_rate_ratio=None` at once -- a combination
    `evaluate_ceiling` itself refuses ("need rtf ... or tick_rate_ratio,
    got neither"), because a silent skip of the sustained-throughput
    disjunct would misreport the point as "not reached": for the M4 sweep,
    that would mean claiming an approach had headroom it was never tested
    for. Raising here, loudly and by name, is the correct behaviour, not a
    workaround pending a softer one -- the message says so explicitly, so
    an operator who hits this reads "known pending dependency" and moves
    on, rather than "the tool is broken" and starts debugging this tool.
    """
    if tick_hz is None:
        task = TICK_HZ_PENDING_TASK.get(cell)
        pending = f"pending Task {task}" if task else "not yet registered"
        raise ValueError(
            f"metrics.tick_hz is null for cell {cell!r} ({pending} -- see "
            "benchmarks/config/cells.yaml's metrics: block and "
            "benchmarks/README.md's tick_hz amendment log): the unpaced "
            f"arm's tick_rate_ratio cannot be computed for cell {cell!r}, "
            "and this cell/class cannot be scored on the unpaced arm "
            "until tick_hz is registered. This is a known pending "
            "dependency, not a defect in this tool."
        )
    w = np.sort(np.asarray(wall_ns, dtype=np.int64))
    if w.size < 2:
        raise ValueError("need >= 2 clock.csv rows to compute a tick-rate series")
    gap_s = np.diff(w).astype(np.float64) / 1e9
    if np.any(gap_s <= 0):
        raise ValueError("clock.csv has non-increasing wall timestamps")
    return w[1:], (1.0 / gap_s) / tick_hz


def _expected_lidar_count(window_s: float, lidar_expected_hz: float | None) -> int:
    """Expected LiDAR message count for the M2 three-way reconciliation.

    `lidar_expected_hz` is the sensor's own expected scan rate --
    `metrics["lidar_expected_hz"]`, a per-cell binding registered
    SEPARATELY from `tick_hz` because they are different quantities in
    principle (`--fixed_delta` moves the world tick, not the rig's
    `sensor_tick`) and were briefly registered 5x apart on the
    high-frequency sensitivity cells A-hf/B-hf before that registration
    was itself found wrong and both bindings were nulled pending Task 26
    -- see `TICK_HZ_PENDING_TASK`'s comment. A `None` binding is a
    legitimate "not pre-registered yet" state (e.g. cell B's
    `lidar_expected_hz`, pending Task 13) and must fail loudly here
    rather than silently substituting a plausible-looking number --
    exactly the defect this split exists to prevent (a shared constant
    would have reported `publisher_rate_ratio ~= 0.2` and fired a
    ceiling disjunct spuriously on A-hf/B-hf, back when they diverged
    rather than being null together).
    """
    if lidar_expected_hz is None:
        raise ValueError(
            "lidar_expected_hz is not registered for this cell's metrics "
            "(None): the M4 sweep's expected LiDAR message count cannot be "
            "computed until it is filled in (see benchmarks/README.md's "
            "achieved_rate_ratio registration)"
        )
    return max(1, round(window_s * lidar_expected_hz))


def _publisher_rate_ratio(
    run_dir: Path, topic: str | None, expected_count: int
) -> tuple[float, float, str | None]:
    """publisher_rate_ratio (an `evaluate_ceiling` input) plus
    observer_loss_rate (a diagnostic only -- `evaluate_ceiling` does not
    consume it) for one run.

    `publisher_counts.json` is written by `collect_gt.py --count-lidar`
    and is valid as the publisher-side proxy for A/B cells only: for
    E-cells (python-bridge) the bridge is the sensor stream's only
    listener, so no independent publisher-side count exists and the file
    is simply absent there (plan Task 23: "the E report rows carry
    expected-vs-observed only ... marked not measurable"). Treating an
    absent file as a zero count would silently read as total publisher
    failure -- a DIFFERENT, real, file-backed condition (see the module's
    tests for both). This returns a distinct "not measurable" note and a
    ratio of 1.0 so the disjunct does not fire on the ABSENCE of evidence;
    the note is what keeps that non-firing visible rather than looking
    like a clean, measured pass.
    """
    if topic is None:
        raise ValueError(
            "lidar_topic is not registered for this cell's metrics (None): "
            "cannot compute the publisher-side three-way reconciliation"
        )
    observed = read_observer_csv(run_dir / "observer.csv").get(topic)
    observed_count = int(observed["arrival_system_ns"].size) if observed else 0

    counts_path = run_dir / "publisher_counts.json"
    if not counts_path.exists():
        return 1.0, float("nan"), NOT_MEASURABLE

    published_count = int(json.loads(counts_path.read_text())[topic])
    drop = reconcile_drops(expected_count, published_count, observed_count)
    # reconcile_drops.observer_loss_rate is NaN exactly when published_count
    # == 0: a real, file-backed zero-throughput run, distinct from the
    # "not measurable" (file absent) case above. It is returned as-is;
    # render_verdicts formats it explicitly rather than letting a bare
    # "%.2f" or an arithmetic shortcut turn it into a silent 0.0.
    return 1.0 - drop.publisher_drop_rate, drop.observer_loss_rate, None


def _quality_ok(run_dir: Path, arm: str) -> tuple[bool, str | None]:
    """The M5 gate's recorded verdict for this run (`quality.json`).

    This module does not call `analysis/quality.py`'s `evaluate_quality`
    itself: its pose/route/goal inputs are not among the files listed for
    this tool (resources.csv, clock.csv, observer.csv,
    publisher_counts.json). `quality_ok` is the M5 gate step's own
    already-computed verdict, read back here. `quality.json`'s schema is
    registered in `benchmarks/README.md`'s "M5 gate result":
    `dataclasses.asdict(QualityStats)` verbatim plus `arm`, `window_sim_ns`,
    `ladder_branch` and `expected_ndt_hz` provenance keys. `gate_pass` is
    registered as the single field a consumer may treat as the verdict, so
    this reads exactly that field and nothing else from the wider schema.

    No writer for `quality.json` exists yet (the M5 gate step is a
    separate, not-yet-landed task). On the ablation arm (publish disabled,
    no closed loop, so no M5 measurement is possible) a missing file
    defaults to True with a note. On every other arm a missing file is a
    hard error: silently assuming a pass on an arm that IS supposed to be
    closing the loop is exactly the failure mode this campaign guards
    against.
    """
    path = run_dir / "quality.json"
    if path.exists():
        return bool(json.loads(path.read_text())["gate_pass"]), None
    if arm == "ablation":
        return True, NOT_APPLICABLE_ABLATION
    raise FileNotFoundError(
        f"{path} missing: the M5 quality gate result is required to score a {arm!r} sweep point"
    )


def _expected_window_branch(approach: str) -> str:
    """The scoring-window branch a cell's `approach` is expected to take
    (benchmarks/README.md, "Expected branch per cell, so a surprise is
    loud"): calibration cells (`CAL-rmw`, `CAL-seam`) have no simulation
    loop and are expected to take the UNFITTABLE branch; every other
    approach is expected to take the FITTABLE branch.

    Derived from `approach` (`cell_info.merge`'s `merged["approach"]`),
    never from `has_sim_clock`/the `carla:` field -- `CAL-seam` is the
    README-registered discriminating case: `carla: 0.10-fork`, so
    `has_sim_clock` is true, yet it is still expected to take the
    unfittable branch (open contradiction owed to Task 14; this rule is
    correct either way because it tests approach, not the `carla:`
    field an earlier, wrong version of this rule used).
    """
    return "unfittable" if approach == "calibration" else "fittable"


def _actual_window_branch(wall_ns: np.ndarray) -> str:
    """The scoring-window branch a run's OWN `clock.csv` supports, decided
    mechanically per benchmarks/README.md: FITTABLE needs `clock.csv` to
    hold >= 2 data rows -- verbatim `analysis/clockfit.py`'s
    `fit_sim_wall_affine` precondition ("need >= 2 paired (sim, wall)
    samples") -- else UNFITTABLE. Never crashes on a short or empty
    series; it is deliberately just a size check so it can run before
    anything that WOULD crash on one (e.g. `wall_ns.max()`), and so it is
    always safe to compute this diagnostic first.
    """
    return "fittable" if wall_ns.size >= 2 else "unfittable"


def _window_branch_note(expected: str, actual: str) -> str | None:
    """None when the run took its cell's expected branch (the normal
    case, no note needed). Otherwise the mismatch, naming both branches --
    benchmarks/README.md: "A run that takes the branch its cell was not
    expected to take is a loud finding to be reported, not a silent
    fallback." Mirrors Task 22's `duel_verdict.py` (D10, the same
    registered rule); this tool has no visibility into that branch's
    actual wording (not yet landed here), so the branch-name vocabulary
    ("fittable"/"unfittable") is taken verbatim from the registration
    itself, the one source both tools read.
    """
    if expected == actual:
        return None
    return f"window branch: cell expects {expected}, this run took {actual}"


def _resolve_override(flag: str, metrics_key: str, registered, cli_value, override):
    """Resolve one CLI-overridable registered `metrics[...]` binding.

    Generalizes the Minor 15 fix (originally `_resolve_tick_hz`, `--tick-hz`
    only) to every override flag this tool exposes: `--tick-hz`,
    `--lidar-expected-hz` and `--topic`. The reasoning does not distinguish
    the three -- the campaign's reproducibility claim rests on the registry
    being what the tools actually read, and a hand-typed flag that quietly
    displaces a registered value defeats that identically in all three
    cases. Replaced the deleted `_check_paced_hz_consistency` guard, which
    stopped the old global `PACED_TICK_HZ` literal from drifting from
    `cells.yaml`; the value now comes from the registry itself, so the risk
    moved from "the constant drifts from cells.yaml" to "an operator's
    plain flag silently outvotes cells.yaml", not away.

    `override` (`--override-<flag>`) always wins, with no consistency
    check at all -- the flag name says the override is deliberate.
    Otherwise `cli_value` (`--<flag>`) is accepted when the registry has
    nothing to disagree with (`registered is None`, e.g. cell B's
    `lidar_expected_hz` pending Task 13, so `--lidar-expected-hz`
    legitimately fills a real gap) or when it agrees with the registry; a
    `cli_value` that DISAGREES with a real registered value is refused
    loudly here rather than silently winning. The three escape hatches
    (`--override-tick-hz`, `--override-lidar-expected-hz`,
    `--override-topic`) share this one naming pattern deliberately, so an
    operator who has learned one recognizes the other two as the same
    family rather than having to relearn each tool's own convention.
    """
    if override is not None:
        return override
    if cli_value is not None:
        if registered is not None and cli_value != registered:
            raise ValueError(
                f"--{flag} {cli_value!r} disagrees with the registered "
                f"metrics[{metrics_key!r}]={registered!r}; refusing to "
                "silently override a registered value -- pass "
                f"--override-{flag} {cli_value!r} instead if this is a "
                "deliberate what-if"
            )
        return cli_value
    return registered


def _peek_arm(run_dir: Path) -> str | None:
    """The run's `manifest.json` `arm`, or None if the manifest cannot be
    read at all. Used only by main's sweep-arm filter, so a run aborted
    before its manifest was ever written is treated as out-of-scope
    (skipped, counted) rather than crashing the whole cell's table."""
    try:
        return load_manifest(run_dir / "manifest.json").arm
    except (OSError, ValueError, TypeError):
        return None


def verdict_for_run(
    run_dir: Path,
    *,
    topic: str | None,
    tick_hz: float | None,
    lidar_expected_hz: float | None,
    expected_window_branch: str,
) -> RunVerdict:
    """Assemble `evaluate_ceiling`'s inputs for one run directory.

    `topic`, `tick_hz` and `lidar_expected_hz` are the cell's registered
    `metrics:` bindings (`cell_info.metrics_for`) -- callers pass them in
    explicitly (`main` resolves them per cell) rather than this function
    defaulting any of them, so an unregistered (`None`) binding cannot be
    silently papered over with a plausible-looking number.
    `expected_window_branch` is `_expected_window_branch(approach)`
    (`main` resolves it once per cell from `cell_info.merge`'s
    `merged["approach"]`); this function compares it against the run's
    own actual branch (S5, mirroring Task 22's `duel_verdict.py` D10) and
    annotates -- never raises -- on a mismatch.
    """
    run_dir = Path(run_dir)
    manifest = load_manifest(run_dir / "manifest.json")
    errs = manifest.validate()
    if errs:
        raise ValueError(f"invalid manifest {run_dir / 'manifest.json'}: {'; '.join(errs)}")

    # Excluded runs are checked before any other file is opened: an
    # excluded run's data must never enter a verdict, and an aborted run
    # legitimately may have no CSVs at all (exclusions.md: excluded runs
    # stay in the tree with whatever data they managed to write).
    if manifest.excluded:
        return RunVerdict(
            run=run_dir.name,
            arm=manifest.arm,
            excluded=True,
            exclusion_reason=manifest.exclusion_reason,
            verdict=None,
            publisher_rate_ratio=None,
            publisher_note=None,
            observer_loss_rate=float("nan"),
            quality_ok=None,
            quality_note=None,
            window_branch_note=None,
        )

    _clock_ns, wall_ns = read_clock_csv(run_dir / "clock.csv")
    # S5: computed first, from a plain size check that cannot itself
    # crash on a short or empty clock.csv (unlike window_s below) -- see
    # _actual_window_branch's own docstring.
    window_branch_note = _window_branch_note(expected_window_branch, _actual_window_branch(wall_ns))
    window_s = (int(wall_ns.max()) - int(wall_ns.min())) / 1e9
    # Applied identically on every arm (ceiling.py: "applied identically to
    # every sweep point"): the publisher-side count is expected against
    # the sensor's own registered scan rate regardless of whether the
    # TICK itself is paced this run.
    expected_count = _expected_lidar_count(window_s, lidar_expected_hz)

    # Every arm other than "unpaced" is scored via the rtf path (paced and
    # ablation both tick at the paced target; only "unpaced" substitutes
    # tick_rate_ratio, per the spec's fourth disjunct).
    if manifest.arm == "unpaced":
        sample_ns, tick_ratio = _tick_rate_ratio_series(wall_ns, tick_hz, manifest.cell)
        rtf = None
    else:
        resources = read_resources_csv(run_dir / "resources.csv")
        sample_ns, rtf = _rtf_series_from_resources(resources)
        tick_ratio = None

    pub_ratio, obs_loss, pub_note = _publisher_rate_ratio(run_dir, topic, expected_count)
    quality_ok, quality_note = _quality_ok(run_dir, manifest.arm)

    verdict = evaluate_ceiling(sample_ns, rtf, pub_ratio, quality_ok, tick_rate_ratio=tick_ratio)
    return RunVerdict(
        run=run_dir.name,
        arm=manifest.arm,
        excluded=False,
        exclusion_reason="",
        verdict=verdict,
        publisher_rate_ratio=pub_ratio,
        publisher_note=pub_note,
        observer_loss_rate=obs_loss,
        quality_ok=quality_ok,
        quality_note=quality_note,
        window_branch_note=window_branch_note,
    )


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "-"
    if math.isnan(value):
        # Deliberate: a bare "%.2f" turns NaN into the string "nan", which
        # reads close enough to "0.00" to miss at a glance; a NaN silently
        # comparing false against a threshold is exactly the failure this
        # campaign guards against (see _publisher_rate_ratio).
        return "NaN"
    return f"{value:.3f}"


def render_verdicts(
    cell: str, class_id: str, verdicts: list[RunVerdict], *, skipped_out_of_arm: int = 0
) -> str:
    """Markdown per-point verdict table.

    Pure formatting over already-assembled `RunVerdict`s: no filesystem
    access, so it is testable directly against hand-built verdicts without
    a run directory (Task 23 Step 3 design note). `skipped_out_of_arm`
    (default 0, so callers that never skip anything see unchanged output)
    reports how many `results/<cell>/run-*/` directories main() saw but did
    NOT score because their arm was not in cells.yaml's `sweep_arms` --
    e.g. a P3 duel run (static/closed-loop) filed in the same flat run-NNN/
    sequence as this cell's M4 sweep runs. Naming the count keeps that
    exclusion visible instead of it reading as "this cell has fewer runs
    than it does". The notes column also carries `window_branch_note`
    (S5): a run whose scoring window took the branch its cell was NOT
    expected to take is a loud finding here, in the artifact a reader
    sees, not only in a log.
    """
    lines = [
        f"## Sweep verdict: cell {cell}, class {class_id}",
        "",
        "| run | arm | reached | reasons | publisher_rate | observer_loss | quality_ok | notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for v in verdicts:
        if v.excluded:
            lines.append(f"| {v.run} | {v.arm} | EXCLUDED | {v.exclusion_reason} | - | - | - | - |")
            continue
        notes = (
            "; ".join(n for n in (v.publisher_note, v.quality_note, v.window_branch_note) if n)
            or "-"
        )
        lines.append(
            f"| {v.run} | {v.arm} | {v.verdict.reached} "
            f"| {'; '.join(v.verdict.reasons) or '-'} "
            f"| {_fmt_ratio(v.publisher_rate_ratio)} "
            f"| {_fmt_ratio(v.observer_loss_rate)} "
            f"| {v.quality_ok} | {notes} |"
        )
    if skipped_out_of_arm:
        lines.append("")
        lines.append(f"{skipped_out_of_arm} run(s) skipped: arm not in this cell's sweep_arms.")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Assemble the M4 sweep ceiling verdict table for one cell/class."
    )
    p.add_argument("cell", help="cell id registered in benchmarks/config/cells.yaml")
    p.add_argument(
        "--class",
        dest="class_id",
        required=True,
        metavar="ID",
        help="sweep_classes id, validated against cells.yaml",
    )
    p.add_argument(
        "--results-root",
        default=Path("benchmarks/results"),
        type=Path,
        help="root of the results tree (default: benchmarks/results)",
    )
    p.add_argument(
        "--topic",
        default=None,
        help="pointcloud topic for the publisher-side three-way reconciliation; "
        "defaults to metrics['lidar_topic']. Disagreeing with a REGISTERED "
        "value fails loudly -- see --override-topic",
    )
    p.add_argument(
        "--override-topic",
        default=None,
        help="deliberately override a REGISTERED metrics['lidar_topic']; unlike "
        "--topic this is never checked against the registry",
    )
    p.add_argument(
        "--tick-hz",
        type=float,
        default=None,
        help="tick_hz to use when metrics['tick_hz'] is unregistered (None); "
        "if metrics['tick_hz'] IS registered and this disagrees, sweep_verdict "
        "fails loudly instead of silently overriding it -- see --override-tick-hz",
    )
    p.add_argument(
        "--override-tick-hz",
        type=float,
        default=None,
        help="deliberately override a REGISTERED metrics['tick_hz'] with a "
        "different value; unlike --tick-hz this is never checked against the "
        "registry -- the flag name says the override is intentional",
    )
    p.add_argument(
        "--lidar-expected-hz",
        type=float,
        default=None,
        help="lidar_expected_hz to use when metrics['lidar_expected_hz'] is "
        "unregistered (None); disagreeing with a REGISTERED value fails "
        "loudly -- see --override-lidar-expected-hz",
    )
    p.add_argument(
        "--override-lidar-expected-hz",
        type=float,
        default=None,
        help="deliberately override a REGISTERED metrics['lidar_expected_hz']; "
        "unlike --lidar-expected-hz this is never checked against the registry",
    )
    p.add_argument("--cells-yaml", default=None, help="override cells.yaml (tests)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    doc = load_cells_doc(args.cells_yaml)
    # Typo guard + cell/class registration check, reusing cell_info's own
    # validated lookup rather than re-parsing cells.yaml a second way.
    try:
        merged = merge(doc, args.cell, args.class_id)
        metrics = metrics_for(doc, args.cell)
    except UnknownIdError as exc:
        print(f"SWEEP_VERDICT FAIL: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN_ID

    sweep_arms = set(merged.get("sweep_arms") or [])
    # `metrics_for` is the single registered source for all three bindings
    # (cell_info.metrics_for docstring). All three go through
    # `_resolve_override` (Minor 15, generalized to `topic` and
    # `lidar_expected_hz` too): a plain `--<flag>` that disagrees with a
    # REGISTERED value is refused rather than silently winning, so a
    # hand-typed number can never quietly displace the registry the
    # campaign's reproducibility claim rests on; the matching
    # `--override-<flag>` is each one's explicit escape hatch.
    topic = _resolve_override(
        "topic", "lidar_topic", metrics["lidar_topic"], args.topic, args.override_topic
    )
    tick_hz = _resolve_override(
        "tick-hz", "tick_hz", metrics["tick_hz"], args.tick_hz, args.override_tick_hz
    )
    lidar_expected_hz = _resolve_override(
        "lidar-expected-hz",
        "lidar_expected_hz",
        metrics["lidar_expected_hz"],
        args.lidar_expected_hz,
        args.override_lidar_expected_hz,
    )
    # S5: the cell's expected scoring-window branch, resolved once (it is
    # a cell property, same for every run scored this invocation) from
    # `merged["approach"]` -- never from `has_sim_clock`/`carla:`, per
    # `_expected_window_branch`'s own docstring.
    expected_window_branch = _expected_window_branch(merged["approach"])

    cell_dir = args.results_root / args.cell
    verdicts = []
    skipped = 0
    for run_dir in sorted(cell_dir.glob("run-*")):
        if _peek_arm(run_dir) not in sweep_arms:
            skipped += 1
            continue
        verdicts.append(
            verdict_for_run(
                run_dir,
                topic=topic,
                tick_hz=tick_hz,
                lidar_expected_hz=lidar_expected_hz,
                expected_window_branch=expected_window_branch,
            )
        )
    print(render_verdicts(args.cell, args.class_id, verdicts, skipped_out_of_arm=skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
