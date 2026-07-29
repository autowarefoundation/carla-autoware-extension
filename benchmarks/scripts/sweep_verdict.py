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
    per-tick wall-arrival gaps against `PACED_TICK_HZ` (see its docstring
    for why this is a literal rather than a config read).
  * every arm: `publisher_rate_ratio`, from the M2 three-way reconciliation
    (`analysis/cadence.reconcile_drops`) between an expected count (window
    duration x `PACED_TICK_HZ`), the publisher-side count in
    `publisher_counts.json` (absent for E-cells: see
    `_publisher_rate_ratio`), and the observer-side count in observer.csv.
  * every arm: `quality_ok`, read from `quality.json`'s `gate_pass` -- the
    M5 gate's own already-computed verdict (see `_quality_ok`). This module
    does not call `analysis/quality.py`'s `evaluate_quality` itself: its
    pose/route/goal inputs are not among the files this tool reads.

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
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from benchmarks.analysis.bench_io import read_clock_csv, read_observer_csv, read_resources_csv
from benchmarks.analysis.cadence import reconcile_drops
from benchmarks.analysis.ceiling import CeilingVerdict, evaluate_ceiling
from benchmarks.analysis.manifest import load_manifest
from benchmarks.scripts.cell_info import UnknownIdError, load_cells_doc, merge
from benchmarks.scripts.collect_gt import DEFAULT_LIDAR_TOPIC

# The M4 sweep's paced tick target (spec: M4). cells.yaml carries this only
# indirectly -- camera_classes[*].fps is 20 in every entry, with a comment
# equating it to "the 20 Hz tick ceiling" -- and no dedicated tick-rate
# field exists yet (no physics.yaml in this tree), so this is a literal,
# flagged here rather than silently hardcoded elsewhere.
# `_check_paced_hz_consistency` asserts this literal cannot drift from the
# camera_classes fps values without being caught; `--paced-hz` overrides it
# if a dedicated config value takes over later.
PACED_TICK_HZ = 20.0

# observer_topics/<cell>.yaml is the committed source of truth for a cell's
# LiDAR topic name (already consumed by run.sh and cells/calibration.sh);
# `_lidar_topic_for_cell` reads it. `DEFAULT_LIDAR_TOPIC` (collect_gt.py's
# own constant, the key it writes publisher_counts.json under) is the
# fallback for a cell whose file is absent or has no PointCloud2 entry
# (e.g. CAL-seam, deliberately empty pending Task 14).
OBSERVER_TOPICS_DIR = Path(__file__).resolve().parent.parent / "config" / "observer_topics"
POINTCLOUD_TYPE = "sensor_msgs/msg/PointCloud2"

NOT_MEASURABLE = "publisher rate not measurable (no publisher_counts.json)"
NOT_APPLICABLE_ABLATION = "quality not applicable (ablation arm, no closed loop)"

EXIT_UNKNOWN_ID = 2


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


