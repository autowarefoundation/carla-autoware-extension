#!/usr/bin/env python3
"""Per-run integrity facts for the P4 Task 15 32ch step-up sweep.

    PYTHONPATH=. python3 benchmarks/evidence/p4-task15-32ch-sweep/integrity_pass.py A
    PYTHONPATH=. python3 benchmarks/evidence/p4-task15-32ch-sweep/integrity_pass.py B-cyc

Reads arm, class label, exclusion label, transport, duel flags, host/engine
placement, instrument PRESENCE, and the ablation client's own recorded rig.
Deliberately NOT a verdict: the ceiling reading is `sweep_verdict.py`'s,
invoked once per cell under the registered no-peeking exception, and nothing
here duplicates it.

TWO DELIBERATE DIFFERENCES FROM TASK 14's PASS, both carrying out the
correction §23.2 recorded against it. That pass printed raw `observer rows` /
`resources rows` / `clock rows` counts for BOTH cells into ONE committed
artifact -- and an observer row count IS `observed_count`, one of the three
terms `cadence.reconcile_drops` consumes, i.e. a measured magnitude and not a
presence check. §23.2 instructed Task 15 to "either split this output per cell
or reduce measured-arm rows to booleans". BOTH are done here, because they
close different halves of the hole and neither subsumes the other:

  1. ROW COUNTS ARE BOOLEANS. The integrity claim these columns support is
     "the instrument produced data" -- presence and non-emptiness -- which a
     boolean carries exactly as well as a count, and the raw counts were never
     load-bearing for it. They were additionally unnormalized for run duration,
     so any impression a reader formed from them was premature as well as
     unlicensed. A boolean cannot be differenced, so the material is gone
     rather than merely separated.
  2. ONE CELL PER INVOCATION, one log per cell. The pass takes a cell argument
     and refuses to render two cells into one artifact, so no committed file in
     this directory holds both cells' per-run instrument facts side by side --
     the shape §23.2 faulted, independently of what the columns contain.

The `-1` sentinel for "file absent entirely" is preserved as a distinct value
from "present but empty": `False` for an absent file and `False` for a
zero-row file would collapse a missing instrument into an idle one, and those
are different failures.

Runs are selected by `manifest.class_id == "32ch"` EXACTLY -- no legacy `""`
clause. `sweep_verdict._class_admits`'s legacy clause exists so Task 14's
already-filed manifests stay poolable as vlp16; every run this pass reports on
was filed after `RunManifest.class_id` landed and carries the field, so
admitting `""` here would only pull Task 14's vlp16 runs into a 32ch report.

Every figure this prints is one a claim in benchmarks/results/PROVENANCE.md
sec 26 rests on, so the claims are checkable by re-running this file rather
than by trusting prose.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "benchmarks" / "results"

# The Task 11 measurement (PROVENANCE sec 14.5), which cells/tier4-native.sh
# passes to the ablation client as --mount -- since 2026-08-04 as the launcher
# constant TIER4_ABLATION_MOUNT rather than as an operator-supplied argument.
# Repeated here so this pass can confirm the value the CLIENT ITSELF RECORDED
# matches it -- an independent check of the wiring, taken from the run
# directory rather than from the launcher that wrote it.
MEASURED_TIER4_MOUNT_LOC = [-0.497071, 0.000002, 2.000000]
MEASURED_TIER4_MOUNT_ROT = [0.859670, -0.053676, -88.156119]

# `sweep_arms` (cells.yaml). A run whose arm is not one of these is P3/P4 duel
# data filed in the same flat run-NNN sequence and is not this task's.
SWEEP_ARMS = ("paced", "unpaced", "ablation")

# The class this task collected. Registered in cells.yaml's sweep_classes as
# the pre-registered step-up from vlp16.
CLASS_ID = "32ch"

# The cells whose Task 14 vlp16 ceiling boolean was "did not fire", i.e. the
# cells the pre-registered trigger steps up. Both of them.
CELLS = ("A", "B-cyc")

# Which cells' ablation runs are launched with an explicit `--mount`. The
# tier4-native family's `default_mount()` fallback is an ESTIMATE, wrong by
# 1.397071 m in x; the extension family's IS the committed kit and is exact,
# so it correctly passes no --mount at all.
EXPECT_MEASURED_MOUNT = {"A": False, "B-cyc": True}


def has_rows(path: Path) -> str:
    """Presence and non-emptiness of a CSV, never its size.

    `absent` and `empty` stay distinct: a missing instrument and an idle one
    are different failures, and collapsing both to `False` would hide which.
    """
    if not path.is_file():
        return "absent"
    with path.open() as fh:
        for n, _ in enumerate(fh):
            if n >= 1:  # a header plus at least one data row
                return "True"
    return "empty"


def load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def sweep_runs(cell: str) -> list[Path]:
    out = []
    for run_dir in sorted((RESULTS / cell).glob("run-*")):
        manifest = load_json(run_dir / "manifest.json")
        if not manifest or manifest.get("arm") not in SWEEP_ARMS:
            continue
        if manifest.get("class_id") != CLASS_ID:
            continue
        out.append(run_dir)
    return out


def report_cell(cell: str) -> dict:
    runs = sweep_runs(cell)
    print(f"## cell {cell}: {len(runs)} sweep-arm run(s) at class `{CLASS_ID}`")
    print()
    print("| run | arm | class_id | excluded | reason | rmw | shm_enabled "
          "| dds_profile_sha256 | duel_adm | duel_id |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    per_arm: dict[str, list[str]] = {a: [] for a in SWEEP_ARMS}
    excluded = []
    for run_dir in runs:
        m = load_json(run_dir / "manifest.json")
        t = m.get("transport") or {}
        per_arm[m["arm"]].append(run_dir.name)
        if m.get("excluded"):
            excluded.append((run_dir.name, m.get("exclusion_reason")))
        print(
            f"| {run_dir.name} | {m['arm']} | {m.get('class_id') or '(empty)'} "
            f"| {m.get('excluded')} "
            f"| {m.get('exclusion_reason') or '-'} | {t.get('rmw')} "
            f"| {t.get('shm_enabled')} "
            f"| {t.get('dds_profile_sha256') or '(none)'} | {m.get('duel_admissible')} "
            f"| {m.get('duel_id') or '(empty)'} |"
        )
    print()

    # Host/engine facts, per run, straight out of each manifest's placement
    # block -- the evidence for "D8 was not spent" and for the governor and
    # load the sweep actually ran under.
    print("| run | arm | engine_build_id | cpu_governor | loadavg | run_mode |")
    print("|---|---|---|---|---|---|")
    for run_dir in runs:
        m = load_json(run_dir / "manifest.json")
        p = m.get("placement") or {}
        print(
            f"| {run_dir.name} | {m['arm']} | {p.get('engine_build_id')} "
            f"| {p.get('cpu_governor')} | {p.get('loadavg')} | {p.get('run_mode')} |"
        )
    print()
    for arm in SWEEP_ARMS:
        names = per_arm[arm]
        print(f"- arm `{arm}`: n={len(names)} {' '.join(names) if names else '(none)'}")
    print()

    # PRESENCE ONLY -- see the module docstring. `True` means "header plus at
    # least one data row"; `empty` and `absent` are kept apart.
    print("| run | arm | observer rows? | resources rows? | clock rows? | "
          "publisher_counts | quality.json |")
    print("|---|---|---|---|---|---|---|")
    for run_dir in runs:
        m = load_json(run_dir / "manifest.json")
        print(
            f"| {run_dir.name} | {m['arm']} | {has_rows(run_dir / 'observer.csv')} "
            f"| {has_rows(run_dir / 'resources.csv')} | {has_rows(run_dir / 'clock.csv')} "
            f"| {(run_dir / 'publisher_counts.json').is_file()} "
            f"| {(run_dir / 'quality.json').is_file()} |"
        )
    print()
    return {"runs": runs, "per_arm": per_arm, "excluded": excluded}


def report_ablation_mount(cell: str, runs: list[Path], *, expect_measured: bool) -> None:
    """What the ablation CLIENT recorded about its own rig, per run.

    `expect_measured` is True only for the tier4-native family, whose launcher
    passes the Task 11 `--mount` from its own TIER4_ABLATION_MOUNT constant.
    Cell A's extension rig has no --mount and must not: `default_mount()`
    composes the committed kit and is EXACT there.

    `mount_source` (added by §23.5) is read with `.get()`: Task 14's six filed
    ablation summaries predate the key, so a consumer that indexes it would
    break on them even though it is present on every run filed here.
    """
    abl = []
    for run_dir in runs:
        summary = load_json(run_dir / "raycast_baseline.json")
        if summary is not None:
            abl.append((run_dir, summary))
    if not abl:
        print(f"cell {cell}: no ablation summaries found\n")
        return
    print(f"### cell {cell} ablation client, as the client itself recorded it")
    print()
    print("| run | rig | class_id | channels | pps | mount_location_m "
          "| mount_rotation_deg | mount_source |")
    print("|---|---|---|---|---|---|---|---|")
    for run_dir, s in abl:
        a = s.get("attributes") or {}
        print(
            f"| {run_dir.name} | {s.get('rig')} | {s.get('class_id')} "
            f"| {a.get('channels')} | {a.get('points_per_second')} "
            f"| {s.get('mount_location_m')} | {s.get('mount_rotation_deg')} "
            f"| {s.get('mount_source', '(key absent)')} |"
        )
    print()
    print("| run | clock_rows_written? | hdr_reasserts | toctou | stood_down "
          "| by_signal |")
    print("|---|---|---|---|---|---|")
    for run_dir, s in abl:
        written = s.get("clock_rows_written")
        print(
            f"| {run_dir.name} "
            f"| {'True' if isinstance(written, int) and written > 0 else written} "
            f"| {s.get('clock_header_reasserts')} "
            f"| {s.get('clock_toctou_repairs')} | {s.get('clock_stood_down')} "
            f"| {s.get('stopped_by_signal')} |"
        )
    print()
    if expect_measured:
        ok = 0
        for run_dir, s in abl:
            loc = [round(float(v), 6) for v in s.get("mount_location_m", [])]
            rot = [round(float(v), 6) for v in s.get("mount_rotation_deg", [])]
            match = loc == MEASURED_TIER4_MOUNT_LOC and rot == MEASURED_TIER4_MOUNT_ROT
            ok += bool(match)
            if not match:
                print(f"  MISMATCH {run_dir.name}: {loc} {rot}")
        print(
            f"-> the Task 11 measured `--mount` reached the client: {ok}/{len(abl)} run(s)"
        )
    else:
        print(
            "-> extension rig: no --mount is passed and none is expected; "
            "`default_mount()` composes the committed kit and is exact here."
        )
    print()


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in CELLS:
        print(f"usage: {Path(argv[0]).name} <{'|'.join(CELLS)}>", file=sys.stderr)
        print(
            "ONE CELL PER INVOCATION, deliberately: see the module docstring "
            "and PROVENANCE 23.2 -- no committed artifact in this directory may "
            "carry two cells' per-run instrument facts.",
            file=sys.stderr,
        )
        return 2
    cell = argv[1]
    print(f"# P4 Task 15 -- {CLASS_ID} sweep integrity pass, cell {cell}")
    print()
    print("Facts only: arm, class label, exclusion label, transport, duel flags,")
    print("instrument PRESENCE (not size), and the ablation client's self-recorded")
    print("rig. No verdicts, no magnitudes, one cell.")
    print()
    state = report_cell(cell)
    report_ablation_mount(
        cell, state["runs"], expect_measured=EXPECT_MEASURED_MOUNT[cell]
    )
    print("## exclusions")
    print()
    if state["excluded"]:
        for name, reason in state["excluded"]:
            print(f"- {cell}/{name}: {reason}")
    else:
        print(f"None. No run of cell {cell} at class `{CLASS_ID}` carries "
              "`excluded: true`.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
