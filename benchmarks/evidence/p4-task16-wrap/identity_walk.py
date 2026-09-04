#!/usr/bin/env python3
"""The P4 wrap's identity walk -- everything section 9 of the wrap doc asserts.

    PYTHONPATH=. python3 benchmarks/evidence/p4-task16-wrap/identity_walk.py

Read-only over `benchmarks/results/*/run-*/manifest.json`. It writes nothing,
opens no run directory beyond its manifest, and is deterministic.

WHY THIS EXISTS AS A FILED SCRIPT rather than a heredoc in the wrap doc. Task
16's review round 1 raised two findings that were really one defect: the wrap's
BuildId sentence carried a run count (`91`) that NO filed command produced and
that is reconstructible from no partition of the filed data, and the walk it was
cited to aggregated only `engine_build_id` / `autoware_image` /
`dds_profile_sha256` -- so section 9.2's entire table (per-pool
`harness_git_sha`) and 9.3's `patches_git_sha` claim had no runnable command
behind them, against the document's own rule that every number does. Replacing
the count with a better guess would have left that hole open. This walk closes
it at the source: it emits the census, the count, the partition it counted, AND
the per-pool sha table, so every figure in section 9 comes out of one
invocation.

THE P4 BOUNDARY IS DERIVED, NOT ASSERTED, and that is the whole point of
`P4_PATCHES`. `patches_git_sha` is `git log -1 --format=%H --
benchmarks/patches/` (`write_manifest.py:30`), and it moved to `7000c785` --
Task 9's registered relink commit -- exactly at the P3->P4 transition. Selecting
on it therefore partitions the filed runs by the same event that moved the
engine BuildId, rather than by a hand-maintained list of run-id ranges that
would drift the moment a run is added. The partition it produces disagrees with
the range-based guess `A/016-053 + B-cyc/001-045 + CAL-seam/001-005` by one run,
and the disagreement is a fact worth surfacing rather than smoothing: the P4
boundary in cell A falls at `run-015` (Task 11's cell-A bring-up), not
`run-016`. `A/run-015` is the first cell-A run carrying both `7000c78` and
`bc08ce19`; `A/run-014` carries `ccff4f9` / `4210e602` and a 2026-07-31 P3-era
harness sha.

THE THREE COUNTS ARE DIFFERENT QUESTIONS and the output keeps them apart:
84 manifests carry `engine_build_id = bc08ce19` (the only ones the identity
claim is about), 89 filed runs are P4 runs, and the difference is CAL-seam's
five, which carry NO BuildId key at all. That absence is PROVENANCE 12.2's
structural finding -- `preflight.sh`'s BuildId check is gated on
`APPROACH = extension | tier4-native` and CAL-seam registers `calibration` --
not drift, and a walk that silently folded `None` into a total would hide
exactly the thing 12.2 exists to record.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter, defaultdict

# Task 9's relink commit: the sha `patches_git_sha` moved to at the P3->P4
# boundary. See the module docstring on why this, and not a run-id range.
P4_PATCHES = "7000c785"

RESULTS = pathlib.Path("benchmarks/results")


def short(sha: str) -> str:
    """Abbreviate a manifest sha WITHOUT dropping its `-dirty` suffix.

    `sha[:7]` is wrong here and the wrap depends on it being wrong:
    `write_manifest.py:19-22` appends `-dirty` when the working tree differed
    from HEAD, and a truncating census structurally cannot surface the one
    property of these two keys most worth surfacing. Two pools in this campaign
    are `-dirty` (both cells' vlp16 sweeps) and the duel pools are not; that
    contrast is a provenance claim the wrap makes, so it has to survive
    abbreviation.
    """
    head, _, tail = sha.partition("-")
    return head[:7] + ("-" + tail if tail else "")


def pool_of(m: dict) -> str:
    """Name the pool a run belongs to, from the manifest alone.

    Deliberately derived rather than looked up: an excluded run is named as
    excluded FIRST (so the six criterion-3 exclusions never merge into the
    scored 32ch pool), sweep arms are keyed by class, and duel membership is
    read off `duel_admissible` so a bring-up run cannot be counted into a
    verdict's pool by accident.
    """
    if m["excluded"]:
        return f"{m['_cell']} EXCLUDED"
    arm = m["arm"]
    if arm in ("paced", "unpaced", "ablation"):
        # A sweep manifest predating `class_id` carries "", which
        # `sweep_verdict._class_admits` reads as vlp16; mirror that rule here
        # rather than inventing a second one.
        return f"{m['_cell']} sweep {m.get('class_id', '') or 'vlp16'}"
    if not m["duel_admissible"]:
        return f"{m['_cell']} {arm} non-duel"
    return f"{m['_cell']} {arm} duel"


def main() -> int:
    runs = []
    for p in sorted(RESULTS.glob("*/run-*/manifest.json")):
        m = json.loads(p.read_text())
        m["_cell"], m["_run"] = p.parent.parent.name, p.parent.name
        runs.append(m)

    # 1. Campaign-wide engine_build_id census. Counted over EVERY filed
    #    manifest, not only P4's, so a `4210e602` leaking into a P4 pool would
    #    be visible as a non-zero count next to a P4 range below.
    census = Counter(str(m["placement"].get("engine_build_id")) for m in runs)
    print(f"engine_build_id over all {len(runs)} filed manifests:")
    for key, n in sorted(census.items(), key=lambda kv: -kv[1]):
        print(f"  {key:<40} {n}")

    # 2. The P4 partition, derived from the relink sha.
    p4 = [m for m in runs if m["patches_git_sha"].startswith(P4_PATCHES)]
    by_cell: dict[str, list[str]] = defaultdict(list)
    for m in p4:
        by_cell[m["_cell"]].append(m["_run"])
    print(f"\nP4 runs (patches_git_sha startswith {P4_PATCHES}): {len(p4)}")
    for cell, run_ids in sorted(by_cell.items()):
        bid = Counter(
            str(m["placement"].get("engine_build_id"))[:8] for m in p4 if m["_cell"] == cell
        )
        print(
            f"  {cell:<10} {run_ids[0]}..{run_ids[-1]}  n={len(run_ids):<3} "
            f"engine_build_id={dict(bid)}"
        )

    # 3. Per-pool identity, over the P4 partition only. Sets, not first-wins:
    #    a pool spanning two shas must RENDER as two, which is how B-cyc's
    #    32ch pool discloses its re-collection split.
    agg: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for m in p4:
        a = agg[pool_of(m)]
        a["n"].add(m["_run"])
        a["harness"].add(short(m["harness_git_sha"]))
        a["patches"].add(short(m["patches_git_sha"]))
        a["buildid"].add(str(m["placement"].get("engine_build_id"))[:8])
        a["image"].add(m["autoware_image"].rsplit("/", 1)[-1][:24])
        a["dds"].add(m["transport"]["dds_profile_sha256"][:8] or "(none)")
    print()
    for name in sorted(agg):
        a = agg[name]
        print(
            f"  {name:<28} n={len(a['n']):<3} harness={sorted(a['harness'])} "
            f"patches={sorted(a['patches'])} buildid={sorted(a['buildid'])} "
            f"image={sorted(a['image'])} dds={sorted(a['dds'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
