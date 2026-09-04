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

THE MEASURED-ARM RIG FACT, AND WHY THIS PASS NOW HAS AN EXIT CODE (P4 Task 15
review finding I1, added 2026-08-04). As first filed, this pass could not have
failed on the defect it was standing over:

  - it read the spawned rig back only from `raycast_baseline.json`, which the
    ABLATION arm writes and the measured arms do not, so for the twelve
    measured runs it printed `manifest.class_id` -- a LABEL, the very field
    under suspicion -- and called that a class check;
  - and `main` returned 0 unconditionally, so even the ablation side's
    `MISMATCH` line filed as a passing artifact.

The defect it missed is finding C1: `BENCH_TIER4_SWEEP_ARGS` was derived
unexported in `cells/tier4-native.sh`, the measured arms spawn the demo as a
CHILD, and the child fell back to the patched demo's own defaults
(`--lidar-channels 16 --lidar-pps 288000`) -- exactly the vlp16 class -- while
the manifest still said `32ch`. Six B-cyc measured runs were filed that way.
Every label-level check passed, and had to: a label cannot contradict itself.

So this pass now derives a MEASURED rig quantity for the measured arms, from
data already filed: the median serialized `size_bytes` of the registered
`lidar_topic` in each run's own `observer.csv`, against the same cell's own
vlp16 measured runs, checked against the class ratio
`points_per_second(32ch) / points_per_second(vlp16)` read out of
`cells.yaml sweep_classes`. Payload bytes scale with the point budget, so a
rig that silently stayed at vlp16 reads x1.00 where the class demands x4.17 --
a factor-of-four gap no tolerance can absorb. And `main` now RETURNS NON-ZERO
on any mismatch, ablation or measured. An instrument that cannot fail is not
an instrument.

WHY THIS IS NOT A NO-PEEKING BREACH. `size_bytes` is a WORKLOAD property --
how many points the sensor was configured to emit -- not a performance
magnitude: no latency, no rate, no RTF, and nothing `duel_verdict.py` consumes.
It is the measured counterpart of the `channels 32 / points_per_second 1200000`
read-back this directory's PROVENANCE.md already admits on exactly the ground
that a registered class definition read back off the rig is not a measurement
of how well a cell performs. The ratio is taken WITHIN one cell against that
cell's own vlp16 baseline, never across cells, and the one-cell-per-invocation
rule (below) still applies, so no committed artifact here carries both cells'
numbers.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

from benchmarks.scripts.cell_info import load_cells_doc, metrics_for
from benchmarks.scripts.sweep_verdict import _class_admits

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

# --- the measured-arm rig fact (finding I1) --------------------------------

# The class the 32ch payload is measured AGAINST, within the same cell. Every
# cell reported on here has Task 14's vlp16 runs filed beside its 32ch ones,
# which is what makes an in-cell ratio possible at all; a cell without them
# is a REFUSAL below, never a silent pass.
BASELINE_CLASS_ID = "vlp16"

# The arms that publish to the observer. The ablation arm deliberately files a
# header-only observer.csv (it publishes nothing), so its rig is checked the
# other way -- from `raycast_baseline.json`, which only it writes.
MEASURED_ARMS = ("paced", "unpaced")

# How far the measured byte ratio may sit from the registered point ratio.
# Payload = a fixed header plus points x point_step, so the byte ratio lands
# slightly BELOW the point ratio (the header does not scale): cell A measured
# x4.1644 against a registered 4.1667, i.e. 0.06 % low. 5 % is therefore a
# wide margin on the true signal and still nowhere near the failure it exists
# to catch -- a rig that silently stayed at vlp16 reads x1.00, which is 76 %
# away. A tolerance that could not separate those two would be decoration.
SIZE_RATIO_TOL = 0.05


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


