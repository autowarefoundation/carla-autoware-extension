"""Task 13 per-run integrity pass (brief Step 2). Read-only over results/.

Task 12's checks, per run: manifest.validate() is empty, duel_id == "A+B-cyc",
duel_admissible is True, quality.json is present, the clock-stall watchdog
marker is absent, and any exclusion reason is one the frozen exclusions.md
criteria admit (manifest.known_exclusion_reason).

PLUS the two closed-loop checks this task adds:
  * engage recorded -- arm.log carries arm_and_goal.py's engage publish
    (`/autoware/engage: published engage=true`, arm_and_goal.py:730) AND its
    ARMED verdict line (`ARMED: ... autonomous engaged`, :936). Both are
    required: the publish alone is not the verdict, and the verdict line is
    what run.sh's step 9 exit code is derived from.
  * `goal_closest_approach_m` non-null in quality.json.

Also answers Q1 (does cell A's CLOSED-LOOP arm populate published_time.csv?)
with PROVENANCE.md section 15.5's three named checks.

NO-PEEKING DISCIPLINE, and why this file prints what it prints. Task 16 owns
the only comparison; this pass is an integrity pass, so it prints the CHECKS
rather than the measured values behind them. Concretely:

  * `goal_closest_approach_m` is reported as non-null / null, which is the
    check the brief states. The metre value stays in each run's own
    quality.json, where it is auditable, rather than being tabulated for two
    cells side by side here.
  * section 15.5's row counts are printed in full for cell A ONLY, because
    they ARE Q1's evidence and Q1 is cell-A-specific by construction. Cell
    B-cyc's counterpart is reported as the same three checks in boolean form:
    the within-run identity is verifiable without putting a second cell's
    absolute control-command counts on the same page.

This mirrors Task 12's convention, which printed cell B-cyc's `ndt_rate_ratio`
because its brief asked for it within-cell and deliberately did not print cell
A's. No cross-cell statistic is computed anywhere in this file.
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path("/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0")
sys.path.insert(0, str(ROOT))

from benchmarks.analysis.manifest import known_exclusion_reason, load_manifest  # noqa: E402

RESULTS = ROOT / "benchmarks" / "results"
# Runs that already existed before Task 13 started; anything at or below these
# indices is prior evidence (Task 12's static duel and earlier), not this
# task's closed-loop collection.
PRE_TASK13 = {"A": 25, "B-cyc": 11}

CONTROL_CMD = "/control/command/control_cmd"
PUBLISHED_TIME_TOPIC = "/control/command/control_cmd/debug/published_time"

ENGAGE_PUBLISH = "/autoware/engage: published engage=true"
ARMED_PREFIX = "ARMED:"


def published_time_facts(d: Path) -> dict:
    """PROVENANCE.md section 15.5's three checks, verbatim in intent."""
    p = d / "published_time.csv"
    if not p.exists():
        return {"pt_rows": None, "pt_topics": [], "pt_all_registered": None}
    with p.open() as fh:
        rows = list(csv.DictReader(fh))
    topics = sorted({r["topic"] for r in rows})
    return {
        "pt_rows": len(rows),
        "pt_topics": topics,
        "pt_all_registered": bool(rows) and topics == [PUBLISHED_TIME_TOPIC],
    }


def observer_control_cmd_rows(d: Path) -> int | None:
    p = d / "observer.csv"
    if not p.exists():
        return None
    n = 0
    with p.open() as fh:
        for r in csv.DictReader(fh):
            if r["topic"] == CONTROL_CMD:
                n += 1
    return n


def arm_facts(d: Path) -> dict:
    p = d / "arm.log"
    if not p.exists():
        return {"arm_log": False, "engage_published": None, "armed_line": None}
    text = p.read_text(errors="replace")
    return {
        "arm_log": True,
        "engage_published": ENGAGE_PUBLISH in text,
        "armed_line": any(ln.startswith(ARMED_PREFIX) for ln in text.splitlines()),
    }


