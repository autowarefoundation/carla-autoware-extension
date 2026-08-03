#!/usr/bin/env python3
"""CLI wrapper over `RunManifest`: writes `<run-dir>/manifest.json`.

Two modes, both of which end in `RunManifest.save()` and therefore inherit
the P0 guarantee that an invalid manifest is REFUSED rather than written
(benchmarks/analysis/manifest.py):

* create (default) -- build the manifest from the run's transport / version /
  placement facts and write it BEFORE the run starts, which is the last point
  at which a bad cell/arm/transport costs nothing.
* rewrite (`--exclude <reason>`) -- load an existing manifest, mark it
  excluded with a pre-registered reason (benchmarks/config/exclusions.md),
  save it back. Everything else is preserved, so an excluded run keeps its
  full provenance; nothing is deleted (exclusions.md's own rule).

Provenance is computed here rather than passed in, so no caller can supply a
stale value:

* `harness_git_sha`  = `git rev-parse HEAD`, with `-dirty` appended when the
  working tree differs from it. Without that suffix the field ASSERTS a
  tie-back (benchmarks/README.md's "any result can be tied back to the exact
  analysis code that scored it") which a dirty tree makes false. Measured
  2026-07-29 (Task 10): results/E/run-002..004 record `d0612c4`, a commit in
  which `cells/python-bridge.sh` had no `save_stage_logs` at all -- yet
  run-003 and run-004 contain the `bridge-stage*.log` files only that function
  writes. The code that ran was uncommitted, and no commit exists to name it,
  so the four records cannot be repaired retroactively; this stops the next one
  from being unrepairable. `benchmarks/results/` is excluded from the dirty
  test because the run writes into it while the run is happening.
* `patches_git_sha`  = `git log -1 --format=%H -- benchmarks/patches/`, with the
  same `-dirty` suffix on the same condition, for the same reason: run-001..004
  claim `ec998b4`, which PREDATES the patch files their image was built from.
* `dds_profile_sha256` = sha256 of the profile file (`--dds-profile none`
  records the empty string, which is what "no XML profile in play" means --
  distinguishable from a profile whose content happened to hash to zeros).

`--duel` is the ONE declaration this tool cannot compute: whether the run
belongs to the primary duel's interleaved A,B,A,B design. Only the caller that
ordered the interleaving knows (scripts/duel.sh), so it opts in explicitly and
everything else defaults to false -- see `RunManifest.duel_admissible`. Rewrite
mode preserves it along with everything else, so excluding a duel run does not
silently reclassify it.

`approach` and `map_name` are NOT arguments: they are looked up from the
pre-registered cells.yaml via `cell_info`, so a run cannot be filed under
cell A while claiming a different approach or map.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from benchmarks.analysis.manifest import RunManifest, load_manifest
from benchmarks.scripts.cell_info import UnknownIdError, cell_entry, load_cells_doc

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PATCHES_PATH = "benchmarks/patches/"
RUN_DIR_RE = re.compile(r"^run-(\d+)$")

EXIT_BAD_ARGS = 2


class ManifestArgError(ValueError):
    """A caller-supplied value that must not reach RunManifest."""


def run_index_from_dir(run_dir: Path) -> int:
    """`results/<cell>/run-007` -> 7.

    The index is derived from the directory name rather than passed in
    separately: two sources for one number is how a manifest ends up
    claiming run 7 inside run-008/.
    """
    m = RUN_DIR_RE.match(Path(run_dir).name)
    if not m:
        raise ManifestArgError(
            f"run dir {run_dir} is not named run-<NNN> (got {Path(run_dir).name!r})"
        )
    return int(m.group(1))


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ManifestArgError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def tree_is_dirty() -> bool:
    """Do tracked files differ from HEAD, ignoring benchmarks/results/?

    The run writes into benchmarks/results/ while it runs, so that path must be
    excluded or every manifest would be marked dirty by its own run directory.
    Untracked files elsewhere are ignored too: an untracked scratch file cannot
    change what the harness executed, while a modified tracked file can.
    """
    status = _git(
        "status",
        "--porcelain",
        "--untracked-files=no",
        "--",
        ".",
        ":(exclude)benchmarks/results",
    )
    return bool(status.strip())


def _dirty_suffix() -> str:
    return "-dirty" if tree_is_dirty() else ""


def harness_git_sha() -> str:
    """HEAD, suffixed `-dirty` when the working tree is not HEAD.

    See the module docstring: an unsuffixed sha asserts a tie-back that a dirty
    tree makes false, and four of cell E's bring-up runs assert exactly that.
    """
    return _git("rev-parse", "HEAD") + _dirty_suffix()


def patches_git_sha() -> str:
    """HEAD commit that last touched benchmarks/patches/, `-dirty` as above.

    Empty when no commit has touched it yet -- recorded as "" rather than
    substituted with the harness sha, so "the patch set is unversioned here"
    stays distinguishable from "the patch set is at the harness commit". The
    dirty suffix is NOT appended to that empty value: "" already says the patch
    set is unversioned, which is strictly more informative than "-dirty".
    """
    sha = _git("log", "-1", "--format=%H", "--", PATCHES_PATH)
    return sha + _dirty_suffix() if sha else sha


def dds_profile_sha256(profile: str) -> str:
    """sha256 of a DDS XML profile; "" for the literal `none`."""
    if profile == "none":
        return ""
    path = Path(profile)
    if not path.is_file():
        raise ManifestArgError(f"--dds-profile {profile} is not a file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(args: argparse.Namespace) -> RunManifest:
    try:
        cell = cell_entry(load_cells_doc(), args.cell)
    except UnknownIdError as exc:
        raise ManifestArgError(str(exc)) from exc
    try:
        placement = json.loads(args.placement_json)
    except json.JSONDecodeError as exc:
        raise ManifestArgError(f"--placement-json is not valid JSON: {exc}") from exc
    if not isinstance(placement, dict):
        raise ManifestArgError("--placement-json must be a JSON object")
    return RunManifest(
        cell=args.cell,
        approach=str(cell["approach"]),
        map_name=str(cell["map"]),
        run_index=run_index_from_dir(Path(args.run_dir)),
        arm=args.arm,
        harness_git_sha=harness_git_sha(),
        patches_git_sha=patches_git_sha(),
        transport={
            "rmw": args.rmw,
            "shm_enabled": args.shm == "on",
            "dds_profile_sha256": dds_profile_sha256(args.dds_profile),
        },
        carla_version=args.carla_version,
        autoware_image=args.autoware_image,
        started_at_ns=time.time_ns(),
        placement=placement,
        # Opt IN, never inferred (amendment 2026-07-30, Task 15b): this tool
        # cannot know whether a run is part of the primary duel's interleaved
        # A,B,A,B design -- only the caller that ORDERED the interleaving can,
        # which is scripts/duel.sh. So the default is false and --duel is the
        # single explicit declaration; see RunManifest.duel_admissible for why
        # the default points this way.
        duel_admissible=bool(args.duel),
        # Which duel's pool this run belongs to (Amendment 2026-08-03,
        # Task 2). Same opt-in-only rationale as duel_admissible just
        # above: this tool cannot know which pairing ordered the run, only
        # the caller that did (scripts/duel.sh, which stamps
        # `--duel-id "${CELL_A}+${CELL_B}"`); every other caller leaves it
        # at its default "", matching RunManifest.duel_id's own default.
        duel_id=args.duel_id,
    )


def exclude_manifest(run_dir: Path, reason: str) -> RunManifest:
    """Load, mark excluded, save. `reason` must be non-empty (validate()
    rejects an excluded manifest without one, so an accidental `--exclude ""`
    fails here instead of filing an unexplained exclusion)."""
    path = Path(run_dir) / "manifest.json"
    if not path.is_file():
        raise ManifestArgError(f"no manifest to exclude at {path}")
    current = load_manifest(path)
    updated = dataclasses.replace(current, excluded=True, exclusion_reason=reason)
    updated.save(path)
    return updated


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", required=True, help="results/<cell>/run-<NNN>")
    p.add_argument("--cell")
    p.add_argument("--arm")
    p.add_argument("--rmw", help="RMW_IMPLEMENTATION in force for this run")
    p.add_argument("--shm", choices=("on", "off"), help="DDS shared memory")
    p.add_argument("--dds-profile", help="path to the DDS XML profile, or 'none'")
    p.add_argument("--carla-version", help="cells.yaml's registered CARLA identity")
    p.add_argument("--autoware-image", help="image reference (digest-pinned)")
    p.add_argument("--placement-json", help="JSON object for the placement block")
    p.add_argument(
        "--duel",
        action="store_true",
        help="declare this run PRIMARY-DUEL data (RunManifest.duel_admissible). "
        "Passed by scripts/duel.sh on every run it orders; omitted by every "
        "other invocation, so a bring-up or gate run cannot reach the "
        "equivalence verdict in benchmarks/scripts/duel_verdict.py",
    )
    p.add_argument(
        "--duel-id",
        default="",
        help="WHICH duel's admission pool this run belongs to "
        "(RunManifest.duel_id; Amendment 2026-08-03, Task 2), "
        "conventionally f'{cell_a}+{cell_b}' in the order the two cells "
        "were given to scripts/duel.sh, which is the only caller that "
        "ever passes this. Defaults to '', the legacy/no-duel value every "
        "manifest predating this field also reads as.",
    )
    p.add_argument(
        "--exclude",
        metavar="REASON",
        default=None,
        help="rewrite mode: mark an existing manifest excluded (a reason from "
        "benchmarks/config/exclusions.md)",
    )
    return p


CREATE_REQUIRED = (
    "cell",
    "arm",
    "rmw",
    "shm",
    "dds_profile",
    "carla_version",
    "autoware_image",
    "placement_json",
)


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    path = Path(args.run_dir) / "manifest.json"
    try:
        if args.exclude is not None:
            updated = exclude_manifest(Path(args.run_dir), args.exclude)
            print(f"EXCLUDED {path}: {updated.exclusion_reason}")
            return 0
        missing = [f"--{n.replace('_', '-')}" for n in CREATE_REQUIRED if getattr(args, n) is None]
        if missing:
            raise ManifestArgError(f"create mode needs {', '.join(missing)}")
        manifest = build_manifest(args)
        # Validated BEFORE the directory is created, so a refused write leaves
        # NO run directory behind. An empty run-NNN/ with no manifest is worse
        # than no directory at all: it consumes an index, and every consumer
        # that walks a cell's run-* directories (report.render_cell, the M2/M5
        # analyses) then meets a directory it can neither read nor attribute --
        # it was never labelled excluded, because there was no manifest to
        # label. This is the only place that creates a run directory.
        errs = manifest.validate()
        if errs:
            raise ManifestArgError(f"invalid run manifest: {'; '.join(errs)}")
        Path(args.run_dir).mkdir(parents=True, exist_ok=True)
        manifest.save(path)
    except (ManifestArgError, ValueError) as exc:
        print(f"MANIFEST FAIL: {exc}", file=sys.stderr)
        return EXIT_BAD_ARGS
    print(f"WROTE {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