def _tick_rate_ratio_series(wall_ns: np.ndarray, paced_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Per-tick achieved ticks/s as a fraction of `paced_hz`.

    clock.csv has one row per /clock receipt, i.e. one row per world tick,
    so consecutive rows' wall-arrival gap directly IS the tick period: the
    instantaneous reading the spec's "sustained ticks/s" wording asks for,
    rather than a trailing-window average that would smear a sharp stall
    across samples it did not occur in. The series is one sample shorter
    than the input (the first tick has no preceding gap) and is
    timestamped at the LATER tick of each pair, matching when the rate
    becomes knowable.
    """
    w = np.sort(np.asarray(wall_ns, dtype=np.int64))
    if w.size < 2:
        raise ValueError("need >= 2 clock.csv rows to compute a tick-rate series")
    gap_s = np.diff(w).astype(np.float64) / 1e9
    if np.any(gap_s <= 0):
        raise ValueError("clock.csv has non-increasing wall timestamps")
    return w[1:], (1.0 / gap_s) / paced_hz


def _publisher_rate_ratio(
    run_dir: Path, topic: str, expected_count: int
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
    already-computed verdict, read back here. `quality.json` is this
    tool's minimal contract for that verdict --
    `{"gate_pass": bool, "reasons": [...]}`, mirroring
    `dataclasses.asdict(QualityStats)`'s key field -- pending whichever
    task lands the actual M5-gate writer.

    On the ablation arm (publish disabled, no closed loop, so no M5
    measurement is possible) a missing file defaults to True with a note.
    On every other arm a missing file is a hard error: silently assuming a
    pass on an arm that IS supposed to be closing the loop is exactly the
    failure mode this campaign guards against.
    """
    path = run_dir / "quality.json"
    if path.exists():
        return bool(json.loads(path.read_text())["gate_pass"]), None
    if arm == "ablation":
        return True, NOT_APPLICABLE_ABLATION
    raise FileNotFoundError(
        f"{path} missing: the M5 quality gate result is required to score a {arm!r} sweep point"
    )


def _lidar_topic_for_cell(cell: str, observer_topics_dir: Path | None = None) -> str:
    """The LiDAR pointcloud topic name for `cell`.

    Reads `observer_topics/<cell>.yaml` (a ROS 2 params file: `/**:
    ros__parameters: topics: ["<topic>|<type>|<kind>", ...]`, the same file
    `run.sh` and `cells/calibration.sh` already consume) and returns the
    first entry whose type is `sensor_msgs/msg/PointCloud2`. Falls back to
    `collect_gt.DEFAULT_LIDAR_TOPIC` when the file is missing or carries no
    such entry (e.g. CAL-seam's deliberately-empty topic list) -- never to
    a made-up literal.
    """
    path = (observer_topics_dir or OBSERVER_TOPICS_DIR) / f"{cell}.yaml"
    if path.exists():
        doc = yaml.safe_load(path.read_text()) or {}
        params = ((doc.get("/**") or {}).get("ros__parameters")) or {}
        for entry in params.get("topics") or []:
            name, _, rest = str(entry).partition("|")
            msg_type = rest.split("|", 1)[0]
            if msg_type == POINTCLOUD_TYPE:
                return name
    return DEFAULT_LIDAR_TOPIC


def _check_paced_hz_consistency(doc: dict, paced_hz: float) -> None:
    """Refuse to silently drift `PACED_TICK_HZ` away from cells.yaml's
    camera_classes fps entries, the one place cells.yaml machine-encodes
    the 20 Hz tick ceiling (see PACED_TICK_HZ's own docstring). Only
    checked when `paced_hz` is still the module default: an explicit
    `--paced-hz` override is a deliberate what-if the operator asked for,
    not a claim about camera_classes.
    """
    if paced_hz != PACED_TICK_HZ:
        return
    for entry in doc.get("camera_classes") or []:
        fps = entry.get("fps")
        if fps is not None and fps != paced_hz:
            raise ValueError(
                f"PACED_TICK_HZ={paced_hz} no longer matches cells.yaml "
                f"camera_classes {entry.get('id')!r} fps={fps}; update one "
                "to match the other (see PACED_TICK_HZ's docstring)"
            )


def _peek_arm(run_dir: Path) -> str | None:
    """The run's `manifest.json` `arm`, or None if the manifest cannot be
    read at all. Used only by main's sweep-arm filter, so a run aborted
    before its manifest was ever written is treated as out-of-scope
    (skipped, counted) rather than crashing the whole cell's table."""
    try:
        return load_manifest(run_dir / "manifest.json").arm
    except (OSError, ValueError, TypeError):
        return None


def verdict_for_run(run_dir: Path, *, topic: str, paced_hz: float = PACED_TICK_HZ) -> RunVerdict:
    """Assemble `evaluate_ceiling`'s inputs for one run directory."""
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
        )

    _clock_ns, wall_ns = read_clock_csv(run_dir / "clock.csv")
    window_s = (int(wall_ns.max()) - int(wall_ns.min())) / 1e9
    # The registered scan-rate target, applied identically on every arm
    # (ceiling.py: "applied identically to every sweep point"): the
    # publisher-side count is expected against the same paced target
    # regardless of whether the TICK itself is paced this run.
    expected_count = max(1, round(window_s * paced_hz))

    # Every arm other than "unpaced" is scored via the rtf path (paced and
    # ablation both tick at the paced target; only "unpaced" substitutes
    # tick_rate_ratio, per the spec's fourth disjunct).
    if manifest.arm == "unpaced":
        sample_ns, tick_ratio = _tick_rate_ratio_series(wall_ns, paced_hz)
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
    than it does".
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
        notes = "; ".join(n for n in (v.publisher_note, v.quality_note) if n) or "-"
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
        "defaults to the cell's observer_topics/<cell>.yaml entry",
    )
    p.add_argument("--paced-hz", type=float, default=PACED_TICK_HZ)
    p.add_argument("--cells-yaml", default=None, help="override cells.yaml (tests)")
    p.add_argument(
        "--observer-topics-dir", default=None, type=Path, help="override observer_topics/ (tests)"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    doc = load_cells_doc(args.cells_yaml)
    # Typo guard + cell/class registration check, reusing cell_info's own
    # validated lookup rather than re-parsing cells.yaml a second way.
    try:
        merged = merge(doc, args.cell, args.class_id)
    except UnknownIdError as exc:
        print(f"SWEEP_VERDICT FAIL: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN_ID
    _check_paced_hz_consistency(doc, args.paced_hz)

    sweep_arms = set(merged.get("sweep_arms") or [])
    topic = args.topic or _lidar_topic_for_cell(args.cell, args.observer_topics_dir)

    cell_dir = args.results_root / args.cell
    verdicts = []
    skipped = 0
    for run_dir in sorted(cell_dir.glob("run-*")):
        if _peek_arm(run_dir) not in sweep_arms:
            skipped += 1
            continue
        verdicts.append(verdict_for_run(run_dir, topic=topic, paced_hz=args.paced_hz))
    print(render_verdicts(args.cell, args.class_id, verdicts, skipped_out_of_arm=skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