def rows(cell: str):
    out = []
    for d in sorted((RESULTS / cell).glob("run-*")):
        idx = int(d.name.split("-")[1])
        if idx <= PRE_TASK13[cell]:
            continue
        m = load_manifest(d / "manifest.json")
        errs = m.validate()
        q = d / "quality.json"
        qd = json.loads(q.read_text()) if q.exists() else None
        reason = m.exclusion_reason
        rec = {
            "run": f"{cell}/{d.name}",
            "arm": m.arm,
            "manifest_valid": not errs,
            "manifest_errors": errs,
            "duel_id": m.duel_id,
            "duel_id_ok": m.duel_id == "A+B-cyc",
            "duel_admissible": m.duel_admissible,
            "quality_json": q.exists(),
            "watchdog_marker": (d / "clock_stall.marker").exists(),
            "excluded": m.excluded,
            "exclusion_reason": reason,
            "reason_known": known_exclusion_reason(reason) if reason else None,
            "gate_pass": qd.get("gate_pass") if qd else None,
            "reasons": qd.get("reasons") if qd else None,
            "goal_closest_approach_m": (qd.get("goal_closest_approach_m") if qd else None),
            "quality_arm": qd.get("arm") if qd else None,
            "cc_rows": observer_control_cmd_rows(d),
        }
        rec.update(arm_facts(d))
        rec.update(published_time_facts(d))
        rec["engage_recorded"] = bool(rec["engage_published"]) and bool(rec["armed_line"])
        rec["goal_non_null"] = rec["goal_closest_approach_m"] is not None
        out.append(rec)
    return out


def integrity_table(label: str, recs: list[dict]) -> None:
    print(f"\n## integrity pass -- {label}")
    print(
        f"{'run':<16} {'arm':<11} {'mval':<5} {'duel_id':<10} {'adm':<5} "
        f"{'qual':<5} {'wdog':<5} {'excl':<5} {'engage':<7} {'goal!=None':<10} reason"
    )
    for r in recs:
        print(
            f"{r['run']:<16} {r['arm']:<11} {str(r['manifest_valid']):<5} "
            f"{r['duel_id']:<10} {str(r['duel_admissible']):<5} "
            f"{str(r['quality_json']):<5} {str(r['watchdog_marker']):<5} "
            f"{str(r['excluded']):<5} {str(r['engage_recorded']):<7} "
            f"{str(r['goal_non_null']):<10} {r['exclusion_reason'] or '-'}"
            + (f"  [reason_known={r['reason_known']}]" if r["exclusion_reason"] else "")
        )
        if r["manifest_errors"]:
            print(f"    MANIFEST ERRORS: {r['manifest_errors']}")


def q1_table_cell_a(recs: list[dict]) -> None:
    """Q1's evidence in full. Cell A only -- see the no-peeking note above."""
    print("\n## Q1 -- PROVENANCE section 15.5's three checks, cell A (within-cell gate fact)")
    print(f"{'run':<16} {'pt_rows':>8} {'cc_rows':>8} {'ratio':>7}  all_rows_registered_topic  topics")
    for r in recs:
        pt, cc = r["pt_rows"], r["cc_rows"]
        ratio = f"{pt / cc:.3f}" if pt and cc else "-"
        print(
            f"{r['run']:<16} {str(pt):>8} {str(cc):>8} {ratio:>7}  "
            f"{str(r['pt_all_registered']):<25}  {','.join(r['pt_topics']) or '-'}"
        )


def q1_checks_only(label: str, recs: list[dict]) -> None:
    """The same three checks, boolean form, with no absolute counts printed."""
    print(f"\n## PROVENANCE section 15.5's three checks, {label} -- CHECKS ONLY (no counts)")
    print(f"{'run':<16} {'non_empty':<10} {'all_registered_topic':<21} {'rows==cc_rows':<14}")
    for r in recs:
        pt, cc = r["pt_rows"], r["cc_rows"]
        print(
            f"{r['run']:<16} {str(bool(pt)):<10} {str(r['pt_all_registered']):<21} "
            f"{str(pt == cc):<14}"
        )


def main():
    a = rows("A")
    b = rows("B-cyc")
    print(f"# new runs: A={len(a)}  B-cyc={len(b)}")

    integrity_table("cell A", a)
    integrity_table("cell B-cyc", b)

    print("\n## closed-loop checks summary (per cell, no comparison)")
    for label, recs in (("A", a), ("B-cyc", b)):
        print(
            f"{label:<6} engage_recorded {sum(r['engage_recorded'] for r in recs)}/{len(recs)}   "
            f"goal_closest_approach_m non-null {sum(r['goal_non_null'] for r in recs)}/{len(recs)}   "
            f"arm=='closed-loop' {sum(r['arm'] == 'closed-loop' for r in recs)}/{len(recs)}   "
            f"quality.arm=='closed-loop' {sum(r['quality_arm'] == 'closed-loop' for r in recs)}/{len(recs)}"
        )

    q1_table_cell_a(a)
    q1_checks_only("cell B-cyc", b)

    admissible_a = [r for r in a if not r["excluded"]]
    admissible_b = [r for r in b if not r["excluded"]]
    print(f"\n## admissible: A={len(admissible_a)}  B-cyc={len(admissible_b)}")
    print(f"## admissible PAIRS (min of the two) = {min(len(admissible_a), len(admissible_b))}")


if __name__ == "__main__":
    main()