def sweep_runs(cell: str, class_id: str = CLASS_ID, *, legacy_ok: bool = False) -> list[Path]:
    """Sweep-arm runs of `cell` at `class_id`.

    `legacy_ok=False` (the default, and what every 32ch caller uses) matches
    the field EXACTLY -- see the module docstring: every run reported on here
    was filed after `RunManifest.class_id` landed, so admitting the legacy
    `""` would only pull Task 14's vlp16 runs into a 32ch report.

    `legacy_ok=True` is the vlp16 BASELINE selector added with finding I1's
    fix, and it must be the registered pool rule rather than a private one:
    Task 14's eighteen sweep-arm manifests predate the field entirely (they
    carry no `class_id` key at all), and `sweep_verdict._class_admits`'s
    legacy clause -- `"" admits to vlp16, and to nothing else` -- is exactly
    what keeps them poolable without rewriting a filed manifest. Imported
    rather than re-implemented so the baseline this pass measures against is
    the same set `sweep_verdict.py` scores.
    """
    out = []
    for run_dir in sorted((RESULTS / cell).glob("run-*")):
        manifest = load_json(run_dir / "manifest.json")
        if not manifest or manifest.get("arm") not in SWEEP_ARMS:
            continue
        # `or ""` because the legacy manifests have no `class_id` KEY at all,
        # not an empty one -- `.get()` returns None there, and `_class_admits`
        # is written against the dataclass default `""`.
        filed = manifest.get("class_id") or ""
        admits = _class_admits(filed, class_id) if legacy_ok else filed == class_id
        if not admits:
            continue
        out.append(run_dir)
    return out


def lidar_size_median(run_dir: Path, topic: str) -> int | None:
    """Median serialized `size_bytes` of `topic` in this run's observer.csv.

    The MEASURED rig fact -- the one quantity in a measured run's own filed
    data that moves when the sensor's point budget moves, and the only thing
    that could have caught finding C1. `None` when the file is absent or holds
    no row for the topic (the ablation arm, whose observer.csv is header-only
    by design); callers must decide what an absent value means for the arm
    they are checking, never treat it as a pass.

    Median rather than mean: a scoring window's first and last clouds can be
    partial, and one truncated row must not move a rig check by more than a
    row's worth.
    """
    path = run_dir / "observer.csv"
    if not path.is_file():
        return None
    sizes: list[int] = []
    with path.open() as fh:
        for row in csv.DictReader(fh):
            if row.get("topic") != topic:
                continue
            raw = row.get("size_bytes")
            if raw:
                sizes.append(int(raw))
    return int(statistics.median(sizes)) if sizes else None


def class_points_per_second(doc: dict, class_id: str) -> int:
    for entry in doc.get("sweep_classes") or []:
        if entry.get("id") == class_id:
            return int(entry["points_per_second"])
    raise KeyError(f"cells.yaml sweep_classes has no class {class_id!r}")


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


