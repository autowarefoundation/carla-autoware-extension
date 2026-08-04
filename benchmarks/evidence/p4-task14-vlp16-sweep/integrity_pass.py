#!/usr/bin/env python3
"""Per-run integrity facts for the P4 Task 14 vlp16 sweep.

    PYTHONPATH=. python3 benchmarks/evidence/p4-task14-vlp16-sweep/integrity_pass.py

Reads arm, exclusion label, transport, duel flags, host/engine placement, file
presence, row counts, and the ablation client's own recorded mount.
Deliberately NOT a verdict: the ceiling reading is `sweep_verdict.py`'s,
invoked once per cell under the registered no-peeking exception, and nothing
here duplicates it.

CORRECTION 2026-08-04 (Task 14 review, I2). This docstring used to claim the
pass "can be run and read WITHOUT touching the sweep's measured magnitudes."
**That is false, and the false part is the `observer rows` column**: an observer
row count IS `observed_count`, one of the three terms `cadence.reconcile_drops`
consumes, so it is a measured magnitude and not a presence check. The filed
`integrity-pass.log` therefore carries both cells' measured-arm counts in one
committed artifact, forty lines apart. No delta is computed and no prose in
this directory compares them -- but that is exactly the material the no-peeking
rule withholds, and it falls short of the standard applied one file over, where
`sweep_verdict.py`'s tables were deliberately NOT filed for carrying per-run
magnitudes. The counts are additionally unnormalized for run duration, so any
impression a reader forms from them is premature as well as unlicensed.

What the integrity claim actually needs from that column is **presence and
non-emptiness**, which a boolean carries just as well. It stays a raw count
HERE only because this file is the certified producer of an already-filed log
and changing its output would falsify that certification. Task 15 either splits
the output per cell or reduces measured-arm rows to booleans; see
`benchmarks/results/PROVENANCE.md` §23.2.

Every figure this prints is one a claim in benchmarks/results/PROVENANCE.md
sec 22 rests on, so the claims are checkable by re-running this file rather
than by trusting prose.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "benchmarks" / "results"

# The Task 11 measurement (PROVENANCE sec 14.5), which cells/tier4-native.sh
# passes to the ablation client as --mount. Repeated here so this pass can
# confirm the value the CLIENT ITSELF RECORDED matches it -- an independent
# check of the wiring, taken from the run directory rather than from the
# launcher that wrote it.
MEASURED_TIER4_MOUNT_LOC = [-0.497071, 0.000002, 2.000000]
MEASURED_TIER4_MOUNT_ROT = [0.859670, -0.053676, -88.156119]

# `sweep_arms` (cells.yaml). A run whose arm is not one of these is P3/P4 duel
# data filed in the same flat run-NNN sequence and is not this task's.
SWEEP_ARMS = ("paced", "unpaced", "ablation")


def rows(path: Path) -> int:
    """Data rows in a CSV (header excluded), or -1 when the file is absent."""
    if not path.is_file():
        return -1
    with path.open() as fh:
        return max(0, sum(1 for _ in fh) - 1)


def load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def sweep_runs(cell: str) -> list[Path]:
    out = []
    for run_dir in sorted((RESULTS / cell).glob("run-*")):
        manifest = load_json(run_dir / "manifest.json")
        if manifest and manifest.get("arm") in SWEEP_ARMS:
            out.append(run_dir)
    return out


def report_cell(cell: str) -> dict:
    runs = sweep_runs(cell)
    print(f"## cell {cell}: {len(runs)} sweep-arm run(s)")
    print()
    print("| run | arm | excluded | reason | rmw | shm_enabled | dds_profile_sha256 "
          "| duel_adm | duel_id |")
    print("|---|---|---|---|---|---|---|---|---|")
    per_arm: dict[str, list[str]] = {a: [] for a in SWEEP_ARMS}
    excluded = []
    for run_dir in runs:
        m = load_json(run_dir / "manifest.json")
        t = m.get("transport") or {}
        per_arm[m["arm"]].append(run_dir.name)
        if m.get("excluded"):
            excluded.append((run_dir.name, m.get("exclusion_reason")))
        print(
            f"| {run_dir.name} | {m['arm']} | {m.get('excluded')} "
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

    print("| run | arm | observer rows | resources rows | clock rows | "
          "publisher_counts | quality.json |")
    print("|---|---|---|---|---|---|---|")
    for run_dir in runs:
        m = load_json(run_dir / "manifest.json")
        print(
            f"| {run_dir.name} | {m['arm']} | {rows(run_dir / 'observer.csv')} "
            f"| {rows(run_dir / 'resources.csv')} | {rows(run_dir / 'clock.csv')} "
            f"| {(run_dir / 'publisher_counts.json').is_file()} "
            f"| {(run_dir / 'quality.json').is_file()} |"
        )
    print()
    return {"runs": runs, "per_arm": per_arm, "excluded": excluded}


def report_ablation_mount(cell: str, runs: list[Path], *, expect_measured: bool) -> None:
    """What the ablation CLIENT recorded about its own rig, per run.

    `expect_measured` is True only for the tier4-native family, whose launcher
    passes the Task 11 `--mount`. Cell A's extension rig has no --mount and
    must not: `default_mount()` composes the committed kit and is EXACT there.
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
    print("| run | rig | class_id | channels | pps | mount_location_m | mount_rotation_deg |")
    print("|---|---|---|---|---|---|---|")
    for run_dir, s in abl:
        a = s.get("attributes") or {}
        print(
            f"| {run_dir.name} | {s.get('rig')} | {s.get('class_id')} "
            f"| {a.get('channels')} | {a.get('points_per_second')} "
            f"| {s.get('mount_location_m')} | {s.get('mount_rotation_deg')} |"
        )
    print()
    print("| run | ticks | sensor_callbacks | clock_rows | hdr_reasserts | "
          "toctou | stood_down | by_signal |")
    print("|---|---|---|---|---|---|---|---|")
    for run_dir, s in abl:
        print(
            f"| {run_dir.name} | {s.get('ticks')} | {s.get('sensor_callbacks')} "
            f"| {s.get('clock_rows_written')} | {s.get('clock_header_reasserts')} "
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


def main() -> int:
    print("# P4 Task 14 -- vlp16 sweep integrity pass")
    print()
    print("Facts only: arm, exclusion label, transport, duel flags, file presence,")
    print("row counts, and the ablation client's self-recorded rig. No verdicts.")
    print()
    state = {}
    for cell in ("A", "B-cyc"):
        state[cell] = report_cell(cell)
    for cell, expect in (("A", False), ("B-cyc", True)):
        report_ablation_mount(cell, state[cell]["runs"], expect_measured=expect)
    print("## exclusions")
    print()
    any_excluded = False
    for cell in ("A", "B-cyc"):
        for name, reason in state[cell]["excluded"]:
            any_excluded = True
            print(f"- {cell}/{name}: {reason}")
    if not any_excluded:
        print("None. No run in either cell carries `excluded: true`.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
