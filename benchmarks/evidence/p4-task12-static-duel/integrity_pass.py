"""Task 12 per-run integrity pass (brief Step 2). Read-only over results/.

Checks, per run: manifest.validate() is empty, duel_id == "A+B-cyc",
duel_admissible is True, quality.json is present, the clock-stall watchdog
marker is absent, and any exclusion reason is one the frozen
exclusions.md criteria admit (manifest.known_exclusion_reason).

Also emits each B-cyc run's own ndt_rate_ratio (brief Step 3, within-cell).
Cell A's counterpart is deliberately NOT read or printed.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0")

from benchmarks.analysis.manifest import known_exclusion_reason, load_manifest

RESULTS = Path("/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0/benchmarks/results")
# Runs that already existed before Task 12 started; anything at or below these
# indices is prior evidence, not this task's collection.
PRE_TASK12 = {"A": 15, "B-cyc": 1}


def rows(cell: str):
    out = []
    for d in sorted((RESULTS / cell).glob("run-*")):
        idx = int(d.name.split("-")[1])
        if idx <= PRE_TASK12[cell]:
            continue
        m = load_manifest(d / "manifest.json")
        errs = m.validate()
        q = d / "quality.json"
        qd = json.loads(q.read_text()) if q.exists() else None
        reason = m.exclusion_reason
        out.append(
            {
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
                "ndt_rate_ratio": qd.get("ndt_rate_ratio") if qd else None,
            }
        )
    return out


def main():
    a = rows("A")
    b = rows("B-cyc")
    print(f"# new runs: A={len(a)}  B-cyc={len(b)}\n")
    print("## integrity pass (both cells; no measured value of cell A is printed)")
    hdr = f"{'run':<16} {'arm':<7} {'mval':<5} {'duel_id':<10} {'adm':<5} {'qual':<5} {'wdog':<5} {'excl':<5} reason"
    print(hdr)
    for r in a + b:
        print(
            f"{r['run']:<16} {r['arm']:<7} {str(r['manifest_valid']):<5} "
            f"{r['duel_id']:<10} {str(r['duel_admissible']):<5} "
            f"{str(r['quality_json']):<5} {str(r['watchdog_marker']):<5} "
            f"{str(r['excluded']):<5} {r['exclusion_reason'] or '-'}"
            + (f"  [reason_known={r['reason_known']}]" if r["exclusion_reason"] else "")
        )
        if r["manifest_errors"]:
            print(f"    MANIFEST ERRORS: {r['manifest_errors']}")

    print("\n## Step 3 -- B-cyc ndt_rate_ratio (within-cell gate fact)")
    for r in b:
        print(
            f"{r['run']:<16} ndt_rate_ratio={r['ndt_rate_ratio']}  "
            f"gate_pass={r['gate_pass']}  reasons={r['reasons']}"
        )
    vals = [r["ndt_rate_ratio"] for r in b if r["ndt_rate_ratio"] is not None and not r["excluded"]]
    if vals:
        print(f"\nB-cyc admissible n={len(vals)}  min={min(vals):.6f}  max={max(vals):.6f}")
        print(f"all >= 0.9: {all(v >= 0.9 for v in vals)}")

    admissible_a = [r for r in a if not r["excluded"]]
    admissible_b = [r for r in b if not r["excluded"]]
    print(f"\n## admissible: A={len(admissible_a)}  B-cyc={len(admissible_b)}")
    print(f"## admissible PAIRS (min of the two) = {min(len(admissible_a), len(admissible_b))}")


if __name__ == "__main__":
    main()