def report_measured_rig(cell: str, runs: list[Path]) -> list[str]:
    """The MEASURED arms' rig, derived from each run's own observer.csv.

    Finding I1's fix. For the twelve measured runs this pass previously showed
    `manifest.class_id` -- a LABEL written by the same invocation whose rig was
    in doubt -- and called it a class check. This instead measures: median
    serialized `size_bytes` of the registered `lidar_topic`, per run, divided
    by the SAME CELL's median over its non-excluded `vlp16` measured runs, and
    compared with the registered point ratio from `cells.yaml sweep_classes`.

    Returns the list of failure strings, so `main` can exit non-zero. Three
    distinct ways to fail, all loud, none silent:

      * no in-cell vlp16 baseline at all -> REFUSAL. The check cannot be
        performed, and "cannot check" must never read as "checked, fine".
      * a measured run with no lidar rows -> failure. A measured arm that
        published nothing is not a passing rig.
      * a ratio outside SIZE_RATIO_TOL -> failure, naming both numbers.

    EXCLUDED runs are reported with their ratio and explicitly NOT counted:
    an excluded run is out of every pool by definition (exclusions.md's
    closing paragraph keeps its data in place, which is why it can still be
    shown). Their rows are the retro-evidence -- this is the check that would
    have caught them on the day, printed against the runs it missed.
    """
    doc = load_cells_doc()
    topic = metrics_for(doc, cell)["lidar_topic"]
    expected = class_points_per_second(doc, CLASS_ID) / class_points_per_second(
        doc, BASELINE_CLASS_ID
    )
    failures: list[str] = []

    print(f"### cell {cell} measured-arm rig, from each run's own observer.csv")
    print()
    print(f"topic `{topic}`; baseline class `{BASELINE_CLASS_ID}`; registered point")
    print(f"ratio {CLASS_ID}/{BASELINE_CLASS_ID} = {expected:.4f}; tolerance "
          f"+/-{SIZE_RATIO_TOL:.0%}.")
    print()

    baseline_runs = []
    for r in sweep_runs(cell, BASELINE_CLASS_ID, legacy_ok=True):
        bm = load_json(r / "manifest.json") or {}
        if bm.get("arm") in MEASURED_ARMS and not bm.get("excluded"):
            baseline_runs.append(r)
    baseline_medians = [
        (r.name, m) for r in baseline_runs if (m := lidar_size_median(r, topic)) is not None
    ]
    if not baseline_medians:
        msg = (
            f"REFUSAL: cell {cell} has no usable {BASELINE_CLASS_ID} measured-arm "
            f"baseline, so the {CLASS_ID} rig cannot be checked against the class "
            f"ratio. Not a pass."
        )
        print(msg)
        print()
        return [msg]
    baseline = int(statistics.median(m for _, m in baseline_medians))
    print(
        f"baseline: {len(baseline_medians)} {BASELINE_CLASS_ID} measured run(s) "
        f"({', '.join(n for n, _ in baseline_medians)}), median {baseline} B"
    )
    print()

    print("| run | arm | excluded | median size_bytes | x baseline | rig |")
    print("|---|---|---|---|---|---|")
    checked = 0
    for run_dir in runs:
        m = load_json(run_dir / "manifest.json") or {}
        if m.get("arm") not in MEASURED_ARMS:
            continue
        is_excluded = bool(m.get("excluded"))
        median = lidar_size_median(run_dir, topic)
        if median is None:
            ratio_txt, rig = "-", "NO LIDAR ROWS"
            if not is_excluded:
                failures.append(
                    f"{cell}/{run_dir.name}: measured arm `{m.get('arm')}` has no "
                    f"`{topic}` rows in observer.csv -- the rig cannot be confirmed"
                )
        else:
            ratio = median / baseline
            ratio_txt = f"x{ratio:.4f}"
            ok = abs(ratio / expected - 1.0) <= SIZE_RATIO_TOL
            rig = "OK" if ok else "MISMATCH"
            if is_excluded:
                rig += " (excluded; not counted)"
            elif not ok:
                failures.append(
                    f"{cell}/{run_dir.name}: lidar payload is {ratio_txt} the "
                    f"{BASELINE_CLASS_ID} baseline, but class `{CLASS_ID}` requires "
                    f"x{expected:.4f} +/-{SIZE_RATIO_TOL:.0%} -- the manifest says "
                    f"`{CLASS_ID}` and the rig does not"
                )
            else:
                checked += 1
        print(
            f"| {run_dir.name} | {m.get('arm')} | {is_excluded} | "
            f"{median if median is not None else '-'} | {ratio_txt} | {rig} |"
        )
    print()
    print(
        f"-> the {CLASS_ID} rig is confirmed from measured data on {checked} "
        f"non-excluded measured run(s) of cell {cell}"
    )
    if not checked:
        # The I1 disease in its purest form: a check that ran over nothing and
        # reported no failure. `sweep_arms` gives every cell two measured arms
        # at every class it collects, so zero confirmed measured runs means the
        # data is missing or wholly excluded -- never that the rig is fine.
        msg = (
            f"REFUSAL: cell {cell} has NO non-excluded measured run at class "
            f"`{CLASS_ID}` whose rig could be confirmed. Nothing was checked, "
            f"which is not a pass."
        )
        print()
        print(msg)
        failures.append(msg)
    print()
    return failures


