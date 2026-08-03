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
    # Validated on the way IN as well as on the way out (RunManifest.save): a
    # manifest can reach here hand-edited or written by an older harness, and
    # an unregistered cell or a missing transport key must not render as a
    # table row that reads exactly like a scored one.
    errs = manifest.validate()
    if errs:
        raise ValueError(f"invalid manifest {run_dir / 'manifest.json'}: {'; '.join(errs)}")
    clock_ns, clock_wall = read_clock_csv(run_dir / "clock.csv")
    fit = fit_sim_wall_affine(clock_ns, clock_wall)
    # KNOWN TRAP for CAL-seam, registered 2026-08-03 (P4 whole-branch review,
    # benchmarks/README.md "Expected branch per cell"). This fit is applied
    # below to EVERY topic's `header_stamp_ns`, and it is a sim->wall map. The
    # CAL-seam cell reaches this renderer -- `cells.yaml` gives it `carla:
    # 0.10-fork`, so `has_sim_clock` is true and run.sh step 15 routes it here
    # rather than to `cal_report.py` -- but its two bench publishers
    # (`/bench/seam_cloud`, `/bench/incore_cloud`) stamp `header.stamp` with
    # WALL `now()`. Mapping a wall stamp through a sim->wall affine yields a
    # finite, plausible-looking `one_hop_p50_ms` that is NOT a latency, with no
    # exception and nothing in the table to mark it. It is the campaign's one
    # registered path that produces a wrong number instead of a loud failure,
    # so it is written here as well as in the README: whoever reads a CAL-seam
    # report is reading this function's output.
    #
    # `C1(a)` -- the paired seam-vs-in-core delta -- SURVIVES it: both topics
    # are stamped the same way and go through the same fit in the same run, so
    # the mapping is common-mode and cancels. Neither topic's absolute
    # `one_hop_p50_ms`/`one_hop_p99_ms` may be quoted as a one-hop latency, and
    # neither may be compared against a sim-stamped cell's number. Do not
    # "fix" this by special-casing the cell here: `analysis/**` is frozen, the
    # delta is what CAL-seam exists to produce, and a silent per-cell branch in
    # the shared renderer would be a worse trap than the disclosed one.
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


def _best_effort_excluded(run_dir: Path) -> bool:
    """Read `excluded` off a run's manifest without raising.

    Used only to label a row that ALREADY failed to render for some other
    reason (see render_cell below): a manifest that cannot even be read
    (missing, unparsable, pre-P0 schema) is reported as not-known-excluded
    rather than raising a second exception on top of the first.
    """
    try:
        return bool(load_manifest(run_dir / "manifest.json").excluded)
    except Exception:  # noqa: BLE001 - diagnostic best-effort, see docstring
        return False


def render_cell(cell_dir: Path) -> str:
    """Markdown table for one cell, over every run directory it holds.

    A run that cannot be summarized renders as a visible RENDER FAILED row
    rather than aborting the whole cell. This is not leniency about bad data:
    `summarize_run` stays strict, and a caller that needs ONE run validated
    (the harness's own post-run smoke, and the tests below) calls it directly.
    It is that a cell accumulates runs over hours, and an aborted or excluded
    run with no observer CSVs is an EXPECTED resident of that tree
    (exclusions.md: "Excluded runs remain in benchmarks/results/ with their
    data; nothing is deleted"). Raising here made every LATER run of the cell
    unrenderable, so one bring-up failure reported every subsequent healthy
    run as not contract-valid -- and in an interleaved duel, aborted the duel.
    """
    cell_dir = Path(cell_dir)
    lines = [
        f"## Cell {cell_dir.name}",
        "",
        "| run | topic | hz | p95 ms | 1-hop p50 ms | 1-hop p99 ms | MB/s |",
        "|---|---|---|---|---|---|---|",
    ]
    for run_dir in sorted(cell_dir.glob("run-*")):
        try:
            s = summarize_run(run_dir)
        except Exception as exc:  # noqa: BLE001 - deliberate; see the docstring
            # Broad on purpose: this function renders a directory tree it does
            # not control, and the reachable failures span OSError (missing
            # CSV), ValueError (invalid manifest, degenerate clock fit),
            # TypeError (older manifest schema) and more. The failure is
            # REPORTED IN THE TABLE, naming the exception -- never swallowed.
            label = run_dir.name
            if _best_effort_excluded(run_dir):
                # Tagged the same way a successfully-summarized excluded run
                # is below, so a reader (and main()'s exit code) can tell an
                # EXPECTED excluded-run failure from an unexplained one,
                # without re-deriving it from the exception text.
                label = f"{label} (EXCLUDED)"
            # The exception message would otherwise be interpolated straight
            # into the cell: a "|" in it (a path, a validation error list)
            # would be read as extra column separators and break the table,
            # and an embedded newline would break it into extra rows.
            msg = f"{type(exc).__name__}: {exc}".replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {label} | RENDER FAILED: {msg} | - | - | - | - | - |")
            continue
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
    unexplained_failure = False
    for cell_dir in sorted(p for p in results.iterdir() if p.is_dir()):
        text = render_cell(cell_dir)
        print(text)
        print()
        # A RENDER FAILED row tagged (EXCLUDED) is the expected shape of a
        # pre-registered excluded run (exclusions.md: "Excluded runs remain
        # in benchmarks/results/ ... nothing is deleted"); one that is NOT
        # tagged is a run that should have rendered and did not, which must
        # fail loud rather than exit 0 alongside a table full of failures.
        unexplained_failure |= any(
            "RENDER FAILED" in line and "(EXCLUDED)" not in line for line in text.splitlines()
        )
    if unexplained_failure:
        sys.exit(
            "one or more runs RENDER FAILED without an (EXCLUDED) manifest "
            "to explain it -- see the rows above"
        )


if __name__ == "__main__":
    main()
