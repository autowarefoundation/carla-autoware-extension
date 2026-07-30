#!/usr/bin/env python3
"""The M5 gate step: assemble `evaluate_quality`'s inputs for one run
directory and write its `quality.json`.

    python3 -m benchmarks.scripts.write_quality --run-dir <results/.../run-NNN>

`quality.json` is the M5 gate's recorded verdict for a run, pre-registered in
`benchmarks/README.md` ("M5 gate result"): `dataclasses.asdict(QualityStats)`
verbatim plus four provenance keys (`arm`, `window_sim_ns`, `ladder_branch`,
`expected_ndt_hz`). It is a recorded FACT of the run, written once at run time
by `run.sh`, not recomputed by each consumer -- so the verdict is tied to the
analysis code the manifest's `harness_git_sha` names, and two consumers cannot
disagree about it. `gate_pass` is the single field a consumer may treat as the
verdict; `scripts/sweep_verdict.py` reads exactly that.

Scoring itself is NOT reimplemented here. `analysis/quality.py`'s
`evaluate_quality` is the single pre-registered scorer and
`analysis/window.py`'s `spatial_window`/`static_window` are the single
pre-registered windows. This module's only job is building their inputs from
the run's own committed files:

  * `pose.csv` rows for the cell's registered `ndt_topic` -- the NDT pose,
    recorded by bench_observer's typed `pose` subscription. NOT
    `odometry.csv`'s `/localization/kinematic_state`, which is the EKF-fused
    pose: scoring `pose_error` on that would mask NDT error behind
    IMU/odometry fusion (README, "M5 definitions").
  * `gt.csv` -- the CARLA ground truth, joined to the NDT series at nearest
    sim stamp within `quality.JOIN_TOL_NS`.
  * `odometry.csv` rows for `/localization/kinematic_state` -- the ego track
    the goal and lateral-deviation metrics are computed on, and the series
    the closed-loop spatial window is resolved against.
  * `config/routes/<map>.yaml` -- the committed route polyline, its station
    bounds, and the goal pose.
  * `cells.yaml`'s per-cell `metrics:` block (via `cell_info.metrics_for`):
    `ndt_topic`, `ndt_expected_hz`, and the two ladder keys. No topic, rate
    or threshold is hardcoded here.

REFUSALS. Every input this step cannot resolve aborts by name and writes
nothing, rather than defaulting: a `quality.json` that exists is a scored
verdict, so an absent one has to mean "not scored". The consumer side already
depends on that -- `sweep_verdict._quality_ok` treats a missing file as a hard
error on any arm that closes the loop, precisely so an ungated run cannot read
as a passing one. The refusals are:

  * `metrics.ladder_branch` is null -> no G1 ladder branch is selected for
    this cell yet (Task 11's live re-gate selects it). Defaulting to the
    relative branch is what `evaluate_quality(abs_pose_gate_m=None)` would
    silently do, and it would report an UNGATED cell as gated.
  * the ladder registration is internally inconsistent (`absolute` with no
    threshold, `relative` with one, an unrecognised branch name).
  * `metrics.ndt_expected_hz` is null -- README: "A cell whose
    `ndt_expected_hz` is null cannot be gated: the M5 gate must refuse to
    write a verdict for it rather than assume a rate."
  * `metrics.ndt_topic` is null, or that topic has no rows in `pose.csv`.
  * any required file is missing or unreadable (`pose.csv`, `gt.csv`,
    `odometry.csv`, `clock.csv`, the route file).
  * the run's `clock.csv` holds fewer than 2 rows on a non-closed-loop arm:
    that is the README's UNFITTABLE branch, which has no sim domain at all,
    so no sim window exists to convert to. A cell that takes it (the
    calibration cells) has no localization stack and no `ndt_expected_hz`
    either, so this refusal is a backstop, not the normal path.
  * the manifest is already marked excluded -- excluded data must not be
    scored (`exclusions.md`; `sweep_verdict` short-circuits such runs before
    reading this file at all).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import yaml

from benchmarks.analysis.bench_io import (
    read_clock_csv,
    read_gt_csv,
    read_odometry_csv,
    read_pose_csv,
)
from benchmarks.analysis.clockfit import fit_sim_wall_affine
from benchmarks.analysis.manifest import RunManifest, load_manifest
from benchmarks.analysis.quality import evaluate_quality
from benchmarks.analysis.window import spatial_window, static_window
from benchmarks.scripts.cell_info import UnknownIdError, load_cells_doc, metrics_for

ROUTES_DIR = Path(__file__).resolve().parent.parent / "config" / "routes"

# Scoring-window warm-up discard (README, "Scoring window"): 20 s, in ns.
# The same int `duel_verdict.WARMUP_NS` carries, and the same value the
# README pins as `window.py`'s `warmup_ns` argument throughout.
WARMUP_NS = 20_000_000_000

# The odometry topic the closed-loop scoring window is resolved against, and
# the ego track the goal/lateral metrics are computed on. Registered in
# README prose ("spatial_window over odometry.csv's
# /localization/kinematic_state rows") rather than as a cells.yaml binding,
# so it is a literal here exactly as it is in `duel_verdict.py`.
ODOM_TOPIC = "/localization/kinematic_state"

# The two registered G1 ladder branches (README, "M5 definitions"). A
# `ladder_branch` outside this set is an inconsistent registration, not a
# third branch.
LADDER_BRANCHES = ("absolute", "relative")

QUALITY_JSON = "quality.json"

EXIT_REFUSED = 2


class GateRefused(RuntimeError):
    """The M5 gate cannot score this run, and says why instead of guessing.

    Every raise site names the input it could not resolve. Nothing is
    written when this is raised: an absent `quality.json` means "not
    scored", which is the state every consumer is already built to fail
    loudly on for an arm that closes the loop.
    """


def _read_or_refuse(reader, path: Path, what: str):
    """`reader(path)`, turning an unreadable file into a named refusal.

    A bare OSError/KeyError from deep inside a CSV reader names the file but
    not what the gate wanted it for, and this step runs unattended inside
    `run.sh` where that difference is the whole diagnostic.
    """
    try:
        return reader(path)
    except OSError as exc:
        raise GateRefused(f"cannot read {what} ({path}): {exc}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        # TypeError covers a manifest whose JSON no longer matches
        # `RunManifest`'s fields -- `load_manifest` splats the document into the
        # dataclass, so a renamed or missing key surfaces there and nowhere
        # else. Same three exception types `sweep_verdict._peek_arm` treats as
        # "this manifest cannot be read".
        raise GateRefused(f"{what} ({path}) does not match its contract: {exc}") from exc


def resolve_ladder(metrics: dict, cell: str) -> tuple[str, float | None]:
    """(`ladder_branch`, `abs_pose_gate_m`) for `evaluate_quality`, or a
    refusal.

    The two keys are one binding in two fields, for the reason cells.yaml's
    header block records: `evaluate_quality(abs_pose_gate_m=None)` IS the
    relative branch, so a lone nullable threshold could not tell a selected
    relative branch from an unselected cell -- and the second must refuse.
    Three registered states, everything else refused by name:

      absolute + float -> absolute branch, that threshold
      relative + null  -> relative branch (no-drift + bounded-spread)
      null             -> refuse
    """
    branch = metrics["ladder_branch"]
    gate = metrics["abs_pose_gate_m"]
    if branch is None:
        raise GateRefused(
            f"metrics.ladder_branch is null for cell {cell!r}: no G1 ladder "
            "branch is selected for the map bundle this cell localizes "
            "against, so the M5 gate has no localization criterion to apply. "
            "Plan Task 11's live G1 re-gate selects it ('absolute' with "
            "abs_pose_gate_m, or 'relative'). This refusal is deliberate: "
            "the relative branch is what evaluate_quality would apply by "
            "default, which would record an UNGATED cell as gated. See "
            "benchmarks/config/cells.yaml's metrics: header block."
        )
    if branch not in LADDER_BRANCHES:
        raise GateRefused(
            f"metrics.ladder_branch is {branch!r} for cell {cell!r}; the "
            f"registered branches are {LADDER_BRANCHES}"
        )
    if branch == "absolute":
        if gate is None:
            raise GateRefused(
                f"cell {cell!r} registers ladder_branch 'absolute' with a "
                "null abs_pose_gate_m: the absolute branch IS a threshold on "
                "max pose_error, so there is nothing to gate on. Register the "
                "threshold or select the relative branch."
            )
        return branch, float(gate)
    if gate is not None:
        raise GateRefused(
            f"cell {cell!r} registers ladder_branch 'relative' with "
            f"abs_pose_gate_m {gate!r}: the relative branch applies no "
            "absolute threshold, so a registered one would be silently "
            "ignored. Drop it, or select the absolute branch."
        )
    return branch, None


def load_route(map_name: str) -> tuple[np.ndarray, float, float, np.ndarray]:
    """(route_xy, start_station_m, end_station_m, goal_xy) from
    `config/routes/<map>.yaml` -- the committed polyline, its pre-registered
    station bounds and the run's goal pose."""
    path = ROUTES_DIR / f"{map_name}.yaml"
    if not path.is_file():
        raise GateRefused(f"no route file for map {map_name!r} at {path}")
    doc = yaml.safe_load(path.read_text())
    try:
        route_xy = np.asarray(doc["polyline"], dtype=np.float64)
        stations = doc["stations"]
        goal = doc["goal"]
        return (
            route_xy,
            float(stations["start_m"]),
            float(stations["end_m"]),
            np.asarray([float(goal["x"]), float(goal["y"])], dtype=np.float64),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GateRefused(f"route file {path} is missing a required field: {exc}") from exc


def resolve_window_sim_ns(
    run_dir: Path, manifest: RunManifest, odom: dict, route_xy, start_m: float, end_m: float
) -> tuple[int, int]:
    """The run's scoring window in SIM ns, per README's "Scoring windows".

    closed-loop arm: `window.spatial_window` over `odometry.csv`'s
    `/localization/kinematic_state` rows against the route polyline and the
    route file's station bounds -- already SIM ns, since those are header
    stamps, so no conversion is applied.

    every other arm: `window.static_window` over `clock.csv`'s wall arrivals
    (first and last row, i.e. min/max of a monotone series -- the same bounds
    `duel_verdict._resolve_window` takes), then converted into the sim domain
    through the run's own affine fit by the README's registered inverse,
    `(wall_ns - intercept_ns) / slope`. The conversion is required rather
    than cosmetic: both series this gate filters (`pose.csv`, `odometry.csv`)
    carry SIM header stamps, and `quality.json`'s registered
    `window_sim_ns` is a sim-domain pair.

    A `clock.csv` with fewer than 2 rows is the README's UNFITTABLE branch.
    It has no sim domain at all, so there is no window to convert and none is
    invented.
    """
    if manifest.arm == "closed-loop":
        try:
            lo, hi = spatial_window(
                odom["header_stamp_ns"],
                np.stack([odom["x_m"], odom["y_m"]], axis=1),
                route_xy,
                start_m,
                end_m,
                WARMUP_NS,
            )
        except ValueError as exc:
            raise GateRefused(f"cannot resolve the closed-loop spatial window: {exc}") from exc
        return int(lo), int(hi)

    clock_ns, clock_wall = _read_or_refuse(
        read_clock_csv, run_dir / "clock.csv", "the /clock series"
    )
    if clock_ns.size < 2:
        raise GateRefused(
            f"clock.csv holds {clock_ns.size} data row(s): this run took the "
            "UNFITTABLE scoring-window branch (README: fewer than 2 rows), "
            "which has no simulation-time domain, so the "
            f"{manifest.arm!r} arm's window cannot be expressed in the sim "
            "stamps pose.csv and odometry.csv carry"
        )
    fit = fit_sim_wall_affine(clock_ns, clock_wall)
    try:
        wall_lo, wall_hi = static_window(int(clock_wall.min()), int(clock_wall.max()), WARMUP_NS)
    except ValueError as exc:
        raise GateRefused(f"cannot resolve the {manifest.arm!r} static window: {exc}") from exc
    return (
        int(round((wall_lo - fit.intercept_ns) / fit.slope)),
        int(round((wall_hi - fit.intercept_ns) / fit.slope)),
    )


def build_quality(run_dir: Path, *, cells_yaml: str | None = None) -> dict:
    """The `quality.json` document for `run_dir`, or a `GateRefused`.

    Pure: reads the run's files and the registry, computes, returns. The
    caller writes -- so a refusal cannot leave a half-written verdict behind.
    """
    run_dir = Path(run_dir)
    manifest = _read_or_refuse(load_manifest, run_dir / "manifest.json", "the run manifest")
    if manifest.excluded:
        raise GateRefused(
            f"{run_dir.name} is already marked excluded "
            f"({manifest.exclusion_reason!r}): excluded data is not scored, so "
            "no M5 verdict is written for it"
        )

    try:
        metrics = metrics_for(load_cells_doc(cells_yaml), manifest.cell)
    except UnknownIdError as exc:
        raise GateRefused(str(exc)) from exc

    branch, abs_gate = resolve_ladder(metrics, manifest.cell)

    expected_ndt_hz = metrics["ndt_expected_hz"]
    if expected_ndt_hz is None:
        raise GateRefused(
            f"metrics.ndt_expected_hz is null for cell {manifest.cell!r}: it "
            "is the divisor of the gate's 'NDT rate >= 90% of expected' "
            "criterion, and README registers that such a cell cannot be "
            "gated rather than gated against an assumed rate"
        )
    ndt_topic = metrics["ndt_topic"]
    if ndt_topic is None:
        raise GateRefused(
            f"metrics.ndt_topic is null for cell {manifest.cell!r}: there is "
            "no registered topic to read the NDT pose from"
        )

    pose = _read_or_refuse(read_pose_csv, run_dir / "pose.csv", "the NDT pose series")
    if ndt_topic not in pose:
        raise GateRefused(
            f"{ndt_topic} has no rows in {run_dir / 'pose.csv'}: the NDT pose "
            "was never recorded, so pose_error has no data source. Check that "
            f"config/observer_topics/{manifest.cell}.yaml registers it with "
            "the typed `pose` kind and that the observer image carries that "
            "kind"
        )
    odom_all = _read_or_refuse(read_odometry_csv, run_dir / "odometry.csv", "the ego odometry")
    if ODOM_TOPIC not in odom_all:
        raise GateRefused(f"{ODOM_TOPIC} has no rows in {run_dir / 'odometry.csv'}")
    odom = odom_all[ODOM_TOPIC]
    gt = _read_or_refuse(read_gt_csv, run_dir / "gt.csv", "the M5 ground truth")
    if gt["sim_ns"].size == 0:
        raise GateRefused(f"{run_dir / 'gt.csv'} has no data rows: no M5 ground truth")
    if np.any(np.diff(gt["sim_ns"]) < 0):
        raise GateRefused(
            f"{run_dir / 'gt.csv'}'s sim_ns column is not non-decreasing; the "
            "nearest-stamp join searches it as a sorted series, so out-of-"
            "order rows would pair NDT poses with the wrong ground truth"
        )

    route_xy, start_m, end_m, goal_xy = load_route(manifest.map_name)
    lo, hi = resolve_window_sim_ns(run_dir, manifest, odom, route_xy, start_m, end_m)

    # A ValueError out of the scorer is a real "this run does not support the
    # measurement" (too few NDT<->GT pairs in the window, an empty ego track),
    # and it must land as a named refusal with NO file written -- same
    # not-scored state as an unresolved input, never a written verdict built
    # from whatever survived.
    try:
        stats = evaluate_quality(
            ndt_stamp_ns=pose[ndt_topic]["header_stamp_ns"],
            ndt_xy=np.stack([pose[ndt_topic]["x_m"], pose[ndt_topic]["y_m"]], axis=1),
            gt_sim_ns=gt["sim_ns"],
            gt_xy=np.stack([gt["x_m"], gt["y_m"]], axis=1),
            odom_stamp_ns=odom["header_stamp_ns"],
            odom_xy=np.stack([odom["x_m"], odom["y_m"]], axis=1),
            route_xy=route_xy,
            goal_xy=goal_xy,
            window=(lo, hi),
            expected_ndt_hz=float(expected_ndt_hz),
            abs_pose_gate_m=abs_gate,
        )
    except (ValueError, IndexError) as exc:
        raise GateRefused(
            f"evaluate_quality could not score {run_dir.name} over the "
            f"window [{lo}, {hi}] sim ns: {exc}"
        ) from exc

    # asdict first, then the four provenance keys -- exactly the registered
    # order and shape (README, "M5 gate result"). `ladder_branch` comes from
    # the REGISTRY, never from `abs_gate is None`: inferring it would make an
    # unselected cell read as a deliberate relative-branch scoring.
    doc = dataclasses.asdict(stats)
    doc["arm"] = manifest.arm
    doc["window_sim_ns"] = [lo, hi]
    doc["ladder_branch"] = branch
    doc["expected_ndt_hz"] = float(expected_ndt_hz)
    return doc


def write_quality(run_dir: Path, *, cells_yaml: str | None = None) -> Path:
    """Build and write `<run_dir>/quality.json`; returns its path."""
    doc = build_quality(run_dir, cells_yaml=cells_yaml)
    path = Path(run_dir) / QUALITY_JSON
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Write one run directory's M5 gate verdict (quality.json)."
    )
    p.add_argument("--run-dir", required=True, type=Path, help="a results/<cell>/run-NNN directory")
    p.add_argument("--cells-yaml", default=None, help="override cells.yaml (tests)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        path = write_quality(args.run_dir, cells_yaml=args.cells_yaml)
    except GateRefused as exc:
        # Named, non-zero, and no file written. run.sh treats this as a
        # warning rather than an abort (see its M5 gate step): a run that
        # cannot be gated must still be filed and labelled by the exclusion
        # step that follows, and the absent quality.json is what stops a
        # consumer reading it as a pass.
        print(f"QUALITY GATE FAIL: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    doc = json.loads(path.read_text())
    print(
        f"{path}: gate_pass={doc['gate_pass']} branch={doc['ladder_branch']} "
        f"ndt_rate_ratio={doc['ndt_rate_ratio']:.3f} "
        f"pose_err_max_m={doc['pose_err_max_m']:.3f}"
        + (f" reasons={'; '.join(doc['reasons'])}" if doc["reasons"] else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