def report_ablation_mount(cell: str, runs: list[Path], *, expect_measured: bool) -> list[str]:
    """What the ablation CLIENT recorded about its own rig, per run.

    `expect_measured` is True only for the tier4-native family, whose launcher
    passes the Task 11 `--mount` from its own TIER4_ABLATION_MOUNT constant.
    Cell A's extension rig has no --mount and must not: `default_mount()`
    composes the committed kit and is EXACT there.

    `mount_source` (added by §23.5) is read with `.get()`: Task 14's six filed
    ablation summaries predate the key, so a consumer that indexes it would
    break on them even though it is present on every run filed here.

    Returns the list of failure strings (finding I1). Before that fix this
    printed `MISMATCH` and returned None, and `main` returned 0 regardless --
    so an ablation client that had been handed the wrong pose still filed as a
    passing artifact. It also refuses on a cell whose ablation arm produced no
    summary at all, for the same reason `report_measured_rig` refuses on a
    missing baseline: "nothing to check" is not "checked".
    """
    abl = []
    for run_dir in runs:
        summary = load_json(run_dir / "raycast_baseline.json")
        if summary is not None:
            abl.append((run_dir, summary))
    if not abl:
        msg = (
            f"REFUSAL: cell {cell} has no ablation `raycast_baseline.json` at "
            f"class `{CLASS_ID}`, so the ablation rig cannot be read back. "
            f"Not a pass."
        )
        print(msg)
        print()
        return [msg]
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

    failures: list[str] = []

    # The ablation arm's own rig read-back, now ENFORCED rather than printed.
    # This is the arm's counterpart of `report_measured_rig`: the client
    # records the attributes of the sensor it actually spawned, so a run that
    # silently kept another class's rig says so here.
    expected_pps = class_points_per_second(load_cells_doc(), CLASS_ID)
    for run_dir, s in abl:
        a = s.get("attributes") or {}
        if s.get("class_id") != CLASS_ID or int(a.get("points_per_second", -1)) != expected_pps:
            failures.append(
                f"{cell}/{run_dir.name}: ablation client recorded class "
                f"{s.get('class_id')!r} / points_per_second "
                f"{a.get('points_per_second')}, expected {CLASS_ID!r} / {expected_pps}"
            )

    if expect_measured:
        ok = 0
        for run_dir, s in abl:
            loc = [round(float(v), 6) for v in s.get("mount_location_m", [])]
            rot = [round(float(v), 6) for v in s.get("mount_rotation_deg", [])]
            match = loc == MEASURED_TIER4_MOUNT_LOC and rot == MEASURED_TIER4_MOUNT_ROT
            ok += bool(match)
            if not match:
                print(f"  MISMATCH {run_dir.name}: {loc} {rot}")
                failures.append(
                    f"{cell}/{run_dir.name}: ablation client recorded mount "
                    f"{loc} {rot}, expected {MEASURED_TIER4_MOUNT_LOC} "
                    f"{MEASURED_TIER4_MOUNT_ROT} (PROVENANCE sec 14.5)"
                )
        print(
            f"-> the Task 11 measured `--mount` reached the client: {ok}/{len(abl)} run(s)"
        )
    else:
        print(
            "-> extension rig: no --mount is passed and none is expected; "
            "`default_mount()` composes the committed kit and is exact here."
        )
    print()
    return failures


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
    print("instrument PRESENCE (not size), each measured arm's RIG derived from")
    print("its own observer payload, and the ablation client's self-recorded rig.")
    print("No ceiling verdict, one cell. Exits non-zero on any rig mismatch.")
    print()
    state = report_cell(cell)
    failures = report_measured_rig(cell, state["runs"])
    failures += report_ablation_mount(
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

    # THE EXIT CODE (finding I1). This pass used to `return 0` unconditionally,
    # so nothing it printed could make it fail -- an ablation-side MISMATCH
    # filed as a passing artifact just like a clean run. An instrument that
    # cannot fail is not an instrument.
    print("## rig verdict")
    print()
    if failures:
        print(f"**{len(failures)} RIG FAILURE(S)** -- this pass exits 1.")
        print()
        for f in failures:
            print(f"- {f}")
        print()
        return 1
    print(f"PASS: every non-excluded run of cell {cell} at class `{CLASS_ID}` "
          "carries the rig its manifest claims, on both arms.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
